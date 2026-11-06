"""SQLite persistence layer for the music player."""

from .database_manager import DatabaseManager, DatabaseError, get_database_path

__all__ = ["DatabaseError", "DatabaseManager", "get_database_path"]
