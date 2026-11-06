from __future__ import annotations

import json
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PIL import Image
from PySide6.QtCore import QEventLoop, QThreadPool, QTimer
from PySide6.QtWidgets import QApplication
from mutagen.id3 import ID3, TALB, TIT2, TPE1

from app.bootstrap import build_runtime
from core.audio.audio_backend import AudioBackend
from core.audio.audio_engine import AudioEngine
from core.metadata.tagging import embedded_artwork
from core.models import Track


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


class _TestBackend(AudioBackend):
    def __init__(self):
        super().__init__()
        self._state = "stopped"
        self._position = 0
        self._duration = 0
        self._seekable = False
        self._media_status = "nomedia"
        self._volume = 1.0
        self._muted = False
        self.source_count = 0

    @property
    def state(self):
        return self._state

    @property
    def position(self):
        return self._position

    @property
    def duration(self):
        return self._duration

    @property
    def seekable(self):
        return self._seekable

    @property
    def media_status(self):
        return self._media_status

    @property
    def volume(self):
        return self._volume

    @property
    def is_muted(self):
        return self._muted

    def set_source(self, path):
        self.source_count += 1
        self._position = 0
        self._duration = 120_000
        self._seekable = True
        self._media_status = "loadedmedia"
        self.duration_changed.emit(self._duration)
        self.seekable_changed.emit(True)
        self.media_status_changed.emit(self._media_status)

    def play(self):
        self._state = "playing"
        self.state_changed.emit(self._state)

    def pause(self):
        self._state = "paused"
        self.state_changed.emit(self._state)

    def stop(self):
        self._state = "stopped"
        self._position = 0
        self.state_changed.emit(self._state)

    def seek(self, position_ms):
        self._position = int(position_ms)
        self.position_changed.emit(self._position)

    def set_volume(self, volume):
        self._volume = float(volume)
        self.volume_changed.emit(self._volume)

    def set_muted(self, muted):
        self._muted = bool(muted)
        self.muted_changed.emit(self._muted)

    def shutdown(self):
        self.stop()


def _build(qapp, database_path: Path, tmp_path: Path, *, candidates=None, migrate=True):
    backend = _TestBackend()
    runtime = build_runtime(
        ["sonora-test"],
        database_path=database_path,
        legacy_candidates=candidates,
        migrate_legacy=migrate,
        application=qapp,
        audio_engine=AudioEngine(backend),
        log_path=tmp_path / "logs" / "sonora.log",
    )
    QThreadPool.globalInstance().waitForDone(5_000)
    qapp.processEvents()
    return runtime, backend


def _make_mp3(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"")
    tags = ID3()
    tags.add(TIT2(encoding=3, text="Original title"))
    tags.add(TPE1(encoding=3, text="Test artist"))
    tags.add(TALB(encoding=3, text="Test album"))
    tags.save(path)
    frame = b"\xff\xfb\x90\x64" + b"\x00" * 413
    with path.open("ab") as stream:
        stream.write(frame * 12)


def test_application_startup_empty_library_and_idempotent_legacy_migration(qapp, tmp_path):
    legacy = tmp_path / "playlists.json"
    legacy.write_text(json.dumps({"Favorites": [str(tmp_path / "missing.mp3")], "Road Trip": []}), encoding="utf-8")
    database = tmp_path / "library.sqlite3"

    runtime, _ = _build(qapp, database, tmp_path, candidates=[legacy])
    try:
        assert runtime.window.windowTitle().startswith("Sonora")
        assert runtime.window.library_service is runtime.services.library
        assert runtime.window.playback_controller is runtime.services.playback_ui
        assert runtime.window._tracks == []
        assert {playlist.name for playlist in runtime.services.playlists.list_playlists()} == {"Favorites", "Road Trip"}
        migration = runtime.services.migrate_legacy_playlists([legacy])
        assert migration.migrated_files == []
        assert list(tmp_path.glob("playlists.json.backup-*"))
    finally:
        runtime.shutdown()

    restarted, _ = _build(qapp, database, tmp_path, candidates=[legacy])
    try:
        playlists = restarted.services.playlists.list_playlists()
        assert [playlist.name for playlist in playlists].count("Road Trip") == 1
        assert restarted.services.library.list_tracks() == []
    finally:
        restarted.shutdown()


def test_default_multimedia_backend_starts_without_audio_files(qapp, tmp_path):
    runtime = build_runtime(
        ["sonora-smoke"],
        database_path=tmp_path / "fresh.sqlite3",
        legacy_candidates=[],
        application=qapp,
        log_path=tmp_path / "logs" / "smoke.log",
    )
    try:
        assert runtime.services.playback.current_track is None
        assert runtime.services.library.list_tracks() == []
        assert runtime.window.pages["home"] is runtime.window.home_page
    finally:
        runtime.shutdown()


def test_background_scan_publishes_new_tracks_to_the_open_window(qapp, tmp_path):
    runtime, _ = _build(qapp, tmp_path / "library.sqlite3", tmp_path, migrate=False)
    try:
        folder = tmp_path / "Music"
        folder.mkdir()
        _make_mp3(folder / "new-track.mp3")
        runtime.services.library.add_library_folder(folder)
        runtime.services.settings.set("library.folders", [str(folder)])

        loop = QEventLoop()
        results = []
        runtime.services.library.scan_completed.connect(lambda result: (results.append(result), loop.quit()))
        worker = runtime.services.library.scan_library()
        QTimer.singleShot(10_000, loop.quit)
        loop.exec()
        assert worker.wait(1_000)
        QThreadPool.globalInstance().waitForDone(5_000)
        qapp.processEvents()

        assert results and results[0].added == 1
        assert len(runtime.services.library.list_tracks()) == 1
        assert len(runtime.window._tracks) == 1
        assert runtime.window._tracks[0].title == "Original title"
    finally:
        runtime.shutdown()


def test_real_service_and_controller_contracts_work_through_ui_adapters(qapp, tmp_path):
    database = tmp_path / "library.sqlite3"
    runtime, backend = _build(qapp, database, tmp_path, migrate=False)
    try:
        tracks = []
        for name in ("first.wav", "second.wav", "third.wav"):
            path = tmp_path / name
            path.write_bytes(b"test audio")
            track, _ = runtime.services.domain.tracks.upsert(
                Track(None, str(path), title=path.stem, duration_ms=120_000)
            )
            tracks.append(track)

        player = runtime.services.playback_ui
        player.play_queue(tracks[:2], start_index=1)
        assert player.current_track.id == tracks[1].id
        assert player.current_queue_index == 1
        assert runtime.services.playback.position == 0
        player.seek(12.345)
        assert runtime.services.playback.position == 12_345
        assert player.position == pytest.approx(12.345)

        refreshed = runtime.services.domain.tracks.set_metadata(tracks[1].id, {"title": "Second revised"})
        source_count = backend.source_count
        assert player.controller.refresh_track(refreshed)
        assert player.current_track.title == "Second revised"
        assert runtime.window.playback_bar.position == pytest.approx(12.345)
        assert backend.source_count == source_count

        player.play_next(tracks[2])
        assert [track.id for track in player.queue] == [tracks[0].id, tracks[1].id, tracks[2].id]
        source_count = backend.source_count
        player.remove_from_queue(0)
        assert player.current_track.id == tracks[1].id
        assert player.current_queue_index == 0
        assert backend.source_count == source_count
        player.set_muted(True)
        assert player.is_muted and runtime.window.playback_bar.muted

        mp3_path = tmp_path / "tags" / "tagged.mp3"
        _make_mp3(mp3_path)
        tagged, _ = runtime.services.domain.tracks.upsert(Track(None, str(mp3_path), title="Original title"))
        metadata = runtime.services.metadata
        assert metadata.read_metadata(tagged)["title"] == "Original title"
        metadata.write_metadata(tagged, {"title": "Updated title"})
        assert runtime.services.library.get_track(tagged.id).title == "Updated title"

        cover_path = tmp_path / "cover.png"
        Image.new("RGB", (12, 12), (20, 40, 80)).save(cover_path)
        metadata.write_metadata(tagged, {"artwork_path": str(cover_path)})
        assert embedded_artwork(mp3_path) is not None

        lyrics = runtime.services.lyrics
        lyrics.save_lyrics(tagged, "[00:01.25]First line", mode="lrc", storage="sidecar")
        assert lyrics.get_lyrics(tagged) == "[00:01.25]First line"
        assert runtime.services.settings.get("lyrics.storage") == "sidecar"

        playlists = runtime.services.playlists
        favorites = next(item for item in playlists.list_playlists() if item.is_favorite)
        playlists.add_track(favorites.id, tagged.id)
        assert [track.id for track in playlists.list_favorites()] == [tagged.id]
        mix = playlists.create_playlist("Integration Mix")
        playlists.add_track(mix.id, tracks[0].id)
        playlists.add_track(mix.id, tracks[1].id)
        playlists.move_track(mix.id, tracks[1].id, 0)
        assert [track.id for track in playlists.get_playlist_tracks(mix.id)] == [tracks[1].id, tracks[0].id]
        assert runtime.services.history.recently_played(1)[0].id == tracks[1].id
    finally:
        runtime.shutdown()

    restarted, _ = _build(qapp, database, tmp_path, migrate=False)
    try:
        mix = next(item for item in restarted.services.playlists.list_playlists() if item.name == "Integration Mix")
        assert [track.id for track in restarted.services.playlists.get_playlist_tracks(mix.id)] == [tracks[1].id, tracks[0].id]
        assert restarted.services.playlists.is_favorite(tagged.id)
        assert restarted.services.settings.get("lyrics.storage") == "sidecar"
    finally:
        restarted.shutdown()
