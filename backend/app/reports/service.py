from __future__ import annotations

import sqlite3
import uuid
from typing import Any

from fastapi import status

from backend.app.auth.service import raise_api_error
from backend.app.core.database import get_connection, transaction
from backend.app.core.time import utc_now_iso
from backend.app.messages.business_object_access import resolve_business_object_access
from backend.app.posts import interaction_service as post_interactions
from backend.app.reports.schemas import ContentReportCreate, ContentReportCreateResponse, ContentReportRecord
from backend.app.reports.schemas import MessageReportCreate, MessageReportListResponse, MessageReportRecord, MessageReportResponse, MessageReportUpdate


def _row_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {key: row[key] for key in row.keys()}


def _ensure_active_user(connection: sqlite3.Connection, user_id: str) -> None:
    row = connection.execute(
        """
        SELECT 1
        FROM users
        WHERE user_id = ?
          AND status = 'active'
          AND deleted_at IS NULL
        LIMIT 1;
        """,
        (user_id,),
    ).fetchone()
    if row is None:
        raise_api_error(status.HTTP_404_NOT_FOUND, "USER_NOT_FOUND", "User was not found.")


def _report_record(row: sqlite3.Row) -> ContentReportRecord:
    return ContentReportRecord(**_row_dict(row))


def _validate_report_target(connection: sqlite3.Connection, reporter_user_id: str, payload: ContentReportCreate) -> None:
    if payload.target_type == "user":
        if reporter_user_id == payload.target_id:
            raise_api_error(status.HTTP_400_BAD_REQUEST, "CANNOT_REPORT_SELF", "You cannot report yourself.")
        row = connection.execute(
            """
            SELECT 1
            FROM users
            WHERE user_id = ?
              AND deleted_at IS NULL
            LIMIT 1;
            """,
            (payload.target_id,),
        ).fetchone()
    elif payload.target_type == "social_post":
        post_interactions._select_accessible_post(connection, payload.target_id, reporter_user_id)
        row = (1,)
    elif payload.target_type == "post_comment":
        row = connection.execute(
            """
            SELECT social_post_id
            FROM post_comments
            WHERE comment_id = ?
              AND status = 'active'
              AND deleted_at IS NULL
            LIMIT 1;
            """,
            (payload.target_id,),
        ).fetchone()
        if row is not None:
            post_interactions._select_accessible_post(connection, row["social_post_id"], reporter_user_id)
    elif payload.target_type == "chat_conversation":
        row = connection.execute(
            """
            SELECT 1
            FROM chat_conversation_members AS members
            JOIN chat_conversations AS conversations
              ON conversations.conversation_id = members.conversation_id
            WHERE members.user_id = ?
              AND members.conversation_id = ?
              AND members.status = 'active'
              AND members.deleted_at IS NULL
              AND conversations.status = 'active'
              AND conversations.deleted_at IS NULL
            LIMIT 1;
            """,
            (reporter_user_id, payload.target_id),
        ).fetchone()
    elif payload.target_type == "chat_message":
        row = connection.execute(
            """
            SELECT 1
            FROM chat_messages
            JOIN chat_conversation_members AS members
              ON members.conversation_id = chat_messages.conversation_id
            WHERE chat_messages.message_id = ?
              AND chat_messages.deleted_at IS NULL
              AND members.user_id = ?
              AND members.status = 'active'
              AND members.deleted_at IS NULL
            LIMIT 1;
            """,
            (payload.target_id, reporter_user_id),
        ).fetchone()
    else:
        row = connection.execute(
            """
            SELECT 1
            FROM videos
            WHERE video_id = ?
              AND deleted_at IS NULL
            LIMIT 1;
            """,
            (payload.target_id,),
        ).fetchone()

    if row is None:
        raise_api_error(
            status.HTTP_404_NOT_FOUND,
            "REPORT_TARGET_NOT_FOUND",
            "The reported target was not found.",
        )


def create_report(user_id: str, payload: ContentReportCreate) -> ContentReportCreateResponse:
    if not payload.target_id:
        raise_api_error(status.HTTP_400_BAD_REQUEST, "REPORT_TARGET_REQUIRED", "Report target is required.")

    with transaction() as connection:
        _ensure_active_user(connection, user_id)
        _validate_report_target(connection, user_id, payload)
        existing = connection.execute(
            """
            SELECT *
            FROM content_reports
            WHERE reporter_user_id = ?
              AND target_type = ?
              AND target_id = ?
              AND status IN ('pending', 'reviewing')
            LIMIT 1;
            """,
            (user_id, payload.target_type, payload.target_id),
        ).fetchone()
        if existing is not None:
            return ContentReportCreateResponse(success=True, report=_report_record(existing))

        report_id = str(uuid.uuid4())
        try:
            connection.execute(
                """
                INSERT INTO content_reports (
                    content_report_id,
                    reporter_user_id,
                    target_type,
                    target_id,
                    reason_type,
                    reason_text,
                    source
                )
                VALUES (?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    report_id,
                    user_id,
                    payload.target_type,
                    payload.target_id,
                    payload.reason_type,
                    payload.reason_text,
                    payload.source,
                ),
            )
        except sqlite3.IntegrityError:
            existing = connection.execute(
                """
                SELECT *
                FROM content_reports
                WHERE reporter_user_id = ?
                  AND target_type = ?
                  AND target_id = ?
                  AND status IN ('pending', 'reviewing')
                LIMIT 1;
                """,
                (user_id, payload.target_type, payload.target_id),
            ).fetchone()
            if existing is None:
                raise
            return ContentReportCreateResponse(success=True, report=_report_record(existing))
        row = connection.execute(
            """
            SELECT *
            FROM content_reports
            WHERE content_report_id = ?
            LIMIT 1;
            """,
            (report_id,),
        ).fetchone()
    return ContentReportCreateResponse(success=True, report=_report_record(row))


def _message_report_record(row: Any) -> MessageReportRecord:
    return MessageReportRecord(**_row_dict(row))


def _validate_message_report_target(connection: Any, user_id: str, payload: MessageReportCreate) -> Any:
    if payload.target_kind == "message":
        row = connection.execute("SELECT * FROM chat_messages WHERE message_id = ? AND deleted_at IS NULL AND status = 'sent' LIMIT 1;", (payload.target_id,)).fetchone()
        if row is None:
            raise_api_error(status.HTTP_404_NOT_FOUND, "REPORT_TARGET_NOT_FOUND", "The reported target was not found.")
        member = connection.execute("SELECT 1 FROM chat_conversation_members WHERE conversation_id = ? AND user_id = ? AND status = 'active' AND deleted_at IS NULL LIMIT 1;", (row["conversation_id"], user_id)).fetchone()
        if member is None:
            raise_api_error(status.HTTP_404_NOT_FOUND, "REPORT_TARGET_NOT_FOUND", "The reported target was not found.")
        return row
    if payload.target_kind == "business_object":
        row = connection.execute("SELECT * FROM chat_messages WHERE message_id = ? AND deleted_at IS NULL AND status = 'sent' AND target_object_type IS NOT NULL LIMIT 1;", (payload.target_id,)).fetchone()
        if row is None:
            row = connection.execute("SELECT * FROM chat_messages WHERE target_object_id = ? AND deleted_at IS NULL AND status = 'sent' LIMIT 1;", (payload.target_id,)).fetchone()
        if row is None:
            raise_api_error(status.HTTP_404_NOT_FOUND, "REPORT_TARGET_NOT_FOUND", "The reported target was not found.")
        member = connection.execute("SELECT 1 FROM chat_conversation_members WHERE conversation_id = ? AND user_id = ? AND status = 'active' AND deleted_at IS NULL LIMIT 1;", (row["conversation_id"], user_id)).fetchone()
        if member is None or not row["target_object_type"] or not resolve_business_object_access(connection, row["target_object_type"], row["target_object_id"], user_id).can_preview:
            raise_api_error(status.HTTP_404_NOT_FOUND, "REPORT_TARGET_NOT_FOUND", "The reported target was not found.")
        return row
    row = connection.execute("SELECT messages.* FROM chat_message_attachments attachments JOIN chat_messages messages ON messages.message_id = attachments.message_id WHERE attachments.media_id = ? AND messages.deleted_at IS NULL AND messages.status = 'sent' LIMIT 1;", (payload.target_id,)).fetchone()
    if row is None:
        raise_api_error(status.HTTP_404_NOT_FOUND, "REPORT_TARGET_NOT_FOUND", "The reported target was not found.")
    member = connection.execute("SELECT 1 FROM chat_conversation_members WHERE conversation_id = ? AND user_id = ? AND status = 'active' AND deleted_at IS NULL LIMIT 1;", (row["conversation_id"], user_id)).fetchone()
    if member is None:
        raise_api_error(status.HTTP_404_NOT_FOUND, "REPORT_TARGET_NOT_FOUND", "The reported target was not found.")
    return row


def create_message_report(user_id: str, payload: MessageReportCreate) -> MessageReportResponse:
    with transaction() as connection:
        _ensure_active_user(connection, user_id)
        message = _validate_message_report_target(connection, user_id, payload)
        existing = connection.execute("SELECT * FROM message_moderation_reports WHERE reporter_user_id = ? AND idempotency_key = ? LIMIT 1;", (user_id, payload.idempotency_key)).fetchone()
        if existing is not None:
            if existing["target_kind"] != payload.target_kind or existing["target_id"] != payload.target_id or existing["reason_code"] != payload.reason_code:
                raise_api_error(status.HTTP_409_CONFLICT, "REPORT_IDEMPOTENCY_CONFLICT", "The idempotency key is already bound to another report.")
            return MessageReportResponse(success=True, report=_message_report_record(existing))
        report_id = str(uuid.uuid4())
        connection.execute("INSERT INTO message_moderation_reports (report_id, reporter_user_id, target_kind, target_id, conversation_id, message_id, object_type, reason_code, description, idempotency_key) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);", (report_id, user_id, payload.target_kind, payload.target_id, message["conversation_id"], message["message_id"], message["target_object_type"], payload.reason_code, payload.description, payload.idempotency_key))
        row = connection.execute("SELECT * FROM message_moderation_reports WHERE report_id = ?;", (report_id,)).fetchone()
    return MessageReportResponse(success=True, report=_message_report_record(row))


def list_message_reports(page: int, page_size: int, status_filter: str | None = None) -> MessageReportListResponse:
    with get_connection() as connection:
        sql = "SELECT * FROM message_moderation_reports"
        params: list[Any] = []
        if status_filter:
            sql += " WHERE status = ?"; params.append(status_filter)
        sql += " ORDER BY created_at DESC, report_id DESC LIMIT ? OFFSET ?;"; params.extend([page_size, (page - 1) * page_size])
        rows = connection.execute(sql, tuple(params)).fetchall()
    return MessageReportListResponse(items=[_message_report_record(row) for row in rows], page=page, page_size=page_size)


def update_message_report(report_id: str, actor_user_id: str, payload: MessageReportUpdate) -> MessageReportResponse:
    allowed = {"open": {"under_review", "rejected", "closed"}, "under_review": {"resolved", "rejected", "closed"}, "resolved": set(), "rejected": set(), "closed": set()}
    with transaction() as connection:
        row = connection.execute("SELECT * FROM message_moderation_reports WHERE report_id = ? LIMIT 1;", (report_id,)).fetchone()
        if row is None:
            raise_api_error(status.HTTP_404_NOT_FOUND, "REPORT_NOT_FOUND", "Report was not found.")
        if payload.status == row["status"]:
            return MessageReportResponse(success=True, report=_message_report_record(row))
        if payload.status not in allowed.get(row["status"], set()):
            raise_api_error(status.HTTP_409_CONFLICT, "REPORT_STATUS_INVALID", "The report status transition is invalid.")
        now = utc_now_iso() if payload.status in {"resolved", "rejected", "closed"} else None
        connection.execute("UPDATE message_moderation_reports SET status = ?, resolved_at = ?, resolved_by = ?, resolution_code = ?, updated_at = CURRENT_TIMESTAMP WHERE report_id = ?;", (payload.status, now, actor_user_id if now else None, payload.resolution_code, report_id))
        connection.execute("INSERT INTO message_moderation_audit_logs (audit_id, report_id, actor_user_id, previous_status, next_status, resolution_code) VALUES (?, ?, ?, ?, ?, ?);", (str(uuid.uuid4()), report_id, actor_user_id, row["status"], payload.status, payload.resolution_code))
        updated = connection.execute("SELECT * FROM message_moderation_reports WHERE report_id = ?;", (report_id,)).fetchone()
    return MessageReportResponse(success=True, report=_message_report_record(updated))
