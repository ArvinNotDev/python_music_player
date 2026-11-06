"""Ordered playlists and their path-preserving entries."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from core.models import Playlist, Track
from database.database_manager import DatabaseManager
from .track_repository import TRACK_SELECT, _parse_date, _track, normalize_path


class PlaylistRepository:
    FAVORITES_NAME = "Favorites"

    def __init__(self, database: DatabaseManager):
        self.database = database
        self.ensure_favorites()

    def ensure_favorites(self) -> int:
        now = datetime.now(timezone.utc).isoformat()
        with self.database.transaction(write=True) as conn:
            row = conn.execute("SELECT id FROM playlists WHERE is_favorite=1").fetchone()
            if row:
                return int(row["id"])
            conn.execute("INSERT OR IGNORE INTO playlists(name,is_favorite,created_at,updated_at) VALUES(?,1,?,?)", (self.FAVORITES_NAME, now, now))
            return int(conn.execute("SELECT id FROM playlists WHERE is_favorite=1").fetchone()["id"])

    @staticmethod
    def _playlist(row: sqlite3.Row) -> Playlist:
        return Playlist(row["id"], row["name"], bool(row["is_favorite"]), row["track_count"], _parse_date(row["created_at"]), _parse_date(row["updated_at"]))

    def list(self) -> list[Playlist]:
        with self.database.transaction() as conn:
            rows = conn.execute(
                """SELECT p.*,COUNT(pt.id) AS track_count FROM playlists p
                   LEFT JOIN playlist_tracks pt ON pt.playlist_id=p.id
                   GROUP BY p.id ORDER BY p.is_favorite DESC,p.name COLLATE NOCASE"""
            ).fetchall()
            return [self._playlist(row) for row in rows]

    def get(self, playlist_id: int) -> Playlist | None:
        with self.database.transaction() as conn:
            row = conn.execute(
                """SELECT p.*,COUNT(pt.id) AS track_count FROM playlists p
                   LEFT JOIN playlist_tracks pt ON pt.playlist_id=p.id WHERE p.id=? GROUP BY p.id""",
                (playlist_id,),
            ).fetchone()
            return self._playlist(row) if row else None

    def create(self, name: str) -> Playlist:
        clean = name.strip()
        if not clean:
            raise ValueError("Playlist name cannot be empty")
        now = datetime.now(timezone.utc).isoformat()
        try:
            with self.database.transaction(write=True) as conn:
                conn.execute("INSERT INTO playlists(name,created_at,updated_at) VALUES(?,?,?)", (clean, now, now))
                playlist_id = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
                row = conn.execute("SELECT p.*,0 AS track_count FROM playlists p WHERE id=?", (playlist_id,)).fetchone()
                return self._playlist(row)
        except Exception as exc:
            if "UNIQUE constraint failed" in str(exc):
                raise ValueError(f"A playlist named {clean!r} already exists") from exc
            raise

    def rename(self, playlist_id: int, name: str) -> Playlist:
        clean = name.strip()
        if not clean:
            raise ValueError("Playlist name cannot be empty")
        with self.database.transaction(write=True) as conn:
            row = conn.execute("SELECT is_favorite FROM playlists WHERE id=?", (playlist_id,)).fetchone()
            if not row:
                raise KeyError(f"Playlist {playlist_id} does not exist")
            if row["is_favorite"]:
                raise ValueError("The built-in Favorites playlist cannot be renamed")
            try:
                conn.execute("UPDATE playlists SET name=?,updated_at=? WHERE id=?", (clean, datetime.now(timezone.utc).isoformat(), playlist_id))
            except sqlite3.IntegrityError as exc:
                raise ValueError(f"A playlist named {clean!r} already exists") from exc
        return self.get(playlist_id)

    def delete(self, playlist_id: int) -> None:
        with self.database.transaction(write=True) as conn:
            row = conn.execute("SELECT is_favorite FROM playlists WHERE id=?", (playlist_id,)).fetchone()
            if not row:
                return
            if row["is_favorite"]:
                raise ValueError("The built-in Favorites playlist cannot be deleted")
            conn.execute("DELETE FROM playlists WHERE id=?", (playlist_id,))

    def add_track(self, playlist_id: int, track_id: int) -> bool:
        with self.database.transaction(write=True) as conn:
            if not conn.execute("SELECT 1 FROM playlists WHERE id=?", (playlist_id,)).fetchone():
                raise KeyError(f"Playlist {playlist_id} does not exist")
            row = conn.execute("SELECT path FROM tracks WHERE id=?", (track_id,)).fetchone()
            if not row:
                raise KeyError(f"Track {track_id} does not exist")
            if conn.execute("SELECT 1 FROM playlist_tracks WHERE playlist_id=? AND track_id=?", (playlist_id, track_id)).fetchone():
                return False
            position = conn.execute("SELECT COALESCE(MAX(position)+1,0) FROM playlist_tracks WHERE playlist_id=?", (playlist_id,)).fetchone()[0]
            conn.execute("INSERT INTO playlist_tracks(playlist_id,track_id,source_path,position) VALUES(?,?,?,?)", (playlist_id, track_id, row["path"], position))
            is_favorite = conn.execute("SELECT is_favorite FROM playlists WHERE id=?", (playlist_id,)).fetchone()["is_favorite"]
            if is_favorite:
                conn.execute("INSERT OR IGNORE INTO favorites(track_id,added_at) VALUES(?,?)", (track_id, datetime.now(timezone.utc).isoformat()))
            conn.execute("UPDATE playlists SET updated_at=? WHERE id=?", (datetime.now(timezone.utc).isoformat(), playlist_id))
            return True

    def add_path(self, playlist_id: int, path: str | Path, *, track_id: int | None = None) -> bool:
        normalized = normalize_path(path)
        with self.database.transaction(write=True) as conn:
            if not conn.execute("SELECT 1 FROM playlists WHERE id=?", (playlist_id,)).fetchone():
                raise KeyError(f"Playlist {playlist_id} does not exist")
            if track_id is None:
                row = conn.execute("SELECT id FROM tracks WHERE path=?", (normalized,)).fetchone()
                track_id = int(row["id"]) if row else None
            existing = conn.execute("SELECT 1 FROM playlist_tracks WHERE playlist_id=? AND source_path=?", (playlist_id, normalized)).fetchone()
            if existing:
                if track_id is not None:
                    conn.execute("UPDATE playlist_tracks SET track_id=? WHERE playlist_id=? AND source_path=? AND track_id IS NULL", (track_id, playlist_id, normalized))
                return False
            pos = conn.execute("SELECT COALESCE(MAX(position)+1,0) FROM playlist_tracks WHERE playlist_id=?", (playlist_id,)).fetchone()[0]
            conn.execute("INSERT INTO playlist_tracks(playlist_id,track_id,source_path,position) VALUES(?,?,?,?)", (playlist_id, track_id, normalized, pos))
            is_favorite = conn.execute("SELECT is_favorite FROM playlists WHERE id=?", (playlist_id,)).fetchone()["is_favorite"]
            if is_favorite and track_id is not None:
                conn.execute("INSERT OR IGNORE INTO favorites(track_id,added_at) VALUES(?,?)", (track_id, datetime.now(timezone.utc).isoformat()))
            conn.execute("UPDATE playlists SET updated_at=? WHERE id=?", (datetime.now(timezone.utc).isoformat(), playlist_id))
            return True

    def remove_track(self, playlist_id: int, track_id: int) -> bool:
        with self.database.transaction(write=True) as conn:
            row = conn.execute("SELECT id,position FROM playlist_tracks WHERE playlist_id=? AND track_id=?", (playlist_id, track_id)).fetchone()
            if not row:
                return False
            conn.execute("DELETE FROM playlist_tracks WHERE id=?", (row["id"],))
            playlist = conn.execute("SELECT is_favorite FROM playlists WHERE id=?", (playlist_id,)).fetchone()
            if playlist and playlist["is_favorite"]:
                conn.execute("DELETE FROM favorites WHERE track_id=?", (track_id,))
            self._compact(conn, playlist_id)
            conn.execute("UPDATE playlists SET updated_at=? WHERE id=?", (datetime.now(timezone.utc).isoformat(), playlist_id))
            return True

    @staticmethod
    def _compact(conn: sqlite3.Connection, playlist_id: int) -> None:
        rows = conn.execute("SELECT id FROM playlist_tracks WHERE playlist_id=? ORDER BY position", (playlist_id,)).fetchall()
        conn.execute("UPDATE playlist_tracks SET position=-position-1 WHERE playlist_id=?", (playlist_id,))
        conn.executemany("UPDATE playlist_tracks SET position=? WHERE id=?", ((idx, row["id"]) for idx, row in enumerate(rows)))

    def reorder(self, playlist_id: int, source_index: int, destination_index: int) -> None:
        with self.database.transaction(write=True) as conn:
            rows = conn.execute("SELECT id FROM playlist_tracks WHERE playlist_id=? ORDER BY position", (playlist_id,)).fetchall()
            entries = [row["id"] for row in rows]
            if not (0 <= source_index < len(entries) and 0 <= destination_index < len(entries)):
                raise IndexError("Playlist reorder index is out of range")
            moved = entries.pop(source_index)
            entries.insert(destination_index, moved)
            conn.execute("UPDATE playlist_tracks SET position=-position-1 WHERE playlist_id=?", (playlist_id,))
            conn.executemany("UPDATE playlist_tracks SET position=? WHERE id=?", ((idx, entry_id) for idx, entry_id in enumerate(entries)))
            conn.execute("UPDATE playlists SET updated_at=? WHERE id=?", (datetime.now(timezone.utc).isoformat(), playlist_id))

    def entries(self, playlist_id: int) -> list[dict[str, object]]:
        with self.database.transaction() as conn:
            rows = conn.execute(
                """SELECT pt.id AS entry_id,pt.track_id AS entry_track_id,pt.source_path,pt.position,
                   t.*,COALESCE(ar.name,'') AS artist,COALESCE(al.title,'') AS album,
                   COALESCE(NULLIF(t.album_artist,''),al.album_artist,'') AS display_album_artist
                   FROM playlist_tracks pt LEFT JOIN tracks t ON t.id=pt.track_id
                   LEFT JOIN artists ar ON ar.id=t.artist_id LEFT JOIN albums al ON al.id=t.album_id
                   WHERE pt.playlist_id=? ORDER BY pt.position""",
                (playlist_id,),
            ).fetchall()
            return [dict(row) for row in rows]

    def tracks(self, playlist_id: int) -> list[Track]:
        with self.database.transaction() as conn:
            rows = conn.execute(
                TRACK_SELECT + " JOIN playlist_tracks pt ON pt.track_id=t.id WHERE pt.playlist_id=? ORDER BY pt.position",
                (playlist_id,),
            ).fetchall()
            return [t for row in rows if (t := _track(row)) is not None]

    def favorites_id(self) -> int:
        return self.ensure_favorites()

    def is_favorite(self, track_id: int) -> bool:
        with self.database.transaction() as conn:
            return bool(conn.execute("SELECT 1 FROM favorites WHERE track_id=?", (track_id,)).fetchone())

    def toggle_favorite(self, track_id: int) -> bool:
        now = datetime.now(timezone.utc).isoformat()
        with self.database.transaction(write=True) as conn:
            if not conn.execute("SELECT 1 FROM tracks WHERE id=?", (track_id,)).fetchone():
                raise KeyError(f"Track {track_id} does not exist")
            existing = conn.execute("SELECT 1 FROM favorites WHERE track_id=?", (track_id,)).fetchone()
            fav_id = conn.execute("SELECT id FROM playlists WHERE is_favorite=1").fetchone()["id"]
            if existing:
                conn.execute("DELETE FROM favorites WHERE track_id=?", (track_id,))
                conn.execute("DELETE FROM playlist_tracks WHERE playlist_id=? AND track_id=?", (fav_id, track_id))
                self._compact(conn, fav_id)
                return False
            conn.execute("INSERT INTO favorites(track_id,added_at) VALUES(?,?)", (track_id, now))
            pos = conn.execute("SELECT COALESCE(MAX(position)+1,0) FROM playlist_tracks WHERE playlist_id=?", (fav_id,)).fetchone()[0]
            path = conn.execute("SELECT path FROM tracks WHERE id=?", (track_id,)).fetchone()["path"]
            conn.execute("INSERT INTO playlist_tracks(playlist_id,track_id,source_path,position) VALUES(?,?,?,?)", (fav_id, track_id, path, pos))
            return True

    def import_legacy_mapping(self, mapping: dict[str, list[str]]) -> tuple[int, int, list[str]]:
        """Merge legacy playlist names and source paths without dropping unresolved paths."""
        added = duplicates = 0
        invalid: list[str] = []
        now = datetime.now(timezone.utc).isoformat()
        with self.database.transaction(write=True) as conn:
            favorite = conn.execute("SELECT id FROM playlists WHERE is_favorite=1").fetchone()
            if not favorite:
                conn.execute("INSERT INTO playlists(name,is_favorite,created_at,updated_at) VALUES(?,1,?,?)", (self.FAVORITES_NAME, now, now))
                favorite_id = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
            else:
                favorite_id = int(favorite["id"])
            for raw_name, raw_paths in mapping.items():
                name = raw_name.strip()
                if not name or not isinstance(raw_paths, list):
                    invalid.append(f"Invalid playlist entry {raw_name!r}")
                    continue
                if name.casefold() == self.FAVORITES_NAME.casefold():
                    playlist_id = favorite_id
                else:
                    existing = conn.execute("SELECT id FROM playlists WHERE name=? COLLATE NOCASE", (name,)).fetchone()
                    if existing:
                        playlist_id = int(existing["id"])
                    else:
                        conn.execute("INSERT INTO playlists(name,created_at,updated_at) VALUES(?,?,?)", (name, now, now))
                        playlist_id = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
                for raw_path in raw_paths:
                    if not isinstance(raw_path, str) or not raw_path.strip():
                        invalid.append(f"Playlist {name!r} contains a non-path entry")
                        continue
                    try:
                        source_path = normalize_path(raw_path)
                    except (OSError, RuntimeError, ValueError) as exc:
                        invalid.append(f"Playlist {name!r}: {raw_path!r}: {exc}")
                        continue
                    if conn.execute("SELECT 1 FROM playlist_tracks WHERE playlist_id=? AND source_path=?", (playlist_id, source_path)).fetchone():
                        duplicates += 1
                        continue
                    track = conn.execute("SELECT id FROM tracks WHERE path=?", (source_path,)).fetchone()
                    track_id = int(track["id"]) if track else None
                    position = conn.execute("SELECT COALESCE(MAX(position)+1,0) FROM playlist_tracks WHERE playlist_id=?", (playlist_id,)).fetchone()[0]
                    conn.execute("INSERT INTO playlist_tracks(playlist_id,track_id,source_path,position) VALUES(?,?,?,?)", (playlist_id, track_id, source_path, position))
                    if playlist_id == favorite_id and track_id is not None:
                        conn.execute("INSERT OR IGNORE INTO favorites(track_id,added_at) VALUES(?,?)", (track_id, now))
                    added += 1
            conn.execute("UPDATE playlists SET updated_at=? WHERE id=?", (now, favorite_id))
        return added, duplicates, invalid

    def set_favorite(self, track_id: int, favorite: bool) -> None:
        if self.is_favorite(track_id) != favorite:
            self.toggle_favorite(track_id)

    def import_paths(self, playlist_id: int, paths: Iterable[str | Path]) -> tuple[int, int]:
        added = duplicates = 0
        for path in paths:
            if self.add_path(playlist_id, path):
                added += 1
            else:
                duplicates += 1
        return added, duplicates
