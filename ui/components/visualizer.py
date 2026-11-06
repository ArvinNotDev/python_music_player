"""Lightweight animated playback activity indicator (not a spectrum analyzer)."""

from __future__ import annotations

import math

from PySide6.QtCore import QTimer, Qt, QRectF
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QWidget


class PlaybackVisualizer(QWidget):
    """A small, low-cost motion cue that animates only while playback is active."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("PlaybackVisualizer")
        self.setToolTip("Animated playback activity")
        self.setFixedSize(38, 20)
        self._color = QColor("#8B7CFF")
        self._phase = 0.0
        self._playing = False
        self._animations_enabled = True
        self._timer = QTimer(self)
        self._timer.setInterval(48)
        self._timer.timeout.connect(self._advance)

    def set_color(self, color: str) -> None:
        candidate = QColor(color)
        if candidate.isValid():
            self._color = candidate
            self.update()

    def set_animations_enabled(self, enabled: bool) -> None:
        self._animations_enabled = bool(enabled)
        self._sync_timer()
        self.update()

    def set_playing(self, playing: bool) -> None:
        self._playing = bool(playing)
        self._sync_timer()
        self.update()

    def _sync_timer(self) -> None:
        should_animate = self._playing and self._animations_enabled and self.isVisible()
        if should_animate and not self._timer.isActive():
            self._timer.start()
        elif not should_animate and self._timer.isActive():
            self._timer.stop()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._sync_timer()

    def hideEvent(self, event) -> None:
        self._timer.stop()
        super().hideEvent(event)

    def _advance(self) -> None:
        self._phase += 0.24
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        width = self.width()
        height = self.height()
        count = 5
        gap = 3.0
        bar_width = (width - gap * (count - 1)) / count
        base = QColor(self._color)
        for index in range(count):
            if self._playing and self._animations_enabled:
                wave = (math.sin(self._phase + index * 0.86) + 1.0) / 2.0
                ratio = 0.24 + 0.70 * wave
                alpha = 170 + int(85 * wave)
            else:
                ratio = 0.18
                alpha = 105
            color = QColor(base)
            color.setAlpha(alpha)
            painter.setBrush(color)
            painter.setPen(Qt.PenStyle.NoPen)
            bar_height = max(3.0, height * ratio)
            x = index * (bar_width + gap)
            y = (height - bar_height) / 2.0
            painter.drawRoundedRect(QRectF(x, y, bar_width, bar_height), 2.0, 2.0)
