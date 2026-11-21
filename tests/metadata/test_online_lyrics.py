from __future__ import annotations

import json
from email.message import Message
from io import BytesIO
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlsplit

import pytest

import core.metadata.online_lyrics as online_module
from core.metadata.online_lyrics import (
    LyricsCandidate,
    LyricsProviderResult,
    LyricsRateLimited,
    OnlineLyricsClient,
)
from core.metadata.lyrics_service import LyricsLookupResult, LyricsService
from core.models import LyricsDocument, Track
from database.repositories.track_repository import TrackRepository


def _record(**overrides):
    record = {
        "id": 17,
        "trackName": "Northern Lights",
        "artistName": "Mira Vale",
        "albumName": "First Light",
        "duration": 245,
        "instrumental": False,
        "plainLyrics": "First line\nSecond line",
        "syncedLyrics": "[00:01.00]First line\n[00:05.00]Second line",
    }
    record.update(overrides)
    return record


class _Headers(Message):
    def __init__(self, content_type="application/json", **headers):
        super().__init__()
        self.add_header("Content-Type", content_type)
        for key, value in headers.items():
            self.add_header(key, value)


class _Response:
    def __init__(self, payload, *, content_type="application/json", status=200, headers=None):
        self.status = status
        self.headers = _Headers(content_type, **(headers or {}))
        self._body = payload if isinstance(payload, bytes) else json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, _limit=-1):
        return self._body


def _http_error(request, status, *, headers=None):
    return HTTPError(
        request.full_url,
        status,
        "test response",
        _Headers("application/json", **(headers or {})),
        BytesIO(b'{"message":"test"}'),
    )


def _fast_client(monkeypatch):
    monkeypatch.setattr(online_module.time, "sleep", lambda _seconds: None)
    return OnlineLyricsClient(minimum_gap=0.2)


def test_lrclib_direct_lookup_encodes_parameters_and_converts_duration(monkeypatch):
    requests = []

    def fake_urlopen(request, timeout):
        requests.append((request, timeout))
        return _Response(_record())

    monkeypatch.setattr(online_module, "urlopen", fake_urlopen)
    client = _fast_client(monkeypatch)
    result = client.lookup(
        title="Northern Lights",
        artist="Mira Vale",
        album="First Light",
        duration_ms=245_000,
    )

    assert result.status == "found"
    assert result.candidate is not None
    assert result.candidate.provider == "LRCLIB"
    params = parse_qs(urlsplit(requests[0][0].full_url).query)
    assert params["track_name"] == ["Northern Lights"]
    assert params["artist_name"] == ["Mira Vale"]
    assert params["album_name"] == ["First Light"]
    assert params["duration"] == ["245"]
    assert requests[0][0].get_header("User-agent") == online_module.USER_AGENT
    assert requests[0][1] <= 6.0


def test_lrclib_direct_result_preserves_plain_and_synced_formats(monkeypatch, database, tmp_path):
    monkeypatch.setattr(online_module, "urlopen", lambda request, timeout: _Response(_record()))
    track = Track(None, str(tmp_path / "local.mp3"), title="Northern Lights", artist="Mira Vale", album="First Light", duration_ms=245_000)
    saved, _ = TrackRepository(database).upsert(track)
    service = LyricsService(TrackRepository(database), online_client=_fast_client(monkeypatch))

    result = service.load_lyrics(saved.id)

    assert result.status == "found"
    assert result.source == "LRCLIB"
    assert result.plain_document is not None
    assert result.plain_document.text == "First line\nSecond line"
    assert result.synced_document is not None
    assert [line.timestamp_ms for line in result.synced_document.lines] == [1000, 5000]
    assert result.document is result.synced_document


def test_instrumental_response_is_a_distinct_state(monkeypatch):
    record = _record(instrumental=True, plainLyrics=None, syncedLyrics=None)
    monkeypatch.setattr(online_module, "urlopen", lambda request, timeout: _Response(record))
    result = _fast_client(monkeypatch).lookup(
        title="Northern Lights", artist="Mira Vale", duration_ms=245_000
    )
    assert result.status == "instrumental"
    assert result.candidate.instrumental is True


def test_direct_404_then_search_selects_confident_duration_match(monkeypatch):
    calls = []

    def fake_urlopen(request, timeout):
        calls.append(request.full_url)
        if "/api/get?" in request.full_url:
            raise _http_error(request, 404)
        return _Response([_record(id=18)])

    monkeypatch.setattr(online_module, "urlopen", fake_urlopen)
    result = _fast_client(monkeypatch).lookup(
        title="Northern Lights", artist="Mira Vale", album="First Light", duration_ms=245_000
    )

    assert result.status == "found"
    assert result.candidate.record_id == 18
    assert len(calls) == 2
    assert "/api/search?" in calls[1]


def test_ambiguous_search_does_not_silently_choose_first_record(monkeypatch):
    calls = []

    def fake_urlopen(request, timeout):
        calls.append(request.full_url)
        if "/api/get?" in request.full_url:
            raise _http_error(request, 404)
        return _Response([_record(id=1, albumName="First Light"), _record(id=2, albumName="First Light")])

    monkeypatch.setattr(online_module, "urlopen", fake_urlopen)
    result = _fast_client(monkeypatch).lookup(
        title="Northern Lights", artist="Mira Vale", album="", duration_ms=0
    )

    assert result.status == "ambiguous"
    assert len(result.candidates) == 2
    assert len(calls) == 2


def test_wrong_duration_candidate_is_rejected_before_plain_fallback(monkeypatch):
    calls = []

    def fake_urlopen(request, timeout):
        calls.append(request.full_url)
        if "/api/get?" in request.full_url:
            raise _http_error(request, 404)
        if "/api/search?" in request.full_url:
            return _Response([_record(duration=301)])
        raise _http_error(request, 404)

    monkeypatch.setattr(online_module, "urlopen", fake_urlopen)
    result = _fast_client(monkeypatch).lookup(
        title="Northern Lights", artist="Mira Vale", duration_ms=245_000
    )

    assert result.status == "not_found"
    assert len(calls) == 3
    assert "/v1/" in calls[2]


def test_lyrics_ovh_fallback_uses_encoded_path_components(monkeypatch):
    calls = []

    def fake_urlopen(request, timeout):
        calls.append(request.full_url)
        if "/api/get?" in request.full_url:
            raise _http_error(request, 404)
        if "/api/search?" in request.full_url:
            return _Response([])
        return _Response({"lyrics": "Plain lyrics only"})

    monkeypatch.setattr(online_module, "urlopen", fake_urlopen)
    result = _fast_client(monkeypatch).lookup(
        title="A Song / Live", artist="A&B", duration_ms=0
    )

    assert result.status == "found"
    assert result.candidate.provider == "lyrics.ovh"
    assert result.candidate.plain_lyrics == "Plain lyrics only"
    assert "%2F" in calls[-1] and "%26" in calls[-1]


def test_lrclib_rate_limit_honors_retry_after_and_skips_fallback(monkeypatch):
    calls = []

    def fake_urlopen(request, timeout):
        calls.append(request.full_url)
        raise _http_error(request, 429, headers={"Retry-After": "23"})

    monkeypatch.setattr(online_module, "urlopen", fake_urlopen)
    with pytest.raises(LyricsRateLimited) as caught:
        _fast_client(monkeypatch).lookup(
            title="Northern Lights", artist="Mira Vale", duration_ms=245_000
        )

    assert caught.value.retry_after == 23
    assert len(calls) == 1
    assert "/api/get?" in calls[0]


def test_network_timeout_and_malformed_json_are_rejected(monkeypatch):
    def timeout(_request, timeout):
        raise URLError("timed out")

    monkeypatch.setattr(online_module, "urlopen", timeout)
    with pytest.raises(online_module.LyricsNetworkError):
        _fast_client(monkeypatch).lookup(title="Northern Lights", artist="Mira Vale")

    monkeypatch.setattr(
        online_module,
        "urlopen",
        lambda request, timeout: _Response(b"not-json", content_type="application/json"),
    )
    with pytest.raises(online_module.LyricsMalformedResponse):
        _fast_client(monkeypatch).lookup(title="Northern Lights", artist="Mira Vale")


def test_unexpected_content_type_is_rejected(monkeypatch):
    monkeypatch.setattr(
        online_module,
        "urlopen",
        lambda request, timeout: _Response("<html/>", content_type="text/html"),
    )
    with pytest.raises(online_module.LyricsMalformedResponse):
        _fast_client(monkeypatch).lookup(title="Northern Lights", artist="Mira Vale")


class _FakeOnlineClient:
    def __init__(self, candidate):
        self.candidate = candidate
        self.calls = 0

    def lookup(self, **_metadata):
        self.calls += 1
        return LyricsProviderResult("found", candidate=self.candidate)


def _stored_track(database, tmp_path, *, title="Northern Lights", artist="Mira Vale", album="First Light"):
    path = tmp_path / f"{title.replace(' ', '_')}.mp3"
    path.write_bytes(b"fixture")
    track, _ = TrackRepository(database).upsert(
        Track(None, str(path), title=title, artist=artist, album=album, duration_ms=245_000)
    )
    return track, path


def test_local_sidecar_has_priority_over_online_lookup(database, tmp_path):
    track, path = _stored_track(database, tmp_path)
    path.with_suffix(".lrc").write_text("[00:02.00]Local sidecar", encoding="utf-8")
    client = _FakeOnlineClient(LyricsCandidate("LRCLIB", "Northern Lights", "Mira Vale", synced_lyrics="[00:01.00]Online"))
    service = LyricsService(TrackRepository(database), online_client=client)

    result = service.load_lyrics(track.id)

    assert result.source == "Local sidecar"
    assert result.document.text == "Local sidecar"
    assert client.calls == 0


def test_embedded_lyrics_have_priority_over_online_lookup(monkeypatch, database, tmp_path):
    track, _path = _stored_track(database, tmp_path)
    monkeypatch.setattr("core.metadata.lyrics_service.read_embedded_lyrics", lambda _path: "Embedded words")
    client = _FakeOnlineClient(LyricsCandidate("LRCLIB", "Northern Lights", "Mira Vale", plain_lyrics="Online"))
    result = LyricsService(TrackRepository(database), online_client=client).load_lyrics(track.id)

    assert result.source == "Embedded lyrics"
    assert result.document.text == "Embedded words"
    assert client.calls == 0


def test_successful_results_are_cached_and_cache_expires(database, tmp_path):
    track, _path = _stored_track(database, tmp_path)
    candidate = LyricsCandidate("LRCLIB", "Northern Lights", "Mira Vale", plain_lyrics="Cached line")
    client = _FakeOnlineClient(candidate)
    service = LyricsService(TrackRepository(database), online_client=client)

    first = service.load_lyrics(track.id)
    second = service.load_lyrics(track.id)
    assert first.document.text == second.document.text == "Cached line"
    assert client.calls == 1

    key = service._cache_key(track)
    service._online_cache[key] = (0.0, first)
    third = service.load_lyrics(track.id)
    assert third.document.text == "Cached line"
    assert client.calls == 2


def test_cache_is_separated_by_track_identity_metadata(database, tmp_path):
    first_track, _ = _stored_track(database, tmp_path, title="Northern Lights")
    second_track, _ = _stored_track(database, tmp_path, title="Southern Roads", artist="Mira Vale")
    client = _FakeOnlineClient(LyricsCandidate("LRCLIB", "Northern Lights", "Mira Vale", plain_lyrics="First"))
    service = LyricsService(TrackRepository(database), online_client=client)

    service.load_lyrics(first_track.id)
    service.load_lyrics(second_track.id)
    assert client.calls == 2


def test_disabled_online_lookup_keeps_local_service_available(monkeypatch, database, tmp_path):
    track, _path = _stored_track(database, tmp_path)
    monkeypatch.setattr("core.metadata.lyrics_service.read_embedded_lyrics", lambda _path: None)
    client = _FakeOnlineClient(LyricsCandidate("LRCLIB", "Northern Lights", "Mira Vale", plain_lyrics="Online"))
    result = LyricsService(TrackRepository(database), online_client=client).load_lyrics(
        track.id, online_enabled=False
    )
    assert result.status == "online_disabled"
    assert client.calls == 0


def test_selecting_a_candidate_explicitly_caches_the_chosen_version(database, tmp_path):
    track, _path = _stored_track(database, tmp_path)
    candidate = LyricsCandidate("LRCLIB", "Northern Lights", "Mira Vale", album_name="First Light", plain_lyrics="Chosen")
    service = LyricsService(TrackRepository(database), online_client=_FakeOnlineClient(candidate))
    result = service.select_candidate(track.id, candidate)
    assert result.document.text == "Chosen"
    assert result.source == "LRCLIB"
    assert service.load_lyrics(track.id).document.text == "Chosen"


def test_missing_metadata_does_not_make_network_requests(monkeypatch):
    def unexpected_request(*_args, **_kwargs):
        raise AssertionError("no request should be made without both title and artist")

    monkeypatch.setattr(online_module, "urlopen", unexpected_request)
    result = _fast_client(monkeypatch).lookup(title="Northern Lights", artist="")
    assert result.status == "missing_metadata"


def test_invalid_duration_is_omitted_from_direct_lookup(monkeypatch):
    requests = []

    def fake_urlopen(request, timeout):
        requests.append(request)
        return _Response(_record())

    monkeypatch.setattr(online_module, "urlopen", fake_urlopen)
    result = _fast_client(monkeypatch).lookup(
        title="Northern Lights", artist="Mira Vale", duration_ms="invalid"
    )
    assert result.status == "found"
    params = parse_qs(urlsplit(requests[0].full_url).query)
    assert "duration" not in params


def test_lrclib_server_error_does_not_trigger_plain_fallback(monkeypatch):
    calls = []

    def fake_urlopen(request, timeout):
        calls.append(request.full_url)
        raise _http_error(request, 503, headers={"Retry-After": "10"})

    monkeypatch.setattr(online_module, "urlopen", fake_urlopen)
    with pytest.raises(online_module.LyricsNetworkError):
        _fast_client(monkeypatch).lookup(
            title="Northern Lights", artist="Mira Vale", duration_ms=245_000
        )
    assert len(calls) == 1
    assert "/api/get?" in calls[0]


def test_lyrics_ovh_malformed_response_is_rejected(monkeypatch):
    def fake_urlopen(request, timeout):
        if "/api/get?" in request.full_url:
            raise _http_error(request, 404)
        if "/api/search?" in request.full_url:
            return _Response([])
        return _Response({"unexpected": "shape"})

    monkeypatch.setattr(online_module, "urlopen", fake_urlopen)
    with pytest.raises(online_module.LyricsMalformedResponse):
        _fast_client(monkeypatch).lookup(
            title="Northern Lights", artist="Mira Vale", duration_ms=0
        )


def test_service_exposes_rate_limit_as_structured_retry_state(database, tmp_path):
    track, _path = _stored_track(database, tmp_path)

    class LimitedClient:
        def lookup(self, **_metadata):
            raise LyricsRateLimited(42)

    result = LyricsService(TrackRepository(database), online_client=LimitedClient()).load_lyrics(track.id)
    assert result.status == "rate_limited"
    assert result.retry_after == 42
    assert "42 seconds" in result.message


def test_retry_after_blocks_subsequent_lrclib_requests(monkeypatch):
    calls = []

    def fake_urlopen(request, timeout):
        calls.append(request.full_url)
        raise _http_error(request, 429, headers={"Retry-After": "18"})

    monkeypatch.setattr(online_module, "urlopen", fake_urlopen)
    client = _fast_client(monkeypatch)
    with pytest.raises(LyricsRateLimited) as first:
        client.lookup(title="Northern Lights", artist="Mira Vale")
    assert first.value.retry_after == 18

    with pytest.raises(LyricsRateLimited) as second:
        client.lookup(title="Northern Lights", artist="Mira Vale")
    assert second.value.retry_after is not None
    assert 0 < second.value.retry_after <= 18
    assert len(calls) == 1
