"""Initialize the CV analysis tables in PostgreSQL."""

from __future__ import annotations

import argparse
import os

from cv.persistence.postgres import initialize_schema


def main() -> None:
    parser = argparse.ArgumentParser(description="Initialize CV PostgreSQL tables.")
    parser.add_argument("--dsn", help="PostgreSQL DSN; defaults to TENNIS_CV_DATABASE_URL/TENNIS_DATABASE_URL")
    parser.add_argument("--schema", default="cv_analysis", help="Target schema (default: cv_analysis).")
    args = parser.parse_args()
    if args.dsn:
        os.environ["TENNIS_CV_DATABASE_URL"] = args.dsn
    initialize_schema(dsn=args.dsn, schema=args.schema)
    print(f"CV PostgreSQL schema initialized: {args.schema}")


if __name__ == "__main__":
    main()
