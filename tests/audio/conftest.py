"""Deterministic audio fixtures that do not require an output device."""

from __future__ import annotations

from dataclasses import dataclass

import pytest
from PySide6.QtCore import QCoreApplication

from core.audio.audio_backend import AudioBackend
from core.audio.audio_engine import AudioEngine
from core.audio.playback_controller import PlaybackController


@dataclass
class TestTrack:
    id: int
    path: str
    title: str
    artist: str = "Artist"
    album: str = "Album"
    album_artist: str = "Artist"
    duration_ms: int = 12_000
    artwork_path: str | None = None


class FakeBackend(AudioBackend):
    """Signal-compatible backend controlled directly by each unit test."""

    def __init__(self) -> None:
        super().__init__()
        self._state = "stopped"
        self._position = 0
        self._duration = 0
        self._seekable = False
        self._media_status = "nomedia"
        self._volume = 1.0
        self._muted = False
        self.source: str | None = None
        self.play_requests = 0
        self.pause_requests = 0
        self.stop_requests = 0
        self.seek_requests: list[int] = []
        self.shutdown_requests = 0

    @property
    def state(self) -> str:
        return self._state

    @property
    def position(self) -> int:
        return self._position

    @property
    def duration(self) -> int:
        return self._duration

    @property
    def seekable(self) -> bool:
        return self._seekable

    @property
    def media_status(self) -> str:
        return self._media_status

    @property
    def volume(self) -> float:
        return self._volume

    @property
    def is_muted(self) -> bool:
        return self._muted

    def set_source(self, path: str) -> None:
        self.source = path
        self._position = 0
        self._duration = 0
        self._seekable = False
        self._media_status = "loadingmedia"
        self.position_changed.emit(0)
        self.duration_changed.emit(0)
        self.seekable_changed.emit(False)
        self.media_status_changed.emit(self._media_status)

    def play(self) -> None:
        self.play_requests += 1

    def pause(self) -> None:
        self.pause_requests += 1

    def stop(self) -> None:
        self.stop_requests += 1
        self._state = "stopped"
        self._position = 0
        if self._media_status == "endofmedia":
            self._media_status = "loadedmedia"
        self.state_changed.emit(self._state)
        self.position_changed.emit(0)

    def seek(self, position_ms: int) -> None:
        if not self._seekable:
            return
        value = max(0, min(position_ms, self._duration or position_ms))
        self.seek_requests.append(value)
        self._position = value
        self.position_changed.emit(value)

    def set_volume(self, volume: float) -> None:
        value = max(0.0, min(float(volume), 1.0))
        if value == self._volume:
            return
        self._volume = value
        self.volume_changed.emit(value)

    def set_muted(self, muted: bool) -> None:
        value = bool(muted)
        if value == self._muted:
            return
        self._muted = value
        self.muted_changed.emit(value)

    def shutdown(self) -> None:
        self.shutdown_requests += 1
        self.stop()

    def start_playing(self) -> None:
        """Report that playback actually started."""
        self._media_status = "loadedmedia"
        self._state = "playing"
        self.media_status_changed.emit(self._media_status)
        self.state_changed.emit(self._state)

    def set_seekable(self, value: bool, duration_ms: int = 12_000) -> None:
        self._seekable = value
        self._duration = duration_ms
        self._media_status = "loadedmedia"
        self.seekable_changed.emit(value)
        self.duration_changed.emit(duration_ms)
        self.media_status_changed.emit(self._media_status)

    def complete(self) -> None:
        """Emit the same end-of-media events consumed by the controller."""
        self._media_status = "endofmedia"
        self._state = "stopped"
        self.media_status_changed.emit(self._media_status)
        self.state_changed.emit(self._state)
        self.end_of_media.emit()
        if self._media_status == "endofmedia":
            self._media_status = "loadedmedia"

    def fail(self, message: str = "decode failed") -> None:
        self.error_occurred.emit(message)


@pytest.fixture(scope="session", autouse=True)
def qcore_application() -> QCoreApplication:
    """Keep a Qt application alive for QObject and Multimedia tests."""
    app = QCoreApplication.instance()
    if app is None:
        app = QCoreApplication([])
    return app


@pytest.fixture
def make_files(tmp_path):
    """Create local placeholder files accepted by path validation."""

    def create(*names: str) -> list[TestTrack]:
        tracks = []
        for index, name in enumerate(names, 1):
            path = tmp_path / f"{name}.wav"
            path.write_bytes(b"test audio")
            tracks.append(TestTrack(index, str(path), name))
        return tracks

    return create


@pytest.fixture
def controller_factory(make_files):
    """Build a controller with an inspectable fake backend and real paths."""
    instances: list[tuple[PlaybackController, FakeBackend]] = []

    def create(names: tuple[str, ...] = ("one", "two", "three"), **kwargs):
        tracks = make_files(*names)
        backend = FakeBackend()
        controller = PlaybackController(AudioEngine(backend), **kwargs)
        instances.append((controller, backend))
        return controller, backend, tracks

    yield create
    for controller, _ in instances:
        controller.shutdown()
