from ui.ui import MusicPlayerUI
from PyQt6.QtWidgets import QApplication
from playlist.playlists_manager import PlaylistManager
import sys


def start_ui():
    app = QApplication(sys.argv)
    playlist_manager = PlaylistManager()
    player = MusicPlayerUI(playlist_manager)
    player.show()
    sys.exit(app.exec())
