from __future__ import annotations

from typing import Any

from PySide6.QtCore import QObject, QRunnable, QTimer, Signal, Qt
from PySide6.QtWidgets import (
    QCheckBox, QColorDialog, QComboBox, QFileDialog, QFrame, QHBoxLayout, QLabel,
    QListWidget, QMessageBox, QPushButton, QSlider, QVBoxLayout, QWidget,
)

from .base import ScrollPage


class _ScanSignals(QObject):
    done = Signal(object, object)


class _ScanTask(QRunnable):
    def __init__(self, service, folders):
        super().__init__()
        self.service, self.folders = service, folders
        self.signals = _ScanSignals()

    def run(self):
        try:
            try:
                result = self.service.scan_library(folders=self.folders)
            except TypeError:
                try:
                    result = self.service.scan_library(self.folders)
                except TypeError:
                    result = self.service.scan_library()
            self.signals.done.emit(result, None)
        except Exception as exc:
            self.signals.done.emit(None, exc)


class _ActionTask(QRunnable):
    def __init__(self, method, args=()):
        super().__init__()
        self.method, self.args = method, args
        self.signals = _ScanSignals()

    def run(self):
        try:
            try:
                result = self.method(*self.args)
            except TypeError:
                if self.args:
                    result = self.method()
                else:
                    raise
            self.signals.done.emit(result, None)
        except Exception as exc:
            self.signals.done.emit(None, exc)


class SettingsPage(ScrollPage):
    themeChanged = Signal(str)
    appearanceChanged = Signal()
    lyricsDisplayChanged = Signal(bool)
    statusChanged = Signal(str)
    _pool = __import__("PySide6.QtCore", fromlist=["QThreadPool"]).QThreadPool.globalInstance()

    def __init__(self, settings_service: Any, library_service: Any, playback_controller: Any, parent=None):
        super().__init__(parent)
        self.settings = settings_service
        self.library = library_service
        self.playback = playback_controller
        self.content.addWidget(QLabel("Settings"))
        self._section("Appearance")
        self.theme = QComboBox()
        self.theme.addItems(["dark", "light", "system"])
        self._row("Theme", self.theme)
        self.accent_button = QPushButton("Choose accent color")
        self._row("Accent color", self.accent_button)
        self.compact = QCheckBox("Use compact spacing")
        self._row("Density", self.compact)
        self.animations = QCheckBox("Enable interface animations")
        self._row("Motion", self.animations)

        self._section("Library")
        folders_frame = QFrame()
        folders_layout = QVBoxLayout(folders_frame)
        self.folders = QListWidget()
        folders_layout.addWidget(self.folders)
        folder_actions = QHBoxLayout()
        self.add_folder = QPushButton("Add folder")
        self.remove_folder = QPushButton("Remove selected")
        self.rescan = QPushButton("Rescan library")
        folder_actions.addWidget(self.add_folder)
        folder_actions.addWidget(self.remove_folder)
        folder_actions.addWidget(self.rescan)
        folders_layout.addLayout(folder_actions)
        self.content.addWidget(folders_frame)
        self.auto_scan = QCheckBox("Scan folders automatically at startup")
        self.content.addWidget(self.auto_scan)

        self._section("Playback")
        self.volume = QSlider(Qt.Orientation.Horizontal)
        self.volume.setRange(0, 100)
        self._row("Default volume", self.volume)
        self.shuffle_default = QCheckBox("Start playback in shuffle mode")
        self.content.addWidget(self.shuffle_default)
        self.repeat_default = QComboBox()
        self.repeat_default.addItems(["Off", "Repeat all", "Repeat one"])
        self._row("Repeat", self.repeat_default)
        if callable(getattr(playback_controller, "set_speed", None)):
            self.speed = QComboBox()
            self.speed.addItems(["0.75×", "0.9×", "1.0×", "1.1×", "1.25×", "1.5×", "2.0×"])
            self._row("Playback speed", self.speed)
            self.speed.currentTextChanged.connect(self._save_speed)
        if callable(getattr(playback_controller, "set_crossfade", None)):
            self.crossfade = QCheckBox("Enable crossfade")
            self.content.addWidget(self.crossfade)
            self.crossfade.toggled.connect(self._save_crossfade)

        self._section("Lyrics")
        self.lyrics_autoscroll = QCheckBox("Automatically follow timestamped lyrics")
        self.content.addWidget(self.lyrics_autoscroll)
        self.large_lyrics = QCheckBox("Use larger lyric text")
        self.content.addWidget(self.large_lyrics)

        self._section("Desktop")
        self.tray = QCheckBox("Show system tray icon")
        self.notifications = QCheckBox("Show playback notifications")
        self.media_keys = QCheckBox("Enable media keys")
        for widget in (self.tray, self.notifications, self.media_keys):
            widget.setEnabled(False)
            widget.setToolTip("This feature is not available in this build.")
        self.content.addWidget(self.tray)
        self.content.addWidget(self.notifications)
        self.content.addWidget(self.media_keys)

        self._section("Storage")
        storage = QHBoxLayout()
        self.clear_artwork = QPushButton("Clear artwork cache")
        self.export_data = QPushButton("Export data")
        self.reset = QPushButton("Reset settings")
        self.content.addLayout(storage)
        storage.addWidget(self.clear_artwork)
        storage.addWidget(self.export_data)
        storage.addWidget(self.reset)
        self.feedback = QLabel("")
        self.feedback.setProperty("role", "secondary")
        self.content.addWidget(self.feedback)

        self._load()
        self._volume_persist_timer = QTimer(self)
        self._volume_persist_timer.setSingleShot(True)
        self._volume_persist_timer.setInterval(300)
        self._volume_persist_timer.timeout.connect(lambda: self._set("playback.default_volume", self.volume.value() / 100))
        self.theme.currentTextChanged.connect(self._save_theme)
        self.accent_button.clicked.connect(self._choose_accent)
        self.compact.toggled.connect(self._save_density)
        self.animations.toggled.connect(self._save_animations)
        self.auto_scan.toggled.connect(lambda value: self._set("library.auto_scan", value))
        self.add_folder.clicked.connect(self._add_folder)
        self.remove_folder.clicked.connect(self._remove_folder)
        self.rescan.clicked.connect(self._rescan)
        self.volume.valueChanged.connect(self._preview_volume)
        self.volume.sliderReleased.connect(self._persist_volume)
        self.shuffle_default.toggled.connect(self._save_shuffle)
        self.repeat_default.currentIndexChanged.connect(self._save_repeat)
        self.lyrics_autoscroll.toggled.connect(lambda value: self._set("lyrics.auto_scroll", value))
        self.large_lyrics.toggled.connect(lambda value: self._set("lyrics.large_text", value))
        self.large_lyrics.toggled.connect(self.lyricsDisplayChanged)
        self._wire_optional_storage()

    def _get(self, key, default=None):
        try:
            return self.settings.get(key, default) if self.settings else default
        except Exception:
            return default

    def _set(self, key, value):
        try:
            if not self.settings or not callable(getattr(self.settings, "set", None)):
                raise RuntimeError("Settings service is unavailable")
            self.settings.set(key, value)
            self.feedback.setText("Setting saved.")
        except Exception as exc:
            self.feedback.setText(f"Couldn't save setting: {exc}")

    def _load(self):
        get = self._get
        self.theme.setCurrentText(str(get("appearance.theme", "dark")))
        self.compact.setChecked(get("appearance.density", "comfortable") == "compact")
        self.animations.setChecked(bool(get("appearance.animations", True)))
        folders = get("library.folders", []) or []
        self.folders.addItems([str(path) for path in folders])
        self.auto_scan.setChecked(bool(get("library.auto_scan", True)))
        try:
            self.volume.setValue(max(0, min(100, int(float(get("playback.default_volume", 0.7)) * 100))))
        except (TypeError, ValueError):
            self.volume.setValue(70)
        self.shuffle_default.setChecked(bool(get("playback.shuffle", False)))
        repeat = get("playback.repeat", 0)
        repeat = {"off": 0, "all": 1, "one": 2}.get(str(repeat).lower(), repeat)
        try:
            self.repeat_default.setCurrentIndex(max(0, min(2, int(repeat))))
        except (TypeError, ValueError):
            self.repeat_default.setCurrentIndex(0)
        self.lyrics_autoscroll.setChecked(bool(get("lyrics.auto_scroll", True)))
        self.large_lyrics.setChecked(bool(get("lyrics.large_text", False)))
        self.tray.setChecked(bool(get("desktop.tray", True)))
        self.notifications.setChecked(bool(get("desktop.notifications", True)))
        self.media_keys.setChecked(bool(get("desktop.media_keys", True)))
        if hasattr(self, "speed"):
            self.speed.setCurrentText(str(get("playback.speed", "1.0×")))
        if hasattr(self, "crossfade"):
            self.crossfade.setChecked(bool(get("playback.crossfade", False)))

    def _section(self, title: str) -> None:
        label = QLabel(title)
        label.setStyleSheet("font-size: 18px; font-weight: 700; margin-top: 6px;")
        self.content.addWidget(label)

    def _row(self, title: str, widget: QWidget) -> None:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        label = QLabel(title)
        layout.addWidget(label, 1)
        widget.setMinimumWidth(210)
        layout.addWidget(widget)
        self.content.addWidget(row)

    def _save_theme(self, theme: str) -> None:
        self._set("appearance.theme", theme)
        self.themeChanged.emit(theme)

    def _save_density(self, compact: bool) -> None:
        self._set("appearance.density", "compact" if compact else "comfortable")
        self.appearanceChanged.emit()

    def _save_animations(self, enabled: bool) -> None:
        self._set("appearance.animations", enabled)
        self.appearanceChanged.emit()

    def _choose_accent(self) -> None:
        from PySide6.QtGui import QColor
        color = QColorDialog.getColor(QColor(self._get("appearance.accent", "#8B7CFF")), self, "Accent color")
        if color.isValid():
            self._set("appearance.accent", color.name())
            self.themeChanged.emit(str(self._get("appearance.theme", "dark")))

    def _add_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Add music folder")
        if not folder:
            return
        folders = [self.folders.item(i).text() for i in range(self.folders.count())]
        if folder not in folders:
            register = getattr(self.library, "add_library_folder", None)
            if callable(register):
                try:
                    folder = register(folder)
                except Exception as exc:
                    self.feedback.setText(f"Couldn't add library folder: {exc}")
                    return
            folders.append(folder)
            self.folders.addItem(folder)
            self._set("library.folders", folders)

    def _remove_folder(self) -> None:
        row = self.folders.currentRow()
        item = self.folders.item(row) if row >= 0 else None
        if item:
            remove = getattr(self.library, "remove_library_folder", None)
            if callable(remove):
                try:
                    remove(item.text())
                except Exception as exc:
                    self.feedback.setText(f"Couldn't remove library folder: {exc}")
                    return
            self.folders.takeItem(row)
            self._set("library.folders", [self.folders.item(i).text() for i in range(self.folders.count())])

    def _rescan(self) -> None:
        if not callable(getattr(self.library, "scan_library", None)):
            self.feedback.setText("Library scanning is unavailable.")
            return
        folders = [self.folders.item(i).text() for i in range(self.folders.count())]
        if not folders:
            self.feedback.setText("Add a library folder before scanning.")
            return
        self.rescan.setEnabled(False)
        self.feedback.setText("Scanning library in the background…")
        task = _ScanTask(self.library, folders)
        task.signals.done.connect(self._scan_done)
        self._pool.start(task)

    def _scan_done(self, result, error) -> None:
        is_worker = callable(getattr(result, "isRunning", None))
        if error or not is_worker:
            self.rescan.setEnabled(True)
        message = f"Library scan failed: {error}" if error else "Library scan started."
        self.feedback.setText(message)
        self.statusChanged.emit(message)

    def scan_finished(self, message: str = "Library scan complete.") -> None:
        self.rescan.setEnabled(True)
        self.feedback.setText(message)

    def _preview_volume(self, value: int) -> None:
        if callable(getattr(self.playback, "set_volume", None)):
            try:
                self.playback.set_volume(value / 100)
            except Exception as exc:
                self.feedback.setText(f"Couldn't change playback volume: {exc}")
        self._volume_persist_timer.start()

    def _persist_volume(self) -> None:
        self._volume_persist_timer.stop()
        self._set("playback.default_volume", self.volume.value() / 100)

    def _save_shuffle(self, enabled: bool) -> None:
        self._set("playback.shuffle", enabled)
        if callable(getattr(self.playback, "set_shuffle", None)):
            try:
                self.playback.set_shuffle(enabled)
            except Exception as exc:
                self.feedback.setText(f"Couldn't change shuffle: {exc}")

    def _save_repeat(self, index: int) -> None:
        self._set("playback.repeat", index)
        if callable(getattr(self.playback, "set_repeat_mode", None)):
            try:
                self.playback.set_repeat_mode(("off", "all", "one")[max(0, min(2, index))])
            except Exception as exc:
                self.feedback.setText(f"Couldn't change repeat mode: {exc}")

    def _save_speed(self, text: str) -> None:
        speed = float(text.replace("×", ""))
        self._set("playback.speed", text)
        self.playback.set_speed(speed)

    def _save_crossfade(self, enabled: bool) -> None:
        self._set("playback.crossfade", enabled)
        self.playback.set_crossfade(enabled)

    def _wire_optional_storage(self) -> None:
        targets = (
            (self.clear_artwork, self.library, "clear_artwork_cache", "Artwork cache cleanup is unavailable."),
            (self.export_data, self.settings, "export_data", "Data export is unavailable."),
            (self.reset, self.settings, "reset", "Reset is unavailable."),
        )
        for button, service, method_name, unavailable in targets:
            method = getattr(service, method_name, None) if service else None
            button.setEnabled(callable(method))
            button.setToolTip("Run this storage action" if callable(method) else unavailable)
            if callable(method):
                button.clicked.connect(lambda _checked=False, m=method, b=button: self._start_storage_action(m, b.text()))

    def _start_storage_action(self, method, label: str) -> None:
        args = ()
        if label == "Export data":
            path, _ = QFileDialog.getSaveFileName(self, "Export application data", "sonora-data.json", "JSON (*.json);;All files (*.*)")
            if not path:
                return
            args = (path,)
        if label == "Reset settings":
            answer = QMessageBox.question(self, "Reset settings", "Reset saved settings to their defaults?", QMessageBox.StandardButton.Reset | QMessageBox.StandardButton.Cancel, QMessageBox.StandardButton.Cancel)
            if answer != QMessageBox.StandardButton.Reset:
                return
        self.feedback.setText(f"{label} in progress…")
        task = _ActionTask(method, args)
        task.signals.done.connect(lambda result, error, name=label: self._storage_action_done(name, result, error))
        self._pool.start(task)

    def _storage_action_done(self, label, _result, error) -> None:
        self.feedback.setText(f"{label} failed: {error}" if error else f"{label} complete.")
