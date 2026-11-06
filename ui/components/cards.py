"""Artwork-led collection and track cards."""

from __future__ import annotations

from typing import Any, Callable

from PySide6.QtCore import Qt, Signal, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QFrame, QGraphicsDropShadowEffect, QGridLayout, QHBoxLayout, QLabel, QScrollArea, QSizePolicy, QVBoxLayout,
    QWidget,
)

from .common import ArtworkLabel, IconButton
from ..services import track_title, value


class CollectionCard(QFrame):
    clicked = Signal(object)

    def __init__(self, item: Any, kind: str, metadata_service: Any = None, parent=None):
        super().__init__(parent)
        self.item = item
        self.kind = kind
        self.setObjectName("CollectionCard")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.setFixedWidth(174)
        col = QVBoxLayout(self)
        col.setContentsMargins(0, 0, 0, 4)
        col.setSpacing(8)
        art = ArtworkLabel(158, self)
        art.set_track(item, metadata_service)
        art.setStyleSheet("background: #242630; border-radius: 10px; color: #A095FF; font-size: 34px;")
        art.setCursor(Qt.CursorShape.PointingHandCursor)
        art.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.art = art
        col.addWidget(art, 0, Qt.AlignmentFlag.AlignHCenter)
        title = QLabel(str(value(item, "title", "name", "album", "artist", default="Unknown")))
        title.setStyleSheet("font-weight: 650;")
        title.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        title.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        title.setToolTip(title.text())
        title.setWordWrap(False)
        title.setText(title.fontMetrics().elidedText(title.text(), Qt.TextElideMode.ElideRight, 164))
        col.addWidget(title)
        detail = self._detail(item, kind)
        caption = QLabel(detail)
        caption.setProperty("role", "secondary")
        caption.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        caption.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        caption.setWordWrap(False)
        caption.setToolTip(detail)
        caption.setText(caption.fontMetrics().elidedText(detail, Qt.TextElideMode.ElideRight, 164))
        col.addWidget(caption)
        self._shadow_effect = QGraphicsDropShadowEffect(self)
        self._shadow_effect.setBlurRadius(0)
        self._shadow_effect.setOffset(0, 2)
        self._shadow_effect.setColor(QColor(139, 124, 255, 72))
        self.setGraphicsEffect(self._shadow_effect)
        self._hover_animation = None
        self.setStyleSheet("QFrame#CollectionCard { background: transparent; border: 1px solid transparent; border-radius: 10px; } QFrame#CollectionCard:hover { background: rgba(130, 120, 255, 0.08); border-color: rgba(130, 120, 255, 0.16); }")

    _animations_enabled = True

    @classmethod
    def set_animations_enabled_for_all(cls, enabled: bool) -> None:
        cls._animations_enabled = bool(enabled)

    def _animate_shadow(self, hovered: bool) -> None:
        if not self._animations_enabled:
            self._shadow_effect.setBlurRadius(0)
            return
        if self._hover_animation is not None:
            self._hover_animation.stop()
            self._hover_animation.deleteLater()
            self._hover_animation = None
        animation = QPropertyAnimation(self._shadow_effect, b"blurRadius", self)
        animation.setDuration(210)
        animation.setStartValue(self._shadow_effect.blurRadius())
        animation.setEndValue(19.0 if hovered else 0.0)
        animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        animation.finished.connect(lambda current=animation: self._finish_hover_animation(current))
        self._hover_animation = animation
        animation.start()

    def _finish_hover_animation(self, animation: QPropertyAnimation) -> None:
        if self._hover_animation is animation:
            self._hover_animation = None
        animation.deleteLater()

    def enterEvent(self, event) -> None:
        self._animate_shadow(True)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._animate_shadow(False)
        super().leaveEvent(event)

    @staticmethod
    def _detail(item: Any, kind: str) -> str:
        if kind == "album":
            artist = value(item, "artist", "album_artist", default="Unknown artist")
            year = value(item, "year", "release_year", default="")
            count = value(item, "track_count", default="")
            extra = f" · {count} tracks" if count else ""
            return f"{artist}{f' · {year}' if year else ''}{extra}"
        if kind == "artist":
            albums = value(item, "album_count", default="")
            return f"{albums} albums" if albums else "Artist"
        return str(value(item, "artist", "subtitle", default=""))

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.item)
        super().mousePressEvent(event)


class ResponsiveCardGrid(QWidget):
    itemClicked = Signal(object)

    def __init__(self, kind: str, metadata_service: Any = None, parent=None):
        super().__init__(parent)
        self.kind = kind
        self.metadata_service = metadata_service
        self._items: list[Any] = []
        self._cards: list[CollectionCard] = []
        self._columns = 0
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setHorizontalSpacing(16)
        self.grid.setVerticalSpacing(20)

    def set_items(self, items: list[Any]) -> None:
        self._items = list(items)
        while self.grid.count():
            self.grid.takeAt(0)
        for card in self._cards:
            card.deleteLater()
        self._cards.clear()
        for item in self._items:
            card = CollectionCard(item, self.kind, self.metadata_service, self)
            card.clicked.connect(self.itemClicked)
            self._cards.append(card)
        self._layout_cards(force=True)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._layout_cards()

    def _layout_cards(self, force: bool = False) -> None:
        columns = max(1, self.width() // 190)
        if not force and columns == self._columns:
            return
        self._columns = columns
        while self.grid.count():
            self.grid.takeAt(0)
        for index, card in enumerate(self._cards):
            self.grid.addWidget(card, index // columns, index % columns, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.grid.setRowStretch((len(self._items) + columns - 1) // columns, 1)


class TrackCardStrip(QWidget):
    trackActivated = Signal(object)

    def __init__(self, metadata_service: Any = None, parent=None):
        super().__init__(parent)
        self.metadata_service = metadata_service
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.container = QWidget()
        self.row = QHBoxLayout(self.container)
        self.row.setContentsMargins(0, 0, 0, 0)
        self.row.setSpacing(14)
        self.row.addStretch(1)
        self.scroll.setWidget(self.container)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.scroll)

    def set_tracks(self, tracks: list[Any]) -> None:
        while self.row.count():
            item = self.row.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for track in tracks:
            card = QWidget()
            card.setFixedWidth(128)
            col = QVBoxLayout(card)
            col.setContentsMargins(0, 0, 0, 0)
            col.setSpacing(7)
            cover = ArtworkLabel(116, card)
            cover.set_track(track, self.metadata_service)
            cover.setStyleSheet("background: #242630; border-radius: 9px; color: #A095FF; font-size: 28px;")
            cover.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            col.addWidget(cover, 0, Qt.AlignmentFlag.AlignHCenter)
            title = QLabel(track_title(track))
            title.setToolTip(title.text())
            title.setText(title.fontMetrics().elidedText(title.text(), Qt.TextElideMode.ElideRight, 124))
            title.setStyleSheet("font-weight: 600;")
            title.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            subtitle = str(value(track, "artist", "artists", default="Unknown artist"))
            artist = QLabel(subtitle)
            artist.setProperty("role", "secondary")
            artist.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            artist.setText(artist.fontMetrics().elidedText(subtitle, Qt.TextElideMode.ElideRight, 124))
            col.addWidget(title)
            col.addWidget(artist)
            card.setCursor(Qt.CursorShape.PointingHandCursor)
            card.mousePressEvent = lambda event, t=track: self.trackActivated.emit(t) if event.button() == Qt.MouseButton.LeftButton else None
            self.row.insertWidget(self.row.count(), card)
        self.row.addStretch(1)
