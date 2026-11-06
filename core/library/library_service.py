"""UI-friendly library queries, folder registration, and background scanning."""

from __future__ import annotations

from pathlib import Path
from threading import Event
from typing import Any, Iterable, Mapping

from PySide6.QtCore import QObject, QThread, Signal

from core.library.scanner import LibraryScanner
from core.metadata.artwork_manager import ArtworkManager
from core.models import Album, Artist, ScanResult, Track
from database.database_manager import DatabaseManager
from database.repositories.library_repository import LibraryFolderRepository
from database.repositories.track_repository import TrackRepository, normalize_path


class _ScanWorker(QThread):
    progress = Signal(int, int, str)
    completed = Signal(object)
    error = Signal(str)

    def __init__(self, scanner: LibraryScanner, paths: list[str] | None):
        super().__init__()
        self.scanner = scanner
        self.paths = paths
        self._cancel = Event()

    def cancel(self) -> None:
        self._cancel.set()

    def run(self) -> None:
        result = ScanResult()
        try:
            result = self.scanner.scan(
                self.paths,
                cancel=self._cancel,
                progress=self.progress.emit,
                on_error=self.error.emit,
            )
        except Exception as exc:
            result.errors.append(str(exc))
            self.error.emit(str(exc))
        self.completed.emit(result)


class LibraryService(QObject):
    """Canonical library API. ``scan_library`` starts a Qt worker and returns it."""

    scan_progress = Signal(int, int, str)
    scan_completed = Signal(object)
    scan_error = Signal(str)
    library_changed = Signal(str, object)

    def __init__(self, database: DatabaseManager, *, artwork: ArtworkManager | None = None):
        super().__init__()
        self.database = database
        self.tracks = TrackRepository(database)
        self.folders = LibraryFolderRepository(database)
        self.artwork = artwork or ArtworkManager()
        self.scanner = LibraryScanner(self.tracks, self.folders, self.artwork)
        self._worker: _ScanWorker | None = None
        self._last_scan: ScanResult | None = None

    def list_tracks(self, query: str = "", sort_by: str = "title", descending: bool = False,
                    filters: Mapping[str, Any] | None = None) -> list[Track]:
        return self.tracks.list_tracks(query, sort_by, descending, filters)

    def list_albums(self, query: str = "") -> list[Album]:
        return self.tracks.list_albums(query)

    def list_artists(self, query: str = "") -> list[Artist]:
        return self.tracks.list_artists(query)

    def get_track(self, track_id: int) -> Track | None:
        return self.tracks.get(track_id)

    def notify_track_changed(self, track: Track) -> None:
        """Publish an update made by another domain service, such as tag editing."""
        self.library_changed.emit("track_changed", track)

    def add_library_folder(self, path: str | Path) -> str:
        folder = Path(path).expanduser().resolve(strict=False)
        if not folder.exists():
            raise FileNotFoundError(f"Library folder does not exist: {folder}")
        if not folder.is_dir():
            raise NotADirectoryError(f"Library path is not a directory: {folder}")
        normalized = self.folders.add(folder)
        self.library_changed.emit("folder_added", normalized)
        return normalized

    def remove_library_folder(self, path: str | Path) -> bool:
        normalized = normalize_path(path)
        removed = self.folders.remove(normalized)
        if removed:
            self.library_changed.emit("folder_removed", normalized)
        return removed

    def list_library_folders(self) -> list[str]:
        return self.folders.list()

    def scan_library(self, paths: Iterable[str | Path] | None = None) -> QThread:
        if self._worker is not None and self._worker.isRunning():
            raise RuntimeError("A library scan is already running")
        normalized = [normalize_path(path) for path in paths] if paths is not None else None
        worker = _ScanWorker(self.scanner, normalized)
        worker.progress.connect(self.scan_progress.emit)
        worker.error.connect(self.scan_error.emit)
        worker.completed.connect(self._on_scan_completed)
        worker.finished.connect(self._on_worker_finished)
        self._worker = worker
        worker.start()
        return worker

    def cancel_scan(self) -> bool:
        if self._worker is None or not self._worker.isRunning():
            return False
        self._worker.cancel()
        return True

    def _on_scan_completed(self, result: ScanResult) -> None:
        self._last_scan = result
        self.scan_completed.emit(result)
        self.library_changed.emit("scan_completed", result)

    def _on_worker_finished(self) -> None:
        worker = self._worker
        self._worker = None
        if worker is not None:
            worker.deleteLater()

    @property
    def last_scan(self) -> ScanResult | None:
        return self._last_scan
