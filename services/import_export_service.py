"""Playlist file operations and explicit one-time legacy JSON migration."""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from core.playlists import PlaylistExportResult, PlaylistImportResult, PlaylistService
from database.database_manager import DatabaseManager
from database.repositories.playlist_repository import PlaylistRepository
from database.repositories.settings_repository import SettingsRepository


@dataclass(slots=True)
class LegacyMigrationResult:
    migrated_files: list[str] = field(default_factory=list)
    backup_files: list[str] = field(default_factory=list)
    playlists_added: int = 0
    entries_added: int = 0
    duplicates_skipped: int = 0
    invalid_entries: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


class LegacyPlaylistMigrator:
    """Imports old CWD-relative ``playlists.json`` files and keeps dated copies."""

    def __init__(self, database: DatabaseManager, playlists: PlaylistRepository,
                 settings: SettingsRepository | None = None):
        self.database = database
        self.playlists = playlists
        self.settings = settings or SettingsRepository(database)

    @staticmethod
    def discover_candidates(extra: Iterable[str | Path] = ()) -> list[Path]:
        package_root = Path(__file__).resolve().parents[1]
        executable_dir = Path(sys.argv[0]).expanduser().resolve(strict=False).parent if sys.argv and sys.argv[0] else None
        home = Path.home()
        candidates = [Path.cwd() / "playlists.json", package_root / "playlists.json", home / "playlists.json"]
        if executable_dir is not None:
            candidates.append(executable_dir / "playlists.json")
        candidates.extend((
            home / "python_music_player" / "playlists.json",
            home / "Documents" / "python_music_player" / "playlists.json",
            home / "Music" / "python_music_player" / "playlists.json",
        ))
        candidates.extend(Path(item).expanduser() / "playlists.json" for item in extra)
        unique: list[Path] = []
        seen: set[str] = set()
        for candidate in candidates:
            resolved = candidate.expanduser().resolve(strict=False)
            key = str(resolved).casefold() if sys.platform == "win32" else str(resolved)
            if key not in seen and resolved.is_file():
                seen.add(key)
                unique.append(resolved)
        return unique

    @staticmethod
    def _backup_path(source: Path) -> Path:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        candidate = source.with_name(f"{source.name}.backup-{stamp}")
        suffix = 1
        while candidate.exists():
            candidate = source.with_name(f"{source.name}.backup-{stamp}-{suffix}")
            suffix += 1
        return candidate

    def migrate(self, candidates: Iterable[str | Path] | None = None) -> LegacyMigrationResult:
        result = LegacyMigrationResult()
        sources = [Path(path).expanduser().resolve(strict=False) for path in candidates] if candidates is not None else self.discover_candidates()
        visited: set[str] = set()
        for source in sources:
            key = str(source).casefold() if sys.platform == "win32" else str(source)
            if key in visited:
                continue
            visited.add(key)
            if not source.is_file():
                continue
            setting_key = "legacy_playlists_migrated:" + hashlib.sha256(key.encode("utf-8")).hexdigest()
            if self.settings.get(setting_key, False):
                continue
            try:
                raw = json.loads(source.read_text(encoding="utf-8-sig"))
            except (OSError, UnicodeError, json.JSONDecodeError) as exc:
                result.errors.append(f"Could not read legacy playlists {source}: {exc}")
                continue
            if not isinstance(raw, dict):
                result.errors.append(f"Legacy playlists file must contain a JSON object: {source}")
                continue
            valid: dict[str, list[str]] = {}
            for name, paths in raw.items():
                if not isinstance(name, str) or not isinstance(paths, list):
                    result.invalid_entries.append(f"{source}: invalid playlist {name!r}")
                    continue
                valid[name] = paths
            before = len(self.playlists.list())
            try:
                added, duplicates, invalid = self.playlists.import_legacy_mapping(valid)
                backup = self._backup_path(source)
                shutil.copy2(source, backup)
                self.settings.set(setting_key, {"backup": str(backup), "migrated_at": datetime.now(timezone.utc).isoformat()})
            except Exception as exc:
                result.errors.append(f"Migration of {source} did not complete: {exc}")
                continue
            result.migrated_files.append(str(source))
            result.backup_files.append(str(backup))
            result.playlists_added += max(0, len(self.playlists.list()) - before)
            result.entries_added += added
            result.duplicates_skipped += duplicates
            result.invalid_entries.extend(f"{source}: {message}" for message in invalid)
        return result


class ImportExportService:
    def __init__(self, playlists: PlaylistService, migrator: LegacyPlaylistMigrator | None = None):
        self.playlists = playlists
        self.migrator = migrator

    def import_playlist(self, path: str | Path, name: str | None = None) -> PlaylistImportResult:
        return self.playlists.import_playlist(path, name)

    def export_playlist(self, playlist_id: int, path: str | Path) -> PlaylistExportResult:
        return self.playlists.export_playlist(playlist_id, path)

    def migrate_legacy_playlists(self, candidates: Iterable[str | Path] | None = None) -> LegacyMigrationResult:
        if self.migrator is None:
            raise RuntimeError("No LegacyPlaylistMigrator was configured")
        return self.migrator.migrate(candidates)
