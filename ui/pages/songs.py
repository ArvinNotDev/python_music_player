from __future__ import annotations

from typing import Any

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QPushButton, QWidget

from ..components import EmptyState, SearchBox, SectionHeader, TrackTable
from .base import ScrollPage


class SongsPage(ScrollPage):
    addFilesRequested = Signal()

    def __init__(self, tracks: list[Any] | None = None, metadata_service=None, parent=None):
        super().__init__(parent)
        top = QWidget()
        row = QHBoxLayout(top)
        row.setContentsMargins(0, 0, 0, 0)
        self.header = SectionHeader("Songs", "Your full music library")
        row.addWidget(self.header, 1)
        self.add_button = QPushButton("Add music")
        self.add_button.setProperty("primary", True)
        self.add_button.clicked.connect(self.addFilesRequested)
        row.addWidget(self.add_button)
        self.content.addWidget(top)
        self.search = SearchBox("Filter songs")
        self.content.addWidget(self.search)
        self.table = TrackTable(tracks or [], metadata_service)
        self.table.setMinimumHeight(360)
        self.content.addWidget(self.table, 1)
        self.empty = EmptyState("No songs yet", "Add music to your library to see your tracks here.")
        self.content.addWidget(self.empty)
        self.search.textChanged.connect(self.table.set_filter)
        self.set_tracks(tracks or [])

    def set_tracks(self, tracks: list[Any]) -> None:
        self.table.set_tracks(tracks)
        self.table.setVisible(bool(tracks))
        self.empty.setVisible(not tracks)
