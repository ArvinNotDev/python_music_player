"""Stable-entry queue storage, independent of playback and shuffle policy."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import count
from typing import Callable, Iterable

from PySide6.QtCore import QObject, Signal

from .track_protocol import TrackLike


@dataclass(frozen=True, slots=True)
class QueueEntry:
    """One queue occurrence. Duplicate tracks get distinct entry IDs."""

    entry_id: int
    track: TrackLike


class PlaybackQueue(QObject):
    """Ordered track queue with stable current-entry identity.

    The active track is retained when its queue row is removed or the upcoming
    queue is cleared. It then plays as a detached current entry until another
    queue entry is selected. Queue operations emit ``changed`` only when the
    ordered contents change.
    """

    changed = Signal(object)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._entries: list[QueueEntry] = []
        self._current: QueueEntry | None = None
        self._detached_next_id: int | None = None
        self._ids = count(1)
        self._archive: dict[int, QueueEntry] = {}

    @property
    def entries(self) -> tuple[QueueEntry, ...]:
        """Return an immutable snapshot of ordered queue entries."""
        return tuple(self._entries)

    @property
    def tracks(self) -> list[TrackLike]:
        """Return a new list containing the ordered track objects."""
        return [entry.track for entry in self._entries]

    @property
    def current_entry(self) -> QueueEntry | None:
        """Return the active queue occurrence, if one has been selected."""
        return self._current

    @property
    def current_entry_id(self) -> int | None:
        """Return the stable identity of the active queue occurrence."""
        return self._current.entry_id if self._current is not None else None

    @property
    def current_track(self) -> TrackLike | None:
        """Return the active track, including a detached current track."""
        return self._current.track if self._current is not None else None

    @property
    def current_index(self) -> int | None:
        """Return the active row index, or ``None`` if it was removed."""
        if self._current is None:
            return None
        for index, entry in enumerate(self._entries):
            if entry.entry_id == self._current.entry_id:
                return index
        return None

    @property
    def detached_next_id(self) -> int | None:
        """Return the row at the boundary after a removed current entry."""
        return self._detached_next_id

    def entry_at(self, index: int) -> QueueEntry:
        """Return the entry at ``index``; raise ``IndexError`` if invalid."""
        return self._entries[index]

    def entry_by_id(self, entry_id: int) -> QueueEntry | None:
        """Find a queued entry or the currently active detached occurrence."""
        return self._archive.get(entry_id)

    def contains(self, entry_id: int) -> bool:
        """Return whether an entry ID is currently present in the queue."""
        return any(entry.entry_id == entry_id for entry in self._entries)

    def ids(self) -> tuple[int, ...]:
        """Return stable IDs in the queue's current ordered sequence."""
        return tuple(entry.entry_id for entry in self._entries)

    def replace(self, tracks: Iterable[TrackLike], start_index: int = 0) -> QueueEntry | None:
        """Replace queue contents and select ``start_index`` as current.

        An empty queue only accepts ``start_index=0``. For a non-empty queue,
        an out-of-range index raises ``IndexError`` without changing contents.
        """
        materialized = list(tracks)
        if not materialized:
            if start_index != 0:
                raise IndexError("start_index must be 0 for an empty queue")
            changed = bool(self._entries)
            self._entries.clear()
            self._current = None
            self._detached_next_id = None
            self._archive.clear()
            if changed:
                self._emit_changed()
            return None
        if start_index < 0 or start_index >= len(materialized):
            raise IndexError("start_index is outside the queue")
        entries = [self._new_entry(track) for track in materialized]
        self._entries = entries
        self._current = entries[start_index]
        self._archive = {entry.entry_id: entry for entry in entries}
        self._detached_next_id = None
        self._emit_changed()
        return self._current

    def append(self, track: TrackLike) -> QueueEntry:
        """Append one occurrence and return its stable queue entry."""
        entry = self._new_entry(track)
        self._entries.append(entry)
        self._emit_changed()
        return entry

    def insert_next(self, track: TrackLike) -> QueueEntry:
        """Insert one occurrence directly after current, or at index zero."""
        entry = self._new_entry(track)
        current_index = self.current_index
        if current_index is not None:
            insert_index = current_index + 1
        elif self._current is not None:
            insert_index = self._index_of(self._detached_next_id) if self._detached_next_id is not None else len(self._entries)
        elif self._detached_next_id is not None:
            insert_index = self._index_of(self._detached_next_id)
        else:
            insert_index = 0
        self._entries.insert(insert_index, entry)
        if self._current is not None and self.current_index is None:
            # The inserted row is now the next item at the detached boundary.
            self._detached_next_id = entry.entry_id
        self._emit_changed()
        return entry

    def set_current(self, entry_id: int | None) -> QueueEntry | None:
        """Select a queued or archived entry without altering queue order."""
        if entry_id is None:
            if self._current is not None and not self.contains(self._current.entry_id):
                self._archive.pop(self._current.entry_id, None)
            self._current = None
            self._detached_next_id = None
            return None
        entry = self._archive.get(entry_id)
        if entry is None:
            raise KeyError(f"unknown queue entry: {entry_id}")
        old_current_id = self.current_entry_id
        self._current = entry
        if old_current_id is not None and old_current_id != entry_id and not self.contains(old_current_id):
            self._archive.pop(old_current_id, None)
        self._detached_next_id = None if self.contains(entry_id) else self._following_id(entry_id)
        return entry

    def remove(self, index: int) -> QueueEntry:
        """Remove one row while preserving the current track if it was active."""
        if index < 0 or index >= len(self._entries):
            raise IndexError("queue index is outside the queue")
        removed = self._entries.pop(index)
        if self._current is not None and self._current.entry_id == removed.entry_id:
            self._detached_next_id = self._entries[index].entry_id if index < len(self._entries) else None
        elif self._detached_next_id == removed.entry_id:
            self._detached_next_id = self._entries[index].entry_id if index < len(self._entries) else None
            self._archive.pop(removed.entry_id, None)
        else:
            self._archive.pop(removed.entry_id, None)
        self._emit_changed()
        return removed

    def move(self, source_index: int, destination_index: int) -> bool:
        """Move a row to its final index, preserving entry identity.

        Return ``False`` for a no-op. Invalid indices raise ``IndexError``.
        """
        size = len(self._entries)
        if not (0 <= source_index < size and 0 <= destination_index < size):
            raise IndexError("queue index is outside the queue")
        if source_index == destination_index:
            return False
        entry = self._entries.pop(source_index)
        self._entries.insert(destination_index, entry)
        self._emit_changed()
        return True

    def refresh_track(self, track: TrackLike, matches: Callable[[TrackLike, TrackLike], bool]) -> bool:
        """Replace cached Track objects while preserving every queue entry ID."""
        changed = False
        for index, entry in enumerate(self._entries):
            if matches(entry.track, track):
                refreshed = QueueEntry(entry.entry_id, track)
                self._entries[index] = refreshed
                self._archive[entry.entry_id] = refreshed
                if self._current is not None and self._current.entry_id == entry.entry_id:
                    self._current = refreshed
                changed = True
        if self._current is not None and not self.contains(self._current.entry_id) and matches(self._current.track, track):
            refreshed = QueueEntry(self._current.entry_id, track)
            self._current = refreshed
            self._archive[refreshed.entry_id] = refreshed
            changed = True
        return changed

    def clear(self) -> None:
        """Clear queued rows while keeping a selected current track playing."""
        if not self._entries:
            return
        self._entries.clear()
        self._archive = (
            {self._current.entry_id: self._current}
            if self._current is not None
            else {}
        )
        self._detached_next_id = None
        self._emit_changed()

    def next_ordered(self, repeat_all: bool = False) -> QueueEntry | None:
        """Return the next ordered entry, respecting the detached cursor."""
        if not self._entries:
            return None
        index = self.current_index
        if index is not None:
            candidate = index + 1
            if candidate < len(self._entries):
                return self._entries[candidate]
            return self._entries[0] if repeat_all else None
        if self._detached_next_id is not None:
            candidate = self._index_of(self._detached_next_id)
            if candidate >= 0:
                return self._entries[candidate]
        return self._entries[0] if repeat_all else None

    def previous_ordered(self, repeat_all: bool = False) -> QueueEntry | None:
        """Return the previous ordered entry, respecting the detached cursor."""
        if not self._entries:
            return None
        index = self.current_index
        if index is not None:
            if index > 0:
                return self._entries[index - 1]
            return self._entries[-1] if repeat_all else None
        if self._detached_next_id is None:
            return self._entries[-1]
        boundary = self._index_of(self._detached_next_id)
        if boundary > 0:
            return self._entries[boundary - 1]
        return self._entries[-1] if repeat_all else None

    def _new_entry(self, track: TrackLike) -> QueueEntry:
        entry = QueueEntry(next(self._ids), track)
        self._archive[entry.entry_id] = entry
        return entry

    def _index_of(self, entry_id: int) -> int:
        for index, entry in enumerate(self._entries):
            if entry.entry_id == entry_id:
                return index
        return -1

    def _following_id(self, entry_id: int) -> int | None:
        index = self._index_of(entry_id)
        if index < 0:
            return None
        following = index + 1
        return self._entries[following].entry_id if following < len(self._entries) else None

    def _emit_changed(self) -> None:
        self.changed.emit(self.tracks)
