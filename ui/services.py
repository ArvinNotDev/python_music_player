"""Small structural contracts used by the presentation layer."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class LibraryService(Protocol):
    def list_tracks(self, *args: Any, **kwargs: Any) -> list[Any]: ...
    def list_albums(self, *args: Any, **kwargs: Any) -> list[Any]: ...
    def list_artists(self, *args: Any, **kwargs: Any) -> list[Any]: ...
    def scan_library(self, *args: Any, **kwargs: Any) -> Any: ...


@runtime_checkable
class PlaylistService(Protocol):
    def list_playlists(self) -> list[Any]: ...
    def get_playlist_tracks(self, playlist_id: Any) -> list[Any]: ...
    def create_playlist(self, name: str, *args: Any, **kwargs: Any) -> Any: ...
    def add_track(self, playlist_id: Any, track_id: Any) -> Any: ...
    def remove_track(self, playlist_id: Any, track_id: Any) -> Any: ...


@runtime_checkable
class MetadataService(Protocol):
    def read_metadata(self, track: Any) -> Any: ...
    def write_metadata(self, track: Any, metadata: dict[str, Any]) -> Any: ...
    def read_artwork(self, track: Any) -> Any: ...


@runtime_checkable
class LyricsService(Protocol):
    def get_lyrics(self, track: Any) -> Any: ...
    def save_lyrics(self, track: Any, lyrics: str, *args: Any, **kwargs: Any) -> Any: ...


@runtime_checkable
class SettingsService(Protocol):
    def get(self, key: str, default: Any = None) -> Any: ...
    def set(self, key: str, value: Any) -> Any: ...


@runtime_checkable
class HistoryService(Protocol):
    def recently_played(self, *args: Any, **kwargs: Any) -> list[Any]: ...
    def recently_added(self, *args: Any, **kwargs: Any) -> list[Any]: ...


@runtime_checkable
class PlaybackController(Protocol):
    def play_track(self, track: Any, *args: Any, **kwargs: Any) -> Any: ...
    def play_queue(self, tracks: list[Any], *args: Any, **kwargs: Any) -> Any: ...
    def toggle_play_pause(self) -> Any: ...
    def next(self) -> Any: ...
    def previous(self) -> Any: ...
    def seek(self, position: float) -> Any: ...
    def set_volume(self, volume: float) -> Any: ...
    def add_to_queue(self, track: Any) -> Any: ...
    def play_next(self, track: Any) -> Any: ...


def value(obj: Any, *keys: str, default: Any = "") -> Any:
    """Read a field from dicts, Qt-independent records, or plain objects."""
    for key in keys:
        if isinstance(obj, dict) and key in obj:
            result = obj[key]
        else:
            result = getattr(obj, key, None)
        if result is not None:
            return result
    return default


def track_id(track: Any) -> Any:
    return value(track, "id", "track_id", "path", "file_path", default=track)


def track_title(track: Any) -> str:
    title = value(track, "title", "name", default="")
    if title:
        return str(title)
    path = value(track, "path", "file_path", default="")
    return str(path).replace("\\", "/").rsplit("/", 1)[-1] if path else "Unknown track"


def display_duration(track: Any) -> str:
    raw = value(track, "duration", "duration_seconds", default=0)
    try:
        seconds = int(float(raw or 0))
    except (TypeError, ValueError):
        return str(raw or "—")
    return f"{seconds // 60}:{seconds % 60:02d}" if seconds else "—"
