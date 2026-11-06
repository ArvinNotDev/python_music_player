from __future__ import annotations

from typing import Any

from PySide6.QtCore import QAbstractTableModel, QMimeData, QModelIndex, Qt, Signal
from PySide6.QtWidgets import QAbstractItemView, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QTableView, QVBoxLayout, QWidget

from ..delegates import ArtworkDelegate
from ..services import display_duration, track_title, value


class QueueModel(QAbstractTableModel):
    moveRequested = Signal(int, int)
    HEADERS = ("", "", "Title", "Artist", "Duration")
    TrackRole = Qt.ItemDataRole.UserRole

    def __init__(self, parent=None):
        super().__init__(parent)
        self._tracks: list[Any] = []
        self.current_index = -1

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._tracks)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else 5

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return self.HEADERS[section]
        return None

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self._tracks):
            return None
        track = self._tracks[index.row()]
        if role == Qt.ItemDataRole.DisplayRole:
            return ("▶" if index.row() == self.current_index else "", "", track_title(track), str(value(track, "artist", "artists", default="Unknown artist")), display_duration(track))[index.column()]
        if role == Qt.ItemDataRole.UserRole:
            return track
        return None

    def set_queue(self, tracks: list[Any], current_index: int) -> None:
        self.beginResetModel()
        self._tracks = list(tracks)
        self.current_index = current_index
        self.endResetModel()

    def track_at(self, row: int):
        return self._tracks[row] if 0 <= row < len(self._tracks) else None

    def flags(self, index):
        base = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        if index.isValid():
            return base | Qt.ItemFlag.ItemIsDragEnabled | Qt.ItemFlag.ItemIsDropEnabled
        return base | Qt.ItemFlag.ItemIsDropEnabled

    def mimeTypes(self):
        return ["application/x-sonora-queue-row"]

    def mimeData(self, indexes):
        data = QMimeData()
        rows = sorted({index.row() for index in indexes if index.isValid()})
        if rows:
            data.setData("application/x-sonora-queue-row", str(rows[0]).encode("ascii"))
        return data

    def supportedDropActions(self):
        return Qt.DropAction.MoveAction

    def dropMimeData(self, data, action, row, column, parent):
        if action == Qt.DropAction.IgnoreAction:
            return True
        if not data.hasFormat("application/x-sonora-queue-row"):
            return False
        try:
            source = int(bytes(data.data("application/x-sonora-queue-row")).decode("ascii"))
        except (TypeError, ValueError):
            return False
        target = row if row >= 0 else parent.row()
        if 0 <= source < len(self._tracks) and 0 <= target < len(self._tracks) and source != target:
            self.moveRequested.emit(source, target)
            return True
        return False


class QueuePanel(QWidget):
    removeRequested = Signal(int)
    moveRequested = Signal(int, int)
    playRequested = Signal(int)
    clearRequested = Signal()
    addMoreRequested = Signal()

    def __init__(self, metadata_service=None, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 20, 18, 16)
        layout.setSpacing(14)
        top = QHBoxLayout()
        title = QLabel("Queue")
        title.setStyleSheet("font-size: 18px; font-weight: 700;")
        top.addWidget(title, 1)
        self.add_button = QPushButton("Add music")
        self.clear_button = QPushButton("Clear")
        top.addWidget(self.add_button)
        top.addWidget(self.clear_button)
        layout.addLayout(top)
        self.current_label = QLabel("Nothing playing")
        self.current_label.setProperty("role", "secondary")
        layout.addWidget(self.current_label)
        self.model = QueueModel(self)
        self.table = QTableView()
        self.table.setModel(self.model)
        self.table.setItemDelegateForColumn(1, ArtworkDelegate(metadata_service, self.table))
        self.table.setDragEnabled(True)
        self.table.setAcceptDrops(True)
        self.table.setDropIndicatorShown(True)
        self.table.setDragDropMode(QTableView.DragDropMode.InternalMove)
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setDefaultSectionSize(50)
        self.table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(True)
        self.table.setWordWrap(False)
        self.table.setColumnWidth(0, 20)
        self.table.setColumnWidth(1, 46)
        self.table.setColumnWidth(2, 132)
        self.table.setColumnWidth(3, 100)
        self.table.setColumnWidth(4, 60)
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table, 1)
        actions = QHBoxLayout()
        actions.setSpacing(8)
        self.up = QPushButton("Move up")
        self.down = QPushButton("Move down")
        self.remove = QPushButton("Remove")
        for button in (self.up, self.down, self.remove):
            button.setMinimumHeight(36)
        self.remove.setProperty("primary", True)
        actions.addWidget(self.up)
        actions.addWidget(self.down)
        actions.addWidget(self.remove)
        layout.addLayout(actions)
        self.add_button.clicked.connect(self.addMoreRequested)
        self.model.moveRequested.connect(self.moveRequested)
        self.clear_button.clicked.connect(self.clearRequested)
        self.remove.clicked.connect(self._remove)
        self.up.clicked.connect(lambda: self._move(-1))
        self.down.clicked.connect(lambda: self._move(1))
        self.table.doubleClicked.connect(lambda index: self.playRequested.emit(index.row()))

    def set_queue(self, tracks: list[Any], current_index: int = -1, current_track: Any = None) -> None:
        self.model.set_queue(tracks, current_index)
        name = track_title(current_track) if current_track else (track_title(tracks[current_index]) if 0 <= current_index < len(tracks) else "Nothing playing")
        self.current_label.setText(f"Now playing  ·  {name}" if name != "Nothing playing" else name)

    def _selected_row(self) -> int:
        rows = self.table.selectionModel().selectedRows()
        return rows[0].row() if rows else -1

    def _remove(self) -> None:
        row = self._selected_row()
        if row >= 0:
            self.removeRequested.emit(row)

    def _move(self, delta: int) -> None:
        row = self._selected_row()
        target = row + delta
        if row >= 0 and 0 <= target < self.model.rowCount():
            self.moveRequested.emit(row, target)
