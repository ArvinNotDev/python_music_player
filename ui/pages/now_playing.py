from __future__ import annotations

from typing import Any

from PySide6.QtCore import QBoxLayout, QSignalBlocker, QSize, Qt, Signal
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton, QSlider, QSizePolicy, QVBoxLayout, QWidget,
)

from ..components import ArtworkLabel, IconButton
from ..components.icons import icon
from ..services import display_duration, duration_seconds, track_id, track_title, value
from .base import ScrollPage


def _clock(seconds: float) -> str:
    total = max(0, int(seconds or 0))
    return f"{total // 60}:{total % 60:02d}"


class CenteredArtworkRow(QWidget):
    """A full-width row that keeps the square cover centered at every size."""

    def __init__(self, artwork: ArtworkLabel, parent=None):
        super().__init__(parent)
        self.artwork = artwork
        self.artwork.setParent(self)
        self.setMinimumWidth(0)
        self.setFixedHeight(artwork.height())
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._center_artwork()

    def _center_artwork(self) -> None:
        x = max(0, (self.width() - self.artwork.width()) // 2)
        y = max(0, (self.height() - self.artwork.height()) // 2)
        self.artwork.move(x, y)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._center_artwork()


class NowPlayingPage(ScrollPage):
    favoriteRequested = Signal(object)
    playlistRequested = Signal(object)
    moreRequested = Signal(object)
    lyricsRequested = Signal()
    transportRequested = Signal(str)
    seekRequested = Signal(float)

    def __init__(self, metadata_service=None, parent=None):
        super().__init__(parent)
        self.metadata_service = metadata_service
        self.track: Any = None
        self.playing = False
        self.position = 0.0
        self.duration = 0.0
        self._dragging = False
        self._text_color = "#F4F6FA"
        self._accent_color = "#8B7CFF"

        self.content.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.content.setSpacing(18)

        eyebrow = QLabel("YOUR LISTENING SPACE")
        eyebrow.setProperty("role", "eyebrow")
        self.content.addWidget(eyebrow)

        self.surface = QFrame()
        self.surface.setObjectName("NowPlayingSurface")
        self.hero_layout = QBoxLayout(QBoxLayout.Direction.LeftToRight, self.surface)
        self.hero_layout.setContentsMargins(28, 28, 28, 28)
        self.hero_layout.setSpacing(30)

        self.artwork_panel = QWidget()
        artwork_column = QVBoxLayout(self.artwork_panel)
        artwork_column.setContentsMargins(0, 0, 0, 0)
        artwork_column.setSpacing(12)
        artwork_frame = QFrame()
        artwork_frame.setObjectName("NowPlayingArtworkFrame")
        artwork_layout = QVBoxLayout(artwork_frame)
        artwork_layout.setContentsMargins(10, 10, 10, 10)
        self.cover = ArtworkLabel(340)
        self.cover.setStyleSheet(
            "background: #222936; border-radius: 12px; color: #A397FF; font-size: 72px;"
        )
        self.cover.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.cover_row = CenteredArtworkRow(self.cover)
        artwork_layout.addWidget(self.cover_row)
        artwork_column.addWidget(artwork_frame)
        art_caption = QLabel("ALBUM ARTWORK")
        art_caption.setProperty("role", "muted")
        art_caption.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        art_caption.setStyleSheet("font-size: 10px; font-weight: 700; letter-spacing: 1.2px;")
        artwork_column.addWidget(art_caption)
        artwork_column.addStretch(1)

        self.details_panel = QWidget()
        details = QVBoxLayout(self.details_panel)
        details.setContentsMargins(0, 4, 0, 0)
        details.setSpacing(12)

        self.track_state = QLabel("NOW PLAYING")
        self.track_state.setProperty("role", "eyebrow")
        details.addWidget(self.track_state)

        self.title = QLabel("Nothing playing")
        self.title.setWordWrap(True)
        self.title.setMinimumWidth(0)
        self.title.setMaximumHeight(102)
        self.title.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.title.setStyleSheet("font-size: 31px; font-weight: 800; letter-spacing: -0.6px;")
        details.addWidget(self.title)

        self.artist = QLabel("Choose a track from your library")
        self.artist.setProperty("role", "secondary")
        self.artist.setWordWrap(True)
        self.artist.setMinimumWidth(0)
        self.artist.setStyleSheet("font-size: 17px; font-weight: 600;")
        details.addWidget(self.artist)

        self.album = QLabel("")
        self.album.setProperty("role", "muted")
        self.album.setWordWrap(True)
        self.album.setMinimumWidth(0)
        details.addWidget(self.album)

        self.info = QFrame()
        self.info.setObjectName("Surface")
        info_layout = QVBoxLayout(self.info)
        info_layout.setContentsMargins(14, 12, 14, 12)
        info_layout.setSpacing(5)
        info_heading = QLabel("TRACK DETAILS")
        info_heading.setProperty("role", "muted")
        info_heading.setStyleSheet("font-size: 10px; font-weight: 750; letter-spacing: 1.1px;")
        info_layout.addWidget(info_heading)
        self.info_text = QLabel("Track details will appear here.")
        self.info_text.setProperty("role", "secondary")
        self.info_text.setWordWrap(True)
        self.info_text.setMinimumWidth(0)
        self.info_text.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        info_layout.addWidget(self.info_text)
        details.addWidget(self.info)

        transport = QHBoxLayout()
        transport.setSpacing(10)
        transport.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self.previous = IconButton("previous", "Previous track")
        self.play_button = IconButton("play", "Play", checkable=True)
        self.play_button.setFixedSize(54, 54)
        self.play_button.setIconSize(QSize(24, 24))
        self.play_button.setProperty("primary", True)
        self.next = IconButton("next", "Next track")
        transport.addWidget(self.previous)
        transport.addWidget(self.play_button)
        transport.addWidget(self.next)
        details.addLayout(transport)

        progress = QHBoxLayout()
        progress.setSpacing(10)
        self.current_time = QLabel("0:00")
        self.current_time.setProperty("role", "muted")
        self.current_time.setMinimumWidth(42)
        self.current_time.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.seek = QSlider(Qt.Orientation.Horizontal)
        self.seek.setRange(0, 1000)
        self.seek.setEnabled(False)
        self.total_time = QLabel("0:00")
        self.total_time.setProperty("role", "muted")
        self.total_time.setMinimumWidth(42)
        progress.addWidget(self.current_time)
        progress.addWidget(self.seek, 1)
        progress.addWidget(self.total_time)
        details.addLayout(progress)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        self.favorite = IconButton("heart", "Add to favorites", checkable=True)
        self.add_playlist = QPushButton("Add to playlist")
        self.lyrics = QPushButton("Lyrics")
        self.more = IconButton("more", "More track options")
        actions.addWidget(self.favorite)
        actions.addWidget(self.add_playlist)
        actions.addWidget(self.lyrics)
        actions.addWidget(self.more)
        actions.addStretch(1)
        details.addLayout(actions)
        details.addStretch(1)

        self.hero_layout.addWidget(self.artwork_panel, 5)
        self.hero_layout.addWidget(self.details_panel, 6)
        self.content.addWidget(self.surface)

        self.previous.clicked.connect(lambda: self.transportRequested.emit("previous"))
        self.play_button.clicked.connect(lambda: self.transportRequested.emit("toggle_play_pause"))
        self.next.clicked.connect(lambda: self.transportRequested.emit("next"))
        self.seek.sliderPressed.connect(self._seek_started)
        self.seek.sliderReleased.connect(self._seek_released)
        self.favorite.clicked.connect(lambda: self.favoriteRequested.emit(self.track) if self.track else None)
        self.add_playlist.clicked.connect(lambda: self.playlistRequested.emit(self.track) if self.track else None)
        self.more.clicked.connect(lambda: self.moreRequested.emit(self.track) if self.track else None)
        self.lyrics.clicked.connect(self.lyricsRequested)

        self._set_track_actions_enabled(False)
        self._adapt_layout()

    def _set_track_actions_enabled(self, enabled: bool) -> None:
        for widget in (
            self.previous, self.play_button, self.next, self.seek,
            self.favorite, self.add_playlist, self.lyrics, self.more,
        ):
            widget.setEnabled(enabled)

    def _adapt_layout(self) -> None:
        viewport_width = self.scroll.viewport().width()
        wide = viewport_width >= 920
        self.hero_layout.setDirection(
            QBoxLayout.Direction.LeftToRight if wide else QBoxLayout.Direction.TopToBottom
        )
        self.hero_layout.setSpacing(30 if wide else 20)
        self.hero_layout.setStretch(0, 5 if wide else 0)
        self.hero_layout.setStretch(1, 6 if wide else 0)
        self.hero_layout.setContentsMargins(28 if wide else 20, 24, 28 if wide else 20, 24)
        self.artwork_panel.setMaximumWidth(440 if wide else 16777215)
        size = min(360, max(188, int(viewport_width * (0.34 if wide else 0.58))))
        self.cover.set_artwork_size(size)
        self.cover_row.setFixedHeight(size)
        self.artwork_panel.setSizePolicy(
            QSizePolicy.Policy.Preferred if wide else QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Preferred,
        )

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._adapt_layout()

    def set_track(self, track: Any, *, force: bool = False) -> None:
        same_track = track_id(track) == track_id(self.track)
        if same_track and not force:
            return
        self.track = track
        if not track:
            self.cover.set_track(None)
            self.title.setText("Nothing playing")
            self.artist.setText("Choose a track from your library")
            self.album.setText("")
            self.info_text.setText("Track details will appear here.")
            self.position = 0.0
            self.duration = 0.0
            self._set_track_actions_enabled(False)
            self.set_position(0.0, 0.0)
            self.set_playback_state(False)
            self.set_favorite(False)
            return

        self.cover.set_track(track, self.metadata_service)
        self.title.setText(track_title(track))
        self.title.setToolTip(self.title.text())
        self.artist.setText(str(value(track, "artist", "artists", default="Unknown artist") or "Unknown artist"))
        self.album.setText(str(value(track, "album", default="") or ""))
        self.album.setVisible(bool(self.album.text()))

        details = []
        for key, label in (
            ("album_artist", "Album artist"),
            ("genre", "Genre"),
            ("year", "Year"),
            ("track_number", "Track"),
            ("disc_number", "Disc"),
            ("composer", "Composer"),
        ):
            field = value(track, key, default="")
            if field not in (None, ""):
                details.append(f"{label}: {field}")
        duration = display_duration(track)
        if duration != "—":
            details.append(f"Duration: {duration}")
        self.info_text.setText("   ·   ".join(details) if details else "No additional metadata is available.")
        self._set_track_actions_enabled(True)
        self.set_position(0.0, duration_seconds(track))

    def set_playback_state(self, playing: bool) -> None:
        self.playing = bool(playing)
        blocker = QSignalBlocker(self.play_button)
        self.play_button.setChecked(self.playing)
        del blocker
        self.play_button.icon_name = "pause" if self.playing else "play"
        self.play_button.setIcon(icon(self.play_button.icon_name, "#FFFFFF" if self.playing else self._text_color))
        self.play_button.setToolTip("Pause" if self.playing else "Play")
        self.play_button.setAccessibleName(self.play_button.toolTip())

    def set_position(self, seconds: float, duration: float | None = None) -> None:
        if duration is not None:
            self.duration = max(0.0, float(duration or 0))
        self.position = max(0.0, float(seconds or 0))
        self.current_time.setText(_clock(self.position))
        self.total_time.setText(_clock(self.duration))
        self.seek.setEnabled(bool(self.track) and self.duration > 0)
        if not self._dragging and self.duration > 0:
            blocker = QSignalBlocker(self.seek)
            self.seek.setValue(round(min(self.position, self.duration) / self.duration * 1000))
            del blocker

    def set_favorite(self, favorite: bool) -> None:
        active = bool(favorite)
        self.favorite.setChecked(active)
        self.favorite.setProperty("active", active)
        self.favorite.setToolTip("Remove from favorites" if active else "Add to favorites")
        self.favorite.setIcon(icon("heart", self._accent_color if active else self._text_color))
        self.favorite.style().unpolish(self.favorite)
        self.favorite.style().polish(self.favorite)

    def set_theme_colors(self, text_color: str, accent_color: str) -> None:
        self._text_color = text_color
        self._accent_color = accent_color
        self.set_playback_state(self.playing)
        self.set_favorite(self.favorite.isChecked())

    def _seek_started(self) -> None:
        self._dragging = True

    def _seek_released(self) -> None:
        if self.duration > 0:
            position = self.seek.value() / 1000 * self.duration
            self.seekRequested.emit(position)
        self._dragging = False
