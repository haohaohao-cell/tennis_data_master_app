from __future__ import annotations

import sqlite3
import uuid
from typing import Any

from fastapi import status

from backend.app.auth.service import raise_api_error
from backend.app.core.database import transaction
from backend.app.posts import interaction_service as post_interactions
from backend.app.reports.schemas import ContentReportCreate, ContentReportCreateResponse, ContentReportRecord


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
