"""Build the desktop application graph in a deterministic, testable order."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from PySide6.QtCore import QThreadPool
from PySide6.QtWidgets import QApplication

from database.database_manager import app_data_dir
from .service_container import ServiceContainer

logger = logging.getLogger(__name__)


def create_qapplication(argv: Sequence[str] | None = None) -> QApplication:
    application = QApplication.instance()
    if application is None:
        application = QApplication(list(argv) if argv is not None else sys.argv[:1])
    application.setOrganizationName("ArvinNotDev")
    application.setApplicationName("PythonMusicPlayer")
    application.setApplicationDisplayName("Sonora")
    application.setQuitOnLastWindowClosed(True)
    return application


def configure_logging(log_path: str | Path | None = None) -> Path:
    selected_path = Path(log_path) if log_path is not None else app_data_dir() / "logs" / "sonora.log"
    selected_path.parent.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    if not any(getattr(handler, "baseFilename", None) == str(selected_path) for handler in root.handlers):
        handler = RotatingFileHandler(selected_path, maxBytes=2_000_000, backupCount=3, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        root.addHandler(handler)
    return selected_path


@dataclass
class ApplicationRuntime:
    app: QApplication
    services: ServiceContainer
    window: object
    _closed: bool = False

    def shutdown(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            if not QThreadPool.globalInstance().waitForDone(5_000):
                logger.warning("Background UI tasks were still running during shutdown")
        finally:
            self.services.close()


def _restore_playback_settings(services: ServiceContainer) -> None:
    settings = services.settings
    try:
        volume = float(settings.get("playback.default_volume", 0.7))
    except (TypeError, ValueError):
        volume = 0.7
    services.playback.set_volume(volume)
    services.playback.set_shuffle(bool(settings.get("playback.shuffle", False)))

    repeat = settings.get("playback.repeat", "off")
    repeat = {0: "off", 1: "all", 2: "one", "0": "off", "1": "all", "2": "one"}.get(repeat, repeat)
    if repeat not in {"off", "all", "one"}:
        repeat = "off"
    services.playback.set_repeat_mode(repeat)


def build_runtime(
    argv: Sequence[str] | None = None,
    *,
    database_path: str | Path | None = None,
    legacy_candidates=None,
    migrate_legacy: bool = True,
    application: QApplication | None = None,
    audio_engine=None,
    log_path: str | Path | None = None,
) -> ApplicationRuntime:
    """Construct one QApplication, domain graph, audio controller, and window.

    Pass ``database_path`` and ``legacy_candidates=[]`` in isolated tests to avoid
    touching the user's normal application data or legacy JSON files.
    """
    app = application or create_qapplication(argv)
    if QApplication.instance() is not app:
        raise RuntimeError("The supplied application is not the active QApplication")
    app.setOrganizationName("ArvinNotDev")
    app.setApplicationName("PythonMusicPlayer")
    app.setApplicationDisplayName("Sonora")
    configure_logging(log_path)

    services = ServiceContainer(database_path, parent=app, audio_engine=audio_engine)
    try:
        if migrate_legacy:
            migration = services.migrate_legacy_playlists(legacy_candidates)
            for error in migration.errors:
                logger.warning("Legacy playlist migration: %s", error)
            for backup in migration.backup_files:
                logger.info("Legacy playlists backed up to %s", backup)

        folders = services.register_saved_folders()
        _restore_playback_settings(services)

        from ui.main_window import MainWindow

        window = MainWindow(
            library_service=services.library,
            playlist_service=services.playlists,
            metadata_service=services.metadata,
            lyrics_service=services.lyrics,
            settings_service=services.settings,
            history_service=services.history,
            playback_controller=services.playback_ui,
        )

        services.library.library_changed.connect(window._on_library_changed)
        services.library.scan_progress.connect(window._on_scan_progress)
        services.library.scan_completed.connect(window._on_scan_completed)
        services.library.scan_error.connect(window._on_scan_error)

        runtime = ApplicationRuntime(app, services, window)
        app.aboutToQuit.connect(runtime.shutdown)

        if bool(services.settings.get("library.auto_scan", True)):
            if folders:
                try:
                    services.library.scan_library(folders)
                    window.settings_page.rescan.setEnabled(False)
                except Exception:
                    logger.exception("Could not start the automatic library scan")
        return runtime
    except Exception:
        services.close()
        raise
