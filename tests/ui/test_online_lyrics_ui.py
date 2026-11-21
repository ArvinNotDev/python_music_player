from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from core.metadata.lyrics_service import LyricsLookupResult, parse_lrc
from core.models import LyricsDocument, LyricsLine
from ui.pages.lyrics import LyricsPage
from ui.pages.settings import SettingsPage


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


TRACK = {
    "id": "lyrics-ui-track",
    "title": "Northern Lights",
    "artist": "Mira Vale",
    "album": "First Light",
    "duration_ms": 245_000,
}


class Settings:
    def __init__(self):
        self.values = {}

    def get(self, key, default=None):
        return self.values.get(key, default)

    def set(self, key, value):
        self.values[key] = value


def test_lyrics_page_loading_success_and_synced_plain_switch(qapp):
    page = LyricsPage()
    page.set_loading(TRACK)
    assert not page.state_card.isHidden()
    assert "Loading" in page.state_title.text()

    plain = LyricsDocument([LyricsLine("First line"), LyricsLine("Second line")], "plain")
    synced = parse_lrc("[00:01.00]First line\n[00:05.00]Second line")
    result = LyricsLookupResult(
        status="found",
        document=synced,
        plain_document=plain,
        synced_document=synced,
        source="LRCLIB",
        attribution_url="https://lrclib.net",
    )
    page.set_lookup_result(TRACK, result)

    assert page.state_card.isHidden()
    assert not page.format_selector.isHidden()
    assert page.source_label.text().find("LRCLIB") >= 0
    assert page.list.count() == 2
    assert page.lines[0][0] == 1000

    page.format_selector.setCurrentIndex(1)
    assert page.document.format == "plain"
    assert page.list.item(0).text() == "First line"
    page.close()


def test_lyrics_page_displays_no_results_and_rate_limit_states(qapp):
    page = LyricsPage()
    page.set_lookup_result(
        TRACK,
        LyricsLookupResult(status="not_found", message="No matching lyrics were found."),
    )
    assert not page.state_card.isHidden()
    assert page.state_title.text() == "No lyrics found"
    assert page.retry_button.isEnabled()
    assert page.list.isHidden()

    page.set_lookup_result(
        TRACK,
        LyricsLookupResult(status="rate_limited", retry_after=31, message="LRCLIB rate limit reached."),
    )
    assert page.state_title.text() == "Please wait before retrying"
    assert "31 seconds" in page.state_message.text()
    page.close()


def test_lrc_page_sync_survives_forward_backward_seek_and_offset(qapp):
    page = LyricsPage()
    document = parse_lrc(
        "[offset:1000]\n"
        "[00:01.00][00:02.00]Repeated line\n"
        "[00:04.00]Final line"
    )
    page.set_track_lyrics(TRACK, document)

    page.set_position(2.5)
    assert page.active_line == 0
    page.set_position(3.5)
    assert page.active_line == 1
    page.set_position(5.5)
    assert page.active_line == 2
    page.set_position(1.0)
    assert page.active_line == -1
    page.set_position(5.2)
    assert page.active_line == 2
    page.close()


def test_online_lyrics_preference_defaults_on_and_persists(qapp):
    settings = Settings()
    page = SettingsPage(settings, None, None)

    assert page.online_lyrics.isChecked() is True
    page.online_lyrics.setChecked(False)
    assert settings.get("lyrics.auto_online") is False
    page.online_lyrics.setChecked(True)
    assert settings.get("lyrics.auto_online") is True
    page.close()


def test_lyrics_page_instrumental_and_network_error_states(qapp):
    page = LyricsPage()
    page.set_lookup_result(TRACK, LyricsLookupResult(status="instrumental", source="LRCLIB", attribution_url="https://lrclib.net"))
    assert page.state_title.text() == "Instrumental track"
    assert page.sync_label.text() == "Instrumental"
    assert page.document is None

    page.set_lookup_result(
        TRACK,
        LyricsLookupResult(status="network_error", message="Check the internet connection and retry."),
    )
    assert page.state_title.text() == "Lyrics service unavailable"
    assert "internet connection" in page.state_message.text()
    assert page.retry_button.isEnabled()
    page.close()


def test_lyrics_page_ambiguous_matches_require_explicit_selection(qapp):
    from core.metadata.online_lyrics import LyricsCandidate

    page = LyricsPage()
    candidates = [
        LyricsCandidate("LRCLIB", "Northern Lights", "Mira Vale", "First Light", 245, synced_lyrics="[00:01.00]One"),
        LyricsCandidate("LRCLIB", "Northern Lights", "Mira Vale", "Acoustic Sessions", 246, plain_lyrics="Two"),
    ]
    result = LyricsLookupResult(
        status="ambiguous",
        candidates=candidates,
        message="Choose the correct recording.",
        source="LRCLIB",
    )
    selected = []
    page.candidateSelected.connect(selected.append)
    page.set_lookup_result(TRACK, result)

    assert page.state_title.text() == "Choose the matching recording"
    assert page.candidate_selector.count() == 2
    assert page.list.isHidden()
    page.candidate_selector.setCurrentIndex(1)
    page.use_candidate_button.click()
    assert selected == [candidates[1]]
    page.close()
