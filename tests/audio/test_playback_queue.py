from __future__ import annotations

import pytest

from core.audio.playback_queue import PlaybackQueue


def test_queue_keeps_duplicate_occurrences_distinct(make_files):
    track, = make_files("same")
    queue = PlaybackQueue()

    first = queue.append(track)
    second = queue.append(track)

    assert queue.tracks == [track, track]
    assert first.entry_id != second.entry_id
    assert queue.ids() == (first.entry_id, second.entry_id)


def test_replace_selects_start_index_and_validates_index(make_files):
    tracks = make_files("one", "two", "three")
    queue = PlaybackQueue()

    current = queue.replace(tracks, start_index=1)

    assert current is not None
    assert current.track is tracks[1]
    assert queue.current_index == 1
    with pytest.raises(IndexError):
        queue.replace(tracks, start_index=3)
    assert queue.current_track is tracks[1]


def test_reorder_and_remove_preserve_current_entry(make_files):
    tracks = make_files("one", "two", "three")
    queue = PlaybackQueue()
    queue.replace(tracks, start_index=1)
    current_id = queue.current_entry_id

    assert queue.move(1, 0)
    assert queue.current_index == 0
    assert queue.current_entry_id == current_id
    removed = queue.remove(0)

    assert removed.track is tracks[1]
    assert queue.current_track is tracks[1]
    assert queue.current_index is None
    assert queue.next_ordered().track is tracks[0]


def test_clear_keeps_current_track_but_empties_upcoming_queue(make_files):
    tracks = make_files("one", "two")
    queue = PlaybackQueue()
    queue.replace(tracks)

    queue.clear()

    assert queue.tracks == []
    assert queue.current_track is tracks[0]
    assert queue.next_ordered() is None


def test_play_next_after_detached_current_goes_at_the_boundary(make_files):
    tracks = make_files("one", "two", "three")
    queue = PlaybackQueue()
    queue.replace(tracks, start_index=2)
    queue.remove(2)

    inserted = queue.insert_next(tracks[0])

    assert queue.tracks == [tracks[0], tracks[1], tracks[0]]
    assert queue.current_track is tracks[2]
    assert queue.next_ordered().entry_id == inserted.entry_id
