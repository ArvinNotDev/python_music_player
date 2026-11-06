from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from ui.components.command_palette import CommandPalette
from ui.components.visualizer import PlaybackVisualizer
from ui.dialogs.sleep_timer import SleepTimerDialog


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def test_command_palette_filters_and_dispatches(qapp):
    palette = CommandPalette()
    palette.set_commands([
        {
            "id": "page:lyrics",
            "title": "Open lyrics",
            "description": "View synchronized lyrics",
            "shortcut": "Ctrl+L",
        },
        {
            "id": "action:sleep",
            "title": "Start sleep timer",
            "description": "Pause playback after a delay",
            "shortcut": "",
        },
    ])
    palette.search.setText("synchronized")
    assert palette.list_widget.count() == 1
    assert palette.list_widget.item(0).data(256) == "page:lyrics"

    activated = []
    palette.commandActivated.connect(activated.append)
    palette._activate_current()
    assert activated == ["page:lyrics"]
    palette.close()


def test_sleep_timer_dialog_has_safe_duration_bounds(qapp):
    dialog = SleepTimerDialog(default_minutes=45)
    assert dialog.minutes_input.minimum() == 1
    assert dialog.minutes_input.maximum() == 240
    assert dialog.duration_minutes == 45
    dialog.minutes_input.setValue(90)
    assert dialog.duration_minutes == 90
    dialog.close()


def test_playback_visualizer_respects_motion_setting(qapp):
    visualizer = PlaybackVisualizer()
    visualizer.set_animations_enabled(False)
    visualizer.set_playing(True)
    assert not visualizer._timer.isActive()

    visualizer.set_animations_enabled(True)
    assert visualizer._timer.isActive()
    visualizer.set_playing(False)
    assert not visualizer._timer.isActive()
    visualizer.close()
