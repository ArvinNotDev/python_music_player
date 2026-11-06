from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QVBoxLayout,
)

from ..components import TrackTable
from ..services import value


class PlaylistSelectDialog(QDialog):
    """Pick an existing playlist or enter a new name."""
    def __init__(self, playlists: list[Any], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add to playlist")
        self.setMinimumSize(360, 420)
        self.selected_playlist: Any = None
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Choose a playlist or create one"))
        self.list = QListWidget()
        for playlist in playlists:
            item = QListWidgetItem(str(value(playlist, "name", "title", default=playlist)))
            item.setData(Qt.ItemDataRole.UserRole, playlist)
            self.list.addItem(item)
        layout.addWidget(self.list, 1)
        self.name = QLineEdit()
        self.name.setPlaceholderText("New playlist name")
        layout.addWidget(self.name)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok)
        layout.addWidget(buttons)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)

    def _accept(self):
        if self.name.text().strip():
            self.selected_playlist = self.name.text().strip()
        elif self.list.currentItem():
            self.selected_playlist = self.list.currentItem().data(Qt.ItemDataRole.UserRole)
        else:
            return
        self.accept()


class TrackPickerDialog(QDialog):
    def __init__(self, tracks: list[Any], metadata_service=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add songs to playlist")
        self.setMinimumSize(760, 540)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Select one or more songs"))
        self.table = TrackTable(tracks, metadata_service, context_actions=False)
        self.table.table.setSelectionMode(self.table.table.SelectionMode.ExtendedSelection)
        layout.addWidget(self.table, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok)
        layout.addWidget(buttons)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

    def selected_tracks(self) -> list[Any]:
        return self.table.selected_tracks()
