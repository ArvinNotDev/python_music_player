"""Low-cost snapshot transitions for the main page stack."""

from __future__ import annotations

from PySide6.QtCore import (
    QEasingCurve, QParallelAnimationGroup, QPoint, QPropertyAnimation, Qt,
)
from PySide6.QtWidgets import QGraphicsOpacityEffect, QLabel, QStackedWidget


class AnimatedStackedWidget(QStackedWidget):
    """Animate page changes without applying effects to live page contents."""

    TRANSITION_MS = 190
    SLIDE_DISTANCE = 14

    def __init__(self, parent=None):
        super().__init__(parent)
        self._animations_enabled = True
        self._active_transition = None

    def set_animations_enabled(self, enabled: bool) -> None:
        self._animations_enabled = bool(enabled)
        if not self._animations_enabled:
            self._finish_transition()

    def setCurrentWidget(self, widget) -> None:
        index = self.indexOf(widget)
        if index >= 0:
            self.setCurrentIndex(index)

    def setCurrentIndex(self, index: int) -> None:
        if index == self.currentIndex() or not 0 <= index < self.count():
            return
        self._finish_transition()
        old_index = self.currentIndex()
        old_page = self.currentWidget()
        can_animate = self._animations_enabled and self.isVisible() and old_page is not None
        snapshot = None
        old_geometry = None
        if can_animate:
            try:
                old_geometry = old_page.geometry()
                snapshot = old_page.grab()
            except RuntimeError:
                snapshot = None

        super().setCurrentIndex(index)
        new_page = self.currentWidget()
        if not can_animate or new_page is None or new_page is old_page or snapshot is None or snapshot.isNull():
            return

        target_pos = new_page.pos()
        direction = 1 if index > old_index else -1
        overlay = QLabel(self)
        overlay.setObjectName("PageTransitionSnapshot")
        overlay.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        overlay.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        overlay.setStyleSheet(
            "QLabel#PageTransitionSnapshot { background: transparent; border: none; padding: 0; }"
        )
        overlay.setPixmap(snapshot)
        overlay.setGeometry(old_geometry or self.rect())
        opacity = QGraphicsOpacityEffect(overlay)
        opacity.setOpacity(1.0)
        overlay.setGraphicsEffect(opacity)

        new_page.move(target_pos + QPoint(direction * self.SLIDE_DISTANCE, 0))
        new_page.show()
        overlay.show()
        overlay.raise_()

        group = QParallelAnimationGroup(self)
        fade = QPropertyAnimation(opacity, b"opacity", group)
        fade.setDuration(self.TRANSITION_MS)
        fade.setStartValue(1.0)
        fade.setEndValue(0.0)
        fade.setEasingCurve(QEasingCurve.Type.OutCubic)

        outgoing = QPropertyAnimation(overlay, b"pos", group)
        outgoing.setDuration(self.TRANSITION_MS)
        outgoing.setStartValue(overlay.pos())
        outgoing.setEndValue(overlay.pos() - QPoint(direction * self.SLIDE_DISTANCE, 0))
        outgoing.setEasingCurve(QEasingCurve.Type.OutCubic)

        incoming = QPropertyAnimation(new_page, b"pos", group)
        incoming.setDuration(self.TRANSITION_MS)
        incoming.setStartValue(new_page.pos())
        incoming.setEndValue(target_pos)
        incoming.setEasingCurve(QEasingCurve.Type.OutCubic)

        transition = {"group": group, "overlay": overlay, "page": new_page, "target_pos": target_pos}
        self._active_transition = transition
        group.finished.connect(lambda current=transition: self._complete_transition(current))
        group.start()

    def resizeEvent(self, event) -> None:
        self._finish_transition()
        super().resizeEvent(event)

    def _complete_transition(self, transition) -> None:
        if self._active_transition is not transition:
            return
        self._active_transition = None
        page = transition["page"]
        if self.indexOf(page) >= 0:
            page.move(transition["target_pos"])
        overlay = transition["overlay"]
        overlay.setGraphicsEffect(None)
        overlay.hide()
        overlay.deleteLater()
        transition["group"].deleteLater()

    def _finish_transition(self) -> None:
        transition = self._active_transition
        if transition is None:
            return
        self._active_transition = None
        group = transition["group"]
        group.stop()
        page = transition["page"]
        if self.indexOf(page) >= 0:
            page.move(transition["target_pos"])
        overlay = transition["overlay"]
        overlay.setGraphicsEffect(None)
        overlay.hide()
        overlay.deleteLater()
        group.deleteLater()
