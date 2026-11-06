"""Recursive scanner that caches file signatures and tolerates filesystem errors."""

from __future__ import annotations

import os
from pathlib import Path
from threading import Event
from typing import Callable, Iterable

from core.models import ScanResult, Track
from database.repositories.library_repository import LibraryFolderRepository
from database.repositories.track_repository import TrackRepository, normalize_path
from core.metadata.artwork_manager import ArtworkError, ArtworkManager
from core.metadata.tagging import read_metadata

AUDIO_EXTENSIONS = frozenset({
    ".mp3", ".flac", ".wav", ".ogg", ".oga", ".opus", ".spx", ".m4a", ".m4b", ".m4p", ".mp4",
    ".mp1", ".mp2", ".mpga", ".aac", ".aif", ".aiff", ".aifc", ".wma", ".asf", ".ape", ".mpc", ".wv", ".tta", ".tak",
})


class LibraryScanner:
    def __init__(self, tracks: TrackRepository, folders: LibraryFolderRepository,
                 artwork: ArtworkManager | None = None):
        self.tracks = tracks
        self.folders = folders
        self.artwork = artwork or ArtworkManager()

    def scan(self, paths: Iterable[str | Path] | None = None, *, cancel: Event | None = None,
             progress: Callable[[int, int, str], None] | None = None,
             on_error: Callable[[str], None] | None = None) -> ScanResult:
        cancel = cancel or Event()
        result = ScanResult()
        requested = list(paths) if paths is not None else self.folders.list()
        roots: list[Path] = []
        root_keys: set[str] = set()
        root_errors: set[str] = set()
        for raw_path in requested:
            root = Path(raw_path).expanduser().resolve(strict=False)
            key = normalize_path(root)
            if key in root_keys:
                continue
            root_keys.add(key)
            if not root.exists():
                self._error(result, on_error, f"Library folder is missing: {root}")
                continue
            if not root.is_dir():
                self._error(result, on_error, f"Library path is not a directory: {root}")
                continue
            if not os.access(root, os.R_OK):
                self._error(result, on_error, f"Library folder is inaccessible: {root}")
                root_errors.add(key)
                continue
            roots.append(root)
        paths_to_scan: dict[str, Path] = {}
        discovered: set[str] = set()

        def walk_error(root_key: str, root: Path, exc: OSError) -> None:
            root_errors.add(root_key)
            self._error(result, on_error, f"Could not read folder under {root}: {exc}")

        for root in roots:
            if cancel.is_set():
                result.canceled = True
                break
            root_key = normalize_path(root)
            try:
                for current_root, dirs, files in os.walk(root, topdown=True, followlinks=False,
                                                          onerror=lambda exc, rk=root_key, r=root: walk_error(rk, r, exc)):
                    if progress:
                        progress(0, 0, current_root)
                    dirs[:] = [directory for directory in dirs if not (Path(current_root) / directory).is_symlink()]
                    for filename in files:
                        path = Path(current_root) / filename
                        try:
                            key = normalize_path(path)
                        except (OSError, RuntimeError, ValueError) as exc:
                            self._error(result, on_error, f"Could not normalize path {path}: {exc}")
                            continue
                        discovered.add(key)
                        if path.suffix.casefold() in AUDIO_EXTENSIONS:
                            paths_to_scan.setdefault(key, path)
            except OSError as exc:
                root_errors.add(root_key)
                self._error(result, on_error, f"Could not scan {root}: {exc}")
        files = list(paths_to_scan.items())
        result.total = len(files)
        if progress:
            progress(0, result.total, "")
        for index, (normalized, path) in enumerate(files, start=1):
            if cancel.is_set():
                result.canceled = True
                break
            current_text = str(path)
            try:
                stat = path.stat()
                if not path.is_file():
                    continue
                cached = self.tracks.file_signature_matches(path, stat.st_size, stat.st_mtime_ns)
                if cached is not None:
                    if not cached.is_available:
                        self.tracks.update_scan_state(path, stat.st_size, stat.st_mtime_ns)
                    result.unchanged += 1
                else:
                    previous = self.tracks.find_by_path(path)
                    track = read_metadata(path)
                    saved, inserted = self.tracks.upsert(track, file_size=stat.st_size, file_mtime_ns=stat.st_mtime_ns)
                    try:
                        artwork_path = self.artwork.get_artwork_path(saved.id, path)
                    except ArtworkError as exc:
                        self._error(result, on_error, f"Could not cache artwork for {current_text}: {exc}")
                        artwork_path = None
                    if saved.artwork_path != artwork_path:
                        self.tracks.set_metadata(saved.id, {"artwork_path": artwork_path})
                    if inserted:
                        result.added += 1
                    elif previous:
                        result.updated += 1
                    else:
                        result.added += 1
                result.scanned += 1
            except Exception as exc:
                self._error(result, on_error, f"Could not index {current_text}: {exc}")
            finally:
                if progress:
                    progress(index, result.total, current_text)
        if not result.canceled and roots:
            safe_roots = [root for root in roots if normalize_path(root) not in root_errors]
            if safe_roots:
                result.missing = self.tracks.mark_removed_outside_folders(safe_roots, discovered)
            for root in roots:
                self.folders.mark_scanned(root)
        return result

    @staticmethod
    def _error(result: ScanResult, on_error: Callable[[str], None] | None, message: str) -> None:
        result.errors.append(message)
        if on_error:
            on_error(message)
