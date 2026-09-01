"""Apply the stage-9 durable message-event schema non-destructively.

PostgreSQL applies the complete idempotent rendered schema in an explicitly
named schema. This command never deletes, truncates, overwrites, or imports
application rows.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Apply the stage-9 outbox schema without destructive operations.")
    parser.add_argument("--db", type=Path, default=ROOT_DIR / "backend/db/tennis_data_master.sqlite3")
    parser.add_argument("--dsn", help="PostgreSQL DSN; defaults to TENNIS_DATABASE_URL/TENNIS_POSTGRES_DSN")
    parser.add_argument("--schema", default="public")
    parser.add_argument(
        "--sqlite-only",
        action="store_true",
        help="Deprecated and rejected: SQLite is no longer an application runtime database.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.sqlite_only:
        raise SystemExit("--sqlite-only is no longer supported; initialize PostgreSQL instead.")

    if not (args.dsn or os.getenv("TENNIS_DATABASE_URL") or os.getenv("TENNIS_POSTGRES_DSN")):
        raise SystemExit("--dsn or TENNIS_DATABASE_URL is required; SQLite runtime migration is disabled.")

    dsn = args.dsn or os.getenv("TENNIS_DATABASE_URL") or os.getenv("TENNIS_POSTGRES_DSN")
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
