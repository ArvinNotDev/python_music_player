"""Public playlist/favorites API and Unicode-safe M3U import/export."""

from __future__ import annotations

import os
import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import unquote, urlsplit

from core.models import Playlist, Track
from database.repositories.playlist_repository import PlaylistRepository
from database.repositories.track_repository import normalize_path


@dataclass(slots=True)
class PlaylistImportResult:
    playlist_id: int
    playlist_name: str
    added_count: int = 0
    duplicate_count: int = 0
    missing_paths: list[str] = field(default_factory=list)
    invalid_lines: list[tuple[int, str, str]] = field(default_factory=list)


@dataclass(slots=True)
class PlaylistExportResult:
    path: str
    entries_written: int
    missing_paths: list[str] = field(default_factory=list)


class PlaylistService:
    def __init__(self, repository: PlaylistRepository):
        self.repository = repository

    def list_playlists(self) -> list[Playlist]:
        return self.repository.list()

    def get_playlist_tracks(self, playlist_id: int) -> list[Track]:
        return self.repository.tracks(playlist_id)

    def get_playlist_entries(self, playlist_id: int) -> list[dict[str, object]]:
        """Return ordered raw entries, including unresolved M3U paths."""
        return self.repository.entries(playlist_id)

    def create_playlist(self, name: str) -> Playlist:
        return self.repository.create(name)

    def rename_playlist(self, playlist_id: int, new_name: str) -> Playlist:
        return self.repository.rename(playlist_id, new_name)

    def delete_playlist(self, playlist_id: int) -> None:
        self.repository.delete(playlist_id)

    def add_track(self, playlist_id: int, track_id: int) -> bool:
        return self.repository.add_track(playlist_id, track_id)

    def remove_track(self, playlist_id: int, track_id: int) -> bool:
        return self.repository.remove_track(playlist_id, track_id)

    def reorder_tracks(self, playlist_id: int, source_index: int, destination_index: int) -> None:
        return self.repository.reorder(playlist_id, source_index, destination_index)

    def is_favorite(self, track_id: int) -> bool:
        return self.repository.is_favorite(track_id)

    def toggle_favorite(self, track_id: int) -> bool:
        return self.repository.toggle_favorite(track_id)

    def import_playlist(self, path: str | Path, name: str | None = None) -> PlaylistImportResult:
        playlist_file = Path(path).expanduser().resolve(strict=False)
        if playlist_file.suffix.lower() not in {".m3u", ".m3u8"}:
            raise ValueError("Only .m3u and .m3u8 playlists are supported")
        if not playlist_file.is_file():
            raise FileNotFoundError(playlist_file)
        try:
            content = playlist_file.read_text(encoding="utf-8-sig")
        except UnicodeDecodeError:
            if playlist_file.suffix.lower() == ".m3u8":
                raise ValueError("M3U8 playlist is not valid UTF-8")
            content = playlist_file.read_text(encoding="cp1252")
        clean_name = (name or playlist_file.stem).strip()
        if not clean_name:
            raise ValueError("Playlist name cannot be empty")
        playlist = self.repository.create(clean_name)
        result = PlaylistImportResult(playlist.id, playlist.name)
        paths: list[tuple[int, str]] = []
        for line_number, raw_line in enumerate(content.splitlines(), start=1):
            line = raw_line.strip().lstrip("\ufeff")
            if not line or line.startswith("#"):
                continue
            try:
                resolved = self._resolve_playlist_entry(line, playlist_file.parent)
            except ValueError as exc:
                result.invalid_lines.append((line_number, raw_line, str(exc)))
                continue
            paths.append((line_number, resolved))
        for line_number, resolved in paths:
            added = self.repository.add_path(playlist.id, resolved)
            if added:
                result.added_count += 1
                if not Path(resolved).is_file():
                    result.missing_paths.append(normalize_path(resolved))
            else:
                result.duplicate_count += 1
        return result

    @staticmethod
    def _resolve_playlist_entry(entry: str, base: Path) -> str:
        if "\x00" in entry:
            raise ValueError("path contains a NUL character")
        if entry.casefold().startswith("file://"):
            parsed = urlsplit(entry)
            decoded = unquote(parsed.path)
            if parsed.netloc and parsed.netloc.casefold() != "localhost":
                decoded = f"//{parsed.netloc}{decoded}"
            if re.match(r"^/[A-Za-z]:/", decoded):
                decoded = decoded[1:]
            candidate = Path(decoded)
        elif re.match(r"^[A-Za-z][A-Za-z0-9+.-]*://", entry) and not re.match(r"^[A-Za-z]:[\\/]", entry):
            raise ValueError("remote URLs are not local audio file paths")
        else:
            candidate = Path(entry)
        if not candidate.is_absolute():
            candidate = base / candidate
        return str(candidate.expanduser().resolve(strict=False))

    def export_playlist(self, playlist_id: int, path: str | Path) -> PlaylistExportResult:
        destination = Path(path).expanduser().resolve(strict=False)
        if destination.suffix.lower() not in {".m3u", ".m3u8"}:
            raise ValueError("Export path must end in .m3u or .m3u8")
        entries = self.repository.entries(playlist_id)
        tracks_by_id = {track.id: track for track in self.repository.tracks(playlist_id)}
        if not entries:
            if self.repository.get(playlist_id) is None:
                raise KeyError(f"Playlist {playlist_id} does not exist")
        destination.parent.mkdir(parents=True, exist_ok=True)
        lines = ["#EXTM3U"]
        missing: list[str] = []
        for entry in entries:
            source = str(entry.get("source_path") or "")
            if not source:
                continue
            track_id = entry.get("entry_track_id")
            track = tracks_by_id.get(track_id) if isinstance(track_id, int) else None
            if track is not None:
                if Path(track.path).is_file():
                    title = (track.title or Path(track.path).stem).replace("\r", " ").replace("\n", " ")
                    lines.append(f"#EXTINF:{track.duration_ms // 1000},{title}")
                else:
                    missing.append(track.path)
                source = track.path
            elif not Path(source).is_file():
                missing.append(source)
            try:
                source = os.path.relpath(source, destination.parent)
            except ValueError:
                pass
            lines.append(source)
        temporary_name = None
        try:
            with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="\n", delete=False,
                                             dir=destination.parent, prefix=f".{destination.name}.", suffix=".tmp") as temporary:
                temporary.write("\n".join(lines) + "\n")
                temporary.flush()
                os.fsync(temporary.fileno())
                temporary_name = temporary.name
            os.replace(temporary_name, destination)
        except OSError as exc:
            if temporary_name:
                try:
                    os.unlink(temporary_name)
                except OSError:
                    pass
            raise OSError(f"Could not export playlist to {destination}: {exc}") from exc
        return PlaylistExportResult(str(destination), len(entries), missing)
