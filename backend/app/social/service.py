from __future__ import annotations

import sqlite3
import uuid
from typing import Any, Literal

from fastapi import status

from backend.app.auth.service import raise_api_error
from backend.app.core.database import get_connection, transaction
from backend.app.core.time import utc_now_iso
from backend.app.messages.service import create_notification_in_transaction
from backend.app.social.schemas import (
    BlockActionResponse,
    BlockListItem,
    BlockListResponse,
    BlockRecord,
    FollowActionResponse,
    FollowListItem,
    FollowListResponse,
    FollowRecord,
    RelationshipResponse,
    SocialStatsResponse,
    SocialUserSummary,
)


def _row_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {key: row[key] for key in row.keys()}


def _row_to_follow(row: sqlite3.Row) -> FollowRecord:
    return FollowRecord(**_row_dict(row))


def _row_to_block(row: sqlite3.Row) -> BlockRecord:
    return BlockRecord(**_row_dict(row))


def _row_to_user_summary(row: sqlite3.Row) -> SocialUserSummary:
    return SocialUserSummary(
        user_id=row["user_id"],
        nickname=row["nickname"],
        avatar_path=row["avatar_path"],
        is_coach=bool(row["is_coach"]),
        coach_status=row["coach_status"],
    )


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


def _select_active_follow(
    connection: sqlite3.Connection,
    follower_user_id: str,
    following_user_id: str,
) -> sqlite3.Row | None:
    return connection.execute(
        """
        SELECT *
        FROM user_follows
        WHERE follower_user_id = ?
          AND following_user_id = ?
          AND status = 'active'
        LIMIT 1;
        """,
        (follower_user_id, following_user_id),
    ).fetchone()


def _is_following(connection: sqlite3.Connection, follower_user_id: str, following_user_id: str) -> bool:
    return _select_active_follow(connection, follower_user_id, following_user_id) is not None


def _select_active_block(
    connection: sqlite3.Connection,
    blocker_user_id: str,
    blocked_user_id: str,
) -> sqlite3.Row | None:
    return connection.execute(
        """
        SELECT *
        FROM user_blocks
        WHERE blocker_user_id = ?
          AND blocked_user_id = ?
          AND deleted_at IS NULL
        LIMIT 1;
        """,
        (blocker_user_id, blocked_user_id),
    ).fetchone()


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


def _relationship(
    connection: sqlite3.Connection,
    user_id: str,
    target_user_id: str,
) -> RelationshipResponse:
    is_following = _is_following(connection, user_id, target_user_id)
    is_followed_by = _is_following(connection, target_user_id, user_id)
    return RelationshipResponse(
        user_id=user_id,
        target_user_id=target_user_id,
        is_following=is_following,
        is_followed_by=is_followed_by,
        is_friend=is_following and is_followed_by,
    )


def follow_user(user_id: str, target_user_id: str, source: str | None = None) -> FollowActionResponse:
    if user_id == target_user_id:
        raise_api_error(status.HTTP_400_BAD_REQUEST, "CANNOT_FOLLOW_SELF", "You cannot follow yourself.")

    with transaction() as connection:
        current_user = _ensure_active_user(connection, user_id)
        target_user = _ensure_active_user(connection, target_user_id)
        if _has_block_relation(connection, user_id, target_user_id):
            raise_api_error(
                status.HTTP_403_FORBIDDEN,
                "USER_INTERACTION_BLOCKED",
                "Following is unavailable between these users.",
            )
        existing = _select_active_follow(connection, user_id, target_user_id)
        if existing is not None:
            return FollowActionResponse(
                success=True,
                relationship=_relationship(connection, user_id, target_user_id),
                follow=_row_to_follow(existing),
            )

        follow_id = str(uuid.uuid4())
        connection.execute(
            """
            INSERT INTO user_follows (
                follow_id,
                follower_user_id,
                following_user_id,
                source
            )
            VALUES (?, ?, ?, ?);
            """,
            (follow_id, user_id, target_user_id, source),
        )
        follow_row = connection.execute(
            "SELECT * FROM user_follows WHERE follow_id = ? LIMIT 1;",
            (follow_id,),
        ).fetchone()

        create_notification_in_transaction(
            connection,
            recipient_user_id=target_user_id,
            event_type="follow",
            category="interaction",
            actor_user_id=user_id,
            object_type="user",
            object_id=user_id,
            title="New follower",
            body=f"{current_user['nickname']} followed you.",
            deep_link=f"/users/{user_id}",
            dedup_key=f"follow:{follow_id}",
            payload={
                "follower_user_id": user_id,
                "follower_nickname": current_user["nickname"],
                "target_user_id": target_user["user_id"],
            },
        )

        return FollowActionResponse(
            success=True,
            relationship=_relationship(connection, user_id, target_user_id),
            follow=_row_to_follow(follow_row),
        )


def unfollow_user(user_id: str, target_user_id: str) -> FollowActionResponse:
    if user_id == target_user_id:
        raise_api_error(status.HTTP_400_BAD_REQUEST, "CANNOT_UNFOLLOW_SELF", "You cannot unfollow yourself.")

    with transaction() as connection:
        _ensure_active_user(connection, user_id)
        _ensure_active_user(connection, target_user_id)
        existing = _select_active_follow(connection, user_id, target_user_id)
        if existing is not None:
            connection.execute(
                """
                UPDATE user_follows
                SET status = 'canceled',
                    canceled_at = CURRENT_TIMESTAMP
                WHERE follow_id = ?;
                """,
                (existing["follow_id"],),
            )

        return FollowActionResponse(
            success=True,
            relationship=_relationship(connection, user_id, target_user_id),
            follow=None,
        )


def get_relationship(user_id: str, target_user_id: str) -> RelationshipResponse:
    with get_connection() as connection:
        _ensure_active_user(connection, user_id)
        _ensure_active_user(connection, target_user_id)
        return _relationship(connection, user_id, target_user_id)


def _list_follows(
    user_id: str,
    list_type: Literal["followers", "following", "friends"],
    page: int,
    page_size: int,
) -> FollowListResponse:
    offset = (page - 1) * page_size
    with get_connection() as connection:
        _ensure_active_user(connection, user_id)
        if list_type == "followers":
            rows = connection.execute(
                """
                SELECT
                    users.user_id,
                    users.nickname,
                    users.avatar_path,
                    users.is_coach,
                    users.coach_status,
                    user_follows.*,
                    reciprocal.follow_id AS reciprocal_follow_id
                FROM user_follows
                JOIN users ON users.user_id = user_follows.follower_user_id
                LEFT JOIN user_follows AS reciprocal
                    ON reciprocal.follower_user_id = user_follows.following_user_id
                   AND reciprocal.following_user_id = user_follows.follower_user_id
                   AND reciprocal.status = 'active'
                WHERE user_follows.following_user_id = ?
                  AND user_follows.status = 'active'
                  AND users.status = 'active'
                  AND users.deleted_at IS NULL
                ORDER BY user_follows.followed_at DESC
                LIMIT ? OFFSET ?;
                """,
                (user_id, page_size, offset),
            ).fetchall()
        elif list_type == "following":
            rows = connection.execute(
                """
                SELECT
                    users.user_id,
                    users.nickname,
                    users.avatar_path,
                    users.is_coach,
                    users.coach_status,
                    user_follows.*,
                    reciprocal.follow_id AS reciprocal_follow_id
                FROM user_follows
                JOIN users ON users.user_id = user_follows.following_user_id
                LEFT JOIN user_follows AS reciprocal
                    ON reciprocal.follower_user_id = user_follows.following_user_id
                   AND reciprocal.following_user_id = user_follows.follower_user_id
                   AND reciprocal.status = 'active'
                WHERE user_follows.follower_user_id = ?
                  AND user_follows.status = 'active'
                  AND users.status = 'active'
                  AND users.deleted_at IS NULL
                ORDER BY user_follows.followed_at DESC
                LIMIT ? OFFSET ?;
                """,
                (user_id, page_size, offset),
            ).fetchall()
        else:
            rows = connection.execute(
                """
                SELECT
                    users.user_id,
                    users.nickname,
                    users.avatar_path,
                    users.is_coach,
                    users.coach_status,
                    user_follows.*,
                    reciprocal.follow_id AS reciprocal_follow_id
                FROM user_follows
                JOIN user_follows AS reciprocal
                    ON reciprocal.follower_user_id = user_follows.following_user_id
                   AND reciprocal.following_user_id = user_follows.follower_user_id
                   AND reciprocal.status = 'active'
                JOIN users ON users.user_id = user_follows.following_user_id
                WHERE user_follows.follower_user_id = ?
                  AND user_follows.status = 'active'
                  AND users.status = 'active'
                  AND users.deleted_at IS NULL
                ORDER BY user_follows.followed_at DESC
                LIMIT ? OFFSET ?;
                """,
                (user_id, page_size, offset),
            ).fetchall()

    return FollowListResponse(
        items=[
            FollowListItem(
                user=_row_to_user_summary(row),
                follow=_row_to_follow(row),
                is_friend=row["reciprocal_follow_id"] is not None,
            )
            for row in rows
        ],
        page=page,
        page_size=page_size,
    )


def list_followers(user_id: str, page: int, page_size: int) -> FollowListResponse:
    return _list_follows(user_id, "followers", page, page_size)


def list_following(user_id: str, page: int, page_size: int) -> FollowListResponse:
    return _list_follows(user_id, "following", page, page_size)


def list_friends(user_id: str, page: int, page_size: int) -> FollowListResponse:
    return _list_follows(user_id, "friends", page, page_size)


def get_social_stats(user_id: str) -> SocialStatsResponse:
    with get_connection() as connection:
        _ensure_active_user(connection, user_id)
        follower_count = connection.execute(
            """
            SELECT count(*)
            FROM user_follows
            WHERE following_user_id = ?
              AND status = 'active';
            """,
            (user_id,),
        ).fetchone()[0]
        following_count = connection.execute(
            """
            SELECT count(*)
            FROM user_follows
            WHERE follower_user_id = ?
              AND status = 'active';
            """,
            (user_id,),
        ).fetchone()[0]
        friend_count = connection.execute(
            """
            SELECT count(*)
            FROM user_follows
            JOIN user_follows AS reciprocal
                ON reciprocal.follower_user_id = user_follows.following_user_id
               AND reciprocal.following_user_id = user_follows.follower_user_id
               AND reciprocal.status = 'active'
            WHERE user_follows.follower_user_id = ?
              AND user_follows.status = 'active';
            """,
            (user_id,),
        ).fetchone()[0]

    return SocialStatsResponse(
        user_id=user_id,
        follower_count=int(follower_count),
        following_count=int(following_count),
        friend_count=int(friend_count),
    )


def block_user(user_id: str, target_user_id: str, reason: str | None = None) -> BlockActionResponse:
    if user_id == target_user_id:
        raise_api_error(status.HTTP_400_BAD_REQUEST, "CANNOT_BLOCK_SELF", "You cannot block yourself.")

    with transaction() as connection:
        _ensure_active_user(connection, user_id)
        _ensure_active_user(connection, target_user_id)
        existing = _select_active_block(connection, user_id, target_user_id)
        now = utc_now_iso()
        if existing is None:
            block_id = str(uuid.uuid4())
            connection.execute(
                """
                INSERT INTO user_blocks (
                    user_block_id,
                    blocker_user_id,
                    blocked_user_id,
                    reason,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?);
                """,
                (block_id, user_id, target_user_id, reason, now),
            )
            block_row = connection.execute(
                "SELECT * FROM user_blocks WHERE user_block_id = ? LIMIT 1;",
                (block_id,),
            ).fetchone()
        else:
            block_row = existing
            if reason is not None and reason != existing["reason"]:
                connection.execute(
                    """
                    UPDATE user_blocks
                    SET reason = ?
                    WHERE user_block_id = ?;
                    """,
                    (reason, existing["user_block_id"]),
                )
                block_row = connection.execute(
                    "SELECT * FROM user_blocks WHERE user_block_id = ? LIMIT 1;",
                    (existing["user_block_id"],),
                ).fetchone()

        connection.execute(
            """
            UPDATE user_follows
            SET status = 'canceled',
                canceled_at = COALESCE(canceled_at, ?)
            WHERE status = 'active'
              AND (
                  (follower_user_id = ? AND following_user_id = ?)
                  OR (follower_user_id = ? AND following_user_id = ?)
              );
            """,
            (now, user_id, target_user_id, target_user_id, user_id),
        )
        connection.execute(
            """
            UPDATE chat_message_requests
            SET status = 'blocked',
                responded_at = COALESCE(responded_at, ?)
            WHERE status = 'pending'
              AND (
                  (requester_user_id = ? AND recipient_user_id = ?)
                  OR (requester_user_id = ? AND recipient_user_id = ?)
              );
            """,
            (now, user_id, target_user_id, target_user_id, user_id),
        )
    return BlockActionResponse(success=True, block=_row_to_block(block_row))


def unblock_user(user_id: str, target_user_id: str) -> BlockActionResponse:
    if user_id == target_user_id:
        raise_api_error(status.HTTP_400_BAD_REQUEST, "CANNOT_UNBLOCK_SELF", "You cannot unblock yourself.")

    with transaction() as connection:
        _ensure_active_user(connection, user_id)
        _ensure_active_user(connection, target_user_id)
        existing = _select_active_block(connection, user_id, target_user_id)
        if existing is not None:
            connection.execute(
                """
                UPDATE user_blocks
                SET deleted_at = ?
                WHERE user_block_id = ?;
                """,
                (utc_now_iso(), existing["user_block_id"]),
            )
    return BlockActionResponse(success=True, block=None)


def list_blocks(user_id: str, page: int, page_size: int) -> BlockListResponse:
    offset = (page - 1) * page_size
    with get_connection() as connection:
        _ensure_active_user(connection, user_id)
        rows = connection.execute(
            """
            SELECT
                users.user_id,
                users.nickname,
                users.avatar_path,
                users.is_coach,
                users.coach_status,
                user_blocks.*
            FROM user_blocks
            JOIN users ON users.user_id = user_blocks.blocked_user_id
            WHERE user_blocks.blocker_user_id = ?
              AND user_blocks.deleted_at IS NULL
              AND users.status = 'active'
              AND users.deleted_at IS NULL
            ORDER BY user_blocks.created_at DESC
            LIMIT ? OFFSET ?;
            """,
            (user_id, page_size, offset),
        ).fetchall()
    return BlockListResponse(
        items=[
            BlockListItem(
                user=_row_to_user_summary(row),
                block=_row_to_block(row),
            )
            for row in rows
        ],
        page=page,
        page_size=page_size,
    )
