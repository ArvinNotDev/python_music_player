"""Metadata and lyrics editors backed by injected services."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QObject, QRunnable, Signal, Qt
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QHBoxLayout,
    QLabel, QLineEdit, QMessageBox, QPushButton, QScrollArea, QSpinBox, QTextEdit,
    QVBoxLayout, QWidget,
)

from ..components import ArtworkLabel
from ..services import value


class _TaskSignals(QObject):
    done = Signal(object, object)


class _ServiceTask(QRunnable):
    def __init__(self, method, args: tuple, kwargs: dict | None = None):
        super().__init__()
        self.method, self.args, self.kwargs = method, args, kwargs or {}
        self.signals = _TaskSignals()

    def run(self):
        try:
            self.signals.done.emit(self.method(*self.args, **self.kwargs), None)
        except Exception as exc:
            self.signals.done.emit(None, exc)


def _save_lyrics_compatible(method, track, text: str, is_lrc: bool, storage: str):
    mode = "lrc" if is_lrc else "plain"
    try:
        return method(track, text, mode=mode, storage=storage)
    except TypeError:
        try:
            return method(track, text, mode=mode)
        except TypeError:
            try:
                return method(track, text, is_lrc=is_lrc)
            except TypeError:
                try:
                    return method(track, text, is_lrc)
                except TypeError:
                    return method(track, text)


class MetadataEditorDialog(QDialog):
    """Asynchronous metadata read/write dialog."""
    _pool = __import__("PySide6.QtCore", fromlist=["QThreadPool"]).QThreadPool.globalInstance()

    def __init__(self, track: Any, metadata_service: Any, parent=None):
        super().__init__(parent)
        self.track = track
        self.metadata_service = metadata_service
        self.setWindowTitle("Track details")
        self.setMinimumSize(620, 600)
        self._original: dict[str, Any] = {}
        root = QVBoxLayout(self)
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(16)
        art_row = QHBoxLayout()
        self.artwork = ArtworkLabel(132)
        self.artwork.set_track(track, metadata_service)
        art_row.addWidget(self.artwork)
        art_actions = QVBoxLayout()
        art_actions.addWidget(QLabel("Artwork"))
        self.replace_art = QPushButton("Replace artwork…")
        self.remove_art = QPushButton("Remove artwork")
        self.preview_art = QPushButton("Preview")
        art_actions.addWidget(self.replace_art)
        art_actions.addWidget(self.remove_art)
        art_actions.addWidget(self.preview_art)
        art_actions.addStretch()
        art_row.addLayout(art_actions, 1)
        layout.addLayout(art_row)
        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        self.fields: dict[str, QLineEdit] = {}
        for key, label in (
            ("title", "Title"), ("artist", "Artist"), ("album", "Album"),
            ("album_artist", "Album artist"), ("track_number", "Track number"),
            ("disc_number", "Disc number"), ("year", "Year"), ("genre", "Genre"),
            ("composer", "Composer"), ("comment", "Comment"),
        ):
            field = QLineEdit()
            field.setObjectName(f"metadata_{key}")
            self.fields[key] = field
            form.addRow(label, field)
        layout.addLayout(form)
        self.destination = QLabel("Changes will be written to the audio file's metadata.")
        self.destination.setProperty("role", "muted")
        layout.addWidget(self.destination)
        root.addWidget(content)
        self.status = QLabel("Loading track metadata…")
        self.status.setProperty("role", "secondary")
        root.addWidget(self.status)
        buttons = QDialogButtonBox()
        self.revert_button = buttons.addButton("Revert", QDialogButtonBox.ButtonRole.ResetRole)
        self.cancel_button = buttons.addButton(QDialogButtonBox.StandardButton.Cancel)
        self.save_button = buttons.addButton(QDialogButtonBox.StandardButton.Save)
        self.save_button.setProperty("primary", True)
        root.addWidget(buttons)
        self.replace_art.clicked.connect(self._choose_artwork)
        self.remove_art.clicked.connect(self._remove_artwork)
        self.preview_art.clicked.connect(self._preview_artwork)
        self.revert_button.clicked.connect(self._revert)
        self.cancel_button.clicked.connect(self.reject)
        self.save_button.clicked.connect(self._save)
        self._artwork_path: str | None = None
        self._remove_art = False
        self._set_enabled(False)
        self._run(self.metadata_service.read_metadata, (track,), self._loaded)

    def _run(self, method, args, callback, *extra):
        task = _ServiceTask(method, args)
        task.signals.done.connect(lambda result, error: callback(result, error, *extra))
        self._pool.start(task)

    def _loaded(self, result, error) -> None:
        if error:
            self.status.setText(f"Couldn't read metadata: {error}")
            return
        if not isinstance(result, dict):
            result = {key: value(result, key, default="") for key in self.fields}
        self._original = {key: result.get(key, "") for key in self.fields}
        self._populate(self._original)
        self.status.setText("Metadata loaded. Some fields depend on the audio file format.")
        self._set_enabled(True)

    def _populate(self, data: dict[str, Any]) -> None:
        for key, field in self.fields.items():
            field.setText(str(data.get(key, "") or ""))

    def _set_enabled(self, enabled: bool) -> None:
        self.save_button.setEnabled(enabled)
        for field in self.fields.values():
            field.setEnabled(enabled)

    def _choose_artwork(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Choose artwork", "", "Images (*.png *.jpg *.jpeg *.webp *.gif)")
        if path:
            self._artwork_path = path
            self._remove_art = False
            self.artwork.set_track({"id": path, "artwork": path}, None)

    def _remove_artwork(self) -> None:
        self._artwork_path = None
        self._remove_art = True
        self.artwork.set_track({}, None)

    def _preview_artwork(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("Artwork preview")
        dialog.setMinimumSize(400, 440)
        layout = QVBoxLayout(dialog)
        preview = ArtworkLabel(360, dialog)
        track = {"id": self._artwork_path, "artwork": self._artwork_path} if self._artwork_path else self.track
        preview.set_track(track, None if self._artwork_path else self.metadata_service)
        layout.addWidget(preview, 0, Qt.AlignmentFlag.AlignCenter)
        dialog.exec()

    def _revert(self) -> None:
        self._populate(self._original)
        self._artwork_path = None
        self._remove_art = False
        self.artwork.set_track(self.track, self.metadata_service)
        self.status.setText("Changes reverted.")

    def _save(self) -> None:
        metadata = {key: field.text().strip() for key, field in self.fields.items()}
        if self._artwork_path:
            metadata["artwork_path"] = self._artwork_path
        elif self._remove_art:
            metadata["artwork"] = None
        self.save_button.setEnabled(False)
        self.status.setText("Saving metadata…")
        self._run(self.metadata_service.write_metadata, (self.track, metadata), self._saved)

    def _saved(self, result, error) -> None:
        self.save_button.setEnabled(True)
        if error or result is False:
            self.status.setText(f"Couldn't save metadata: {error or 'unsupported field or file format'}")
            QMessageBox.warning(self, "Metadata not saved", self.status.text())
            return
        ArtworkLabel.invalidate(self.track)
        self.status.setText("Metadata saved successfully.")
        self.accept()


class LyricsEditorDialog(QDialog):
    _pool = MetadataEditorDialog._pool

    def __init__(self, track: Any, lyrics_service: Any, lyrics: Any = None, parent=None):
        super().__init__(parent)
        self.track = track
        self.service = lyrics_service
        self._original = self._lyrics_text(lyrics)
        self.setWindowTitle("Edit lyrics")
        self.setMinimumSize(680, 520)
        layout = QVBoxLayout(self)
        top = QHBoxLayout()
        self.mode = QComboBox()
        self.mode.addItems(["Plain lyrics", "Timestamped LRC"])
        if self._original and "[00:" in self._original:
            self.mode.setCurrentIndex(1)
        top.addWidget(QLabel("Format"))
        top.addWidget(self.mode)
        self.storage = QComboBox()
        self.storage.addItem("Sidecar file", "sidecar")
        self.storage.addItem("Embedded in audio file", "embedded")
        default_storage = getattr(lyrics_service, "default_storage", "sidecar")
        self.storage.setCurrentIndex(max(0, self.storage.findData(default_storage)))
        top.addWidget(QLabel("Save as"))
        top.addWidget(self.storage)
        top.addStretch()
        layout.addLayout(top)
        self.editor = QTextEdit()
        self.editor.setPlaceholderText("Enter lyrics…")
        self.editor.setPlainText(self._original)
        self.editor.textChanged.connect(self._set_dirty)
        layout.addWidget(self.editor, 1)
        self.destination = QLabel("Lyrics are saved through your configured lyrics service.")
        self.destination.setProperty("role", "muted")
        layout.addWidget(self.destination)
        self.status = QLabel("")
        self.status.setProperty("role", "secondary")
        layout.addWidget(self.status)
        buttons = QDialogButtonBox()
        self.cancel = buttons.addButton(QDialogButtonBox.StandardButton.Cancel)
        self.save = buttons.addButton(QDialogButtonBox.StandardButton.Save)
        self.save.setProperty("primary", True)
        layout.addWidget(buttons)
        self.cancel.clicked.connect(self.reject)
        self.save.clicked.connect(self._save)
        self._dirty = False

    @staticmethod
    def _lyrics_text(lyrics: Any) -> str:
        if isinstance(lyrics, str):
            return lyrics
        return str(value(lyrics, "text", "lyrics", "content", default="") or "")

    def _set_dirty(self) -> None:
        self._dirty = self.editor.toPlainText() != self._original

    def _save(self) -> None:
        method = getattr(self.service, "save_lyrics", None)
        if not callable(method):
            QMessageBox.warning(self, "Lyrics unavailable", "The configured lyrics service cannot save lyrics.")
            return
        self.save.setEnabled(False)
        self.status.setText("Saving lyrics…")
        task = _ServiceTask(_save_lyrics_compatible, (
            method, self.track, self.editor.toPlainText(), self.mode.currentIndex() == 1,
            str(self.storage.currentData()),
        ))
        task.signals.done.connect(self._saved)
        self._pool.start(task)

    def _saved(self, result, error) -> None:
        self.save.setEnabled(True)
        if error or result is False:
            self.status.setText(f"Couldn't save lyrics: {error or 'service rejected the lyrics'}")
            return
        self._dirty = False
        self.accept()

    def closeEvent(self, event) -> None:
        if self._dirty:
            answer = QMessageBox.question(self, "Discard unsaved lyrics?", "Your lyric edits have not been saved.", QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel, QMessageBox.StandardButton.Cancel)
            if answer != QMessageBox.StandardButton.Discard:
                event.ignore()
                return
        self._dirty = False
        event.accept()

    def reject(self) -> None:
        if self._dirty:
            answer = QMessageBox.question(self, "Discard unsaved lyrics?", "Your lyric edits have not been saved.", QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel, QMessageBox.StandardButton.Cancel)
            if answer != QMessageBox.StandardButton.Discard:
                return
        self._dirty = False
        super().reject()
