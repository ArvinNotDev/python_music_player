"""Typed JSON settings stored in SQLite."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from database.database_manager import DatabaseManager


class SettingsRepository:
    def __init__(self, database: DatabaseManager):
        self.database = database

    def get(self, key: str, default: Any = None) -> Any:
        with self.database.transaction() as conn:
            row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
            if not row:
                return default
            try:
                return json.loads(row["value"])
            except (TypeError, json.JSONDecodeError):
                return default

    def set(self, key: str, value: Any) -> None:
        if not key or not isinstance(key, str):
            raise ValueError("setting key must be a non-empty string")
        try:
            encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Setting {key!r} is not JSON serializable") from exc
        with self.database.transaction(write=True) as conn:
            conn.execute(
                "INSERT INTO settings(key,value,updated_at) VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at",
                (key, encoded, datetime.now(timezone.utc).isoformat()),
            )

    def all(self) -> dict[str, Any]:
        with self.database.transaction() as conn:
            rows = conn.execute("SELECT key,value FROM settings ORDER BY key").fetchall()
            values: dict[str, Any] = {}
            for row in rows:
                try:
                    values[row["key"]] = json.loads(row["value"])
                except (TypeError, json.JSONDecodeError):
                    values[row["key"]] = None
            return values
