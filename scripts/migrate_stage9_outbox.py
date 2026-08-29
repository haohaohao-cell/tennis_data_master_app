"""Apply the stage-9 durable message-event schema non-destructively.

SQLite uses the normal runtime upgrade path. PostgreSQL applies the complete
idempotent rendered schema in an explicitly named schema. This command never
deletes, truncates, overwrites, or imports application rows.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sqlite3
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Apply the stage-9 outbox schema without destructive operations.")
    parser.add_argument("--db", type=Path, default=ROOT_DIR / "backend/db/tennis_data_master.sqlite3")
    parser.add_argument("--dsn", help="PostgreSQL DSN; defaults to TENNIS_DATABASE_URL")
    parser.add_argument("--schema", default="public")
    parser.add_argument("--sqlite-only", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.sqlite_only or not (args.dsn or os.getenv("TENNIS_DATABASE_URL")):
        os.environ["TENNIS_DB_PATH"] = str(args.db.resolve())
        from backend.app.core.database import get_connection, initialize_database

        initialize_database()
        with get_connection() as connection:
            table_count = connection.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE type = 'table' AND name = 'outbox_events'"
            ).fetchone()[0]
        if table_count != 1:
            raise RuntimeError("outbox_events was not initialized")
        print("Stage 9 SQLite outbox migration applied idempotently.")
        return

    dsn = args.dsn or os.getenv("TENNIS_DATABASE_URL")
    os.environ["TENNIS_DATABASE_URL"] = dsn
    from backend.app.core import config
    from backend.app.core.postgres import close_pool
    from backend.app.core.postgres_schema import render_postgres_schema

    object.__setattr__(config.settings, "database_url", dsn)
    import psycopg

    try:
        with psycopg.connect(dsn) as connection:
            connection.execute(render_postgres_schema(schema=args.schema))
            connection.commit()
        print("Stage 9 PostgreSQL outbox migration applied idempotently.")
    finally:
        close_pool()


if __name__ == "__main__":
    main()
