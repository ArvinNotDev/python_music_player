"""Canonical local music track model."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import math
from pathlib import Path


def _utc(value: datetime | None, field_name: str, *, optional: bool) -> datetime | None:
    if value is None:
        if optional:
            return None
        return datetime.now(timezone.utc)
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be a datetime")
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


@dataclass(slots=True)
class Track:
    """A track row. ``id`` is assigned by SQLite; ``path`` is always absolute."""

    id: int | None
    path: str
    title: str = ""
    artist: str = ""
    album: str = ""
    album_artist: str = ""
    duration_ms: int = 0
    track_number: int | None = None
    disc_number: int | None = None
    year: int | None = None
    genre: str = ""
    composer: str = ""
    comment: str = ""
    bitrate: int | None = None
    sample_rate: int | None = None
    artwork_path: str | None = None
    date_added: datetime | None = None
    last_played: datetime | None = None
    play_count: int = 0
    is_available: bool = True
    bpm: float | None = None

    def __post_init__(self) -> None:
        if self.id is not None and (not isinstance(self.id, int) or self.id < 1):
            raise ValueError("id must be a positive integer or None before persistence")
        if not isinstance(self.path, (str, Path)) or not str(self.path).strip():
            raise ValueError("path must be a non-empty local file path")
        self.path = str(Path(self.path).expanduser().resolve(strict=False))
        for name in ("title", "artist", "album", "album_artist", "genre", "composer", "comment"):
            value = getattr(self, name)
            if value is None:
                setattr(self, name, "")
            elif not isinstance(value, str):
                setattr(self, name, str(value))
        self.duration_ms = self._nonnegative_int(self.duration_ms, "duration_ms")
        self.play_count = self._nonnegative_int(self.play_count, "play_count")
        for name in ("track_number", "disc_number", "year", "bitrate", "sample_rate"):
            value = getattr(self, name)
            if value is not None:
                normalized = self._nonnegative_int(value, name)
                if normalized == 0:
                    raise ValueError(f"{name} must be positive when provided")
                setattr(self, name, normalized)
        if self.bpm is not None:
            self.bpm = float(self.bpm)
            if not math.isfinite(self.bpm) or self.bpm < 0:
                raise ValueError("bpm must be a finite, non-negative number")
        self.date_added = _utc(self.date_added, "date_added", optional=False)
        self.last_played = _utc(self.last_played, "last_played", optional=True)
        if not isinstance(self.is_available, bool):
            raise TypeError("is_available must be a bool")

    @staticmethod
    def _nonnegative_int(value: int, field_name: str) -> int:
        if isinstance(value, bool):
            raise TypeError(f"{field_name} must be an integer")
        try:
            converted = int(value)
        except (TypeError, ValueError) as exc:
            raise TypeError(f"{field_name} must be an integer") from exc
        if converted < 0:
            raise ValueError(f"{field_name} cannot be negative")
        return converted
