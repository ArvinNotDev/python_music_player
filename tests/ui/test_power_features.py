from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QImage, QPainter
from PySide6.QtWidgets import QApplication, QStyleOptionViewItem

from ui.components.track_table import TrackTable
from ui.delegates.artwork import ArtworkDelegate
from ui.models import TrackTableModel

from ui.components.command_palette import CommandPalette
from ui.components.visualizer import PlaybackVisualizer
from ui.dialogs.sleep_timer import SleepTimerDialog
from ui.pages.now_playing import NowPlayingPage
from ui.player.playback_bar import PlaybackBar


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def test_artwork_delegate_reads_track_role_through_proxy_model(qapp):
    track = {
        "id": "proxy-track-1",
        "title": "Proxy artwork test",
        "artist": "Test artist",
        "album": "Test album",
        "duration": 120,
    }
    widget = TrackTable([track], metadata_service=None, context_actions=False)
    widget.resize(640, 300)
    widget.show()
    qapp.processEvents()

    proxy = widget.proxy_model
    index = proxy.index(0, 0)
    assert index.isValid()
    assert index.data(TrackTableModel.TrackRole) == track

    delegate = widget.table.itemDelegateForColumn(0)
    assert isinstance(delegate, ArtworkDelegate)
    image = QImage(64, 64, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    option = QStyleOptionViewItem()
    option.rect = QRect(0, 0, 58, 58)
    delegate.paint(painter, option, index)
    painter.end()

    widget.close()
    assert not image.isNull()


class RepeatController:
    def __init__(self):
        self.repeat_mode = "off"

    def set_repeat_mode(self, mode):
        self.repeat_mode = mode


def test_repeat_button_cycles_three_modes_with_distinct_repeat_one_icon(qapp):
    controller = RepeatController()
    bar = PlaybackBar(controller)
    errors = []
    bar.errorOccurred.connect(errors.append)

    assert not bar.repeat_button.isCheckable()
    assert bar.repeat_mode == "off"

    bar.repeat_button.click()
    assert controller.repeat_mode == "all"
    assert bar.repeat_mode == "all"
    assert bar.repeat_button.toolTip() == "Repeat all"
    all_icon_key = bar.repeat_button.icon().cacheKey()

    bar.repeat_button.click()
    assert controller.repeat_mode == "one"
    assert bar.repeat_mode == "one"
    assert bar.repeat_button.toolTip() == "Repeat current track"
    one_icon_key = bar.repeat_button.icon().cacheKey()
    assert one_icon_key != all_icon_key

    bar.repeat_button.click()
    assert controller.repeat_mode == "off"
    assert bar.repeat_mode == "off"
    assert bar.repeat_button.toolTip() == "Repeat off"
    assert errors == []
    bar.close()


def test_repeat_mode_accepts_enum_and_legacy_numeric_values(qapp):
    bar = PlaybackBar(RepeatController())
    bar.set_repeat_mode(2)
    assert bar.repeat_mode == "one"
    bar.set_repeat_mode(1)
    assert bar.repeat_mode == "all"
    bar.set_repeat_mode(0)
    assert bar.repeat_mode == "off"
    bar.close()


def test_now_playing_metadata_card_stays_centered_and_wraps_long_text(qapp):
    page = NowPlayingPage()
    page.resize(820, 760)
    page.set_track({
        "id": "long-track",
        "title": "A Very Long Track Title " * 12,
        "artist": "A Very Long Artist Name " * 8,
        "album": "An Album With A Long Name " * 8,
        "duration": 245,
        "genre": "Ambient · Electronic",
    })
    page.show()
    qapp.processEvents()

    viewport_width = page.scroll.viewport().width()
    assert page.info.maximumWidth() == 760
    assert page.info.width() <= viewport_width
    assert page.cover.width() == 340
    assert page.title.wordWrap()
    assert page.artist.wordWrap()
    assert page.album.wordWrap()
    assert page.info_text.wordWrap()
    page.close()


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
    assert palette.list_widget.item(0).data(Qt.ItemDataRole.UserRole) == "page:lyrics"

    activated = []
    palette.commandActivated.connect(activated.append)
    palette._activate_current()
    assert activated == ["page:lyrics"]
    palette.close()

def test_command_palette_entry_animation_is_configured(qapp):
    palette = CommandPalette()
    palette.set_commands([{"id": "page:home", "title": "Home"}])
    palette.show_palette([{"id": "page:home", "title": "Home"}])
    qapp.processEvents()
    assert palette.isVisible()
    assert palette._show_animation is not None
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
    visualizer.show()
    qapp.processEvents()
    visualizer.set_animations_enabled(False)
    visualizer.set_playing(True)
    assert not visualizer._timer.isActive()

    visualizer.set_animations_enabled(True)
    assert visualizer._timer.isActive()
    visualizer.set_playing(False)
    assert not visualizer._timer.isActive()
    visualizer.close()
