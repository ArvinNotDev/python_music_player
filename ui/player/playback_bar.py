from __future__ import annotations

from typing import Any

from PySide6.QtCore import QSignalBlocker, QSize, Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QMenu, QSlider, QVBoxLayout, QWidget

from ..components import ArtworkLabel, IconButton
from ..components.visualizer import PlaybackVisualizer
from ..services import display_duration, duration_seconds, track_title, value


def _seconds(track: Any) -> int:
    return int(duration_seconds(track))


def _clock(seconds: float) -> str:
    total = max(0, int(seconds))
    return f"{total // 60}:{total % 60:02d}"


class PlaybackBar(QFrame):
    queueRequested = Signal()
    lyricsRequested = Signal()
    favoriteRequested = Signal(object)
    playlistRequested = Signal(object)
    metadataRequested = Signal(object)
    moreRequested = Signal(object)
    errorOccurred = Signal(str)
    positionUpdated = Signal(float)

    def __init__(self, playback_controller: Any, metadata_service: Any = None, parent=None):
        super().__init__(parent)
        self.setObjectName("PlaybackBar")
        self.controller = playback_controller
        self.metadata_service = metadata_service
        self.track: Any = None
        self.playing = False
        self.position = 0.0
        self.duration = 0.0
        self.shuffle = False
        self.repeat_mode = "off"
        self.muted = False
        self._text_color = "#F4F5F8"
        self._accent_color = "#8B7CFF"
        self._dragging = False
        root = QHBoxLayout(self)
        root.setContentsMargins(20, 10, 20, 10)
        root.setSpacing(16)
        left = QWidget()
        left.setMinimumWidth(220)
        left.setMaximumWidth(320)
        left_row = QHBoxLayout(left)
        left_row.setContentsMargins(0, 0, 0, 0)
        left_row.setSpacing(10)
        self.art = ArtworkLabel(48)
        self.art.setStyleSheet("background: #242630; border-radius: 7px; color: #A095FF;")
        self.title = QLabel("Nothing playing")
        self.title.setStyleSheet("font-weight: 650;")
        self.title.setMaximumWidth(190)
        self.title.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        self.artist = QLabel("Select a song")
        self.artist.setProperty("role", "secondary")
        self.artist.setMaximumWidth(190)
        self.info = QVBoxLayout()
        self.info.setSpacing(3)
        self.info.addWidget(self.title)
        self.info.addWidget(self.artist)
        left_row.addWidget(self.art)
        left_row.addLayout(self.info, 1)
        self.favorite = IconButton("heart", "Add to favorites", checkable=True)
        self.favorite.setFixedSize(32, 32)
        self.more = IconButton("more", "More track options")
        self.more.setFixedSize(32, 32)
        left_row.addWidget(self.favorite)
        left_row.addWidget(self.more)
        root.addWidget(left, 1)

        center = QWidget()
        center.setMinimumWidth(400)
        center_col = QVBoxLayout(center)
        center_col.setContentsMargins(0, 0, 0, 0)
        center_col.setSpacing(3)
        controls = QHBoxLayout()
        controls.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        controls.setSpacing(8)
        self.shuffle_button = IconButton("shuffle", "Shuffle", checkable=True)
        self.previous_button = IconButton("previous", "Previous track")
        self.play_button = IconButton("play", "Play", checkable=True)
        self.play_button.setFixedSize(42, 42)
        self.play_button.setStyleSheet("QToolButton { background: #8B7CFF; border-radius: 21px; } QToolButton:hover { background: #A095FF; }")
        self.play_button.setIconSize(QSize(20, 20))
        self.next_button = IconButton("next", "Next track")
        self.repeat_button = IconButton("repeat", "Repeat off")
        controls.addWidget(self.shuffle_button)
        controls.addWidget(self.previous_button)
        controls.addWidget(self.play_button)
        controls.addWidget(self.next_button)
        controls.addWidget(self.repeat_button)
        center_col.addLayout(controls)
        progress = QHBoxLayout()
        progress.setSpacing(8)
        self.current_time = QLabel("0:00")
        self.current_time.setProperty("role", "muted")
        self.current_time.setMinimumWidth(38)
        self.current_time.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.seek = QSlider(Qt.Orientation.Horizontal)
        self.seek.setRange(0, 1000)
        self.seek.setEnabled(False)
        self.total_time = QLabel("0:00")
        self.total_time.setProperty("role", "muted")
        self.total_time.setMinimumWidth(38)
        progress.addWidget(self.current_time)
        progress.addWidget(self.seek, 1)
        progress.addWidget(self.total_time)
        center_col.addLayout(progress)
        root.addWidget(center, 2)

        right = QWidget()
        right.setMinimumWidth(214)
        right_row = QHBoxLayout(right)
        right_row.setContentsMargins(0, 0, 0, 0)
        right_row.setSpacing(5)
        self.volume_icon = IconButton("volume", "Mute")
        self.volume_icon.setFixedSize(32, 32)
        self.volume = QSlider(Qt.Orientation.Horizontal)
        self.volume.setRange(0, 100)
        self.volume.setFixedWidth(96)
        self.visualizer = PlaybackVisualizer()
        right_row.addWidget(self.visualizer)
        self.queue = IconButton("queue", "Queue")
        self.lyrics = IconButton("lyrics", "Lyrics")
        right_row.addWidget(self.volume_icon)
        right_row.addWidget(self.volume)
        right_row.addWidget(self.queue)
        right_row.addWidget(self.lyrics)
        root.addWidget(right, 1)

        self.previous_button.clicked.connect(lambda: self._call("previous"))
        self.next_button.clicked.connect(lambda: self._call("next"))
        self.play_button.clicked.connect(lambda: self._call("toggle_play_pause"))
        self.shuffle_button.clicked.connect(self._toggle_shuffle)
        self.repeat_button.clicked.connect(self._cycle_repeat)
        self.volume.valueChanged.connect(self._set_volume)
        self.volume_icon.clicked.connect(self._toggle_mute)
        self.seek.sliderPressed.connect(self._seek_started)
        self.seek.sliderReleased.connect(self._seek_released)
        self.queue.clicked.connect(self.queueRequested)
        self.lyrics.clicked.connect(self.lyricsRequested)
        self.favorite.clicked.connect(lambda: self.favoriteRequested.emit(self.track) if self.track else None)
        self.more.clicked.connect(self._show_more)
        self.volume.setValue(int(float(value(playback_controller, "volume", "current_volume", default=0.7)) * 100))

    def _call(self, method: str, *args):
        function = getattr(self.controller, method, None) if self.controller else None
        if not callable(function):
            self.errorOccurred.emit(f"Playback action unavailable: {method}")
            return None
        try:
            return function(*args)
        except Exception as exc:
            self.errorOccurred.emit(str(exc))
            return None

    def set_track(self, track: Any) -> None:
        self.track = track
        self.art.set_track(track, self.metadata_service)
        self.title.setText(track_title(track) if track else "Nothing playing")
        self.title.setToolTip(self.title.text())
        self.artist.setText(str(value(track, "artist", "artists", default="Select a song") or "Select a song"))
        self.artist.setToolTip(self.artist.text())
        self.duration = float(_seconds(track))
        self.total_time.setText(display_duration(track) if track else "0:00")
        self.seek.setEnabled(self.duration > 0)
        if not self._dragging:
            self.set_position(0)
        self.favorite.setEnabled(bool(track))
        self.more.setEnabled(bool(track))

    def set_playback_state(self, playing: bool) -> None:
        self.playing = bool(playing)
        self.visualizer.set_playing(self.playing)
        from ..components.icons import icon
        self.play_button.setIcon(icon("pause" if self.playing else "play", "#FFFFFF"))
        self.play_button.setToolTip("Pause" if self.playing else "Play")

    def set_position(self, seconds: float, duration: float | None = None) -> None:
        if duration is not None and duration > 0:
            self.duration = float(duration)
            self.total_time.setText(_clock(self.duration))
        self.position = max(0.0, float(seconds or 0))
        self.current_time.setText(_clock(self.position))
        self.positionUpdated.emit(self.position)
        if not self._dragging and self.duration > 0:
            blocker = QSignalBlocker(self.seek)
            self.seek.setValue(round(self.position / self.duration * 1000))
            del blocker

    def set_volume(self, volume: float) -> None:
        blocker = QSignalBlocker(self.volume)
        self.volume.setValue(max(0, min(100, round(float(volume) * 100))))
        del blocker
        self.volume_icon.setIcon(self._icon("mute" if self.muted or volume <= 0 else "volume"))
        self.volume_icon.setToolTip("Unmute" if self.muted else "Mute")

    def set_muted(self, muted: bool) -> None:
        self.muted = bool(muted)
        self.volume_icon.setIcon(self._icon("mute" if self.muted else "volume"))
        self.volume_icon.setToolTip("Unmute" if self.muted else "Mute")

    def set_shuffle(self, enabled: bool) -> None:
        self.shuffle = bool(enabled)
        self.shuffle_button.setChecked(self.shuffle)
        self.shuffle_button.setProperty("active", self.shuffle)
        self.shuffle_button.setIcon(self._icon("shuffle", self.shuffle))
        self.shuffle_button.style().unpolish(self.shuffle_button)
        self.shuffle_button.style().polish(self.shuffle_button)

    @staticmethod
    def _normalize_repeat_mode(mode: Any) -> str:
        raw = getattr(mode, "value", mode)
        if isinstance(raw, int):
            return {0: "off", 1: "all", 2: "one"}.get(raw, "off")
        normalized = str(raw or "off").strip().lower()
        normalized = normalized.rsplit(".", 1)[-1]
        return {
            "none": "off", "0": "off",
            "1": "all", "repeat_all": "all",
            "2": "one", "repeat_one": "one", "track": "one",
        }.get(normalized, normalized if normalized in ("off", "all", "one") else "off")

    def set_repeat_mode(self, mode: str) -> None:
        self.repeat_mode = self._normalize_repeat_mode(mode)
        active = self.repeat_mode != "off"
        icon_name = "repeat_one" if self.repeat_mode == "one" else "repeat"
        tooltips = {
            "off": "Repeat off",
            "all": "Repeat all",
            "one": "Repeat current track",
        }
        self.repeat_button.setProperty("active", active)
        self.repeat_button.setIcon(self._icon(icon_name, active))
        self.repeat_button.setToolTip(tooltips[self.repeat_mode])
        self.repeat_button.setAccessibleName(tooltips[self.repeat_mode])
        self.repeat_button.style().unpolish(self.repeat_button)
        self.repeat_button.style().polish(self.repeat_button)

    def set_favorite(self, favorite: bool) -> None:
        self.favorite.setChecked(bool(favorite))
        self.favorite.setToolTip("Remove from favorites" if favorite else "Add to favorites")
        self.favorite.setProperty("active", bool(favorite))
        self.favorite.setIcon(self._icon("heart", bool(favorite)))
        self.favorite.style().unpolish(self.favorite)
        self.favorite.style().polish(self.favorite)

    def _icon(self, name: str, active: bool = False):
        from ..components.icons import icon
        return icon(name, self._accent_color if active else self._text_color)

    def set_animations_enabled(self, enabled: bool) -> None:
        self.visualizer.set_animations_enabled(enabled)

    def set_theme_colors(self, text_color: str, accent_color: str) -> None:
        self._text_color = text_color
        self._accent_color = accent_color
        self.visualizer.set_color(accent_color)
        self.set_shuffle(self.shuffle)
        self.set_repeat_mode(self.repeat_mode)
        self.set_favorite(self.favorite.isChecked())
        self.set_volume(self.volume.value() / 100)

    def _toggle_shuffle(self, enabled: bool) -> None:
        method = getattr(self.controller, "set_shuffle", None)
        if not callable(method):
            self.errorOccurred.emit("Shuffle control is not supported by the playback controller.")
            return
        try:
            method(enabled)
            self.set_shuffle(enabled)
        except Exception as exc:
            self.errorOccurred.emit(f"Couldn't change shuffle: {exc}")

    def _cycle_repeat(self, _checked: bool = False) -> None:
        controller_mode = value(self.controller, "repeat_mode", default=self.repeat_mode)
        current = self._normalize_repeat_mode(controller_mode)
        next_mode = {"off": "all", "all": "one", "one": "off"}[current]
        method = getattr(self.controller, "set_repeat_mode", None)
        if not callable(method):
            self.errorOccurred.emit("Repeat control is not supported by the playback controller.")
            self.set_repeat_mode(current)
            return
        try:
            method(next_mode)
            self.set_repeat_mode(next_mode)
        except Exception as exc:
            self.set_repeat_mode(current)
            self.errorOccurred.emit(f"Couldn't change repeat mode: {exc}")

    def _set_volume(self, value: int) -> None:
        method = getattr(self.controller, "set_volume", None)
        if not callable(method):
            self.errorOccurred.emit("Volume control is not supported by the playback controller.")
            return
        try:
            method(value / 100)
            self.set_volume(value / 100)
        except Exception as exc:
            self.errorOccurred.emit(f"Couldn't change volume: {exc}")

    def _toggle_mute(self) -> None:
        method = getattr(self.controller, "set_muted", None) if self.controller else None
        if callable(method):
            self._call("set_muted", not self.muted)
        else:
            current = self.volume.value()
            if current:
                self._last_volume = current
                self.volume.setValue(0)
            else:
                self.volume.setValue(getattr(self, "_last_volume", 70))

    def _seek_started(self) -> None:
        self._dragging = True

    def _seek_released(self) -> None:
        if self.duration > 0:
            seconds = self.seek.value() / 1000 * self.duration
            self._call("seek", seconds)
            self._dragging = False
            self.set_position(seconds)
        else:
            self._dragging = False

    def _show_more(self) -> None:
        if not self.track:
            return
        menu = QMenu(self)
        menu.addAction("Play next", lambda: self._call("play_next", self.track))
        menu.addAction("Add to queue", lambda: self._call("add_to_queue", self.track))
        menu.addSeparator()
        menu.addAction("Add to playlist…", lambda: self.playlistRequested.emit(self.track))
        menu.addAction("Track details…", lambda: self.metadataRequested.emit(self.track))
        menu.addAction("More options…", lambda: self.moreRequested.emit(self.track))
        menu.exec(self.more.mapToGlobal(self.more.rect().bottomLeft()))
