"""Core PostgreSQL business tables for the tennis analysis system.

Minimal schema:
- users: registered users
- uploads: one upload plus its video metadata and analysis status
"""

from __future__ import annotations

import argparse
from pathlib import Path

from .connection import DEFAULT_DB_PATH, get_connection


CREATE_CORE_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS users (
    user_id TEXT PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    display_name TEXT,
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'disabled')),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_users_email
ON users(email);


CREATE TABLE IF NOT EXISTS uploads (
    upload_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    original_filename TEXT NOT NULL,
    stored_path TEXT NOT NULL,
    file_size_bytes INTEGER CHECK (file_size_bytes IS NULL OR file_size_bytes >= 0),
    duration_sec REAL CHECK (duration_sec IS NULL OR duration_sec >= 0),
    fps REAL CHECK (fps IS NULL OR fps > 0),
    width INTEGER CHECK (width IS NULL OR width > 0),
    height INTEGER CHECK (height IS NULL OR height > 0),
    status TEXT NOT NULL DEFAULT 'uploaded'
        CHECK (status IN ('uploaded', 'processing', 'completed', 'failed')),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    started_at TEXT,
    finished_at TEXT,
    error_message TEXT,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_uploads_user_id
ON uploads(user_id);

CREATE INDEX IF NOT EXISTS idx_uploads_status
ON uploads(status);

CREATE INDEX IF NOT EXISTS idx_uploads_created_at
ON uploads(created_at);

CREATE INDEX IF NOT EXISTS idx_uploads_original_filename
ON uploads(original_filename);
"""

UPLOAD_PROGRESS_COLUMNS: dict[str, str] = {
    "progress_percent": "INTEGER NOT NULL DEFAULT 0",
    "progress_stage": "TEXT",
    "progress_message": "TEXT",
    "processed_frames": "INTEGER",
    "total_frames": "INTEGER",
}


def _ensure_upload_progress_columns(connection) -> None:
    existing_columns = {
        row["column_name"]
        for row in connection.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = current_schema() AND table_name = 'uploads'
            """
        ).fetchall()
    }
    for column_name, column_sql in UPLOAD_PROGRESS_COLUMNS.items():
        if column_name in existing_columns:
            continue
        connection.execute(f"ALTER TABLE uploads ADD COLUMN {column_name} {column_sql}")


def create_core_tables(db_path: str | Path = DEFAULT_DB_PATH) -> Path:
    path = Path(db_path)

    with get_connection(path) as connection:
        connection.executescript(CREATE_CORE_TABLES_SQL)
        _ensure_upload_progress_columns(connection)
        connection.commit()

    return path


def main() -> None:
    parser = argparse.ArgumentParser(description="Create the CV PostgreSQL core tables.")
    parser.add_argument(
        "--db-path",
        type=Path,
        default=DEFAULT_DB_PATH,
        help="Deprecated compatibility path; PostgreSQL DSN comes from environment.",
    )
    args = parser.parse_args()

    db_path = create_core_tables(args.db_path)
    print(f"CV PostgreSQL core tables are ready (schema from environment); path ignored: {db_path}")


if __name__ == "__main__":
    main()
