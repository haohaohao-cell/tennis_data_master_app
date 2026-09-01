"""Recipient-scoped public message replay and device lifecycle services."""

from __future__ import annotations

import base64
import binascii
from datetime import timedelta
import hashlib
import hmac
import json
import re
import sqlite3
import uuid

from fastapi import HTTPException, status

from backend.app.auth.service import raise_api_error
from backend.app.core.config import settings
from backend.app.core.database import get_connection, transaction
from backend.app.core.time import to_iso, utc_now, utc_now_iso
from backend.app.messages.schemas import (
    MessageDevicePatchRequest,
    MessageDeviceRecord,
    MessageDeviceRegisterRequest,
    MessageDeviceResponse,
    MessageSyncCheckpointRequest,
    MessageSyncCheckpointResponse,
    MessageSyncEventRecord,
    MessageSyncResponse,
)


DEVICE_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{7,119}$")
SYNC_RETENTION_EPOCH = 1


def _raise_device_error(code: str, message: str, error_status: int = status.HTTP_404_NOT_FOUND) -> None:
    raise_api_error(error_status, code, message)


def _validate_device_id(device_id: str) -> str:
    normalized = device_id.strip()
    if not DEVICE_ID_PATTERN.fullmatch(normalized):
        _raise_device_error(
            "MESSAGING_DEVICE_ID_INVALID",
            "The messaging device id is invalid.",
            status.HTTP_422_UNPROCESSABLE_ENTITY,
        )
    return normalized


def _device_record(row: sqlite3.Row) -> MessageDeviceRecord:
    return MessageDeviceRecord(
        device_id=row["device_id"],
        user_id=row["user_id"],
        platform=row["platform"],
        app_version=row["app_version"],
        created_at=row["created_at"],
        last_seen_at=row["last_seen_at"],
        revoked_at=row["revoked_at"],
        updated_at=row["updated_at"],
    )


def _select_device(
    connection: sqlite3.Connection,
    user_id: str,
    device_id: str,
    *,
    active_only: bool = True,
) -> sqlite3.Row:
    query = "SELECT * FROM messaging_devices WHERE device_id = ? AND user_id = ?"
    if active_only:
        query += " AND revoked_at IS NULL"
    query += " LIMIT 1;"
    row = connection.execute(query, (device_id, user_id)).fetchone()
    if row is not None:
        return row
    revoked = connection.execute(
        "SELECT revoked_at FROM messaging_devices WHERE device_id = ? AND user_id = ? LIMIT 1;",
        (device_id, user_id),
    ).fetchone()
    if active_only and revoked is not None and revoked["revoked_at"] is not None:
        _raise_device_error(
            "MESSAGING_DEVICE_REVOKED",
            "This messaging device has been revoked.",
            status.HTTP_403_FORBIDDEN,
        )
    _raise_device_error("MESSAGING_DEVICE_NOT_FOUND", "The messaging device was not found.")
    raise AssertionError("unreachable")


def register_device(user_id: str, payload: MessageDeviceRegisterRequest) -> MessageDeviceResponse:
    device_id = _validate_device_id(payload.device_id)
    now = utc_now_iso()
    with transaction(immediate=True, lock_key=f"messaging-device:{device_id}") as connection:
        existing = connection.execute(
            "SELECT * FROM messaging_devices WHERE device_id = ? LIMIT 1;",
            (device_id,),
        ).fetchone()
        if existing is not None:
            if existing["user_id"] != user_id:
                _raise_device_error(
                    "MESSAGING_DEVICE_OWNERSHIP_CONFLICT",
                    "The messaging device belongs to another user.",
                    status.HTTP_409_CONFLICT,
                )
            if existing["revoked_at"] is not None:
                _raise_device_error(
                    "MESSAGING_DEVICE_REVOKED",
                    "This messaging device has been revoked.",
                    status.HTTP_403_FORBIDDEN,
                )
            connection.execute(
                """
                UPDATE messaging_devices
                SET platform = ?, app_version = ?, last_seen_at = ?, updated_at = ?
                WHERE device_id = ? AND user_id = ? AND revoked_at IS NULL;
                """,
                (payload.platform, payload.app_version, now, now, device_id, user_id),
            )
        else:
            connection.execute(
                """
                INSERT INTO messaging_devices (
                    device_id, user_id, platform, app_version,
                    created_at, last_seen_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (device_id) DO NOTHING;
                """,
                (device_id, user_id, payload.platform, payload.app_version, now, now, now),
            )
            existing = connection.execute(
                "SELECT * FROM messaging_devices WHERE device_id = ? LIMIT 1;",
                (device_id,),
            ).fetchone()
            if existing is None:
                _raise_device_error("MESSAGING_DEVICE_NOT_FOUND", "The messaging device was not found.")
            if existing["user_id"] != user_id:
                _raise_device_error(
                    "MESSAGING_DEVICE_OWNERSHIP_CONFLICT",
                    "The messaging device belongs to another user.",
                    status.HTTP_409_CONFLICT,
                )
        row = connection.execute(
            "SELECT * FROM messaging_devices WHERE device_id = ? AND user_id = ? LIMIT 1;",
            (device_id, user_id),
        ).fetchone()
    if row is None:
        _raise_device_error("MESSAGING_DEVICE_NOT_FOUND", "The messaging device was not found.")
    return MessageDeviceResponse(device=_device_record(row))


def update_device(user_id: str, device_id: str, payload: MessageDevicePatchRequest) -> MessageDeviceResponse:
    requested_id = _validate_device_id(device_id)
    now = utc_now_iso()
    with transaction(immediate=True, lock_key=f"messaging-device:{requested_id}") as connection:
        _select_device(connection, user_id, requested_id)
        connection.execute(
            """
            UPDATE messaging_devices
            SET platform = ?, app_version = ?, last_seen_at = ?, updated_at = ?
            WHERE device_id = ? AND user_id = ? AND revoked_at IS NULL;
            """,
            (payload.platform, payload.app_version, now, now, requested_id, user_id),
        )
        row = _select_device(connection, user_id, requested_id)
    return MessageDeviceResponse(device=_device_record(row))


def revoke_device(user_id: str, device_id: str) -> MessageDeviceResponse:
    requested_id = _validate_device_id(device_id)
    now = utc_now_iso()
    with transaction(immediate=True, lock_key=f"messaging-device:{requested_id}") as connection:
        row = _select_device(connection, user_id, requested_id, active_only=False)
        if row["revoked_at"] is None:
            connection.execute(
                """
                UPDATE messaging_devices
                SET revoked_at = ?, last_seen_at = ?, updated_at = ?
                WHERE device_id = ? AND user_id = ? AND revoked_at IS NULL;
                """,
                (now, now, now, requested_id, user_id),
            )
        row = connection.execute(
            "SELECT * FROM messaging_devices WHERE device_id = ? AND user_id = ? LIMIT 1;",
            (requested_id, user_id),
        ).fetchone()
    if row is None:
        _raise_device_error("MESSAGING_DEVICE_NOT_FOUND", "The messaging device was not found.")
    from backend.app.messages import push

    push.revoke_device_tokens(user_id, requested_id)
    return MessageDeviceResponse(device=_device_record(row))


def _cursor_signature(encoded_body: str) -> str:
    return hmac.new(
        settings.resolved_message_sync_cursor_secret().encode("utf-8"),
        encoded_body.encode("ascii"),
        hashlib.sha256,
    ).hexdigest()


def _encode_cursor(user_id: str, device_id: str, persisted_at: str, event_id: str) -> str:
    body = json.dumps(
        {"v": 1, "u": user_id, "d": device_id, "e": SYNC_RETENTION_EPOCH, "p": persisted_at, "i": event_id},
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    encoded_body = base64.urlsafe_b64encode(body).decode("ascii").rstrip("=")
    return f"{encoded_body}.{_cursor_signature(encoded_body)}"


def _decode_cursor(cursor: str, user_id: str, device_id: str) -> tuple[str, str]:
    try:
        encoded_body, signature = cursor.split(".", 1)
        if not hmac.compare_digest(signature, _cursor_signature(encoded_body)):
            raise ValueError("signature")
        padded = encoded_body + "=" * (-len(encoded_body) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded).decode("utf-8"))
        if (
            not isinstance(payload, dict)
            or payload.get("v") != 1
            or payload.get("u") != user_id
            or payload.get("d") != device_id
            or payload.get("e") != SYNC_RETENTION_EPOCH
            or not isinstance(payload.get("p"), str)
            or not isinstance(payload.get("i"), str)
        ):
            raise ValueError("claims")
        return payload["p"], payload["i"]
    except (AttributeError, KeyError, TypeError, ValueError, UnicodeDecodeError, json.JSONDecodeError, binascii.Error):
        _raise_device_error("SYNC_CURSOR_INVALID", "The sync cursor is invalid.", status.HTTP_400_BAD_REQUEST)
        raise AssertionError("unreachable")


def _raise_cursor_expired() -> None:
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={
            "code": "SYNC_CURSOR_EXPIRED",
            "message": "The sync cursor has expired; full reconciliation is required.",
            "requires_full_reconciliation": True,
            "reconciliation": [
                "GET /api/v1/messages/conversations",
                "GET /api/v1/messages/unread-counts",
                "GET /api/v1/notifications",
                "GET /api/v1/messages/conversations/{conversation_id}/messages",
                "POST /api/v1/messages/conversations/{conversation_id}/messages/reconcile",
                "POST /api/v1/messages/conversations/{conversation_id}/messages/by-client-id/{client_message_id}",
            ],
        },
    )


def _event_record(row: sqlite3.Row) -> MessageSyncEventRecord:
    try:
        payload = json.loads(row["payload_json"])
    except (TypeError, json.JSONDecodeError):
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    return MessageSyncEventRecord(
        user_sync_event_id=row["user_sync_event_id"],
        event_id=row["event_id"],
        event_type=row["event_type"],
        event_version=row["event_version"],
        aggregate_type=row["aggregate_type"],
        aggregate_id=row["aggregate_id"],
        actor_user_id=row["actor_user_id"],
        recipient_user_id=row["recipient_user_id"],
        conversation_id=row["conversation_id"],
        message_id=row["message_id"],
        message_seq=row["message_seq"],
        occurred_at=row["occurred_at"],
        persisted_at=row["persisted_at"],
        privacy_classification=row["privacy_classification"],
        payload=payload,
    )


def append_conversation_event(
    connection: sqlite3.Connection,
    *,
    event_id: str,
    event_type: str,
    conversation_id: str,
    actor_user_id: str | None,
    aggregate_type: str,
    message_id: str | None,
    message_seq: int | None,
    occurred_at: str,
    changed_fields: list[str],
) -> None:
    persisted_at = utc_now_iso()
    payload_json = json.dumps({"changed_fields": changed_fields}, separators=(",", ":"))
    recipients = connection.execute(
        """
        SELECT user_id
        FROM chat_conversation_members
        WHERE conversation_id = ? AND status = 'active' AND deleted_at IS NULL;
        """,
        (conversation_id,),
    ).fetchall()
    for recipient in recipients:
        connection.execute(
            """
            INSERT INTO user_sync_events (
                user_sync_event_id, event_id, event_type, event_version,
                aggregate_type, aggregate_id, actor_user_id, recipient_user_id,
                conversation_id, message_id, message_seq, occurred_at,
                persisted_at, retention_epoch, privacy_classification, payload_json
            ) VALUES (?, ?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'private_metadata', ?)
            ON CONFLICT (recipient_user_id, event_id) DO NOTHING;
            """,
            (
                str(uuid.uuid4()), event_id, event_type, aggregate_type, conversation_id,
                actor_user_id, recipient["user_id"], conversation_id,
                message_id, message_seq, occurred_at, persisted_at,
                SYNC_RETENTION_EPOCH, payload_json,
            ),
        )


def _ensure_sync_user(connection: sqlite3.Connection, user_id: str) -> None:
    row = connection.execute(
        "SELECT 1 FROM users WHERE user_id = ? AND status = 'active' AND deleted_at IS NULL LIMIT 1;",
        (user_id,),
    ).fetchone()
    if row is None:
        _raise_device_error("USER_NOT_FOUND", "User was not found.")


def _server_watermark(connection: sqlite3.Connection, user_id: str) -> str | None:
    row = connection.execute(
        """
        SELECT persisted_at FROM user_sync_events
        WHERE recipient_user_id = ? AND retention_epoch = ?
        ORDER BY persisted_at DESC, event_id DESC LIMIT 1;
        """,
        (user_id, SYNC_RETENTION_EPOCH),
    ).fetchone()
    return row["persisted_at"] if row is not None else None


def sync_events(user_id: str, device_id: str, cursor: str | None, limit: int) -> MessageSyncResponse:
    requested_device_id = _validate_device_id(device_id)
    with get_connection() as connection:
        _ensure_sync_user(connection, user_id)
        _select_device(connection, user_id, requested_device_id)
        cursor_position: tuple[str, str] | None = None
        if cursor:
            cursor_position = _decode_cursor(cursor, user_id, requested_device_id)
            if cursor_position[0] < to_iso(utc_now() - timedelta(days=settings.message_sync_retention_days)):
                _raise_cursor_expired()
            known_cursor = connection.execute(
                """
                SELECT 1 FROM user_sync_events
                WHERE recipient_user_id = ? AND event_id = ? AND persisted_at = ?
                  AND retention_epoch = ? LIMIT 1;
                """,
                (user_id, cursor_position[1], cursor_position[0], SYNC_RETENTION_EPOCH),
            ).fetchone()
            if known_cursor is None:
                _raise_cursor_expired()

        query = """
            SELECT * FROM user_sync_events
            WHERE recipient_user_id = ? AND retention_epoch = ?
              AND (
                conversation_id IS NULL
                OR (
                    EXISTS (
                        SELECT 1 FROM chat_conversation_members AS member
                        JOIN chat_conversations AS conversation
                          ON conversation.conversation_id = member.conversation_id
                        WHERE member.conversation_id = user_sync_events.conversation_id
                          AND member.user_id = user_sync_events.recipient_user_id
                          AND member.status = 'active' AND member.deleted_at IS NULL
                          AND conversation.status = 'active' AND conversation.deleted_at IS NULL
                    )
                    AND NOT EXISTS (
                        SELECT 1
                        FROM chat_conversations AS direct_conversation
                        JOIN chat_conversation_members AS other_member
                          ON other_member.conversation_id = direct_conversation.conversation_id
                         AND other_member.user_id <> user_sync_events.recipient_user_id
                         AND other_member.status = 'active' AND other_member.deleted_at IS NULL
                        JOIN user_blocks AS block
                          ON block.deleted_at IS NULL
                         AND ((block.blocker_user_id = user_sync_events.recipient_user_id
                               AND block.blocked_user_id = other_member.user_id)
                           OR (block.blocker_user_id = other_member.user_id
                               AND block.blocked_user_id = user_sync_events.recipient_user_id))
                        WHERE direct_conversation.conversation_id = user_sync_events.conversation_id
                          AND direct_conversation.conversation_type = 'direct'
                    )
                )
              )
        """
        params: list[object] = [user_id, SYNC_RETENTION_EPOCH]
        if cursor_position:
            query += " AND (persisted_at > ? OR (persisted_at = ? AND event_id > ?))"
            params.extend([cursor_position[0], cursor_position[0], cursor_position[1]])
        query += " ORDER BY persisted_at ASC, event_id ASC LIMIT ?;"
        params.append(limit + 1)
        rows = connection.execute(query, tuple(params)).fetchall()
        has_more = len(rows) > limit
        items = rows[:limit]
        watermark = _server_watermark(connection, user_id)

    next_cursor = None
    if items:
        last = items[-1]
        next_cursor = _encode_cursor(user_id, requested_device_id, last["persisted_at"], last["event_id"])
    return MessageSyncResponse(
        items=[_event_record(row) for row in items],
        next_cursor=next_cursor,
        has_more=has_more,
        server_watermark=watermark,
        cursor_status="valid" if cursor else "initial",
    )


def save_checkpoint(user_id: str, payload: MessageSyncCheckpointRequest) -> MessageSyncCheckpointResponse:
    device_id = _validate_device_id(payload.device_id)
    with transaction(immediate=True, lock_key=f"message-sync-checkpoint:{device_id}") as connection:
        _select_device(connection, user_id, device_id)
        persisted_at, event_id = _decode_cursor(payload.cursor, user_id, device_id)
        event = connection.execute(
            """
            SELECT 1 FROM user_sync_events
            WHERE recipient_user_id = ? AND event_id = ? AND persisted_at = ? AND retention_epoch = ?
            LIMIT 1;
            """,
            (user_id, event_id, persisted_at, SYNC_RETENTION_EPOCH),
        ).fetchone()
        if event is None:
            _raise_cursor_expired()
        now = utc_now_iso()
        current = connection.execute(
            "SELECT cursor, cursor_persisted_at, last_event_id, updated_at "
            "FROM device_sync_checkpoints WHERE device_id = ? LIMIT 1;",
            (device_id,),
        ).fetchone()
        if current is None or (
            persisted_at > current["cursor_persisted_at"]
            or (persisted_at == current["cursor_persisted_at"] and event_id > current["last_event_id"])
        ):
            connection.execute(
                """
                INSERT INTO device_sync_checkpoints (
                    device_id, user_id, cursor, cursor_persisted_at, last_event_id, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT (device_id) DO UPDATE SET
                    cursor = excluded.cursor,
                    cursor_persisted_at = excluded.cursor_persisted_at,
                    last_event_id = excluded.last_event_id,
                    updated_at = excluded.updated_at;
                """,
                (device_id, user_id, payload.cursor, persisted_at, event_id, now),
            )
            stored_cursor = payload.cursor
            updated_at = now
        else:
            stored_cursor = current["cursor"]
            updated_at = current["updated_at"]
    return MessageSyncCheckpointResponse(
        success=True,
        device_id=device_id,
        cursor=stored_cursor,
        updated_at=updated_at,
    )
