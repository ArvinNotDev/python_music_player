from __future__ import annotations

from typing import Any

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QLabel

from ..components import EmptyState, ResponsiveCardGrid, SearchBox, SectionHeader, TrackTable
from ..services import value
from .base import ScrollPage


class EntityGridPage(ScrollPage):
    itemActivated = Signal(object)

    def __init__(self, kind: str, metadata_service=None, parent=None):
        super().__init__(parent)
        self.kind = kind
        title = "Albums" if kind == "album" else "Artists"
        self.content.addWidget(SectionHeader(title, f"Browse your {kind} collection"))
        self.search = SearchBox(f"Search {title.lower()}")
        self.content.addWidget(self.search)
        self.grid = ResponsiveCardGrid(kind, metadata_service)
        self.grid.itemClicked.connect(self.itemActivated)
        self.content.addWidget(self.grid)
        self.empty = EmptyState(f"No {title.lower()} yet", "Add music to your library and this collection will appear here.")
        self.content.addWidget(self.empty)
        self._items: list[Any] = []
        self.search.textChanged.connect(self._filter)

    def set_items(self, items: list[Any]) -> None:
        self._items = list(items)
        self._filter(self.search.input.text())

    def _filter(self, query: str) -> None:
        q = query.casefold().strip()
        if not q:
            matches = self._items
        else:
            matches = [item for item in self._items if q in " ".join(str(value(item, k, default="")) for k in ("title", "name", "artist", "album", "genre")).casefold()]
        self.grid.set_items(matches)
        self.empty.setVisible(not self._items)
        self.grid.setVisible(bool(matches))


class CollectionDetailPage(ScrollPage):
    backRequested = Signal()
    playAllRequested = Signal()
    shuffleRequested = Signal()
    relatedAlbumActivated = Signal(object)

    def __init__(self, metadata_service=None, parent=None):
        super().__init__(parent)
        from PySide6.QtWidgets import QHBoxLayout, QPushButton, QVBoxLayout, QWidget
        from ..components import ArtworkLabel

        self.toolbar = QWidget()
        toolbar_layout = QHBoxLayout(self.toolbar)
        toolbar_layout.setContentsMargins(0, 0, 0, 0)
        self.back_button = QPushButton("‹  Back")
        self.back_button.clicked.connect(self.backRequested)
        toolbar_layout.addWidget(self.back_button)
        toolbar_layout.addStretch(1)
        self.content.addWidget(self.toolbar)
        hero = QWidget()
        hero_layout = QHBoxLayout(hero)
        hero_layout.setContentsMargins(0, 0, 0, 0)
        self.art = ArtworkLabel(216)
        self.art.setStyleSheet("background: #242630; border-radius: 14px; color: #A095FF; font-size: 48px;")
        hero_layout.addWidget(self.art)
        info = QVBoxLayout()
        info.setAlignment(__import__("PySide6.QtCore", fromlist=["Qt"]).Qt.AlignmentFlag.AlignVCenter)
        self.kind_label = QLabel("ALBUM")
        self.kind_label.setProperty("role", "muted")
        self.title = QLabel("Collection")
        self.title.setWordWrap(True)
        self.title.setStyleSheet("font-size: 30px; font-weight: 750;")
        self.subtitle = QLabel("")
        self.subtitle.setProperty("role", "secondary")
        self.subtitle.setWordWrap(True)
        self.play_button = QPushButton("Play")
        self.play_button.setProperty("primary", True)
        self.play_button.clicked.connect(self.playAllRequested)
        self.shuffle_button = QPushButton("Shuffle")
        self.shuffle_button.clicked.connect(self.shuffleRequested)
        controls = QHBoxLayout()
        controls.addWidget(self.play_button)
        controls.addWidget(self.shuffle_button)
        info.addWidget(self.kind_label)
        info.addWidget(self.title)
        info.addWidget(self.subtitle)
        info.addSpacing(10)
        info.addLayout(controls)
        info.addStretch()
        hero_layout.addLayout(info, 1)
        self.content.addWidget(hero)
        self.related_title = QLabel("Albums by this artist")
        self.related_title.setStyleSheet("font-size: 18px; font-weight: 700;")
        self.related_grid = ResponsiveCardGrid("album", metadata_service)
        self.related_grid.itemClicked.connect(self.relatedAlbumActivated)
        self.content.addWidget(self.related_title)
        self.content.addWidget(self.related_grid)
        self.table = TrackTable([], metadata_service)
        self.table.setMinimumHeight(360)
        self.content.addWidget(self.table)
        self.item: Any = None

    def set_item(self, item: Any, tracks: list[Any], kind: str, metadata_service=None, related_albums: list[Any] | None = None) -> None:
        self.item = item
        self.kind_label.setText(kind.upper())
        self.title.setText(str(value(item, "title", "name", "album", "artist", default="Collection")))
        artist = value(item, "artist", "album_artist", default="")
        year = value(item, "year", "release_year", default="")
        count = len(tracks)
        parts = [str(x) for x in (artist, year, f"{count} tracks") if x]
        self.subtitle.setText(" · ".join(parts))
        self.art.set_track(item, metadata_service)
        self.related_title.setVisible(kind == "artist" and bool(related_albums))
        self.related_grid.setVisible(kind == "artist" and bool(related_albums))
        self.related_grid.set_items(related_albums or [])
        self.table.set_tracks(tracks)
