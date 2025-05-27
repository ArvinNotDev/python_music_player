import sys
import os

# Add the parent directory (python_music_player) to sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from ui.ui_manager import start_ui

def main():
    start_ui()

if __name__ == "__main__":
    main()