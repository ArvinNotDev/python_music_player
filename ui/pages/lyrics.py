from __future__ import annotations

import bisect
import time
from typing import Any

from PySide6.QtCore import QEasingCurve, Qt, QVariantAnimation, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QComboBox, QFrame, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QPushButton, QVBoxLayout, QWidget,
)

from core.metadata.lyrics_service import LyricsLookupResult, parse_lrc
from core.models import LyricsDocument, LyricsLine
from ..components import ArtworkLabel, EmptyState
from ..services import track_title, value
from .base import ScrollPage


class LyricsPage(ScrollPage):
    editRequested = Signal(object, object)
    autoScrollChanged = Signal(bool)
    retryRequested = Signal()
    candidateSelected = Signal(object)

    def __init__(self, auto_scroll: bool = True, metadata_service: Any = None, parent=None):
        super().__init__(parent)
        self.metadata_service = metadata_service
        self.title = QLabel("Lyrics")
        self.title.setStyleSheet("font-size: 27px; font-weight: 750;")
        self.track_label = QLabel("No track selected")
        self.track_label.setProperty("role", "secondary")
        self.artist_label = QLabel("")
        self.artist_label.setProperty("role", "secondary")

        self.header_card = QFrame()
        self.header_card.setObjectName("LyricsHeaderCard")
        header = QHBoxLayout(self.header_card)
        header.setContentsMargins(18, 16, 18, 16)
        header.setSpacing(16)
        self.artwork = ArtworkLabel(76, self.header_card)
        header.addWidget(self.artwork)
        identity = QVBoxLayout()
        identity.setSpacing(4)
        self.track_label.setWordWrap(True)
        self.artist_label.setWordWrap(True)
        identity.addWidget(self.track_label)
        identity.addWidget(self.artist_label)
        self.source_label = QLabel("Source not loaded")
        self.source_label.setProperty("role", "secondary")
        self.source_label.setOpenExternalLinks(True)
        identity.addWidget(self.source_label)
        header.addLayout(identity, 1)
        self.sync_label = QLabel("")
        self.sync_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.sync_label.setProperty("role", "secondary")
        header.addWidget(self.sync_label)

        self.toolbar = QWidget()
        row = QHBoxLayout(self.toolbar)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        self.format_selector = QComboBox()
        self.format_selector.addItem("Synchronized", "synced")
        self.format_selector.addItem("Plain text", "plain")
        self.format_selector.hide()
        self.format_selector.currentIndexChanged.connect(self._format_changed)
        self.scroll_button = QPushButton("Auto-scroll on" if auto_scroll else "Auto-scroll off")
        self.scroll_button.setCheckable(True)
        self.scroll_button.setChecked(auto_scroll)
        self.scroll_button.clicked.connect(self._toggle_scroll)
        self.retry_button = QPushButton("Refresh lyrics")
        self.retry_button.clicked.connect(self.retryRequested)
        self.edit_button = QPushButton("Edit lyrics")
        self.edit_button.clicked.connect(self._edit)
        row.addWidget(self.format_selector)
        row.addStretch(1)
        row.addWidget(self.scroll_button)
        row.addWidget(self.retry_button)
        row.addWidget(self.edit_button)

        self.state_card = QFrame()
        self.state_card.setObjectName("LyricsStateCard")
        state_layout = QVBoxLayout(self.state_card)
        state_layout.setContentsMargins(22, 22, 22, 22)
        state_layout.setSpacing(8)
        self.state_title = QLabel("Lyrics aren't available")
        self.state_title.setStyleSheet("font-size: 18px; font-weight: 700;")
        self.state_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.state_message = QLabel("Add lyrics or search online for this track.")
        self.state_message.setProperty("role", "secondary")
        self.state_message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.state_message.setWordWrap(True)
        self.state_progress = QFrame()
        self.state_progress.setFixedHeight(3)
        self.state_progress.setObjectName("LyricsLoadingIndicator")
        self.candidate_selector = QComboBox()
        self.candidate_selector.setMinimumWidth(280)
        self.candidate_selector.hide()
        self.use_candidate_button = QPushButton("Use selected version")
        self.use_candidate_button.hide()
        self.use_candidate_button.clicked.connect(self._choose_candidate)
        state_layout.addWidget(self.state_title)
        state_layout.addWidget(self.state_message)
        state_layout.addWidget(self.state_progress)
        state_layout.addWidget(self.candidate_selector, alignment=Qt.AlignmentFlag.AlignCenter)
        state_layout.addWidget(self.use_candidate_button, alignment=Qt.AlignmentFlag.AlignCenter)

        self.empty = EmptyState(
            "Lyrics aren't available",
            "Add plain lyrics or timestamped LRC for this track.",
            "Add lyrics",
        )
        self.empty.action.clicked.connect(self._edit)
        self.content.addWidget(self.title)
        self.content.addWidget(self.header_card)
        self.content.addWidget(self.toolbar)
        self.content.addWidget(self.state_card)
        self.content.addWidget(self.empty)
        self.list = QListWidget()
        self.list.setFrameShape(QListWidget.Shape.NoFrame)
        self.list.setSpacing(7)
        self.list.setWordWrap(True)
        self.list.setUniformItemSizes(False)
        self.list.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list.setStyleSheet(
            "QListWidget { background: transparent; border: none; }"
            "QListWidget::item { padding: 10px 16px; border-radius: 10px; }"
        )
        self.list.verticalScrollBar().valueChanged.connect(self._manual_scroll)
        self.content.addWidget(self.list)

        self.track: Any = None
        self.raw_lyrics: Any = None
        self.document: LyricsDocument | None = None
        self._result: LyricsLookupResult | None = None
        self.lines: list[tuple[int | None, str]] = []
        self._timed_rows: list[tuple[int, int]] = []
        self._timed_stamps: list[int] = []
        self.active_line = -1
        self.auto_scroll = auto_scroll
        self.large_text = False
        self._manual_until = 0.0
        self._programmatic_scroll = False
        self._secondary_color = "#AAB2C0"
        self._muted_color = "#778294"
        self._accent_color = "#8B7CFF"
        self._animations_enabled = True
        self._row_animations: dict[int, QVariantAnimation] = {}
        self._current_mode = "synced"
        self.set_empty_state("No track selected", "Play a song, then open Lyrics to view or retrieve its lyrics.")
        self.retry_button.setEnabled(False)
        self.edit_button.setEnabled(False)

    def _set_source(self, source: str, url: str = "") -> None:
        if source and url:
            from html import escape
            self.source_label.setText(f'<a href="{escape(url, quote=True)}">Source · {escape(source)} ↗</a>')
        elif source:
            self.source_label.setText(f"Source · {source}")
        else:
            self.source_label.setText("Source unavailable")

    def _set_track_header(self, track: Any) -> None:
        self.track = track
        self.track_label.setText(track_title(track) if track else "No track selected")
        artist = (
            str(value(track, "artist", default="") or value(track, "album_artist", default="") or "")
            if track else ""
        )
        album = str(value(track, "album", default="") or "") if track else ""
        details = " · ".join(part for part in (artist, album) if part)
        self.artist_label.setText(details)
        self.artwork.set_track(track, self.metadata_service)
        self.edit_button.setEnabled(bool(track))
        self.retry_button.setEnabled(bool(track))

    def set_loading(self, track: Any, provider: str = "LRCLIB") -> None:
        self._set_track_header(track)
        self._stop_row_animations()
        self._result = None
        self.raw_lyrics = None
        self.document = None
        self.lines = []
        self._timed_rows = []
        self._timed_stamps = []
        self.active_line = -1
        self.list.clear()
        self.source_label.setText("Checking local files…" if provider == "local" else "Checking local files first…")
        self.sync_label.setText("")
        self.state_title.setText("Loading lyrics…")
        self.state_message.setText(
            "RW Player checks local sidecar and embedded lyrics first. "
            + ("An online search follows when no local lyrics exist." if provider != "local"
               else "Online lookup is disabled; your local files remain available.")
        )
        self.state_progress.show()
        self.candidate_selector.hide()
        self.use_candidate_button.hide()
        self.state_card.show()
        self.empty.hide()
        self.list.hide()
        self.format_selector.hide()

    def set_empty_state(self, title: str, message: str) -> None:
        self._stop_row_animations()
        self._result = None
        self.state_title.setText(title)
        self.state_message.setText(message)
        self.source_label.setText("No lyrics loaded")
        self.sync_label.setText("")
        self.state_progress.hide()
        self.candidate_selector.hide()
        self.use_candidate_button.hide()
        self.state_card.show()
        self.empty.hide()
        self.list.hide()
        self.format_selector.hide()
        self.raw_lyrics = None
        self.document = None
        self.lines = []
        self._timed_rows = []
        self._timed_stamps = []
        self.active_line = -1

    def set_lookup_result(self, track: Any, result: LyricsLookupResult) -> None:
        self._set_track_header(track)
        self._stop_row_animations()
        self._result = result
        self.state_progress.hide()
        self.candidate_selector.hide()
        self.use_candidate_button.hide()
        self.format_selector.hide()
        status = result.status

        if status == "ambiguous":
            self.lines = []
            self._timed_rows = []
            self._timed_stamps = []
            self.active_line = -1
            self.list.clear()
            self.raw_lyrics = None
            self.document = None
            self.source_label.setText('<a href="https://lrclib.net">Source · LRCLIB ↗</a>')
            self.sync_label.setText("Choose a recording")
            self.state_title.setText("Choose the matching recording")
            self.state_message.setText(result.message or "More than one version matches this track.")
            self.candidate_selector.clear()
            for candidate in result.candidates:
                parts = [candidate.track_name, candidate.artist_name]
                if candidate.album_name:
                    parts.append(candidate.album_name)
                if candidate.duration:
                    parts.append(f"{int(round(candidate.duration))} sec")
                parts.append("Synced" if candidate.has_synced_lyrics else "Plain" if candidate.has_plain_lyrics else "Instrumental")
                self.candidate_selector.addItem(" · ".join(parts), candidate)
            self.candidate_selector.show()
            self.use_candidate_button.setEnabled(bool(result.candidates))
            self.use_candidate_button.show()
            self.state_card.show()
            self.empty.hide()
            self.list.hide()
            return

        if status == "instrumental":
            self.lines = []
            self._timed_rows = []
            self._timed_stamps = []
            self.active_line = -1
            self.list.clear()
            self._set_source(result.source, result.attribution_url)
            self.sync_label.setText("Instrumental")
            self.state_title.setText("Instrumental track")
            self.state_message.setText("This recording is marked as instrumental. There are no lyrics to display.")
            self.state_card.show()
            self.empty.hide()
            self.list.hide()
            self.raw_lyrics = None
            self.document = None
            return

        if status == "found" and result.document is not None:
            self._set_source(result.source or "Local", result.attribution_url)
            self.sync_label.setText("Time-synchronized" if result.is_synchronized else "Plain lyrics")
            self.state_card.hide()
            self.empty.hide()
            has_both = result.plain_document is not None and result.synced_document is not None
            if has_both:
                self.format_selector.blockSignals(True)
                self.format_selector.setCurrentIndex(0)
                self.format_selector.blockSignals(False)
                self.format_selector.show()
                self._current_mode = "synced"
                selected = result.synced_document
            elif result.synced_document is not None:
                selected = result.synced_document
                self._current_mode = "synced"
            else:
                selected = result.plain_document or result.document
                self._current_mode = "plain"
            self.set_track_lyrics(track, selected)
            return

        messages = {
            "online_disabled": ("Online search is disabled", result.message or "Enable automatic online lyrics in Settings, or retry manually."),
            "not_found": ("No lyrics found", result.message or "No matching lyrics were found for this recording."),
            "missing_metadata": ("Track information is incomplete", result.message or "A title and artist are required to search online."),
            "network_error": ("Lyrics service unavailable", result.message or "Check your internet connection and try again."),
            "rate_limited": ("Please wait before retrying", result.message or "The lyrics provider temporarily limited requests."),
            "error": ("Couldn't load lyrics", result.message or "The provider returned an invalid or unusable response."),
        }
        heading, message = messages.get(status, ("Lyrics unavailable", result.message or "Lyrics could not be loaded."))
        if status == "rate_limited" and result.retry_after is not None:
            message = f"{message} You can retry in about {result.retry_after} seconds."
        self._set_source(result.source, result.attribution_url)
        self.sync_label.setText("")
        self.state_title.setText(heading)
        self.state_message.setText(message)
        self.state_card.show()
        self.empty.hide()
        self.list.hide()
        self.raw_lyrics = None
        self.document = None
        self.lines = []
        self._timed_rows = []
        self._timed_stamps = []
        self.active_line = -1

    def set_track_lyrics(self, track: Any, lyrics: Any) -> None:
        """Compatibility entry point used by existing UI tests and integrations."""
        self._set_track_header(track)
        self.raw_lyrics = lyrics
        if isinstance(lyrics, LyricsDocument):
            document = lyrics
        elif isinstance(lyrics, str):
            document = parse_lrc(lyrics) if "[" in lyrics and ":" in lyrics else LyricsDocument(
                [LyricsLine(line) for line in lyrics.splitlines()], "plain"
            )
        else:
            raw = value(lyrics, "text", "lyrics", "content", default="")
            document = parse_lrc(str(raw)) if isinstance(raw, str) and "[" in raw and ":" in raw else LyricsDocument(
                [LyricsLine(line) for line in str(raw or "").splitlines()], "plain"
            )
        self.document = document
        self._stop_row_animations()
        self.lines = [(line.timestamp_ms, line.text) for line in document.lines]
        timed = sorted(
            ((stamp, index) for index, (stamp, _text) in enumerate(self.lines) if stamp is not None),
            key=lambda item: item[0],
        )
        self._timed_rows = timed
        self._timed_stamps = [stamp for stamp, _row in timed]
        self.active_line = -1
        self.list.clear()
        for _stamp, text in self.lines:
            item = QListWidgetItem(text)
            item.setTextAlignment(Qt.AlignmentFlag.AlignHCenter)
            font = QFont()
            font.setPointSize(16 if self.large_text else 15)
            item.setFont(font)
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            self.list.addItem(item)
            self._style_row(self.list.count() - 1, False)
        has_lines = bool(self.lines) and bool(document.text.strip())
        # The state card owns all no-lyrics messaging; keep the legacy EmptyState
        # hidden so the two empty-state surfaces never overlap.
        self.empty.hide()
        self.list.setVisible(has_lines)
        self.state_card.setVisible(not has_lines)
        if not has_lines and self._result is None:
            self.state_title.setText("Lyrics aren't available")
            self.state_message.setText("Add plain lyrics or timestamped LRC for this track.")
        if has_lines:
            self.state_card.hide()
        self.edit_button.setEnabled(bool(track))
        self.retry_button.setEnabled(bool(track))

    def _format_changed(self, _index: int) -> None:
        if not self._result:
            return
        selected = self.format_selector.currentData()
        document = self._result.synced_document if selected == "synced" else self._result.plain_document
        if document is None:
            return
        self._current_mode = selected
        self.sync_label.setText("Time-synchronized" if selected == "synced" else "Plain lyrics")
        self.set_track_lyrics(self.track, document)

    def set_position(self, seconds: float) -> None:
        if not self._timed_stamps:
            return
        target = int(max(0.0, float(seconds)) * 1000)
        location = bisect.bisect_right(self._timed_stamps, target) - 1
        current = self._timed_rows[location][1] if location >= 0 else -1
        if current == self.active_line:
            return
        previous = self.active_line
        self.active_line = current
        if 0 <= previous < self.list.count():
            self._style_row(previous, False)
        if current >= 0:
            self._style_row(current, True)
            if self.auto_scroll and time.monotonic() >= self._manual_until:
                self._programmatic_scroll = True
                self.list.scrollToItem(self.list.item(current), QListWidget.ScrollHint.PositionAtCenter)
                self._programmatic_scroll = False

    def _style_row(self, row: int, active: bool) -> None:
        item = self.list.item(row)
        if item is None:
            return
        animation = self._row_animations.pop(row, None)
        if animation is not None:
            animation.stop()
            animation.deleteLater()

        start_text = item.foreground().color()
        target_text = QColor(self._accent_color if active else self._secondary_color)
        start_background = item.background().color()
        if not start_background.isValid():
            start_background = QColor(self._accent_color)
            start_background.setAlpha(0)
        target_background = QColor(self._accent_color)
        target_background.setAlpha(38 if active else 0)

        if self._animations_enabled and self.isVisible() and start_text.isValid():
            animation = QVariantAnimation(self)
            animation.setDuration(135)
            animation.setStartValue(0.0)
            animation.setEndValue(1.0)
            animation.setEasingCurve(QEasingCurve.Type.OutCubic)

            def interpolate(start: QColor, end: QColor, amount: float) -> QColor:
                return QColor(
                    round(start.red() + (end.red() - start.red()) * amount),
                    round(start.green() + (end.green() - start.green()) * amount),
                    round(start.blue() + (end.blue() - start.blue()) * amount),
                    round(start.alpha() + (end.alpha() - start.alpha()) * amount),
                )

            animation.valueChanged.connect(
                lambda amount, target=item, fg_start=QColor(start_text),
                fg_end=QColor(target_text), bg_start=QColor(start_background),
                bg_end=QColor(target_background):
                    (
                        target.setForeground(interpolate(fg_start, fg_end, float(amount))),
                        target.setBackground(interpolate(bg_start, bg_end, float(amount))),
                    )
            )
            animation.finished.connect(
                lambda current=animation, index=row: self._finish_row_animation(index, current)
            )
            self._row_animations[row] = animation
            animation.start()
        else:
            item.setForeground(target_text)
            item.setBackground(target_background)

        font = item.font()
        font.setBold(active)
        font.setPointSize((18 if active else 16) if self.large_text else (17 if active else 15))
        item.setFont(font)

    def _finish_row_animation(self, row: int, animation: QVariantAnimation) -> None:
        if self._row_animations.get(row) is animation:
            self._row_animations.pop(row, None)
        animation.deleteLater()

    def _stop_row_animations(self) -> None:
        for animation in self._row_animations.values():
            animation.stop()
            animation.deleteLater()
        self._row_animations.clear()

    def set_animations_enabled(self, enabled: bool) -> None:
        self._animations_enabled = bool(enabled)
        if not self._animations_enabled:
            self._stop_row_animations()
        for row in range(self.list.count()):
            self._style_row(row, row == self.active_line)

    def set_theme_colors(self, secondary: str, muted: str, accent: str) -> None:
        self._secondary_color = secondary
        self._muted_color = muted
        self._accent_color = accent
        for row in range(self.list.count()):
            self._style_row(row, row == self.active_line)

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
            font.setPointSize(
                18 if enabled and row == self.active_line else
                16 if enabled else 17 if row == self.active_line else 15
            )
            item.setFont(font)

    def _choose_candidate(self) -> None:
        candidate = self.candidate_selector.currentData()
        if candidate is not None:
            self.candidateSelected.emit(candidate)

    def _edit(self) -> None:
        if self.track:
            initial = self.document if isinstance(self.document, LyricsDocument) else self.raw_lyrics
            if isinstance(initial, LyricsDocument):
                initial = initial.to_lrc() if initial.format == "lrc" else initial.to_plain_text()
            self.editRequested.emit(self.track, initial)
