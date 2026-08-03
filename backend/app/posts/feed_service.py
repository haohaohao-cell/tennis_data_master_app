from __future__ import annotations

import base64
import json
import logging
import sqlite3
import time
import uuid
from typing import Any

from fastapi import status

from backend.app.auth.schemas import UserPublic
from backend.app.auth.service import raise_api_error
from backend.app.core.database import get_connection, transaction
from backend.app.core.time import utc_now_iso
from backend.app.posts.schemas import (
    FeedType,
    PostCollectionKind,
    PostCollectionResponse,
    PostAuthor,
    PostDetailResponse,
    PostFeedItem,
    PostFeedResponse,
    PostFeedStateResponse,
    PostHideCreate,
    PostHideResponse,
    PostMediaRecord,
    PostStatsRecord,
    PostViewerState,
    PostViewItem,
    PostViewsBulkCreate,
    PostViewsBulkResponse,
)
from backend.app.posts.service import _row_to_media, _row_to_post, _row_to_video
from backend.app.uploads.thumbnails import ensure_video_thumbnail_records
from backend.app.uploads.schemas import VideoRecord


FEED_SORT_STRATEGY_VERSION = "view_bucket_published_at_desc_v1"
SORT_STRATEGY_BY_FEED: dict[FeedType, str] = {
    "recommended": FEED_SORT_STRATEGY_VERSION,
    "following": FEED_SORT_STRATEGY_VERSION,
    "nearby": FEED_SORT_STRATEGY_VERSION,
}


logger = logging.getLogger(__name__)
REPORT_VIEW_LOCK_RETRY_DELAYS_SECONDS = (0.05, 0.15, 0.35)


def _encode_cursor(
    *,
    feed_type: FeedType,
    view_bucket: int,
    sort_time: str,
    social_post_id: str,
) -> str:
    payload = {
        "v": 2,
        "feed_type": feed_type,
        "view_bucket": view_bucket,
        "sort_time": sort_time,
        "social_post_id": social_post_id,
    }
    encoded = base64.urlsafe_b64encode(
        json.dumps(payload, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    )
    return encoded.decode("ascii").rstrip("=")


def _decode_cursor(cursor: str | None, feed_type: FeedType) -> dict[str, Any] | None:
    if not cursor:
        return None
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded).decode("utf-8"))
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
        raise_api_error(status.HTTP_400_BAD_REQUEST, "INVALID_FEED_CURSOR", "Feed cursor is invalid.")

    if (
        payload.get("v") != 2
        or payload.get("feed_type") != feed_type
        or not isinstance(payload.get("view_bucket"), int)
        or not isinstance(payload.get("sort_time"), str)
        or not isinstance(payload.get("social_post_id"), str)
    ):
        raise_api_error(status.HTTP_400_BAD_REQUEST, "INVALID_FEED_CURSOR", "Feed cursor is invalid.")
    return payload


def _encode_collection_cursor(
    *,
    collection: PostCollectionKind,
    collection_time: str,
    collection_id: str,
) -> str:
    payload = {
        "v": 1,
        "collection": collection,
        "collection_time": collection_time,
        "collection_id": collection_id,
    }
    encoded = base64.urlsafe_b64encode(
        json.dumps(payload, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    )
    return encoded.decode("ascii").rstrip("=")


def _decode_collection_cursor(
    cursor: str | None,
    collection: PostCollectionKind,
) -> dict[str, str] | None:
    if not cursor:
        return None
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded).decode("utf-8"))
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
        raise_api_error(
            status.HTTP_400_BAD_REQUEST,
            "INVALID_POST_COLLECTION_CURSOR",
            "Post collection cursor is invalid.",
        )

    if (
        payload.get("v") != 1
        or payload.get("collection") != collection
        or not isinstance(payload.get("collection_time"), str)
        or not isinstance(payload.get("collection_id"), str)
    ):
        raise_api_error(
            status.HTTP_400_BAD_REQUEST,
            "INVALID_POST_COLLECTION_CURSOR",
            "Post collection cursor is invalid.",
        )
    return {
        "collection_time": payload["collection_time"],
        "collection_id": payload["collection_id"],
    }


def _placeholders(values: list[str]) -> str:
    return ", ".join("?" for _ in values)


def _visibility_clause(feed_type: FeedType, user_id: str | None) -> tuple[str, list[object]]:
    if feed_type in {"recommended", "nearby"}:
        return "sp.visibility = 'public'", []
    if not user_id:
        return "1 = 0", []
    return (
        """
        (
            sp.visibility = 'public'
            OR (
                sp.visibility = 'followers'
                AND EXISTS (
                    SELECT 1
                    FROM user_follows viewer_follow
                    WHERE viewer_follow.follower_user_id = ?
                      AND viewer_follow.following_user_id = sp.author_user_id
                      AND viewer_follow.status = 'active'
                )
            )
            OR (
                sp.visibility = 'friends'
                AND EXISTS (
                    SELECT 1
                    FROM user_follows viewer_follow
                    JOIN user_follows author_follow
                      ON author_follow.follower_user_id = sp.author_user_id
                     AND author_follow.following_user_id = ?
                     AND author_follow.status = 'active'
                    WHERE viewer_follow.follower_user_id = ?
                      AND viewer_follow.following_user_id = sp.author_user_id
                      AND viewer_follow.status = 'active'
                )
            )
        )
        """,
        [user_id, user_id, user_id],
    )


def _collection_visibility_clause(user_id: str) -> tuple[str, list[object]]:
    return (
        """
        (
            sp.author_user_id = ?
            OR sp.visibility = 'public'
            OR (
                sp.visibility = 'followers'
                AND EXISTS (
                    SELECT 1
                    FROM user_follows viewer_follow
                    WHERE viewer_follow.follower_user_id = ?
                      AND viewer_follow.following_user_id = sp.author_user_id
                      AND viewer_follow.status = 'active'
                )
            )
            OR (
                sp.visibility = 'friends'
                AND EXISTS (
                    SELECT 1
                    FROM user_follows viewer_follow
                    WHERE viewer_follow.follower_user_id = ?
                      AND viewer_follow.following_user_id = sp.author_user_id
                      AND viewer_follow.status = 'active'
                )
                AND EXISTS (
                    SELECT 1
                    FROM user_follows author_follow
                    WHERE author_follow.follower_user_id = sp.author_user_id
                      AND author_follow.following_user_id = ?
                      AND author_follow.status = 'active'
                )
            )
        )
        """,
        [user_id, user_id, user_id, user_id],
    )


def _candidate_query(
    *,
    feed_type: FeedType,
    user_id: str | None,
    city: str | None,
    region: str | None,
    cursor: dict[str, Any] | None,
    limit: int,
) -> tuple[str, list[object]]:
    params: list[object] = []
    view_bucket_expression = "0 AS view_bucket"
    if user_id:
        params.append(user_id)
        view_bucket_expression = (
            "CASE WHEN viewed_post.social_post_id IS NULL THEN 0 ELSE 1 END AS view_bucket"
        )

    where = [
        "sp.status = 'published'",
        "sp.review_status = 'approved'",
        "sp.deleted_at IS NULL",
        "author.status = 'active'",
        "author.deleted_at IS NULL",
    ]
    visibility_sql, visibility_params = _visibility_clause(feed_type, user_id)
    where.append(visibility_sql)
    params.extend(visibility_params)

    if user_id:
        where.extend(
            [
                "sp.author_user_id <> ?",
                """
                NOT EXISTS (
                    SELECT 1
                    FROM user_blocks block_relation
                    WHERE block_relation.deleted_at IS NULL
                      AND (
                          (block_relation.blocker_user_id = ? AND block_relation.blocked_user_id = sp.author_user_id)
                          OR
                          (block_relation.blocker_user_id = sp.author_user_id AND block_relation.blocked_user_id = ?)
                      )
                )
                """,
                """
                NOT EXISTS (
                    SELECT 1
                    FROM user_post_hides hidden_post
                    WHERE hidden_post.user_id = ?
                      AND hidden_post.social_post_id = sp.social_post_id
                      AND hidden_post.status = 'active'
                )
                """,
            ]
        )
        params.extend([user_id, user_id, user_id, user_id])

    if feed_type == "following":
        where.append(
            """
            EXISTS (
                SELECT 1
                FROM user_follows followed_author
                WHERE followed_author.follower_user_id = ?
                  AND followed_author.following_user_id = sp.author_user_id
                  AND followed_author.status = 'active'
            )
            """
        )
        params.append(user_id)

    feed_source_sql = "'recommended'"
    if feed_type == "following":
        feed_source_sql = "'following'"
    elif feed_type == "nearby":
        if not city and not region:
            return "", []
        location_conditions: list[str] = []
        if city:
            location_conditions.append("(sp.location_scope = 'city' AND sp.location_city = ?)")
            params.append(city)
        if region:
            location_conditions.append("(sp.location_scope IN ('region', 'city') AND sp.location_region = ?)")
            params.append(region)
        where.append(f"({' OR '.join(location_conditions)})")
        if city:
            feed_source_sql = "'nearby'"
        else:
            feed_source_sql = "'nearby_region_fallback'"
    cursor_where = ""
    cursor_params: list[object] = []
    if cursor:
        cursor_where = """
            (
                view_bucket > ?
                OR (
                    view_bucket = ?
                    AND (
                        sort_time < ?
                        OR (sort_time = ? AND social_post_id < ?)
                    )
                )
            )
        """
        cursor_params.extend(
            [
                cursor["view_bucket"],
                cursor["view_bucket"],
                cursor["sort_time"],
                cursor["sort_time"],
                cursor["social_post_id"],
            ]
        )

    order_by = "view_bucket ASC, sort_time DESC, social_post_id DESC"
    query = f"""
        WITH candidates AS (
            SELECT
                sp.*,
                COALESCE(sp.published_at, sp.created_at) AS sort_time,
                {view_bucket_expression},
                {feed_source_sql} AS feed_source
            FROM social_posts sp
            JOIN users author ON author.user_id = sp.author_user_id
            {"LEFT JOIN user_post_views viewed_post ON viewed_post.user_id = ? AND viewed_post.social_post_id = sp.social_post_id" if user_id else ""}
            WHERE {' AND '.join(where)}
        )
        SELECT *
        FROM candidates
        {"WHERE " + cursor_where if cursor_where else ""}
        ORDER BY {order_by}
        LIMIT ?;
    """
    params.extend(cursor_params)
    params.append(limit + 1)
    return query, params


def _batch_details(
    connection: sqlite3.Connection,
    post_rows: list[sqlite3.Row],
    viewer_user_id: str | None = None,
) -> dict[str, PostDetailResponse]:
    if not post_rows:
        return {}

    post_ids = [row["social_post_id"] for row in post_rows]
    author_ids = list(dict.fromkeys(row["author_user_id"] for row in post_rows))
    post_id_sql = _placeholders(post_ids)
    author_id_sql = _placeholders(author_ids)

    author_rows = connection.execute(
        f"""
        SELECT user_id, nickname, avatar_path
        FROM users
        WHERE user_id IN ({author_id_sql})
          AND deleted_at IS NULL;
        """,
        author_ids,
    ).fetchall()
    authors = {
        row["user_id"]: PostAuthor(**{key: row[key] for key in row.keys()})
        for row in author_rows
    }

    media_rows = connection.execute(
        f"""
        SELECT *
        FROM post_media
        WHERE social_post_id IN ({post_id_sql})
          AND deleted_at IS NULL
        ORDER BY sort_order ASC, created_at ASC, post_media_id ASC;
        """,
        post_ids,
    ).fetchall()
    media_by_post: dict[str, list[sqlite3.Row]] = {}
    video_ids: list[str] = []
    for row in media_rows:
        media_by_post.setdefault(row["social_post_id"], []).append(row)
        if row["video_id"]:
            video_ids.append(row["video_id"])

    videos_by_id: dict[str, dict[str, Any]] = {}
    if video_ids:
        video_id_sql = _placeholders(list(dict.fromkeys(video_ids)))
        video_rows = connection.execute(
            f"""
            SELECT *
            FROM videos
            WHERE video_id IN ({video_id_sql})
              AND deleted_at IS NULL;
            """,
            list(dict.fromkeys(video_ids)),
        ).fetchall()
        video_records = ensure_video_thumbnail_records(connection, video_rows)
        videos_by_id = {record["video_id"]: record for record in video_records}

    stats_rows = connection.execute(
        f"""
        SELECT *
        FROM social_post_stats
        WHERE social_post_id IN ({post_id_sql});
        """,
        post_ids,
    ).fetchall()
    stats_by_post = {
        row["social_post_id"]: PostStatsRecord(**{key: row[key] for key in row.keys()})
        for row in stats_rows
    }
    viewer_state_by_post: dict[str, PostViewerState] = {}
    if viewer_user_id:
        liked_rows = connection.execute(
            f"""
            SELECT social_post_id
            FROM post_reactions
            WHERE user_id = ?
              AND social_post_id IN ({post_id_sql})
              AND reaction_type = 'like'
              AND status = 'active';
            """,
            [viewer_user_id, *post_ids],
        ).fetchall()
        favorited_rows = connection.execute(
            f"""
            SELECT social_post_id
            FROM post_favorites
            WHERE user_id = ?
              AND social_post_id IN ({post_id_sql})
              AND status = 'active';
            """,
            [viewer_user_id, *post_ids],
        ).fetchall()
        liked_ids = {row["social_post_id"] for row in liked_rows}
        favorited_ids = {row["social_post_id"] for row in favorited_rows}
        viewer_state_by_post = {
            post_id: PostViewerState(
                is_liked=post_id in liked_ids,
                is_favorited=post_id in favorited_ids,
            )
            for post_id in post_ids
        }

    details: dict[str, PostDetailResponse] = {}
    for post_row in post_rows:
        post_id = post_row["social_post_id"]
        media_for_post = media_by_post.get(post_id, [])
        ordered_video_ids = [row["video_id"] for row in media_for_post if row["video_id"]]
        details[post_id] = PostDetailResponse(
            post=_row_to_post(post_row),
            author=authors[post_row["author_user_id"]],
            media=[_row_to_media(row) for row in media_for_post],
            videos=[
                _row_to_video(videos_by_id[video_id])
                for video_id in ordered_video_ids
                if video_id in videos_by_id
            ],
            stats=stats_by_post.get(post_id),
            viewer_state=viewer_state_by_post.get(post_id),
        )
    return details


def list_feed(
    *,
    feed_type: FeedType,
    user: UserPublic | None,
    cursor: str | None,
    limit: int,
    city: str | None = None,
    region: str | None = None,
) -> PostFeedResponse:
    user_id = user.user_id if user else None
    cursor_payload = _decode_cursor(cursor, feed_type)
    if feed_type == "following" and not user_id:
        raise_api_error(status.HTTP_401_UNAUTHORIZED, "LOGIN_REQUIRED", "Login is required for the following feed.")

    normalized_city = city.strip() if city else None
    normalized_region = region.strip() if region else None
    if feed_type == "nearby" and not normalized_city and not normalized_region:
        return PostFeedResponse(
            feed_type=feed_type,
            items=[],
            has_more=False,
            strategy_version=SORT_STRATEGY_BY_FEED[feed_type],
            fallback_mode="location_required",
        )

    query, params = _candidate_query(
        feed_type=feed_type,
        user_id=user_id,
        city=normalized_city,
        region=normalized_region,
        cursor=cursor_payload,
        limit=limit,
    )
    with get_connection() as connection:
        rows = connection.execute(query, params).fetchall()
        has_more = len(rows) > limit
        page_rows = rows[:limit]
        details = _batch_details(connection, page_rows, user_id)

    items: list[PostFeedItem] = []
    for row in page_rows:
        detail = details[row["social_post_id"]]
        items.append(
            PostFeedItem(
                **detail.model_dump(),
                feed_source=(
                    "nearby"
                    if feed_type == "nearby"
                    and normalized_city
                    and row["location_scope"] == "city"
                    and row["location_city"] == normalized_city
                    else (
                        "nearby_region_fallback"
                        if feed_type == "nearby"
                        else row["feed_source"]
                    )
                ),
                sort_strategy=SORT_STRATEGY_BY_FEED[feed_type],
            )
        )

    next_cursor = None
    if has_more and page_rows:
        last_row = page_rows[-1]
        next_cursor = _encode_cursor(
            feed_type=feed_type,
            view_bucket=last_row["view_bucket"],
            sort_time=last_row["sort_time"],
            social_post_id=last_row["social_post_id"],
        )

    fallback_mode = None
    if feed_type == "nearby" and normalized_city and normalized_region:
        fallback_mode = "region"
    return PostFeedResponse(
        feed_type=feed_type,
        items=items,
        next_cursor=next_cursor,
        has_more=has_more,
        strategy_version=SORT_STRATEGY_BY_FEED[feed_type],
        fallback_mode=fallback_mode,
    )


def list_current_user_post_collection(
    *,
    user_id: str,
    collection: PostCollectionKind,
    cursor: str | None,
    limit: int,
) -> PostCollectionResponse:
    cursor_payload = _decode_collection_cursor(cursor, collection)
    interaction_table = "post_favorites" if collection == "favorites" else "post_reactions"
    interaction_id_column = "favorite_id" if collection == "favorites" else "reaction_id"
    interaction_time_column = "favorited_at" if collection == "favorites" else "reacted_at"

    where = [
        "interaction.user_id = ?",
        "interaction.status = 'active'",
        "sp.status = 'published'",
        "sp.review_status = 'approved'",
        "sp.deleted_at IS NULL",
        "author.status = 'active'",
        "author.deleted_at IS NULL",
    ]
    params: list[object] = [user_id]
    if collection == "likes":
        where.append("interaction.reaction_type = 'like'")

    visibility_sql, visibility_params = _collection_visibility_clause(user_id)
    where.append(visibility_sql)
    params.extend(visibility_params)
    where.extend(
        [
            """
            NOT EXISTS (
                SELECT 1
                FROM user_blocks block_relation
                WHERE block_relation.deleted_at IS NULL
                  AND (
                      (block_relation.blocker_user_id = ? AND block_relation.blocked_user_id = sp.author_user_id)
                      OR
                      (block_relation.blocker_user_id = sp.author_user_id AND block_relation.blocked_user_id = ?)
                  )
            )
            """,
            """
            NOT EXISTS (
                SELECT 1
                FROM user_post_hides hidden_post
                WHERE hidden_post.user_id = ?
                  AND hidden_post.social_post_id = sp.social_post_id
                  AND hidden_post.status = 'active'
            )
            """,
        ]
    )
    params.extend([user_id, user_id, user_id])

    cursor_where = ""
    if cursor_payload:
        cursor_where = """
            WHERE collection_time < ?
               OR (collection_time = ? AND collection_id < ?)
        """
        params.extend(
            [
                cursor_payload["collection_time"],
                cursor_payload["collection_time"],
                cursor_payload["collection_id"],
            ]
        )

    query = f"""
        WITH collection_items AS (
            SELECT
                sp.*,
                COALESCE(interaction.{interaction_time_column}, interaction.created_at) AS collection_time,
                interaction.{interaction_id_column} AS collection_id
            FROM {interaction_table} interaction
            JOIN social_posts sp ON sp.social_post_id = interaction.social_post_id
            JOIN users author ON author.user_id = sp.author_user_id
            WHERE {' AND '.join(where)}
        )
        SELECT *
        FROM collection_items
        {cursor_where}
        ORDER BY collection_time DESC, collection_id DESC
        LIMIT ?;
    """
    params.append(limit + 1)

    with get_connection() as connection:
        rows = connection.execute(query, params).fetchall()
        has_more = len(rows) > limit
        page_rows = rows[:limit]
        details = _batch_details(connection, page_rows, user_id)

    next_cursor = None
    if has_more and page_rows:
        last_row = page_rows[-1]
        next_cursor = _encode_collection_cursor(
            collection=collection,
            collection_time=last_row["collection_time"],
            collection_id=last_row["collection_id"],
        )

    return PostCollectionResponse(
        collection=collection,
        items=[details[row["social_post_id"]] for row in page_rows],
        next_cursor=next_cursor,
        has_more=has_more,
    )


def get_feed_state() -> PostFeedStateResponse:
    return PostFeedStateResponse(
        supported_feed_types=["recommended", "following", "nearby"],
        recommended_strategy_version=FEED_SORT_STRATEGY_VERSION,
        nearby_requires_location=True,
        nearby_location_privacy="only coarse city or region is stored and returned",
    )


def _accessible_post_ids(
    connection: sqlite3.Connection,
    *,
    user_id: str,
    post_ids: list[str],
) -> set[str]:
    if not post_ids:
        return set()
    id_sql = _placeholders(post_ids)
    rows = connection.execute(
        f"""
        SELECT sp.social_post_id
        FROM social_posts sp
        JOIN users author ON author.user_id = sp.author_user_id
        WHERE sp.social_post_id IN ({id_sql})
          AND sp.status = 'published'
          AND sp.review_status = 'approved'
          AND sp.deleted_at IS NULL
          AND author.status = 'active'
          AND author.deleted_at IS NULL
          AND (
              sp.visibility = 'public'
              OR (
                  sp.visibility = 'followers'
                  AND EXISTS (
                      SELECT 1 FROM user_follows
                      WHERE follower_user_id = ?
                        AND following_user_id = sp.author_user_id
                        AND status = 'active'
                  )
              )
              OR (
                  sp.visibility = 'friends'
                  AND EXISTS (
                      SELECT 1 FROM user_follows own_follow
                      WHERE own_follow.follower_user_id = ?
                        AND own_follow.following_user_id = sp.author_user_id
                        AND own_follow.status = 'active'
                  )
                  AND EXISTS (
                      SELECT 1 FROM user_follows reverse_follow
                      WHERE reverse_follow.follower_user_id = sp.author_user_id
                        AND reverse_follow.following_user_id = ?
                        AND reverse_follow.status = 'active'
                  )
              )
          )
          AND NOT EXISTS (
              SELECT 1 FROM user_blocks
              WHERE deleted_at IS NULL
                AND (
                    (blocker_user_id = ? AND blocked_user_id = sp.author_user_id)
                    OR (blocker_user_id = sp.author_user_id AND blocked_user_id = ?)
                )
          );
        """,
        [*post_ids, user_id, user_id, user_id, user_id, user_id],
    ).fetchall()
    return {row["social_post_id"] for row in rows}


def report_views(user_id: str, payload: PostViewsBulkCreate) -> PostViewsBulkResponse:
    unique_items: list[PostViewItem] = []
    seen_ids: set[str] = set()
    for item in payload.items:
        if item.social_post_id in seen_ids:
            continue
        seen_ids.add(item.social_post_id)
        unique_items.append(item)

    with get_connection() as connection:
        accessible_ids = _accessible_post_ids(
            connection,
            user_id=user_id,
            post_ids=[item.social_post_id for item in unique_items],
        )

    accepted_items = [item for item in unique_items if item.social_post_id in accessible_ids]
    ignored_ids = [item.social_post_id for item in unique_items if item.social_post_id not in accessible_ids]

    if accepted_items:
        report_failed = False
        for retry_delay in (*REPORT_VIEW_LOCK_RETRY_DELAYS_SECONDS, None):
            try:
                now = utc_now_iso()
                with transaction(immediate=True) as connection:
                    for item in accepted_items:
                        connection.execute(
                            """
                            INSERT INTO user_post_views (
                                user_post_view_id,
                                user_id,
                                social_post_id,
                                first_viewed_at,
                                last_viewed_at,
                                first_view_source,
                                last_view_source,
                                view_count,
                                total_dwell_time_ms,
                                last_dwell_time_ms
                            )
                            VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
                            ON CONFLICT (user_id, social_post_id) DO UPDATE SET
                                last_viewed_at = excluded.last_viewed_at,
                                last_view_source = excluded.last_view_source,
                                view_count = user_post_views.view_count + 1,
                                total_dwell_time_ms = user_post_views.total_dwell_time_ms + excluded.last_dwell_time_ms,
                                last_dwell_time_ms = excluded.last_dwell_time_ms;
                            """,
                            (
                                str(uuid.uuid4()),
                                user_id,
                                item.social_post_id,
                                now,
                                now,
                                item.source,
                                item.source,
                                item.dwell_time_ms,
                                item.dwell_time_ms,
                            ),
                        )
                        connection.execute(
                            """
                            INSERT INTO social_post_stats (social_post_id, view_count)
                            VALUES (?, 1)
                            ON CONFLICT (social_post_id) DO UPDATE SET
                                view_count = social_post_stats.view_count + 1;
                            """,
                            (item.social_post_id,),
                        )
                report_failed = False
                break
            except sqlite3.OperationalError as error:
                if "database is locked" not in str(error).lower():
                    raise
                report_failed = True
                if retry_delay is None:
                    break
                time.sleep(retry_delay)

        if report_failed:
            logger.warning(
                "post view report skipped because the database is locked",
                extra={
                    "user_id": user_id,
                    "accepted_count": len(accepted_items),
                    "ignored_count": len(ignored_ids),
                },
            )
            raise_api_error(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "DATABASE_BUSY",
                "Database is busy. Please retry.",
            )
    return PostViewsBulkResponse(
        accepted_post_ids=[item.social_post_id for item in accepted_items],
        ignored_post_ids=ignored_ids,
    )


def hide_post(user_id: str, social_post_id: str, payload: PostHideCreate) -> PostHideResponse:
    with transaction() as connection:
        if social_post_id not in _accessible_post_ids(
            connection,
            user_id=user_id,
            post_ids=[social_post_id],
        ):
            raise_api_error(status.HTTP_404_NOT_FOUND, "POST_NOT_FOUND", "Post was not found.")
        now = utc_now_iso()
        existing = connection.execute(
            """
            SELECT user_post_hide_id
            FROM user_post_hides
            WHERE user_id = ? AND social_post_id = ?
            ORDER BY created_at DESC
            LIMIT 1;
            """,
            (user_id, social_post_id),
        ).fetchone()
        if existing:
            connection.execute(
                """
                UPDATE user_post_hides
                SET status = 'active',
                    source = ?,
                    reason = ?,
                    hidden_at = ?,
                    canceled_at = NULL
                WHERE user_post_hide_id = ?;
                """,
                (payload.source, payload.reason, now, existing["user_post_hide_id"]),
            )
        else:
            connection.execute(
                """
                INSERT INTO user_post_hides (
                    user_post_hide_id, user_id, social_post_id, status, source, reason, hidden_at
                )
                VALUES (?, ?, ?, 'active', ?, ?, ?);
                """,
                (str(uuid.uuid4()), user_id, social_post_id, payload.source, payload.reason, now),
            )
    return PostHideResponse(success=True, social_post_id=social_post_id)


def unhide_post(user_id: str, social_post_id: str) -> PostHideResponse:
    with transaction() as connection:
        connection.execute(
            """
            UPDATE user_post_hides
            SET status = 'canceled',
                canceled_at = ?
            WHERE user_id = ?
              AND social_post_id = ?
              AND status = 'active';
            """,
            (utc_now_iso(), user_id, social_post_id),
        )
    return PostHideResponse(success=True, social_post_id=social_post_id)
