"""A softly animated cursor highlight, rasterized once per theme."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QTimer, Qt
from PySide6.QtGui import QColor, QPainter, QPen, QRadialGradient, QPixmap
from PySide6.QtWidgets import QLabel, QWidget


class CursorSpotlight(QLabel):
    RADIUS = 166
    DIAMETER = RADIUS * 2

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setObjectName("CursorSpotlight")
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAutoFillBackground(False)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setFixedSize(self.DIAMETER, self.DIAMETER)
        self.setStyleSheet(
            "QLabel#CursorSpotlight { background: transparent; border: none; padding: 0; }"
        )
        self._position = QPointF()
        self._target = QPointF()
        self._has_position = False
        self._animations_enabled = True
        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._advance)
        self.apply_theme()
        self.hide()

    def set_animations_enabled(self, enabled: bool) -> None:
        self._animations_enabled = bool(enabled)
        if not self._animations_enabled and self._has_position:
            self._timer.stop()
            self._position = QPointF(self._target)
            self._move_to_position()

    def apply_theme(self, theme: str = "dark", accent: str = "#8B7CFF") -> None:
        accent_color = QColor(accent)
        if not accent_color.isValid():
            accent_color = QColor("#8B7CFF")
        self.setPixmap(self._build_gradient_pixmap(theme == "light", accent_color))

    @classmethod
    def _build_gradient_pixmap(cls, light: bool, accent: QColor) -> QPixmap:
        pixmap = QPixmap(cls.DIAMETER, cls.DIAMETER)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        center = QPointF(cls.RADIUS, cls.RADIUS)

        primary = QColor(accent)
        primary.setAlpha(48 if light else 38)
        secondary = QColor("#38BDF8" if light else "#43D4DE")
        secondary.setAlpha(27 if light else 30)
        outer = QColor("#6478E8" if light else "#526BCE")
        outer.setAlpha(10)

        gradient = QRadialGradient(center, cls.RADIUS)
        gradient.setColorAt(0.0, primary)
        gradient.setColorAt(0.38, secondary)
        gradient.setColorAt(0.76, outer)
        gradient.setColorAt(1.0, QColor(outer.red(), outer.green(), outer.blue(), 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(gradient)
        painter.drawEllipse(0, 0, cls.DIAMETER, cls.DIAMETER)

        painter.setBrush(Qt.BrushStyle.NoBrush)
        ring = QColor(accent)
        ring.setAlpha(20 if light else 15)
        painter.setPen(QPen(ring, 1))
        painter.drawEllipse(center, cls.RADIUS * 0.43, cls.RADIUS * 0.43)
        outer_ring = QColor(secondary)
        outer_ring.setAlpha(10)
        painter.setPen(QPen(outer_ring, 1))
        painter.drawEllipse(center, cls.RADIUS * 0.76, cls.RADIUS * 0.76)
        painter.end()
        return pixmap

    def set_target(self, position) -> None:
        target = QPointF(position)
        if not self._has_position:
            self._position = QPointF(target)
            self._target = QPointF(target)
            self._has_position = True
            self._move_to_position()
            self.show()
            self.raise_()
            return

        self._target = target
        if not self._animations_enabled:
            self._timer.stop()
            self._position = QPointF(target)
            self._move_to_position()
            if not self.isVisible():
                self.show()
                self.raise_()
            return

        if not self.isVisible():
            self.show()
            self.raise_()
        if not self._timer.isActive():
            self._timer.start()

    def hide_spotlight(self) -> None:
        self._timer.stop()
        self._has_position = False
        self.hide()

    def _advance(self) -> None:
        dx = self._target.x() - self._position.x()
        dy = self._target.y() - self._position.y()
        if dx * dx + dy * dy < 1.0:
            self._position = QPointF(self._target)
            self._timer.stop()
        else:
            self._position.setX(self._position.x() + dx * 0.32)
            self._position.setY(self._position.y() + dy * 0.32)
        self._move_to_position()

    def _move_to_position(self) -> None:
        self.move(
            round(self._position.x() - self.RADIUS),
            round(self._position.y() - self.RADIUS),
        )
