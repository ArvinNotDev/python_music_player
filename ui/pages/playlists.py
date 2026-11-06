from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QPushButton, QSplitter,
    QVBoxLayout, QWidget,
)

from ..components import EmptyState, SectionHeader, TrackTable
from ..services import value
from .base import ScrollPage


class PlaylistsPage(ScrollPage):
    createRequested = Signal()
    renameRequested = Signal(object)
    deleteRequested = Signal(object)
    playlistSelected = Signal(object)
    playAllRequested = Signal()
    shuffleRequested = Signal()
    addSongsRequested = Signal()
    queueRequested = Signal()
    moveTrackRequested = Signal(int)

    def __init__(self, metadata_service=None, parent=None):
        super().__init__(parent)
        self.content.setContentsMargins(24, 24, 24, 24)
        header = QWidget()
        headrow = QHBoxLayout(header)
        headrow.setContentsMargins(0, 0, 0, 0)
        headrow.addWidget(SectionHeader("Playlists", "Your collections, together"), 1)
        self.create_button = QPushButton("＋  New playlist")
        self.create_button.setProperty("primary", True)
        self.create_button.clicked.connect(self.createRequested)
        headrow.addWidget(self.create_button)
        self.content.addWidget(header)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.list = QListWidget()
        self.list.setMinimumWidth(190)
        self.list.setMaximumWidth(300)
        self.list.currentItemChanged.connect(self._selection_changed)
        splitter.addWidget(self.list)
        detail = QWidget()
        detail_layout = QVBoxLayout(detail)
        detail_layout.setContentsMargins(12, 0, 0, 0)
        toolbar = QWidget()
        tools = QHBoxLayout(toolbar)
        tools.setContentsMargins(0, 0, 0, 0)
        self.name = QLabel("Select a playlist")
        self.name.setStyleSheet("font-size: 22px; font-weight: 700;")
        tools.addWidget(self.name, 1)
        self.play = QPushButton("Play")
        self.play.setProperty("primary", True)
        self.shuffle = QPushButton("Shuffle")
        self.add_songs = QPushButton("Add songs")
        self.queue = QPushButton("Add to queue")
        self.move_up = QPushButton("↑")
        self.move_up.setToolTip("Move selected track up")
        self.move_down = QPushButton("↓")
        self.move_down.setToolTip("Move selected track down")
        self.rename = QPushButton("Rename")
        self.delete = QPushButton("Delete")
        for button in (self.play, self.shuffle, self.add_songs, self.queue, self.move_up, self.move_down, self.rename, self.delete):
            tools.addWidget(button)
        self.play.clicked.connect(self.playAllRequested)
        self.shuffle.clicked.connect(self.shuffleRequested)
        self.add_songs.clicked.connect(self.addSongsRequested)
        self.queue.clicked.connect(self.queueRequested)
        self.move_up.clicked.connect(lambda: self.moveTrackRequested.emit(-1))
        self.move_down.clicked.connect(lambda: self.moveTrackRequested.emit(1))
        self.rename.clicked.connect(self._rename)
        self.delete.clicked.connect(self._delete)
        detail_layout.addWidget(toolbar)
        self.empty = EmptyState("Choose a playlist", "Select a playlist on the left to view and play its tracks.")
        detail_layout.addWidget(self.empty, 1)
        self.table = TrackTable([], metadata_service)
        self.table.setMinimumHeight(320)
        self.table.setVisible(False)
        detail_layout.addWidget(self.table, 1)
        self.table.table.selectionModel().currentChanged.connect(lambda *_: self._update_track_actions())
        splitter.addWidget(detail)
        splitter.setSizes([230, 720])
        self.content.addWidget(splitter, 1)
        self._playlists: list[Any] = []
        self._current: Any = None

    def set_playlists(self, playlists: list[Any]) -> None:
        self._playlists = list(playlists)
        current_id = value(self._current, "id", "playlist_id", "name", default=None) if self._current else None
        self.list.blockSignals(True)
        self.list.clear()
        selected = None
        for playlist in self._playlists:
            name = str(value(playlist, "name", "title", default=playlist))
            item = QListWidgetItem(name)
            item.setData(Qt.ItemDataRole.UserRole, playlist)
            self.list.addItem(item)
            if value(playlist, "id", "playlist_id", "name", default=name) == current_id:
                selected = item
        if selected:
            self.list.setCurrentItem(selected)
        elif self.list.count():
            self.list.setCurrentRow(0)
        self._current = self.current_playlist()
        self.list.blockSignals(False)
        self._update_actions()

    def select_playlist(self, playlist: Any) -> None:
        identifier = value(playlist, "id", "playlist_id", "name", default=playlist)
        self.list.blockSignals(True)
        for row in range(self.list.count()):
            item = self.list.item(row)
            candidate = item.data(Qt.ItemDataRole.UserRole)
            if value(candidate, "id", "playlist_id", "name", default=candidate) == identifier:
                self.list.setCurrentItem(item)
                self._current = candidate
                break
        self.list.blockSignals(False)
        self._update_actions()

    def set_playlist_tracks(self, playlist: Any, tracks: list[Any]) -> None:
        self._current = playlist
        name = str(value(playlist, "name", "title", default=playlist or "Playlist"))
        self.name.setText(name)
        self.table.set_tracks(tracks)
        self.empty.setVisible(not tracks)
        self.table.setVisible(bool(tracks))
        self._update_actions()

    def current_playlist(self) -> Any:
        item = self.list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _selection_changed(self, current, _previous) -> None:
        playlist = current.data(Qt.ItemDataRole.UserRole) if current else None
        self._current = playlist
        self._update_actions()
        if playlist:
            self.playlistSelected.emit(playlist)

    def _update_actions(self) -> None:
        enabled = self._current is not None
        self.play.setEnabled(enabled)
        self.shuffle.setEnabled(enabled)
        self.add_songs.setEnabled(enabled)
        name = str(value(self._current, "name", "title", default=self._current or "")) if enabled else ""
        protected = name.casefold() == "favorites"
        self.rename.setEnabled(enabled and not protected)
        self.delete.setEnabled(enabled and not protected)
        self.queue.setEnabled(enabled)
        self._update_track_actions()

    def set_reorder_supported(self, supported: bool) -> None:
        self._reorder_supported = supported
        self.move_up.setToolTip("Move selected track up" if supported else "Track reordering is unavailable")
        self.move_down.setToolTip("Move selected track down" if supported else "Track reordering is unavailable")
        self._update_track_actions()

    def _update_track_actions(self) -> None:
        supported = getattr(self, "_reorder_supported", False)
        row = self.table.table.currentIndex().row()
        count = self.table.proxy_model.rowCount()
        self.move_up.setEnabled(supported and row > 0)
        self.move_down.setEnabled(supported and 0 <= row < count - 1)

    def _rename(self) -> None:
        if self._current:
            self.renameRequested.emit(self._current)

    def _delete(self) -> None:
        if self._current:
            self.deleteRequested.emit(self._current)
