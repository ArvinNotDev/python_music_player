"""Local and on-demand online lyrics retrieval with bounded successful-result caching."""

from __future__ import annotations

import copy
import logging
import os
import tempfile
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from core.models import LyricsDocument, LyricsLine
from database.repositories.track_repository import TrackRepository
from .online_lyrics import (
    LyricsCandidate,
    LyricsNetworkError,
    LyricsProviderError,
    LyricsRateLimited,
    OnlineLyricsClient,
    normalize_match_text,
)
from .tagging import MetadataWriteError, read_embedded_lyrics, write_embedded_lyrics

_TIMESTAMP = __import__("re").compile(r"\[(\d{1,4}):([0-5]?\d)(?:[.:](\d{1,3}))?\](?!\d)")
_META = __import__("re").compile(r"\[([A-Za-z][A-Za-z0-9_-]*):(.*?)\]")
logger = logging.getLogger(__name__)


class LyricsError(RuntimeError):
    """Lyrics could not be read, parsed, or saved as requested."""


@dataclass(slots=True)
class LyricsSaveResult:
    document: LyricsDocument
    storage: str
    path: str | None = None
    embedded: bool = False


@dataclass(slots=True)
class LyricsLookupResult:
    """UI-safe lookup outcome; lyric text is kept in documents, not log messages."""

    status: str
    document: LyricsDocument | None = None
    plain_document: LyricsDocument | None = None
    synced_document: LyricsDocument | None = None
    source: str = ""
    attribution_url: str = ""
    matched_track: dict[str, Any] = field(default_factory=dict)
    candidates: list[LyricsCandidate] = field(default_factory=list)
    message: str = ""
    retry_after: int | None = None

    @property
    def is_synchronized(self) -> bool:
        return self.synced_document is not None


def _fraction_ms(value: str | None) -> int:
    if not value:
        return 0
    if len(value) == 1:
        return int(value) * 100
    if len(value) == 2:
        return int(value) * 10
    return int(value[:3])


def parse_lrc(content: str) -> LyricsDocument:
    """Parse standard LRC timestamps, repeated timestamps, metadata, and offsets."""
    if not isinstance(content, str):
        raise TypeError("LRC content must be text")
    metadata: dict[str, str] = {}
    offset_ms = 0
    lines: list[LyricsLine] = []
    for raw_line in content.splitlines():
        for match in _META.finditer(raw_line):
            key, value = match.group(1), match.group(2)
            if key.casefold() == "offset":
                try:
                    offset_ms = int(value.strip())
                except ValueError:
                    pass
            elif key.casefold() not in {"ar", "ti", "al", "by", "re", "ve", "length", "offset"}:
                metadata[key] = value
            else:
                metadata[key.casefold()] = value
        matches = list(_TIMESTAMP.finditer(raw_line))
        if not matches:
            if _META.fullmatch(raw_line.strip()):
                continue
            lines.append(LyricsLine(raw_line))
            continue
        lyric_text = _TIMESTAMP.sub("", raw_line).strip()
        for match in matches:
            minutes = int(match.group(1))
            seconds = int(match.group(2))
            stamp = max(0, minutes * 60_000 + seconds * 1000 + _fraction_ms(match.group(3)) + offset_ms)
            lines.append(LyricsLine(lyric_text, stamp))
    return LyricsDocument(lines, "lrc", metadata=metadata)


def _as_document(content: str | LyricsDocument, fmt: str) -> LyricsDocument:
    if fmt not in {"plain", "lrc"}:
        raise ValueError("format must be 'plain' or 'lrc'")
    if isinstance(content, LyricsDocument):
        if content.format == fmt:
            return content
        text = content.to_lrc() if fmt == "lrc" else content.to_plain_text()
    elif isinstance(content, str):
        text = content
    else:
        raise TypeError("lyrics content must be text or a LyricsDocument")
    if fmt == "lrc":
        return parse_lrc(text)
    return LyricsDocument([LyricsLine(line) for line in text.splitlines()], "plain")


def _serialize(document: LyricsDocument, fmt: str) -> str:
    return document.to_lrc() if fmt == "lrc" else document.to_plain_text()


class LyricsService:
    CACHE_TTL_SECONDS = 6 * 60 * 60
    CACHE_LIMIT = 100

    def __init__(self, tracks: TrackRepository, online_client: OnlineLyricsClient | None = None):
        self.tracks = tracks
        self.online_client = online_client or OnlineLyricsClient()
        self._online_cache: OrderedDict[tuple, tuple[float, LyricsLookupResult]] = OrderedDict()
        self._cache_lock = threading.RLock()

    @staticmethod
    def sidecar_path(audio_path: str | Path, fmt: str) -> Path:
        suffix = ".lrc" if fmt == "lrc" else ".txt"
        return Path(audio_path).with_suffix(suffix)

    def _get_local_lyrics(self, track_id: int) -> tuple[LyricsDocument, str]:
        track = self.tracks.get(track_id)
        if track is None:
            raise KeyError(f"Track {track_id} does not exist")
        path = Path(track.path)
        lrc_path = self.sidecar_path(path, "lrc")
        plain_path = self.sidecar_path(path, "plain")
        existing_sidecars = [
            (candidate, fmt)
            for candidate, fmt in ((lrc_path, "lrc"), (plain_path, "plain"))
            if candidate.is_file()
        ]
        existing_sidecars.sort(key=lambda item: item[0].stat().st_mtime_ns, reverse=True)
        for sidecar, fmt in existing_sidecars:
            try:
                text = sidecar.read_text(encoding="utf-8-sig")
            except (OSError, UnicodeError) as exc:
                raise LyricsError(f"Could not read lyrics sidecar {sidecar}: {exc}") from exc
            if text.strip():
                document = parse_lrc(text) if fmt == "lrc" else _as_document(text, fmt)
                return document, "Local sidecar"

        if path.is_file():
            try:
                embedded = read_embedded_lyrics(path)
            except Exception as exc:
                if isinstance(exc, (ImportError, MetadataWriteError)):
                    raise LyricsError(str(exc)) from exc
                raise LyricsError(f"Could not read embedded lyrics: {exc}") from exc
            if embedded and embedded.strip():
                document = parse_lrc(embedded) if _TIMESTAMP.search(embedded) else _as_document(embedded, "plain")
                return document, "Embedded lyrics"
        return LyricsDocument(), ""

    def get_lyrics(self, track_id: int) -> LyricsDocument:
        """Read local sidecar/embedded lyrics only; retained for compatibility."""
        return self._get_local_lyrics(track_id)[0]

    @staticmethod
    def _cache_key(track) -> tuple:
        duration_ms = getattr(track, "duration_ms", 0) or 0
        try:
            duration_seconds = int(round(int(duration_ms) / 1000.0)) if int(duration_ms) > 0 else 0
        except (TypeError, ValueError, OverflowError):
            duration_seconds = 0
        return (
            normalize_match_text(getattr(track, "title", "")),
            normalize_match_text(getattr(track, "artist", "")),
            normalize_match_text(getattr(track, "album", "")),
            duration_seconds,
        )

    def _cache_get(self, key: tuple) -> LyricsLookupResult | None:
        now = time.monotonic()
        with self._cache_lock:
            cached = self._online_cache.get(key)
            if cached is None:
                return None
            expires_at, result = cached
            if expires_at <= now:
                self._online_cache.pop(key, None)
                return None
            self._online_cache.move_to_end(key)
            return copy.deepcopy(result)

    def _cache_put(self, key: tuple, result: LyricsLookupResult) -> None:
        with self._cache_lock:
            self._online_cache[key] = (time.monotonic() + self.CACHE_TTL_SECONDS, copy.deepcopy(result))
            self._online_cache.move_to_end(key)
            while len(self._online_cache) > self.CACHE_LIMIT:
                self._online_cache.popitem(last=False)

    @staticmethod
    def _candidate_result(candidate: LyricsCandidate) -> LyricsLookupResult:
        plain_document = (
            _as_document(candidate.plain_lyrics, "plain")
            if candidate.plain_lyrics.strip()
            else None
        )
        synced_document = None
        if candidate.synced_lyrics.strip():
            parsed = parse_lrc(candidate.synced_lyrics)
            if any(line.timestamp_ms is not None for line in parsed.lines):
                synced_document = parsed
            elif plain_document is None:
                raise LyricsError("The provider returned synchronized lyrics without valid timestamps.")
        if plain_document is None and synced_document is not None:
            plain_document = _as_document(synced_document.to_plain_text(), "plain")
        if (plain_document is None or not plain_document.text.strip()) and synced_document is None and not candidate.instrumental:
            raise LyricsError("The provider returned an empty lyrics record.")

        source = "LRCLIB" if candidate.provider.casefold() == "lrclib" else "lyrics.ovh"
        attribution = "https://lrclib.net" if source == "LRCLIB" else "https://lyrics.ovh"
        matched = {
            "title": candidate.track_name,
            "artist": candidate.artist_name,
            "album": candidate.album_name,
            "duration": candidate.duration,
        }
        return LyricsLookupResult(
            status="instrumental" if candidate.instrumental else "found",
            document=synced_document or plain_document,
            plain_document=plain_document,
            synced_document=synced_document,
            source=source,
            attribution_url=attribution,
            matched_track=matched,
        )

    def load_lyrics(self, track_id: int, *, online_enabled: bool = True, force: bool = False) -> LyricsLookupResult:
        """Prefer local lyrics, then optionally query online providers on explicit UI demand."""
        track = self.tracks.get(track_id)
        if track is None:
            raise KeyError(f"Track {track_id} does not exist")
        local_read_error = ""
        try:
            local_document, local_source = self._get_local_lyrics(track_id)
        except LyricsError as exc:
            # A broken or unsupported embedded tag must not prevent an online
            # lookup from using the track metadata already stored in the library.
            local_document, local_source = LyricsDocument(), ""
            local_read_error = str(exc)
            logger.info("Local lyrics could not be read for track %s: %s", track_id, exc)
        if local_document.text.strip():
            plain_document = local_document if local_document.format == "plain" else _as_document(local_document.to_plain_text(), "plain")
            synced_document = local_document if local_document.format == "lrc" and any(
                line.timestamp_ms is not None for line in local_document.lines
            ) else None
            return LyricsLookupResult(
                status="found",
                document=local_document,
                plain_document=plain_document,
                synced_document=synced_document,
                source=local_source,
                attribution_url="",
                matched_track={"title": track.title, "artist": track.artist, "album": track.album, "duration": track.duration_ms / 1000.0},
            )
        if not online_enabled:
            return LyricsLookupResult(
                status="error" if local_read_error else "online_disabled",
                source="",
                message=(
                    f"Local lyrics could not be read: {local_read_error}"
                    if local_read_error else
                    "No local lyrics are available. Online lyrics search is disabled in Settings."
                ),
            )

        key = self._cache_key(track)
        if not force:
            cached = self._cache_get(key)
            if cached is not None:
                return cached

        try:
            provider_result = self.online_client.lookup(
                title=track.title,
                artist=track.artist,
                album=track.album,
                duration_ms=track.duration_ms,
            )
            if provider_result.status == "ambiguous":
                return LyricsLookupResult(
                    status="ambiguous",
                    source="LRCLIB",
                    attribution_url="https://lrclib.net",
                    candidates=list(provider_result.candidates or []),
                    message=provider_result.message or "Choose the correct recording.",
                )
            if provider_result.status == "not_found":
                return LyricsLookupResult(
                    status="not_found",
                    message=provider_result.message or "No matching lyrics were found online.",
                )
            if provider_result.status == "missing_metadata":
                return LyricsLookupResult(status="missing_metadata", message=provider_result.message)
            if provider_result.candidate is None:
                raise LyricsError("The lyrics provider did not return a usable record.")
            result = self._candidate_result(provider_result.candidate)
            self._cache_put(key, result)
            return result
        except LyricsRateLimited as exc:
            logger.info("LRCLIB rate limit reached; retry_after=%s", exc.retry_after)
            return LyricsLookupResult(status="rate_limited", source="LRCLIB", message=str(exc), retry_after=exc.retry_after)
        except LyricsNetworkError as exc:
            logger.info("Online lyrics lookup temporarily unavailable: %s", exc)
            return LyricsLookupResult(status="network_error", message=str(exc))
        except (LyricsProviderError, LyricsError, ValueError, TypeError) as exc:
            logger.warning("Online lyrics lookup failed: %s", exc)
            return LyricsLookupResult(status="error", message=str(exc))

    def select_candidate(self, track_id: int, candidate: LyricsCandidate) -> LyricsLookupResult:
        """Accept an explicitly selected LRCLIB candidate and cache the chosen recording."""
        track = self.tracks.get(track_id)
        if track is None:
            raise KeyError(f"Track {track_id} does not exist")
        result = self._candidate_result(candidate)
        self._cache_put(self._cache_key(track), result)
        return result

    def save_lyrics(self, track_id: int, content: str | LyricsDocument, format: str, storage: str) -> LyricsSaveResult:
        if format not in {"plain", "lrc"}:
            raise ValueError("format must be 'plain' or 'lrc'")
        if storage not in {"embedded", "sidecar"}:
            raise ValueError("storage must be 'embedded' or 'sidecar'")
        track = self.tracks.get(track_id)
        if track is None:
            raise KeyError(f"Track {track_id} does not exist")
        document = _as_document(content, format)
        serialized = _serialize(document, format)
        if storage == "sidecar":
            destination = self.sidecar_path(track.path, format)
            temporary_name = None
            try:
                destination.parent.mkdir(parents=True, exist_ok=True)
                with tempfile.NamedTemporaryFile(
                    "w", encoding="utf-8", newline="", delete=False,
                    dir=destination.parent, prefix=f".{destination.name}.", suffix=".tmp",
                ) as temporary:
                    temporary.write(serialized)
                    temporary.flush()
                    os.fsync(temporary.fileno())
                    temporary_name = temporary.name
                os.replace(temporary_name, destination)
            except (OSError, UnicodeError) as exc:
                if temporary_name:
                    try:
                        os.unlink(temporary_name)
                    except OSError:
                        pass
                raise LyricsError(f"Could not save lyrics sidecar {destination}: {exc}") from exc
            self._invalidate_online_cache(track)
            return LyricsSaveResult(document, "sidecar", str(destination), embedded=False)
        audio_path = Path(track.path)
        if not audio_path.is_file():
            raise LyricsError(f"Audio file is missing: {audio_path}")
        try:
            write_embedded_lyrics(audio_path, serialized)
        except Exception as exc:
            raise LyricsError(f"Could not embed lyrics in {audio_path}: {exc}") from exc
        stat = audio_path.stat()
        self.tracks.update_scan_state(audio_path, stat.st_size, stat.st_mtime_ns)
        self._invalidate_online_cache(track)
        return LyricsSaveResult(document, "embedded", str(audio_path), embedded=True)

    def _invalidate_online_cache(self, track) -> None:
        key = self._cache_key(track)
        with self._cache_lock:
            self._online_cache.pop(key, None)
