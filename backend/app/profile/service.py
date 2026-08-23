from __future__ import annotations

import sqlite3
from typing import Any, Literal, cast

from backend.app.core.database import get_connection
from backend.app.tennis_activity_location import activity_location_from_row
from backend.app.profile.schemas import (
    ActivityAnalysisStatus,
    ActivityUploadStatus,
    ProfileContentActivity,
    ProfileContentLesson,
    ProfileContentPost,
    ProfileContentResponse,
    ProfileContentStats,
    ProfileContentVideoSummary,
)
from backend.app.uploads.thumbnails import ensure_video_thumbnail_path


def _row_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {key: row[key] for key in row.keys()}


def _fold_status(values: list[str], empty_value: str = "none") -> str:
    if not values:
        return empty_value
    unique_values = set(values)
    if len(unique_values) == 1:
        return values[0]
    return "mixed"


def _ensure_first_video_thumbnail(row: sqlite3.Row) -> str | None:
    if row["first_video_id"] is None:
        return None
    return ensure_video_thumbnail_path(
        {
            "video_id": row["first_video_id"],
            "video_path": row["first_video_path"],
            "thumbnail_path": row["first_thumbnail_path"],
            "upload_status": row["first_upload_status"],
        }
    )


def _row_to_video_summary(
    connection: sqlite3.Connection,
    row: sqlite3.Row | None,
) -> ProfileContentVideoSummary | None:
    if row is None or row["first_video_id"] is None:
        return None
    thumbnail_path = _ensure_first_video_thumbnail(row)
    return ProfileContentVideoSummary(
        video_id=row["first_video_id"],
        original_filename=row["first_original_filename"],
        video_path=row["first_video_path"],
        thumbnail_path=thumbnail_path,
        mime_type=row["first_mime_type"],
        file_size_bytes=row["first_file_size_bytes"],
        upload_status=row["first_upload_status"],
        analysis_status=row["first_analysis_status"],
        uploaded_at=row["first_uploaded_at"],
        created_at=row["first_video_created_at"],
    )


def _activity_statuses(
    connection: sqlite3.Connection,
    tennis_activity_id: str,
) -> tuple[ActivityUploadStatus, ActivityAnalysisStatus]:
    rows = connection.execute(
        """
        SELECT upload_status, analysis_status
        FROM videos
        WHERE tennis_activity_id = ?
          AND deleted_at IS NULL
        ORDER BY created_at ASC, video_id ASC;
        """,
        (tennis_activity_id,),
    ).fetchall()
    upload_status = _fold_status([row["upload_status"] for row in rows], "pending")
    analysis_status = _fold_status([row["analysis_status"] for row in rows], "none")
    return cast(ActivityUploadStatus, upload_status), cast(ActivityAnalysisStatus, analysis_status)


def _row_to_activity(
    connection: sqlite3.Connection,
    row: sqlite3.Row,
) -> ProfileContentActivity:
    upload_status, analysis_status = _activity_statuses(connection, row["tennis_activity_id"])
    return ProfileContentActivity(
        tennis_activity_id=row["tennis_activity_id"],
        owner_user_id=row["owner_user_id"],
        lesson_id=row["lesson_id"],
        title=row["title"],
        activity_type=row["activity_type"],
        default_visibility=row["default_visibility"],
        started_at=row["started_at"],
        ended_at=row["ended_at"],
        location_name=row["location_name"],
        location=activity_location_from_row(row, include_exact=True),
        note=row["note"],
        analysis_summary_status=row["analysis_summary_status"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        video_count=int(row["video_count"]),
        uploaded_video_count=int(row["uploaded_video_count"]),
        upload_status=upload_status,
        analysis_status=analysis_status,
        first_video=_row_to_video_summary(connection, row),
    )


def _select_activities(
    connection: sqlite3.Connection,
    user_id: str,
    *,
    kind: Literal["matches", "training"],
) -> list[ProfileContentActivity]:
    comparator = "=" if kind == "matches" else "<>"
    rows = connection.execute(
        f"""
        SELECT
            tennis_activities.*,
            COUNT(videos.video_id) AS video_count,
            SUM(CASE WHEN videos.upload_status = 'uploaded' THEN 1 ELSE 0 END) AS uploaded_video_count,
            first_video.video_id AS first_video_id,
            first_video.original_filename AS first_original_filename,
            first_video.video_path AS first_video_path,
            first_video.thumbnail_path AS first_thumbnail_path,
            first_video.mime_type AS first_mime_type,
            first_video.file_size_bytes AS first_file_size_bytes,
            first_video.upload_status AS first_upload_status,
            first_video.analysis_status AS first_analysis_status,
            first_video.uploaded_at AS first_uploaded_at,
            first_video.created_at AS first_video_created_at
        FROM tennis_activities
        LEFT JOIN videos ON videos.tennis_activity_id = tennis_activities.tennis_activity_id
            AND videos.deleted_at IS NULL
        LEFT JOIN videos AS first_video ON first_video.video_id = (
            SELECT inner_videos.video_id
            FROM videos AS inner_videos
            WHERE inner_videos.tennis_activity_id = tennis_activities.tennis_activity_id
              AND inner_videos.deleted_at IS NULL
            ORDER BY inner_videos.created_at ASC, inner_videos.video_id ASC
            LIMIT 1
        )
        WHERE tennis_activities.owner_user_id = ?
          AND tennis_activities.activity_type {comparator} 'match'
          AND tennis_activities.deleted_at IS NULL
        GROUP BY tennis_activities.tennis_activity_id
        ORDER BY
            COALESCE(tennis_activities.started_at, tennis_activities.created_at) DESC,
            tennis_activities.created_at DESC,
            tennis_activities.tennis_activity_id DESC
        LIMIT 100;
        """,
        (user_id,),
    ).fetchall()
    return [_row_to_activity(connection, row) for row in rows]


def _select_posts(connection: sqlite3.Connection, user_id: str) -> list[ProfileContentPost]:
    rows = connection.execute(
        """
        SELECT
            social_posts.*,
            COUNT(post_media.post_media_id) AS media_count,
            first_media.media_type AS first_media_type,
            first_media.image_path AS first_image_path,
            first_media_video.video_id AS first_video_id,
            first_media_video.video_path AS first_video_path,
            first_media_video.thumbnail_path AS first_video_thumbnail_path,
            first_media_video.upload_status AS first_video_upload_status
        FROM social_posts
        LEFT JOIN post_media ON post_media.social_post_id = social_posts.social_post_id
            AND post_media.deleted_at IS NULL
        LEFT JOIN post_media AS first_media ON first_media.post_media_id = (
            SELECT inner_media.post_media_id
            FROM post_media AS inner_media
            WHERE inner_media.social_post_id = social_posts.social_post_id
              AND inner_media.deleted_at IS NULL
            ORDER BY inner_media.sort_order ASC, inner_media.created_at ASC
            LIMIT 1
        )
        LEFT JOIN videos AS first_media_video ON first_media_video.video_id = first_media.video_id
        WHERE social_posts.author_user_id = ?
          AND social_posts.deleted_at IS NULL
          AND social_posts.status <> 'deleted'
        GROUP BY social_posts.social_post_id
        ORDER BY
            COALESCE(social_posts.published_at, social_posts.created_at) DESC,
            social_posts.created_at DESC,
            social_posts.social_post_id DESC
        LIMIT 100;
        """,
        (user_id,),
    ).fetchall()
    posts: list[ProfileContentPost] = []
    for row in rows:
        data = _row_dict(row)
        thumbnail_path = ensure_video_thumbnail_path(
            {
                "video_id": data["first_video_id"],
                "video_path": data["first_video_path"],
                "thumbnail_path": data["first_video_thumbnail_path"],
                "upload_status": data["first_video_upload_status"],
            }
        )
        if thumbnail_path:
            data["first_video_thumbnail_path"] = thumbnail_path
        data.pop("first_video_id", None)
        data.pop("first_video_upload_status", None)
        posts.append(ProfileContentPost(**data))
    return posts


def _select_lessons(connection: sqlite3.Connection, user_id: str) -> list[ProfileContentLesson]:
    rows = connection.execute(
        """
        SELECT *
        FROM (
            SELECT
                lessons.lesson_id,
                lessons.coach_user_id,
                lessons.title,
                lessons.lesson_type,
                lessons.status,
                lessons.started_at,
                lessons.ended_at,
                lessons.location_name,
                lessons.training_content,
                lessons.coach_summary,
                lessons.homework,
                lessons.next_focus,
                lessons.updated_at,
                'coach' AS role,
                COUNT(DISTINCT tennis_activities.tennis_activity_id) AS activity_count,
                COUNT(DISTINCT videos.video_id) AS video_count
            FROM lessons
            LEFT JOIN tennis_activities ON tennis_activities.lesson_id = lessons.lesson_id
                AND tennis_activities.deleted_at IS NULL
            LEFT JOIN videos ON videos.tennis_activity_id = tennis_activities.tennis_activity_id
                AND videos.deleted_at IS NULL
            WHERE lessons.coach_user_id = ?
              AND lessons.deleted_at IS NULL
            GROUP BY lessons.lesson_id

            UNION ALL

            SELECT
                lessons.lesson_id,
                lessons.coach_user_id,
                lessons.title,
                lessons.lesson_type,
                lessons.status,
                lessons.started_at,
                lessons.ended_at,
                lessons.location_name,
                lessons.training_content,
                lessons.coach_summary,
                lessons.homework,
                lessons.next_focus,
                lessons.updated_at,
                'student' AS role,
                COUNT(DISTINCT tennis_activities.tennis_activity_id) AS activity_count,
                COUNT(DISTINCT videos.video_id) AS video_count
            FROM lesson_students
            JOIN lessons ON lessons.lesson_id = lesson_students.lesson_id
            LEFT JOIN tennis_activities ON tennis_activities.lesson_id = lessons.lesson_id
                AND tennis_activities.deleted_at IS NULL
            LEFT JOIN videos ON videos.tennis_activity_id = tennis_activities.tennis_activity_id
                AND videos.deleted_at IS NULL
            WHERE lesson_students.student_user_id = ?
              AND lesson_students.deleted_at IS NULL
              AND lessons.deleted_at IS NULL
            GROUP BY lessons.lesson_id
        )
        ORDER BY started_at DESC, updated_at DESC, lesson_id DESC
        LIMIT 100;
        """,
        (user_id, user_id),
    ).fetchall()
    return [ProfileContentLesson(**_row_dict(row)) for row in rows]


def get_profile_content(user_id: str) -> ProfileContentResponse:
    with get_connection() as connection:
        posts = _select_posts(connection, user_id)
        matches = _select_activities(connection, user_id, kind="matches")
        training = _select_activities(connection, user_id, kind="training")
        courses = _select_lessons(connection, user_id)

    return ProfileContentResponse(
        stats=ProfileContentStats(
            posts=len(posts),
            matches=len(matches),
            training=len(training),
            courses=len(courses),
        ),
        posts=posts,
        matches=matches,
        training=training,
        courses=courses,
    )
