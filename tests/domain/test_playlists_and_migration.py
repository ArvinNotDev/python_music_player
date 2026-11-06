from __future__ import annotations

import json
import os

from core.models import Track
from core.playlists import PlaylistService
from database.repositories.playlist_repository import PlaylistRepository
from database.repositories.settings_repository import SettingsRepository
from database.repositories.track_repository import TrackRepository
from services.import_export_service import LegacyPlaylistMigrator


def test_m3u8_import_export_reports_missing_paths_and_round_trips_unicode(database, tmp_path):
    audio = tmp_path / "音乐" / "歌曲.mp3"
    audio.parent.mkdir()
    audio.write_bytes(b"fixture")
    track, _ = TrackRepository(database).upsert(Track(None, str(audio), title="夜曲"))
    playlist_file = tmp_path / "playlist.m3u8"
    playlist_file.write_text("#EXTM3U\n#EXTINF:10,夜曲\n音乐/歌曲.mp3\nmissing.mp3\n", encoding="utf-8")
    service = PlaylistService(PlaylistRepository(database))
    imported = service.import_playlist(playlist_file, "Unicode list")
    assert imported.added_count == 2
    assert imported.missing_paths == [os.path.normcase(str((tmp_path / "missing.mp3").resolve()))]
    assert [item.id for item in service.get_playlist_tracks(imported.playlist_id)] == [track.id]
    assert len(service.get_playlist_entries(imported.playlist_id)) == 2
    exported_path = tmp_path / "export.m3u8"
    exported = service.export_playlist(imported.playlist_id, exported_path)
    assert exported.entries_written == 2
    assert exported.missing_paths == imported.missing_paths
    exported_text = exported_path.read_text(encoding="utf-8")
    assert "歌曲.mp3" in exported_text and "missing.mp3" in exported_text


def test_playlist_import_rejects_remote_and_reports_invalid_lines(database, tmp_path):
    source = tmp_path / "mixed.m3u"
    source.write_text("#EXTM3U\nhttps://example.invalid/audio.mp3\n", encoding="utf-8")
    result = PlaylistService(PlaylistRepository(database)).import_playlist(source)
    assert result.added_count == 0
    assert result.invalid_lines[0][0] == 2


def test_legacy_migration_preserves_favorites_backups_and_is_idempotent(database, tmp_path):
    known_path = tmp_path / "known.flac"
    known_path.write_bytes(b"x")
    track, _ = TrackRepository(database).upsert(Track(None, str(known_path), title="Known"))
    legacy = tmp_path / "playlists.json"
    legacy.write_text(json.dumps({
        "Favorites": [str(known_path), str(known_path)],
        "Old mix": [str(known_path), str(tmp_path / "missing.mp3")],
    }), encoding="utf-8")
    repo = PlaylistRepository(database)
    migrator = LegacyPlaylistMigrator(database, repo, SettingsRepository(database))
    first = migrator.migrate([legacy])
    assert first.migrated_files == [str(legacy.resolve())]
    assert first.backup_files and legacy.exists()
    assert first.duplicates_skipped == 1
    service = PlaylistService(repo)
    assert service.is_favorite(track.id)
    old_mix = next(item for item in service.list_playlists() if item.name == "Old mix")
    assert len(service.get_playlist_entries(old_mix.id)) == 2
    second = migrator.migrate([legacy])
    assert second.migrated_files == []
    assert len(service.get_playlist_entries(old_mix.id)) == 2


def test_malformed_legacy_json_is_reported_without_backup_or_marker(database, tmp_path):
    legacy = tmp_path / "broken.json"
    legacy.write_text("{not-json", encoding="utf-8")
    result = LegacyPlaylistMigrator(database, PlaylistRepository(database)).migrate([legacy])
    assert result.errors
    assert not result.backup_files
    assert legacy.exists()
