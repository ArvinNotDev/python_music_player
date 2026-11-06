"""Reusable presentation components shared by the pages."""

from __future__ import annotations

from collections import OrderedDict
from pathlib import Path
from typing import Any

from PySide6.QtCore import QByteArray, QObject, QRunnable, QThreadPool, QSize, Qt, Signal
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QSizePolicy, QToolButton,
    QVBoxLayout, QWidget,
)

from .icons import icon
from ..theme import PALETTES, resolve_theme


class IconButton(QToolButton):
    def __init__(self, icon_name: str, tooltip: str, parent: QWidget | None = None, *, checkable: bool = False):
        super().__init__(parent)
        self.icon_name = icon_name
        self.setToolTip(tooltip)
        self.setAccessibleName(tooltip)
        self.setIcon(icon(icon_name))
        self.setIconSize(QSize(18, 18))
        self.setFixedSize(36, 36)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setCheckable(checkable)


class SearchBox(QFrame):
    textChanged = Signal(str)
    returnPressed = Signal()

    def __init__(self, placeholder: str = "Search your library", parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("SearchBox")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 8, 0)
        layout.setSpacing(8)
        search_icon = QLabel()
        search_icon.setPixmap(icon("search", "#7E8492", 18).pixmap(18, 18))
        self.input = QLineEdit()
        self.input.setPlaceholderText(placeholder)
        self.input.setClearButtonEnabled(True)
        self.input.setFrame(False)
        self.input.textChanged.connect(self.textChanged)
        self.input.returnPressed.connect(self.returnPressed)
        layout.addWidget(search_icon)
        layout.addWidget(self.input, 1)
        self.setStyleSheet("QFrame#SearchBox { border: 1px solid palette(mid); border-radius: 9px; } QFrame#SearchBox QLineEdit { border: 0; background: transparent; padding-left: 0; }")

    def setFocus(self) -> None:
        self.input.setFocus()
        self.input.selectAll()

    def clear(self) -> None:
        self.input.clear()


class SectionHeader(QWidget):
    def __init__(self, title: str, subtitle: str = "", action_text: str = "", parent: QWidget | None = None):
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        title_col = QVBoxLayout()
        title_col.setSpacing(3)
        heading = QLabel(title)
        heading.setStyleSheet("font-size: 22px; font-weight: 700;")
        title_col.addWidget(heading)
        if subtitle:
            sub = QLabel(subtitle)
            sub.setProperty("role", "secondary")
            title_col.addWidget(sub)
        row.addLayout(title_col, 1)
        self.action = QPushButton(action_text) if action_text else None
        if self.action:
            row.addWidget(self.action, 0, Qt.AlignmentFlag.AlignBottom)


class EmptyState(QFrame):
    def __init__(self, title: str, description: str = "", action_text: str = "", parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("Surface")
        self.setMinimumHeight(190)
        col = QVBoxLayout(self)
        col.setContentsMargins(28, 28, 28, 28)
        col.setAlignment(Qt.AlignmentFlag.AlignCenter)
        mark = QLabel("♪")
        mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        mark.setStyleSheet("font-size: 30px; color: #8B7CFF;")
        label = QLabel(title)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet("font-size: 17px; font-weight: 650;")
        self.title_label = label
        col.addWidget(mark)
        col.addWidget(label)
        if description:
            detail = QLabel(description)
            detail.setProperty("role", "secondary")
            detail.setWordWrap(True)
            detail.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.description_label = detail
            col.addWidget(detail)
        self.action = QPushButton(action_text) if action_text else None
        if self.action:
            self.action.setProperty("primary", True)
            self.action.setMinimumWidth(120)
            col.addSpacing(8)
            col.addWidget(self.action, 0, Qt.AlignmentFlag.AlignCenter)


class ArtworkSignals(QObject):
    loaded = Signal(str, QImage)
    failed = Signal(str)


class _ArtworkTask(QRunnable):
    def __init__(self, key: str, service: Any, track: Any, signals: ArtworkSignals):
        super().__init__()
        self.key = key
        self.service = service
        self.track = track
        self.signals = signals

    def run(self) -> None:
        try:
            if self.service is None:
                result = self.track.get("artwork") if isinstance(self.track, dict) else getattr(self.track, "artwork", None)
            else:
                result = self.service.read_artwork(self.track)
            if isinstance(result, dict):
                result = result.get("image", result.get("data", result.get("path")))
            image = QImage()
            if isinstance(result, QImage):
                image = result
            elif isinstance(result, QPixmap):
                image = result.toImage()
            elif isinstance(result, (bytes, bytearray)):
                image.loadFromData(QByteArray(result))
            elif isinstance(result, (str, Path)) and result:
                image.load(str(result))
            if image.isNull():
                self.signals.failed.emit(self.key)
            else:
                self.signals.loaded.emit(self.key, image)
        except Exception:
            self.signals.failed.emit(self.key)


_ART_CACHE: OrderedDict[str, QImage] = OrderedDict()
_ART_CACHE_LIMIT = 160


class ArtworkLabel(QLabel):
    """Artwork widget with bounded cache and background service reads."""
    _pool = QThreadPool.globalInstance()
    _signals = ArtworkSignals()

    def __init__(self, size: int = 56, parent: QWidget | None = None):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setScaledContents(False)
        self.setStyleSheet("background: #242630; border-radius: 8px; color: #8B7CFF; font-size: 20px;")
        self.setText("♪")
        self._key = ""
        self._target_size = size
        self._signals.loaded.connect(self._on_loaded)
        self._signals.failed.connect(self._on_failed)

    def set_track(self, track: Any, metadata_service: Any = None) -> None:
        from ..services import track_id
        key = str(track_id(track))
        self._key = key
        self.setPixmap(QPixmap())
        self.setText("♪")
        if not track:
            return
        if key in _ART_CACHE:
            image = _ART_CACHE.pop(key)
            _ART_CACHE[key] = image
            self._apply(image)
            return
        self._pool.start(_ArtworkTask(key, metadata_service, track, self._signals))

    @staticmethod
    def invalidate(track: Any) -> None:
        from ..services import track_id
        _ART_CACHE.pop(str(track_id(track)), None)

    def _on_loaded(self, key: str, image: QImage) -> None:
        _ART_CACHE[key] = image
        _ART_CACHE.move_to_end(key)
        while len(_ART_CACHE) > _ART_CACHE_LIMIT:
            _ART_CACHE.popitem(last=False)
        if key == self._key:
            self._apply(image)

    def _on_failed(self, key: str) -> None:
        if key == self._key:
            self.setPixmap(QPixmap())
            self.setText("♪")

    def _apply(self, image: QImage) -> None:
        pixmap = QPixmap.fromImage(image).scaled(
            self._target_size, self._target_size, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.setText("")
        self.setPixmap(pixmap)


def themed_color(name: str, theme: str = "dark") -> str:
    return getattr(PALETTES[resolve_theme(theme)], name)
