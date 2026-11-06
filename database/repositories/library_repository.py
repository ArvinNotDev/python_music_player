"""Registered local music source folders."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from database.database_manager import DatabaseManager
from .track_repository import normalize_path


class LibraryFolderRepository:
    def __init__(self, database: DatabaseManager):
        self.database = database

    def add(self, path: str | Path) -> str:
        normalized = normalize_path(path)
        with self.database.transaction(write=True) as conn:
            conn.execute("INSERT OR IGNORE INTO library_folders(path,date_added) VALUES(?,?)", (normalized, datetime.now(timezone.utc).isoformat()))
        return normalized

    def remove(self, path: str | Path) -> bool:
        normalized = normalize_path(path)
        root = Path(normalized)
        with self.database.transaction(write=True) as conn:
            row = conn.execute("SELECT id FROM library_folders WHERE path=?", (normalized,)).fetchone()
            if not row:
                return False
            conn.execute("DELETE FROM library_folders WHERE id=?", (row["id"],))
            tracks = conn.execute("SELECT id,path FROM tracks WHERE is_available=1").fetchall()
            ids = [row["id"] for row in tracks if Path(row["path"]) == root or root in Path(row["path"]).parents]
            conn.executemany("UPDATE tracks SET is_available=0 WHERE id=?", ((track_id,) for track_id in ids))
            return True

    def list(self) -> list[str]:
        with self.database.transaction() as conn:
            return [row["path"] for row in conn.execute("SELECT path FROM library_folders ORDER BY path COLLATE NOCASE")]

    def mark_scanned(self, path: str | Path) -> None:
        with self.database.transaction(write=True) as conn:
            conn.execute("UPDATE library_folders SET last_scanned=? WHERE path=?", (datetime.now(timezone.utc).isoformat(), normalize_path(path)))
