"""Fast, keyboard-first command launcher for Sonora."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import (
    QEasingCurve, QParallelAnimationGroup, QPropertyAnimation, QSize, Qt, Signal,
)
from PySide6.QtWidgets import (
    QDialog, QFrame, QGraphicsOpacityEffect, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QVBoxLayout, QWidget,
)


class CommandPalette(QDialog):
    """A searchable, keyboard-friendly launcher for pages and playback actions."""

    commandActivated = Signal(str)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("CommandPalette")
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.setModal(True)
        self.setFixedWidth(620)
        self._opacity_effect = QGraphicsOpacityEffect(self)
        self._opacity_effect.setOpacity(1.0)
        self.setGraphicsEffect(self._opacity_effect)
        self._show_animation: QParallelAnimationGroup | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        panel = QFrame(self)
        panel.setObjectName("CommandPaletteSurface")
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(18, 18, 18, 14)
        panel_layout.setSpacing(12)

        heading_row = QHBoxLayout()
        heading = QLabel("Quick actions")
        heading.setObjectName("CommandPaletteHeading")
        hint = QLabel("CTRL  K")
        hint.setObjectName("CommandPaletteHint")
        heading_row.addWidget(heading)
        heading_row.addStretch(1)
        heading_row.addWidget(hint)
        panel_layout.addLayout(heading_row)

        self.search = QLineEdit(panel)
        self.search.setObjectName("CommandPaletteInput")
        self.search.setPlaceholderText("Search pages, playback, and actions…")
        self.search.setClearButtonEnabled(True)
        panel_layout.addWidget(self.search)

        self.list_widget = QListWidget(panel)
        self.list_widget.setObjectName("CommandPaletteList")
        self.list_widget.setMinimumHeight(96)
        self.list_widget.setMaximumHeight(360)
        self.list_widget.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list_widget.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        panel_layout.addWidget(self.list_widget)

        footer = QHBoxLayout()
        self.empty_label = QLabel("No matching actions")
        self.empty_label.setObjectName("CommandPaletteEmpty")
        footer.addWidget(self.empty_label)
        footer.addStretch(1)
        footer.addWidget(QLabel("↑ ↓  Navigate"))
        footer.addWidget(QLabel("↵  Run"))
        footer.addWidget(QLabel("Esc  Close"))
        panel_layout.addLayout(footer)
        root.addWidget(panel)

        self._commands: list[dict[str, Any]] = []
        self.search.textChanged.connect(self._filter_commands)
        self.search.returnPressed.connect(self._activate_current)
        self.list_widget.itemActivated.connect(self._activate_item)
        self.list_widget.itemClicked.connect(self._activate_item)

    def set_commands(self, commands: list[dict[str, Any]]) -> None:
        self._commands = [dict(command) for command in commands]
        self._filter_commands(self.search.text())

    def show_palette(self, commands: list[dict[str, Any]]) -> None:
        self.set_commands(commands)
        self.search.clear()
        self._filter_commands("")
        if self.list_widget.count():
            self.list_widget.setCurrentRow(0)
        self.adjustSize()
        parent = self.parentWidget()
        if parent is not None:
            center = parent.mapToGlobal(parent.rect().center())
            target = self.geometry()
            target.moveTo(
                center.x() - self.width() // 2,
                max(18, center.y() - self.height() // 2 - 80),
            )
            self.setGeometry(target.translated(0, -12))
        else:
            target = self.geometry()
        if self._show_animation is not None:
            self._show_animation.stop()
            self._show_animation.deleteLater()
        self._opacity_effect.setOpacity(0.0)
        self.show()
        self.raise_()
        self.activateWindow()
        group = QParallelAnimationGroup(self)
        fade = QPropertyAnimation(self._opacity_effect, b"opacity", group)
        fade.setDuration(150)
        fade.setStartValue(0.0)
        fade.setEndValue(1.0)
        fade.setEasingCurve(QEasingCurve.Type.OutCubic)
        slide = QPropertyAnimation(self, b"geometry", group)
        slide.setDuration(180)
        slide.setStartValue(self.geometry())
        slide.setEndValue(target)
        slide.setEasingCurve(QEasingCurve.Type.OutCubic)
        group.finished.connect(lambda current=group: self._finish_show_animation(current))
        self._show_animation = group
        group.start()
        self.search.setFocus()

    def _finish_show_animation(self, animation: QParallelAnimationGroup) -> None:
        if self._show_animation is animation:
            self._show_animation = None
        animation.deleteLater()

    def _filter_commands(self, query: str) -> None:
        normalized = query.strip().casefold()
        self.list_widget.clear()
        for command in self._commands:
            title = str(command.get("title", ""))
            description = str(command.get("description", ""))
            shortcut = str(command.get("shortcut", ""))
            haystack = f"{title} {description} {shortcut}".casefold()
            if normalized and normalized not in haystack:
                continue
            item = QListWidgetItem(title)
            item.setData(Qt.ItemDataRole.UserRole, str(command.get("id", "")))
            item.setToolTip(
                f"{description}\nShortcut: {shortcut}" if shortcut else description
            )
            item.setSizeHint(QSize(0, 44))
            self.list_widget.addItem(item)
        has_results = self.list_widget.count() > 0
        self.empty_label.setVisible(not has_results)
        self.list_widget.setVisible(has_results)
        if has_results:
            self.list_widget.setCurrentRow(0)

    def _activate_current(self) -> None:
        item = self.list_widget.currentItem()
        if item is None and self.list_widget.count():
            item = self.list_widget.item(0)
        if item is not None:
            self._activate_item(item)

    def _activate_item(self, item: QListWidgetItem) -> None:
        command_id = str(item.data(Qt.ItemDataRole.UserRole) or "")
        if not command_id:
            return
        self.hide()
        self.commandActivated.emit(command_id)

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.reject()
            return
        if event.key() in (Qt.Key.Key_Down, Qt.Key.Key_Up):
            self.list_widget.setFocus()
            if self.list_widget.count() and self.list_widget.currentRow() < 0:
                self.list_widget.setCurrentRow(0)
            return
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._activate_current()
            return
        super().keyPressEvent(event)
