from __future__ import annotations

from typing import Any

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import QFrame, QLabel, QScrollArea, QSizePolicy, QToolButton, QVBoxLayout, QWidget

from .icons import icon
from ..services import value


class NavigationButton(QToolButton):
    def __init__(self, name: str, label: str, icon_name: str, parent=None):
        super().__init__(parent)
        self.page_name = name
        self.icon_name = icon_name
        self.setText(label)
        self.setIcon(icon(icon_name))
        self.setIconSize(QSize(18, 18))
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.setCheckable(True)
        self.setAutoExclusive(True)
        self.setMinimumHeight(38)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet("QToolButton { text-align: left; padding: 0 11px; border-radius: 8px; } QToolButton:checked { background: rgba(139,124,255,0.16); color: #A99FFF; font-weight: 650; }")


class Sidebar(QFrame):
    navigate = Signal(str)
    playlistSelected = Signal(object)
    createPlaylist = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Sidebar")
        self.setMinimumWidth(0)
        self.setMaximumWidth(232)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 20, 14, 16)
        root.setSpacing(16)
        brand_row = QWidget()
        b = QVBoxLayout(brand_row)
        b.setContentsMargins(8, 0, 0, 0)
        name = QLabel("SONORA")
        name.setStyleSheet("font-size: 16px; font-weight: 800; letter-spacing: 2px; color: #A99FFF;")
        tagline = QLabel("LOCAL MUSIC, REFINED")
        tagline.setProperty("role", "muted")
        tagline.setStyleSheet("font-size: 9px; letter-spacing: 1.3px;")
        b.addWidget(name)
        b.addWidget(tagline)
        root.addWidget(brand_row)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        body = QWidget()
        self.nav_layout = QVBoxLayout(body)
        self.nav_layout.setContentsMargins(0, 4, 2, 4)
        self.nav_layout.setSpacing(6)
        self.buttons: dict[str, NavigationButton] = {}
        self._section("DISCOVER")
        for name, label, icon_name in (
            ("home", "Home", "home"), ("now_playing", "Now Playing", "play"),
            ("songs", "Songs", "songs"), ("albums", "Albums", "album"),
            ("artists", "Artists", "artist"), ("recently_played", "Recently played", "recent"),
        ):
            self._add_navigation(name, label, icon_name)
        self._section("YOUR LIBRARY")
        self._add_navigation("playlists", "Playlists", "playlist")
        self._add_navigation("favorites", "Favorites", "heart")
        self.playlist_header = QLabel("PLAYLISTS")
        self.playlist_header.setStyleSheet("font-size: 10px; font-weight: 700; letter-spacing: 1px; color: #777D8B; margin: 12px 8px 3px;")
        self.nav_layout.addWidget(self.playlist_header)
        self.playlist_buttons: list[QToolButton] = []
        self.nav_layout.addStretch(1)
        scroll.setWidget(body)
        root.addWidget(scroll, 1)
        self.create_button = NavigationButton("create_playlist", "Create playlist", "plus")
        self.create_button.setAutoExclusive(False)
        root.addWidget(self.create_button)
        self.settings_button = NavigationButton("settings", "Settings", "settings")
        self.settings_button.setAutoExclusive(False)
        root.addWidget(self.settings_button)
        self.create_button.clicked.connect(self.createPlaylist)
        self.settings_button.clicked.connect(lambda: self.navigate.emit("settings"))
        self.set_active("home")

    def _section(self, title: str) -> None:
        label = QLabel(title)
        label.setStyleSheet("font-size: 10px; font-weight: 700; letter-spacing: 1px; color: #777D8B; margin: 8px 8px 3px;")
        self.nav_layout.addWidget(label)

    def _add_navigation(self, name: str, label: str, icon_name: str) -> None:
        button = NavigationButton(name, label, icon_name, self)
        button.clicked.connect(lambda _checked=False, key=name: self.navigate.emit(key))
        self.buttons[name] = button
        self.nav_layout.addWidget(button)

    def set_active(self, name: str) -> None:
        for item in self.buttons.values():
            item.setChecked(False)
        self.settings_button.setChecked(False)
        button = self.buttons.get(name)
        if button:
            button.setChecked(True)
        elif name == "settings":
            self.settings_button.setChecked(True)

    def set_playlists(self, playlists: list[Any]) -> None:
        for button in self.playlist_buttons:
            self.nav_layout.removeWidget(button)
            button.deleteLater()
        self.playlist_buttons.clear()
        for playlist in playlists:
            name = str(value(playlist, "name", "title", default=playlist))
            button = QToolButton()
            button.setText(name)
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
            button.setToolTip(name)
            button.setMinimumHeight(32)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setStyleSheet("QToolButton { text-align: left; padding: 0 12px; border-radius: 7px; color: palette(text); } QToolButton:hover { background: rgba(139,124,255,0.10); }")
            button.clicked.connect(lambda _checked=False, p=playlist: self.playlistSelected.emit(p))
            self.nav_layout.insertWidget(self.nav_layout.indexOf(self.playlist_header) + 1 + len(self.playlist_buttons), button)
            self.playlist_buttons.append(button)
