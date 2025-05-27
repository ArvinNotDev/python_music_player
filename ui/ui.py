from PyQt6.QtCore import Qt, QTimer, QRectF, QPointF
from PyQt6.QtGui import QPainter, QColor, QFont, QPen, QBrush
from PyQt6.QtWidgets import QWidget, QMenu, QTextEdit
import os
import math
from player.player import Music_player
from utils.file_manager import file_manager
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLineEdit, QListWidget, QPushButton, QLabel, QMessageBox


class PlaylistDialog(QDialog):
    def __init__(self, parent, existing_playlists, theme='light'):
        super().__init__(parent)
        self.setWindowTitle("🎶 Add to Playlist")
        self.setFixedSize(320, 420)
        self.setModal(True)

        self.selected_playlist = None
        self.theme = theme

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
                QDialog {
                    background-color: #121212;
                    color: #ffffff;
                    border-radius: 10px;
                }
                QLabel {
                    color: #dddddd;
                }
                QLineEdit {
                    background-color: #1e1e1e;
                    color: #ffffff;
                    padding: 6px;
                    border-radius: 6px;
                    border: 1px solid #333333;
                }
                QListWidget {
                    background-color: #1e1e1e;
                    color: #ffffff;
                    border: 1px solid #333333;
                    padding: 4px;
                }
                QPushButton {
                    background-color: #3f51b5;
                    color: white;
                    padding: 8px;
                    border-radius: 6px;
                }
                QPushButton:hover {
                    background-color: #5c6bc0;
                }
            """
        else:  # light theme
            return """
                QDialog {
                    background-color: #ffffff;
                    color: #000000;
                    border-radius: 10px;
                }
                QLabel {
                    color: #333333;
                }
                QLineEdit {
                    background-color: #f0f0f0;
                    color: #000000;
                    padding: 6px;
                    border-radius: 6px;
                    border: 1px solid #cccccc;
                }
                QListWidget {
                    background-color: #f9f9f9;
                    color: #000000;
                    border: 1px solid #cccccc;
                    padding: 4px;
                }
                QPushButton {
                    background-color: #2196f3;
                    color: white;
                    padding: 8px;
                    border-radius: 6px;
                }
                QPushButton:hover {
                    background-color: #42a5f5;
                }
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
        self.songs = [p.split("\\")[-1] for p in self.songs_path]
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

        # Initialize favorites before calling refresh_lists
        self.favorites = ["Favorite Song 1", "Favorite Song 2", "Favorite Song 3"]  # not implemented yet
        self.playlists = self.playlist_manager.get_all_playlists()

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

        # Now safe to call refresh_lists
        self.refresh_lists()

    def refresh_lists(self):
        """Refresh playlists and favorites from the manager."""
        self.playlists = self.playlist_manager.get_all_playlists()
        if hasattr(self.playlist_manager, 'get_favorites'):
            self.favorites = self.playlist_manager.get_favorites()
            
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

        # Draw top buttons
        for name, rect in self.top_buttons.items():
            label = "Queue 🎶" if name == "toggle_queue" else name.capitalize()
            self.draw_button(painter, rect, label, hovered=(self.hovered_button == name))

        # Draw rotating CD
        center = QPointF(self.width() / 2, 190)
        radius = 90
        painter.save()
        painter.translate(center)
        painter.rotate(self.rotation_angle if self.is_playing else 0)
        self.draw_cd(painter, radius)
        painter.restore()

        # Draw volume indicator and list
        self.draw_volume_indicator(painter)
        self.draw_list(painter, 30, 340, self.width() - 240, 310)

        # Draw bottom buttons
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
        """Draw the current volume level."""
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
        if not items:  # Handle empty list
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
            painter.drawText(r, Qt.AlignmentFlag.AlignVCenter, items[i])
        painter.restore()

    def show_context_menu(self, global_pos):
        menu = QMenu()
        play_action = menu.addAction("▶️ Play")
        play_next_action = menu.addAction("⏭️ Play Next")
        add_fav_action = menu.addAction("❤️ Add to Favorites")
        add_playlist_action = menu.addAction("➕ Add to Playlist")
        remove_from_queue = menu.addAction("❌ Remove from Queue")

        action = menu.exec(global_pos)
        if action == play_action and self.get_current_list():
            self.backend.audio_controls.queue = self.songs_path
            self.backend.audio_controls.song_pointer = self.selected_index
            self.backend.start()
            self.backend.audio_controls.is_paused = False
            self.is_playing = True
        elif action == play_next_action and self.get_current_list():
            self.backend.playnext(self.songs_path[self.selected_index], self.selected_index)
        elif action == add_fav_action and self.get_current_list():
            self.favorites.append(self.get_current_list()[self.selected_index])
            print(f"Added to favorites: {self.get_current_list()[self.selected_index]}")
        elif action == add_playlist_action and self.get_current_list():
            self.playlists.append(self.get_current_list()[self.selected_index])
            print(f"Added to playlist: {self.get_current_list()[self.selected_index]}")
        elif action == remove_from_queue and self.backend.audio_controls.queue:
            self.backend.remove_from_queue(self.songs_path[self.selected_index])
        self.refresh_lists()
        self.update()

    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        amt = -1 if delta > 0 else 1
        maxs = max(0, len(self.get_current_list()) - (310 // 30))
        self.scroll_offset = max(0, min(self.scroll_offset + amt, maxs))
        self.update()

    def get_current_list(self):
        """Return the current list based on the view."""
        return {
            "songs": self.songs,
            "playlists": self.playlists,
            "favorites": self.favorites
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
                    self.backend.audio_controls.queue = self.songs_path
                    self.backend.audio_controls.song_pointer = idx
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
        """Update the queue display with the current queue state."""
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
        """Handle clicks on top buttons."""
        if name == "playlists":
            self.current_view, self.selected_index = "playlists", 0
        elif name == "favorites":
            self.current_view, self.selected_index = "favorites", 0
        elif name == "theme":
            self.toggle_theme()
        elif name == "list":
            self.current_view, self.selected_index = "songs", 0
        elif name == "toggle_queue":
            self.queue_visible = not self.queue_visible
            self.update_queue_display()
        self.update()

    def handle_bottom_button(self, name):
        """Handle clicks on bottom control buttons."""
        current_list = self.get_current_list()

        if name == "play":
            if not self.is_playing and self.songs_path:
                self.backend.audio_controls.queue = self.songs_path
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

        elif name == "add_fav" and current_list:
            song = current_list[self.selected_index]
            if song not in self.favorites:
                self.favorites.append(song)
                print(f"Added to favorites: {song}")
            else:
                print(f"Already in favorites: {song}")

        elif name == "add_playlist":
            if current_list:
                song = current_list[self.selected_index]
                existing_playlists = self.playlist_manager.get_all_playlists()

                dialog = PlaylistDialog(self, existing_playlists)
                if dialog.exec():
                    selected_name = dialog.selected_playlist
                    if selected_name not in existing_playlists:
                        self.playlist_manager.add_playlist(selected_name, [song])
                    else:
                        self.playlist_manager.add_song_to_playlist(selected_name, song)



        elif name == "volume_up":
            self.backend.volume_up()

        elif name == "volume_down":
            self.backend.volume_down()

        self.refresh_lists()
        self.update()

    def toggle_theme(self):
        """Switch between light and dark themes."""
        self.theme_name = "apple_dark" if self.theme_name == "apple" else "apple"
        self.theme = self.themes[self.theme_name]

    def keyPressEvent(self, event):
        """Handle keyboard navigation."""
        max_idx = len(self.get_current_list()) - 1
        if not max_idx >= 0:
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
        elif event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and self.songs_path:
            self.backend.audio_controls.queue = self.songs_path
            self.backend.audio_controls.song_pointer = self.selected_index
            self.backend.start()
            self.backend.audio_controls.is_paused = False
            self.is_playing = True
        self.update_queue_display()
        self.update()