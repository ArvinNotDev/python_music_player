from __future__ import annotations

import io

import pytest
pytest.importorskip("PIL", reason="install Pillow>=9.1 to run artwork cache tests")
from PIL import Image

from core.metadata.artwork_manager import ArtworkManager
from core.metadata.lyrics_service import LyricsService, parse_lrc
from core.models import LyricsDocument, LyricsLine, Track
from database.repositories.track_repository import TrackRepository


def _png(color=(40, 120, 220), size=(1200, 900)):
    image = Image.new("RGB", size, color)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def test_lrc_parses_fractional_timestamps_multiple_times_and_malformed_lines():
    document = parse_lrc("[ti:曲名]\n[00:01.25][00:02:500]سلام\n[bad timestamp]keep\n[00:60.00]bad seconds")
    assert document.format == "lrc"
    assert document.metadata["ti"] == "曲名"
    assert [line.timestamp_ms for line in document.lines[:2]] == [1250, 2500]
    assert document.lines[0].text == "سلام"
    assert document.lines[-1].timestamp_ms is None
    assert "[00:01.25]سلام" in document.to_lrc()


def test_lyrics_sidecar_is_utf8_and_structured(database, tmp_path):
    audio_path = tmp_path / "track.mp3"
    audio_path.write_bytes(b"fixture")
    track, _ = TrackRepository(database).upsert(Track(None, str(audio_path)))
    lyrics = LyricsService(TrackRepository(database))
    saved = lyrics.save_lyrics(track.id, "[00:03.20]سلام\n[00:05.00]دنیا", "lrc", "sidecar")
    assert saved.storage == "sidecar" and not saved.embedded
    loaded = lyrics.get_lyrics(track.id)
    assert [(line.timestamp_ms, line.text) for line in loaded.lines] == [(3200, "سلام"), (5000, "دنیا")]
    with pytest.raises(ValueError, match="format"):
        lyrics.save_lyrics(track.id, "x", "srt", "sidecar")


def test_artwork_cache_optimizes_and_evicts_old_entries(tmp_path):
    cache = ArtworkManager(tmp_path / "cache", max_entries=2, memory_entries=1, thumbnail_size=(128, 128))
    outputs = []
    for index in range(3):
        data, path = cache.prepare(_png((index * 30, 10, 100)), cache_key=f"image-{index}")
        outputs.append(path)
        with Image.open(io.BytesIO(data)) as image:
            assert max(image.size) <= 128
    assert len(list((tmp_path / "cache").glob("*.jpg"))) + len(list((tmp_path / "cache").glob("*.png"))) <= 2
    with pytest.raises(Exception, match="Invalid or unreadable"):
        cache.prepare(b"not an image")


def test_artwork_manager_reads_external_cover_and_invalidates(tmp_path):
    folder = tmp_path / "music"
    folder.mkdir()
    audio = folder / "track.mp3"
    audio.write_bytes(b"audio")
    (folder / "COVER.PNG").write_bytes(_png())
    manager = ArtworkManager(tmp_path / "cache")
    data = manager.read_artwork(7, audio)
    assert data
    with Image.open(io.BytesIO(data)) as image:
        assert max(image.size) <= 512
    assert manager.get_artwork_path(7, audio)
    manager.invalidate(7)
