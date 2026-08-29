"""Collect read-only PostgreSQL plans for the Stage 8 message queries."""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import psycopg


def schema_name(value: str) -> str:
    if not value or not value.replace("_", "a").isalnum() or not (value[0].isalpha() or value[0] == "_"):
        raise ValueError("schema must be a simple PostgreSQL identifier")
    return value


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dsn", default=os.getenv("TENNIS_DATABASE_URL"))
    parser.add_argument("--schema", required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    if not args.dsn:
        raise SystemExit("--dsn or TENNIS_DATABASE_URL is required")
    schema = schema_name(args.schema)
    quoted = '"' + schema + '"'
    queries = {
        "conversation_list": f"""
            SELECT conversations.* FROM {quoted}.chat_conversations AS conversations
            JOIN {quoted}.chat_conversation_members AS members
              ON members.conversation_id = conversations.conversation_id
            WHERE members.user_id = 'benchmark-user' AND members.status = 'active'
              AND members.deleted_at IS NULL AND conversations.deleted_at IS NULL
            ORDER BY conversations.last_message_at DESC NULLS LAST
            LIMIT 50
        """,
        "message_history": f"""
            SELECT * FROM {quoted}.chat_messages
            WHERE conversation_id = 'benchmark-large-000' AND deleted_at IS NULL
            ORDER BY message_seq DESC LIMIT 100
        """,
        "message_history_search": f"""
            SELECT * FROM {quoted}.chat_messages
            WHERE conversation_id = 'benchmark-large-000' AND message_type IN ('text', 'post_share')
              AND status = 'sent' AND text_content LIKE '%baseline-search-token%'
              AND deleted_at IS NULL
            ORDER BY message_seq DESC LIMIT 30
        """,
    }
    report = {
        "stage": "stage8-postgresql-explain",
        "run_at_utc": datetime.now(timezone.utc).isoformat(),
        "database": "local_test_only",
        "schema": schema,
        "plans": {},
        "errors": [],
    }
    with psycopg.connect(args.dsn, connect_timeout=5) as connection:
        identity = connection.execute("SELECT current_database(), current_user, version()").fetchone()
        report["identity"] = {"database": identity[0], "user": identity[1], "server_version": identity[2]}
        for name, query in queries.items():
            try:
                plan = connection.execute("EXPLAIN (FORMAT JSON) " + query).fetchone()[0]
                analyzed = connection.execute("EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + query).fetchone()[0]
                report["plans"][name] = {"explain": plan, "explain_analyze": analyzed}
            except Exception as error:
                report["errors"].append({"query": name, "type": type(error).__name__, "message": str(error)})
    report["status"] = "ok" if not report["errors"] else "differences_found"
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps({"stage": report["stage"], "schema": schema, "queries": len(report["plans"]), "errors": len(report["errors"]), "status": report["status"]}, ensure_ascii=False))
    if report["errors"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
