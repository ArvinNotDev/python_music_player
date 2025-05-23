from PyQt6.QtCore import Qt, QTimer, QRectF, QPointF
from PyQt6.QtGui import QPainter, QColor, QFont, QPen, QBrush
from PyQt6.QtWidgets import QApplication, QWidget, QMenu, QTextEdit
import sys
import os
import math
from player import Music_player
from files import file_manager

class MusicPlayerUI(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Music Player UI")
        self.resize(800, 700)
        self.file_manager_ = file_manager()
        self.backend = Music_player()
        self.songs_path = self.file_manager_.search()
        self.songs = [p.split("\\")[-1] for p in self.songs_path]
        self.scroll_offset = 0

        self.queue_display = QTextEdit(self)
        self.queue_display.setReadOnly(True)
        self.queue_display.setGeometry(600, 80, 180, 550)
        self.queue_display.hide()
        self.queue_visible = False

        self.themes = {
            "dark": {
                "bg": QColor(18, 18, 18),
                "fg": QColor(230, 230, 230),
                "highlight": QColor(187, 134, 252),
                "button_bg": QColor(31, 31, 31),
                "button_fg": QColor(230, 230, 230)
            },
            "bright": {
                "bg": QColor(240, 240, 240),
                "fg": QColor(30, 30, 30),
                "highlight": QColor(98, 0, 238),
                "button_bg": QColor(224, 224, 224),
                "button_fg": QColor(30, 30, 30)
            }
        }
        self.theme_name = "dark"
        self.theme = self.themes[self.theme_name]

        self.playlists = ["Playlist 1", "Playlist 2", "Road Trip", "Workout Mix"]
        self.favorites = ["Favorite Song 1", "Favorite Song 2", "Favorite Song 3"]

        self.current_view = "songs"
        self.selected_index = 0
        self.is_playing = False
        self.rotation_angle = 0.0

        self.top_buttons = {
            "list": QRectF(260, 20, 80, 40),
            "playlists": QRectF(20, 20, 110, 40),
            "favorites": QRectF(140, 20, 110, 40),
            "theme": QRectF(350, 20, 110, 40),
            "toggle_queue": QRectF(470, 20, 40, 40)
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

    def update_rotation(self):
        if self.is_playing:
            self.rotation_angle = (self.rotation_angle + 0.8) % 360
            self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), self.theme["bg"])

        for name, rect in self.top_buttons.items():
            self.draw_button(painter, rect, name.capitalize(), hovered=(self.hovered_button == name))

        center = QPointF(self.width() / 2, 190)
        radius = 90
        painter.save()
        painter.translate(center)
        painter.rotate(self.rotation_angle if self.is_playing else 0)
        self.draw_cd(painter, radius)
        painter.restore()

        self.draw_volume_indicator(painter)
        self.draw_list(painter, 30, 310, self.width() - 240, 310)

        for name, rect in self.bottom_buttons.items():
            icon = {
                "prev": "⏮",
                "play": "⏸" if self.is_playing else "▶️",
                "next": "⏭",
                "repeat": {1: "🔁", 2: "🔂", 3: "🔀"}[self.backend.audio_controls.repeat],
                "add_fav": "❤️",
                "add_playlist": "➕",
                "volume_down": "🔉",
                "volume_up": "🔊"
            }[name]
            self.draw_button(painter, rect, icon, hovered=(self.hovered_button == name))

    def draw_button(self, painter, rect, text, hovered=False):
        painter.setBrush(QBrush(self.theme["highlight"] if hovered else self.theme["button_bg"]))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(rect, 6, 6)
        painter.setPen(self.theme["button_fg"])
        font = QFont("Arial", 14 if len(text) == 1 else 16)
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
        lh = 30
        painter.setFont(QFont("Arial", 14))
        start = self.scroll_offset
        end = min(start + height // lh, len(items))
        for i in range(start, end):
            r = QRectF(x, y + (i - start) * lh, width, lh)
            if i == self.selected_index:
                painter.fillRect(r, self.theme["highlight"])
                painter.setPen(self.theme["bg"])
            else:
                painter.setPen(self.theme["fg"])
            painter.drawText(r.adjusted(10, 0, 0, 0), Qt.AlignmentFlag.AlignVCenter, items[i])
        painter.restore()

    def show_context_menu(self, global_pos):
        menu = QMenu()
        play_action = menu.addAction("▶️ Play")
        play_next_action = menu.addAction("⏭️ Play Next")
        add_fav_action = menu.addAction("❤️ Add to Favorites")
        add_playlist_action = menu.addAction("➕ Add to Playlist")
        remove_from_queue = menu.addAction("❌ Remove from Queue")

        action = menu.exec(global_pos)

        if action == play_action:
            self.backend.audio_controls.queue = self.songs_path
            self.backend.audio_controls.song_pointer = self.selected_index
            self.backend.start()
            self.backend.audio_controls.is_paused = False
            self.is_playing = True
        elif action == play_next_action:
            self.backend.playnext(self.songs_path[self.selected_index], self.selected_index)
        elif action == add_fav_action:
            print(f"Added to favorites: {self.get_current_list()[self.selected_index]}")
        elif action == add_playlist_action:
            print(f"Added to playlist: {self.get_current_list()[self.selected_index]}")
        elif action == remove_from_queue:
            self.backend.remove_from_queue(self.songs_path[self.selected_index])

        self.update_queue_display()
        self.update()

    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        amt = -1 if delta > 0 else 1
        maxs = max(0, len(self.get_current_list()) - (310 // 30))
        self.scroll_offset = max(0, min(self.scroll_offset + amt, maxs))
        self.update()

    def get_current_list(self):
        if self.current_view == "songs": return self.songs
        if self.current_view == "playlists": return self.playlists
        if self.current_view == "favorites": return self.favorites
        return []

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
            lr = QRectF(30, 310, self.width() - 240, 310)
            if lr.contains(pos):
                idx = int((pos.y() - 310) // 30) + self.scroll_offset
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
            lr = QRectF(30, 310, self.width() - 240, 310)
            if lr.contains(pos):
                idx = int((pos.y() - 310) // 30) + self.scroll_offset
                lst = self.get_current_list()
                if 0 <= idx < len(lst):
                    self.selected_index = idx
                    self.show_context_menu(event.globalPosition().toPoint())
        self.update_queue_display()

    def update_queue_display(self):
        if self.queue_visible:
            self.queue_display.show()
            current_index = self.backend.audio_controls.song_pointer
            queue = self.backend.audio_controls.queue
            formatted = ""
            for i, song in enumerate(queue):
                marker = "🎵 " if i == current_index else "   "
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
        if name == "play":
            if not self.is_playing:
                self.backend.audio_controls.queue = self.songs_path
                self.backend.audio_controls.song_pointer = self.selected_index
                self.backend.start()
            else:
                self.backend.pause()
            self.is_playing = not self.is_playing
        elif name == "prev":
            self.backend.prev_song()
            self.selected_index = self.backend.audio_controls.song_pointer
            self.is_playing = True
        elif name == "next":
            self.backend.next_song()
            self.selected_index = self.backend.audio_controls.song_pointer
            self.is_playing = True
        elif name == "repeat":
            self.backend.toggle_repeat()
            self.songs_path = self.backend.audio_controls.queue
            self.selected_index = self.backend.audio_controls.song_pointer
        elif name == "add_fav":
            print(f"Added to favorites: {self.get_current_list()[self.selected_index]}")
        elif name == "add_playlist":
            print(f"Added to playlist: {self.get_current_list()[self.selected_index]}")
        elif name == "volume_up":
            self.backend.volume_up()
        elif name == "volume_down":
            self.backend.volume_down()

        self.update_queue_display()
        self.update()

    def toggle_theme(self):
        self.theme_name = "light" if self.theme_name == "dark" else "dark"
        self.theme = self.themes[self.theme_name]

    def keyPressEvent(self, event):
        max_idx = len(self.get_current_list()) - 1
        if event.key() == Qt.Key.Key_Up and self.selected_index > 0:
            self.selected_index -= 1
        elif event.key() == Qt.Key.Key_Down and self.selected_index < max_idx:
            self.selected_index += 1
        vis = 310 // 30
        if self.selected_index < self.scroll_offset:
            self.scroll_offset = self.selected_index
        elif self.selected_index >= self.scroll_offset + vis:
            self.scroll_offset = self.selected_index - vis + 1
        self.update_queue_display()
        self.update()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    player = MusicPlayerUI()
    player.show()
    sys.exit(app.exec())
