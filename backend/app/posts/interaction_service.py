from __future__ import annotations

import json
import sqlite3
import uuid
from typing import Any

from fastapi import status

from backend.app.auth.service import raise_api_error
from backend.app.core.database import get_connection, transaction
from backend.app.core.time import utc_now_iso
from backend.app.messages import service as message_service
from backend.app.messages.schemas import MessageCreate
from backend.app.posts.schemas import (
    PostAuthor,
    PostCommentCreate,
    PostCommentCreateResponse,
    PostCommentDeleteResponse,
    PostCommentListResponse,
    PostCommentRecord,
    PostFavoriteResponse,
    PostInteractionCreate,
    PostLikeResponse,
    PostShareCreate,
    PostShareRecord,
    PostShareResponse,
    PostStatsRecord,
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
        SELECT user_id, nickname, avatar_path
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


def _has_block_relation(connection: sqlite3.Connection, user_id: str, target_user_id: str) -> bool:
    row = connection.execute(
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
    return row is not None


def _select_accessible_post(
    connection: sqlite3.Connection,
    social_post_id: str,
    user_id: str | None,
) -> sqlite3.Row:
    row = connection.execute(
        """
        SELECT
            social_posts.*,
            authors.nickname AS author_nickname,
            authors.avatar_path AS author_avatar_path
        FROM social_posts
        JOIN users AS authors ON authors.user_id = social_posts.author_user_id
        WHERE social_posts.social_post_id = ?
          AND social_posts.status = 'published'
          AND social_posts.review_status = 'approved'
          AND social_posts.deleted_at IS NULL
          AND authors.status = 'active'
          AND authors.deleted_at IS NULL
        LIMIT 1;
        """,
        (social_post_id,),
    ).fetchone()
    if row is None:
        raise_api_error(status.HTTP_404_NOT_FOUND, "POST_NOT_FOUND", "Post was not found.")

    author_user_id = row["author_user_id"]
    if user_id == author_user_id:
        return row
    if user_id is not None and _has_block_relation(connection, user_id, author_user_id):
        raise_api_error(status.HTTP_404_NOT_FOUND, "POST_NOT_FOUND", "Post was not found.")
    if row["visibility"] == "public":
        return row
    if user_id is None:
        raise_api_error(status.HTTP_404_NOT_FOUND, "POST_NOT_FOUND", "Post was not found.")
    if row["visibility"] == "followers" and _is_following(connection, user_id, author_user_id):
        return row
    if (
        row["visibility"] == "friends"
        and _is_following(connection, user_id, author_user_id)
        and _is_following(connection, author_user_id, user_id)
    ):
        return row
    raise_api_error(status.HTTP_404_NOT_FOUND, "POST_NOT_FOUND", "Post was not found.")


def _stats_record(connection: sqlite3.Connection, social_post_id: str) -> PostStatsRecord:
    connection.execute(
        "INSERT OR IGNORE INTO social_post_stats (social_post_id) VALUES (?);",
        (social_post_id,),
    )
    row = connection.execute(
        """
        SELECT *
        FROM social_post_stats
        WHERE social_post_id = ?
        LIMIT 1;
        """,
        (social_post_id,),
    ).fetchone()
    return PostStatsRecord(**_row_dict(row))


def _update_stat_count(connection: sqlite3.Connection, social_post_id: str, column: str, delta: int) -> PostStatsRecord:
    if column not in {"like_count", "favorite_count", "comment_count", "share_count"}:
        raise ValueError(f"Unsupported post stat column: {column}")
    connection.execute(
        "INSERT OR IGNORE INTO social_post_stats (social_post_id) VALUES (?);",
        (social_post_id,),
    )
    connection.execute(
        f"""
        UPDATE social_post_stats
        SET {column} = MAX(0, {column} + ?)
        WHERE social_post_id = ?;
        """,
        (delta, social_post_id),
    )
    return _stats_record(connection, social_post_id)


def _comment_author(row: sqlite3.Row) -> PostAuthor:
    return PostAuthor(
        user_id=row["author_user_id"],
        nickname=row["author_nickname"],
        avatar_path=row["author_avatar_path"],
    )


def _comment_record(connection: sqlite3.Connection, row: sqlite3.Row) -> PostCommentRecord:
    reply_count = connection.execute(
        """
        SELECT count(*)
        FROM post_comments
        WHERE parent_comment_id = ?
          AND status = 'active'
          AND deleted_at IS NULL;
        """,
        (row["comment_id"],),
    ).fetchone()[0]
    return PostCommentRecord(
        comment_id=row["comment_id"],
        social_post_id=row["social_post_id"],
        author_user_id=row["author_user_id"],
        parent_comment_id=row["parent_comment_id"],
        root_comment_id=row["root_comment_id"],
        content=row["content"],
        status=row["status"],
        source=row["source"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        deleted_at=row["deleted_at"],
        author=_comment_author(row),
        reply_count=int(reply_count),
    )


def _select_comment(
    connection: sqlite3.Connection,
    social_post_id: str,
    comment_id: str,
    *,
    active_only: bool = True,
) -> sqlite3.Row:
    query = """
        SELECT
            post_comments.*,
            users.nickname AS author_nickname,
            users.avatar_path AS author_avatar_path
        FROM post_comments
        JOIN users ON users.user_id = post_comments.author_user_id
        WHERE post_comments.social_post_id = ?
          AND post_comments.comment_id = ?
          AND post_comments.deleted_at IS NULL
    """
    params: list[object] = [social_post_id, comment_id]
    if active_only:
        query += " AND post_comments.status = 'active'"
    query += " LIMIT 1;"
    row = connection.execute(query, tuple(params)).fetchone()
    if row is None:
        raise_api_error(status.HTTP_404_NOT_FOUND, "COMMENT_NOT_FOUND", "Comment was not found.")
    return row


def _share_record(row: sqlite3.Row) -> PostShareRecord:
    return PostShareRecord(**_row_dict(row))


def _share_payloads_equal(stored_payload_json: str | None, requested_payload: dict[str, Any] | None) -> bool:
    """Compare payload values rather than JSON key ordering for idempotency."""
    try:
        stored = json.loads(stored_payload_json) if stored_payload_json is not None else None
    except (TypeError, ValueError):
        return False
    return stored == requested_payload


def _share_request_matches(
    connection: sqlite3.Connection,
    existing: sqlite3.Row,
    *,
    social_post_id: str,
    payload: PostShareCreate,
) -> bool:
    if (
        existing["social_post_id"] != social_post_id
        or existing["share_target_type"] != payload.share_target_type
        or existing["conversation_id"] != payload.conversation_id
        or existing["channel"] != payload.channel
        or existing["message_text"] != payload.message_text
        or not _share_payloads_equal(existing["payload_json"], payload.payload)
    ):
        return False
    if payload.share_target_type != "conversation":
        return True
    if not existing["message_id"]:
        return False
    message = connection.execute(
        """
        SELECT message_type, conversation_id, text_content,
               target_object_type, target_object_id, payload_json
        FROM chat_messages
        WHERE message_id = ?
        LIMIT 1;
        """,
        (existing["message_id"],),
    ).fetchone()
    if message is None:
        return False
    return (
        message["message_type"] == "post_share"
        and message["conversation_id"] == payload.conversation_id
        and message["text_content"] == payload.message_text
        and message["target_object_type"] == "social_post"
        and message["target_object_id"] == social_post_id
    )


def like_post(
    user_id: str,
    social_post_id: str,
    payload: PostInteractionCreate | None = None,
) -> PostLikeResponse:
    with transaction() as connection:
        user = _ensure_active_user(connection, user_id)
        post = _select_accessible_post(connection, social_post_id, user_id)
        active = connection.execute(
            """
            SELECT *
            FROM post_reactions
            WHERE user_id = ?
              AND social_post_id = ?
              AND reaction_type = 'like'
              AND status = 'active'
            LIMIT 1;
            """,
            (user_id, social_post_id),
        ).fetchone()
        if active is not None:
            return PostLikeResponse(
                success=True,
                social_post_id=social_post_id,
                is_liked=True,
                stats=_stats_record(connection, social_post_id),
            )

        now = utc_now_iso()
        existing = connection.execute(
            """
            SELECT reaction_id
            FROM post_reactions
            WHERE user_id = ?
              AND social_post_id = ?
              AND reaction_type = 'like'
            ORDER BY created_at DESC
            LIMIT 1;
            """,
            (user_id, social_post_id),
        ).fetchone()
        if existing is not None:
            connection.execute(
                """
                UPDATE post_reactions
                SET status = 'active',
                    source = ?,
                    reacted_at = ?,
                    canceled_at = NULL
                WHERE reaction_id = ?;
                """,
                (payload.source if payload else None, now, existing["reaction_id"]),
            )
        else:
            connection.execute(
                """
                INSERT INTO post_reactions (
                    reaction_id,
                    social_post_id,
                    user_id,
                    reaction_type,
                    status,
                    source,
                    reacted_at
                )
                VALUES (?, ?, ?, 'like', 'active', ?, ?);
                """,
                (str(uuid.uuid4()), social_post_id, user_id, payload.source if payload else None, now),
            )
        stats = _update_stat_count(connection, social_post_id, "like_count", 1)
        if post["author_user_id"] != user_id:
            create_title = "New like"
            create_body = f"{user['nickname']} liked your post."
            message_service.create_notification_in_transaction(
                connection,
                recipient_user_id=post["author_user_id"],
                event_type="post_like",
                category="interaction",
                actor_user_id=user_id,
                object_type="social_post",
                object_id=social_post_id,
                context_type="social_post",
                context_id=social_post_id,
                title=create_title,
                body=create_body,
                deep_link=f"/posts/{social_post_id}",
                dedup_key=f"post_like:{social_post_id}:{user_id}",
            )
    return PostLikeResponse(success=True, social_post_id=social_post_id, is_liked=True, stats=stats)


def unlike_post(user_id: str, social_post_id: str) -> PostLikeResponse:
    with transaction() as connection:
        _ensure_active_user(connection, user_id)
        _select_accessible_post(connection, social_post_id, user_id)
        active = connection.execute(
            """
            SELECT reaction_id
            FROM post_reactions
            WHERE user_id = ?
              AND social_post_id = ?
              AND reaction_type = 'like'
              AND status = 'active'
            LIMIT 1;
            """,
            (user_id, social_post_id),
        ).fetchone()
        if active is not None:
            connection.execute(
                """
                UPDATE post_reactions
                SET status = 'canceled',
                    canceled_at = ?
                WHERE reaction_id = ?;
                """,
                (utc_now_iso(), active["reaction_id"]),
            )
            stats = _update_stat_count(connection, social_post_id, "like_count", -1)
        else:
            stats = _stats_record(connection, social_post_id)
    return PostLikeResponse(success=True, social_post_id=social_post_id, is_liked=False, stats=stats)


def favorite_post(
    user_id: str,
    social_post_id: str,
    payload: PostInteractionCreate | None = None,
) -> PostFavoriteResponse:
    with transaction() as connection:
        _ensure_active_user(connection, user_id)
        _select_accessible_post(connection, social_post_id, user_id)
        active = connection.execute(
            """
            SELECT favorite_id
            FROM post_favorites
            WHERE user_id = ?
              AND social_post_id = ?
              AND status = 'active'
            LIMIT 1;
            """,
            (user_id, social_post_id),
        ).fetchone()
        if active is not None:
            return PostFavoriteResponse(
                success=True,
                social_post_id=social_post_id,
                is_favorited=True,
                stats=_stats_record(connection, social_post_id),
            )

        now = utc_now_iso()
        existing = connection.execute(
            """
            SELECT favorite_id
            FROM post_favorites
            WHERE user_id = ?
              AND social_post_id = ?
            ORDER BY created_at DESC
            LIMIT 1;
            """,
            (user_id, social_post_id),
        ).fetchone()
        if existing is not None:
            connection.execute(
                """
                UPDATE post_favorites
                SET status = 'active',
                    source = ?,
                    favorited_at = ?,
                    canceled_at = NULL
                WHERE favorite_id = ?;
                """,
                (payload.source if payload else None, now, existing["favorite_id"]),
            )
        else:
            connection.execute(
                """
                INSERT INTO post_favorites (
                    favorite_id,
                    social_post_id,
                    user_id,
                    status,
                    source,
                    favorited_at
                )
                VALUES (?, ?, ?, 'active', ?, ?);
                """,
                (str(uuid.uuid4()), social_post_id, user_id, payload.source if payload else None, now),
            )
        stats = _update_stat_count(connection, social_post_id, "favorite_count", 1)
    return PostFavoriteResponse(success=True, social_post_id=social_post_id, is_favorited=True, stats=stats)


def unfavorite_post(user_id: str, social_post_id: str) -> PostFavoriteResponse:
    with transaction() as connection:
        _ensure_active_user(connection, user_id)
        _select_accessible_post(connection, social_post_id, user_id)
        active = connection.execute(
            """
            SELECT favorite_id
            FROM post_favorites
            WHERE user_id = ?
              AND social_post_id = ?
              AND status = 'active'
            LIMIT 1;
            """,
            (user_id, social_post_id),
        ).fetchone()
        if active is not None:
            connection.execute(
                """
                UPDATE post_favorites
                SET status = 'canceled',
                    canceled_at = ?
                WHERE favorite_id = ?;
                """,
                (utc_now_iso(), active["favorite_id"]),
            )
            stats = _update_stat_count(connection, social_post_id, "favorite_count", -1)
        else:
            stats = _stats_record(connection, social_post_id)
    return PostFavoriteResponse(success=True, social_post_id=social_post_id, is_favorited=False, stats=stats)


def list_comments(
    social_post_id: str,
    user_id: str | None,
    page: int,
    page_size: int,
    parent_comment_id: str | None,
) -> PostCommentListResponse:
    offset = (page - 1) * page_size
    with get_connection() as connection:
        if user_id is not None:
            _ensure_active_user(connection, user_id)
        _select_accessible_post(connection, social_post_id, user_id)
        params: list[object] = [social_post_id]
        where = [
            "post_comments.social_post_id = ?",
            "post_comments.status = 'active'",
            "post_comments.deleted_at IS NULL",
            "users.status = 'active'",
            "users.deleted_at IS NULL",
        ]
        if parent_comment_id:
            _select_comment(connection, social_post_id, parent_comment_id)
            where.append("post_comments.parent_comment_id = ?")
            params.append(parent_comment_id)
        else:
            where.append("post_comments.parent_comment_id IS NULL")
        params.extend([page_size, offset])
        rows = connection.execute(
            f"""
            SELECT
                post_comments.*,
                users.nickname AS author_nickname,
                users.avatar_path AS author_avatar_path
            FROM post_comments
            JOIN users ON users.user_id = post_comments.author_user_id
            WHERE {" AND ".join(where)}
            ORDER BY post_comments.created_at ASC, post_comments.comment_id ASC
            LIMIT ? OFFSET ?;
            """,
            tuple(params),
        ).fetchall()
        items = [_comment_record(connection, row) for row in rows]
    return PostCommentListResponse(items=items, page=page, page_size=page_size)


def create_comment(user_id: str, social_post_id: str, payload: PostCommentCreate) -> PostCommentCreateResponse:
    with transaction() as connection:
        user = _ensure_active_user(connection, user_id)
        post = _select_accessible_post(connection, social_post_id, user_id)
        parent_row = None
        root_comment_id = None
        if payload.parent_comment_id:
            parent_row = _select_comment(connection, social_post_id, payload.parent_comment_id)
            root_comment_id = parent_row["root_comment_id"] or parent_row["comment_id"]

        comment_id = str(uuid.uuid4())
        connection.execute(
            """
            INSERT INTO post_comments (
                comment_id,
                social_post_id,
                author_user_id,
                parent_comment_id,
                root_comment_id,
                content,
                source
            )
            VALUES (?, ?, ?, ?, ?, ?, ?);
            """,
            (
                comment_id,
                social_post_id,
                user_id,
                payload.parent_comment_id,
                root_comment_id,
                payload.content,
                payload.source,
            ),
        )
        stats = _update_stat_count(connection, social_post_id, "comment_count", 1)

        if parent_row is not None:
            recipient_user_id = parent_row["author_user_id"]
            event_type = "comment_reply"
            title = "New reply"
            body = f"{user['nickname']} replied to your comment."
        else:
            recipient_user_id = post["author_user_id"]
            event_type = "post_comment"
            title = "New comment"
            body = f"{user['nickname']} commented on your post."
        if recipient_user_id != user_id:
            message_service.create_notification_in_transaction(
                connection,
                recipient_user_id=recipient_user_id,
                event_type=event_type,
                category="interaction",
                actor_user_id=user_id,
                object_type="comment",
                object_id=comment_id,
                context_type="social_post",
                context_id=social_post_id,
                title=title,
                body=body,
                deep_link=f"/posts/{social_post_id}",
                dedup_key=f"{event_type}:{comment_id}",
                payload={
                    "social_post_id": social_post_id,
                    "comment_id": comment_id,
                    "parent_comment_id": payload.parent_comment_id,
                },
            )

        comment = _comment_record(connection, _select_comment(connection, social_post_id, comment_id))
    return PostCommentCreateResponse(comment=comment, stats=stats)


def delete_comment(user_id: str, social_post_id: str, comment_id: str) -> PostCommentDeleteResponse:
    with transaction() as connection:
        _ensure_active_user(connection, user_id)
        post = _select_accessible_post(connection, social_post_id, user_id)
        comment = _select_comment(connection, social_post_id, comment_id)
        if user_id not in {comment["author_user_id"], post["author_user_id"]}:
            raise_api_error(
                status.HTTP_403_FORBIDDEN,
                "COMMENT_DELETE_FORBIDDEN",
                "You can only delete your own comments or comments on your post.",
            )
        connection.execute(
            """
            UPDATE post_comments
            SET status = 'deleted',
                content = NULL,
                deleted_at = ?
            WHERE comment_id = ?
              AND status = 'active';
            """,
            (utc_now_iso(), comment_id),
        )
        stats = _update_stat_count(connection, social_post_id, "comment_count", -1)
    return PostCommentDeleteResponse(
        success=True,
        social_post_id=social_post_id,
        comment_id=comment_id,
        stats=stats,
    )


def share_post(user_id: str, social_post_id: str, payload: PostShareCreate) -> PostShareResponse:
    try:
        lock_key = (
            f"message:{payload.conversation_id}"
            if payload.share_target_type == "conversation" and payload.conversation_id
            else f"post-share:{user_id}:{payload.client_message_id or social_post_id}"
        )
        with transaction(
            immediate=True,
            lock_key=lock_key,
        ) as connection:
            _ensure_active_user(connection, user_id)
            _select_accessible_post(connection, social_post_id, user_id)
            if payload.client_message_id:
                existing = connection.execute(
                    """
                    SELECT *
                    FROM post_shares
                    WHERE shared_by_user_id = ?
                      AND client_message_id = ?
                    LIMIT 1;
                    """,
                    (user_id, payload.client_message_id),
                ).fetchone()
                if existing is not None:
                    if not _share_request_matches(
                        connection,
                        existing,
                        social_post_id=social_post_id,
                        payload=payload,
                    ):
                        raise_api_error(
                            status.HTTP_409_CONFLICT,
                            "CLIENT_MESSAGE_ID_CONFLICT",
                            "client_message_id is already bound to another share.",
                        )
                    return PostShareResponse(
                        success=True,
                        share=_share_record(existing),
                        stats=_stats_record(connection, social_post_id),
                    )
            if payload.client_message_id:
                existing_message = connection.execute(
                    """
                    SELECT message_id
                    FROM chat_messages
                    WHERE sender_user_id = ? AND client_message_id = ?
                    LIMIT 1;
                    """,
                    (user_id, payload.client_message_id),
                ).fetchone()
                if existing_message is not None:
                    raise_api_error(
                        status.HTTP_409_CONFLICT,
                        "CLIENT_MESSAGE_ID_CONFLICT",
                        "client_message_id is already bound to another message.",
                    )
            post_share_id = str(uuid.uuid4())
            # Keep the optional share text for complete idempotency comparison;
            # it is internal metadata and is not exposed as a card field.
            connection.execute(
                """
                INSERT INTO post_shares (
                    post_share_id,
                    social_post_id,
                    shared_by_user_id,
                    share_target_type,
                    conversation_id,
                    channel,
                    message_text,
                    client_message_id,
                    payload_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    post_share_id,
                    social_post_id,
                    user_id,
                    payload.share_target_type,
                    payload.conversation_id,
                    payload.channel,
                    payload.message_text,
                    payload.client_message_id,
                    _json_text(payload.payload),
                ),
            )

            if payload.share_target_type == "conversation":
                sent = message_service.send_message_in_transaction(
                    connection,
                    user_id,
                    payload.conversation_id or "",
                    MessageCreate(
                        message_type="post_share",
                        text_content=payload.message_text,
                        payload={"post_share_id": post_share_id},
                        client_message_id=payload.client_message_id,
                        target_object_type="social_post",
                        target_object_id=social_post_id,
                    ),
                )
                connection.execute(
                    """
                    UPDATE post_shares
                    SET message_id = ?
                    WHERE post_share_id = ?;
                    """,
                    (sent.message.message_id, post_share_id),
                )

            stats = _update_stat_count(connection, social_post_id, "share_count", 1)
            row = connection.execute(
                """
                SELECT *
                FROM post_shares
                WHERE post_share_id = ?
                LIMIT 1;
                """,
                (post_share_id,),
            ).fetchone()
        return PostShareResponse(success=True, share=_share_record(row), stats=stats)
    except sqlite3.IntegrityError as error:
        if "UNIQUE constraint failed" in str(error):
            raise_api_error(
                status.HTTP_409_CONFLICT,
                "CLIENT_MESSAGE_ID_CONFLICT",
                "client_message_id is already bound to another request.",
            )
        raise
