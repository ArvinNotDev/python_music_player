"""Versioned, forward-only SQLite migrations."""

from .v001_initial import MIGRATION as MIGRATION_1
from .v002_library_and_services import MIGRATION as MIGRATION_2

MIGRATIONS = (MIGRATION_1, MIGRATION_2)
