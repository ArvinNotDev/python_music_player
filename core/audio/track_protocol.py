"""Structural contract for library tracks used by the audio subsystem."""

from typing import Protocol, runtime_checkable


@runtime_checkable
class TrackLike(Protocol):
    """Minimum fields consumed by playback; the library owns the real model."""

    id: object
    path: str
    title: str
    artist: str
    album: str
    album_artist: str
    duration_ms: int
    artwork_path: str | None
