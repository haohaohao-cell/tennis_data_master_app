"""Initialize the full SQLite schema used by the tennis analysis system."""

from __future__ import annotations

import argparse
from pathlib import Path

from .connection import DEFAULT_DB_PATH, get_connection
from .core_tables import create_core_tables
from .points_schema import create_points_table
from .shots_schema import create_shots_table


def initialize_all_tables(db_path: str | Path = DEFAULT_DB_PATH) -> Path:
    path = Path(db_path)
    create_core_tables(path)
    create_points_table(path)
    create_shots_table(path)
    return path


def rebuild_all_tables(db_path: str | Path = DEFAULT_DB_PATH) -> Path:
    path = Path(db_path)

    with get_connection(path) as connection:
        connection.executescript(
            """
            DROP TABLE IF EXISTS shots;
            DROP TABLE IF EXISTS points;
            DROP TABLE IF EXISTS videos;
            DROP TABLE IF EXISTS uploads;
            DROP TABLE IF EXISTS users;
            """
        )
        connection.commit()

    return initialize_all_tables(path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Initialize all SQLite tables.")
    parser.add_argument(
        "--db-path",
        type=Path,
        default=DEFAULT_DB_PATH,
        help="Target SQLite database path.",
    )
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="Drop existing tables and rebuild the full schema.",
    )
    args = parser.parse_args()

    if args.rebuild:
        db_path = rebuild_all_tables(args.db_path)
    else:
        db_path = initialize_all_tables(args.db_path)
    print(f"Full SQLite schema is ready: {db_path}")


if __name__ == "__main__":
    main()
