"""Reusable model/view track list with keyboard and context actions."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QAbstractItemView, QMenu, QTableView, QVBoxLayout, QWidget

from ..delegates import ArtworkDelegate
from ..models import TrackFilterProxyModel, TrackTableModel


class TrackTable(QWidget):
    activated = Signal(object)
    selected = Signal(object)
    playNextRequested = Signal(object)
    queueRequested = Signal(object)
    favoriteRequested = Signal(object)
    playlistRequested = Signal(object)
    metadataRequested = Signal(object)
    removeRequested = Signal(object)

    def __init__(self, tracks: list[Any] | None = None, metadata_service: Any = None, *, context_actions: bool = True, parent=None):
        super().__init__(parent)
        self.source_model = TrackTableModel(tracks, self)
        self.allow_remove = False
        self.proxy_model = TrackFilterProxyModel(self)
        self.proxy_model.setSourceModel(self.source_model)
        self.table = QTableView(self)
        self.table.setModel(self.proxy_model)
        self.table.setItemDelegateForColumn(0, ArtworkDelegate(metadata_service, self.table))
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(True)
        self.table.setShowGrid(False)
        self.table.setWordWrap(False)
        self.table.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setDefaultSectionSize(58)
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.horizontalHeader().setSectionResizeMode(0, self.table.horizontalHeader().ResizeMode.Fixed)
        self.table.setColumnWidth(0, 58)
        self.table.horizontalHeader().setSectionResizeMode(1, self.table.horizontalHeader().ResizeMode.Stretch)
        self.table.setColumnWidth(2, 180)
        self.table.setColumnWidth(3, 180)
        self.table.setColumnWidth(4, 76)
        self.table.setColumnWidth(5, 130)
        self.table.setColumnWidth(6, 130)
        self.table.doubleClicked.connect(self._activate_index)
        self.table.selectionModel().currentChanged.connect(lambda current, _previous: self.selected.emit(self._track_from_index(current)))
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        if context_actions:
            self.table.customContextMenuRequested.connect(self._show_context_menu)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.table)

    def set_tracks(self, tracks: list[Any]) -> None:
        self.source_model.set_tracks(tracks)

    def tracks(self) -> list[Any]:
        return self.source_model.tracks()

    def set_filter(self, query: str) -> None:
        self.proxy_model.setFilterFixedString(query)

    def selected_tracks(self) -> list[Any]:
        indexes = self.table.selectionModel().selectedRows()
        return [track for index in indexes if (track := self._track_from_index(index)) is not None]

    def current_track(self) -> Any | None:
        return self._track_from_index(self.table.currentIndex())

    def focus_search_result(self) -> None:
        if self.proxy_model.rowCount():
            self.table.setCurrentIndex(self.proxy_model.index(0, 1))

    def _track_from_index(self, index):
        if not index.isValid():
            return None
        source = self.proxy_model.mapToSource(index)
        return self.source_model.track_at(source.row())

    def _activate_index(self, index) -> None:
        track = self._track_from_index(index)
        if track is not None:
            self.activated.emit(track)

    def _show_context_menu(self, point) -> None:
        index = self.table.indexAt(point)
        track = self._track_from_index(index)
        if track is None:
            return
        if not index.isValid():
            return
        self.table.setCurrentIndex(index)
        menu = QMenu(self)
        menu.addAction("Play", lambda: self.activated.emit(track))
        menu.addAction("Play next", lambda: self.playNextRequested.emit(track))
        menu.addAction("Add to queue", lambda: self.queueRequested.emit(track))
        menu.addSeparator()
        menu.addAction("Add to favorites", lambda: self.favoriteRequested.emit(track))
        menu.addAction("Add to playlist…", lambda: self.playlistRequested.emit(track))
        menu.addSeparator()
        menu.addAction("Track details…", lambda: self.metadataRequested.emit(track))
        if self.allow_remove:
            menu.addSeparator()
            menu.addAction("Remove from this list", lambda: self.removeRequested.emit(track))
        menu.exec(self.table.viewport().mapToGlobal(point))


__all__ = ["TrackTable"]
