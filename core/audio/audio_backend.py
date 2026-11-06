"""Low-level backend contract and the Qt Multimedia implementation."""

from __future__ import annotations

import os

from PySide6.QtCore import QObject, QUrl, Signal
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer


class AudioBackend(QObject):
    """Signals and commands required by the playback engine."""

    state_changed = Signal(str)
    position_changed = Signal(int)
    duration_changed = Signal(int)
    seekable_changed = Signal(bool)
    media_status_changed = Signal(str)
    error_occurred = Signal(str)
    end_of_media = Signal()
    volume_changed = Signal(float)
    muted_changed = Signal(bool)

    @property
    def state(self) -> str:
        """Current backend state: stopped, playing, or paused."""
        raise NotImplementedError

    @property
    def position(self) -> int:
        """Current position in milliseconds."""
        raise NotImplementedError

    @property
    def duration(self) -> int:
        """Current duration in milliseconds."""
        raise NotImplementedError

    @property
    def seekable(self) -> bool:
        """Whether the current source can be sought at this moment."""
        raise NotImplementedError

    @property
    def media_status(self) -> str:
        """Normalized current media status."""
        raise NotImplementedError

    @property
    def volume(self) -> float:
        """Output volume in the range 0.0 to 1.0."""
        raise NotImplementedError

    @property
    def is_muted(self) -> bool:
        """Whether the output is muted."""
        raise NotImplementedError

    def set_source(self, path: str) -> None:
        """Load a local media path without blocking the caller."""
        raise NotImplementedError

    def play(self) -> None:
        """Ask the backend to start or resume playback."""
        raise NotImplementedError

    def pause(self) -> None:
        """Ask the backend to pause playback."""
        raise NotImplementedError

    def stop(self) -> None:
        """Stop playback."""
        raise NotImplementedError

    def seek(self, position_ms: int) -> None:
        """Seek to a position in milliseconds when supported."""
        raise NotImplementedError

    def set_volume(self, volume: float) -> None:
        """Set output volume in the range 0.0 to 1.0."""
        raise NotImplementedError

    def set_muted(self, muted: bool) -> None:
        """Set mute without changing the saved volume level."""
        raise NotImplementedError

    def shutdown(self) -> None:
        """Release backend playback resources."""
        raise NotImplementedError


class UnavailableAudioBackend(AudioBackend):
    """Fail-safe backend used when Qt Multimedia cannot initialize."""

    def __init__(self, message: str, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._message = message
        self._volume = 1.0
        self._muted = False

    @property
    def state(self) -> str:
        return "stopped"

    @property
    def position(self) -> int:
        return 0

    @property
    def duration(self) -> int:
        return 0

    @property
    def seekable(self) -> bool:
        return False

    @property
    def media_status(self) -> str:
        return "nomedia"

    @property
    def volume(self) -> float:
        return self._volume

    @property
    def is_muted(self) -> bool:
        return self._muted

    def set_source(self, path: str) -> None:
        self.error_occurred.emit(f"Qt Multimedia could not initialize: {self._message}")

    def play(self) -> None:
        return

    def pause(self) -> None:
        return

    def stop(self) -> None:
        return

    def seek(self, position_ms: int) -> None:
        return

    def set_volume(self, volume: float) -> None:
        value = max(0.0, min(float(volume), 1.0))
        if value == self._volume:
            return
        self._volume = value
        self.volume_changed.emit(self._volume)

    def set_muted(self, muted: bool) -> None:
        value = bool(muted)
        if value == self._muted:
            return
        self._muted = value
        self.muted_changed.emit(self._muted)

    def shutdown(self) -> None:
        return


class QtMultimediaBackend(AudioBackend):
    """Single-player implementation backed by ``QMediaPlayer``/``QAudioOutput``."""

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._closed = False
        self._player = QMediaPlayer(self)
        self._output = QAudioOutput(self)
        self._player.setAudioOutput(self._output)
        self._player.playbackStateChanged.connect(self._on_playback_state_changed)
        self._player.positionChanged.connect(self._on_position_changed)
        self._player.durationChanged.connect(self._on_duration_changed)
        self._player.seekableChanged.connect(self._on_seekable_changed)
        self._player.mediaStatusChanged.connect(self._on_media_status_changed)
        self._player.errorOccurred.connect(self._on_error)
        self._output.volumeChanged.connect(self._on_volume_changed)
        self._output.mutedChanged.connect(self._on_muted_changed)

    @property
    def state(self) -> str:
        return self._state_name(self._player.playbackState())

    @property
    def position(self) -> int:
        return int(self._player.position())

    @property
    def duration(self) -> int:
        return int(self._player.duration())

    @property
    def seekable(self) -> bool:
        return bool(self._player.isSeekable())

    @property
    def media_status(self) -> str:
        return self._status_name(self._player.mediaStatus())

    @property
    def volume(self) -> float:
        return float(self._output.volume())

    @property
    def is_muted(self) -> bool:
        return bool(self._output.isMuted())

    @property
    def player(self) -> QMediaPlayer:
        """Return the player for diagnostics only; UI code should use controller."""
        return self._player

    @property
    def output(self) -> QAudioOutput:
        """Return the output for diagnostics only; UI code should use controller."""
        return self._output

    def set_source(self, path: str) -> None:
        if self._closed:
            return
        self._player.setSource(QUrl.fromLocalFile(os.path.abspath(path)))

    def clear_source(self) -> None:
        """Clear the active source after an immediate path validation failure."""
        if not self._closed:
            self._player.setSource(QUrl())

    def play(self) -> None:
        if not self._closed:
            self._player.play()

    def pause(self) -> None:
        if not self._closed:
            self._player.pause()

    def stop(self) -> None:
        if not self._closed:
            self._player.stop()

    def seek(self, position_ms: int) -> None:
        if not self._closed and self.seekable:
            self._player.setPosition(max(0, min(int(position_ms), self.duration or int(position_ms))))

    def set_volume(self, volume: float) -> None:
        if not self._closed:
            self._output.setVolume(max(0.0, min(float(volume), 1.0)))

    def set_muted(self, muted: bool) -> None:
        if not self._closed:
            self._output.setMuted(bool(muted))

    def shutdown(self) -> None:
        """Stop playback and disconnect owned Qt signals exactly once."""
        if self._closed:
            return
        self._closed = True
        self._player.stop()
        for signal, slot in (
            (self._player.playbackStateChanged, self._on_playback_state_changed),
            (self._player.positionChanged, self._on_position_changed),
            (self._player.durationChanged, self._on_duration_changed),
            (self._player.seekableChanged, self._on_seekable_changed),
            (self._player.mediaStatusChanged, self._on_media_status_changed),
            (self._player.errorOccurred, self._on_error),
            (self._output.volumeChanged, self._on_volume_changed),
            (self._output.mutedChanged, self._on_muted_changed),
        ):
            try:
                signal.disconnect(slot)
            except (RuntimeError, TypeError):
                pass
        self._player.setSource(QUrl())

    @staticmethod
    def _state_name(value: object) -> str:
        name = getattr(value, "name", str(value))
        return str(name).removesuffix("State").lower()

    @staticmethod
    def _status_name(value: object) -> str:
        return str(getattr(value, "name", value)).lower()

    def _on_playback_state_changed(self, state: QMediaPlayer.PlaybackState) -> None:
        self.state_changed.emit(self._state_name(state))

    def _on_position_changed(self, position: int) -> None:
        self.position_changed.emit(int(position))

    def _on_duration_changed(self, duration: int) -> None:
        self.duration_changed.emit(int(duration))

    def _on_volume_changed(self, volume: float) -> None:
        self.volume_changed.emit(float(volume))

    def _on_muted_changed(self, muted: bool) -> None:
        self.muted_changed.emit(bool(muted))

    def _on_seekable_changed(self, seekable: bool) -> None:
        self.seekable_changed.emit(bool(seekable))

    def _on_media_status_changed(self, status: QMediaPlayer.MediaStatus) -> None:
        name = self._status_name(status)
        self.media_status_changed.emit(name)
        if name == "endofmedia":
            self.end_of_media.emit()
        elif name == "invalidmedia":
            message = self._player.errorString().strip() or "The media file is invalid or unsupported."
            self.error_occurred.emit(message)

    def _on_error(self, error: QMediaPlayer.Error, message: str) -> None:
        if error != QMediaPlayer.Error.NoError:
            self.error_occurred.emit(str(message).strip() or f"Audio backend error: {error}")
