from __future__ import annotations

import threading

from core.library.scanner import LibraryScanner
from core.models import Track
from database.repositories.library_repository import LibraryFolderRepository
from database.repositories.track_repository import TrackRepository


def test_scanner_adds_updates_skips_unchanged_and_marks_missing(database, tmp_path, monkeypatch):
    import core.library.scanner as scanner_module

    root = tmp_path / "Music"
    root.mkdir()
    audio = root / "song.mp3"
    audio.write_bytes(b"audio fixture")
    track_repo = TrackRepository(database)
    folders = LibraryFolderRepository(database)
    folders.add(root)
    reads = []

    def fake_read(path):
        reads.append(str(path))
        return Track(None, str(path), title="Indexed song", artist="Artist")

    monkeypatch.setattr(scanner_module, "read_metadata", fake_read)
    scanner = LibraryScanner(track_repo, folders)
    first = scanner.scan()
    assert first.added == 1 and first.scanned == 1
    assert first.errors == []
    second = scanner.scan()
    assert second.unchanged == 1 and len(reads) == 1
    audio.unlink()
    third = scanner.scan()
    assert third.missing == 1
    assert not track_repo.list_tracks()[0].is_available


def test_scanner_deduplicates_overlapping_roots_and_reports_corrupt_files(database, tmp_path, monkeypatch):
    import core.library.scanner as scanner_module

    root = tmp_path / "Music"
    child = root / "Child"
    child.mkdir(parents=True)
    (child / "track.flac").write_bytes(b"broken")
    tracks = TrackRepository(database)
    folders = LibraryFolderRepository(database)
    monkeypatch.setattr(scanner_module, "read_metadata", lambda path: Track(None, str(path), title="One"))
    result = LibraryScanner(tracks, folders).scan([root, child])
    assert result.added == 1
    assert result.total == 1

    broken = root / "bad.opus"
    broken.write_bytes(b"bad")
    monkeypatch.setattr(scanner_module, "read_metadata", lambda path: (_ for _ in ()).throw(ValueError("invalid tags")))
    failed = LibraryScanner(tracks, folders).scan([root])
    assert any("invalid tags" in error for error in failed.errors)
    assert tracks.list_tracks()[0].is_available


def test_scanner_honors_cancellation_before_processing(database, tmp_path, monkeypatch):
    import core.library.scanner as scanner_module

    root = tmp_path / "Music"
    root.mkdir()
    (root / "track.mp3").write_bytes(b"x")
    cancel = threading.Event()
    cancel.set()
    monkeypatch.setattr(scanner_module, "read_metadata", lambda path: (_ for _ in ()).throw(AssertionError("must not read")))
    result = LibraryScanner(TrackRepository(database), LibraryFolderRepository(database)).scan([root], cancel=cancel)
    assert result.canceled
    assert result.scanned == 0


def test_library_service_runs_scan_in_qt_worker(database, tmp_path, monkeypatch):
    import core.library.scanner as scanner_module
    from PyQt6.QtCore import QCoreApplication, QEventLoop, QTimer
    from core.library.library_service import LibraryService

    app = QCoreApplication.instance() or QCoreApplication([])
    root = tmp_path / "Music"
    root.mkdir()
    (root / "song.aiff").write_bytes(b"aiff")
    monkeypatch.setattr(scanner_module, "read_metadata", lambda path: Track(None, str(path), title="Async"))
    service = LibraryService(database)
    service.add_library_folder(root)
    loop = QEventLoop()
    service.scan_completed.connect(lambda _: loop.quit())
    worker = service.scan_library()
    QTimer.singleShot(5000, loop.quit)
    loop.exec()
    assert worker.wait(1000)
    assert service.last_scan is not None and service.last_scan.added == 1
    assert service.get_track(1).title == "Async"
    _ = app
