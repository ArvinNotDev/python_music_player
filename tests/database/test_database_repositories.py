from __future__ import annotations

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import pytest

from core.models import Track
from core.playlists import PlaylistService
from database.database_manager import DatabaseError, DatabaseManager, SCHEMA_VERSION
from database.migrations.v001_initial import MIGRATION as MIGRATION_1
from database.repositories.history_repository import HistoryRepository
from database.repositories.playlist_repository import PlaylistRepository
from database.repositories.settings_repository import SettingsRepository
from database.repositories.track_repository import TrackRepository
from services.history_service import HistoryService
from services.settings_service import SettingsService


def test_database_initializes_latest_schema_and_enables_foreign_keys(database):
    with database.transaction() as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert conn.execute("PRAGMA journal_mode").fetchone()[0].casefold() == "wal"
        assert {row["name"] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")} >= {
            "tracks", "artists", "albums", "library_folders", "playlists", "playlist_tracks",
            "favorites", "playback_history", "settings",
        }


def test_database_upgrades_v1_and_rejects_newer_version(tmp_path):
    path = tmp_path / "upgrade.sqlite3"
    connection = sqlite3.connect(path)
    connection.executescript(MIGRATION_1 + "\nPRAGMA user_version=1;")
    connection.close()
    database = DatabaseManager(path)
    with database.transaction() as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 2
        assert conn.execute("SELECT 1 FROM sqlite_master WHERE name='playlists'").fetchone()
    database.close()

    connection = sqlite3.connect(path)
    connection.execute("PRAGMA user_version=999")
    connection.close()
    with pytest.raises(DatabaseError, match="newer than supported"):
        DatabaseManager(path)


def test_track_repository_groups_and_uses_path_not_filename_as_identity(database, tmp_path):
    repo = TrackRepository(database)
    first = tmp_path / "one" / "same.mp3"
    second = tmp_path / "two" / "same.mp3"
    a, inserted_a = repo.upsert(Track(None, str(first), title="First", artist="Artist", album="Album"))
    b, inserted_b = repo.upsert(Track(None, str(second), title="Second", artist="Artist", album="Album"))
    assert inserted_a and inserted_b
    assert a.id != b.id
    assert repo.find_by_path(first).id == a.id
    assert repo.list_tracks(query="first")[0].id == a.id
    assert len(repo.list_albums()) == 1
    assert repo.list_albums()[0].track_count == 2
    assert repo.list_artists()[0].track_count == 2


def test_playlist_order_favorites_and_protection_persist(database, tmp_path):
    tracks = TrackRepository(database)
    ids = [tracks.upsert(Track(None, str(tmp_path / f"{n}.flac"), title=str(n)))[0].id for n in range(3)]
    repo = PlaylistRepository(database)
    service = PlaylistService(repo)
    playlist = service.create_playlist("Road trip")
    for track_id in ids:
        assert service.add_track(playlist.id, track_id)
    service.reorder_tracks(playlist.id, 0, 2)
    assert [item.id for item in service.get_playlist_tracks(playlist.id)] == [ids[1], ids[2], ids[0]]
    assert service.toggle_favorite(ids[0]) is True
    assert service.is_favorite(ids[0])
    assert [item.id for item in service.get_playlist_tracks(repo.favorites_id())] == [ids[0]]
    with pytest.raises(ValueError, match="cannot be renamed"):
        service.rename_playlist(repo.favorites_id(), "Other")
    with pytest.raises(ValueError, match="cannot be deleted"):
        service.delete_playlist(repo.favorites_id())
    database.close()
    reopened = DatabaseManager(database.path)
    reopened_service = PlaylistService(PlaylistRepository(reopened))
    assert [item.id for item in reopened_service.get_playlist_tracks(playlist.id)] == [ids[1], ids[2], ids[0]]
    assert reopened_service.is_favorite(ids[0])
    reopened.close()


def test_settings_unicode_and_history_are_persistent(database, tmp_path):
    tracks = TrackRepository(database)
    track, _ = tracks.upsert(Track(None, str(tmp_path / "تراک.flac"), title="سلام 🎵"))
    settings = SettingsService(SettingsRepository(database))
    settings.set("language", "فارسی")
    settings.set("window", {"width": 1200, "rtl": True})
    assert settings.get("language") == "فارسی"
    assert settings.all()["window"] == {"width": 1200, "rtl": True}
    history = HistoryService(HistoryRepository(database))
    history.record_play(track.id)
    history.record_play(track.id)
    recent = history.recently_played()
    assert [item.id for item in recent] == [track.id]
    assert recent[0].play_count == 2
    assert recent[0].last_played.tzinfo == timezone.utc
    assert history.recently_added()[0].id == track.id


def test_concurrent_setting_writes_and_transaction_rollback(database):
    repository = SettingsRepository(database)

    def write_batch(batch):
        for index in range(12):
            repository.set(f"{batch}-{index}", {"value": index})

    with ThreadPoolExecutor(max_workers=6) as pool:
        list(pool.map(write_batch, range(6)))
    assert len(repository.all()) == 72
    try:
        with database.transaction(write=True) as conn:
            conn.execute("INSERT INTO settings(key,value,updated_at) VALUES('rolled-back','true','now')")
            raise RuntimeError("force rollback")
    except RuntimeError:
        pass
    assert repository.get("rolled-back") is None
