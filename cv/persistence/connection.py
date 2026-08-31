"""PostgreSQL connection policy shared by all CV persistence modules."""

from pathlib import Path

from cv.config import DEFAULT_DB_PATH
from .postgres import PostgresConnection, get_connection as _get_postgres_connection


def get_connection(db_path: str | Path = DEFAULT_DB_PATH) -> PostgresConnection:
    """Open a PostgreSQL connection; ``db_path`` remains a compatibility arg."""
    return _get_postgres_connection(db_path)


__all__ = ["DEFAULT_DB_PATH", "get_connection"]
