"""Qt model for scalable track tables and collection views."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QSortFilterProxyModel, Qt

from ..services import display_duration, track_id, track_title, value


class TrackTableModel(QAbstractTableModel):
    COLUMNS = ("", "Title", "Artist", "Album", "Duration", "Date added", "Genre")
    TrackRole = Qt.ItemDataRole.UserRole + 1
    TrackIdRole = Qt.ItemDataRole.UserRole + 2

    def __init__(self, tracks: list[Any] | None = None, parent=None):
        super().__init__(parent)
        self._tracks = list(tracks or [])
        self._sort_column = 1
        self._ascending = True

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._tracks)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.COLUMNS)

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return self.COLUMNS[section]
        return None

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self._tracks):
            return None
        track = self._tracks[index.row()]
        if role == self.TrackRole:
            return track
        if role == self.TrackIdRole:
            return track_id(track)
        if role == Qt.ItemDataRole.ToolTipRole:
            path = value(track, "path", "file_path", default="")
            return str(path) if path else track_title(track)
        if role == Qt.ItemDataRole.DisplayRole:
            return (
                "", track_title(track), str(value(track, "artist", "artists", default="Unknown artist") or "Unknown artist"),
                str(value(track, "album", default="Unknown album") or "Unknown album"), display_duration(track),
                str(value(track, "date_added", "added_at", default="") or "—"),
                str(value(track, "genre", default="") or "—"),
            )[index.column()]
        if role == Qt.ItemDataRole.TextAlignmentRole and index.column() == 4:
            return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        if role == Qt.ItemDataRole.UserRole:
            return value(track, "title", "artist", "album", "genre", "date_added", default="")
        return None

    def set_tracks(self, tracks: list[Any]) -> None:
        self.beginResetModel()
        self._tracks = list(tracks)
        if self._sort_column >= 0:
            self._sort(self._sort_column, self._ascending)
        self.endResetModel()

    def track_at(self, row: int) -> Any | None:
        return self._tracks[row] if 0 <= row < len(self._tracks) else None

    def tracks(self) -> list[Any]:
        return list(self._tracks)

    def sort(self, column: int, order: Qt.SortOrder = Qt.SortOrder.AscendingOrder) -> None:
        if not 0 <= column < len(self.COLUMNS) or column == 0:
            return
        self.layoutAboutToBeChanged.emit()
        self._sort(column, order == Qt.SortOrder.AscendingOrder)
        self.layoutChanged.emit()

    def _sort(self, column: int, ascending: bool) -> None:
        keys = {
            1: lambda item: track_title(item).casefold(),
            2: lambda item: str(value(item, "artist", "artists", default="")).casefold(),
            3: lambda item: str(value(item, "album", default="")).casefold(),
            4: lambda item: float(value(item, "duration", "duration_seconds", default=0) or 0),
            5: lambda item: str(value(item, "date_added", "added_at", default="")).casefold(),
            6: lambda item: str(value(item, "genre", default="")).casefold(),
        }
        if column in keys:
            self._tracks.sort(key=keys[column], reverse=not ascending)
        self._sort_column = column
        self._ascending = ascending

    def index_for_track(self, identifier: Any) -> QModelIndex:
        for row, track in enumerate(self._tracks):
            if track_id(track) == identifier:
                return self.index(row, 1)
        return QModelIndex()


class TrackFilterProxyModel(QSortFilterProxyModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.setFilterKeyColumn(-1)
        self.setSortRole(Qt.ItemDataRole.DisplayRole)

    def lessThan(self, left: QModelIndex, right: QModelIndex) -> bool:
        left_track = left.data(TrackTableModel.TrackRole)
        right_track = right.data(TrackTableModel.TrackRole)
        if left.column() == 4:
            try:
                return float(value(left_track, "duration", "duration_seconds", default=0) or 0) < float(value(right_track, "duration", "duration_seconds", default=0) or 0)
            except (TypeError, ValueError):
                pass
        left_text = str(left.data(Qt.ItemDataRole.DisplayRole) or "").casefold()
        right_text = str(right.data(Qt.ItemDataRole.DisplayRole) or "").casefold()
        return left_text < right_text
