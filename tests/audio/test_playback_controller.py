from __future__ import annotations

import math

import pytest

import core.audio.audio_engine as audio_engine_module
from core.audio.audio_engine import AudioEngine
from core.audio.playback_controller import PlaybackController
from core.audio.playback_state import PlaybackState


def test_loading_does_not_claim_playing_until_backend_confirms(controller_factory):
    controller, backend, tracks = controller_factory()
    states: list[str] = []
    controller.playback_state_changed.connect(states.append)

    controller.play_track(tracks[0])

    assert controller.current_state == PlaybackState.LOADING.value
    assert not controller.is_playing
    assert states == [PlaybackState.LOADING.value]
    backend.start_playing()
    assert controller.current_state == PlaybackState.PLAYING.value
    assert states[-1] == PlaybackState.PLAYING.value


def test_play_queue_start_index_and_queue_signals(controller_factory):
    controller, backend, tracks = controller_factory()
    queues: list[list[object]] = []
    current: list[object] = []
    controller.queue_changed.connect(queues.append)
    controller.current_track_changed.connect(current.append)

    controller.play_queue(tracks, start_index=1)

    assert controller.current_track is tracks[1]
    assert controller.queue == tracks
    assert queues == [tracks]
    assert current == [tracks[1]]


def test_duplicate_track_occurrences_emit_queue_index_change(controller_factory):
    controller, backend, tracks = controller_factory(("one",))
    indices: list[int | None] = []
    current_tracks: list[object] = []
    controller.current_queue_index_changed.connect(indices.append)
    controller.current_track_changed.connect(current_tracks.append)

    controller.play_queue([tracks[0], tracks[0]])
    controller.next()

    assert controller.current_track is tracks[0]
    assert controller.current_queue_index == 1
    assert indices == [0, 1]
    assert current_tracks == [tracks[0]]


def test_queue_add_duplicate_play_next_remove_move_clear(controller_factory):
    controller, backend, tracks = controller_factory()
    controller.play_queue(tracks)
    original = controller.current_track

    controller.add_to_queue(tracks[0])
    assert controller.queue == [*tracks, tracks[0]]
    controller.play_next(tracks[1])
    assert controller.queue == [tracks[0], tracks[1], tracks[1], tracks[2], tracks[0]]
    controller.move_queue_item(4, 2)
    assert controller.current_track is original
    controller.remove_from_queue(0)
    assert controller.current_track is original
    controller.clear_queue()
    assert controller.queue == []
    assert controller.current_track is original


def test_removing_current_row_does_not_interrupt_current_playback(controller_factory):
    controller, backend, tracks = controller_factory()
    controller.play_queue(tracks, start_index=1)
    current = controller.current_track

    controller.remove_from_queue(1)

    assert controller.current_track is current
    assert controller.current_state == PlaybackState.LOADING.value
    assert controller.queue == [tracks[0], tracks[2]]
    controller.next()
    assert controller.current_track is tracks[2]


def test_repeat_all_and_repeat_one_end_of_track(controller_factory):
    controller, backend, tracks = controller_factory(("one", "two"))
    controller.play_queue(tracks)
    controller.set_repeat_mode("all")
    backend.complete()
    assert controller.current_track is tracks[1]
    backend.complete()
    assert controller.current_track is tracks[0]

    controller.set_repeat_mode("one")
    backend.set_seekable(True)
    backend.complete()
    assert controller.current_track is tracks[0]
    assert backend.seek_requests[-1:] == [0]


def test_repeat_off_stops_at_end_and_next_is_manual_stop(controller_factory):
    controller, backend, tracks = controller_factory(("one", "two"))
    controller.play_queue(tracks)
    backend.complete()
    assert controller.current_track is tracks[1]
    backend.complete()
    assert controller.current_state == PlaybackState.STOPPED.value
    controller.next()
    assert controller.current_state == PlaybackState.STOPPED.value


def test_shuffle_is_independent_and_visits_each_queue_entry_once(controller_factory):
    controller, backend, tracks = controller_factory(("one", "two", "three", "four", "five"), random_seed=4)
    controller.play_queue(tracks)
    original_order = controller.queue[:]
    controller.set_shuffle(True)
    assert controller.shuffle_enabled

    visited = [controller.current_track]
    for _ in range(4):
        controller.next()
        visited.append(controller.current_track)

    assert len({track.path for track in visited}) == 5
    assert controller.queue == original_order
    controller.play_queue(tracks, start_index=1)
    controller.set_shuffle(True)
    controller.set_shuffle(False)
    controller.next()
    assert controller.current_track is tracks[2]


def test_shuffle_reorders_do_not_change_current_and_play_next_is_prioritized(controller_factory):
    controller, backend, tracks = controller_factory(("one", "two", "three"), random_seed=2)
    controller.play_queue(tracks)
    controller.set_shuffle(True)
    controller.move_queue_item(2, 0)
    controller.play_next(tracks[2])

    controller.next()

    assert controller.current_track is tracks[2]
    assert controller.queue[0] is tracks[2]


def test_repeat_all_shuffle_avoids_immediate_repeat_at_cycle_boundary(controller_factory):
    controller, backend, tracks = controller_factory(("one", "two", "three"), random_seed=0)
    controller.play_queue(tracks)
    controller.set_shuffle(True)
    controller.set_repeat_mode("all")
    visited = [controller.current_track]
    controller.next()
    visited.append(controller.current_track)
    controller.next()
    visited.append(controller.current_track)
    previous = visited[-1]
    controller.next()

    assert controller.current_track is not previous
    assert len({track.path for track in visited}) == 3


def test_shuffle_history_remains_valid_when_an_old_entry_is_removed(controller_factory):
    controller, backend, tracks = controller_factory(("one", "two", "three", "four"), random_seed=6)
    controller.play_queue(tracks)
    controller.set_shuffle(True)
    controller.next()
    controller.next()
    current = controller.current_track
    controller.remove_from_queue(controller.queue.index(tracks[0]))

    controller.next()
    next_track = controller.current_track
    assert next_track is not current
    controller.previous()

    assert controller.current_track is current


def test_previous_threshold_restart_and_ordered_navigation(controller_factory):
    controller, backend, tracks = controller_factory(previous_restart_threshold_ms=3_000)
    controller.play_queue(tracks)
    backend.start_playing()
    backend.set_seekable(True)
    backend._position = 3_001
    backend.position_changed.emit(3_001)
    controller.previous()
    assert backend.seek_requests[-1] == 0
    backend._position = 1_000
    backend.position_changed.emit(1_000)
    controller.next()
    assert controller.current_track is tracks[1]
    controller.previous()
    assert controller.current_track is tracks[0]


def test_seek_clamps_and_is_deferred_until_loading_source_is_seekable(controller_factory):
    controller, backend, tracks = controller_factory()
    controller.play_track(tracks[0])
    controller.seek(8_000)
    assert backend.seek_requests == []
    backend.set_seekable(True, duration_ms=5_000)
    assert backend.seek_requests == [5_000]
    assert controller.position == 5_000
    controller.seek(-20)
    assert backend.seek_requests[-1] == 0
    controller.seek(99_000)
    assert backend.seek_requests[-1] == 5_000


def test_volume_boundaries_mute_and_restore_volume(controller_factory):
    controller, backend, _ = controller_factory()
    changed: list[float] = []
    muted: list[bool] = []
    controller.volume_changed.connect(changed.append)
    controller.muted_changed.connect(muted.append)

    controller.set_volume(-2)
    assert controller.volume == 0.0
    controller.set_volume(2)
    assert controller.volume == 1.0
    controller.set_volume(float("nan"))
    assert controller.volume == 0.0
    controller.set_volume(0.4)
    controller.set_muted(True)
    assert controller.volume == 0.4
    assert controller.is_muted
    controller.set_muted(False)
    assert controller.volume == 0.4
    assert not controller.is_muted
    assert changed == [0.0, 1.0, 0.0, 0.4]
    assert muted == [True, False]


def test_invalid_file_and_backend_errors_enter_error_without_crashing(controller_factory, tmp_path):
    controller, backend, tracks = controller_factory()
    errors: list[str] = []
    controller.error_occurred.connect(errors.append)
    tracks[0].path = str(tmp_path / "missing.wav")

    controller.play_track(tracks[0])

    assert controller.current_state == PlaybackState.ERROR.value
    assert errors and "not found" in errors[-1]
    assert not controller.is_playing

    controller.play_track(tracks[1])
    backend.fail("unsupported codec")
    assert controller.current_state == PlaybackState.ERROR.value
    assert errors[-1] == "unsupported codec"


def test_pause_toggle_stop_and_shutdown_are_idempotent(controller_factory):
    controller, backend, tracks = controller_factory()
    controller.play_track(tracks[0])
    backend.start_playing()
    controller.pause()
    assert backend.pause_requests == 1
    backend._state = "paused"
    backend.state_changed.emit("paused")
    assert controller.is_paused
    controller.toggle_play_pause()
    assert backend.play_requests == 2
    controller.stop()
    assert controller.current_state == PlaybackState.STOPPED.value
    controller.shutdown()
    controller.shutdown()
    assert backend.shutdown_requests == 1


def test_repeat_mode_rejects_unknown_values(controller_factory):
    controller, _, _ = controller_factory()
    with pytest.raises(ValueError):
        controller.set_repeat_mode("cycle")


def test_audio_initialization_failure_is_reported_without_crashing(monkeypatch, make_files):
    def fail_initialization(parent=None):
        raise RuntimeError("multimedia plugin missing")

    monkeypatch.setattr(audio_engine_module, "QtMultimediaBackend", fail_initialization)
    engine = AudioEngine()
    controller = PlaybackController(engine)
    errors: list[str] = []
    controller.error_occurred.connect(errors.append)

    controller.play_track(make_files("one")[0])

    assert engine.initialization_error == "multimedia plugin missing"
    assert controller.current_state == PlaybackState.ERROR.value
    assert "could not initialize" in errors[0]
    controller.shutdown()


def test_unexpected_backend_stop_enters_error(controller_factory):
    controller, backend, tracks = controller_factory()
    controller.play_track(tracks[0])
    backend.start_playing()
    backend._state = "stopped"
    backend._media_status = "loadedmedia"
    backend.state_changed.emit("stopped")

    assert controller.current_state == PlaybackState.ERROR.value
