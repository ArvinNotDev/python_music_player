"""Tag, artwork, and lyrics domain services."""

from .artwork_manager import ArtworkManager, ArtworkError
from .metadata_service import MetadataService
from .lyrics_service import LyricsService, LyricsError, LyricsSaveResult, parse_lrc
from .tagging import MetadataDependencyError, MetadataReadError, MetadataWriteError

__all__ = [
    "ArtworkError", "ArtworkManager", "LyricsError", "LyricsSaveResult", "LyricsService",
    "MetadataDependencyError", "MetadataReadError", "MetadataService", "MetadataWriteError", "parse_lrc",
]
