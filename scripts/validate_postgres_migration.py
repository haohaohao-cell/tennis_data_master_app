"""Compare a PostgreSQL destination with its read-only SQLite source."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from scripts.migrate_sqlite_to_postgres import PREFERRED_ORDER, source_tables, table_columns

EXPECTED_POSTGRES_TABLES = {
    "users", "admin_users", "admin_credentials", "auth_identities",
    "auth_sessions", "auth_verification_codes", "coach_applications",
    "coach_profiles", "lessons", "lesson_students", "tennis_activities",
    "videos", "video_shares", "social_posts", "social_post_stats",
    "post_reactions", "post_favorites", "post_comments", "post_media",
    "user_follows", "user_social_stats", "user_blocks",
    "user_privacy_settings", "user_notification_preferences", "user_post_views",
    "user_post_hides", "chat_conversations", "chat_conversation_members",
    "chat_messages", "outbox_events", "chat_message_media",
    "chat_message_attachments", "chat_message_requests", "post_shares",
    "notification_events", "user_notifications", "user_inbox_counters",
    "content_reports", "points", "shots",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate row counts, keys, foreign keys, JSON fields, and message counters after migration.")
    parser.add_argument("--sqlite", type=Path, default=ROOT_DIR / "backend/db/tennis_data_master.sqlite3")
    parser.add_argument("--dsn", help="PostgreSQL DSN. Required unless TENNIS_DATABASE_URL is set.")
    parser.add_argument("--report", type=Path)
    parser.add_argument("--schema", default="public", help="Explicit destination schema (default: public).")
    return parser.parse_args()


def validate_schema_name(value: str) -> str:
    if not value or not value.replace("_", "a").isalnum() or not (value[0].isalpha() or value[0] == "_"):
        raise ValueError("--schema must be a simple PostgreSQL identifier")
    return value


def file_fingerprint(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"path": str(path), "exists": False}
    return {
        "path": str(path), "exists": True, "size_bytes": path.stat().st_size,
        "mtime_ns": path.stat().st_mtime_ns,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def count(pg: Any, table: str) -> int:
    return int(pg.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])


def validate(args: argparse.Namespace) -> dict[str, Any]:
    source = sqlite3.connect(f"file:{args.sqlite.resolve()}?mode=ro", uri=True)
    source.row_factory = sqlite3.Row
    try:
        dsn = args.dsn or __import__("os").getenv("TENNIS_DATABASE_URL") or __import__("os").getenv("TENNIS_POSTGRES_DSN")
        if not dsn:
            raise ValueError("--dsn or TENNIS_DATABASE_URL is required")
        import psycopg
        schema = validate_schema_name(args.schema)
        with psycopg.connect(dsn) as pg:
            identity = pg.execute("""
                SELECT version(), current_database(), current_user,
                       current_schema(), current_setting('search_path'),
                       has_schema_privilege(current_user, current_schema(), 'USAGE'),
                       has_schema_privilege(current_user, current_schema(), 'CREATE')
            """).fetchone()
            pg.execute(f'SET search_path TO "{schema}", pg_catalog')
            target_identity = pg.execute("""
                SELECT current_database(), current_user, current_schema(),
                       has_schema_privilege(current_user, current_schema(), 'USAGE'),
                       has_schema_privilege(current_user, current_schema(), 'CREATE')
            """).fetchone()
            tables = source_tables(source)
            target_table_names = {
                row[0] for row in pg.execute(
                    "SELECT tablename FROM pg_tables WHERE schemaname = %s", (schema,)
                ).fetchall()
            }
            table_results: dict[str, Any] = {}
            for table in tables:
                source_count = int(source.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])
                target_count = count(pg, table)
                table_results[table] = {"source": source_count, "target": target_count, "match": source_count == target_count}
            target_extra_rows = {
                table: result["target"] - result["source"]
                for table, result in table_results.items()
                if result["target"] > result["source"]
            }
            missing_expected = sorted(EXPECTED_POSTGRES_TABLES - target_table_names)
            fk_rows = pg.execute("""
                SELECT tc.table_name, kcu.column_name, ccu.table_name AS foreign_table_name,
                       ccu.column_name AS foreign_column_name
                FROM information_schema.table_constraints AS tc
                JOIN information_schema.key_column_usage AS kcu ON tc.constraint_name = kcu.constraint_name AND tc.table_schema = kcu.table_schema
                JOIN information_schema.constraint_column_usage AS ccu ON ccu.constraint_name = tc.constraint_name AND ccu.table_schema = tc.table_schema
                WHERE tc.constraint_type = 'FOREIGN KEY' AND tc.table_schema = current_schema()
            """).fetchall()
            unique_checks: dict[str, int] = {}
            if "chat_messages" in target_table_names:
                unique_checks["message_seq_duplicates"] = int(pg.execute("""
                    SELECT COUNT(*) FROM (
                        SELECT conversation_id, message_seq FROM chat_messages
                        GROUP BY conversation_id, message_seq HAVING COUNT(*) > 1
                    ) d
                """).fetchone()[0])
                unique_checks["client_message_id_duplicates"] = int(pg.execute("""
                    SELECT COUNT(*) FROM (
                        SELECT sender_user_id, client_message_id FROM chat_messages
                        WHERE client_message_id IS NOT NULL
                        GROUP BY sender_user_id, client_message_id HAVING COUNT(*) > 1
                    ) d
                """).fetchone()[0])
            if "post_shares" in target_table_names:
                unique_checks["post_share_client_message_duplicates"] = int(pg.execute("""
                    SELECT COUNT(*) FROM (
                        SELECT shared_by_user_id, client_message_id FROM post_shares
                        WHERE client_message_id IS NOT NULL
                        GROUP BY shared_by_user_id, client_message_id HAVING COUNT(*) > 1
                    ) d
                """).fetchone()[0])
            if "chat_message_media" in target_table_names:
                unique_checks["media_upload_id_duplicates"] = int(pg.execute("""
                    SELECT COUNT(*) FROM (
                        SELECT owner_user_id, client_upload_id FROM chat_message_media
                        GROUP BY owner_user_id, client_upload_id HAVING COUNT(*) > 1
                    ) d
                """).fetchone()[0])
            if "chat_message_attachments" in target_table_names:
                unique_checks["media_binding_duplicates"] = int(pg.execute("""
                    SELECT COUNT(*) FROM (
                        SELECT media_id FROM chat_message_attachments
                        WHERE media_id IS NOT NULL GROUP BY media_id HAVING COUNT(*) > 1
                    ) d
                """).fetchone()[0])
            message_checks: dict[str, int] = {}
            if {"chat_conversations", "chat_messages"} <= target_table_names:
                message_checks["last_message_mismatches"] = int(pg.execute("""
                    SELECT COUNT(*) FROM chat_conversations c
                    WHERE c.last_message_id IS NOT NULL AND NOT EXISTS (
                        SELECT 1 FROM chat_messages m WHERE m.message_id = c.last_message_id
                          AND m.conversation_id = c.conversation_id AND m.message_seq = c.last_message_seq
                    )
                """).fetchone()[0])
                message_checks["message_seq_gaps"] = int(pg.execute("""
                    SELECT COUNT(*) FROM (
                        SELECT conversation_id FROM chat_messages
                        GROUP BY conversation_id
                        HAVING MIN(message_seq) <> 1 OR MAX(message_seq) <> COUNT(*)
                    ) d
                """).fetchone()[0])
            json_checks: dict[str, int] = {}
            for table in ("chat_messages", "chat_message_attachments", "notification_events", "post_shares"):
                if table not in tables:
                    continue
                columns = set(table_columns(source, table))
                candidates = [column for column in ("payload_json",) if column in columns]
                for column in candidates:
                    invalid = 0
                    for (value,) in pg.execute(f'SELECT "{column}" FROM "{table}" WHERE "{column}" IS NOT NULL'):
                        try:
                            json.loads(value)
                        except (TypeError, ValueError):
                            invalid += 1
                    json_checks[f"{table}.{column}"] = invalid
            counters: dict[str, Any] = {}
            if "chat_conversation_members" in tables:
                counters["conversation_unread_drift"] = int(pg.execute("""
                    SELECT COUNT(*) FROM chat_conversation_members cm
                    WHERE cm.unread_count <> (
                        SELECT COUNT(*) FROM chat_messages m
                        WHERE m.conversation_id = cm.conversation_id AND m.message_seq > cm.last_read_message_seq
                          AND m.sender_user_id IS NOT NULL AND m.sender_user_id <> cm.user_id
                          AND m.status = 'sent' AND m.deleted_at IS NULL
                    )
                """).fetchone()[0])
            if {"user_inbox_counters", "chat_conversation_members", "chat_conversations"} <= target_table_names:
                counters["inbox_direct_drift"] = int(pg.execute("""
                    SELECT COUNT(*) FROM user_inbox_counters u
                    WHERE u.unread_direct_message_count <> (
                        SELECT COALESCE(SUM(cm.unread_count), 0)
                        FROM chat_conversation_members cm
                        JOIN chat_conversations c ON c.conversation_id = cm.conversation_id
                        WHERE cm.user_id = u.user_id AND cm.status = 'active' AND c.conversation_type = 'direct'
                    )
                """).fetchone()[0])
                counters["inbox_group_drift"] = int(pg.execute("""
                    SELECT COUNT(*) FROM user_inbox_counters u
                    WHERE u.unread_group_message_count <> (
                        SELECT COALESCE(SUM(cm.unread_count), 0)
                        FROM chat_conversation_members cm
                        JOIN chat_conversations c ON c.conversation_id = cm.conversation_id
                        WHERE cm.user_id = u.user_id AND cm.status = 'active' AND c.conversation_type = 'group'
                    )
                """).fetchone()[0])
            if "chat_message_media" in target_table_names:
                counters["invalid_media_storage_namespace"] = int(pg.execute("""
                    SELECT COUNT(*) FROM chat_message_media
                    WHERE storage_key LIKE 'post/%' OR storage_key LIKE 'videos/%' OR storage_key LIKE 'tennis_activity/%'
                """).fetchone()[0])
            expected_extension_tables = sorted(
                (target_table_names - set(tables)) & EXPECTED_POSTGRES_TABLES
            )
            unexpected_extra_tables = sorted(
                (target_table_names - set(tables)) - EXPECTED_POSTGRES_TABLES
            )
            report = {
                "command": "validate_postgres_migration.py",
                "run_at_utc": datetime.now(timezone.utc).isoformat(),
                "sqlite": str(args.sqlite.resolve()),
                "source_sha256": hashlib.sha256(args.sqlite.read_bytes()).hexdigest(),
                "source_files": {
                    "main": file_fingerprint(args.sqlite),
                    "wal": file_fingerprint(Path(str(args.sqlite) + "-wal")),
                    "shm": file_fingerprint(Path(str(args.sqlite) + "-shm")),
                },
                "target": {"database": target_identity[0], "user": target_identity[1], "schema": target_identity[2], "search_path_before": identity[4], "schema_usage": bool(target_identity[3]), "schema_create": bool(target_identity[4]), "server_version": identity[0]},
                "tables": table_results,
                "foreign_key_constraints": len(fk_rows),
                "missing_expected_tables": missing_expected,
                "unique_checks": unique_checks,
                "message_checks": message_checks,
                "json_invalid": json_checks,
                "counter_checks": counters,
                "source_schema_table_count": len(tables),
                "target_schema_table_count": len(target_table_names),
                "target_extra_tables": unexpected_extra_tables,
                "target_expected_extension_tables": expected_extension_tables,
                "target_extra_rows": target_extra_rows,
                "target_data_state": "MIXED_DATA" if target_extra_rows or unexpected_extra_tables else "CLEAN_SCHEMA",
                "status": "ok" if not missing_expected and not target_extra_rows and not unexpected_extra_tables and all(item["match"] for item in table_results.values()) and not any(unique_checks.values()) and not any(message_checks.values()) and not any(json_checks.values()) and not any(counters.values()) else "differences_found",
            }
            return report
    finally:
        source.close()


def main() -> None:
    args = parse_args()
    report = validate(args)
    encoded = json.dumps(report, ensure_ascii=False, indent=2, default=str)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(encoded + "\n", encoding="utf-8")
    print(encoded)
    if report["status"] != "ok":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
