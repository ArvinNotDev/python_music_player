"""Connection lifecycle and SQLite migration management."""

from __future__ import annotations

import os
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from .migrations import MIGRATIONS

SCHEMA_VERSION = len(MIGRATIONS)


class DatabaseError(RuntimeError):
    """Persistence-layer failure with the original exception chained."""


def app_data_dir(app_name: str = "PythonMusicPlayer") -> Path:
    """Return a stable per-user data directory without consulting the CWD."""
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
    elif __import__("sys").platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    return base / app_name


def get_database_path() -> Path:
    """Default application database path."""
    return app_data_dir() / "library.sqlite3"


class DatabaseManager:
    """Opens short-lived, thread-local SQLite connections and applies migrations."""

    def __init__(self, path: str | Path | None = None, *, timeout: float = 10.0):
        raw_path = str(path if path is not None else get_database_path())
        self.path = raw_path if raw_path == ":memory:" else str(Path(raw_path).expanduser().resolve(strict=False))
        self.timeout = timeout
        self._migration_lock = threading.RLock()
        self._memory_uri: str | None = None
        self._keeper: sqlite3.Connection | None = None
        if self.path == ":memory:":
            self._memory_uri = f"file:music-player-{uuid.uuid4().hex}?mode=memory&cache=shared"
            self._keeper = self._connect(self._memory_uri, uri=True)
        self.initialize()

    def _connect(self, path: str | None = None, *, uri: bool = False) -> sqlite3.Connection:
        target = path or self._memory_uri or self.path
        try:
            conn = sqlite3.connect(target, timeout=self.timeout, isolation_level=None, uri=uri or self._memory_uri is not None)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute(f"PRAGMA busy_timeout = {max(1, int(self.timeout * 1000))}")
            if self._memory_uri is None:
                conn.execute("PRAGMA synchronous = NORMAL")
            return conn
        except sqlite3.Error as exc:
            raise DatabaseError(f"Could not open database {target!r}: {exc}") from exc

    def initialize(self) -> None:
        with self._migration_lock:
            if self._memory_uri is None:
                try:
                    Path(self.path).expanduser().resolve(strict=False).parent.mkdir(parents=True, exist_ok=True)
                except OSError as exc:
                    raise DatabaseError(f"Could not create database directory: {exc}") from exc
            conn = self._connect()
            try:
                if self._memory_uri is None:
                    conn.execute("PRAGMA journal_mode = WAL")
                conn.execute("BEGIN IMMEDIATE")
                version = int(conn.execute("PRAGMA user_version").fetchone()[0])
                if version > SCHEMA_VERSION:
                    raise DatabaseError(f"Database schema {version} is newer than supported schema {SCHEMA_VERSION}")
                for index in range(version, SCHEMA_VERSION):
                    try:
                        statement = ""
                        for line in MIGRATIONS[index].splitlines(keepends=True):
                            statement += line
                            if sqlite3.complete_statement(statement):
                                conn.execute(statement)
                                statement = ""
                        if statement.strip():
                            raise DatabaseError(f"Migration {index + 1} has an incomplete SQL statement")
                        conn.execute(f"PRAGMA user_version = {index + 1}")
                    except sqlite3.Error:
                        if conn.in_transaction:
                            conn.rollback()
                        raise
                conn.commit()
            except DatabaseError:
                if conn.in_transaction:
                    conn.rollback()
                raise
            except sqlite3.Error as exc:
                if conn.in_transaction:
                    conn.rollback()
                raise DatabaseError(f"Database initialization failed: {exc}") from exc
            finally:
                conn.close()

    @contextmanager
    def transaction(self, *, write: bool = False) -> Iterator[sqlite3.Connection]:
        """Yield an isolated connection and commit or roll back atomically."""
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            yield conn
            conn.commit()
        except Exception as exc:
            if conn.in_transaction:
                conn.rollback()
            if isinstance(exc, DatabaseError):
                raise
            if isinstance(exc, sqlite3.Error):
                raise DatabaseError(f"Database operation failed: {exc}") from exc
            raise
        finally:
            conn.close()

    def close(self) -> None:
        """Close the shared in-memory database keeper, if one was created."""
        if self._keeper is not None:
            self._keeper.close()
            self._keeper = None
