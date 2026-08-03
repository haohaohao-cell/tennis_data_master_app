from __future__ import annotations

import sqlite3
import uuid
from typing import Any

from fastapi import status

from backend.app.auth.service import raise_api_error
from backend.app.core.config import settings
from backend.app.core.database import get_connection, transaction
from backend.app.core.time import utc_now_iso
from backend.app.posts.schemas import (
    PostAuthor,
    PostCreate,
    PostDetailResponse,
    PostListResponse,
    PostMediaRecord,
    PostStatsRecord,
    PostUpdate,
    PostUploadIntentCreate,
    PostUploadIntentResponse,
    PostViewerState,
    SocialPostRecord,
)
from backend.app.uploads.schemas import VideoRecord
from backend.app.uploads.service import (
    delete_local_video_if_present,
    reserved_public_video_path,
    safe_video_suffix,
)
from backend.app.uploads.thumbnails import (
    delete_public_storage_file_if_present,
    ensure_video_thumbnail_records,
)


POST_MEDIA_LIMIT = 1
USER_SUPPORTED_VISIBILITIES = {"private", "friends", "followers", "public"}


def _row_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {key: row[key] for key in row.keys()}


def _row_to_post(row: sqlite3.Row) -> SocialPostRecord:
    return SocialPostRecord(**_row_dict(row))


def _row_to_media(row: sqlite3.Row) -> PostMediaRecord:
    return PostMediaRecord(**_row_dict(row))


def _row_to_video(row: sqlite3.Row | dict[str, Any]) -> VideoRecord:
    if isinstance(row, dict):
        return VideoRecord(**row)
    return VideoRecord(**_row_dict(row))


def _raise_not_found() -> None:
    raise_api_error(status.HTTP_404_NOT_FOUND, "POST_NOT_FOUND", "Post was not found.")


def _validate_user_visibility(visibility: str) -> None:
    if visibility not in USER_SUPPORTED_VISIBILITIES:
        raise_api_error(
            status.HTTP_400_BAD_REQUEST,
            "POST_VISIBILITY_NOT_SUPPORTED",
            "This post visibility is not available yet.",
        )


def _validate_post_location(scope: str, region: str | None, city: str | None) -> None:
    if scope == "region" and not region:
        raise_api_error(status.HTTP_400_BAD_REQUEST, "POST_LOCATION_REGION_REQUIRED", "A region is required.")
    if scope == "city" and not city:
        raise_api_error(status.HTTP_400_BAD_REQUEST, "POST_LOCATION_CITY_REQUIRED", "A city is required.")


def _validate_post_video_duration(duration_ms: int | None) -> None:
    if duration_ms is None:
        raise_api_error(
            status.HTTP_400_BAD_REQUEST,
            "POST_VIDEO_DURATION_REQUIRED",
            "Post video duration is required.",
        )
    if duration_ms > settings.max_post_video_duration_ms:
        raise_api_error(
            status.HTTP_400_BAD_REQUEST,
            "POST_VIDEO_TOO_LONG",
            "Post videos cannot be longer than the configured limit.",
        )


def _select_owned_post(
    connection: sqlite3.Connection,
    social_post_id: str,
    user_id: str,
) -> sqlite3.Row:
    row = connection.execute(
        """
        SELECT *
        FROM social_posts
        WHERE social_post_id = ?
          AND author_user_id = ?
          AND deleted_at IS NULL
          AND status <> 'deleted'
        LIMIT 1;
        """,
        (social_post_id, user_id),
    ).fetchone()
    if row is None:
        _raise_not_found()
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


def _select_readable_post(
    connection: sqlite3.Connection,
    social_post_id: str,
    viewer_user_id: str | None,
) -> sqlite3.Row:
    row = connection.execute(
        """
        SELECT social_posts.*
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
        _raise_not_found()
    author_user_id = row["author_user_id"]
    if viewer_user_id == author_user_id:
        return row
    if viewer_user_id is not None and _has_block_relation(connection, viewer_user_id, author_user_id):
        _raise_not_found()
    if row["visibility"] == "public":
        return row
    if viewer_user_id is None:
        _raise_not_found()
    if row["visibility"] == "followers" and _is_following(connection, viewer_user_id, author_user_id):
        return row
    if (
        row["visibility"] == "friends"
        and _is_following(connection, viewer_user_id, author_user_id)
        and _is_following(connection, author_user_id, viewer_user_id)
    ):
        return row
    _raise_not_found()
    return row


def _select_detail_post(
    connection: sqlite3.Connection,
    social_post_id: str,
    viewer_user_id: str | None,
) -> sqlite3.Row:
    row = connection.execute(
        """
        SELECT *
        FROM social_posts
        WHERE social_post_id = ?
          AND deleted_at IS NULL
          AND status <> 'deleted'
        LIMIT 1;
        """,
        (social_post_id,),
    ).fetchone()
    if row is None:
        _raise_not_found()

    author_user_id = row["author_user_id"]
    if viewer_user_id == author_user_id:
        return row
    return _select_readable_post(connection, social_post_id, viewer_user_id)


def _select_post_author(connection: sqlite3.Connection, author_user_id: str) -> PostAuthor:
    row = connection.execute(
        """
        SELECT user_id, nickname, avatar_path
        FROM users
        WHERE user_id = ?
          AND status = 'active'
          AND deleted_at IS NULL
        LIMIT 1;
        """,
        (author_user_id,),
    ).fetchone()
    if row is None:
        raise_api_error(status.HTTP_404_NOT_FOUND, "POST_AUTHOR_NOT_FOUND", "Post author was not found.")
    return PostAuthor(**_row_dict(row))


def _select_post_media(connection: sqlite3.Connection, social_post_id: str) -> list[sqlite3.Row]:
    return connection.execute(
        """
        SELECT *
        FROM post_media
        WHERE social_post_id = ?
          AND deleted_at IS NULL
        ORDER BY sort_order ASC, created_at ASC, post_media_id ASC;
        """,
        (social_post_id,),
    ).fetchall()


def _select_media_videos(
    connection: sqlite3.Connection,
    media_rows: list[sqlite3.Row],
) -> list[sqlite3.Row]:
    video_ids = [row["video_id"] for row in media_rows if row["video_id"]]
    if not video_ids:
        return []

    placeholders = ", ".join("?" for _ in video_ids)
    rows = connection.execute(
        f"""
        SELECT *
        FROM videos
        WHERE video_id IN ({placeholders})
          AND deleted_at IS NULL;
        """,
        video_ids,
    ).fetchall()
    rows_by_id = {row["video_id"]: row for row in rows}
    return [rows_by_id[video_id] for video_id in video_ids if video_id in rows_by_id]


def _select_viewer_state(
    connection: sqlite3.Connection,
    social_post_id: str,
    viewer_user_id: str | None,
) -> PostViewerState | None:
    if viewer_user_id is None:
        return None

    liked = connection.execute(
        """
        SELECT 1
        FROM post_reactions
        WHERE social_post_id = ?
          AND user_id = ?
          AND reaction_type = 'like'
          AND status = 'active'
        LIMIT 1;
        """,
        (social_post_id, viewer_user_id),
    ).fetchone()
    favorited = connection.execute(
        """
        SELECT 1
        FROM post_favorites
        WHERE social_post_id = ?
          AND user_id = ?
          AND status = 'active'
        LIMIT 1;
        """,
        (social_post_id, viewer_user_id),
    ).fetchone()
    return PostViewerState(is_liked=liked is not None, is_favorited=favorited is not None)


def _detail_from_post_row(
    connection: sqlite3.Connection,
    post_row: sqlite3.Row,
    *,
    persist_video_thumbnails: bool = False,
    viewer_user_id: str | None = None,
) -> PostDetailResponse:
    media_rows = _select_post_media(connection, post_row["social_post_id"])
    video_rows = _select_media_videos(connection, media_rows)
    video_records = ensure_video_thumbnail_records(
        connection,
        video_rows,
        persist_to_database=persist_video_thumbnails,
    )
    stats_row = connection.execute(
        """
        SELECT *
        FROM social_post_stats
        WHERE social_post_id = ?
        LIMIT 1;
        """,
        (post_row["social_post_id"],),
    ).fetchone()
    return PostDetailResponse(
        post=_row_to_post(post_row),
        author=_select_post_author(connection, post_row["author_user_id"]),
        media=[_row_to_media(row) for row in media_rows],
        videos=[_row_to_video(record) for record in video_records],
        stats=PostStatsRecord(**_row_dict(stats_row)) if stats_row else None,
        viewer_state=_select_viewer_state(
            connection,
            post_row["social_post_id"],
            viewer_user_id,
        ),
    )


def _select_activity_clip_video(
    connection: sqlite3.Connection,
    video_id: str,
    user_id: str,
) -> sqlite3.Row:
    row = connection.execute(
        """
        SELECT
            videos.*,
            tennis_activities.owner_user_id AS activity_owner_user_id,
            tennis_activities.tennis_activity_id AS source_tennis_activity_id
        FROM videos
        JOIN tennis_activities ON tennis_activities.tennis_activity_id = videos.tennis_activity_id
        WHERE videos.video_id = ?
          AND videos.deleted_at IS NULL
          AND tennis_activities.deleted_at IS NULL
        LIMIT 1;
        """,
        (video_id,),
    ).fetchone()
    if row is None:
        raise_api_error(status.HTTP_404_NOT_FOUND, "VIDEO_NOT_FOUND", "Video was not found.")
    if row["owner_user_id"] != user_id and row["activity_owner_user_id"] != user_id:
        raise_api_error(
            status.HTTP_403_FORBIDDEN,
            "POST_SOURCE_VIDEO_FORBIDDEN",
            "You can only publish clips from your own activity videos.",
        )
    if row["upload_status"] != "uploaded":
        raise_api_error(
            status.HTTP_409_CONFLICT,
            "POST_SOURCE_VIDEO_NOT_UPLOADED",
            "Only uploaded videos can be published as post clips.",
        )
    return row


def _validate_publishable_media(
    connection: sqlite3.Connection,
    post_row: sqlite3.Row,
    media_rows: list[sqlite3.Row],
) -> None:
    if not media_rows and not (post_row["title"] or post_row["content"]):
        raise_api_error(
            status.HTTP_409_CONFLICT,
            "POST_HAS_NO_CONTENT",
            "Post must contain text or media before publishing.",
        )
    if len(media_rows) > POST_MEDIA_LIMIT:
        raise_api_error(
            status.HTTP_409_CONFLICT,
            "POST_MEDIA_LIMIT_EXCEEDED",
            "This version supports one media item per post.",
        )

    for media_row in media_rows:
        if media_row["media_type"] not in {"video", "video_clip"}:
            continue
        video_row = connection.execute(
            """
            SELECT *
            FROM videos
            WHERE video_id = ?
              AND deleted_at IS NULL
            LIMIT 1;
            """,
            (media_row["video_id"],),
        ).fetchone()
        if video_row is None:
            raise_api_error(status.HTTP_404_NOT_FOUND, "POST_MEDIA_VIDEO_NOT_FOUND", "Post media video was not found.")
        if video_row["upload_status"] != "uploaded":
            raise_api_error(
                status.HTTP_409_CONFLICT,
                "POST_MEDIA_UPLOAD_INCOMPLETE",
                "All post videos must finish uploading before publishing.",
            )

        if media_row["media_type"] == "video":
            _validate_post_video_duration(video_row["video_duration_ms"])
        else:
            clip_start_ms = media_row["clip_start_ms"]
            clip_end_ms = media_row["clip_end_ms"]
            clip_duration_ms = clip_end_ms - clip_start_ms
            _validate_post_video_duration(clip_duration_ms)
            if video_row["video_duration_ms"] is not None and clip_end_ms > video_row["video_duration_ms"]:
                raise_api_error(
                    status.HTTP_400_BAD_REQUEST,
                    "POST_CLIP_EXCEEDS_VIDEO",
                    "Post clip cannot end after the source video duration.",
                )


def create_post_upload_intent(user_id: str, payload: PostUploadIntentCreate) -> PostUploadIntentResponse:
    _validate_user_visibility(payload.visibility)
    _validate_post_location(payload.location_scope, payload.location_region, payload.location_city)
    for video in payload.videos:
        _validate_post_video_duration(video.video_duration_ms)
        if video.file_size_bytes is not None and video.file_size_bytes > settings.max_upload_video_size_bytes:
            raise_api_error(
                status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                "VIDEO_FILE_TOO_LARGE",
                "Selected video exceeds the upload size limit.",
            )

    post_id = str(uuid.uuid4())
    try:
        with transaction() as connection:
            connection.execute(
                """
                INSERT INTO social_posts (
                    social_post_id,
                    author_user_id,
                    title,
                    content,
                    visibility,
                    location_scope,
                    location_region,
                    location_city,
                    status
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'draft');
                """,
                (
                    post_id,
                    user_id,
                    payload.title,
                    payload.content,
                    payload.visibility,
                    payload.location_scope,
                    payload.location_region,
                    payload.location_city,
                ),
            )
            connection.execute(
                "INSERT OR IGNORE INTO social_post_stats (social_post_id) VALUES (?);",
                (post_id,),
            )

            for index, video in enumerate(payload.videos):
                video_id = str(uuid.uuid4())
                post_media_id = str(uuid.uuid4())
                filename = f"{video_id}{safe_video_suffix(video.original_filename, video.mime_type)}"
                connection.execute(
                    """
                    INSERT INTO videos (
                        video_id,
                        tennis_activity_id,
                        owner_user_id,
                        uploader_user_id,
                        filename,
                        original_filename,
                        video_path,
                        mime_type,
                        file_size_bytes,
                        video_duration_ms,
                        visibility,
                        upload_status,
                        analysis_status,
                        captured_at
                    )
                    VALUES (?, NULL, ?, ?, ?, ?, ?, ?, ?, ?, 'private', 'pending', 'uploaded', ?);
                    """,
                    (
                        video_id,
                        user_id,
                        user_id,
                        filename,
                        video.original_filename,
                        reserved_public_video_path(f"posts/{post_id}", filename),
                        video.mime_type,
                        video.file_size_bytes,
                        video.video_duration_ms,
                        video.captured_at,
                    ),
                )
                connection.execute(
                    """
                    INSERT INTO post_media (
                        post_media_id,
                        social_post_id,
                        media_type,
                        video_id,
                        sort_order,
                        caption
                    )
                    VALUES (?, ?, 'video', ?, ?, ?);
                    """,
                    (post_media_id, post_id, video_id, index, video.caption),
                )

            detail = _detail_from_post_row(connection, _select_owned_post(connection, post_id, user_id))
            return PostUploadIntentResponse(
                **detail.model_dump(),
                max_video_duration_ms=settings.max_post_video_duration_ms,
            )
    except sqlite3.IntegrityError as error:
        raise_api_error(
            status.HTTP_400_BAD_REQUEST,
            "POST_UPLOAD_INTENT_INTEGRITY_ERROR",
            f"Post upload intent constraint failed: {error}",
        )


def create_post_from_activity_clip(user_id: str, payload: PostCreate) -> PostDetailResponse:
    _validate_user_visibility(payload.visibility)
    _validate_post_location(payload.location_scope, payload.location_region, payload.location_city)
    post_id = str(uuid.uuid4())
    now = utc_now_iso() if payload.status == "published" else None
    source_activity_id = payload.source_tennis_activity_id

    try:
        with transaction() as connection:
            for media in payload.media:
                video_row = _select_activity_clip_video(connection, media.video_id, user_id)
                clip_duration_ms = media.clip_end_ms - media.clip_start_ms
                _validate_post_video_duration(clip_duration_ms)
                if (
                    video_row["video_duration_ms"] is not None
                    and media.clip_end_ms > video_row["video_duration_ms"]
                ):
                    raise_api_error(
                        status.HTTP_400_BAD_REQUEST,
                        "POST_CLIP_EXCEEDS_VIDEO",
                        "Post clip cannot end after the source video duration.",
                    )
                if source_activity_id is None:
                    source_activity_id = video_row["source_tennis_activity_id"]
                elif source_activity_id != video_row["source_tennis_activity_id"]:
                    raise_api_error(
                        status.HTTP_400_BAD_REQUEST,
                        "POST_SOURCE_ACTIVITY_MISMATCH",
                        "Post source activity must match all selected clip videos.",
                    )
            connection.execute(
                """
                INSERT INTO social_posts (
                    social_post_id,
                    author_user_id,
                    source_tennis_activity_id,
                    title,
                    content,
                    visibility,
                    location_scope,
                    location_region,
                    location_city,
                    status,
                    published_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    post_id,
                    user_id,
                    source_activity_id,
                    payload.title,
                    payload.content,
                    payload.visibility,
                    payload.location_scope,
                    payload.location_region,
                    payload.location_city,
                    payload.status,
                    now,
                ),
            )
            connection.execute(
                "INSERT OR IGNORE INTO social_post_stats (social_post_id) VALUES (?);",
                (post_id,),
            )

            for index, media in enumerate(payload.media):
                connection.execute(
                    """
                    INSERT INTO post_media (
                        post_media_id,
                        social_post_id,
                        media_type,
                        video_id,
                        clip_start_ms,
                        clip_end_ms,
                        sort_order,
                        caption
                    )
                    VALUES (?, ?, 'video_clip', ?, ?, ?, ?, ?);
                    """,
                    (
                        str(uuid.uuid4()),
                        post_id,
                        media.video_id,
                        media.clip_start_ms,
                        media.clip_end_ms,
                        index,
                        media.caption,
                    ),
                )

            post_row = _select_owned_post(connection, post_id, user_id)
            if payload.status == "published":
                _validate_publishable_media(connection, post_row, _select_post_media(connection, post_id))
            return _detail_from_post_row(connection, post_row)
    except sqlite3.IntegrityError as error:
        raise_api_error(
            status.HTTP_400_BAD_REQUEST,
            "POST_CREATE_INTEGRITY_ERROR",
            f"Post constraint failed: {error}",
        )


def get_public_post(
    social_post_id: str,
    viewer_user_id: str | None = None,
) -> PostDetailResponse:
    with get_connection() as connection:
        return _detail_from_post_row(
            connection,
            _select_readable_post(connection, social_post_id, viewer_user_id),
            persist_video_thumbnails=False,
            viewer_user_id=viewer_user_id,
        )


def get_my_post(user_id: str, social_post_id: str) -> PostDetailResponse:
    with get_connection() as connection:
        return _detail_from_post_row(
            connection,
            _select_owned_post(connection, social_post_id, user_id),
            persist_video_thumbnails=False,
            viewer_user_id=user_id,
        )


def get_post_detail(social_post_id: str, viewer_user_id: str | None = None) -> PostDetailResponse:
    with get_connection() as connection:
        return _detail_from_post_row(
            connection,
            _select_detail_post(connection, social_post_id, viewer_user_id),
            persist_video_thumbnails=False,
            viewer_user_id=viewer_user_id,
        )


def list_public_feed(*, page: int, page_size: int) -> PostListResponse:
    offset = (page - 1) * page_size
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT *
            FROM social_posts
            WHERE status = 'published'
              AND visibility = 'public'
              AND deleted_at IS NULL
            ORDER BY published_at DESC, created_at DESC, social_post_id DESC
            LIMIT ? OFFSET ?;
            """,
            (page_size, offset),
        ).fetchall()
        return PostListResponse(
            items=[
                _detail_from_post_row(connection, row, persist_video_thumbnails=False)
                for row in rows
            ],
            page=page,
            page_size=page_size,
        )


def list_my_posts(user_id: str, *, page: int, page_size: int) -> PostListResponse:
    offset = (page - 1) * page_size
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT *
            FROM social_posts
            WHERE author_user_id = ?
              AND deleted_at IS NULL
              AND status <> 'deleted'
            ORDER BY COALESCE(published_at, created_at) DESC, created_at DESC, social_post_id DESC
            LIMIT ? OFFSET ?;
            """,
            (user_id, page_size, offset),
        ).fetchall()
        return PostListResponse(
            items=[
                _detail_from_post_row(connection, row, persist_video_thumbnails=False)
                for row in rows
            ],
            page=page,
            page_size=page_size,
        )


def update_post(user_id: str, social_post_id: str, payload: PostUpdate) -> PostDetailResponse:
    fields = payload.model_dump(exclude_unset=True)
    if "visibility" in fields and fields["visibility"] is not None:
        _validate_user_visibility(fields["visibility"])
    if any(key in fields for key in ("location_scope", "location_region", "location_city")):
        with get_connection() as connection:
            current = _select_owned_post(connection, social_post_id, user_id)
        _validate_post_location(
            fields.get("location_scope", current["location_scope"]),
            fields.get("location_region", current["location_region"]),
            fields.get("location_city", current["location_city"]),
        )

    assignments: list[str] = []
    params: list[Any] = []
    allowed_columns = (
        "title",
        "content",
        "visibility",
        "location_scope",
        "location_region",
        "location_city",
    )
    for column in allowed_columns:
        if column in fields:
            assignments.append(f"{column} = ?")
            params.append(fields[column])

    if not assignments:
        raise_api_error(status.HTTP_400_BAD_REQUEST, "POST_UPDATE_EMPTY", "At least one field is required.")

    try:
        with transaction() as connection:
            _select_owned_post(connection, social_post_id, user_id)
            params.append(social_post_id)
            connection.execute(
                f"""
                UPDATE social_posts
                SET {", ".join(assignments)}
                WHERE social_post_id = ?;
                """,
                params,
            )
            return _detail_from_post_row(connection, _select_owned_post(connection, social_post_id, user_id))
    except sqlite3.IntegrityError as error:
        raise_api_error(
            status.HTTP_400_BAD_REQUEST,
            "POST_UPDATE_INTEGRITY_ERROR",
            f"Post update constraint failed: {error}",
        )


def publish_post(user_id: str, social_post_id: str) -> PostDetailResponse:
    with transaction() as connection:
        post_row = _select_owned_post(connection, social_post_id, user_id)
        media_rows = _select_post_media(connection, social_post_id)
        _validate_publishable_media(connection, post_row, media_rows)
        published_at = post_row["published_at"] or utc_now_iso()
        connection.execute(
            """
            UPDATE social_posts
            SET status = 'published',
                published_at = ?,
                deleted_at = NULL
            WHERE social_post_id = ?;
            """,
            (published_at, social_post_id),
        )
        connection.execute(
            "INSERT OR IGNORE INTO social_post_stats (social_post_id) VALUES (?);",
            (social_post_id,),
        )
        return _detail_from_post_row(connection, _select_owned_post(connection, social_post_id, user_id))


def delete_post(user_id: str, social_post_id: str) -> None:
    now = utc_now_iso()
    local_media_paths: list[tuple[str, str | None]] = []
    with transaction() as connection:
        post_row = _select_owned_post(connection, social_post_id, user_id)
        is_draft = post_row["status"] == "draft"
        if is_draft:
            rows = connection.execute(
                """
                SELECT videos.video_id, videos.video_path, videos.thumbnail_path
                FROM post_media
                JOIN videos ON videos.video_id = post_media.video_id
                WHERE post_media.social_post_id = ?
                  AND post_media.deleted_at IS NULL
                  AND videos.tennis_activity_id IS NULL
                  AND videos.deleted_at IS NULL;
                """,
                (social_post_id,),
            ).fetchall()
            local_media_paths = [(row["video_path"], row["thumbnail_path"]) for row in rows]
            video_ids = [row["video_id"] for row in rows]
            if video_ids:
                placeholders = ", ".join("?" for _ in video_ids)
                connection.execute(
                    f"""
                    UPDATE videos
                    SET upload_status = 'canceled',
                        analysis_status = 'canceled',
                        deleted_at = ?
                    WHERE video_id IN ({placeholders});
                    """,
                    [now, *video_ids],
                )
            connection.execute(
                """
                UPDATE post_media
                SET deleted_at = ?
                WHERE social_post_id = ?
                  AND deleted_at IS NULL;
                """,
                (now, social_post_id),
            )

        connection.execute(
            """
            UPDATE social_posts
            SET status = 'deleted',
                deleted_at = ?
            WHERE social_post_id = ?;
            """,
            (now, social_post_id),
        )

    for video_path, thumbnail_path in local_media_paths:
        delete_local_video_if_present(video_path)
        delete_public_storage_file_if_present(thumbnail_path)
