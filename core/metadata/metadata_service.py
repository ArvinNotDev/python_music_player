"""Public track metadata and embedded-artwork service."""

from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Any, Mapping

from core.models import Track
from database.repositories.track_repository import TrackRepository
from .artwork_manager import ArtworkError, ArtworkManager
from .tagging import (
    MetadataReadError, MetadataWriteError,
    read_metadata as read_file_metadata, write_artwork as write_file_artwork,
    write_metadata as write_file_metadata,
)


class MetadataService:
    """Reads and writes source-file tags while keeping the SQLite cache in sync."""

    def __init__(self, tracks: TrackRepository, artwork: ArtworkManager | None = None, *, on_track_changed=None):
        self.tracks = tracks
        self.artwork = artwork or ArtworkManager()
        self.on_track_changed = on_track_changed
        self._locks_guard = threading.Lock()
        self._file_locks: dict[str, threading.RLock] = {}

    def _lock_for(self, path: str) -> threading.RLock:
        with self._locks_guard:
            return self._file_locks.setdefault(os.path.normcase(path), threading.RLock())

    def read_metadata(self, track_id: int) -> Track:
        current = self.tracks.get(track_id)
        if current is None:
            raise KeyError(f"Track {track_id} does not exist")
        if not Path(current.path).is_file():
            raise MetadataReadError(f"Audio file is missing: {current.path}")
        metadata = read_file_metadata(current.path, track_id=track_id)
        stat = Path(current.path).stat()
        saved, _ = self.tracks.upsert(metadata, file_size=stat.st_size, file_mtime_ns=stat.st_mtime_ns)
        try:
            artwork_path = self.artwork.get_artwork_path(track_id, current.path)
        except ArtworkError:
            artwork_path = saved.artwork_path
        if artwork_path != saved.artwork_path:
            saved = self.tracks.set_metadata(track_id, {"artwork_path": artwork_path})
        if self.on_track_changed:
            self.on_track_changed(saved)
        return saved

    def write_metadata(self, track_id: int, changes: Mapping[str, Any]) -> Track:
        current = self.tracks.get(track_id)
        if current is None:
            raise KeyError(f"Track {track_id} does not exist")
        if not changes:
            return current
        path = Path(current.path)
        if not path.is_file():
            raise MetadataWriteError(f"Audio file is missing: {current.path}")
        clean = dict(changes)
        lock = self._lock_for(current.path)
        with lock:
            write_file_metadata(current.path, clean)
            stat = path.stat()
            updated = read_file_metadata(current.path, track_id=track_id)
            saved, _ = self.tracks.upsert(updated, file_size=stat.st_size, file_mtime_ns=stat.st_mtime_ns)
            try:
                artwork_path = self.artwork.get_artwork_path(track_id, current.path)
            except ArtworkError:
                artwork_path = saved.artwork_path
            if artwork_path != saved.artwork_path:
                saved = self.tracks.set_metadata(track_id, {"artwork_path": artwork_path})
            if self.on_track_changed:
                self.on_track_changed(saved)
            return saved

    def read_artwork(self, track_id: int) -> bytes | None:
        current = self.tracks.get(track_id)
        if current is None:
            raise KeyError(f"Track {track_id} does not exist")
        return self.artwork.read_artwork(track_id, current.path)

    def write_artwork(self, track_id: int, image_bytes: bytes | None) -> str | None:
        current = self.tracks.get(track_id)
        if current is None:
            raise KeyError(f"Track {track_id} does not exist")
        path = Path(current.path)
        if not path.is_file():
            raise MetadataWriteError(f"Audio file is missing: {current.path}")
        lock = self._lock_for(current.path)
        with lock:
            if image_bytes is not None:
                self.artwork.validate(image_bytes)
            write_file_artwork(current.path, image_bytes)
            self.artwork.invalidate(track_id)
            try:
                artwork_path = self.artwork.get_artwork_path(track_id, current.path, force=True)
            except ArtworkError:
                artwork_path = None
            self.tracks.set_metadata(track_id, {"artwork_path": artwork_path})
            stat = path.stat()
            self.tracks.update_scan_state(path, stat.st_size, stat.st_mtime_ns)
            if self.on_track_changed:
                self.on_track_changed(self.tracks.get(track_id))
            return artwork_path

