"""Track persistence, lookup, grouping, and scan-cache operations."""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from core.models import Album, Artist, Track
from database.database_manager import DatabaseManager


def normalize_path(path: str | Path) -> str:
    return os.path.normcase(str(Path(path).expanduser().resolve(strict=False)))


def _parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)


def _track(row: sqlite3.Row | None) -> Track | None:
    if row is None:
        return None
    return Track(
        id=row["id"], path=row["path"], title=row["title"], artist=row["artist"] or "",
        album=row["album"] or "", album_artist=row["display_album_artist"] or "",
        duration_ms=row["duration_ms"], track_number=row["track_number"], disc_number=row["disc_number"],
        year=row["year"], genre=row["genre"], composer=row["composer"], comment=row["comment"],
        bitrate=row["bitrate"], sample_rate=row["sample_rate"], artwork_path=row["artwork_path"],
        date_added=_parse_date(row["date_added"]), last_played=_parse_date(row["last_played"]),
        play_count=row["play_count"], is_available=bool(row["is_available"]), bpm=row["bpm"],
    )


TRACK_SELECT = """
SELECT t.*, COALESCE(ar.name, '') AS artist,
       COALESCE(al.title, '') AS album,
       COALESCE(NULLIF(t.album_artist, ''), al.album_artist, '') AS display_album_artist
FROM tracks t
LEFT JOIN artists ar ON ar.id = t.artist_id
LEFT JOIN albums al ON al.id = t.album_id
"""


class TrackRepository:
    def __init__(self, database: DatabaseManager):
        self.database = database

    @staticmethod
    def _artist_id(conn: sqlite3.Connection, name: str) -> int | None:
        name = name.strip()
        if not name:
            return None
        conn.execute("INSERT OR IGNORE INTO artists(name) VALUES (?)", (name,))
        return int(conn.execute("SELECT id FROM artists WHERE name = ? COLLATE NOCASE", (name,)).fetchone()[0])

    @staticmethod
    def _album_id(conn: sqlite3.Connection, title: str, album_artist: str, year: int | None) -> int | None:
        title, album_artist = title.strip(), album_artist.strip()
        if not title:
            return None
        conn.execute(
            "INSERT OR IGNORE INTO albums(title, album_artist, year) VALUES (?, ?, ?)",
            (title, album_artist, year),
        )
        row = conn.execute(
            "SELECT id, year FROM albums WHERE title = ? COLLATE NOCASE AND album_artist = ? COLLATE NOCASE",
            (title, album_artist),
        ).fetchone()
        if row and year and not row["year"]:
            conn.execute("UPDATE albums SET year = ? WHERE id = ?", (year, row["id"]))
        return int(row["id"]) if row else None

    def _upsert(self, conn: sqlite3.Connection, track: Track, file_size: int | None, file_mtime_ns: int | None) -> tuple[Track, bool]:
        normalized = normalize_path(track.path)
        artist_id = self._artist_id(conn, track.artist)
        album_id = self._album_id(conn, track.album, track.album_artist or track.artist, track.year)
        existing = conn.execute("SELECT id FROM tracks WHERE path = ?", (normalized,)).fetchone()
        now = datetime.now(timezone.utc).isoformat()
        values = (
            track.title, artist_id, album_id, track.album_artist, track.duration_ms, track.track_number,
            track.disc_number, track.year, track.genre, track.composer, track.comment, track.bitrate,
            track.sample_rate, track.artwork_path, track.bpm, file_size, file_mtime_ns,
        )
        if existing:
            conn.execute(
                """UPDATE tracks SET title=?, artist_id=?, album_id=?, album_artist=?, duration_ms=?,
                   track_number=?, disc_number=?, year=?, genre=?, composer=?, comment=?, bitrate=?,
                   sample_rate=?, artwork_path=?, bpm=?, file_size=?, file_mtime_ns=?, is_available=1
                   WHERE id=?""",
                (*values, existing["id"]),
            )
            track_id, inserted = int(existing["id"]), False
        else:
            conn.execute(
                """INSERT INTO tracks(path,title,artist_id,album_id,album_artist,duration_ms,track_number,
                   disc_number,year,genre,composer,comment,bitrate,sample_rate,artwork_path,bpm,file_size,
                   file_mtime_ns,date_added) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (normalized, *values, now),
            )
            track_id, inserted = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0]), True
        conn.execute(
            "UPDATE playlist_tracks SET track_id=? WHERE source_path=? AND track_id IS NULL",
            (track_id, normalized),
        )
        favorite_playlist = conn.execute("SELECT id FROM playlists WHERE is_favorite=1").fetchone()
        if favorite_playlist and conn.execute(
            "SELECT 1 FROM playlist_tracks WHERE playlist_id=? AND track_id=?",
            (favorite_playlist["id"], track_id),
        ).fetchone():
            conn.execute("INSERT OR IGNORE INTO favorites(track_id,added_at) VALUES(?,?)", (track_id, now))
        row = conn.execute(TRACK_SELECT + " WHERE t.id=?", (track_id,)).fetchone()
        return _track(row), inserted

    def upsert(self, track: Track, *, file_size: int | None = None, file_mtime_ns: int | None = None) -> tuple[Track, bool]:
        with self.database.transaction(write=True) as conn:
            return self._upsert(conn, track, file_size, file_mtime_ns)

    def get(self, track_id: int) -> Track | None:
        with self.database.transaction() as conn:
            return _track(conn.execute(TRACK_SELECT + " WHERE t.id=?", (track_id,)).fetchone())

    def find_by_path(self, path: str | Path) -> Track | None:
        with self.database.transaction() as conn:
            return _track(conn.execute(TRACK_SELECT + " WHERE t.path=?", (normalize_path(path),)).fetchone())

    def file_signature_matches(self, path: str | Path, size: int, mtime_ns: int) -> Track | None:
        with self.database.transaction() as conn:
            row = conn.execute(
                TRACK_SELECT + " WHERE t.path=? AND t.file_size=? AND t.file_mtime_ns=?",
                (normalize_path(path), size, mtime_ns),
            ).fetchone()
            if row:
                return _track(row)
            return None

    def set_metadata(self, track_id: int, changes: Mapping[str, Any]) -> Track:
        fields = {
            "title": "title", "artist": "artist", "album": "album", "album_artist": "album_artist",
            "duration_ms": "duration_ms", "track_number": "track_number", "disc_number": "disc_number",
            "year": "year", "genre": "genre", "composer": "composer", "comment": "comment",
            "bitrate": "bitrate", "sample_rate": "sample_rate", "artwork_path": "artwork_path", "bpm": "bpm",
        }
        unknown = set(changes) - set(fields)
        if unknown:
            raise ValueError(f"Unsupported track fields: {', '.join(sorted(unknown))}")
        with self.database.transaction(write=True) as conn:
            row = conn.execute("SELECT id FROM tracks WHERE id=?", (track_id,)).fetchone()
            if not row:
                raise KeyError(f"Track {track_id} does not exist")
            updates: dict[str, Any] = dict(changes)
            if "artist" in changes:
                updates["artist_id"] = self._artist_id(conn, str(changes["artist"] or ""))
                updates.pop("artist")
            if "album" in changes or "album_artist" in changes:
                current = conn.execute(TRACK_SELECT + " WHERE t.id=?", (track_id,)).fetchone()
                album = str(changes.get("album", current["album"] or ""))
                album_artist = str(changes.get("album_artist", current["display_album_artist"] or ""))
                year = changes.get("year", current["year"])
                updates["album_id"] = self._album_id(conn, album, album_artist, year)
                updates.pop("album", None)
                updates.pop("album_artist", None)
                updates["album_artist"] = album_artist
            if "year" in changes and "album" not in changes and "album_artist" not in changes:
                current = conn.execute("SELECT album_id FROM tracks WHERE id=?", (track_id,)).fetchone()
                if current["album_id"]:
                    conn.execute("UPDATE albums SET year=COALESCE(year, ?) WHERE id=?", (changes["year"], current["album_id"]))
            assignments = ", ".join(f"{fields.get(key, key)}=?" for key in updates)
            if assignments:
                conn.execute(f"UPDATE tracks SET {assignments} WHERE id=?", (*updates.values(), track_id))
            fresh = conn.execute(TRACK_SELECT + " WHERE t.id=?", (track_id,)).fetchone()
            return _track(fresh)

    def list_tracks(self, query: str = "", sort_by: str = "title", descending: bool = False,
                    filters: Mapping[str, Any] | None = None) -> list[Track]:
        sort_columns = {
            "title": "t.title", "artist": "ar.name", "album": "al.title", "date_added": "t.date_added",
            "last_played": "t.last_played", "duration_ms": "t.duration_ms", "track_number": "t.track_number",
            "year": "t.year", "play_count": "t.play_count",
        }
        order = sort_columns.get(sort_by, "t.title")
        clauses: list[str] = []
        params: list[Any] = []
        if query:
            pattern = f"%{query.replace(chr(92), chr(92) * 2).replace('%', chr(92) + '%').replace('_', chr(92) + '_')}%"
            clauses.append("(t.title LIKE ? ESCAPE '\\' COLLATE NOCASE OR ar.name LIKE ? ESCAPE '\\' COLLATE NOCASE OR al.title LIKE ? ESCAPE '\\' COLLATE NOCASE OR t.genre LIKE ? ESCAPE '\\' COLLATE NOCASE OR t.path LIKE ? ESCAPE '\\' COLLATE NOCASE)")
            params.extend([pattern] * 5)
        supported_filters = {
            "artist": "ar.name", "album": "al.title", "genre": "t.genre", "is_available": "t.is_available",
        }
        for name, value in (filters or {}).items():
            if name in {"favorite", "is_favorite"}:
                clauses.append("EXISTS (SELECT 1 FROM favorites f WHERE f.track_id=t.id) = ?")
                params.append(int(bool(value)))
                continue
            if name not in supported_filters:
                continue
            clauses.append(f"{supported_filters[name]} = ?")
            params.append(int(value) if name == "is_available" else value)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        direction = "DESC" if descending else "ASC"
        with self.database.transaction() as conn:
            rows = conn.execute(TRACK_SELECT + where + f" ORDER BY {order} {direction}, t.id", params).fetchall()
            return [t for row in rows if (t := _track(row)) is not None]

    def list_albums(self, query: str = "") -> list[Album]:
        pattern = f"%{query}%"
        with self.database.transaction() as conn:
            rows = conn.execute(
                """SELECT a.id,a.title,a.album_artist,a.year,a.artwork_path,COUNT(t.id) AS track_count,
                   COALESCE(SUM(t.duration_ms),0) AS duration_ms FROM albums a LEFT JOIN tracks t ON t.album_id=a.id
                   WHERE (?='' OR a.title LIKE ? COLLATE NOCASE OR a.album_artist LIKE ? COLLATE NOCASE)
                   GROUP BY a.id ORDER BY a.title COLLATE NOCASE,a.album_artist COLLATE NOCASE""",
                (query, pattern, pattern),
            ).fetchall()
            return [Album(r["id"], r["title"], r["album_artist"], r["year"], r["track_count"], r["duration_ms"], r["artwork_path"]) for r in rows]

    def list_artists(self, query: str = "") -> list[Artist]:
        pattern = f"%{query}%"
        with self.database.transaction() as conn:
            rows = conn.execute(
                """SELECT ar.id,ar.name,COUNT(DISTINCT t.id) AS track_count,COUNT(DISTINCT t.album_id) AS album_count
                   FROM artists ar LEFT JOIN tracks t ON t.artist_id=ar.id
                   WHERE (?='' OR ar.name LIKE ? COLLATE NOCASE) GROUP BY ar.id ORDER BY ar.name COLLATE NOCASE""",
                (query, pattern),
            ).fetchall()
            return [Artist(r["id"], r["name"], r["album_count"], r["track_count"]) for r in rows]

    def set_available(self, track_id: int, available: bool) -> None:
        with self.database.transaction(write=True) as conn:
            conn.execute("UPDATE tracks SET is_available=? WHERE id=?", (int(available), track_id))

    def mark_removed_outside_folders(self, roots: Iterable[str | Path], discovered: set[str]) -> int:
        normalized_roots = [Path(normalize_path(root)) for root in roots]
        with self.database.transaction(write=True) as conn:
            rows = conn.execute("SELECT id,path,is_available FROM tracks").fetchall()
            missing_ids = []
            for row in rows:
                track_path = Path(row["path"])
                if any(track_path == root or root in track_path.parents for root in normalized_roots):
                    if row["path"] not in discovered and row["is_available"]:
                        missing_ids.append(row["id"])
            conn.executemany("UPDATE tracks SET is_available=0 WHERE id=?", ((i,) for i in missing_ids))
            return len(missing_ids)

    def update_scan_state(self, path: str | Path, size: int, mtime_ns: int) -> None:
        with self.database.transaction(write=True) as conn:
            conn.execute("UPDATE tracks SET file_size=?,file_mtime_ns=?,is_available=1 WHERE path=?", (size, mtime_ns, normalize_path(path)))

    def get_by_ids(self, ids: Iterable[int]) -> list[Track]:
        ids = list(ids)
        if not ids:
            return []
        with self.database.transaction() as conn:
            placeholders = ",".join("?" for _ in ids)
            rows = conn.execute(TRACK_SELECT + f" WHERE t.id IN ({placeholders})", ids).fetchall()
            by_id = {track.id: track for row in rows if (track := _track(row)) is not None}
            return [by_id[i] for i in ids if i in by_id]
