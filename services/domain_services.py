"""Convenient composition root for the shared data-domain services."""

from __future__ import annotations

from pathlib import Path

from core.library import LibraryService
from core.metadata import ArtworkManager, LyricsService, MetadataService
from core.playlists import PlaylistService
from database.database_manager import DatabaseManager
from database.repositories.history_repository import HistoryRepository
from database.repositories.playlist_repository import PlaylistRepository
from database.repositories.settings_repository import SettingsRepository
from database.repositories.track_repository import TrackRepository
from services.history_service import HistoryService
from services.import_export_service import ImportExportService, LegacyPlaylistMigrator
from services.settings_service import SettingsService


class DomainServices:
    """Creates a single database/repository graph for UI and audio integration.

    Call ``migrate_legacy_playlists`` during application startup after constructing this
    object. The migration scans known legacy locations and only copies files on success.
    """

    def __init__(self, database_path: str | Path | None = None):
        self.database = DatabaseManager(database_path)
        self.tracks = TrackRepository(self.database)
        self.playlist_repository = PlaylistRepository(self.database)
        self.settings_repository = SettingsRepository(self.database)
        self.history_repository = HistoryRepository(self.database)
        self.artwork = ArtworkManager()
        self.library = LibraryService(self.database, artwork=self.artwork)
        self.playlists = PlaylistService(self.playlist_repository)
        self.metadata = MetadataService(self.tracks, self.artwork, on_track_changed=self.library.notify_track_changed)
        self.lyrics = LyricsService(self.tracks)
        self.settings = SettingsService(self.settings_repository)
        self.history = HistoryService(self.history_repository)
        self.legacy_migrator = LegacyPlaylistMigrator(self.database, self.playlist_repository, self.settings_repository)
        self.import_export = ImportExportService(self.playlists, self.legacy_migrator)

    def migrate_legacy_playlists(self, candidates=None):
        return self.import_export.migrate_legacy_playlists(candidates)

    def close(self) -> None:
        worker = getattr(self.library, "_worker", None)
        if worker is not None and worker.isRunning():
            worker.cancel()
            worker.wait()
        self.database.close()
