from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import status

from backend.app.auth.service import raise_api_error
from backend.app.core.database import get_connection, transaction
from backend.app.core.time import to_iso, utc_now, utc_now_iso
from backend.app.messages.schemas import (
    ChatConversationRecord,
    ChatMessageRecord,
    ConversationCreateResponse,
    ConversationListItem,
    ConversationListResponse,
    ConversationMessageSearchResponse,
    ConversationMemberRecord,
    ConversationHideResponse,
    ConversationMuteResponse,
    ConversationPinResponse,
    DirectConversationInteractionState,
    DirectConversationCreate,
    GroupConversationCreate,
    MessagingPushDisplay,
    MessagingPushDeliveryDecision,
    MessagingPushIntent,
    MarkReadResponse,
    MessageAttachmentRecord,
    MessageCreate,
    MessageListResponse,
    MessageReconcileRequest,
    MessageReconcileResponse,
    MessageRequestActionResponse,
    MessageRequestCreate,
    MessageRequestListResponse,
    MessageRequestRecord,
    MessageReplyPreview,
    MessageSendResponse,
    MessageUserSummary,
    MarkReadRequest,
    NotificationEventRecord,
    NotificationPreferenceKind,
    NotificationPreferencePatch,
    NotificationPreferences,
    NotificationTarget,
    NotificationTargetType,
    NotificationListResponse,
    UserNotificationRecord,
    UnreadCountsResponse,
)


NOTIFICATION_PREFERENCE_FIELDS = (
    "direct_message_notifications",
    "message_request_notifications",
    "like_comment_notifications",
    "follow_notifications",
    "course_notifications",
    "ai_analysis_notifications",
)
PREFERENCE_KIND_FIELD: dict[NotificationPreferenceKind, str] = {
    "direct_message": "direct_message_notifications",
    "message_request": "message_request_notifications",
    "like_comment": "like_comment_notifications",
    "follow": "follow_notifications",
    "course": "course_notifications",
    "ai_analysis": "ai_analysis_notifications",
}
NOTIFICATION_TYPE_PREFERENCE_KIND: dict[str, NotificationPreferenceKind] = {
    "follow": "follow",
    "post_like": "like_comment",
    "post_comment": "like_comment",
    "comment_reply": "like_comment",
    "message_request": "message_request",
    "lesson_created": "course",
    "lesson_updated": "course",
    "ai_analysis_completed": "ai_analysis",
}


def _row_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {key: row[key] for key in row.keys()}


def _json_text(value: dict[str, Any] | None) -> str | None:
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def notification_preference_kind(notification_type: str) -> NotificationPreferenceKind | None:
    """Map normalized notification semantics to a Push preference, if product-defined."""
    return NOTIFICATION_TYPE_PREFERENCE_KIND.get(notification_type)


def _notification_preferences_record(row: sqlite3.Row | None) -> NotificationPreferences:
    if row is None:
        return NotificationPreferences()
    return NotificationPreferences(
        **{field: bool(row[field]) for field in NOTIFICATION_PREFERENCE_FIELDS}
    )


def _notification_preferences_row(
    connection: sqlite3.Connection,
    user_id: str,
) -> sqlite3.Row | None:
    return connection.execute(
        """
        SELECT *
        FROM user_notification_preferences
        WHERE user_id = ?
        LIMIT 1;
        """,
        (user_id,),
    ).fetchone()


def get_notification_preferences(user_id: str) -> NotificationPreferences:
    with get_connection() as connection:
        _ensure_active_user(connection, user_id)
        row = _notification_preferences_row(connection, user_id)
    return _notification_preferences_record(row)


def update_notification_preferences(
    user_id: str,
    payload: NotificationPreferencePatch,
) -> NotificationPreferences:
    fields = payload.model_dump(exclude_unset=True)
    assignments: list[str] = []
    params: list[object] = []
    for field in NOTIFICATION_PREFERENCE_FIELDS:
        if field in fields:
            assignments.append(f"{field} = ?")
            params.append(1 if fields[field] else 0)

    with transaction() as connection:
        _ensure_active_user(connection, user_id)
        connection.execute(
            "INSERT OR IGNORE INTO user_notification_preferences (user_id) VALUES (?);",
            (user_id,),
        )
        params.append(user_id)
        connection.execute(
            f"""
            UPDATE user_notification_preferences
            SET {", ".join(assignments)}
            WHERE user_id = ?;
            """,
            tuple(params),
        )
        row = _notification_preferences_row(connection, user_id)
    return _notification_preferences_record(row)


def is_notification_preference_enabled(
    user_id: str,
    preference_kind: NotificationPreferenceKind,
) -> bool:
    preferences = get_notification_preferences(user_id)
    return bool(getattr(preferences, PREFERENCE_KIND_FIELD[preference_kind]))


def is_notification_push_allowed_by_preferences(user_id: str, notification_type: str) -> bool:
    """Unmapped semantics remain allowed until product defines a suppressing preference."""
    preference_kind = notification_preference_kind(notification_type)
    if preference_kind is None:
        return True
    return is_notification_preference_enabled(user_id, preference_kind)


def _push_preference_decision(
    user_id: str,
    preference_kind: NotificationPreferenceKind,
) -> MessagingPushDeliveryDecision:
    return (
        "eligible"
        if is_notification_preference_enabled(user_id, preference_kind)
        else "suppressed_by_preference"
    )


def build_direct_message_push_intent(
    recipient_user_id: str,
    message_id: str,
) -> MessagingPushIntent:
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT
                messages.message_id,
                messages.conversation_id,
                messages.sender_user_id,
                recipients.muted_until,
                senders.nickname AS sender_nickname
            FROM chat_messages AS messages
            JOIN chat_conversations AS conversations
              ON conversations.conversation_id = messages.conversation_id
            JOIN chat_conversation_members AS recipients
              ON recipients.conversation_id = conversations.conversation_id
             AND recipients.user_id = ?
             AND recipients.status = 'active'
             AND recipients.deleted_at IS NULL
            LEFT JOIN users AS senders
              ON senders.user_id = messages.sender_user_id
            WHERE messages.message_id = ?
              AND messages.status = 'sent'
              AND messages.deleted_at IS NULL
              AND conversations.conversation_type = 'direct'
              AND conversations.status = 'active'
              AND conversations.deleted_at IS NULL
              AND messages.sender_user_id IS NOT NULL
              AND messages.sender_user_id <> ?
            LIMIT 1;
            """,
            (recipient_user_id, message_id, recipient_user_id),
        ).fetchone()
    if row is None:
        return MessagingPushIntent(decision="unsupported")

    request = {
        "push_kind": "direct_message",
        "recipient_user_id": recipient_user_id,
        "delivery_id": f"direct_message:{row['message_id']}",
        "preference_kind": "direct_message",
        "notification_type": None,
        "target": {"type": "chat", "conversation_id": row["conversation_id"]},
        "display": MessagingPushDisplay(title=row["sender_nickname"], body=None),
        "data": {
            "type": "direct_message",
            "message_id": row["message_id"],
            "sender_user_id": row["sender_user_id"],
        },
    }
    preference_decision = _push_preference_decision(recipient_user_id, "direct_message")
    if preference_decision == "suppressed_by_preference":
        return MessagingPushIntent(decision=preference_decision, request=request)
    if _is_conversation_muted(row["muted_until"]):
        return MessagingPushIntent(decision="suppressed_by_conversation_mute", request=request)
    return MessagingPushIntent(decision=preference_decision, request=request)


def build_message_request_push_intent(
    recipient_user_id: str,
    message_request_id: str,
) -> MessagingPushIntent:
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT
                requests.message_request_id,
                requests.requester_user_id,
                requesters.nickname AS requester_nickname
            FROM chat_message_requests AS requests
            LEFT JOIN users AS requesters
              ON requesters.user_id = requests.requester_user_id
            WHERE requests.message_request_id = ?
              AND requests.recipient_user_id = ?
              AND requests.status = 'pending'
            LIMIT 1;
            """,
            (message_request_id, recipient_user_id),
        ).fetchone()
    if row is None:
        return MessagingPushIntent(decision="unsupported")

    request = {
        "push_kind": "message_request",
        "recipient_user_id": recipient_user_id,
        "delivery_id": f"message_request:{row['message_request_id']}",
        "preference_kind": "message_request",
        "notification_type": "message_request",
        "target": {"type": "message_request", "request_id": row["message_request_id"]},
        "display": MessagingPushDisplay(title=row["requester_nickname"], body=None),
        "data": {
            "type": "message_request",
            "request_id": row["message_request_id"],
            "requester_user_id": row["requester_user_id"],
        },
    }
    return MessagingPushIntent(
        decision=_push_preference_decision(recipient_user_id, "message_request"),
        request=request,
    )


EXPECTED_NOTIFICATION_PUSH_TARGETS: dict[str, NotificationTargetType] = {
    "follow": "user_profile",
    "post_like": "post_detail",
    "post_comment": "post_comments",
    "comment_reply": "post_comments",
    "ai_analysis_completed": "activity_detail",
}


def build_notification_event_push_intent(
    recipient_user_id: str,
    notification_event_id: str,
) -> MessagingPushIntent:
    message_request_id = _message_request_id_sql("events")
    with get_connection() as connection:
        row = connection.execute(
            f"""
            SELECT
                events.*,
                events.created_at AS event_created_at,
                ({message_request_id}) AS message_request_id
            FROM notification_events AS events
            JOIN user_notifications AS notifications
              ON notifications.notification_event_id = events.notification_event_id
             AND notifications.recipient_user_id = ?
             AND notifications.status = 'visible'
             AND notifications.deleted_at IS NULL
            WHERE events.notification_event_id = ?
            LIMIT 1;
            """,
            (recipient_user_id, notification_event_id),
        ).fetchone()
    if row is None:
        return MessagingPushIntent(decision="unsupported")
    if row["message_request_id"]:
        return build_message_request_push_intent(recipient_user_id, row["message_request_id"])

    notification_type = row["event_type"]
    preference_kind = notification_preference_kind(notification_type)
    target = _notification_target(row, notification_type)
    request = {
        "push_kind": "notification_event",
        "recipient_user_id": recipient_user_id,
        "delivery_id": f"notification_event:{row['notification_event_id']}",
        "preference_kind": preference_kind,
        "notification_type": notification_type,
        "target": target,
        "display": MessagingPushDisplay(title=row["title"], body=row["body"]),
        "data": {
            "type": "notification_event",
            "notification_event_id": row["notification_event_id"],
            "actor_user_id": row["actor_user_id"],
        },
    }

    if preference_kind is None:
        decision: MessagingPushDeliveryDecision = "eligible_without_preference_mapping"
    elif not is_notification_preference_enabled(recipient_user_id, preference_kind):
        decision = "suppressed_by_preference"
    elif notification_type in {"lesson_created", "lesson_updated"}:
        decision = "unsupported"
    elif target["type"] != EXPECTED_NOTIFICATION_PUSH_TARGETS.get(notification_type):
        decision = "invalid_target"
    else:
        decision = "eligible"
    return MessagingPushIntent(decision=decision, request=request)


def _message_request_notification_exists_sql(event_alias: str) -> str:
    """Return the shared legacy-compatible Message Request event predicate."""
    return f"({_message_request_id_sql(event_alias)}) IS NOT NULL"


def _message_request_id_sql(event_alias: str) -> str:
    return f"""
        SELECT request_semantics.message_request_id
        FROM chat_message_requests AS request_semantics
        WHERE {event_alias}.dedup_key = 'message_request:' || request_semantics.message_request_id
        LIMIT 1
    """


def _notification_target(row: sqlite3.Row, notification_type: str) -> NotificationTarget:
    def identifier(column: str) -> str | None:
        value = row[column]
        if not isinstance(value, str):
            return None
        normalized = value.strip()
        return normalized or None

    object_type = identifier("object_type")
    object_id = identifier("object_id")
    context_type = identifier("context_type")
    context_id = identifier("context_id")

    if notification_type == "follow" and object_type == "user" and object_id:
        return {"type": "user_profile", "user_id": object_id}
    if notification_type == "post_like" and object_type == "social_post" and object_id:
        return {"type": "post_detail", "post_id": object_id}
    if notification_type in {"post_comment", "comment_reply"}:
        post_id = context_id if context_type == "social_post" else object_id if object_type == "social_post" else None
        if post_id:
            return {"type": "post_comments", "post_id": post_id}
    if notification_type == "message_request":
        return {"type": "message_request", "request_id": identifier("message_request_id")}
    if notification_type == "ai_analysis_completed":
        activity_id = (
            object_id
            if object_type == "tennis_activity"
            else context_id
            if context_type == "tennis_activity"
            else None
        )
        if activity_id:
            return {"type": "activity_detail", "activity_id": activity_id}
    if notification_type == "coach_application_reviewed":
        return {"type": "coach_identity"}

    # Lesson detail has no App route yet; unsupported or incomplete metadata stays non-actionable.
    return {"type": "none"}


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


def _direct_interaction_state(
    connection: sqlite3.Connection,
    user_id: str,
    target_user_id: str,
) -> DirectConversationInteractionState:
    block_rows = connection.execute(
        """
        SELECT blocker_user_id
        FROM user_blocks
        WHERE deleted_at IS NULL
          AND (
              (blocker_user_id = ? AND blocked_user_id = ?)
              OR (blocker_user_id = ? AND blocked_user_id = ?)
          );
        """,
        (user_id, target_user_id, target_user_id, user_id),
    ).fetchall()
    return DirectConversationInteractionState(
        can_send=not block_rows,
        blocked_by_current_user=any(row["blocker_user_id"] == user_id for row in block_rows),
    )


def _ensure_not_blocked(
    connection: sqlite3.Connection,
    user_id: str,
    target_user_id: str,
) -> None:
    if not _direct_interaction_state(connection, user_id, target_user_id).can_send:
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
        is_muted=_is_conversation_muted(row["muted_until"]),
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


def _other_members_by_conversation(
    connection: sqlite3.Connection,
    conversation_ids: list[str],
    current_user_id: str,
) -> dict[str, list[MessageUserSummary]]:
    """Load visible participant summaries for a page of conversations in one query."""
    if not conversation_ids:
        return {}
    placeholders = ", ".join("?" for _ in conversation_ids)
    rows = connection.execute(
        f"""
        SELECT
            chat_conversation_members.conversation_id,
            users.user_id,
            users.nickname,
            users.avatar_path,
            users.is_coach,
            users.coach_status
        FROM chat_conversation_members
        JOIN users ON users.user_id = chat_conversation_members.user_id
        WHERE chat_conversation_members.conversation_id IN ({placeholders})
          AND chat_conversation_members.user_id <> ?
          AND chat_conversation_members.status = 'active'
          AND chat_conversation_members.deleted_at IS NULL
          AND users.status = 'active'
          AND users.deleted_at IS NULL
        ORDER BY
            chat_conversation_members.conversation_id ASC,
            chat_conversation_members.joined_at ASC,
            users.user_id ASC;
        """,
        (*conversation_ids, current_user_id),
    ).fetchall()
    members_by_conversation: dict[str, list[MessageUserSummary]] = {
        conversation_id: [] for conversation_id in conversation_ids
    }
    for row in rows:
        members_by_conversation[row["conversation_id"]].append(_user_summary(row))
    return members_by_conversation


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

    with transaction(immediate=True) as connection:
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
    with transaction(immediate=True) as connection:
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
                CASE WHEN members.pinned_at IS NULL THEN 1 ELSE 0 END,
                CASE WHEN conversations.last_message_at IS NULL THEN 1 ELSE 0 END,
                conversations.last_message_at DESC,
                conversations.created_at DESC
            LIMIT ? OFFSET ?;
            """,
            (user_id, page_size, offset),
        ).fetchall()
        other_members_by_conversation = _other_members_by_conversation(
            connection,
            [row["conversation_id"] for row in rows],
            user_id,
        )

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
            "is_muted": _is_conversation_muted(row["muted_until"]),
            "pinned_at": row["pinned_at"],
            "archived_at": row["archived_at"],
        }
        other_members = other_members_by_conversation.get(row["conversation_id"], [])
        items.append(
            ConversationListItem(
                conversation=_conversation_record(row),
                member=ConversationMemberRecord(**member_row),
                other_members=other_members,
            )
        )
    return ConversationListResponse(items=items, page=page, page_size=page_size)


def search_conversations(
    user_id: str,
    query: str,
    page: int,
    page_size: int,
) -> ConversationListResponse:
    """Search the caller's visible conversations without changing membership state."""
    normalized_query = query.strip()
    if not normalized_query:
        raise_api_error(
            status.HTTP_400_BAD_REQUEST,
            "CONVERSATION_SEARCH_QUERY_REQUIRED",
            "Search query cannot be empty.",
        )
    if len(normalized_query) > 100:
        raise_api_error(
            status.HTTP_400_BAD_REQUEST,
            "CONVERSATION_SEARCH_QUERY_TOO_LONG",
            "Search query must be at most 100 characters.",
        )

    offset = (page - 1) * page_size
    pattern = f"%{_escape_like(normalized_query)}%"
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
              AND (
                    (
                        conversations.conversation_type = 'group'
                        AND conversations.title LIKE ? ESCAPE '\\'
                    )
                    OR (
                        conversations.conversation_type = 'direct'
                        AND EXISTS (
                            SELECT 1
                            FROM chat_conversation_members AS other_members
                            JOIN users AS other_users
                              ON other_users.user_id = other_members.user_id
                            WHERE other_members.conversation_id = conversations.conversation_id
                              AND other_members.user_id <> ?
                              AND other_members.status = 'active'
                              AND other_members.deleted_at IS NULL
                              AND other_users.status = 'active'
                              AND other_users.deleted_at IS NULL
                              AND other_users.nickname LIKE ? ESCAPE '\\'
                        )
                    )
              )
            ORDER BY
                CASE WHEN members.pinned_at IS NULL THEN 1 ELSE 0 END,
                CASE WHEN conversations.last_message_at IS NULL THEN 1 ELSE 0 END,
                conversations.last_message_at DESC,
                conversations.created_at DESC
            LIMIT ? OFFSET ?;
            """,
            (user_id, pattern, user_id, pattern, page_size, offset),
        ).fetchall()
        other_members_by_conversation = _other_members_by_conversation(
            connection,
            [row["conversation_id"] for row in rows],
            user_id,
        )

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
            "is_muted": _is_conversation_muted(row["muted_until"]),
            "pinned_at": row["pinned_at"],
            "archived_at": row["archived_at"],
        }
        other_members = other_members_by_conversation.get(row["conversation_id"], [])
        items.append(
            ConversationListItem(
                conversation=_conversation_record(row),
                member=ConversationMemberRecord(**member_row),
                other_members=other_members,
            )
        )
    return ConversationListResponse(items=items, page=page, page_size=page_size)


def set_conversation_pin(
    user_id: str,
    conversation_id: str,
    pinned: bool,
) -> ConversationPinResponse:
    with transaction(immediate=True) as connection:
        _ensure_active_user(connection, user_id)
        member = _select_member(connection, conversation_id, user_id)
        pinned_at = member["pinned_at"]
        if pinned and pinned_at is None:
            pinned_at = utc_now_iso()
            connection.execute(
                """
                UPDATE chat_conversation_members
                SET pinned_at = ?
                WHERE conversation_member_id = ?;
                """,
                (pinned_at, member["conversation_member_id"]),
            )
        elif not pinned and pinned_at is not None:
            pinned_at = None
            connection.execute(
                """
                UPDATE chat_conversation_members
                SET pinned_at = NULL
                WHERE conversation_member_id = ?;
                """,
                (member["conversation_member_id"],),
            )
    return ConversationPinResponse(
        success=True,
        conversation_id=conversation_id,
        pinned_at=pinned_at,
    )


def set_conversation_mute(
    user_id: str,
    conversation_id: str,
    muted: bool,
) -> ConversationMuteResponse:
    """Mute only the caller's active membership for the fixed 24-hour product period."""
    with transaction(immediate=True) as connection:
        _ensure_active_user(connection, user_id)
        member = _select_member(connection, conversation_id, user_id)
        muted_until = member["muted_until"]
        if muted and not _is_conversation_muted(muted_until):
            muted_until = to_iso(utc_now() + timedelta(hours=24))
            connection.execute(
                """
                UPDATE chat_conversation_members
                SET muted_until = ?
                WHERE conversation_member_id = ?;
                """,
                (muted_until, member["conversation_member_id"]),
            )
        elif not muted and muted_until is not None:
            muted_until = None
            connection.execute(
                """
                UPDATE chat_conversation_members
                SET muted_until = NULL
                WHERE conversation_member_id = ?;
                """,
                (member["conversation_member_id"],),
            )
    return ConversationMuteResponse(
        success=True,
        conversation_id=conversation_id,
        muted_until=muted_until,
        is_muted=_is_conversation_muted(muted_until),
    )


def set_conversation_hidden(
    user_id: str,
    conversation_id: str,
    hidden: bool,
) -> ConversationHideResponse:
    """Hide only the caller's membership without changing message state or preferences."""
    with transaction(immediate=True) as connection:
        _ensure_active_user(connection, user_id)
        member = _select_member(connection, conversation_id, user_id)
        archived_at = member["archived_at"]
        if hidden and archived_at is None:
            archived_at = utc_now_iso()
            connection.execute(
                """
                UPDATE chat_conversation_members
                SET archived_at = ?
                WHERE conversation_member_id = ?;
                """,
                (archived_at, member["conversation_member_id"]),
            )
        elif not hidden and archived_at is not None:
            archived_at = None
            connection.execute(
                """
                UPDATE chat_conversation_members
                SET archived_at = NULL
                WHERE conversation_member_id = ?;
                """,
                (member["conversation_member_id"],),
            )
    return ConversationHideResponse(
        success=True,
        conversation_id=conversation_id,
        archived_at=archived_at,
        is_hidden=archived_at is not None,
    )


def _is_conversation_muted(muted_until: str | None, now: datetime | None = None) -> bool:
    """Return the server-authoritative effective state for a membership mute."""
    if muted_until is None:
        return False
    try:
        expires_at = datetime.fromisoformat(muted_until.replace("Z", "+00:00"))
    except ValueError:
        return False
    return expires_at > (now or utc_now())


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

    is_revoked = row["status"] == "revoked"
    attachments = [] if is_revoked else connection.execute(
        """
        SELECT *
        FROM chat_message_attachments
        WHERE message_id = ?
        ORDER BY sort_order ASC, attachment_id ASC;
        """,
        (row["message_id"],),
    ).fetchall()
    reply_preview = None
    if row["reply_to_message_id"] and not is_revoked:
        reply_row = connection.execute(
            """
            SELECT message_id, message_seq, sender_user_id, text_content, status, deleted_at
            FROM chat_messages
            WHERE message_id = ?
              AND conversation_id = ?
            LIMIT 1;
            """,
            (row["reply_to_message_id"], row["conversation_id"]),
        ).fetchone()
        if reply_row is None or reply_row["deleted_at"] is not None or reply_row["status"] != "sent":
            reply_preview = MessageReplyPreview(
                state="unavailable",
                message_id=row["reply_to_message_id"],
            )
        else:
            reply_sender = _request_user_summary(connection, reply_row["sender_user_id"]) if reply_row["sender_user_id"] else None
            reply_preview = MessageReplyPreview(
                state="available",
                message_id=reply_row["message_id"],
                message_seq=reply_row["message_seq"],
                sender_user_id=reply_row["sender_user_id"],
                sender_nickname=reply_sender.nickname if reply_sender else None,
                text_content=(reply_row["text_content"] or "")[:500] or None,
            )
    return ChatMessageRecord(
        message_id=row["message_id"],
        conversation_id=row["conversation_id"],
        message_seq=row["message_seq"],
        sender_user_id=row["sender_user_id"],
        sender_type=row["sender_type"],
        message_type=row["message_type"],
        text_content=None if is_revoked else row["text_content"],
        payload_json=None if is_revoked else row["payload_json"],
        target_object_type=None if is_revoked else row["target_object_type"],
        target_object_id=None if is_revoked else row["target_object_id"],
        context_object_type=None if is_revoked else row["context_object_type"],
        context_object_id=None if is_revoked else row["context_object_id"],
        reply_to_message_id=row["reply_to_message_id"],
        reply_preview=reply_preview,
        client_message_id=row["client_message_id"],
        status=row["status"],
        sent_at=row["sent_at"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        deleted_at=row["deleted_at"],
        sender=sender,
        attachments=[MessageAttachmentRecord(**_row_dict(item)) for item in attachments],
    )


def _message_records(connection: sqlite3.Connection, rows: list[sqlite3.Row]) -> list[ChatMessageRecord]:
    """Hydrate a message page with bounded batch queries while preserving serialization semantics."""
    if not rows:
        return []

    sender_ids = {row["sender_user_id"] for row in rows if row["sender_user_id"]}
    reply_ids = {
        row["reply_to_message_id"]
        for row in rows
        if row["reply_to_message_id"] and row["status"] != "revoked"
    }
    message_ids = {row["message_id"] for row in rows if row["status"] != "revoked"}

    attachments_by_message: dict[str, list[sqlite3.Row]] = {message_id: [] for message_id in message_ids}
    if message_ids:
        placeholders = ", ".join("?" for _ in message_ids)
        attachment_rows = connection.execute(
            f"""
            SELECT *
            FROM chat_message_attachments
            WHERE message_id IN ({placeholders})
            ORDER BY message_id ASC, sort_order ASC, attachment_id ASC;
            """,
            tuple(message_ids),
        ).fetchall()
        for attachment in attachment_rows:
            attachments_by_message.setdefault(attachment["message_id"], []).append(attachment)

    replies_by_id: dict[str, sqlite3.Row] = {}
    if reply_ids:
        placeholders = ", ".join("?" for _ in reply_ids)
        reply_rows = connection.execute(
            f"""
            SELECT message_id, conversation_id, message_seq, sender_user_id, text_content, status, deleted_at
            FROM chat_messages
            WHERE message_id IN ({placeholders});
            """,
            tuple(reply_ids),
        ).fetchall()
        replies_by_id = {row["message_id"]: row for row in reply_rows}

    user_ids = sender_ids | {
        row["sender_user_id"]
        for row in replies_by_id.values()
        if row["sender_user_id"]
    }
    user_rows: list[sqlite3.Row] = []
    if user_ids:
        placeholders = ", ".join("?" for _ in user_ids)
        user_rows = connection.execute(
            f"""
            SELECT user_id, nickname, avatar_path, is_coach, coach_status
            FROM users
            WHERE user_id IN ({placeholders});
            """,
            tuple(user_ids),
        ).fetchall()
    users_by_id = {row["user_id"]: _user_summary(row) for row in user_rows}

    records: list[ChatMessageRecord] = []
    for row in rows:
        is_revoked = row["status"] == "revoked"
        reply_preview = None
        reply_id = row["reply_to_message_id"]
        if reply_id and not is_revoked:
            reply_row = replies_by_id.get(reply_id)
            if (
                reply_row is None
                or reply_row["conversation_id"] != row["conversation_id"]
                or reply_row["deleted_at"] is not None
                or reply_row["status"] != "sent"
            ):
                reply_preview = MessageReplyPreview(state="unavailable", message_id=reply_id)
            else:
                reply_sender = users_by_id.get(reply_row["sender_user_id"])
                reply_preview = MessageReplyPreview(
                    state="available",
                    message_id=reply_row["message_id"],
                    message_seq=reply_row["message_seq"],
                    sender_user_id=reply_row["sender_user_id"],
                    sender_nickname=reply_sender.nickname if reply_sender else None,
                    text_content=(reply_row["text_content"] or "")[:500] or None,
                )
        records.append(
            ChatMessageRecord(
                message_id=row["message_id"],
                conversation_id=row["conversation_id"],
                message_seq=row["message_seq"],
                sender_user_id=row["sender_user_id"],
                sender_type=row["sender_type"],
                message_type=row["message_type"],
                text_content=None if is_revoked else row["text_content"],
                payload_json=None if is_revoked else row["payload_json"],
                target_object_type=None if is_revoked else row["target_object_type"],
                target_object_id=None if is_revoked else row["target_object_id"],
                context_object_type=None if is_revoked else row["context_object_type"],
                context_object_id=None if is_revoked else row["context_object_id"],
                reply_to_message_id=reply_id,
                reply_preview=reply_preview,
                client_message_id=row["client_message_id"],
                status=row["status"],
                sent_at=row["sent_at"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
                deleted_at=row["deleted_at"],
                sender=users_by_id.get(row["sender_user_id"]),
                attachments=[]
                if is_revoked
                else [MessageAttachmentRecord(**_row_dict(item)) for item in attachments_by_message.get(row["message_id"], [])],
            )
        )
    return records


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

    # Only a real new message restores hidden memberships; idempotent retries return above.
    connection.execute(
        """
        UPDATE chat_conversation_members
        SET archived_at = NULL
        WHERE conversation_id = ?
          AND status = 'active'
          AND deleted_at IS NULL
          AND archived_at IS NOT NULL;
        """,
        (conversation_id,),
    )

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
        if reply["deleted_at"] is not None or reply["status"] != "sent":
            raise_api_error(
                status.HTTP_400_BAD_REQUEST,
                "REPLY_MESSAGE_UNAVAILABLE",
                "The reply target is unavailable.",
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
    with transaction(immediate=True) as connection:
        return send_message_in_transaction(connection, user_id, conversation_id, payload)


def recall_message(user_id: str, conversation_id: str, message_id: str) -> MessageSendResponse:
    """Recall one owned Direct text message without changing message ordering or unread state."""
    with transaction(immediate=True) as connection:
        _ensure_active_user(connection, user_id)
        conversation = _select_conversation(connection, conversation_id)
        _select_member(connection, conversation_id, user_id)
        row = connection.execute(
            """
            SELECT *
            FROM chat_messages
            WHERE message_id = ?
              AND conversation_id = ?
            LIMIT 1;
            """,
            (message_id, conversation_id),
        ).fetchone()
        if row is None:
            raise_api_error(status.HTTP_404_NOT_FOUND, "MESSAGE_NOT_FOUND", "Message was not found.")
        if conversation["conversation_type"] != "direct":
            raise_api_error(
                status.HTTP_400_BAD_REQUEST,
                "RECALL_DIRECT_ONLY",
                "Only Direct text messages can be recalled.",
            )
        if row["sender_user_id"] != user_id:
            raise_api_error(
                status.HTTP_403_FORBIDDEN,
                "MESSAGE_RECALL_NOT_ALLOWED",
                "Only the original sender can recall this message.",
            )
        if row["message_type"] != "text":
            raise_api_error(
                status.HTTP_400_BAD_REQUEST,
                "RECALL_TEXT_ONLY",
                "Only text messages can be recalled.",
            )
        if row["status"] == "deleted" or row["deleted_at"] is not None:
            raise_api_error(
                status.HTTP_409_CONFLICT,
                "MESSAGE_RECALL_TERMINAL",
                "This message cannot be recalled.",
            )
        if row["status"] == "sent":
            connection.execute(
                """
                UPDATE chat_messages
                SET status = 'revoked'
                WHERE message_id = ?
                  AND status = 'sent';
                """,
                (message_id,),
            )
            if conversation["last_message_id"] == message_id:
                connection.execute(
                    """
                    UPDATE chat_conversations
                    SET last_message_preview = '[消息已撤回]'
                    WHERE conversation_id = ?
                      AND last_message_id = ?;
                    """,
                    (conversation_id, message_id),
                )
        return MessageSendResponse(message=_message_record(connection, _select_message(connection, message_id)))


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


def _message_request_cooldown_active(
    connection: sqlite3.Connection,
    requester_user_id: str,
    recipient_user_id: str,
    now: datetime | None = None,
) -> bool:
    rows = connection.execute(
        """
        SELECT message_request_id, responded_at
        FROM chat_message_requests
        WHERE requester_user_id = ?
          AND recipient_user_id = ?
          AND status = 'declined'
          AND responded_at IS NOT NULL
        ORDER BY responded_at DESC, message_request_id DESC;
        """,
        (requester_user_id, recipient_user_id),
    ).fetchall()
    current_time = now or utc_now()
    latest_declined_at: datetime | None = None
    for row in rows:
        try:
            declined_at = datetime.fromisoformat(row["responded_at"].replace("Z", "+00:00"))
        except (AttributeError, TypeError, ValueError):
            continue
        if declined_at.tzinfo is None:
            declined_at = declined_at.replace(tzinfo=timezone.utc)
        declined_at = declined_at.astimezone(timezone.utc)
        if latest_declined_at is None or declined_at > latest_declined_at:
            latest_declined_at = declined_at
    return bool(latest_declined_at and latest_declined_at + timedelta(hours=24) > current_time)


def create_message_request(user_id: str, payload: MessageRequestCreate) -> MessageRequestActionResponse:
    target_user_id = (payload.target_user_id or "").strip()
    if not target_user_id:
        raise_api_error(status.HTTP_400_BAD_REQUEST, "TARGET_USER_REQUIRED", "Target user is required.")
    if user_id == target_user_id:
        raise_api_error(status.HTTP_400_BAD_REQUEST, "CANNOT_MESSAGE_SELF", "You cannot message yourself.")

    with transaction(immediate=True) as connection:
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
        if existing_request is None and _message_request_cooldown_active(connection, user_id, target_user_id):
            raise_api_error(
                status.HTTP_429_TOO_MANY_REQUESTS,
                "MESSAGE_REQUEST_COOLDOWN_ACTIVE",
                "You cannot send another message request to this user for 24 hours after a decline.",
            )
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
                payload={
                    "message_request_id": message_request_id,
                    "notification_type": "message_request",
                },
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
    with transaction(immediate=True) as connection:
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
    with transaction(immediate=True) as connection:
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
        conversation = _select_conversation(connection, conversation_id)
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
        messages = _message_records(connection, ordered_rows)
        next_before_seq = rows[-1]["message_seq"] if len(rows) == page_size else None
        other_member_last_read_message_seq = None
        direct_interaction_state = None
        if conversation["conversation_type"] == "direct":
            other_member = connection.execute(
                """
                SELECT user_id, last_read_message_seq
                FROM chat_conversation_members
                WHERE conversation_id = ?
                  AND user_id <> ?
                  AND status = 'active'
                  AND deleted_at IS NULL
                LIMIT 1;
                """,
                (conversation_id, user_id),
            ).fetchone()
            if other_member is not None:
                other_member_last_read_message_seq = int(other_member["last_read_message_seq"])
                direct_interaction_state = _direct_interaction_state(
                    connection,
                    user_id,
                    other_member["user_id"],
                )
            else:
                direct_interaction_state = DirectConversationInteractionState(
                    can_send=False,
                    blocked_by_current_user=False,
                )
    return MessageListResponse(
        items=messages,
        conversation_id=conversation_id,
        next_before_seq=next_before_seq,
        other_member_last_read_message_seq=other_member_last_read_message_seq,
        direct_interaction_state=direct_interaction_state,
    )


def reconcile_messages(
    user_id: str,
    conversation_id: str,
    payload: MessageReconcileRequest,
) -> MessageReconcileResponse:
    """Return authoritative records for already-loaded IDs without read side effects."""
    message_ids = list(dict.fromkeys(payload.message_ids))
    if not message_ids:
        return MessageReconcileResponse(conversation_id=conversation_id, items=[])
    with get_connection() as connection:
        _ensure_active_user(connection, user_id)
        _select_conversation(connection, conversation_id)
        _select_member(connection, conversation_id, user_id)
        placeholders = ", ".join("?" for _ in message_ids)
        rows = connection.execute(
            f"""
            SELECT *
            FROM chat_messages
            WHERE conversation_id = ?
              AND message_id IN ({placeholders})
              AND deleted_at IS NULL
            ORDER BY message_seq ASC;
            """,
            (conversation_id, *message_ids),
        ).fetchall()
        items = _message_records(connection, rows)
    return MessageReconcileResponse(conversation_id=conversation_id, items=items)


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def search_conversation_messages(
    user_id: str,
    conversation_id: str,
    query: str,
    page_size: int,
    before_seq: int | None,
) -> ConversationMessageSearchResponse:
    """Search persisted text messages in one authorized conversation without read side effects."""
    normalized_query = query.strip()
    if not normalized_query:
        raise_api_error(
            status.HTTP_400_BAD_REQUEST,
            "MESSAGE_SEARCH_QUERY_REQUIRED",
            "Search query cannot be empty.",
        )
    if len(normalized_query) > 100:
        raise_api_error(
            status.HTTP_400_BAD_REQUEST,
            "MESSAGE_SEARCH_QUERY_TOO_LONG",
            "Search query must be at most 100 characters.",
        )

    with get_connection() as connection:
        _ensure_active_user(connection, user_id)
        _select_conversation(connection, conversation_id)
        _select_member(connection, conversation_id, user_id)
        sql = """
            SELECT *
            FROM chat_messages
            WHERE conversation_id = ?
              AND message_type = 'text'
              AND status = 'sent'
              AND text_content LIKE ? ESCAPE '\\'
              AND deleted_at IS NULL
        """
        params: list[object] = [conversation_id, f"%{_escape_like(normalized_query)}%"]
        if before_seq is not None:
            sql += " AND message_seq < ?"
            params.append(before_seq)
        sql += " ORDER BY message_seq DESC LIMIT ?;"
        params.append(page_size)
        rows = connection.execute(sql, tuple(params)).fetchall()
        items = _message_records(connection, rows)

    return ConversationMessageSearchResponse(
        conversation_id=conversation_id,
        items=items,
        next_before_seq=rows[-1]["message_seq"] if len(rows) == page_size else None,
    )


def mark_conversation_read(
    user_id: str,
    conversation_id: str,
    payload: MarkReadRequest | None = None,
) -> MarkReadResponse:
    with transaction(immediate=True) as connection:
        _ensure_active_user(connection, user_id)
        conversation = _select_conversation(connection, conversation_id)
        member = _select_member(connection, conversation_id, user_id)
        previous_unread = member["unread_count"]
        requested_seq = (
            conversation["last_message_seq"]
            if payload is None
            else min(payload.through_message_seq, conversation["last_message_seq"])
        )
        target_seq = max(member["last_read_message_seq"], requested_seq)
        target_message = None
        if target_seq > 0:
            target_message = connection.execute(
                """
                SELECT message_id
                FROM chat_messages
                WHERE conversation_id = ?
                  AND message_seq <= ?
                  AND deleted_at IS NULL
                ORDER BY message_seq DESC
                LIMIT 1;
                """,
                (conversation_id, target_seq),
            ).fetchone()
        newly_read = connection.execute(
            """
            SELECT COUNT(*) AS count
            FROM chat_messages
            WHERE conversation_id = ?
              AND message_seq > ?
              AND message_seq <= ?
              AND deleted_at IS NULL
              AND (sender_user_id IS NULL OR sender_user_id <> ?);
            """,
            (conversation_id, member["last_read_message_seq"], target_seq, user_id),
        ).fetchone()["count"]
        unread_count = max(0, int(previous_unread) - int(newly_read))
        connection.execute(
            """
            UPDATE chat_conversation_members
            SET last_read_message_id = ?,
                last_read_message_seq = ?,
                last_read_at = CURRENT_TIMESTAMP,
                unread_count = ?
            WHERE conversation_member_id = ?;
            """,
            (
                target_message["message_id"] if target_message is not None else member["last_read_message_id"],
                target_seq,
                unread_count,
                member["conversation_member_id"],
            ),
        )
        counter_delta = int(previous_unread) - unread_count
        if counter_delta:
            _increment_message_counter(
                connection,
                user_id,
                conversation["conversation_type"],
                -counter_delta,
            )
    return MarkReadResponse(
        success=True,
        conversation_id=conversation_id,
        unread_count=unread_count,
        last_read_message_seq=target_seq,
    )


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
        message_request_predicate = _message_request_notification_exists_sql("notification_events")
        unread_badge_notification = connection.execute(
            f"""
            SELECT count(*)
            FROM user_notifications
            JOIN notification_events
              ON notification_events.notification_event_id = user_notifications.notification_event_id
            WHERE recipient_user_id = ?
              AND status = 'visible'
              AND read_at IS NULL
              AND deleted_at IS NULL
              AND NOT ({message_request_predicate});
            """,
            (user_id,),
        ).fetchone()[0]
        pending_message_request_count = connection.execute(
            """
            SELECT count(*)
            FROM chat_message_requests
            WHERE recipient_user_id = ?
              AND status = 'pending';
            """,
            (user_id,),
        ).fetchone()[0]

    unread_direct = int(row["unread_direct"])
    unread_group = int(row["unread_group"])
    unread_notification = int(unread_notification)
    unread_badge_notification = int(unread_badge_notification)
    pending_message_request_count = int(pending_message_request_count)
    return UnreadCountsResponse(
        unread_direct_message_count=unread_direct,
        unread_group_message_count=unread_group,
        unread_notification_count=unread_notification,
        pending_message_request_count=pending_message_request_count,
        total_unread_count=unread_direct + unread_group + unread_notification,
        messages_tab_badge_count=unread_direct + unread_badge_notification + pending_message_request_count,
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
    is_message_request = bool(row["is_message_request"])
    notification_type = "message_request" if is_message_request else row["event_type"]
    product_category = (
        "request"
        if is_message_request
        else "interaction_follow"
        if row["category"] == "interaction"
        else "course_system"
    )
    event = NotificationEventRecord(
        notification_event_id=row["notification_event_id"],
        event_type=row["event_type"],
        notification_type=notification_type,
        category=row["category"],
        product_category=product_category,
        target=_notification_target(row, notification_type),
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
    product_category: str | None,
    unread_only: bool,
) -> NotificationListResponse:
    offset = (page - 1) * page_size
    with get_connection() as connection:
        _ensure_active_user(connection, user_id)
        message_request_predicate = _message_request_notification_exists_sql("notification_events")
        message_request_id = _message_request_id_sql("notification_events")
        query = f"""
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
                {message_request_predicate} AS is_message_request,
                ({message_request_id}) AS message_request_id,
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
        if product_category == "request":
            query += f" AND ({message_request_predicate})"
        elif product_category == "interaction_follow":
            query += f"""
                AND notification_events.category = 'interaction'
                AND NOT ({message_request_predicate})
            """
        elif product_category == "course_system":
            query += f"""
                AND notification_events.category IN ('system', 'ai', 'coach', 'lesson')
                AND NOT ({message_request_predicate})
            """
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
    with transaction(immediate=True) as connection:
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
    with transaction(immediate=True) as connection:
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
