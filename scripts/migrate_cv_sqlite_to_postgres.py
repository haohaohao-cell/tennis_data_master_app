"""Copy the legacy CV SQLite database into the PostgreSQL CV schema.

The source file is opened read-only and is never modified.  Table and column
names are discovered from both databases so older CV files without progress
columns remain importable while PostgreSQL keeps the current schema contract.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import sqlite3
import sys
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

DEFAULT_SQLITE_PATH = ROOT_DIR / "cv" / "data" / "output" / "match_analysis.sqlite"
TABLE_ORDER = ("users", "uploads", "points", "shots")


def _quote(identifier: str) -> str:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", identifier):
        raise ValueError(f"Invalid identifier: {identifier!r}")
    return '"' + identifier.replace('"', '""') + '"'


def _source_columns(connection: sqlite3.Connection, table: str) -> list[str]:
    return [row[1] for row in connection.execute(f"PRAGMA table_info({_quote(table)})")]


def _source_tables(connection: sqlite3.Connection) -> set[str]:
    return {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
        )
    }


def _destination_columns(connection: Any, schema: str, table: str) -> set[str]:
    rows = connection.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = %s AND table_name = %s
        """,
        (schema, table),
    ).fetchall()
    return {row["column_name"] if isinstance(row, dict) else row[0] for row in rows}


def migrate(*, sqlite_path: Path, dsn: str | None, schema: str, batch_size: int, dry_run: bool) -> dict[str, int]:
    from cv.persistence.postgres import _validate_schema

    target_schema = _validate_schema(schema)
    if not sqlite_path.is_file():
        raise FileNotFoundError(f"SQLite source not found: {sqlite_path}")
    source = sqlite3.connect(f"file:{sqlite_path.resolve()}?mode=ro", uri=True)
    source.row_factory = sqlite3.Row
    counts: dict[str, int] = {}
    try:
        available = _source_tables(source)
        if dry_run:
            for table in TABLE_ORDER:
                count = int(source.execute(f"SELECT COUNT(*) FROM {_quote(table)}").fetchone()[0]) if table in available else 0
                counts[table] = count
                print(f"{table}: {count} source rows (dry run)")
            return counts
        if not dsn:
            raise ValueError("--dsn or TENNIS_DATABASE_URL is required unless --dry-run is used")
        import psycopg
        from psycopg.rows import dict_row
        from cv.persistence.postgres import initialize_schema

        initialize_schema(dsn=dsn, schema=target_schema)
        with psycopg.connect(dsn, row_factory=dict_row) as destination:
            destination.execute(f"SET search_path TO {_quote(target_schema)}, pg_catalog")
            for table in TABLE_ORDER:
                if table not in available:
                    counts[table] = 0
                    print(f"Skipping missing source table: {table}")
                    continue
                source_columns = _source_columns(source, table)
                destination_columns = _destination_columns(destination, target_schema, table)
                columns = [column for column in source_columns if column in destination_columns]
                if not columns:
                    raise RuntimeError(f"No compatible columns for table {table}")
                select_sql = f"SELECT {', '.join(_quote(column) for column in columns)} FROM {_quote(table)}"
                insert_sql = (
                    f"INSERT INTO {_quote(table)} ({', '.join(_quote(column) for column in columns)}) "
                    f"VALUES ({', '.join(['%s'] * len(columns))}) ON CONFLICT DO NOTHING"
                )
                total = 0
                cursor = source.execute(select_sql)
                while True:
                    rows = cursor.fetchmany(batch_size)
                    if not rows:
                        break
                    payload = [tuple(row[column] for column in columns) for row in rows]
                    total += len(payload)
                    if not dry_run:
                        destination.executemany(insert_sql, payload)
                counts[table] = total
                print(f"{table}: {total} source rows processed")
            if not dry_run:
                destination.commit()
    finally:
        source.close()
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate the legacy CV SQLite database to PostgreSQL.")
    parser.add_argument("--sqlite", type=Path, default=DEFAULT_SQLITE_PATH, help="Read-only SQLite source file.")
    parser.add_argument("--dsn", help="PostgreSQL DSN; required unless --dry-run is used.")
    parser.add_argument("--schema", default="cv_analysis", help="Target PostgreSQL schema (default: cv_analysis).")
    parser.add_argument("--batch-size", type=int, default=500, help="Rows per PostgreSQL batch (default: 500).")
    parser.add_argument("--dry-run", action="store_true", help="Inspect and count rows without inserting.")
    args = parser.parse_args()
    if args.batch_size <= 0:
        parser.error("--batch-size must be positive")
    try:
        migrate(
            sqlite_path=args.sqlite.resolve(),
            dsn=args.dsn,
            schema=args.schema,
            batch_size=args.batch_size,
            dry_run=args.dry_run,
        )
    except ImportError as error:
        raise SystemExit("Install backend/requirements.txt (psycopg[binary,pool]) before migrating CV data.") from error


if __name__ == "__main__":
    main()
