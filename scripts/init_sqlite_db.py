from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_SCHEMA_PATH = ROOT_DIR / "backend" / "db" / "schema.sql"
DEFAULT_DB_PATH = ROOT_DIR / "backend" / "db" / "tennis_data_master.sqlite3"
EXPECTED_TABLES = ("users", "uploads", "points", "shots")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Initialize the SQLite database for the tennis data master app."
    )
    parser.add_argument(
        "--schema",
        type=Path,
        default=DEFAULT_SCHEMA_PATH,
        help=f"Path to the schema SQL file. Default: {DEFAULT_SCHEMA_PATH}",
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=DEFAULT_DB_PATH,
        help=f"Output SQLite database path. Default: {DEFAULT_DB_PATH}",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Delete the existing database file before initialization.",
    )
    return parser.parse_args()


def initialize_database(schema_path: Path, db_path: Path, force: bool = False) -> list[str]:
    if not schema_path.is_file():
        raise FileNotFoundError(f"Schema file not found: {schema_path}")

    db_path.parent.mkdir(parents=True, exist_ok=True)
    if force and db_path.exists():
        db_path.unlink()

    schema_sql = schema_path.read_text(encoding="utf-8")

    connection = sqlite3.connect(db_path)
    try:
        connection.execute("PRAGMA foreign_keys = OFF;")
        connection.execute("PRAGMA journal_mode = WAL;")
        connection.execute("PRAGMA synchronous = NORMAL;")
        connection.executescript(schema_sql)
        connection.commit()
        connection.execute("PRAGMA foreign_keys = ON;")

        foreign_key_issues = list(connection.execute("PRAGMA foreign_key_check;"))
        if foreign_key_issues:
            raise RuntimeError(f"Foreign key check failed: {foreign_key_issues}")

        tables = [
            row[0]
            for row in connection.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type = 'table'
                  AND name NOT LIKE 'sqlite_%'
                ORDER BY name;
                """
            )
        ]
        return tables
    finally:
        connection.close()


def main() -> None:
    args = parse_args()
    tables = initialize_database(
        schema_path=args.schema.resolve(),
        db_path=args.db.resolve(),
        force=args.force,
    )

    missing_tables = [table for table in EXPECTED_TABLES if table not in tables]
    if missing_tables:
        raise RuntimeError(f"Database initialized but missing tables: {missing_tables}")

    print(f"SQLite database initialized: {args.db.resolve()}")
    print("Tables:")
    for table_name in tables:
        print(f"- {table_name}")


if __name__ == "__main__":
    main()
