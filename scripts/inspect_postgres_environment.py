"""Read-only PostgreSQL identity and capability check for migration approval."""

from __future__ import annotations

import argparse
import json
import os
import sys

import psycopg


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect PostgreSQL identity and migration privileges without changing the database.")
    parser.add_argument("--dsn", help="PostgreSQL DSN; defaults to TENNIS_DATABASE_URL/TENNIS_POSTGRES_DSN")
    args = parser.parse_args()
    dsn = args.dsn or os.getenv("TENNIS_DATABASE_URL") or os.getenv("TENNIS_POSTGRES_DSN")
    if not dsn:
        raise SystemExit("--dsn or TENNIS_DATABASE_URL is required")
    with psycopg.connect(dsn, connect_timeout=5) as connection:
        row = connection.execute("""
            SELECT version(), current_database(), current_user, current_schema(),
                   current_setting('ssl', true),
                   has_schema_privilege(current_user, current_schema(), 'CREATE'),
                   has_database_privilege(current_user, current_database(), 'CONNECT')
        """).fetchone()
        table_count = connection.execute("""
            SELECT COUNT(*) FROM pg_tables WHERE schemaname = current_schema()
        """).fetchone()[0]
        print(json.dumps({
            "server_version": row[0],
            "database": row[1],
            "user": row[2],
            "schema": row[3],
            "ssl": row[4],
            "can_create_in_schema": bool(row[5]),
            "can_connect_database": bool(row[6]),
            "table_count": int(table_count),
            "dsn_source": "--dsn" if args.dsn else ("TENNIS_DATABASE_URL" if os.getenv("TENNIS_DATABASE_URL") else "TENNIS_POSTGRES_DSN"),
        }, indent=2))


if __name__ == "__main__":
    main()
