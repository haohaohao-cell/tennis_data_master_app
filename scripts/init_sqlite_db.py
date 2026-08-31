from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))
DEFAULT_SCHEMA_PATH = ROOT_DIR / "backend" / "db" / "schema.sql"
DEFAULT_DB_PATH = ROOT_DIR / "backend" / "db" / "tennis_data_master.sqlite3"
EXPECTED_TABLES = (
    "users",
    "admin_users",
    "admin_credentials",
    "auth_identities",
    "auth_sessions",
    "auth_verification_codes",
    "coach_applications",
    "coach_profiles",
    "lessons",
    "lesson_students",
    "tennis_activities",
    "videos",
    "video_shares",
    "social_posts",
    "social_post_stats",
    "post_reactions",
    "post_favorites",
    "post_comments",
    "post_media",
    "user_follows",
    "user_social_stats",
    "user_blocks",
    "user_privacy_settings",
    "user_notification_preferences",
    "user_post_views",
    "user_post_hides",
    "chat_conversations",
    "chat_conversation_members",
    "chat_messages",
    "outbox_events",
    "chat_message_media",
    "chat_message_attachments",
    "chat_message_requests",
    "post_shares",
    "notification_events",
    "user_notifications",
    "user_inbox_counters",
    "content_reports",
    "points",
    "shots",
)


def list_tables(db_path: Path) -> list[str]:
    connection = sqlite3.connect(db_path)
    try:
        return [
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
    finally:
        connection.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Initialize a legacy SQLite source for one-time PostgreSQL migration."
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
    # This command is intentionally isolated from the application runtime. It
    # creates a disposable SQLite source for the one-time PostgreSQL transfer.
    # The checked-in backend schema already contains the message tables; the
    # incremental file is included for callers supplying an older/custom base.
    incremental_schema_path = schema_path.parent / "social_message_schema.sql"
    if incremental_schema_path.is_file() and schema_path.resolve() == DEFAULT_SCHEMA_PATH.resolve():
        schema_sql += "\n" + incremental_schema_path.read_text(encoding="utf-8")

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

        return list_tables(db_path)
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

    print(f"Legacy SQLite migration source initialized: {args.db.resolve()}")
    print("Tables:")
    for table_name in tables:
        print(f"- {table_name}")


if __name__ == "__main__":
    main()
