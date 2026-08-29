"""Read-only report or explicit PostgreSQL repair for derived inbox counters."""

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


def schema_name(value: str) -> str:
    if not value or not value.replace("_", "a").isalnum() or not (value[0].isalpha() or value[0] == "_"):
        raise ValueError("schema must be a simple PostgreSQL identifier")
    return value


def sqlite_rows(path: Path) -> list[dict[str, Any]]:
    connection = sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute("""
            SELECT u.user_id,
                   COALESCE(i.unread_direct_message_count, 0) AS stored_direct,
                   COALESCE(i.unread_group_message_count, 0) AS stored_group,
                   COALESCE((SELECT SUM(cm.unread_count) FROM chat_conversation_members cm JOIN chat_conversations c ON c.conversation_id = cm.conversation_id WHERE cm.user_id = u.user_id AND cm.status = 'active' AND c.conversation_type = 'direct'), 0) AS derived_direct,
                   COALESCE((SELECT SUM(cm.unread_count) FROM chat_conversation_members cm JOIN chat_conversations c ON c.conversation_id = cm.conversation_id WHERE cm.user_id = u.user_id AND cm.status = 'active' AND c.conversation_type = 'group'), 0) AS derived_group
            FROM users u LEFT JOIN user_inbox_counters i ON i.user_id = u.user_id ORDER BY u.user_id;
        """).fetchall()
        return [dict(row) | {"direct_delta": row["derived_direct"] - row["stored_direct"], "group_delta": row["derived_group"] - row["stored_group"]} for row in rows]
    finally:
        connection.close()


def _target_counter_rows(pg: Any, user_ids: list[str]) -> list[dict[str, Any]]:
    if not user_ids:
        return []
    placeholders = ", ".join("%s" for _ in user_ids)
    rows = pg.execute(
        f"SELECT user_id, unread_direct_message_count, unread_group_message_count FROM user_inbox_counters WHERE user_id IN ({placeholders}) ORDER BY user_id",
        tuple(user_ids),
    ).fetchall()
    return [
        {"user_id": row[0], "stored_direct": int(row[1]), "stored_group": int(row[2])}
        for row in rows
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description="Reconcile derived inbox counters without touching SQLite.")
    parser.add_argument("--sqlite", type=Path, default=ROOT_DIR / "backend/db/tennis_data_master.sqlite3")
    parser.add_argument("--dsn", help="Required for --execute; defaults to TENNIS_DATABASE_URL.")
    parser.add_argument("--schema", default="public")
    parser.add_argument("--execute", action="store_true", help="Repair destination PostgreSQL counters; never modifies SQLite.")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    source = sqlite_rows(args.sqlite)
    report: dict[str, Any] = {
        "command": "reconcile_inbox_counters.py", "run_at_utc": datetime.now(timezone.utc).isoformat(),
        "sqlite": str(args.sqlite.resolve()), "source_sha256": hashlib.sha256(args.sqlite.read_bytes()).hexdigest(),
        "source_status": "source_has_derived_cache_drift" if any(r["direct_delta"] or r["group_delta"] for r in source) else "source_clean",
        "source_rows": source, "execute": args.execute, "destination_status": "not_requested",
    }
    if args.execute:
        dsn = args.dsn or os.getenv("TENNIS_DATABASE_URL") or os.getenv("TENNIS_POSTGRES_DSN")
        if not dsn:
            raise SystemExit("--execute requires --dsn or TENNIS_DATABASE_URL")
        schema = schema_name(args.schema)
        import psycopg
        with psycopg.connect(dsn) as pg:
            pg.execute(f'SET search_path TO "{schema}", pg_catalog')
            identity = pg.execute("SELECT current_database(), current_user, current_schema(), version()").fetchone()
            source_user_ids = [row["user_id"] for row in source]
            before = _target_counter_rows(pg, source_user_ids)
            extra_users = pg.execute(
                "SELECT user_id FROM users WHERE NOT (user_id = ANY(%s)) ORDER BY user_id",
                (source_user_ids,),
            ).fetchall() if source_user_ids else pg.execute("SELECT user_id FROM users ORDER BY user_id").fetchall()
            extra_counters = pg.execute(
                "SELECT i.user_id FROM user_inbox_counters i LEFT JOIN users u ON u.user_id = i.user_id WHERE u.user_id IS NULL ORDER BY i.user_id"
            ).fetchall()
            pg.execute("""
                UPDATE user_inbox_counters i SET
                    unread_direct_message_count = COALESCE((SELECT SUM(cm.unread_count) FROM chat_conversation_members cm JOIN chat_conversations c ON c.conversation_id = cm.conversation_id WHERE cm.user_id = i.user_id AND cm.status = 'active' AND c.conversation_type = 'direct'), 0),
                    unread_group_message_count = COALESCE((SELECT SUM(cm.unread_count) FROM chat_conversation_members cm JOIN chat_conversations c ON c.conversation_id = cm.conversation_id WHERE cm.user_id = i.user_id AND cm.status = 'active' AND c.conversation_type = 'group'), 0),
                    updated_at = (CURRENT_TIMESTAMP AT TIME ZONE 'UTC')::text
                WHERE i.user_id = ANY(%s)
            """, (source_user_ids,))
            pg.commit()
            after = _target_counter_rows(pg, source_user_ids)
        report["destination"] = {"database": identity[0], "user": identity[1], "schema": schema, "server_version": identity[3]}
        report["before"] = before; report["after"] = after
        report["target_extra_users"] = [row[0] for row in extra_users]
        report["target_orphan_counter_users"] = [row[0] for row in extra_counters]
        report["destination_status"] = "destination_reconciled"
    if report["source_status"] == "source_has_derived_cache_drift":
        report["status"] = "source_has_derived_cache_drift"
    elif args.execute:
        report["status"] = "destination_reconciled"
    else:
        report["status"] = "source_clean"
    encoded = json.dumps(report, ensure_ascii=False, indent=2, default=str)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True); args.report.write_text(encoded + "\n", encoding="utf-8")
    print(encoded)


if __name__ == "__main__":
    main()
