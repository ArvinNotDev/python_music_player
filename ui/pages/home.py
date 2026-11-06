from __future__ import annotations

from typing import Any

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QLabel, QPushButton

from ..components import EmptyState, SectionHeader, TrackCardStrip
from .base import ScrollPage


class HomePage(ScrollPage):
    playRequested = Signal(object)
    navigateRequested = Signal(str)
    addFilesRequested = Signal()

    def __init__(self, metadata_service=None, parent=None):
        super().__init__(parent)
        hero = QLabel("Your music, in its own orbit.")
        hero.setStyleSheet("font-size: 30px; font-weight: 750; letter-spacing: -0.5px;")
        self.content.addWidget(hero)
        self.empty = EmptyState("Your library is ready for its first track", "Add a music folder or choose audio files to start building your collection.", "Add music")
        self.empty.action.clicked.connect(self.addFilesRequested)
        self.content.addWidget(self.empty)
        self._sections: dict[str, tuple[SectionHeader, TrackCardStrip]] = {}
        for key, title, action in (
            ("recent", "Recently played", "Show all"),
            ("added", "Recently added", "Browse songs"),
            ("favorites", "Favorites", "Open favorites"),
            ("library", "From your library", "Browse songs"),
        ):
            header = SectionHeader(title, action_text=action)
            strip = TrackCardStrip(metadata_service)
            header.action.clicked.connect(lambda _checked=False, k=key: self.navigateRequested.emit(k))
            self.content.addWidget(header)
            self.content.addWidget(strip)
            strip.trackActivated.connect(self.playRequested)
            self._sections[key] = (header, strip)
        self.set_data([], [], [])

    def set_loading(self, loading: bool) -> None:
        if loading:
            self.empty.title_label.setText("Loading your library…")
            self.empty.description_label.setText("Your music collection will appear here.")
            self.empty.action.hide()
        else:
            self.empty.title_label.setText("Your library is ready for its first track")
            self.empty.description_label.setText("Add a music folder or choose audio files to start building your collection.")
            self.empty.action.show()

    def set_data(self, recently_played: list[Any], recently_added: list[Any], favorites: list[Any], library_tracks: list[Any] | None = None) -> None:
        library_tracks = library_tracks or []
        values = {"recent": recently_played, "added": recently_added, "favorites": favorites, "library": []}
        if not any(values[key] for key in ("recent", "added", "favorites")):
            values["library"] = library_tracks
        self.empty.setVisible(not library_tracks)
        if library_tracks:
            self.set_loading(False)
        for key, tracks in values.items():
            _, strip = self._sections[key]
            strip.set_tracks(tracks[:12])
            strip.setVisible(bool(tracks))
