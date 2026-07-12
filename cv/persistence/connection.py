"""SQLite connection policy shared by all CV persistence modules."""

import sqlite3
from pathlib import Path

from cv.config import DEFAULT_DB_PATH


def get_connection(db_path: str | Path = DEFAULT_DB_PATH) -> sqlite3.Connection:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(path)
    connection.execute("PRAGMA foreign_keys = ON;")
    return connection


__all__ = ["DEFAULT_DB_PATH", "get_connection"]
