"""Responsible LRCLIB and lyrics.ovh clients for on-demand lyrics lookup."""

from __future__ import annotations

import json
import re
import socket
import threading
import time
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from difflib import SequenceMatcher
from email.utils import parsedate_to_datetime
from math import ceil
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen


USER_AGENT = "RW Player/1.0.0 (https://github.com/ArvinNotDev/python_music_player)"
LRCLIB_BASE_URL = "https://lrclib.net"
LYRICS_OVH_BASE_URL = "https://api.lyrics.ovh"


class LyricsProviderError(RuntimeError):
    """A lyrics provider returned an unusable response."""


class LyricsRateLimited(LyricsProviderError):
    """LRCLIB rejected a request because its client is rate limited."""

    def __init__(self, retry_after: int | None = None):
        self.retry_after = retry_after
        suffix = f" Retry after {retry_after} seconds." if retry_after is not None else ""
        super().__init__(f"LRCLIB rate limit reached.{suffix}")


class LyricsNetworkError(LyricsProviderError):
    """A provider could not be reached or returned a transient server error."""


class LyricsMalformedResponse(LyricsProviderError):
    """A provider response did not match its documented JSON contract."""


@dataclass(slots=True, frozen=True)
class LyricsCandidate:
    """A candidate returned by LRCLIB, without exposing its lyrics in UI text."""

    provider: str
    track_name: str
    artist_name: str
    album_name: str = ""
    duration: float | None = None
    plain_lyrics: str = ""
    synced_lyrics: str = ""
    instrumental: bool = False
    record_id: int | str | None = None

    @property
    def has_plain_lyrics(self) -> bool:
        return bool(self.plain_lyrics.strip())

    @property
    def has_synced_lyrics(self) -> bool:
        return bool(self.synced_lyrics.strip())

    @property
    def has_lyrics(self) -> bool:
        return self.instrumental or self.has_plain_lyrics or self.has_synced_lyrics


@dataclass(slots=True)
class LyricsProviderResult:
    status: str
    candidate: LyricsCandidate | None = None
    candidates: list[LyricsCandidate] | None = None
    message: str = ""
    retry_after: int | None = None


def normalize_match_text(value: str) -> str:
    """Normalize comparable metadata without changing the original track fields."""
    normalized = unicodedata.normalize("NFKC", str(value or "")).casefold()
    normalized = "".join(character for character in normalized if character.isalnum() or character.isspace())
    return " ".join(normalized.split())


def _similarity(left: str, right: str) -> float:
    first, second = normalize_match_text(left), normalize_match_text(right)
    if not first or not second:
        return 0.0
    if first == second:
        return 1.0
    return SequenceMatcher(None, first, second).ratio()


def _retry_after_seconds(value: str | None) -> int | None:
    if not value:
        return None
    try:
        return max(0, int(ceil(float(value.strip()))))
    except (TypeError, ValueError):
        try:
            retry_at = parsedate_to_datetime(value)
            if retry_at.tzinfo is None:
                retry_at = retry_at.replace(tzinfo=timezone.utc)
            return max(0, int(ceil((retry_at - datetime.now(timezone.utc)).total_seconds())))
        except (TypeError, ValueError, OverflowError):
            return None


class OnlineLyricsClient:
    """Small standard-library HTTP client; all LRCLIB calls are serialized."""

    def __init__(self, *, timeout: float = 4.0, minimum_gap: float = 0.35):
        self.timeout = max(1.0, float(timeout))
        self.minimum_gap = max(0.2, min(0.5, float(minimum_gap)))
        self._lrclib_lock = threading.Lock()
        self._last_lrclib_request = 0.0
        self._lrclib_blocked_until = 0.0

    def _rate_limit_error(self, headers) -> LyricsRateLimited:
        retry_after = _retry_after_seconds(headers.get("Retry-After") if headers else None)
        if retry_after is not None:
            self._lrclib_blocked_until = max(
                self._lrclib_blocked_until,
                time.monotonic() + retry_after,
            )
        return LyricsRateLimited(retry_after)

    def _request_json(
        self,
        url: str,
        *,
        provider: str,
        allow_not_found: bool = False,
        deadline: float | None = None,
    ):
        request = Request(
            url,
            headers={
                "Accept": "application/json",
                "User-Agent": USER_AGENT,
            },
            method="GET",
        )

        def perform():
            request_timeout = self.timeout
            if deadline is not None:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise LyricsNetworkError(f"{provider} lookup timed out.")
                request_timeout = min(request_timeout, remaining)
            try:
                with urlopen(request, timeout=request_timeout) as response:
                    status = int(response.status)
                    headers = response.headers
                    content_type = headers.get_content_type().casefold()
                    body = response.read(1_500_001)
            except HTTPError as exc:
                status = int(exc.code)
                headers = exc.headers
                body = exc.read(1_500_001) if exc.fp else b""
                if status == 404 and allow_not_found:
                    return None
                if status == 429:
                    raise self._rate_limit_error(headers) from exc
                if status in {500, 502, 503, 504}:
                    raise LyricsNetworkError(f"{provider} is temporarily unavailable (HTTP {status}).") from exc
                raise LyricsProviderError(f"{provider} returned HTTP {status}.") from exc
            except (URLError, TimeoutError, socket.timeout, OSError) as exc:
                raise LyricsNetworkError(f"Could not reach {provider}. Check the internet connection and retry.") from exc

            if status == 404 and allow_not_found:
                return None
            if status == 429:
                raise self._rate_limit_error(headers)
            if status in {500, 502, 503, 504}:
                raise LyricsNetworkError(f"{provider} is temporarily unavailable (HTTP {status}).")
            if status < 200 or status >= 300:
                raise LyricsProviderError(f"{provider} returned HTTP {status}.")
            if len(body) > 1_500_000:
                raise LyricsMalformedResponse(f"{provider} returned an unexpectedly large response.")
            if not (content_type == "application/json" or content_type.endswith("+json")):
                raise LyricsMalformedResponse(f"{provider} returned an unexpected content type.")
            try:
                return json.loads(body.decode("utf-8-sig"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise LyricsMalformedResponse(f"{provider} returned invalid JSON.") from exc

        if provider != "LRCLIB":
            return perform()
        with self._lrclib_lock:
            blocked_for = self._lrclib_blocked_until - time.monotonic()
            if blocked_for > 0:
                raise LyricsRateLimited(int(ceil(blocked_for)))
            elapsed = time.monotonic() - self._last_lrclib_request
            if self._last_lrclib_request and elapsed < self.minimum_gap:
                gap = self.minimum_gap - elapsed
                if deadline is not None and gap >= deadline - time.monotonic():
                    raise LyricsNetworkError("LRCLIB lookup timed out.")
                time.sleep(gap)
            try:
                return perform()
            finally:
                self._last_lrclib_request = time.monotonic()

    @staticmethod
    def _candidate(record: object, provider: str = "LRCLIB") -> LyricsCandidate | None:
        if not isinstance(record, dict):
            return None
        title = record.get("trackName") or record.get("name") or ""
        artist = record.get("artistName") or ""
        if not isinstance(title, str) or not isinstance(artist, str):
            return None
        duration_value = record.get("duration")
        try:
            duration = float(duration_value) if duration_value is not None else None
            if duration is not None and (duration <= 0 or duration > 3600):
                duration = None
        except (TypeError, ValueError):
            duration = None
        plain = record.get("plainLyrics") or ""
        synced = record.get("syncedLyrics") or ""
        if not isinstance(plain, str) or not isinstance(synced, str):
            return None
        record_id = record.get("id")
        if isinstance(record_id, bool) or not isinstance(record_id, (int, str)):
            record_id = None
        return LyricsCandidate(
            provider=provider,
            track_name=title.strip(),
            artist_name=artist.strip(),
            album_name=str(record.get("albumName") or "").strip(),
            duration=duration,
            plain_lyrics=plain,
            synced_lyrics=synced,
            instrumental=bool(record.get("instrumental", False)),
            record_id=record_id,
        )

    @staticmethod
    def _match_score(
        candidate: LyricsCandidate,
        title: str,
        artist: str,
        album: str,
        duration_seconds: int | None,
    ) -> float | None:
        title_score = _similarity(title, candidate.track_name)
        artist_score = _similarity(artist, candidate.artist_name)
        if title_score < 0.94 or artist_score < 0.92:
            return None

        duration_score = 0.0
        if duration_seconds and candidate.duration:
            difference = abs(candidate.duration - duration_seconds)
            if difference > 2.0:
                return None
            duration_score = 1.0 - min(difference, 2.0) / 2.0
        album_score = _similarity(album, candidate.album_name) if album and candidate.album_name else 0.0
        if album and candidate.album_name and album_score < 0.72:
            return None
        if duration_seconds is None and album and candidate.album_name and album_score < 0.78:
            return None
        return title_score * 0.46 + artist_score * 0.44 + album_score * 0.06 + duration_score * 0.04

    @staticmethod
    def _direct_match(
        candidate: LyricsCandidate,
        title: str,
        artist: str,
        album: str,
        duration_seconds: int | None,
    ) -> bool:
        if _similarity(title, candidate.track_name) < 0.94:
            return False
        if _similarity(artist, candidate.artist_name) < 0.92:
            return False
        if duration_seconds and candidate.duration and abs(candidate.duration - duration_seconds) > 2.0:
            return False
        if album and candidate.album_name and _similarity(album, candidate.album_name) < 0.72:
            return False
        if not duration_seconds and album and candidate.album_name:
            return _similarity(album, candidate.album_name) >= 0.78
        return True

    def lookup(
        self,
        *,
        title: str,
        artist: str,
        album: str = "",
        duration_ms: int = 0,
    ) -> LyricsProviderResult:
        title, artist, album = str(title or "").strip(), str(artist or "").strip(), str(album or "").strip()
        if not title or not artist:
            return LyricsProviderResult("missing_metadata", message="A track title and artist are required for online lookup.")

        duration_seconds = None
        try:
            milliseconds = int(duration_ms or 0)
            if milliseconds > 0:
                seconds = int(round(milliseconds / 1000.0))
                if 1 <= seconds <= 3600:
                    duration_seconds = seconds
        except (TypeError, ValueError, OverflowError):
            duration_seconds = None

        params = {"track_name": title, "artist_name": artist}
        if album:
            params["album_name"] = album
        if duration_seconds is not None:
            params["duration"] = str(duration_seconds)
        direct_url = f"{LRCLIB_BASE_URL}/api/get?{urlencode(params)}"

        deadline = time.monotonic() + 4.5
        direct_record = self._request_json(
            direct_url,
            provider="LRCLIB",
            allow_not_found=True,
            deadline=deadline,
        )
        if direct_record is not None:
            if not isinstance(direct_record, dict):
                raise LyricsMalformedResponse("LRCLIB direct lookup returned an unexpected response structure.")
            direct_candidate = self._candidate(direct_record)
            if direct_candidate and direct_candidate.has_lyrics and self._direct_match(
                direct_candidate, title, artist, album, duration_seconds
            ):
                return LyricsProviderResult(
                    "instrumental" if direct_candidate.instrumental else "found",
                    candidate=direct_candidate,
                )

        query = " ".join(part for part in (title, artist, album) if part)
        search_url = f"{LRCLIB_BASE_URL}/api/search?{urlencode({'q': query})}"
        search_data = self._request_json(search_url, provider="LRCLIB", deadline=deadline)
        if not isinstance(search_data, list):
            raise LyricsMalformedResponse("LRCLIB search returned an unexpected response structure.")

        matched: list[tuple[float, LyricsCandidate]] = []
        for record in search_data:
            candidate = self._candidate(record)
            if candidate is None or not candidate.has_lyrics:
                continue
            score = self._match_score(candidate, title, artist, album, duration_seconds)
            if score is not None:
                matched.append((score, candidate))
        matched.sort(key=lambda item: item[0], reverse=True)

        if matched:
            if len(matched) == 1:
                candidate = matched[0][1]
                if duration_seconds and candidate.duration is None and album and _similarity(album, candidate.album_name) < 0.9:
                    return LyricsProviderResult("ambiguous", candidates=[candidate])
                return LyricsProviderResult(
                    "instrumental" if candidate.instrumental else "found",
                    candidate=candidate,
                )

            if duration_seconds is not None:
                duration_matches = [
                    candidate for _, candidate in matched
                    if candidate.duration is not None and abs(candidate.duration - duration_seconds) <= 2.0
                ]
                if len(duration_matches) == 1:
                    candidate = duration_matches[0]
                    return LyricsProviderResult(
                        "instrumental" if candidate.instrumental else "found",
                        candidate=candidate,
                    )

            if album:
                album_matches = [
                    candidate for _, candidate in matched
                    if candidate.album_name and _similarity(album, candidate.album_name) >= 0.94
                ]
                if len(album_matches) == 1:
                    candidate = album_matches[0]
                    return LyricsProviderResult(
                        "instrumental" if candidate.instrumental else "found",
                        candidate=candidate,
                    )
            return LyricsProviderResult(
                "ambiguous",
                candidates=[candidate for _, candidate in matched[:8]],
                message="Several recordings match this track. Choose the correct version.",
            )

        fallback_url = (
            f"{LYRICS_OVH_BASE_URL}/v1/{quote(artist, safe='')}/{quote(title, safe='')}"
        )
        fallback_data = self._request_json(
            fallback_url,
            provider="lyrics.ovh",
            allow_not_found=True,
            deadline=deadline,
        )
        if fallback_data is None:
            return LyricsProviderResult("not_found", message="No matching lyrics were found online.")
        if not isinstance(fallback_data, dict) or not isinstance(fallback_data.get("lyrics"), str):
            raise LyricsMalformedResponse("lyrics.ovh returned an unexpected response structure.")
        plain = fallback_data["lyrics"].strip()
        if not plain:
            return LyricsProviderResult("not_found", message="No matching lyrics were found online.")
        candidate = LyricsCandidate(
            provider="lyrics.ovh",
            track_name=title,
            artist_name=artist,
            album_name=album,
            duration=duration_seconds,
            plain_lyrics=plain,
        )
        return LyricsProviderResult("found", candidate=candidate)
