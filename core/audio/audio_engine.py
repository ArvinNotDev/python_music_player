"""Backend-neutral facade that normalizes audio backend events and controls."""

from __future__ import annotations

import math

from PySide6.QtCore import QObject, Signal

from .audio_backend import AudioBackend, QtMultimediaBackend, UnavailableAudioBackend


class AudioEngine(QObject):
    """Own the backend and forward normalized state and control signals."""

    state_changed = Signal(str)
    position_changed = Signal(int)
    duration_changed = Signal(int)
    seekable_changed = Signal(bool)
    media_status_changed = Signal(str)
    error_occurred = Signal(str)
    end_of_media = Signal()
    volume_changed = Signal(float)
    muted_changed = Signal(bool)

    def __init__(self, backend: AudioBackend | None = None, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._initialization_error: str | None = None
        if backend is None:
            try:
                backend = QtMultimediaBackend(self)
            except Exception as exc:
                self._initialization_error = str(exc) or repr(exc)
                backend = UnavailableAudioBackend(self._initialization_error, self)
        self._backend = backend
        if self._backend.parent() is None:
            self._backend.setParent(self)
        self._backend.state_changed.connect(self.state_changed)
        self._backend.position_changed.connect(self.position_changed)
        self._backend.duration_changed.connect(self.duration_changed)
        self._backend.seekable_changed.connect(self.seekable_changed)
        self._backend.media_status_changed.connect(self.media_status_changed)
        self._backend.error_occurred.connect(self.error_occurred)
        self._backend.end_of_media.connect(self.end_of_media)
        self._backend.volume_changed.connect(self.volume_changed)
        self._backend.muted_changed.connect(self.muted_changed)

    @property
    def backend(self) -> AudioBackend:
        """Return the backend for diagnostics or deterministic test doubles."""
        return self._backend

    @property
    def initialization_error(self) -> str | None:
        """Initialization failure text, if the production backend could not start."""
        return self._initialization_error

    @property
    def state(self) -> str:
        return self._backend.state

    @property
    def position(self) -> int:
        return max(0, int(self._backend.position))

    @property
    def duration(self) -> int:
        return max(0, int(self._backend.duration))

    @property
    def seekable(self) -> bool:
        return bool(self._backend.seekable)

    @property
    def media_status(self) -> str:
        return self._backend.media_status

    @property
    def volume(self) -> float:
        return self._backend.volume

    @property
    def is_muted(self) -> bool:
        return self._backend.is_muted

    def set_source(self, path: str) -> None:
        """Load a path through the backend without waiting for decoding."""
        self._backend.set_source(path)

    def clear_source(self) -> None:
        """Clear source when the backend supports it."""
        clear = getattr(self._backend, "clear_source", None)
        if callable(clear):
            clear()

    def play(self) -> None:
        """Request playback; actual playing state arrives asynchronously."""
        self._backend.play()

    def pause(self) -> None:
        """Request a pause."""
        self._backend.pause()

    def stop(self) -> None:
        """Request a stop."""
        self._backend.stop()

    def seek(self, position_ms: int) -> None:
        """Seek to a non-negative millisecond position if the source permits."""
        self._backend.seek(max(0, int(position_ms)))

    def set_volume(self, volume: float) -> float:
        """Clamp and set linear output volume; return the stored value."""
        value = float(volume)
        if math.isnan(value):
            value = 0.0
        value = max(0.0, min(value, 1.0))
        self._backend.set_volume(value)
        return value

    def set_muted(self, muted: bool) -> None:
        """Set mute independently of the stored volume."""
        self._backend.set_muted(bool(muted))

    def shutdown(self) -> None:
        """Stop and release backend resources; safe to call more than once."""
        self._backend.shutdown()
