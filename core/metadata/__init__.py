"""Tag, artwork, and lyrics domain services."""

from .artwork_manager import ArtworkManager, ArtworkError
from .metadata_service import MetadataService
from .lyrics_service import LyricsService, LyricsError, LyricsLookupResult, LyricsSaveResult, parse_lrc
from .online_lyrics import LyricsCandidate, LyricsProviderError, LyricsRateLimited
from .tagging import MetadataDependencyError, MetadataReadError, MetadataWriteError

__all__ = [
    "ArtworkError", "ArtworkManager", "LyricsCandidate", "LyricsError", "LyricsLookupResult", "LyricsProviderError", "LyricsRateLimited", "LyricsSaveResult", "LyricsService",
    "MetadataDependencyError", "MetadataReadError", "MetadataService", "MetadataWriteError", "parse_lrc",
]
