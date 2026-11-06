"""Structural smoke tests for the injected PySide6 presentation layer."""

from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QObject, QEventLoop, QTimer, Signal
from PySide6.QtWidgets import QApplication

from ui.dialogs import LyricsEditorDialog, MetadataEditorDialog, PlaylistSelectDialog, TrackPickerDialog
from ui.main_window import MainWindow


TRACKS = [
    {"id": "t1", "title": "Amber Roads", "artist": "Mira Vale", "album": "First Light", "duration": 187, "genre": "Ambient"},
    {"id": "t2", "title": "Quiet Current", "artist": "Jonas North", "album": "Blue Hour", "duration": 231, "genre": "Jazz"},
]


class Library:
    def list_tracks(self):
        return list(TRACKS)

    def list_albums(self):
        return [{"id": "a1", "title": "First Light", "artist": "Mira Vale", "track_count": 1}]

    def list_artists(self):
        return [{"id": "ar1", "name": "Mira Vale", "album_count": 1}]

    def scan_library(self, **kwargs):
        return True


class Playlists:
    def __init__(self):
        self.items = [{"id": "fav", "name": "Favorites"}, {"id": "p1", "name": "Night Drive"}]
        self.contents = {"fav": [TRACKS[0]], "p1": [TRACKS[1]]}

    def list_playlists(self):
        return list(self.items)

    def list_favorites(self):
        return list(self.contents["fav"])

    def get_playlist_tracks(self, playlist_id):
        return list(self.contents.get(playlist_id, []))

    def create_playlist(self, name):
        item = {"id": name.casefold().replace(" ", "_"), "name": name}
        self.items.append(item)
        self.contents[item["id"]] = []
        return item

    def add_track(self, playlist_id, track_id):
        track = next(item for item in TRACKS if item["id"] == track_id)
        self.contents.setdefault(playlist_id, []).append(track)

    def remove_track(self, playlist_id, track_id):
        self.contents[playlist_id] = [item for item in self.contents.get(playlist_id, []) if item["id"] != track_id]

    def rename_playlist(self, playlist_id, new_name):
        next(item for item in self.items if item["id"] == playlist_id)["name"] = new_name

    def delete_playlist(self, playlist_id):
        self.items = [item for item in self.items if item["id"] != playlist_id]
        self.contents.pop(playlist_id, None)


class Metadata:
    def read_metadata(self, track):
        return dict(track)

    def write_metadata(self, track, metadata):
        track.update(metadata)
        return True

    def read_artwork(self, track):
        return None


class Lyrics:
    def get_lyrics(self, track):
        return "[00:01.00]A quiet line"

    def save_lyrics(self, track, text, is_lrc=False):
        return True


class Settings:
    def __init__(self):
        self.values = {}

    def get(self, key, default=None):
        return self.values.get(key, default)

    def set(self, key, value):
        self.values[key] = value


class History:
    def recently_played(self, limit=20):
        return [TRACKS[0]]

    def recently_added(self, limit=20):
        return list(TRACKS)


class Playback(QObject):
    track_changed = Signal(object)
    playback_state_changed = Signal(str)
    position_changed = Signal(float, float)
    volume_changed = Signal(float)
    queue_changed = Signal(object, int)

    def __init__(self):
        super().__init__()
        self.current_track = None
        self.is_playing = False
        self.position = 0.0
        self.duration = 0.0
        self.volume = 0.7
        self.queue = []
        self.current_index = -1
        self.shuffle = False
        self.repeat_mode = "off"

    def play_track(self, track):
        self.queue = [track]
        self.current_index = 0
        self.current_track = track
        self.is_playing = True
        self.track_changed.emit(track)
        self.playback_state_changed.emit("playing")
        self.queue_changed.emit(self.queue, self.current_index)

    def play_queue(self, tracks, start_index=0):
        self.queue = list(tracks)
        self.current_index = start_index
        self.current_track = self.queue[start_index]
        self.is_playing = True
        self.track_changed.emit(self.current_track)
        self.playback_state_changed.emit("playing")
        self.queue_changed.emit(self.queue, self.current_index)

    def toggle_play_pause(self):
        self.is_playing = not self.is_playing
        self.playback_state_changed.emit("playing" if self.is_playing else "paused")

    def next(self):
        if self.queue and self.current_index + 1 < len(self.queue):
            self.current_index += 1
            self.current_track = self.queue[self.current_index]
            self.track_changed.emit(self.current_track)

    def previous(self):
        if self.current_index > 0:
            self.current_index -= 1
            self.current_track = self.queue[self.current_index]
            self.track_changed.emit(self.current_track)

    def seek(self, position):
        self.position = position

    def set_volume(self, volume):
        self.volume = volume
        self.volume_changed.emit(volume)

    def set_shuffle(self, shuffle):
        self.shuffle = shuffle

    def set_repeat_mode(self, mode):
        self.repeat_mode = mode

    def add_to_queue(self, track):
        self.queue.append(track)
        self.queue_changed.emit(self.queue, self.current_index)

    def play_next(self, track):
        self.queue.insert(max(0, self.current_index + 1), track)

    def remove_from_queue(self, index):
        self.queue.pop(index)
        self.queue_changed.emit(self.queue, self.current_index)

    def move_queue_item(self, old, new):
        self.queue.insert(new, self.queue.pop(old))
        self.queue_changed.emit(self.queue, self.current_index)

    def clear_queue(self):
        self.queue.clear()
        self.current_index = -1
        self.queue_changed.emit(self.queue, self.current_index)


class MainWindowSmokeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = MainWindow(
            library_service=Library(), playlist_service=Playlists(), metadata_service=Metadata(),
            lyrics_service=Lyrics(), settings_service=Settings(), history_service=History(),
            playback_controller=Playback(),
        )
        loop = QEventLoop()
        QTimer.singleShot(250, loop.quit)
        loop.exec()

    def tearDown(self):
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()

    def test_pages_registered_and_service_data_loaded(self):
        expected = {"home", "now_playing", "songs", "albums", "artists", "recently_played", "favorites", "playlists", "lyrics", "settings", "entity_detail", "search"}
        self.assertEqual(set(self.window.pages), expected)
        self.assertEqual(self.window.songs_page.table.source_model.rowCount(), 2)
        self.assertEqual(self.window.albums_page.grid.layout().count(), 1)

    def test_track_activation_and_seek_drag(self):
        self.window._play_from_table(self.window.songs_page.table, TRACKS[1])
        self.assertEqual(self.window.playback_controller.current_track["id"], "t2")
        self.window.playback_bar.set_track(TRACKS[0])
        self.window.playback_bar.set_position(20, 187)
        self.window.playback_bar._seek_started()
        self.window.playback_bar.seek.setValue(800)
        self.window.playback_bar.set_position(30, 187)
        self.assertEqual(self.window.playback_bar.seek.value(), 800)
        self.window.playback_bar._seek_released()
        self.assertAlmostEqual(self.window.playback_controller.position, 149.6, places=1)

    def test_navigation_and_search(self):
        self.window.navigate("albums")
        self.assertEqual(self.window._active_page, "albums")
        self.window.global_search.input.setText("Amber")
        self.window._run_search("Amber")
        self.assertEqual(self.window.search_page.tracks.source_model.rowCount(), 1)
        self.assertEqual(self.window._active_page, "search")
        self.window.settings_page.theme.setCurrentText("light")
        self.assertEqual(self.window.settings_service.get("appearance.theme"), "light")
        self.assertIn("#F4F5F8", self.window.styleSheet())

    def test_queue_and_favorite_actions_use_services(self):
        self.window.playback_controller.play_queue(TRACKS, 0)
        self.window._add_to_queue(TRACKS[1])
        self.assertEqual(len(self.window.playback_controller.queue), 3)
        self.window._remove_queue_item(2)
        self.assertEqual(len(self.window.playback_controller.queue), 2)
        self.window._toggle_favorite(TRACKS[1])
        self.assertIn(TRACKS[1], self.window.playlist_service.contents["fav"])

    def test_palette_toolbar_and_sleep_timer_are_wired(self):
        self.assertTrue(hasattr(self.window, "command_button"))
        self.assertTrue(hasattr(self.window, "timer_button"))
        self.window._set_timer_button_active(True)
        self.assertTrue(self.window.timer_button.property("active"))

        self.window.playback_controller.is_playing = True
        self.window._sleep_remaining_seconds = 1
        self.window._sleep_timer.start()
        self.window._on_sleep_timer_tick()

        self.assertFalse(self.window._sleep_timer.isActive())
        self.assertFalse(self.window.timer_button.property("active"))
        self.assertFalse(self.window.playback_controller.is_playing)

    def test_side_drawers_open_and_close_cleanly_without_motion(self):
        self.window.settings_service.set("appearance.animations", False)

        self.assertEqual(self.window.sidebar.maximumWidth(), 232)
        self.window._toggle_sidebar()
        self.assertEqual(self.window.sidebar.maximumWidth(), 0)
        self.window._toggle_sidebar()
        self.assertEqual(self.window.sidebar.maximumWidth(), 232)

        self.window._toggle_queue()
        self.assertFalse(self.window.queue_panel.isHidden())
        self.assertEqual(self.window.queue_panel.maximumWidth(), 420)
        self.window._toggle_queue()
        self.assertTrue(self.window.queue_panel.isHidden())
        self.assertEqual(self.window.queue_panel.maximumWidth(), 0)

    def test_dialogs_can_be_constructed_offscreen(self):
        playlist_dialog = PlaylistSelectDialog([{"id": "p1", "name": "Mix"}])
        picker = TrackPickerDialog(TRACKS, Metadata())
        metadata = MetadataEditorDialog(TRACKS[0], Metadata())
        lyrics = LyricsEditorDialog(TRACKS[0], Lyrics(), "[00:01.00]Line")
        for dialog in (playlist_dialog, picker, metadata, lyrics):
            dialog.close()


if __name__ == "__main__":
    unittest.main()
