from __future__ import annotations

from typing import Any

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QListWidget, QListWidgetItem, QTabWidget, QVBoxLayout, QWidget

from ..components import EmptyState, ResponsiveCardGrid, TrackTable
from ..services import value
from .base import ScrollPage


class SearchPage(ScrollPage):
    trackActivated = Signal(object)
    albumActivated = Signal(object)
    artistActivated = Signal(object)
    playlistActivated = Signal(object)

    def __init__(self, metadata_service=None, parent=None):
        super().__init__(parent)
        self.tabs = QTabWidget()
        self.tracks = TrackTable([], metadata_service)
        self.tracks.activated.connect(self.trackActivated)
        self.albums = ResponsiveCardGrid("album", metadata_service)
        self.artists = ResponsiveCardGrid("artist", metadata_service)
        self.albums.itemClicked.connect(self.albumActivated)
        self.artists.itemClicked.connect(self.artistActivated)
        self.playlists = QListWidget()
        self.playlists.itemActivated.connect(lambda item: self.playlistActivated.emit(item.data(256)))
        self.tabs.addTab(self.tracks, "Songs")
        self.tabs.addTab(self.albums, "Albums")
        self.tabs.addTab(self.artists, "Artists")
        self.tabs.addTab(self.playlists, "Playlists")
        self.content.addWidget(self.tabs, 1)
        self.empty = EmptyState("Search your library", "Find songs, artists, albums, and playlists.")
        self.content.addWidget(self.empty)
        self._all: tuple[list[Any], list[Any], list[Any], list[Any]] = ([], [], [], [])

    def set_data(self, tracks, albums, artists, playlists) -> None:
        self._all = (list(tracks), list(albums), list(artists), list(playlists))

    def search(self, query: str) -> None:
        q = query.casefold().strip()
        tracks, albums, artists, playlists = self._all
        track_matches = [item for item in tracks if not q or q in " ".join(str(value(item, k, default="")) for k in ("title", "artist", "album", "genre", "album_artist", "composer", "comment", "year", "track_number")).casefold()]
        album_matches = [item for item in albums if not q or q in " ".join(str(value(item, k, default="")) for k in ("title", "name", "album", "artist", "year")).casefold()]
        artist_matches = [item for item in artists if not q or q in str(value(item, "name", "artist", "title", default="")).casefold()]
        self.tracks.set_tracks(track_matches)
        self.albums.set_items(album_matches)
        self.artists.set_items(artist_matches)
        self.playlists.clear()
        playlist_matches = 0
        for playlist in playlists:
            name = str(value(playlist, "name", "title", default=playlist))
            if not q or q in name.casefold():
                item = QListWidgetItem(name)
                item.setData(256, playlist)
                self.playlists.addItem(item)
                playlist_matches += 1
        total = len(track_matches) + len(album_matches) + len(artist_matches) + playlist_matches
        self.empty.title_label.setText("Search your library" if not q else "No matches found")
        self.empty.description_label.setText("Find songs, artists, albums, and playlists." if not q else f"Nothing matched “{query}”. Try a different title, artist, album, or playlist.")
        self.empty.setVisible(not q or total == 0)
        self.tabs.setVisible(bool(q and total))
