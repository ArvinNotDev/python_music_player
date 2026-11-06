from __future__ import annotations

import pytest
from PIL import Image
import io

mutagen = pytest.importorskip("mutagen", reason="install mutagen>=1.47 to run audio tag integration tests")
pytest.importorskip("PIL", reason="install Pillow>=9.1 to run artwork integration tests")

from mutagen.id3 import APIC, COMM, ID3, TXXX, USLT, TIT2, TPE1, TALB

from core.metadata import MetadataService
from core.metadata.lyrics_service import LyricsService
from core.metadata.tagging import embedded_artwork, read_metadata
from core.models import Track
from database.repositories.track_repository import TrackRepository


def _png():
    image = Image.new("RGB", (4, 4), (10, 20, 30))
    data = io.BytesIO()
    image.save(data, format="PNG")
    return data.getvalue()


def _make_mp3(path):
    frame = b"\xff\xfb\x90\x64" + b"\x00" * 413
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"")
    tags = ID3()
    tags.add(TIT2(encoding=3, text="Initial"))
    tags.add(TPE1(encoding=3, text="Artist"))
    tags.add(TALB(encoding=3, text="Album"))
    tags.add(TXXX(encoding=3, desc="Custom", text="preserve me"))
    tags.add(COMM(encoding=3, lang="eng", desc="", text="original comment"))
    tags.add(COMM(encoding=3, lang="eng", desc="other", text="preserve comment"))
    tags.add(USLT(encoding=3, lang="eng", desc="", text="[00:01.00]lyric"))
    tags.add(APIC(encoding=3, mime="image/png", type=3, desc="Cover", data=_png()))
    tags.save(path)
    with path.open("ab") as stream:
        stream.write(frame * 12)


def test_metadata_read_write_preserves_unrelated_id3_frames(database, tmp_path):
    audio = tmp_path / "song.mp3"
    _make_mp3(audio)
    metadata = read_metadata(audio)
    assert metadata.title == "Initial"
    assert metadata.artist == "Artist"
    assert metadata.album == "Album"
    tracks = TrackRepository(database)
    track, _ = tracks.upsert(metadata, file_size=audio.stat().st_size, file_mtime_ns=audio.stat().st_mtime_ns)
    service = MetadataService(tracks)
    updated = service.write_metadata(track.id, {"title": "夜曲", "comment": "new comment", "track_number": 2})
    assert updated.title == "夜曲"
    assert updated.comment == "new comment"
    assert updated.track_number == 2
    raw = ID3(audio)
    assert raw.getall("TXXX")[0].text == ["preserve me"]
    assert any(frame.desc == "other" and frame.text == ["preserve comment"] for frame in raw.getall("COMM"))
    assert raw.getall("USLT")[0].text == "[00:01.00]lyric"
    assert raw.getall("APIC")


def test_embedded_artwork_replace_and_remove(database, tmp_path):
    audio = tmp_path / "song.mp3"
    _make_mp3(audio)
    track, _ = TrackRepository(database).upsert(Track(None, str(audio), title="Track"))
    service = MetadataService(TrackRepository(database))
    new_art = _png()
    service.write_artwork(track.id, new_art)
    assert embedded_artwork(audio) == new_art
    service.write_artwork(track.id, None)
    assert embedded_artwork(audio) is None


def test_unsupported_metadata_change_is_rejected_before_writing(database, tmp_path):
    audio = tmp_path / "song.mp3"
    _make_mp3(audio)
    tracks = TrackRepository(database)
    track, _ = tracks.upsert(Track(None, str(audio), title="Initial"))
    service = MetadataService(tracks)
    with pytest.raises(Exception, match="cannot be written as tags"):
        service.write_metadata(track.id, {"duration_ms": 1000})
    assert read_metadata(audio).title == "Initial"


def test_embedded_lyrics_report_storage_and_return_structured_document(database, tmp_path):
    audio = tmp_path / "song.mp3"
    _make_mp3(audio)
    tracks = TrackRepository(database)
    track, _ = tracks.upsert(Track(None, str(audio), title="Initial"))
    lyrics = LyricsService(tracks)
    saved = lyrics.save_lyrics(track.id, "[00:01.25]سلام\n[00:02.00]دنیا", "lrc", "embedded")
    assert saved.embedded is True and saved.storage == "embedded"
    loaded = lyrics.get_lyrics(track.id)
    assert [line.timestamp_ms for line in loaded.lines] == [1250, 2000]
    raw = ID3(audio)
    assert raw.getall("USLT")[0].text == "[00:01.25]سلام\n[00:02.00]دنیا"
