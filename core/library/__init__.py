"""Music folder registration, scanning, and library query APIs."""

from .scanner import LibraryScanner, AUDIO_EXTENSIONS

__all__ = ["AUDIO_EXTENSIONS", "LibraryScanner", "LibraryService"]


def __getattr__(name: str):
    if name == "LibraryService":
        from .library_service import LibraryService
        return LibraryService
    raise AttributeError(name)
