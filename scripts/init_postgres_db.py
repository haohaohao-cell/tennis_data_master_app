"""Initialize PostgreSQL from the repository's deterministic rendered schema."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from backend.app.core.postgres import close_pool, connection
from backend.app.core.postgres_schema import render_postgres_schema


def main() -> None:
    parser = argparse.ArgumentParser(description="Initialize the configured PostgreSQL database.")
    parser.add_argument("--dsn", help="PostgreSQL DSN; defaults to TENNIS_DATABASE_URL/TENNIS_POSTGRES_DSN")
    parser.add_argument("--schema", default="public", help="Explicit target schema (default: public).")
    parser.add_argument("--render", type=Path, help="Write the rendered schema SQL to this path without connecting.")
    args = parser.parse_args()
    schema = render_postgres_schema(schema=args.schema)
    if args.render:
        args.render.parent.mkdir(parents=True, exist_ok=True)
        args.render.write_text(schema, encoding="utf-8")
        print(f"Rendered PostgreSQL schema: {args.render.resolve()}")
        return
    if args.dsn:
        import os
        os.environ["TENNIS_DATABASE_URL"] = args.dsn
        # Settings is imported by the adapter at module load, so a CLI DSN is
        # passed through before opening the connection only for this command.
        from backend.app.core import config
        object.__setattr__(config.settings, "database_url", args.dsn)
    try:
        with connection() as db:
            db.raw.execute(schema)
            db.raw.commit()
        print("PostgreSQL schema initialized.")
    finally:
        close_pool()


if __name__ == "__main__":
    main()
