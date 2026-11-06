"""Library grouping and playlist models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


def _now(value: datetime | None) -> datetime:
    value = value or datetime.now(timezone.utc)
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


@dataclass(slots=True)
class Album:
    id: int | None
    title: str
    album_artist: str = ""
    year: int | None = None
    track_count: int = 0
    duration_ms: int = 0
    artwork_path: str | None = None


@dataclass(slots=True)
class Artist:
    id: int | None
    name: str
    album_count: int = 0
    track_count: int = 0
    artwork_path: str | None = None


@dataclass(slots=True)
class Playlist:
    id: int | None
    name: str
    is_favorite: bool = False
    track_count: int = 0
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        for name in ("created_at", "updated_at"):
            setattr(self, name, _now(getattr(self, name)))
