"""Structured LRC parsing and safe sidecar/embedded lyrics persistence."""

from __future__ import annotations

import os
import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from core.models import LyricsDocument, LyricsLine
from database.repositories.track_repository import TrackRepository
from .tagging import MetadataWriteError, read_embedded_lyrics, write_embedded_lyrics

_TIMESTAMP = re.compile(r"\[(\d{1,4}):([0-5]?\d)(?:[.:](\d{1,3}))?\](?!\d)")
_META = re.compile(r"\[([A-Za-z][A-Za-z0-9_-]*):(.*?)\]")


class LyricsError(RuntimeError):
    """Lyrics could not be read, parsed, or saved as requested."""


@dataclass(slots=True)
class LyricsSaveResult:
    document: LyricsDocument
    storage: str
    path: str | None = None
    embedded: bool = False


def _fraction_ms(value: str | None) -> int:
    if not value:
        return 0
    if len(value) == 1:
        return int(value) * 100
    if len(value) == 2:
        return int(value) * 10
    return int(value[:3])


def parse_lrc(content: str) -> LyricsDocument:
    """Parse valid timestamp tags and preserve malformed/non-timestamped lines."""
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
            # Recognized LRC metadata headers are not lyric lines; malformed timestamp-looking
            # content is left intact so an editor can repair it later.
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
    def __init__(self, tracks: TrackRepository):
        self.tracks = tracks

    @staticmethod
    def sidecar_path(audio_path: str | Path, fmt: str) -> Path:
        suffix = ".lrc" if fmt == "lrc" else ".txt"
        return Path(audio_path).with_suffix(suffix)

    def get_lyrics(self, track_id: int) -> LyricsDocument:
        track = self.tracks.get(track_id)
        if track is None:
            raise KeyError(f"Track {track_id} does not exist")
        path = Path(track.path)
        lrc_path = self.sidecar_path(path, "lrc")
        plain_path = self.sidecar_path(path, "plain")
        existing_sidecars = [(candidate, fmt) for candidate, fmt in ((lrc_path, "lrc"), (plain_path, "plain")) if candidate.is_file()]
        existing_sidecars.sort(key=lambda item: item[0].stat().st_mtime_ns, reverse=True)
        for sidecar, fmt in existing_sidecars:
            try:
                if sidecar.is_file():
                    text = sidecar.read_text(encoding="utf-8-sig")
                    return parse_lrc(text) if fmt == "lrc" else _as_document(text, fmt)
            except (OSError, UnicodeError) as exc:
                raise LyricsError(f"Could not read lyrics sidecar {sidecar}: {exc}") from exc
        if path.is_file():
            try:
                embedded = read_embedded_lyrics(path)
            except Exception as exc:
                # A missing optional Mutagen install should be diagnosable; a file with no tags
                # is handled by the adapter and returns None.
                if isinstance(exc, (ImportError, MetadataWriteError)):
                    raise LyricsError(str(exc)) from exc
                raise LyricsError(f"Could not read embedded lyrics: {exc}") from exc
            if embedded:
                return parse_lrc(embedded) if _TIMESTAMP.search(embedded) else _as_document(embedded, "plain")
        return LyricsDocument()

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
                with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="", delete=False,
                                                 dir=destination.parent, prefix=f".{destination.name}.", suffix=".tmp") as temporary:
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
        return LyricsSaveResult(document, "embedded", str(audio_path), embedded=True)
