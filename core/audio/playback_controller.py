"""UI-independent playback orchestration, navigation, and audio controls."""

from __future__ import annotations

import math
import os
import random
from typing import Iterable

from PySide6.QtCore import QObject, Signal

from .audio_engine import AudioEngine
from .playback_queue import PlaybackQueue, QueueEntry
from .playback_state import PlaybackState
from .repeat_mode import RepeatMode
from .track_protocol import TrackLike


class PlaybackController(QObject):
    """Stable public playback API for a desktop player UI.

    The controller owns queue navigation and policy; callers never need to
    access a ``QMediaPlayer`` or ``QAudioOutput``. All public times are ms and
    volume is linear in the range 0.0 through 1.0.
    """

    current_track_changed = Signal(object)
    current_queue_index_changed = Signal(object)
    playback_state_changed = Signal(str)
    position_changed = Signal(int)
    duration_changed = Signal(int)
    volume_changed = Signal(float)
    muted_changed = Signal(bool)
    queue_changed = Signal(object)
    shuffle_changed = Signal(bool)
    repeat_mode_changed = Signal(str)
    error_occurred = Signal(str)

    def __init__(
        self,
        engine: AudioEngine | None = None,
        *,
        previous_restart_threshold_ms: int = 3_000,
        random_seed: int | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._engine = engine or AudioEngine(parent=self)
        if self._engine.parent() is None:
            self._engine.setParent(self)
        self._queue = PlaybackQueue(self)
        self._state = PlaybackState.STOPPED
        self._last_current_queue_index: int | None = None
        self._position = 0
        self._duration = 0
        self._volume = self._engine.volume
        self._is_muted = self._engine.is_muted
        self._shuffle = False
        self._repeat_mode = RepeatMode.OFF
        self._restart_threshold = max(0, int(previous_restart_threshold_ms))
        self._random = random.Random(random_seed)
        self._shuffle_history: list[int] = []
        self._shuffle_cursor = -1
        self._shuffle_bag: list[int] = []
        self._shuffle_priority: list[int] = []
        self._pending_seek: int | None = None
        self._loading = False
        self._error_latched = False
        self._closed = False

        self._queue.changed.connect(self._on_queue_changed)
        self._engine.state_changed.connect(self._on_backend_state)
        self._engine.position_changed.connect(self._on_backend_position)
        self._engine.duration_changed.connect(self._on_backend_duration)
        self._engine.seekable_changed.connect(self._on_backend_seekable)
        self._engine.media_status_changed.connect(self._on_backend_media_status)
        self._engine.error_occurred.connect(self._on_backend_error)
        self._engine.end_of_media.connect(self._on_end_of_media)
        self._engine.volume_changed.connect(self._on_backend_volume)
        self._engine.muted_changed.connect(self._on_backend_muted)

    @property
    def current_track(self) -> TrackLike | None:
        """The active track, including one removed from the upcoming queue."""
        return self._queue.current_track

    @property
    def current_queue_index(self) -> int | None:
        """Active queue row index, or ``None`` for a detached current track."""
        return self._queue.current_index

    @property
    def current_state(self) -> str:
        """Current lifecycle state as ``stopped``, ``loading``, etc."""
        return self._state.value

    @property
    def position(self) -> int:
        """Current playback position in milliseconds."""
        return self._position

    @property
    def duration(self) -> int:
        """Current track duration in milliseconds, or zero if unknown."""
        return self._duration

    @property
    def volume(self) -> float:
        """Current linear output volume in the range 0.0 through 1.0."""
        return self._volume

    @property
    def is_muted(self) -> bool:
        """Whether the output is muted without changing ``volume``."""
        return self._is_muted

    @property
    def is_playing(self) -> bool:
        """Whether the backend has confirmed active playback."""
        return self._state is PlaybackState.PLAYING

    @property
    def is_paused(self) -> bool:
        """Whether the backend has confirmed paused playback."""
        return self._state is PlaybackState.PAUSED

    @property
    def queue(self) -> list[TrackLike]:
        """A copy of the queue's ordered track list."""
        return self._queue.tracks

    @property
    def shuffle_enabled(self) -> bool:
        """Whether randomized next-track navigation is enabled."""
        return self._shuffle

    @property
    def repeat_mode(self) -> str:
        """Current repeat mode: ``off``, ``all``, or ``one``."""
        return self._repeat_mode.value

    def play_track(self, track: TrackLike) -> None:
        """Replace the queue with ``track`` and request its playback."""
        self.play_queue([track], start_index=0)

    def play_queue(self, tracks: Iterable[TrackLike], start_index: int = 0) -> None:
        """Replace the queue and request the selected track's playback."""
        materialized = list(tracks)
        if not materialized:
            if start_index != 0:
                raise IndexError("start_index must be 0 for an empty queue")
            old_track = self.current_track
            self._queue.replace([], 0)
            self._reset_shuffle()
            self.stop()
            if old_track is not None:
                self.current_track_changed.emit(None)
            self._set_duration(0)
            return
        old_track = self.current_track
        entry = self._queue.replace(materialized, start_index)
        assert entry is not None
        self._reset_shuffle()
        if not self._same_track(old_track, entry.track):
            self.current_track_changed.emit(entry.track)
        self._start_entry(entry)

    def play(self) -> None:
        """Start, resume, or restart the selected track."""
        if self._closed:
            return
        if self.current_track is None:
            if self._queue.entries:
                self._start_entry(self._queue.entries[0])
            return
        if self._state is PlaybackState.PLAYING:
            return
        if self._state is PlaybackState.ERROR or self._state is PlaybackState.STOPPED:
            entry = self._queue.current_entry
            if entry is not None:
                self._start_entry(entry)
            return
        self._engine.play()

    def pause(self) -> None:
        """Request a pause when a track is loading or playing."""
        if self._state in (PlaybackState.LOADING, PlaybackState.PLAYING):
            self._engine.pause()

    def toggle_play_pause(self) -> None:
        """Pause confirmed playback or start/resume otherwise."""
        if self._state in (PlaybackState.PLAYING, PlaybackState.LOADING):
            self.pause()
        else:
            self.play()

    def stop(self) -> None:
        """Stop playback, retaining the current track and queue selection."""
        if self._closed:
            return
        self._loading = False
        self._error_latched = False
        self._pending_seek = None
        self._set_state(PlaybackState.STOPPED)
        self._engine.stop()
        self._set_position(0)

    def next(self) -> None:
        """Move to the next queue entry, respecting shuffle and repeat-all."""
        if self.current_track is None:
            if self._queue.entries:
                self._start_entry(self._queue.entries[0])
            return
        entry = self._next_entry()
        if entry is None:
            self.stop()
        elif entry.entry_id == self._queue.current_entry_id:
            self._restart_current()
        else:
            self._start_entry(entry)

    def previous(self) -> None:
        """Restart after the configured threshold; otherwise navigate back."""
        if self.current_track is None:
            return
        if self._position > self._restart_threshold:
            self.seek(0)
            return
        entry = self._previous_entry()
        if entry is None:
            self.seek(0)
        elif entry.entry_id == self._queue.current_entry_id:
            self._restart_current()
        else:
            self._start_entry(entry)

    def seek(self, position_ms: int) -> None:
        """Seek to a non-negative millisecond position.

        If a source is still loading, the target is held until the backend says
        that seeking is available. A known duration clamps the target.
        """
        if self.current_track is None:
            return
        target = max(0, int(position_ms))
        if self._duration > 0:
            target = min(target, self._duration)
        if self._engine.seekable:
            self._pending_seek = None
            self._engine.seek(target)
        elif self._state is PlaybackState.LOADING:
            self._pending_seek = target

    def set_volume(self, volume: float) -> None:
        """Set linear output volume, clamped to the inclusive range 0–1."""
        value = float(volume)
        if math.isnan(value):
            value = 0.0
        value = max(0.0, min(value, 1.0))
        self._engine.set_volume(value)
        self._set_volume(self._engine.volume)

    def set_muted(self, muted: bool) -> None:
        """Mute or unmute while preserving the current volume value."""
        self._engine.set_muted(bool(muted))
        self._set_muted(self._engine.is_muted)

    def set_shuffle(self, enabled: bool) -> None:
        """Enable or disable shuffle without restarting current playback."""
        value = bool(enabled)
        if value == self._shuffle:
            return
        self._shuffle = value
        if value:
            self._reset_shuffle()
        else:
            self._shuffle_history.clear()
            self._shuffle_cursor = -1
            self._shuffle_bag.clear()
            self._shuffle_priority.clear()
        self.shuffle_changed.emit(value)

    def set_repeat_mode(self, mode: RepeatMode | str) -> None:
        """Set repeat policy independently of shuffle."""
        value = RepeatMode.coerce(mode)
        if value is self._repeat_mode:
            return
        self._repeat_mode = value
        self.repeat_mode_changed.emit(value.value)

    def add_to_queue(self, track: TrackLike) -> None:
        """Append one occurrence to the queue; duplicate tracks are allowed."""
        entry = self._queue.append(track)
        if self._shuffle:
            self._shuffle_bag.append(entry.entry_id)

    def play_next(self, track: TrackLike) -> None:
        """Insert one occurrence immediately after the current entry."""
        entry = self._queue.insert_next(track)
        if self._shuffle:
            future = self._shuffle_history[self._shuffle_cursor + 1 :]
            self._shuffle_history = self._shuffle_history[: self._shuffle_cursor + 1]
            self._shuffle_priority = [
                entry.entry_id,
                *future,
                *self._shuffle_priority,
                *self._shuffle_bag,
            ]
            self._shuffle_bag.clear()

    def remove_from_queue(self, index: int) -> None:
        """Remove a queue row without interrupting it if it is currently active."""
        removed = self._queue.remove(index)
        if self._shuffle and removed.entry_id != self._queue.current_entry_id:
            self._remove_shuffle_id(removed.entry_id)

    def move_queue_item(self, source_index: int, destination_index: int) -> None:
        """Move a queue row to its final index without changing active entry."""
        self._queue.move(source_index, destination_index)

    def refresh_track(self, track: TrackLike) -> bool:
        """Update matching Track models without interrupting current playback."""
        if not self._queue.refresh_track(track, self._same_track):
            return False
        current = self.current_track
        if current is not None and self._same_track(current, track):
            self.current_track_changed.emit(current)
        self.queue_changed.emit(self._queue.tracks)
        return True

    def clear_queue(self) -> None:
        """Remove upcoming rows while letting the selected track finish."""
        current_id = self._queue.current_entry_id
        self._queue.clear()
        if self._shuffle:
            self._shuffle_bag.clear()
            self._shuffle_priority.clear()
            self._shuffle_history = [current_id] if current_id is not None else []
            self._shuffle_cursor = 0 if current_id is not None else -1

    def shutdown(self) -> None:
        """Stop playback and release audio resources. Safe to call repeatedly."""
        if self._closed:
            return
        self._closed = True
        self._loading = False
        self._pending_seek = None
        self._engine.shutdown()
        self._set_position(0)
        self._set_state(PlaybackState.STOPPED)

    def _start_entry(self, entry: QueueEntry) -> None:
        if self._closed:
            return
        previous_track = self._queue.current_track
        selected = self._queue.set_current(entry.entry_id)
        if selected is None:
            return
        self._emit_current_queue_index_if_changed()
        self._sync_shuffle_selection(selected)
        if not self._same_track(previous_track, selected.track):
            self.current_track_changed.emit(selected.track)
        self._loading = True
        self._error_latched = False
        self._pending_seek = None
        self._set_position(0)
        duration = self._track_duration(selected.track)
        self._set_duration(duration)
        self._set_state(PlaybackState.LOADING)

        try:
            path = os.fspath(selected.track.path)
            if not path or not os.path.isfile(path):
                raise FileNotFoundError(f"Audio file not found: {path or '<empty path>'}")
            self._engine.stop()
            self._engine.set_source(path)
            self._engine.play()
        except (OSError, TypeError, ValueError, RuntimeError) as exc:
            self._fail(str(exc) or "Unable to load the selected audio file.")

    def _next_entry(self) -> QueueEntry | None:
        if not self._shuffle:
            return self._queue.next_ordered(repeat_all=self._repeat_mode is RepeatMode.ALL)
        while self._shuffle_cursor + 1 < len(self._shuffle_history):
            self._shuffle_cursor += 1
            entry = self._queue.entry_by_id(self._shuffle_history[self._shuffle_cursor])
            if entry is not None and (self._queue.contains(entry.entry_id) or entry.entry_id == self._queue.current_entry_id):
                return entry
        while self._shuffle_priority:
            entry_id = self._shuffle_priority.pop(0)
            entry = self._queue.entry_by_id(entry_id)
            if entry is not None and self._queue.contains(entry_id):
                return self._record_shuffle_entry(entry)
        while self._shuffle_bag:
            entry_id = self._shuffle_bag.pop(0)
            entry = self._queue.entry_by_id(entry_id)
            if entry is not None and self._queue.contains(entry_id):
                return self._record_shuffle_entry(entry)
        if self._repeat_mode is not RepeatMode.ALL:
            return None
        candidates = [
            entry for entry in self._queue.entries
            if entry.entry_id != self._queue.current_entry_id
        ]
        if not candidates:
            return self._queue.current_entry
        self._random.shuffle(candidates)
        previous_id = self._shuffle_history[self._shuffle_cursor - 1] if self._shuffle_cursor > 0 else None
        if len(candidates) > 1 and candidates[0].entry_id == previous_id:
            candidates[0], candidates[1] = candidates[1], candidates[0]
        self._shuffle_bag = [entry.entry_id for entry in candidates]
        return self._record_shuffle_entry(self._queue.entry_by_id(self._shuffle_bag.pop(0)))

    def _previous_entry(self) -> QueueEntry | None:
        if not self._shuffle:
            return self._queue.previous_ordered(repeat_all=self._repeat_mode is RepeatMode.ALL)
        while self._shuffle_cursor > 0:
            self._shuffle_cursor -= 1
            entry = self._queue.entry_by_id(self._shuffle_history[self._shuffle_cursor])
            if entry is not None and (self._queue.contains(entry.entry_id) or entry.entry_id == self._queue.current_entry_id):
                return entry
        if self._repeat_mode is RepeatMode.ALL and self._queue.entries:
            return self._queue.entries[-1]
        return None

    def _record_shuffle_entry(self, entry: QueueEntry | None) -> QueueEntry | None:
        if entry is None:
            return None
        self._shuffle_history = [
            entry_id for entry_id in self._shuffle_history
            if self._queue.contains(entry_id) or entry_id == self._queue.current_entry_id
        ][: self._shuffle_cursor + 1]
        self._shuffle_cursor = len(self._shuffle_history) - 1
        self._shuffle_history.append(entry.entry_id)
        self._shuffle_cursor += 1
        return entry

    def _restart_current(self) -> None:
        entry = self._queue.current_entry
        if entry is None:
            return
        self._loading = True
        self._pending_seek = None
        self._set_position(0)
        self._set_state(PlaybackState.LOADING)
        if self._engine.seekable:
            self._engine.seek(0)
            self._engine.play()
        else:
            self._start_entry(entry)

    def _on_end_of_media(self) -> None:
        if self._closed or self._error_latched:
            return
        if self._repeat_mode is RepeatMode.ONE:
            self._restart_current()
            return
        entry = self._next_entry()
        if entry is None:
            self._set_position(self._duration)
            self._loading = False
            self._set_state(PlaybackState.STOPPED)
        elif entry.entry_id == self._queue.current_entry_id:
            self._restart_current()
        else:
            self._start_entry(entry)

    def _on_backend_state(self, state: str) -> None:
        if self._closed or self._error_latched:
            return
        normalized = str(state).strip().lower()
        if normalized == "playing":
            self._loading = False
            self._set_state(PlaybackState.PLAYING)
        elif normalized == "paused":
            self._loading = False
            self._set_state(PlaybackState.PAUSED)
        elif normalized == "stopped":
            if self._loading or self._engine.media_status == "endofmedia":
                return
            if self._state in (PlaybackState.PLAYING, PlaybackState.PAUSED):
                self._fail("Playback stopped unexpectedly.")
            else:
                self._set_state(PlaybackState.STOPPED)

    def _on_queue_changed(self, tracks: object) -> None:
        self.queue_changed.emit(tracks)
        self._emit_current_queue_index_if_changed()

    def _emit_current_queue_index_if_changed(self) -> None:
        index = self._queue.current_index
        if index == self._last_current_queue_index:
            return
        self._last_current_queue_index = index
        self.current_queue_index_changed.emit(index)

    def _on_backend_position(self, position: int) -> None:
        self._set_position(max(0, int(position)))

    def _on_backend_duration(self, duration: int) -> None:
        # Qt reports 0 while replacing a source; retain library duration then.
        value = max(0, int(duration))
        if value > 0 or self.current_track is None:
            self._set_duration(value)
        self._apply_pending_seek()

    def _on_backend_seekable(self, seekable: bool) -> None:
        if seekable:
            self._apply_pending_seek()

    def _on_backend_media_status(self, status: str) -> None:
        if status.strip().lower() == "invalidmedia":
            self._fail("The selected file is invalid or its audio format is unsupported.")
        elif status.strip().lower() in ("nomedia", "endofmedia"):
            self._pending_seek = None

    def _on_backend_error(self, message: str) -> None:
        self._fail(message or "The audio backend failed to play this file.")

    def _on_backend_volume(self, value: float) -> None:
        self._set_volume(value)

    def _on_backend_muted(self, value: bool) -> None:
        self._set_muted(value)

    def _apply_pending_seek(self) -> None:
        if self._pending_seek is None or not self._engine.seekable:
            return
        position = self._pending_seek
        self._pending_seek = None
        if self._duration > 0:
            position = min(position, self._duration)
        self._engine.seek(position)

    def _fail(self, message: str) -> None:
        if self._error_latched or self._closed:
            return
        self._error_latched = True
        self._loading = False
        self._pending_seek = None
        self._engine.stop()
        self._engine.clear_source()
        self._set_position(0)
        self._set_duration(0)
        self._set_state(PlaybackState.ERROR)
        self.error_occurred.emit(message.strip() or "Unknown audio playback error.")

    def _reset_shuffle(self) -> None:
        self._shuffle_history.clear()
        self._shuffle_priority.clear()
        current_id = self._queue.current_entry_id
        self._shuffle_history = [current_id] if self._shuffle and current_id is not None else []
        self._shuffle_cursor = len(self._shuffle_history) - 1
        self._shuffle_bag = [entry.entry_id for entry in self._queue.entries if entry.entry_id != current_id]
        if self._shuffle:
            self._random.shuffle(self._shuffle_bag)
        else:
            self._shuffle_bag.clear()

    def _sync_shuffle_selection(self, entry: QueueEntry) -> None:
        """Keep shuffle history aligned when a track is selected externally."""
        if not self._shuffle:
            return
        if self._shuffle_cursor >= 0 and self._shuffle_history[self._shuffle_cursor] == entry.entry_id:
            self._shuffle_bag = [value for value in self._shuffle_bag if value != entry.entry_id]
            self._shuffle_priority = [value for value in self._shuffle_priority if value != entry.entry_id]
            return
        self._shuffle_history = self._shuffle_history[: self._shuffle_cursor + 1]
        self._shuffle_history = [
            value for value in self._shuffle_history
            if self._queue.contains(value) or value == self._queue.current_entry_id
        ]
        self._shuffle_history.append(entry.entry_id)
        self._shuffle_cursor = len(self._shuffle_history) - 1
        self._shuffle_bag = [value for value in self._shuffle_bag if value != entry.entry_id]
        self._shuffle_priority = [value for value in self._shuffle_priority if value != entry.entry_id]

    def _remove_shuffle_id(self, entry_id: int) -> None:
        current_id = self._queue.current_entry_id
        self._shuffle_bag = [value for value in self._shuffle_bag if value != entry_id]
        self._shuffle_priority = [value for value in self._shuffle_priority if value != entry_id]
        self._shuffle_history = [
            value for value in self._shuffle_history
            if value != entry_id or value == current_id
        ]
        if current_id in self._shuffle_history:
            self._shuffle_cursor = self._shuffle_history.index(current_id)
        else:
            self._shuffle_cursor = min(self._shuffle_cursor, len(self._shuffle_history) - 1)

    def _set_state(self, state: PlaybackState) -> None:
        if state is self._state:
            return
        self._state = state
        self.playback_state_changed.emit(state.value)

    def _set_position(self, position: int) -> None:
        value = max(0, int(position))
        if self._duration > 0:
            value = min(value, self._duration)
        if value == self._position:
            return
        self._position = value
        self.position_changed.emit(value)

    def _set_duration(self, duration: int) -> None:
        value = max(0, int(duration))
        if value == self._duration:
            return
        self._duration = value
        if self._duration > 0 and self._position > self._duration:
            self._set_position(self._duration)
        self.duration_changed.emit(value)

    def _set_volume(self, volume: float) -> None:
        value = float(volume)
        if math.isnan(value):
            value = 0.0
        value = max(0.0, min(value, 1.0))
        if math.isclose(value, self._volume, abs_tol=1e-6):
            return
        self._volume = value
        self.volume_changed.emit(value)

    def _set_muted(self, muted: bool) -> None:
        value = bool(muted)
        if value == self._is_muted:
            return
        self._is_muted = value
        self.muted_changed.emit(value)

    @staticmethod
    def _track_duration(track: TrackLike) -> int:
        try:
            return max(0, int(track.duration_ms or 0))
        except (AttributeError, TypeError, ValueError):
            return 0

    @staticmethod
    def _same_track(first: TrackLike | None, second: TrackLike | None) -> bool:
        if first is None or second is None:
            return first is second
        if first is second:
            return True
        try:
            return first.id == second.id
        except AttributeError:
            return False
