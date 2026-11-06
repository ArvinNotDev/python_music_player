from __future__ import annotations

import re
import time
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import QLabel, QListWidget, QListWidgetItem, QPushButton, QHBoxLayout, QWidget

from ..components import EmptyState
from ..services import track_title, value
from .base import ScrollPage


_TIMESTAMP = re.compile(r"\[(\d{1,2}):(\d{2})(?:[.:](\d{1,3}))?\]")


class LyricsPage(ScrollPage):
    editRequested = Signal(object, object)
    autoScrollChanged = Signal(bool)

    def __init__(self, auto_scroll: bool = True, parent=None):
        super().__init__(parent)
        self.title = QLabel("Lyrics")
        self.title.setStyleSheet("font-size: 27px; font-weight: 750;")
        self.track_label = QLabel("No track selected")
        self.track_label.setProperty("role", "secondary")
        toolbar = QWidget()
        row = QHBoxLayout(toolbar)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(self.track_label, 1)
        self.scroll_button = QPushButton("Auto-scroll on" if auto_scroll else "Auto-scroll off")
        self.scroll_button.setCheckable(True)
        self.scroll_button.setChecked(auto_scroll)
        self.scroll_button.clicked.connect(self._toggle_scroll)
        self.edit_button = QPushButton("Edit lyrics")
        self.edit_button.clicked.connect(self._edit)
        row.addWidget(self.scroll_button)
        row.addWidget(self.edit_button)
        self.content.addWidget(self.title)
        self.content.addWidget(toolbar)
        self.empty = EmptyState("Lyrics aren't available", "Add plain lyrics or timestamped LRC for this track.", "Add lyrics")
        self.empty.action.clicked.connect(self._edit)
        self.content.addWidget(self.empty)
        self.list = QListWidget()
        self.list.setFrameShape(QListWidget.Shape.NoFrame)
        self.list.setSpacing(7)
        self.list.setStyleSheet("QListWidget { background: transparent; } QListWidget::item { padding: 7px 10px; border-radius: 8px; }")
        self.list.verticalScrollBar().valueChanged.connect(self._manual_scroll)
        self.content.addWidget(self.list)
        self.track: Any = None
        self.raw_lyrics: Any = None
        self.lines: list[tuple[float | None, str]] = []
        self.active_line = -1
        self.auto_scroll = auto_scroll
        self.large_text = False
        self._manual_until = 0.0
        self._programmatic_scroll = False

    def set_track_lyrics(self, track: Any, lyrics: Any) -> None:
        self.track, self.raw_lyrics = track, lyrics
        self.track_label.setText(track_title(track) if track else "No track selected")
        self.list.clear()
        self.lines = self._parse(lyrics)
        self.active_line = -1
        self.empty.setVisible(not self.lines)
        self.list.setVisible(bool(self.lines))
        for _, text in self.lines:
            item = QListWidgetItem(text)
            item.setTextAlignment(Qt.AlignmentFlag.AlignHCenter)
            font = QFont()
            font.setPointSize(16 if self.large_text else 15)
            item.setFont(font)
            self.list.addItem(item)

    @staticmethod
    def _parse(lyrics: Any) -> list[tuple[float | None, str]]:
        raw = lyrics if isinstance(lyrics, str) else value(lyrics, "text", "lyrics", "content", default="")
        result: list[tuple[float | None, str]] = []
        for line in str(raw or "").splitlines():
            stamps = list(_TIMESTAMP.finditer(line))
            text = _TIMESTAMP.sub("", line).strip()
            if stamps:
                for stamp in stamps:
                    minute, second, fraction = stamp.groups()
                    centis = int((fraction or "0").ljust(2, "0")[:2])
                    result.append((int(minute) * 60 + int(second) + centis / 100, text))
            elif text and not (text.startswith("[") and ":" in text):
                result.append((None, text))
        result.sort(key=lambda item: item[0] if item[0] is not None else -1)
        return result

    def set_position(self, seconds: float) -> None:
        timed = [(i, stamp) for i, (stamp, _) in enumerate(self.lines) if stamp is not None]
        current = -1
        for index, stamp in timed:
            if stamp <= seconds:
                current = index
            else:
                break
        if current == self.active_line:
            return
        if 0 <= self.active_line < self.list.count():
            self._style_row(self.active_line, False)
        self.active_line = current
        if current >= 0:
            self._style_row(current, True)
            if self.auto_scroll and time.monotonic() >= self._manual_until:
                self._programmatic_scroll = True
                self.list.scrollToItem(self.list.item(current), QListWidget.ScrollHint.PositionAtCenter)
                self._programmatic_scroll = False

    def _style_row(self, row: int, active: bool) -> None:
        item = self.list.item(row)
        if item:
            item.setForeground(QColor("#A095FF" if active else ("#F4F5F8" if row >= self.active_line else "#777D8B")))
            font = item.font()
            font.setBold(active)
            font.setPointSize((18 if active else 16) if self.large_text else (17 if active else 15))
            item.setFont(font)

    def _manual_scroll(self, _value: int) -> None:
        if not self._programmatic_scroll:
            self._manual_until = time.monotonic() + 5.0

    def _toggle_scroll(self, enabled: bool) -> None:
        self.auto_scroll = enabled
        self.scroll_button.setText("Auto-scroll on" if enabled else "Auto-scroll off")
        self.autoScrollChanged.emit(enabled)

    def set_large_text(self, enabled: bool) -> None:
        self.large_text = enabled
        for row in range(self.list.count()):
            item = self.list.item(row)
            font = item.font()
            font.setPointSize(18 if enabled and row == self.active_line else 16 if enabled else 17 if row == self.active_line else 15)
            item.setFont(font)

    def _edit(self) -> None:
        if self.track:
            self.editRequested.emit(self.track, self.raw_lyrics)
