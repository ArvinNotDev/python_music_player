"""Track-table artwork delegate with asynchronous artwork reads."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtWidgets import QStyledItemDelegate, QStyleOptionViewItem

from ..components.common import ArtworkLabel, _ART_CACHE, _ArtworkTask
from ..models import TrackTableModel
from ..services import track_id


class ArtworkDelegate(QStyledItemDelegate):
    _pending: set[str] = set()

    def __init__(self, metadata_service: Any = None, parent=None):
        super().__init__(parent)
        self.metadata_service = metadata_service
        ArtworkLabel._signals.loaded.connect(self._artwork_ready)
        ArtworkLabel._signals.failed.connect(self._artwork_ready_failed)
        self._seen: set[str] = set()

    def sizeHint(self, option: QStyleOptionViewItem, index) -> QSize:
        return QSize(54, 56)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index) -> None:
        # The view supplies a QSortFilterProxyModel index, not the source model.
        # Custom roles belong to TrackTableModel and are forwarded by the proxy.
        track = index.data(TrackTableModel.TrackRole)
        key = str(track_id(track))
        self._seen.add(key)
        if key not in _ART_CACHE and key not in self._pending and track:
            self._pending.add(key)
            ArtworkLabel._pool.start(_ArtworkTask(key, self.metadata_service, track, ArtworkLabel._signals))
        rect = option.rect.adjusted(8, 5, -4, -5)
        pix = QPixmap.fromImage(_ART_CACHE[key]) if key in _ART_CACHE else QPixmap()
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if not pix.isNull():
            side = min(rect.height(), rect.width())
            target = QRect(rect.left(), rect.top() + (rect.height() - side) // 2, side, side)
            scaled = pix.scaled(side, side, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
            painter.setClipRect(target)
            painter.drawPixmap(target, scaled)
        else:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor("#282936"))
            painter.drawRoundedRect(rect.left(), rect.top() + 1, min(rect.height(), rect.width()), min(rect.height(), rect.width()), 6, 6)
            painter.setPen(QColor("#A095FF"))
            painter.drawText(rect.left(), rect.top() + 1, min(rect.height(), rect.width()), min(rect.height(), rect.width()), Qt.AlignmentFlag.AlignCenter, "♪")
        painter.restore()

    def _artwork_ready(self, key: str, _image) -> None:
        self._pending.discard(key)
        self._refresh_rows(key)

    def _artwork_ready_failed(self, key: str) -> None:
        self._pending.discard(key)
        self._refresh_rows(key)

    def _refresh_rows(self, key: str) -> None:
        if key not in self._seen:
            return
        view = self.parent()
        model = view.model() if view and hasattr(view, "model") else None
        if model is None:
            return
        if view.isVisible():
            view.viewport().update()
