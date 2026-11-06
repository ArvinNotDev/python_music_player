from __future__ import annotations

from typing import Any

from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QVBoxLayout, QWidget

from ..components import ArtworkLabel, IconButton
from ..services import display_duration, track_id, track_title, value
from .base import ScrollPage


class NowPlayingPage(ScrollPage):
    favoriteRequested = Signal(object)
    playlistRequested = Signal(object)
    moreRequested = Signal(object)
    lyricsRequested = Signal()

    def __init__(self, metadata_service=None, parent=None):
        super().__init__(parent)
        self.metadata_service = metadata_service
        # Keep the page layout full-width. A dedicated expanding row with
        # equal stretch on both sides guarantees the artwork stays centered
        # as the scroll viewport and stacked page sizes change.
        self.content.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.content.setSpacing(22)
        self.cover = ArtworkLabel(340)
        self.cover.setStyleSheet("background: #242630; border-radius: 16px; color: #A095FF; font-size: 72px;")
        self.cover.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.cover_row = QWidget()
        self.cover_row.setMinimumWidth(0)
        self.cover_row.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        cover_layout = QHBoxLayout(self.cover_row)
        cover_layout.setContentsMargins(0, 0, 0, 0)
        cover_layout.setSpacing(0)
        cover_layout.addStretch(1)
        cover_layout.addWidget(self.cover, 0, Qt.AlignmentFlag.AlignCenter)
        cover_layout.addStretch(1)
        self.content.addWidget(self.cover_row)
        self.title = QLabel("Nothing playing")
        self.title.setWordWrap(True)
        self.title.setMinimumWidth(0)
        self.title.setMaximumWidth(680)
        self.title.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title.setStyleSheet("font-size: 26px; font-weight: 750;")
        self.artist = QLabel("Choose a track from your library")
        self.artist.setProperty("role", "secondary")
        self.artist.setWordWrap(True)
        self.artist.setMinimumWidth(0)
        self.artist.setMaximumWidth(680)
        self.artist.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.artist.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.album = QLabel("")
        self.album.setProperty("role", "muted")
        self.album.setWordWrap(True)
        self.album.setMinimumWidth(0)
        self.album.setMaximumWidth(680)
        self.album.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.album.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.content.addWidget(self.title, 0, Qt.AlignmentFlag.AlignHCenter)
        self.content.addWidget(self.artist, 0, Qt.AlignmentFlag.AlignHCenter)
        self.content.addWidget(self.album, 0, Qt.AlignmentFlag.AlignHCenter)
        actions = QHBoxLayout()
        actions.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.favorite = IconButton("heart", "Add to favorites")
        self.add_playlist = QPushButton("Add to playlist")
        self.add_playlist.setMinimumHeight(38)
        self.more = IconButton("more", "More track options")
        self.lyrics = QPushButton("Open lyrics")
        self.lyrics.setMinimumHeight(38)
        actions.addWidget(self.favorite)
        actions.addWidget(self.add_playlist)
        actions.addWidget(self.lyrics)
        actions.addWidget(self.more)
        self.content.addLayout(actions)
        self.info = QFrame()
        self.info.setObjectName("Surface")
        self.info.setMaximumWidth(760)
        self.info.setMinimumWidth(0)
        self.info.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        info_layout = QVBoxLayout(self.info)
        info_layout.setContentsMargins(22, 18, 22, 18)
        info_layout.setSpacing(10)
        heading = QLabel("Track information")
        heading.setStyleSheet("font-weight: 650;")
        info_layout.addWidget(heading)
        self.info_text = QLabel("Track details will appear here.")
        self.info_text.setProperty("role", "secondary")
        self.info_text.setWordWrap(True)
        self.info_text.setMinimumWidth(0)
        self.info_text.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        info_layout.addWidget(self.info_text)
        self.content.addWidget(self.info, 0, Qt.AlignmentFlag.AlignHCenter)
        self.track: Any = None
        self.favorite.clicked.connect(lambda: self.favoriteRequested.emit(self.track) if self.track else None)
        self.add_playlist.clicked.connect(lambda: self.playlistRequested.emit(self.track) if self.track else None)
        self.more.clicked.connect(lambda: self.moreRequested.emit(self.track) if self.track else None)
        self.lyrics.clicked.connect(self.lyricsRequested)

    def set_track(self, track: Any, *, force: bool = False) -> None:
        same_track = track_id(track) == track_id(self.track)
        if same_track and not force:
            # Re-entering this page should not clear/reload artwork and restart
            # the cover transition when the active track has not changed.
            return
        self.track = track
        if not track:
            self.cover.set_track(None)
            self.title.setText("Nothing playing")
            self.artist.setText("Choose a track from your library")
            self.album.setText("")
            self.info_text.setText("Track details will appear here.")
            return
        self.cover.set_track(track, self.metadata_service)
        self.title.setText(track_title(track))
        self.artist.setText(str(value(track, "artist", "artists", default="Unknown artist")))
        self.album.setText(str(value(track, "album", default="")))
        details = []
        for key, label in (("album", "Album"), ("album_artist", "Album artist"), ("year", "Year"), ("genre", "Genre"), ("track_number", "Track"), ("disc_number", "Disc")):
            val = value(track, key, default="")
            if val:
                details.append(f"{label}: {val}")
        duration = display_duration(track)
        if duration != "—":
            details.append(f"Duration: {duration}")
        self.info_text.setText("  ·  ".join(details) if details else "No additional metadata is available.")
