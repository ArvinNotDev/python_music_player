"""Meaningful play events and recently-played queries."""

from __future__ import annotations

from datetime import datetime, timezone

from core.models import Track
from database.database_manager import DatabaseManager
from .track_repository import TRACK_SELECT, _track


class HistoryRepository:
    def __init__(self, database: DatabaseManager):
        self.database = database

    def record_play(self, track_id: int, played_at: datetime | None = None) -> None:
        timestamp = (played_at or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat()
        with self.database.transaction(write=True) as conn:
            if not conn.execute("SELECT 1 FROM tracks WHERE id=?", (track_id,)).fetchone():
                raise KeyError(f"Track {track_id} does not exist")
            conn.execute("INSERT INTO playback_history(track_id,played_at) VALUES(?,?)", (track_id, timestamp))
            conn.execute("UPDATE tracks SET play_count=play_count+1,last_played=? WHERE id=?", (timestamp, track_id))

    def recently_played(self, limit: int = 20) -> list[Track]:
        limit = max(0, int(limit))
        with self.database.transaction() as conn:
            rows = conn.execute(
                TRACK_SELECT + " JOIN (SELECT track_id,MAX(played_at) AS played_at FROM playback_history GROUP BY track_id) h ON h.track_id=t.id ORDER BY h.played_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [track for row in rows if (track := _track(row)) is not None]

    def recently_added(self, limit: int = 20) -> list[Track]:
        limit = max(0, int(limit))
        with self.database.transaction() as conn:
            rows = conn.execute(TRACK_SELECT + " ORDER BY t.date_added DESC,t.id DESC LIMIT ?", (limit,)).fetchall()
            return [track for row in rows if (track := _track(row)) is not None]
