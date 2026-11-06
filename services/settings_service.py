"""Predictable persistent key/value settings API."""

from typing import Any

from database.repositories.settings_repository import SettingsRepository


class SettingsService:
    def __init__(self, repository: SettingsRepository):
        self.repository = repository

    def get(self, key: str, default: Any = None) -> Any:
        return self.repository.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self.repository.set(key, value)

    def all(self) -> dict[str, Any]:
        return self.repository.all()
