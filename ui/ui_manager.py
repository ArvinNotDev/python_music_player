from ui.ui import MusicPlayerUI
from PyQt6.QtWidgets import QApplication
import sys


def start_ui():
    app = QApplication(sys.argv)
    player = MusicPlayerUI()
    player.show()
    sys.exit(app.exec())
