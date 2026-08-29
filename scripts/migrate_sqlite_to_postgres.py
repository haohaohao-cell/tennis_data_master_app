"""Auditable, non-destructive SQLite -> PostgreSQL data transfer.

The source is opened read-only. Destination rows are never overwritten. A
repeat run skips identical primary-key rows and reports conflicting rows for
manual reconciliation. Table commits make a failed run restartable without a
checkpoint file or destructive rollback.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

PREFERRED_ORDER = [
    "users", "admin_users", "admin_credentials", "auth_identities", "auth_sessions",
    "auth_verification_codes", "user_privacy_settings", "user_notification_preferences",
    "user_follows", "user_blocks", "user_social_stats", "lessons", "lesson_students",
    "tennis_activities", "videos", "video_shares", "social_posts", "social_post_stats",
    "post_media", "post_reactions", "post_favorites", "post_comments", "user_post_views",
    "user_post_hides", "chat_conversations", "chat_messages", "chat_conversation_members",
    "chat_message_media", "chat_message_attachments", "outbox_events", "chat_message_requests", "post_shares",
    "notification_events", "user_notifications", "user_inbox_counters", "content_reports",
    "points", "shots",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Transfer SQLite data to PostgreSQL without modifying the source database.")
    parser.add_argument("--sqlite", type=Path, default=ROOT_DIR / "backend/db/tennis_data_master.sqlite3")
    parser.add_argument("--dsn", help="PostgreSQL DSN. Required unless TENNIS_DATABASE_URL is set.")
    parser.add_argument("--dry-run", action="store_true", help="Read and validate source rows without connecting or writing to PostgreSQL.")
    parser.add_argument("--batch-size", type=int, default=500, help="Rows per destination insert batch (default: 500).")
    parser.add_argument("--table", action="append", dest="tables", help="Migrate only this table; may be repeated.")
    parser.add_argument("--report", type=Path, help="Optional JSON report output path.")
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
        "path": str(path),
        "exists": True,
        "size_bytes": path.stat().st_size,
        "mtime_ns": path.stat().st_mtime_ns,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def source_tables(connection: sqlite3.Connection) -> list[str]:
    names = [row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
    preferred = [name for name in PREFERRED_ORDER if name in names]
    return preferred + [name for name in names if name not in preferred]


def table_columns(connection: sqlite3.Connection, table: str) -> list[str]:
    return [row[1] for row in connection.execute(f'PRAGMA table_info("{table}")')]


def primary_key(connection: sqlite3.Connection, table: str) -> list[str]:
    rows = sorted(connection.execute(f'PRAGMA table_info("{table}")').fetchall(), key=lambda row: row[5])
    return [row[1] for row in rows if row[5]]


def normalize(value: Any) -> Any:
    if isinstance(value, bytes):
        return value.hex()
    return value


def _count(connection: sqlite3.Connection, sql: str, params: tuple[Any, ...] = ()) -> int:
    return int(connection.execute(sql, params).fetchone()[0])


def _json_invalid(connection: sqlite3.Connection, table: str) -> int:
    if "payload_json" not in table_columns(connection, table):
        return 0
    invalid = 0
    for (value,) in connection.execute(f'SELECT payload_json FROM "{table}" WHERE payload_json IS NOT NULL'):
        try:
            json.loads(value)
        except (TypeError, ValueError):
            invalid += 1
    return invalid


def validate_source(connection: sqlite3.Connection, tables: list[str]) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    counts: dict[str, int] = {}
    details: dict[str, Any] = {
        "null_primary_keys": {},
        "duplicate_idempotency_keys": {},
        "orphan_records": {},
        "json_invalid": {},
        "cache_drift": {},
    }
    for table in tables:
        columns = table_columns(connection, table)
        pk = primary_key(connection, table)
        count = connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
        counts[table] = count
        if not pk:
            issues.append({"table": table, "kind": "missing_primary_key"})
            continue
        null_pk = _count(connection, f'SELECT COUNT(*) FROM "{table}" WHERE "{pk[0]}" IS NULL')
        if null_pk:
            details["null_primary_keys"][table] = null_pk
        duplicate = connection.execute(
            f'SELECT COUNT(*) FROM (SELECT "{pk[0]}", COUNT(*) FROM "{table}" GROUP BY "{pk[0]}" HAVING COUNT(*) > 1)'
        ).fetchone()[0]
        if duplicate:
            issues.append({"table": table, "kind": "duplicate_primary_key", "count": duplicate})
    foreign_keys = []
    for table in tables:
        for row in connection.execute(f'PRAGMA foreign_key_check("{table}")'):
            foreign_keys.append({"table": table, "detail": list(row)})
    if foreign_keys:
        issues.append({"kind": "foreign_key_issues", "items": foreign_keys})
    for table, columns in {
        "chat_messages": ("sender_user_id", "client_message_id"),
        "post_shares": ("shared_by_user_id", "client_message_id"),
        "chat_message_media": ("owner_user_id", "client_upload_id"),
    }.items():
        if table in tables and all(column in table_columns(connection, table) for column in columns):
            duplicate_count = _count(
                connection,
                f'SELECT COUNT(*) FROM (SELECT "{columns[0]}", "{columns[1]}", COUNT(*) FROM "{table}" WHERE "{columns[1]}" IS NOT NULL GROUP BY "{columns[0]}", "{columns[1]}" HAVING COUNT(*) > 1)',
            )
            if duplicate_count:
                details["duplicate_idempotency_keys"][table] = duplicate_count
                issues.append({"table": table, "kind": "duplicate_idempotency_key", "count": duplicate_count})

    orphan_queries = {
        "messages_without_conversation": (("chat_messages", "chat_conversations"), "SELECT COUNT(*) FROM chat_messages m LEFT JOIN chat_conversations c ON c.conversation_id = m.conversation_id WHERE c.conversation_id IS NULL"),
        "attachments_without_message": (("chat_message_attachments", "chat_messages"), "SELECT COUNT(*) FROM chat_message_attachments a LEFT JOIN chat_messages m ON m.message_id = a.message_id WHERE m.message_id IS NULL"),
        "media_without_owner": (("chat_message_media", "users"), "SELECT COUNT(*) FROM chat_message_media x LEFT JOIN users u ON u.user_id = x.owner_user_id WHERE u.user_id IS NULL"),
        "media_attachment_without_media": (("chat_message_attachments", "chat_message_media"), "SELECT COUNT(*) FROM chat_message_attachments a LEFT JOIN chat_message_media x ON x.media_id = a.media_id WHERE a.media_id IS NOT NULL AND x.media_id IS NULL"),
    }
    for name, (required_tables, query) in orphan_queries.items():
        if all(table in tables for table in required_tables):
            value = _count(connection, query)
            if value:
                details["orphan_records"][name] = value
                issues.append({"kind": "orphan_record", "name": name, "count": value})

    for table in ("chat_messages", "chat_message_attachments", "notification_events", "post_shares"):
        if table in tables:
            invalid = _json_invalid(connection, table)
            if invalid:
                details["json_invalid"][table] = invalid
                issues.append({"table": table, "kind": "invalid_json", "count": invalid})

    if "chat_conversations" in tables and "chat_messages" in tables:
        mismatch = _count(connection, """
            SELECT COUNT(*) FROM chat_conversations c
            WHERE c.last_message_id IS NOT NULL AND NOT EXISTS (
                SELECT 1 FROM chat_messages m WHERE m.message_id = c.last_message_id
                  AND m.conversation_id = c.conversation_id AND m.message_seq = c.last_message_seq
            )
        """)
        if mismatch:
            details["cache_drift"]["conversation_last_message"] = mismatch

    if {"users", "chat_conversation_members", "chat_conversations", "user_inbox_counters"} <= set(tables):
        inbox_drift = _count(connection, """
            SELECT COUNT(*)
            FROM users u
            LEFT JOIN user_inbox_counters i ON i.user_id = u.user_id
            WHERE COALESCE(i.unread_direct_message_count, 0) <> COALESCE((
                SELECT SUM(cm.unread_count)
                FROM chat_conversation_members cm
                JOIN chat_conversations c ON c.conversation_id = cm.conversation_id
                WHERE cm.user_id = u.user_id
                  AND cm.status = 'active'
                  AND c.conversation_type = 'direct'
            ), 0)
            OR COALESCE(i.unread_group_message_count, 0) <> COALESCE((
                SELECT SUM(cm.unread_count)
                FROM chat_conversation_members cm
                JOIN chat_conversations c ON c.conversation_id = cm.conversation_id
                WHERE cm.user_id = u.user_id
                  AND cm.status = 'active'
                  AND c.conversation_type = 'group'
            ), 0)
        """)
        if inbox_drift:
            details["cache_drift"]["user_inbox_counters"] = inbox_drift

    if "chat_conversation_members" in tables and "chat_messages" in tables:
        mismatch = _count(connection, """
            SELECT COUNT(*) FROM chat_conversation_members cm
            WHERE cm.unread_count <> (
                SELECT COUNT(*) FROM chat_messages m
                WHERE m.conversation_id = cm.conversation_id AND m.message_seq > cm.last_read_message_seq
                  AND m.sender_user_id IS NOT NULL AND m.sender_user_id <> cm.user_id
                  AND m.status = 'sent' AND m.deleted_at IS NULL
            )
        """)
        if mismatch:
            details["cache_drift"]["conversation_unread_count"] = mismatch

    if "social_post_stats" in tables and "post_shares" in tables:
        mismatch = _count(connection, """
            SELECT COUNT(*) FROM social_post_stats s
            WHERE s.share_count <> (SELECT COUNT(*) FROM post_shares p WHERE p.social_post_id = s.social_post_id)
        """)
        if mismatch:
            details["cache_drift"]["post_share_count"] = mismatch

    return {
        "source_metadata": {
            "path": str(Path(connection.execute("PRAGMA database_list").fetchone()[2]).resolve()),
        },
        "source_counts": counts,
        "source_table_count": len(tables),
        "source_issues": issues,
        "source_details": details,
    }


def existing_row(pg: Any, table: str, columns: list[str], pk: list[str], values: tuple[Any, ...]) -> tuple[Any, ...] | None:
    where = " AND ".join(f'"{column}" = %s' for column in pk)
    params = tuple(values[columns.index(column)] for column in pk)
    row = pg.execute(f'SELECT {", ".join(f"\"{c}\"" for c in columns)} FROM "{table}" WHERE {where}', params).fetchone()
    return tuple(row) if row is not None else None


def insert_row(pg: Any, table: str, columns: list[str], pk: list[str], values: tuple[Any, ...]) -> bool:
    quoted_columns = ", ".join(f'"{column}"' for column in columns)
    placeholders = ", ".join(["%s"] * len(columns))
    pk_columns = ", ".join(f'"{column}"' for column in pk)
    row = pg.execute(
        f'INSERT INTO "{table}" ({quoted_columns}) VALUES ({placeholders}) ON CONFLICT DO NOTHING RETURNING {pk_columns}',
        values,
    ).fetchone()
    return row is not None


def migrate(args: argparse.Namespace) -> dict[str, Any]:
    if not args.sqlite.is_file():
        raise FileNotFoundError(args.sqlite)
    if args.batch_size < 1:
        raise ValueError("--batch-size must be positive")
    source = sqlite3.connect(f"file:{args.sqlite.resolve()}?mode=ro", uri=True)
    source.row_factory = sqlite3.Row
    try:
        all_tables = source_tables(source)
        unknown_tables = [table for table in (args.tables or []) if table not in all_tables]
        if unknown_tables:
            raise ValueError(f"Unknown source table(s): {', '.join(unknown_tables)}")
        tables = [table for table in all_tables if not args.tables or table in args.tables]
        source_stat = args.sqlite.stat()
        source_hash = hashlib.sha256(args.sqlite.read_bytes()).hexdigest()
        report: dict[str, Any] = {
            "command": "migrate_sqlite_to_postgres.py",
            "run_at_utc": datetime.now(timezone.utc).isoformat(),
            "sqlite": str(args.sqlite.resolve()),
            "sqlite_size_bytes": source_stat.st_size,
            "sqlite_mtime": source_stat.st_mtime,
            "dry_run": args.dry_run,
            "tables": tables,
            "media_files_migrated": False,
            "retryable": True,
            "source_sha256": source_hash,
            "source_files": {
                "main": file_fingerprint(args.sqlite),
                "wal": file_fingerprint(Path(str(args.sqlite) + "-wal")),
                "shm": file_fingerprint(Path(str(args.sqlite) + "-shm")),
            },
            "target_schema": validate_schema_name(args.schema),
        }
        report.update(validate_source(source, tables))
        if report["source_issues"]:
            raise RuntimeError(f"Source validation failed; no rows were migrated: {json.dumps(report['source_issues'], ensure_ascii=False)}")
        if args.dry_run:
            report["status"] = "dry_run_ok"
            return report

        dsn = args.dsn or os.getenv("TENNIS_DATABASE_URL") or os.getenv("TENNIS_POSTGRES_DSN")
        if not dsn:
            raise ValueError("--dsn or TENNIS_DATABASE_URL is required unless --dry-run is used")
        import psycopg
        from backend.app.core.postgres_schema import render_postgres_schema

        result: dict[str, Any] = {"status": "running", "tables": {}}
        with psycopg.connect(dsn) as pg:
            pg.execute(render_postgres_schema(schema=args.schema))
            pg.commit()
            pg.execute(f'SET search_path TO "{validate_schema_name(args.schema)}", pg_catalog')
            for table in tables:
                columns = table_columns(source, table)
                pk = primary_key(source, table)
                inserted = skipped = conflicts = unique_conflicts = 0
                conflict_keys: list[list[Any]] = []
                quoted_columns = ", ".join(f'"{column}"' for column in columns)
                rows = source.execute(f'SELECT {quoted_columns} FROM "{table}"')
                batch = []
                for row in rows:
                    batch.append(tuple(normalize(row[column]) for column in columns))
                    if len(batch) >= args.batch_size:
                        for values in batch:
                            before = existing_row(pg, table, columns, pk, values)
                            if before is not None:
                                if before != values:
                                    conflicts += 1
                                    conflict_keys.append([values[columns.index(column)] for column in pk])
                                else:
                                    skipped += 1
                                continue
                            if insert_row(pg, table, columns, pk, values):
                                inserted += 1
                            else:
                                unique_conflicts += 1
                        pg.commit()
                        batch.clear()
                for values in batch:
                    before = existing_row(pg, table, columns, pk, values)
                    if before is not None:
                        if before != values:
                            conflicts += 1
                            conflict_keys.append([values[columns.index(column)] for column in pk])
                        else:
                            skipped += 1
                        continue
                    if insert_row(pg, table, columns, pk, values):
                        inserted += 1
                    else:
                        unique_conflicts += 1
                pg.commit()
                result["tables"][table] = {"source": report["source_counts"][table], "inserted": inserted, "skipped_identical": skipped, "conflicts": conflicts, "unique_conflicts": unique_conflicts, "conflict_keys": conflict_keys[:20]}
                if conflicts or unique_conflicts:
                    raise RuntimeError(f"Destination conflicts found in {table}; rows were not overwritten")
            result["status"] = "ok"
        report.update(result)
        return report
    finally:
        source.close()


def main() -> None:
    args = parse_args()
    report = migrate(args)
    encoded = json.dumps(report, ensure_ascii=False, indent=2, default=str)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(encoded + "\n", encoding="utf-8")
    print(encoded)


if __name__ == "__main__":
    main()
