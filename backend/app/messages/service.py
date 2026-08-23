from __future__ import annotations

import json
import sqlite3
import uuid
from typing import Any

from fastapi import status

from backend.app.auth.service import raise_api_error
from backend.app.core.database import get_connection, transaction
from backend.app.core.time import utc_now_iso
from backend.app.messages.schemas import (
    ChatConversationRecord,
    ChatMessageRecord,
    ConversationCreateResponse,
    ConversationListItem,
    ConversationListResponse,
    ConversationMemberRecord,
    DirectConversationCreate,
    GroupConversationCreate,
    MarkReadResponse,
    MessageAttachmentRecord,
    MessageCreate,
    MessageListResponse,
    MessageRequestActionResponse,
    MessageRequestCreate,
    MessageRequestListResponse,
    MessageRequestRecord,
    MessageSendResponse,
    MessageUserSummary,
    NotificationEventRecord,
    NotificationListResponse,
    UserNotificationRecord,
    UnreadCountsResponse,
)


def _row_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {key: row[key] for key in row.keys()}


def _json_text(value: dict[str, Any] | None) -> str | None:
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _ensure_active_user(connection: sqlite3.Connection, user_id: str) -> sqlite3.Row:
    row = connection.execute(
        """
        SELECT user_id, nickname, avatar_path, is_coach, coach_status
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
    return row


def _user_summary(row: sqlite3.Row) -> MessageUserSummary:
    return MessageUserSummary(
        user_id=row["user_id"],
        nickname=row["nickname"],
        avatar_path=row["avatar_path"],
        is_coach=bool(row["is_coach"]),
        coach_status=row["coach_status"],
    )


def _ensure_not_blocked(
    connection: sqlite3.Connection,
    user_id: str,
    target_user_id: str,
) -> None:
    blocked = connection.execute(
        """
        SELECT 1
        FROM user_blocks
        WHERE deleted_at IS NULL
          AND (
              (blocker_user_id = ? AND blocked_user_id = ?)
              OR (blocker_user_id = ? AND blocked_user_id = ?)
          )
        LIMIT 1;
        """,
        (user_id, target_user_id, target_user_id, user_id),
    ).fetchone()
    if blocked is not None:
        raise_api_error(
            status.HTTP_403_FORBIDDEN,
            "USER_INTERACTION_BLOCKED",
            "Messaging is unavailable between these users.",
        )


def _is_following(connection: sqlite3.Connection, follower_user_id: str, following_user_id: str) -> bool:
    row = connection.execute(
        """
        SELECT 1
        FROM user_follows
        WHERE follower_user_id = ?
          AND following_user_id = ?
          AND status = 'active'
        LIMIT 1;
        """,
        (follower_user_id, following_user_id),
    ).fetchone()
    return row is not None


def _privacy_settings_row(connection: sqlite3.Connection, user_id: str) -> sqlite3.Row | None:
    return connection.execute(
        """
        SELECT *
        FROM user_privacy_settings
        WHERE user_id = ?
        LIMIT 1;
        """,
        (user_id,),
    ).fetchone()


def _direct_message_permission(
    connection: sqlite3.Connection,
    requester_user_id: str,
    recipient_user_id: str,
) -> tuple[bool, bool]:
    settings = _privacy_settings_row(connection, recipient_user_id)
    policy = settings["direct_message_policy"] if settings else "friends"
    allow_requests = bool(settings["allow_message_requests"]) if settings else True
    recipient_follows_requester = _is_following(connection, recipient_user_id, requester_user_id)
    requester_follows_recipient = _is_following(connection, requester_user_id, recipient_user_id)
    if policy == "everyone":
        return True, allow_requests
    if policy == "following":
        return recipient_follows_requester, allow_requests
    return recipient_follows_requester and requester_follows_recipient, allow_requests


def _pair_key(first_user_id: str, second_user_id: str) -> str:
    return ":".join(sorted((first_user_id, second_user_id)))


def _conversation_record(row: sqlite3.Row) -> ChatConversationRecord:
    return ChatConversationRecord(
        conversation_id=row["conversation_id"],
        conversation_type=row["conversation_type"],
        group_type=row["group_type"],
        title=row["title"],
        avatar_path=row["avatar_path"],
        context_type=row["context_type"],
        context_id=row["context_id"],
        status=row["status"],
        last_message_id=row["last_message_id"],
        last_message_seq=row["last_message_seq"],
        last_message_preview=row["last_message_preview"],
        last_message_at=row["last_message_at"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _member_record(row: sqlite3.Row) -> ConversationMemberRecord:
    return ConversationMemberRecord(
        conversation_member_id=row["conversation_member_id"],
        conversation_id=row["conversation_id"],
        user_id=row["user_id"],
        member_role=row["member_role"],
        status=row["status"],
        joined_at=row["joined_at"],
        left_at=row["left_at"],
        last_read_message_id=row["last_read_message_id"],
        last_read_message_seq=row["last_read_message_seq"],
        last_read_at=row["last_read_at"],
        unread_count=row["unread_count"],
        muted_until=row["muted_until"],
        pinned_at=row["pinned_at"],
        archived_at=row["archived_at"],
    )


def _select_member(
    connection: sqlite3.Connection,
    conversation_id: str,
    user_id: str,
    require_active: bool = True,
) -> sqlite3.Row:
    query = """
        SELECT *
        FROM chat_conversation_members
        WHERE conversation_id = ?
          AND user_id = ?
          AND deleted_at IS NULL
    """
    params: list[object] = [conversation_id, user_id]
    if require_active:
        query += " AND status = 'active'"
    query += " LIMIT 1;"
    row = connection.execute(query, tuple(params)).fetchone()
    if row is None:
        raise_api_error(
            status.HTTP_403_FORBIDDEN,
            "CONVERSATION_ACCESS_DENIED",
            "You are not an active member of this conversation.",
        )
    return row


def _select_conversation(connection: sqlite3.Connection, conversation_id: str) -> sqlite3.Row:
    row = connection.execute(
        """
        SELECT *
        FROM chat_conversations
        WHERE conversation_id = ?
          AND status <> 'deleted'
          AND deleted_at IS NULL
        LIMIT 1;
        """,
        (conversation_id,),
    ).fetchone()
    if row is None:
        raise_api_error(
            status.HTTP_404_NOT_FOUND,
            "CONVERSATION_NOT_FOUND",
            "Conversation was not found.",
        )
    return row


def _other_members(
    connection: sqlite3.Connection,
    conversation_id: str,
    current_user_id: str,
) -> list[MessageUserSummary]:
    rows = connection.execute(
        """
        SELECT users.user_id, users.nickname, users.avatar_path, users.is_coach, users.coach_status
        FROM chat_conversation_members
        JOIN users ON users.user_id = chat_conversation_members.user_id
        WHERE chat_conversation_members.conversation_id = ?
          AND chat_conversation_members.user_id <> ?
          AND chat_conversation_members.status = 'active'
          AND chat_conversation_members.deleted_at IS NULL
          AND users.status = 'active'
          AND users.deleted_at IS NULL
        ORDER BY chat_conversation_members.joined_at ASC, users.user_id ASC;
        """,
        (conversation_id, current_user_id),
    ).fetchall()
    return [_user_summary(row) for row in rows]


def _ensure_counter(connection: sqlite3.Connection, user_id: str) -> None:
    connection.execute(
        """
        INSERT OR IGNORE INTO user_inbox_counters (user_id)
        VALUES (?);
        """,
        (user_id,),
    )


def _increment_message_counter(
    connection: sqlite3.Connection,
    user_id: str,
    conversation_type: str,
    amount: int,
) -> None:
    _ensure_counter(connection, user_id)
    column = (
        "unread_direct_message_count"
        if conversation_type == "direct"
        else "unread_group_message_count"
    )
    connection.execute(
        f"""
        UPDATE user_inbox_counters
        SET {column} = MAX(0, {column} + ?)
        WHERE user_id = ?;
        """,
        (amount, user_id),
    )


def _increment_notification_counter(
    connection: sqlite3.Connection,
    user_id: str,
    amount: int,
) -> None:
    _ensure_counter(connection, user_id)
    connection.execute(
        """
        UPDATE user_inbox_counters
        SET unread_notification_count = MAX(0, unread_notification_count + ?)
        WHERE user_id = ?;
        """,
        (amount, user_id),
    )


def _ensure_membership(
    connection: sqlite3.Connection,
    conversation_id: str,
    user_id: str,
    member_role: str,
) -> sqlite3.Row:
    existing = connection.execute(
        """
        SELECT *
        FROM chat_conversation_members
        WHERE conversation_id = ?
          AND user_id = ?
          AND deleted_at IS NULL
        LIMIT 1;
        """,
        (conversation_id, user_id),
    ).fetchone()
    if existing is None:
        member_id = str(uuid.uuid4())
        connection.execute(
            """
            INSERT INTO chat_conversation_members (
                conversation_member_id,
                conversation_id,
                user_id,
                member_role
            )
            VALUES (?, ?, ?, ?);
            """,
            (member_id, conversation_id, user_id, member_role),
        )
    elif existing["status"] != "active":
        connection.execute(
            """
            UPDATE chat_conversation_members
            SET status = 'active',
                left_at = NULL,
                member_role = ?
            WHERE conversation_member_id = ?;
            """,
            (member_role, existing["conversation_member_id"]),
        )

    return connection.execute(
        """
        SELECT *
        FROM chat_conversation_members
        WHERE conversation_id = ?
          AND user_id = ?
          AND deleted_at IS NULL
        LIMIT 1;
        """,
        (conversation_id, user_id),
    ).fetchone()


def _conversation_create_response(
    connection: sqlite3.Connection,
    conversation_id: str,
    user_id: str,
) -> ConversationCreateResponse:
    conversation = _select_conversation(connection, conversation_id)
    member = _select_member(connection, conversation_id, user_id)
    return ConversationCreateResponse(
        conversation=_conversation_record(conversation),
        member=_member_record(member),
        other_members=_other_members(connection, conversation_id, user_id),
    )


def ensure_direct_conversation_in_transaction(
    connection: sqlite3.Connection,
    user_id: str,
    target_user_id: str,
    *,
    created_by_user_id: str | None = None,
    require_direct_permission: bool = True,
) -> str:
    direct_pair_key = _pair_key(user_id, target_user_id)
    conversation = connection.execute(
        """
        SELECT conversation_id
        FROM chat_conversations
        WHERE conversation_type = 'direct'
          AND direct_pair_key = ?
          AND deleted_at IS NULL
        LIMIT 1;
        """,
        (direct_pair_key,),
    ).fetchone()
    if conversation is None and require_direct_permission:
        can_message, allow_requests = _direct_message_permission(connection, user_id, target_user_id)
        if not can_message:
            if allow_requests:
                raise_api_error(
                    status.HTTP_403_FORBIDDEN,
                    "MESSAGE_REQUEST_REQUIRED",
                    "A message request is required before starting this conversation.",
                )
            raise_api_error(
                status.HTTP_403_FORBIDDEN,
                "DIRECT_MESSAGE_NOT_ALLOWED",
                "This user does not accept direct messages from you.",
            )

    if conversation is None:
        conversation_id = str(uuid.uuid4())
        connection.execute(
            """
            INSERT INTO chat_conversations (
                conversation_id,
                conversation_type,
                direct_pair_key,
                created_by_user_id
            )
            VALUES (?, 'direct', ?, ?);
            """,
            (conversation_id, direct_pair_key, created_by_user_id or user_id),
        )
    else:
        conversation_id = conversation["conversation_id"]

    _ensure_membership(connection, conversation_id, user_id, "member")
    _ensure_membership(connection, conversation_id, target_user_id, "member")
    return conversation_id


def create_direct_conversation(
    user_id: str,
    payload: DirectConversationCreate,
) -> ConversationCreateResponse:
    target_user_id = payload.target_user_id.strip()
    if user_id == target_user_id:
        raise_api_error(status.HTTP_400_BAD_REQUEST, "CANNOT_MESSAGE_SELF", "You cannot message yourself.")

    with transaction() as connection:
        _ensure_active_user(connection, user_id)
        _ensure_active_user(connection, target_user_id)
        _ensure_not_blocked(connection, user_id, target_user_id)
        conversation_id = ensure_direct_conversation_in_transaction(
            connection,
            user_id,
            target_user_id,
            created_by_user_id=user_id,
            require_direct_permission=True,
        )
        return _conversation_create_response(connection, conversation_id, user_id)


def create_group_conversation(
    user_id: str,
    payload: GroupConversationCreate,
) -> ConversationCreateResponse:
    member_ids = list(dict.fromkeys([user_id, *payload.member_user_ids]))
    with transaction() as connection:
        _ensure_active_user(connection, user_id)
        for member_id in member_ids:
            _ensure_active_user(connection, member_id)
            if member_id != user_id:
                _ensure_not_blocked(connection, user_id, member_id)

        conversation_id = str(uuid.uuid4())
        connection.execute(
            """
            INSERT INTO chat_conversations (
                conversation_id,
                conversation_type,
                group_type,
                title,
                created_by_user_id,
                context_type,
                context_id
            )
            VALUES (?, 'group', ?, ?, ?, ?, ?);
            """,
            (
                conversation_id,
                payload.group_type,
                payload.title,
                user_id,
                payload.context_type,
                payload.context_id,
            ),
        )
        _ensure_membership(connection, conversation_id, user_id, "owner")
        for member_id in member_ids:
            if member_id != user_id:
                _ensure_membership(connection, conversation_id, member_id, "member")
        return _conversation_create_response(connection, conversation_id, user_id)


def list_conversations(user_id: str, page: int, page_size: int) -> ConversationListResponse:
    offset = (page - 1) * page_size
    with get_connection() as connection:
        _ensure_active_user(connection, user_id)
        rows = connection.execute(
            """
            SELECT
                conversations.*,
                members.conversation_member_id,
                members.user_id AS member_user_id,
                members.member_role,
                members.status AS member_status,
                members.joined_at,
                members.left_at,
                members.last_read_message_id,
                members.last_read_message_seq,
                members.last_read_at,
                members.unread_count,
                members.muted_until,
                members.pinned_at,
                members.archived_at
            FROM chat_conversation_members AS members
            JOIN chat_conversations AS conversations
              ON conversations.conversation_id = members.conversation_id
            WHERE members.user_id = ?
              AND members.status = 'active'
              AND members.deleted_at IS NULL
              AND members.archived_at IS NULL
              AND conversations.status = 'active'
              AND conversations.deleted_at IS NULL
            ORDER BY
                CASE WHEN conversations.last_message_at IS NULL THEN 1 ELSE 0 END,
                conversations.last_message_at DESC,
                conversations.created_at DESC
            LIMIT ? OFFSET ?;
            """,
            (user_id, page_size, offset),
        ).fetchall()

    items: list[ConversationListItem] = []
    for row in rows:
        member_row = {
            "conversation_member_id": row["conversation_member_id"],
            "conversation_id": row["conversation_id"],
            "user_id": row["member_user_id"],
            "member_role": row["member_role"],
            "status": row["member_status"],
            "joined_at": row["joined_at"],
            "left_at": row["left_at"],
            "last_read_message_id": row["last_read_message_id"],
            "last_read_message_seq": row["last_read_message_seq"],
            "last_read_at": row["last_read_at"],
            "unread_count": row["unread_count"],
            "muted_until": row["muted_until"],
            "pinned_at": row["pinned_at"],
            "archived_at": row["archived_at"],
        }
        with get_connection() as member_connection:
            other_members = _other_members(member_connection, row["conversation_id"], user_id)
        items.append(
            ConversationListItem(
                conversation=_conversation_record(row),
                member=ConversationMemberRecord(**member_row),
                other_members=other_members,
            )
        )
    return ConversationListResponse(items=items, page=page, page_size=page_size)


def _validate_object_reference(
    connection: sqlite3.Connection,
    object_type: str | None,
    object_id: str | None,
) -> None:
    if object_type is None or object_id is None or object_type in {"analysis", "custom"}:
        return
    table_column = {
        "user": ("users", "user_id"),
        "video": ("videos", "video_id"),
        "social_post": ("social_posts", "social_post_id"),
        "tennis_activity": ("tennis_activities", "tennis_activity_id"),
        "lesson": ("lessons", "lesson_id"),
    }.get(object_type)
    if table_column is None:
        return
    table, column = table_column
    row = connection.execute(
        f"""
        SELECT 1
        FROM {table}
        WHERE {column} = ?
          AND deleted_at IS NULL
        LIMIT 1;
        """,
        (object_id,),
    ).fetchone()
    if row is None:
        raise_api_error(
            status.HTTP_404_NOT_FOUND,
            "MESSAGE_OBJECT_NOT_FOUND",
            "The referenced message object was not found.",
        )


def _message_preview(payload: MessageCreate) -> str:
    if payload.text_content:
        return payload.text_content[:255]
    labels = {
        "image": "[Image]",
        "video": "[Video]",
        "audio": "[Audio]",
        "file": "[File]",
        "post_share": "[Post]",
        "video_share": "[Video]",
        "activity_share": "[Activity]",
        "lesson_share": "[Lesson]",
        "analysis_card": "[Analysis]",
        "system_event": "[System]",
    }
    return labels.get(payload.message_type, "[Message]")


def _select_message(connection: sqlite3.Connection, message_id: str) -> sqlite3.Row:
    row = connection.execute(
        """
        SELECT *
        FROM chat_messages
        WHERE message_id = ?
        LIMIT 1;
        """,
        (message_id,),
    ).fetchone()
    if row is None:
        raise_api_error(status.HTTP_404_NOT_FOUND, "MESSAGE_NOT_FOUND", "Message was not found.")
    return row


def _message_record(connection: sqlite3.Connection, row: sqlite3.Row) -> ChatMessageRecord:
    sender = None
    if row["sender_user_id"]:
        sender_row = connection.execute(
            """
            SELECT user_id, nickname, avatar_path, is_coach, coach_status
            FROM users
            WHERE user_id = ?
            LIMIT 1;
            """,
            (row["sender_user_id"],),
        ).fetchone()
        if sender_row is not None:
            sender = _user_summary(sender_row)

    attachments = connection.execute(
        """
        SELECT *
        FROM chat_message_attachments
        WHERE message_id = ?
        ORDER BY sort_order ASC, attachment_id ASC;
        """,
        (row["message_id"],),
    ).fetchall()
    return ChatMessageRecord(
        message_id=row["message_id"],
        conversation_id=row["conversation_id"],
        message_seq=row["message_seq"],
        sender_user_id=row["sender_user_id"],
        sender_type=row["sender_type"],
        message_type=row["message_type"],
        text_content=row["text_content"],
        payload_json=row["payload_json"],
        target_object_type=row["target_object_type"],
        target_object_id=row["target_object_id"],
        context_object_type=row["context_object_type"],
        context_object_id=row["context_object_id"],
        reply_to_message_id=row["reply_to_message_id"],
        client_message_id=row["client_message_id"],
        status=row["status"],
        sent_at=row["sent_at"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        deleted_at=row["deleted_at"],
        sender=sender,
        attachments=[MessageAttachmentRecord(**_row_dict(item)) for item in attachments],
    )


def send_message_in_transaction(
    connection: sqlite3.Connection,
    user_id: str,
    conversation_id: str,
    payload: MessageCreate,
) -> MessageSendResponse:
    _ensure_active_user(connection, user_id)
    conversation = _select_conversation(connection, conversation_id)
    member = _select_member(connection, conversation_id, user_id)

    if conversation["conversation_type"] == "direct":
        direct_members = connection.execute(
            """
            SELECT user_id
            FROM chat_conversation_members
            WHERE conversation_id = ?
              AND user_id <> ?
              AND status = 'active'
              AND deleted_at IS NULL;
            """,
            (conversation_id, user_id),
        ).fetchall()
        for direct_member in direct_members:
            _ensure_not_blocked(connection, user_id, direct_member["user_id"])

    existing = None
    if payload.client_message_id:
        existing = connection.execute(
            """
            SELECT *
            FROM chat_messages
            WHERE sender_user_id = ?
              AND client_message_id = ?
            LIMIT 1;
            """,
            (user_id, payload.client_message_id),
        ).fetchone()
    if existing is not None:
        return MessageSendResponse(message=_message_record(connection, existing))

    _validate_object_reference(connection, payload.target_object_type, payload.target_object_id)
    _validate_object_reference(connection, payload.context_object_type, payload.context_object_id)
    if payload.reply_to_message_id:
        reply = _select_message(connection, payload.reply_to_message_id)
        if reply["conversation_id"] != conversation_id:
            raise_api_error(
                status.HTTP_400_BAD_REQUEST,
                "REPLY_MESSAGE_WRONG_CONVERSATION",
                "The reply target belongs to another conversation.",
            )

    message_seq = conversation["last_message_seq"] + 1
    message_id = str(uuid.uuid4())
    connection.execute(
        """
        INSERT INTO chat_messages (
            message_id,
            conversation_id,
            message_seq,
            sender_user_id,
            message_type,
            text_content,
            payload_json,
            target_object_type,
            target_object_id,
            context_object_type,
            context_object_id,
            reply_to_message_id,
            client_message_id
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """,
        (
            message_id,
            conversation_id,
            message_seq,
            user_id,
            payload.message_type,
            payload.text_content,
            _json_text(payload.payload),
            payload.target_object_type,
            payload.target_object_id,
            payload.context_object_type,
            payload.context_object_id,
            payload.reply_to_message_id,
            payload.client_message_id,
        ),
    )

    for sort_order, attachment in enumerate(payload.attachments):
        _validate_object_reference(connection, attachment.object_type, attachment.object_id)
        connection.execute(
            """
            INSERT INTO chat_message_attachments (
                attachment_id,
                message_id,
                attachment_type,
                media_path,
                thumbnail_path,
                mime_type,
                file_size_bytes,
                duration_ms,
                width_px,
                height_px,
                object_type,
                object_id,
                payload_json,
                sort_order
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                str(uuid.uuid4()),
                message_id,
                attachment.attachment_type,
                attachment.media_path,
                attachment.thumbnail_path,
                attachment.mime_type,
                attachment.file_size_bytes,
                attachment.duration_ms,
                attachment.width_px,
                attachment.height_px,
                attachment.object_type,
                attachment.object_id,
                _json_text(attachment.payload),
                sort_order,
            ),
        )

    connection.execute(
        """
        UPDATE chat_conversations
        SET last_message_id = ?,
            last_message_seq = ?,
            last_message_preview = ?,
            last_message_at = CURRENT_TIMESTAMP
        WHERE conversation_id = ?;
        """,
        (message_id, message_seq, _message_preview(payload), conversation_id),
    )
    connection.execute(
        """
        UPDATE chat_conversation_members
        SET last_read_message_id = ?,
            last_read_message_seq = ?,
            last_read_at = CURRENT_TIMESTAMP,
            unread_count = 0
        WHERE conversation_member_id = ?;
        """,
        (message_id, message_seq, member["conversation_member_id"]),
    )

    recipients = connection.execute(
        """
        SELECT conversation_member_id, user_id
        FROM chat_conversation_members
        WHERE conversation_id = ?
          AND user_id <> ?
          AND status = 'active'
          AND deleted_at IS NULL;
        """,
        (conversation_id, user_id),
    ).fetchall()
    for recipient in recipients:
        connection.execute(
            """
            UPDATE chat_conversation_members
            SET unread_count = unread_count + 1
            WHERE conversation_member_id = ?;
            """,
            (recipient["conversation_member_id"],),
        )
        _increment_message_counter(connection, recipient["user_id"], conversation["conversation_type"], 1)

    return MessageSendResponse(message=_message_record(connection, _select_message(connection, message_id)))


def send_message(
    user_id: str,
    conversation_id: str,
    payload: MessageCreate,
) -> MessageSendResponse:
    with transaction() as connection:
        return send_message_in_transaction(connection, user_id, conversation_id, payload)


def _request_user_summary(connection: sqlite3.Connection, user_id: str) -> MessageUserSummary:
    row = connection.execute(
        """
        SELECT user_id, nickname, avatar_path, is_coach, coach_status
        FROM users
        WHERE user_id = ?
        LIMIT 1;
        """,
        (user_id,),
    ).fetchone()
    if row is None:
        raise_api_error(status.HTTP_404_NOT_FOUND, "USER_NOT_FOUND", "User was not found.")
    return _user_summary(row)


def _message_request_record(connection: sqlite3.Connection, row: sqlite3.Row) -> MessageRequestRecord:
    return MessageRequestRecord(
        message_request_id=row["message_request_id"],
        requester_user_id=row["requester_user_id"],
        recipient_user_id=row["recipient_user_id"],
        conversation_id=row["conversation_id"],
        status=row["status"],
        request_message=row["request_message"],
        source=row["source"],
        requested_at=row["requested_at"],
        responded_at=row["responded_at"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        requester=_request_user_summary(connection, row["requester_user_id"]),
        recipient=_request_user_summary(connection, row["recipient_user_id"]),
    )


def _select_message_request(connection: sqlite3.Connection, message_request_id: str) -> sqlite3.Row:
    row = connection.execute(
        """
        SELECT *
        FROM chat_message_requests
        WHERE message_request_id = ?
        LIMIT 1;
        """,
        (message_request_id,),
    ).fetchone()
    if row is None:
        raise_api_error(
            status.HTTP_404_NOT_FOUND,
            "MESSAGE_REQUEST_NOT_FOUND",
            "Message request was not found.",
        )
    return row


def create_message_request(user_id: str, payload: MessageRequestCreate) -> MessageRequestActionResponse:
    target_user_id = (payload.target_user_id or "").strip()
    if not target_user_id:
        raise_api_error(status.HTTP_400_BAD_REQUEST, "TARGET_USER_REQUIRED", "Target user is required.")
    if user_id == target_user_id:
        raise_api_error(status.HTTP_400_BAD_REQUEST, "CANNOT_MESSAGE_SELF", "You cannot message yourself.")

    with transaction() as connection:
        requester = _ensure_active_user(connection, user_id)
        _ensure_active_user(connection, target_user_id)
        _ensure_not_blocked(connection, user_id, target_user_id)
        direct_pair_key = _pair_key(user_id, target_user_id)
        existing_conversation = connection.execute(
            """
            SELECT conversation_id
            FROM chat_conversations
            WHERE conversation_type = 'direct'
              AND direct_pair_key = ?
              AND deleted_at IS NULL
            LIMIT 1;
            """,
            (direct_pair_key,),
        ).fetchone()
        if existing_conversation is not None:
            raise_api_error(
                status.HTTP_409_CONFLICT,
                "DIRECT_CONVERSATION_EXISTS",
                "A direct conversation already exists between these users.",
            )

        can_message, allow_requests = _direct_message_permission(connection, user_id, target_user_id)
        if can_message:
            raise_api_error(
                status.HTTP_409_CONFLICT,
                "MESSAGE_REQUEST_NOT_REQUIRED",
                "This user can receive direct messages from you.",
            )
        if not allow_requests:
            raise_api_error(
                status.HTTP_403_FORBIDDEN,
                "MESSAGE_REQUESTS_DISABLED",
                "This user does not accept message requests.",
            )

        existing_request = connection.execute(
            """
            SELECT *
            FROM chat_message_requests
            WHERE requester_user_id = ?
              AND recipient_user_id = ?
              AND status = 'pending'
            LIMIT 1;
            """,
            (user_id, target_user_id),
        ).fetchone()
        if existing_request is None:
            message_request_id = str(uuid.uuid4())
            connection.execute(
                """
                INSERT INTO chat_message_requests (
                    message_request_id,
                    requester_user_id,
                    recipient_user_id,
                    request_message,
                    source
                )
                VALUES (?, ?, ?, ?, ?);
                """,
                (
                    message_request_id,
                    user_id,
                    target_user_id,
                    payload.request_message,
                    payload.source,
                ),
            )
            row = _select_message_request(connection, message_request_id)
            create_notification_in_transaction(
                connection,
                recipient_user_id=target_user_id,
                event_type="custom",
                category="interaction",
                actor_user_id=user_id,
                object_type="user",
                object_id=user_id,
                title="New message request",
                body=f"{requester['nickname']} sent you a message request.",
                deep_link="/messages/requests",
                dedup_key=f"message_request:{message_request_id}",
                payload={"message_request_id": message_request_id},
            )
        else:
            row = existing_request
        request_record = _message_request_record(connection, row)
    return MessageRequestActionResponse(success=True, request=request_record)


def list_message_requests(
    user_id: str,
    box: str,
    status_filter: str | None,
    page: int,
    page_size: int,
) -> MessageRequestListResponse:
    if box not in {"inbox", "sent"}:
        raise_api_error(status.HTTP_400_BAD_REQUEST, "INVALID_MESSAGE_REQUEST_BOX", "Message request box is invalid.")
    if status_filter and status_filter not in {"pending", "accepted", "declined", "blocked", "canceled"}:
        raise_api_error(
            status.HTTP_400_BAD_REQUEST,
            "INVALID_MESSAGE_REQUEST_STATUS",
            "Message request status is invalid.",
        )

    offset = (page - 1) * page_size
    owner_column = "recipient_user_id" if box == "inbox" else "requester_user_id"
    with get_connection() as connection:
        _ensure_active_user(connection, user_id)
        query = f"""
            SELECT *
            FROM chat_message_requests
            WHERE {owner_column} = ?
        """
        params: list[object] = [user_id]
        if status_filter:
            query += " AND status = ?"
            params.append(status_filter)
        query += " ORDER BY requested_at DESC, message_request_id DESC LIMIT ? OFFSET ?;"
        params.extend([page_size, offset])
        rows = connection.execute(query, tuple(params)).fetchall()
        items = [_message_request_record(connection, row) for row in rows]
    return MessageRequestListResponse(items=items, page=page, page_size=page_size)


def accept_message_request(user_id: str, message_request_id: str) -> MessageRequestActionResponse:
    with transaction() as connection:
        _ensure_active_user(connection, user_id)
        row = _select_message_request(connection, message_request_id)
        if row["recipient_user_id"] != user_id or row["status"] != "pending":
            raise_api_error(
                status.HTTP_404_NOT_FOUND,
                "MESSAGE_REQUEST_NOT_FOUND",
                "Pending message request was not found.",
            )
        _ensure_not_blocked(connection, row["requester_user_id"], row["recipient_user_id"])
        conversation_id = ensure_direct_conversation_in_transaction(
            connection,
            row["requester_user_id"],
            row["recipient_user_id"],
            created_by_user_id=user_id,
            require_direct_permission=False,
        )
        connection.execute(
            """
            UPDATE chat_message_requests
            SET status = 'accepted',
                conversation_id = ?,
                responded_at = ?
            WHERE message_request_id = ?;
            """,
            (conversation_id, utc_now_iso(), message_request_id),
        )
        request_record = _message_request_record(connection, _select_message_request(connection, message_request_id))
        conversation = _select_conversation(connection, conversation_id)
        member = _select_member(connection, conversation_id, user_id)
        return MessageRequestActionResponse(
            success=True,
            request=request_record,
            conversation=_conversation_record(conversation),
            member=_member_record(member),
            other_members=_other_members(connection, conversation_id, user_id),
        )


def decline_message_request(user_id: str, message_request_id: str) -> MessageRequestActionResponse:
    with transaction() as connection:
        _ensure_active_user(connection, user_id)
        row = _select_message_request(connection, message_request_id)
        if row["recipient_user_id"] != user_id or row["status"] != "pending":
            raise_api_error(
                status.HTTP_404_NOT_FOUND,
                "MESSAGE_REQUEST_NOT_FOUND",
                "Pending message request was not found.",
            )
        connection.execute(
            """
            UPDATE chat_message_requests
            SET status = 'declined',
                responded_at = ?
            WHERE message_request_id = ?;
            """,
            (utc_now_iso(), message_request_id),
        )
        request_record = _message_request_record(connection, _select_message_request(connection, message_request_id))
    return MessageRequestActionResponse(success=True, request=request_record)


def list_messages(
    user_id: str,
    conversation_id: str,
    page_size: int,
    before_seq: int | None,
) -> MessageListResponse:
    with get_connection() as connection:
        _ensure_active_user(connection, user_id)
        _select_conversation(connection, conversation_id)
        _select_member(connection, conversation_id, user_id)
        query = """
            SELECT *
            FROM chat_messages
            WHERE conversation_id = ?
              AND deleted_at IS NULL
        """
        params: list[object] = [conversation_id]
        if before_seq is not None:
            query += " AND message_seq < ?"
            params.append(before_seq)
        query += " ORDER BY message_seq DESC LIMIT ?;"
        params.append(page_size)
        rows = connection.execute(query, tuple(params)).fetchall()
        ordered_rows = list(reversed(rows))
        messages = [_message_record(connection, row) for row in ordered_rows]
        next_before_seq = rows[-1]["message_seq"] if len(rows) == page_size else None
    return MessageListResponse(
        items=messages,
        conversation_id=conversation_id,
        next_before_seq=next_before_seq,
    )


def mark_conversation_read(user_id: str, conversation_id: str) -> MarkReadResponse:
    with transaction() as connection:
        _ensure_active_user(connection, user_id)
        conversation = _select_conversation(connection, conversation_id)
        member = _select_member(connection, conversation_id, user_id)
        previous_unread = member["unread_count"]
        connection.execute(
            """
            UPDATE chat_conversation_members
            SET last_read_message_id = ?,
                last_read_message_seq = ?,
                last_read_at = CURRENT_TIMESTAMP,
                unread_count = 0
            WHERE conversation_member_id = ?;
            """,
            (
                conversation["last_message_id"],
                conversation["last_message_seq"],
                member["conversation_member_id"],
            ),
        )
        if previous_unread:
            _increment_message_counter(
                connection,
                user_id,
                conversation["conversation_type"],
                -previous_unread,
            )
    return MarkReadResponse(success=True, conversation_id=conversation_id, unread_count=0)


def get_unread_counts(user_id: str) -> UnreadCountsResponse:
    with get_connection() as connection:
        _ensure_active_user(connection, user_id)
        row = connection.execute(
            """
            SELECT
                COALESCE(SUM(CASE WHEN conversations.conversation_type = 'direct'
                    THEN members.unread_count ELSE 0 END), 0) AS unread_direct,
                COALESCE(SUM(CASE WHEN conversations.conversation_type = 'group'
                    THEN members.unread_count ELSE 0 END), 0) AS unread_group
            FROM chat_conversation_members AS members
            JOIN chat_conversations AS conversations
              ON conversations.conversation_id = members.conversation_id
            WHERE members.user_id = ?
              AND members.status = 'active'
              AND members.deleted_at IS NULL
              AND conversations.status = 'active'
              AND conversations.deleted_at IS NULL;
            """,
            (user_id,),
        ).fetchone()
        unread_notification = connection.execute(
            """
            SELECT count(*)
            FROM user_notifications
            WHERE recipient_user_id = ?
              AND status = 'visible'
              AND read_at IS NULL
              AND deleted_at IS NULL;
            """,
            (user_id,),
        ).fetchone()[0]

    unread_direct = int(row["unread_direct"])
    unread_group = int(row["unread_group"])
    unread_notification = int(unread_notification)
    return UnreadCountsResponse(
        unread_direct_message_count=unread_direct,
        unread_group_message_count=unread_group,
        unread_notification_count=unread_notification,
        total_unread_count=unread_direct + unread_group + unread_notification,
    )


def create_notification_in_transaction(
    connection: sqlite3.Connection,
    *,
    recipient_user_id: str,
    event_type: str,
    category: str,
    actor_user_id: str | None = None,
    object_type: str | None = None,
    object_id: str | None = None,
    context_type: str | None = None,
    context_id: str | None = None,
    title: str | None = None,
    body: str | None = None,
    deep_link: str | None = None,
    dedup_key: str | None = None,
    aggregation_key: str | None = None,
    payload: dict[str, Any] | None = None,
) -> str:
    _ensure_active_user(connection, recipient_user_id)
    event = None
    if dedup_key:
        event = connection.execute(
            """
            SELECT notification_event_id
            FROM notification_events
            WHERE dedup_key = ?
            LIMIT 1;
            """,
            (dedup_key,),
        ).fetchone()
    if event is None:
        event_id = str(uuid.uuid4())
        connection.execute(
            """
            INSERT INTO notification_events (
                notification_event_id,
                event_type,
                category,
                actor_user_id,
                object_type,
                object_id,
                context_type,
                context_id,
                title,
                body,
                deep_link,
                payload_json,
                dedup_key,
                aggregation_key
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                event_id,
                event_type,
                category,
                actor_user_id,
                object_type,
                object_id,
                context_type,
                context_id,
                title,
                body,
                deep_link,
                _json_text(payload),
                dedup_key,
                aggregation_key,
            ),
        )
    else:
        event_id = event["notification_event_id"]

    recipient = connection.execute(
        """
        SELECT user_notification_id
        FROM user_notifications
        WHERE recipient_user_id = ?
          AND notification_event_id = ?
        LIMIT 1;
        """,
        (recipient_user_id, event_id),
    ).fetchone()
    if recipient is None:
        connection.execute(
            """
            INSERT INTO user_notifications (
                user_notification_id,
                notification_event_id,
                recipient_user_id,
                priority
            )
            VALUES (?, ?, ?, ?);
            """,
            (str(uuid.uuid4()), event_id, recipient_user_id, "high" if category in {"ai", "coach"} else "normal"),
        )
        _increment_notification_counter(connection, recipient_user_id, 1)
    return event_id


def _notification_record(connection: sqlite3.Connection, row: sqlite3.Row) -> UserNotificationRecord:
    event = NotificationEventRecord(
        notification_event_id=row["notification_event_id"],
        event_type=row["event_type"],
        category=row["category"],
        actor_user_id=row["actor_user_id"],
        object_type=row["object_type"],
        object_id=row["object_id"],
        context_type=row["context_type"],
        context_id=row["context_id"],
        title=row["title"],
        body=row["body"],
        deep_link=row["deep_link"],
        payload_json=row["payload_json"],
        created_at=row["event_created_at"],
    )
    actor = None
    if row["actor_id"]:
        actor = MessageUserSummary(
            user_id=row["actor_id"],
            nickname=row["actor_nickname"],
            avatar_path=row["actor_avatar_path"],
            is_coach=bool(row["actor_is_coach"]),
            coach_status=row["actor_coach_status"],
        )
    return UserNotificationRecord(
        user_notification_id=row["user_notification_id"],
        notification_event_id=row["notification_event_id"],
        recipient_user_id=row["recipient_user_id"],
        status=row["notification_status"],
        priority=row["priority"],
        delivered_at=row["delivered_at"],
        seen_at=row["seen_at"],
        read_at=row["read_at"],
        dismissed_at=row["dismissed_at"],
        created_at=row["notification_created_at"],
        event=event,
        actor=actor,
    )


def list_notifications(
    user_id: str,
    page: int,
    page_size: int,
    category: str | None,
    unread_only: bool,
) -> NotificationListResponse:
    offset = (page - 1) * page_size
    with get_connection() as connection:
        _ensure_active_user(connection, user_id)
        query = """
            SELECT
                user_notifications.user_notification_id,
                user_notifications.recipient_user_id,
                user_notifications.status AS notification_status,
                user_notifications.priority,
                user_notifications.delivered_at,
                user_notifications.seen_at,
                user_notifications.read_at,
                user_notifications.dismissed_at,
                user_notifications.created_at AS notification_created_at,
                notification_events.notification_event_id,
                notification_events.event_type,
                notification_events.category,
                notification_events.actor_user_id,
                notification_events.object_type,
                notification_events.object_id,
                notification_events.context_type,
                notification_events.context_id,
                notification_events.title,
                notification_events.body,
                notification_events.deep_link,
                notification_events.payload_json,
                notification_events.created_at AS event_created_at,
                actors.user_id AS actor_id,
                actors.nickname AS actor_nickname,
                actors.avatar_path AS actor_avatar_path,
                actors.is_coach AS actor_is_coach,
                actors.coach_status AS actor_coach_status
            FROM user_notifications
            JOIN notification_events
              ON notification_events.notification_event_id = user_notifications.notification_event_id
            LEFT JOIN users AS actors
              ON actors.user_id = notification_events.actor_user_id
            WHERE user_notifications.recipient_user_id = ?
              AND user_notifications.status = 'visible'
              AND user_notifications.deleted_at IS NULL
        """
        params: list[object] = [user_id]
        if category:
            query += " AND notification_events.category = ?"
            params.append(category)
        if unread_only:
            query += " AND user_notifications.read_at IS NULL"
        query += " ORDER BY user_notifications.created_at DESC LIMIT ? OFFSET ?;"
        params.extend([page_size, offset])
        rows = connection.execute(query, tuple(params)).fetchall()
        unread_count = connection.execute(
            """
            SELECT count(*)
            FROM user_notifications
            WHERE recipient_user_id = ?
              AND status = 'visible'
              AND read_at IS NULL
              AND deleted_at IS NULL;
            """,
            (user_id,),
        ).fetchone()[0]

    return NotificationListResponse(
        items=[_notification_record(connection, row) for row in rows],
        page=page,
        page_size=page_size,
        unread_count=int(unread_count),
    )


def mark_notification_read(user_id: str, user_notification_id: str) -> bool:
    with transaction() as connection:
        _ensure_active_user(connection, user_id)
        row = connection.execute(
            """
            SELECT *
            FROM user_notifications
            WHERE user_notification_id = ?
              AND recipient_user_id = ?
              AND status = 'visible'
              AND deleted_at IS NULL
            LIMIT 1;
            """,
            (user_notification_id, user_id),
        ).fetchone()
        if row is None:
            raise_api_error(status.HTTP_404_NOT_FOUND, "NOTIFICATION_NOT_FOUND", "Notification was not found.")
        if row["read_at"] is None:
            connection.execute(
                """
                UPDATE user_notifications
                SET read_at = CURRENT_TIMESTAMP,
                    seen_at = COALESCE(seen_at, CURRENT_TIMESTAMP)
                WHERE user_notification_id = ?;
                """,
                (user_notification_id,),
            )
            _increment_notification_counter(connection, user_id, -1)
    return True


def mark_all_notifications_read(user_id: str) -> int:
    with transaction() as connection:
        _ensure_active_user(connection, user_id)
        result = connection.execute(
            """
            UPDATE user_notifications
            SET read_at = CURRENT_TIMESTAMP,
                seen_at = COALESCE(seen_at, CURRENT_TIMESTAMP)
            WHERE recipient_user_id = ?
              AND status = 'visible'
              AND read_at IS NULL
              AND deleted_at IS NULL;
            """,
            (user_id,),
        )
        count = result.rowcount
        if count:
            _increment_notification_counter(connection, user_id, -count)
    return count
