"""Playback event and recency API. Position updates are intentionally not recorded."""

from datetime import datetime

from core.models import Track
from database.repositories.history_repository import HistoryRepository


class HistoryService:
    def __init__(self, repository: HistoryRepository):
        self.repository = repository

    def record_play(self, track_id: int) -> None:
        self.repository.record_play(track_id)

    def recently_played(self, limit: int = 20) -> list[Track]:
        return self.repository.recently_played(limit)

    def recently_added(self, limit: int = 20) -> list[Track]:
        return self.repository.recently_added(limit)
