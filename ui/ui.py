from PyQt6.QtCore import Qt, QTimer, QRectF, QPointF
from PyQt6.QtGui import QPainter, QColor, QFont, QPen, QBrush
from PyQt6.QtWidgets import QWidget, QMenu, QTextEdit, QDialog, QVBoxLayout, QLineEdit, QListWidget, QPushButton, QLabel, QMessageBox, QInputDialog
import os
import math
from player.player import Music_player
from utils.file_manager import file_manager
from playlist.playlists import Playlist

class PlaylistManager:
    def __init__(self):
        self.playlist_obj = Playlist()

    def get_all_playlists(self):
        return self.playlist_obj.get_playlist_names()

    def get_songs(self, playlist_name):
        return self.playlist_obj.get_songs(playlist_name)

    def add_playlist(self, name, songs=None):
        if songs is None:
            songs = []
        self.playlist_obj.new_playlist(name, songs)

    def delete_playlist(self, name):
        self.playlist_obj.delete_playlist(name)

    def rename_playlist(self, old_name, new_name):
        self.playlist_obj.rename_playlist(old_name, new_name)

    def add_song_to_playlist(self, playlist_name, song):
        songs = self.get_songs(playlist_name)
        if song not in songs:
            songs.append(song)
            self.playlist_obj.new_playlist(playlist_name, songs)

    def remove_song_from_playlist(self, playlist_name, song):
        songs = self.get_songs(playlist_name)
        if song in songs:
            songs.remove(song)
            self.playlist_obj.new_playlist(playlist_name, songs)

    def get_favorites(self):
        return self.get_songs("Favorites")

    def add_to_favorites(self, song):
        self.add_song_to_playlist("Favorites", song)

class PlaylistDialog(QDialog):
    def __init__(self, parent, existing_playlists, theme='apple'):
        super().__init__(parent)
        self.setWindowTitle("🎶 Add to Playlist")
        self.setFixedSize(320, 420)
        self.setModal(True)
        self.selected_playlist = None
        self.theme = 'dark' if theme == 'apple_dark' else 'light'

        self.setStyleSheet(self.get_stylesheet())

        layout = QVBoxLayout()
        title = QLabel("➕ Add song to playlist")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 18px; font-weight: bold; margin-bottom: 10px;")
        layout.addWidget(title)

        layout.addWidget(QLabel("📂 Select existing playlist:"))
        self.playlist_list = QListWidget()
        self.playlist_list.addItems(existing_playlists)
        self.playlist_list.setStyleSheet("border-radius: 8px;")
        layout.addWidget(self.playlist_list)

        layout.addWidget(QLabel("🆕 Or create new playlist:"))
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("Enter new playlist name")
        layout.addWidget(self.name_input)

        self.add_button = QPushButton("Add")
        self.add_button.clicked.connect(self.accept_selection)
        layout.addWidget(self.add_button)

        self.setLayout(layout)

    def accept_selection(self):
        name = self.name_input.text().strip()
        if name:
            self.selected_playlist = name
        elif self.playlist_list.currentItem():
            self.selected_playlist = self.playlist_list.currentItem().text()
        else:
            QMessageBox.warning(self, "No Selection", "Please select or enter a playlist name.")
            return
        self.accept()

    def get_stylesheet(self):
        if self.theme == 'dark':
            return """
                QDialog { background-color: #1C1C1E; color: #E5E5EA; border-radius: 10px; }
                QLabel { color: #E5E5EA; }
                QLineEdit { background-color: #2C2C2E; color: #E5E5EA; padding: 6px; border-radius: 6px; border: 1px solid #3A3A3C; }
                QListWidget { background-color: #2C2C2E; color: #E5E5EA; border: 1px solid #3A3A3C; padding: 4px; }
                QPushButton { background-color: #007AFF; color: white; padding: 8px; border-radius: 6px; }
                QPushButton:hover { background-color: #0A84FF; }
            """
        else:
            return """
                QDialog { background-color: #FFFFFF; color: #000000; border-radius: 10px; }
                QLabel { color: #333333; }
                QLineEdit { background-color: #F0F0F0; color: #000000; padding: 6px; border-radius: 6px; border: 1px solid #CCCCCC; }
                QListWidget { background-color: #F9F9F9; color: #000000; border: 1px solid #CCCCCC; padding: 4px; }
                QPushButton { background-color: #007AFF; color: white; padding: 8px; border-radius: 6px; }
                QPushButton:hover { background-color: #42A5F5; }
            """

class AnimatedValue:
    def __init__(self, start=0.0):
        self._value = start
        self.target = start
        self.timer = QTimer()
        self.timer.setInterval(16)
        self.timer.timeout.connect(self.update)

    def start_animation(self, target):
        self.target = target
        self.timer.start()

    def update(self):
        diff = self.target - self._value
        if abs(diff) < 0.1:
            self._value = self.target
            self.timer.stop()
        else:
            self._value += diff * 0.15

    def value(self):
        return self._value

class MusicPlayerUI(QWidget):
    def __init__(self, playlist_manager):
        super().__init__()
        self.playlist_manager = playlist_manager
        self.setWindowTitle("Music Player UI")
        self.resize(800, 700)
        self.file_manager_ = file_manager()
        self.backend = Music_player()
        self.songs_path = self.file_manager_.search()
        self.songs = [p.split("\\")[-1] for p in self.songs_path]  # Filenames for display
        self.scroll_offset = 0
        self.scroll_animated = AnimatedValue(0)

        self.queue_display = QTextEdit(self)
        self.queue_display.setReadOnly(True)
        self.queue_display.setGeometry(600, 80, 180, 550)
        self.queue_display.hide()
        self.queue_visible = False

        self.themes = {
            "apple": {
                "bg": QColor(255, 255, 255),
                "fg": QColor(0, 0, 0),
                "highlight": QColor(0, 122, 255),
                "button_bg": QColor(242, 242, 247),
                "button_fg": QColor(0, 0, 0)
            },
            "apple_dark": {
                "bg": QColor(28, 28, 30),
                "fg": QColor(229, 229, 234),
                "highlight": QColor(10, 132, 255),
                "button_bg": QColor(44, 44, 46),
                "button_fg": QColor(229, 229, 234)
            }
        }
        self.theme_name = "apple"
        self.theme = self.themes[self.theme_name]

        # Initialize lists with full paths
        self.favorites = self.playlist_manager.get_favorites() or []
        self.playlists = self.playlist_manager.get_all_playlists()
        self.current_playlist_songs = []  # Full paths of songs in the selected playlist
        self.current_view = "songs"
        self.selected_index = 0
        self.is_playing = False
        self.rotation_angle = 0.0

        self.top_buttons = {
            "list": QRectF(260, 20, 80, 40),
            "playlists": QRectF(20, 20, 110, 40),
            "favorites": QRectF(140, 20, 110, 40),
            "theme": QRectF(350, 20, 110, 40),
            "toggle_queue": QRectF(470, 20, 100, 40)
        }

        self.bottom_buttons = {
            "prev": QRectF(40, 640, 40, 40),
            "play": QRectF(90, 640, 60, 40),
            "next": QRectF(160, 640, 40, 40),
            "repeat": QRectF(220, 640, 40, 40),
            "volume_down": QRectF(270, 640, 40, 40),
            "volume_up": QRectF(320, 640, 40, 40),
            "add_fav": QRectF(370, 640, 40, 40),
            "add_playlist": QRectF(420, 640, 40, 40),
        }

        self.timer = QTimer()
        self.timer.timeout.connect(self.update_rotation)
        self.timer.start(16)

        self.setMouseTracking(True)
        self.hovered_button = None

    def refresh_lists(self):
        """Refresh playlists, favorites, and current playlist songs."""
        self.playlists = self.playlist_manager.get_all_playlists()
        self.favorites = self.playlist_manager.get_favorites() or []
        if self.current_view == "playlist_songs" and hasattr(self, 'selected_playlist'):
            self.current_playlist_songs = self.playlist_manager.get_songs(self.selected_playlist) or []

    def update_rotation(self):
        """Update rotation animation and queue display."""
        if self.is_playing:
            self.rotation_angle = (self.rotation_angle + 0.8) % 360
        self.scroll_animated.start_animation(self.scroll_offset)
        self.update_queue_display()
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), self.theme["bg"])

        for name, rect in self.top_buttons.items():
            label = "Queue 🎶" if name == "toggle_queue" else name.capitalize()
            self.draw_button(painter, rect, label, hovered=(self.hovered_button == name))

        center = QPointF(self.width() / 2, 190)
        radius = 90
        painter.save()
        painter.translate(center)
        painter.rotate(self.rotation_angle if self.is_playing else 0)
        self.draw_cd(painter, radius)
        painter.restore()

        self.draw_volume_indicator(painter)
        self.draw_list(painter, 30, 340, self.width() - 240, 310)

        for name, rect in self.bottom_buttons.items():
            icon = {
                "prev": "⏮",
                "play": "⏸" if self.is_playing else "▶️",
                "next": "⏭",
                "repeat": {1: "🔁", 2: "🔂", 3: "🔀"}.get(self.backend.audio_controls.repeat, "🔁"),
                "add_fav": "❤️",
                "add_playlist": "➕",
                "volume_down": "🔉",
                "volume_up": "🔊"
            }[name]
            self.draw_button(painter, rect, icon, hovered=(self.hovered_button == name))

    def draw_button(self, painter, rect, text, hovered=False):
        painter.setBrush(QBrush(self.theme["highlight"] if hovered else self.theme["button_bg"]))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(rect, 8, 8)
        painter.setPen(self.theme["button_fg"])
        font = QFont("Helvetica Neue", 14 if len(text) == 1 else 16)
        painter.setFont(font)
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)

    def draw_volume_indicator(self, painter):
        rect = QRectF(20, 70, self.width() - 40, 20)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(self.theme["button_bg"]))
        painter.drawRoundedRect(rect, 5, 5)
        filled = rect.width() * self.backend.current_volume
        painter.setBrush(QBrush(self.theme["highlight"]))
        painter.drawRoundedRect(QRectF(rect.left(), rect.top(), filled, rect.height()), 5, 5)
        painter.setPen(self.theme["fg"])
        painter.setFont(QFont("Arial", 10))
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, f"Volume: {int(self.backend.current_volume * 100)}%")

    def draw_cd(self, painter, radius):
        painter.setBrush(QBrush(QColor(200, 200, 200)))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QPointF(0, 0), radius, radius)
        painter.setPen(QPen(QColor(150, 150, 150), 2))
        for angle in range(0, 360, 20):
            rad = math.radians(angle)
            painter.drawLine(QPointF(0, 0), QPointF(math.cos(rad) * radius, math.sin(rad) * radius))
        painter.setBrush(QBrush(QColor(100, 100, 100)))
        painter.drawEllipse(QPointF(0, 0), 20, 20)

    def draw_list(self, painter, x, y, width, height):
        painter.save()
        painter.setClipRect(x, y, width, height)
        items = self.get_current_list()
        if not items:
            painter.setPen(self.theme["fg"])
            painter.drawText(QRectF(x, y, width, height), Qt.AlignmentFlag.AlignCenter, "No items available")
            painter.restore()
            return
        lh = 30
        painter.setFont(QFont("Arial", 14))
        start = int(self.scroll_animated.value())
        end = min(start + height // lh, len(items))
        for i in range(start, end):
            r = QRectF(x, y + (i - start) * lh, width, lh)
            if i == self.selected_index:
                painter.fillRect(r, self.theme["highlight"])
                painter.setPen(self.theme["bg"])
            else:
                painter.setPen(self.theme["fg"])
            if self.current_view == "playlists":
                painter.drawText(r, Qt.AlignmentFlag.AlignVCenter, items[i])
            else:
                painter.drawText(r, Qt.AlignmentFlag.AlignVCenter, os.path.basename(items[i]))
        painter.restore()

    def show_context_menu(self, global_pos):
        menu = QMenu()
        current_list = self.get_current_list()
        if not current_list:
            return

        if self.current_view == "playlists":
            menu.addAction("🎵 Show Songs", self.show_playlist_songs)
            if self.playlists[self.selected_index] != "Favorites":
                menu.addAction("🗑️ Delete Playlist", self.delete_playlist)
                menu.addAction("✏️ Rename Playlist", self.rename_playlist)
        else:
            menu.addAction("▶️ Play", self.play_song)
            menu.addAction("⏭️ Play Next", self.play_next)
            menu.addAction("❤️ Add to Favorites", self.add_to_favorites)
            menu.addAction("➕ Add to Playlist", self.add_to_playlist)
            if self.current_view == "favorites":
                menu.addAction("❌ Remove from Favorites", self.remove_from_favorites)
            elif self.current_view == "playlist_songs":
                menu.addAction("❌ Remove from Playlist", self.remove_from_playlist)
            menu.addAction("❌ Remove from Queue", self.remove_from_queue)

        menu.exec(global_pos)
        self.refresh_lists()
        self.update()

    def play_song(self):
        current_list = self.get_current_list()
        if current_list:
            if self.current_view == "songs":
                queue = self.songs_path
            elif self.current_view in ("favorites", "playlist_songs"):
                queue = current_list  # Already full paths
            else:
                return
            self.backend.audio_controls.queue = queue
            self.backend.audio_controls.song_pointer = self.selected_index
            self.backend.start()
            self.backend.audio_controls.is_paused = False
            self.is_playing = True
            self.update()

    def play_next(self):
        current_list = self.get_current_list()
        if current_list:
            if self.current_view == "songs":
                song_path = self.songs_path[self.selected_index]
            else:
                song_path = current_list[self.selected_index]
            self.backend.playnext(song_path, self.selected_index)
            self.update()

    def add_to_favorites(self):
        current_list = self.get_current_list()
        if current_list:
            if self.current_view == "songs":
                song_path = self.songs_path[self.selected_index]
            else:
                song_path = current_list[self.selected_index]
            self.playlist_manager.add_to_favorites(song_path)
            print(f"Added to favorites: {os.path.basename(song_path)}")
            self.refresh_lists()
            self.update()

    def remove_from_favorites(self):
        if self.current_view == "favorites" and self.favorites:
            song = self.favorites[self.selected_index]
            self.playlist_manager.remove_song_from_playlist("Favorites", song)
            print(f"Removed from favorites: {os.path.basename(song)}")
            self.refresh_lists()
            self.update()

    def add_to_playlist(self):
        current_list = self.get_current_list()
        if current_list:
            if self.current_view == "songs":
                song_path = self.songs_path[self.selected_index]
            else:
                song_path = current_list[self.selected_index]
            dialog = PlaylistDialog(self, self.playlists, self.theme_name)
            if dialog.exec():
                selected_name = dialog.selected_playlist
                if selected_name not in self.playlists:
                    self.playlist_manager.add_playlist(selected_name, [song_path])
                else:
                    self.playlist_manager.add_song_to_playlist(selected_name, song_path)
                print(f"Added to playlist {selected_name}: {os.path.basename(song_path)}")
                self.refresh_lists()
                self.update()

    def remove_from_playlist(self):
        if self.current_view == "playlist_songs" and self.current_playlist_songs:
            song = self.current_playlist_songs[self.selected_index]
            self.playlist_manager.remove_song_from_playlist(self.selected_playlist, song)
            print(f"Removed from playlist {self.selected_playlist}: {os.path.basename(song)}")
            self.refresh_lists()
            self.update()

    def remove_from_queue(self):
        if self.backend.audio_controls.queue:
            current_list = self.get_current_list()
            if self.current_view == "songs":
                song_path = self.songs_path[self.selected_index]
            else:
                song_path = current_list[self.selected_index]
            self.backend.remove_from_queue(song_path)
            self.update_queue_display()

    def show_playlist_songs(self):
        if self.current_view == "playlists" and self.playlists:
            self.selected_playlist = self.playlists[self.selected_index]
            self.current_playlist_songs = self.playlist_manager.get_songs(self.selected_playlist) or []
            self.current_view = "playlist_songs"
            self.selected_index = 0
            self.scroll_offset = 0
            self.update()

    def delete_playlist(self):
        if self.current_view == "playlists" and self.playlists and self.playlists[self.selected_index] != "Favorites":
            playlist_name = self.playlists[self.selected_index]
            reply = QMessageBox.question(self, "Delete Playlist", f"Are you sure you want to delete '{playlist_name}'?",
                                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if reply == QMessageBox.StandardButton.Yes:
                self.playlist_manager.delete_playlist(playlist_name)
                print(f"Deleted playlist: {playlist_name}")
                self.refresh_lists()
                self.update()

    def rename_playlist(self):
        if self.current_view == "playlists" and self.playlists and self.playlists[self.selected_index] != "Favorites":
            playlist_name = self.playlists[self.selected_index]
            dialog = QInputDialog(self)
            dialog.setWindowTitle("Rename Playlist")
            dialog.setLabelText(f"Enter new name for '{playlist_name}':")
            dialog.setTextValue(playlist_name)
            dialog.setStyleSheet(self.get_dialog_stylesheet())
            if dialog.exec() and dialog.textValue().strip():
                new_name = dialog.textValue().strip()
                if new_name not in self.playlists:
                    self.playlist_manager.rename_playlist(playlist_name, new_name)
                    print(f"Renamed playlist from {playlist_name} to {new_name}")
                    self.refresh_lists()
                    self.update()
                else:
                    QMessageBox.warning(self, "Invalid Name", "Playlist name already exists.")

    def get_dialog_stylesheet(self):
        if self.theme_name == 'apple_dark':
            return """
                QInputDialog { background-color: #1C1C1E; color: #E5E5EA; }
                QLineEdit { background-color: #2C2C2E; color: #E5E5EA; padding: 6px; border-radius: 6px; border: 1px solid #3A3A3C; }
                QPushButton { background-color: #007AFF; color: white; padding: 8px; border-radius: 6px; }
                QPushButton:hover { background-color: #0A84FF; }
            """
        else:
            return """
                QInputDialog { background-color: #FFFFFF; color: #000000; }
                QLineEdit { background-color: #F0F0F0; color: #000000; padding: 6px; border-radius: 6px; border: 1px solid #CCCCCC; }
                QPushButton { background-color: #007AFF; color: white; padding: 8px; border-radius: 6px; }
                QPushButton:hover { background-color: #42A5F5; }
            """

    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        amt = -1 if delta > 0 else 1
        maxs = max(0, len(self.get_current_list()) - (310 // 30))
        self.scroll_offset = max(0, min(self.scroll_offset + amt, maxs))
        self.update()

    def get_current_list(self):
        return {
            "songs": self.songs_path,
            "playlists": self.playlists,
            "favorites": self.favorites,
            "playlist_songs": self.current_playlist_songs
        }.get(self.current_view, [])

    def mousePressEvent(self, event):
        pos = event.position()
        if event.button() == Qt.MouseButton.LeftButton:
            for name, rect in self.top_buttons.items():
                if rect.contains(pos):
                    self.handle_top_button(name)
                    return
            for name, rect in self.bottom_buttons.items():
                if rect.contains(pos):
                    self.handle_bottom_button(name)
                    return
            lr = QRectF(30, 340, self.width() - 240, 310)
            if lr.contains(pos) and self.get_current_list():
                idx = int((pos.y() - 340) // 30) + self.scroll_offset
                lst = self.get_current_list()
                if 0 <= idx < len(lst):
                    self.selected_index = idx
                    if self.current_view == "playlists":
                        self.show_playlist_songs()
                    elif self.current_view in ("songs", "favorites", "playlist_songs"):
                        queue = self.get_current_list() if self.current_view != "songs" else self.songs_path
                        self.backend.audio_controls.queue = queue
                        self.backend.audio_controls.song_pointer = self.selected_index
                        self.backend.start()
                        self.backend.audio_controls.is_paused = False
                        self.is_playing = True
                    self.update()
        elif event.button() == Qt.MouseButton.RightButton:
            lr = QRectF(30, 340, self.width() - 240, 310)
            if lr.contains(pos) and self.get_current_list():
                idx = int((pos.y() - 340) // 30) + self.scroll_offset
                lst = self.get_current_list()
                if 0 <= idx < len(lst):
                    self.selected_index = idx
                    self.show_context_menu(event.globalPosition().toPoint())
        self.update_queue_display()

    def update_queue_display(self):
        if self.queue_visible:
            self.queue_display.show()
            current_index = self.backend.audio_controls.song_pointer
            queue = self.backend.audio_controls.queue or []
            formatted = "Queue is empty" if not queue else ""
            for i, song in enumerate(queue):
                marker = "🎧 " if i == current_index else "   "
                formatted += f"{marker}{os.path.basename(song)}\n--------------------\n"
            self.queue_display.setText(formatted)
        else:
            self.queue_display.hide()

    def mouseMoveEvent(self, event):
        pos = event.position()
        hovered = None
        for name, rect in {**self.top_buttons, **self.bottom_buttons}.items():
            if rect.contains(pos):
                hovered = name
                break
        if hovered != self.hovered_button:
            self.hovered_button = hovered
            self.update()

    def handle_top_button(self, name):
        if name == "playlists":
            self.current_view, self.selected_index = "playlists", 0
            self.current_playlist_songs = []
        elif name == "favorites":
            self.current_view, self.selected_index = "favorites", 0
            self.current_playlist_songs = []
        elif name == "theme":
            self.toggle_theme()
        elif name == "list":
            self.current_view, self.selected_index = "songs", 0
            self.current_playlist_songs = []
        elif name == "toggle_queue":
            self.queue_visible = not self.queue_visible
            self.update_queue_display()
        self.refresh_lists()
        self.update()

    def handle_bottom_button(self, name):
        current_list = self.get_current_list()
        if name == "play":
            if not self.is_playing and current_list:
                queue = current_list if self.current_view != "songs" else self.songs_path
                self.backend.audio_controls.queue = queue
                self.backend.audio_controls.song_pointer = self.selected_index
                self.backend.start()
                self.is_playing = True
            else:
                self.backend.pause()
                self.is_playing = False
        elif name == "prev" and self.backend.audio_controls.queue:
            self.backend.prev_song()
            self.selected_index = self.backend.audio_controls.song_pointer
            self.is_playing = True
        elif name == "next" and self.backend.audio_controls.queue:
            self.backend.next_song()
            self.selected_index = self.backend.audio_controls.song_pointer
            self.is_playing = True
        elif name == "repeat":
            self.backend.toggle_repeat()
            self.songs_path = self.backend.audio_controls.queue
            self.selected_index = self.backend.audio_controls.song_pointer
        elif name == "add_fav":
            if current_list:
                if self.current_view == "songs":
                    song_path = self.songs_path[self.selected_index]
                else:
                    song_path = current_list[self.selected_index]
                self.playlist_manager.add_to_favorites(song_path)
                print(f"Added to favorites: {os.path.basename(song_path)}")
                self.refresh_lists()
        elif name == "add_playlist":
            if current_list:
                if self.current_view == "songs":
                    song_path = self.songs_path[self.selected_index]
                else:
                    song_path = current_list[self.selected_index]
                dialog = PlaylistDialog(self, self.playlists, self.theme_name)
                if dialog.exec():
                    selected_name = dialog.selected_playlist
                    if selected_name not in self.playlists:
                        self.playlist_manager.add_playlist(selected_name, [song_path])
                    else:
                        self.playlist_manager.add_song_to_playlist(selected_name, song_path)
                    print(f"Added to playlist {selected_name}: {os.path.basename(song_path)}")
                    self.refresh_lists()
        elif name == "volume_up":
            self.backend.volume_up()
        elif name == "volume_down":
            self.backend.volume_down()
        self.update()

    def toggle_theme(self):
        self.theme_name = "apple_dark" if self.theme_name == "apple" else "apple"
        self.theme = self.themes[self.theme_name]

    def keyPressEvent(self, event):
        max_idx = len(self.get_current_list()) - 1
        if max_idx < 0:
            return
        if event.key() == Qt.Key.Key_Up and self.selected_index > 0:
            self.selected_index -= 1
            if self.selected_index < self.scroll_offset:
                self.scroll_offset = self.selected_index
        elif event.key() == Qt.Key.Key_Down and self.selected_index < max_idx:
            self.selected_index += 1
            visible_count = 310 // 30
            if self.selected_index >= self.scroll_offset + visible_count:
                self.scroll_offset = self.selected_index - visible_count + 1
        elif event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if self.current_view == "playlists":
                self.show_playlist_songs()
            elif self.current_view in ("songs", "favorites", "playlist_songs"):
                self.play_song()
        self.update_queue_display()
        self.update()