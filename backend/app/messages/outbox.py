"""Durable message event replay and lease primitives.

The table is written by the message transaction and is intentionally not
connected to a delivery provider. Reads are authorization-scoped; claiming is
an internal primitive that only changes lease metadata and never performs a
business side effect.
"""

from __future__ import annotations

import base64
import binascii
from datetime import timedelta
import json
import uuid
from typing import Any

from backend.app.auth.service import raise_api_error
from backend.app.core.config import settings
from backend.app.core.database import get_connection, transaction
from backend.app.core.time import to_iso, utc_now, utc_now_iso
from backend.app.messages.schemas import MessageEventListResponse, OutboxEventRecord


def _encode_cursor(created_at: str, event_id: str) -> str:
    value = f"{created_at}\n{event_id}".encode("utf-8")
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _decode_cursor(value: str) -> tuple[str, str]:
    try:
        padded = value + "=" * (-len(value) % 4)
        created_at, event_id = base64.urlsafe_b64decode(padded).decode("utf-8").split("\n", 1)
    except (ValueError, UnicodeDecodeError, binascii.Error) as error:
        raise_api_error(400, "EVENT_CURSOR_INVALID", "The event cursor is invalid.")
        raise AssertionError from error
    if not created_at or not event_id:
        raise_api_error(400, "EVENT_CURSOR_INVALID", "The event cursor is invalid.")
    return created_at, event_id


def _record(row: Any) -> OutboxEventRecord:
    return OutboxEventRecord(**{key: row[key] for key in row.keys()})


def event_for_message(connection: Any, message_id: str) -> Any | None:
    return connection.execute(
        "SELECT * FROM outbox_events WHERE message_id = ? ORDER BY event_version DESC LIMIT 1;",
        (message_id,),
    ).fetchone()


def create_message_event(connection: Any, message: Any, actor_user_id: str) -> str:
    """Insert the one immutable event for a message, returning its stable ID."""
    existing = event_for_message(connection, message["message_id"])
    if existing is not None:
        return existing["event_id"]
    event_id = str(uuid.uuid4())
    payload = json.dumps(
        {
            "message_id": message["message_id"],
            "conversation_id": message["conversation_id"],
            "message_seq": message["message_seq"],
            "message_type": message["message_type"],
            "client_message_id": message["client_message_id"],
            "actor_user_id": actor_user_id,
            "created_at": message["created_at"],
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )
    connection.execute(
        """
        INSERT INTO outbox_events (
            event_id, aggregate_type, aggregate_id, event_type, event_version,
            actor_user_id, conversation_id, message_id, message_seq, payload_json
        ) VALUES (?, 'chat_message', ?, 'message.created', 1, ?, ?, ?, ?, ?);
        """,
        (
            event_id,
            message["message_id"],
            actor_user_id,
            message["conversation_id"],
            message["message_id"],
            message["message_seq"],
            payload,
        ),
    )
    return event_id


def list_events(
    user_id: str,
    conversation_id: str,
    cursor: str | None,
    limit: int,
) -> MessageEventListResponse:
    from backend.app.messages import service

    with get_connection() as connection:
        service._ensure_active_user(connection, user_id)
        service._select_conversation(connection, conversation_id)
        service._select_member(connection, conversation_id, user_id)
        query = """
            SELECT * FROM outbox_events
            WHERE conversation_id = ?
        """
        params: list[Any] = [conversation_id]
        if cursor:
            created_at, event_id = _decode_cursor(cursor)
            query += " AND (created_at > ? OR (created_at = ? AND event_id > ?))"
            params.extend([created_at, created_at, event_id])
        query += " ORDER BY created_at ASC, event_id ASC LIMIT ?;"
        params.append(limit)
        rows = connection.execute(query, tuple(params)).fetchall()
    items = [_record(row) for row in rows]
    next_cursor = _encode_cursor(items[-1].created_at, items[-1].event_id) if len(items) == limit else None
    return MessageEventListResponse(items=items, next_cursor=next_cursor)


def _lease_cutoff(lease_seconds: int) -> str:
    return to_iso(utc_now() - timedelta(seconds=lease_seconds))


def lease_events(lease_owner: str, limit: int = 20, lease_seconds: int = 60) -> list[OutboxEventRecord]:
    if not lease_owner.strip():
        raise_api_error(400, "LEASE_OWNER_REQUIRED", "A lease owner is required.")
    now = utc_now_iso()
    cutoff = _lease_cutoff(lease_seconds)
    # SQLite has one writer, so the explicit transaction lock serializes the
    # claim/update pair. PostgreSQL uses row-level FOR UPDATE SKIP LOCKED
    # below, allowing independent workers to claim different events.
    with transaction(
        immediate=not settings.uses_postgres,
        lock_key="outbox-events" if not settings.uses_postgres else None,
    ) as connection:
        sql = """
            SELECT * FROM outbox_events
            WHERE (
                (status IN ('pending', 'failed') AND COALESCE(next_attempt_at, available_at) <= ?)
                OR (status = 'leased' AND leased_at IS NOT NULL AND leased_at <= ?)
            )
            ORDER BY created_at ASC, event_id ASC
            LIMIT ?
        """
        if settings.uses_postgres:
            sql += " FOR UPDATE SKIP LOCKED"
        rows = connection.execute(sql, (now, cutoff, limit)).fetchall()
        event_ids = [row["event_id"] for row in rows]
        for event_id in event_ids:
            connection.execute(
                """
                UPDATE outbox_events
                SET status = 'leased', leased_at = ?, lease_owner = ?,
                    attempt_count = attempt_count + 1, updated_at = CURRENT_TIMESTAMP
                WHERE event_id = ?
                """,
                (now, lease_owner, event_id),
            )
        if not event_ids:
            return []
        placeholders = ", ".join("?" for _ in event_ids)
        leased = connection.execute(
            f"SELECT * FROM outbox_events WHERE event_id IN ({placeholders}) ORDER BY created_at ASC, event_id ASC;",
            tuple(event_ids),
        ).fetchall()
    return [_record(row) for row in leased]


def acknowledge_event(event_id: str, lease_owner: str) -> bool:
    with transaction(immediate=True, lock_key=f"outbox-event:{event_id}") as connection:
        result = connection.execute(
            """
            UPDATE outbox_events
            SET status = 'processed', processed_at = CURRENT_TIMESTAMP,
                leased_at = NULL, lease_owner = NULL, updated_at = CURRENT_TIMESTAMP
            WHERE event_id = ? AND status = 'leased' AND lease_owner = ?;
            """,
            (event_id, lease_owner),
        )
        return result.rowcount == 1


def fail_event(
    event_id: str,
    lease_owner: str,
    error_code: str,
    error_message: str,
    retryable: bool = True,
    retry_after_seconds: int = 30,
) -> bool:
    next_attempt = to_iso(utc_now() + timedelta(seconds=max(1, retry_after_seconds)))
    with transaction(immediate=True, lock_key=f"outbox-event:{event_id}") as connection:
        result = connection.execute(
            """
            UPDATE outbox_events
            SET status = ?, next_attempt_at = ?, leased_at = NULL, lease_owner = NULL,
                last_error_code = ?, last_error_message = ?, updated_at = CURRENT_TIMESTAMP
            WHERE event_id = ? AND status = 'leased' AND lease_owner = ?;
            """,
            (
                "pending" if retryable else "failed",
                next_attempt if retryable else None,
                error_code[:80],
                error_message[:500],
                event_id,
                lease_owner,
            ),
        )
        return result.rowcount == 1
