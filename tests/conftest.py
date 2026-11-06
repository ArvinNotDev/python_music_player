from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from database.database_manager import DatabaseManager


@pytest.fixture
def database(tmp_path):
    manager = DatabaseManager(tmp_path / "music.sqlite3")
    yield manager
    manager.close()
