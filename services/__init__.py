"""Application-facing domain services."""

from .history_service import HistoryService
from .import_export_service import ImportExportService, LegacyPlaylistMigrator
from .settings_service import SettingsService

__all__ = ["DomainServices", "HistoryService", "ImportExportService", "LegacyPlaylistMigrator", "SettingsService"]

def __getattr__(name: str):
    if name == "DomainServices":
        from .domain_services import DomainServices
        return DomainServices
    raise AttributeError(name)
