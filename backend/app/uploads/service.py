from __future__ import annotations

import hashlib
from pathlib import Path
import sqlite3
import uuid
from typing import Any
from urllib.parse import unquote

from fastapi import UploadFile, status

from backend.app.auth.service import raise_api_error
from backend.app.core.config import settings
from backend.app.core.database import get_connection, transaction
from backend.app.core.time import utc_now_iso
from backend.app.tennis_activity_location import (
    activity_location_display_name,
    activity_location_from_row,
)
from backend.app.uploads.schemas import (
    ActivityDetailLesson,
    ActivityDetailPermissions,
    ActivityDetailResponse,
    ActivityDetailSummary,
    LessonOption,
    TennisActivityCreate,
    TennisActivityRecord,
    UploadCancelResponse,
    UploadCompleteResponse,
    UploadIntentCreate,
    UploadIntentResponse,
    VideoFileUploadResponse,
    VideoRecord,
)
from backend.app.uploads.thumbnails import (
    delete_public_storage_file_if_present,
    ensure_video_thumbnail_path,
    ensure_video_thumbnail_records,
)


ALLOWED_VIDEO_SUFFIXES = {".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi"}
ALLOWED_VIDEO_CONTENT_TYPES = {
    "application/quicktime",
    "application/x-quicktime",
    "application/octet-stream",
}
LESSON_VISIBILITIES = {"lesson_coach", "lesson_participants"}
STREAM_CHUNK_SIZE = 1024 * 1024
VIDEO_SUFFIX_BY_MIME_TYPE = {
    "video/mp4": ".mp4",
    "video/quicktime": ".mov",
    "video/x-m4v": ".m4v",
    "video/webm": ".webm",
    "video/x-matroska": ".mkv",
    "video/x-msvideo": ".avi",
    "application/quicktime": ".mov",
    "application/x-quicktime": ".mov",
}


def _row_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {key: row[key] for key in row.keys()}


def _row_to_video(row: sqlite3.Row) -> VideoRecord:
    return VideoRecord(**_row_dict(row))


def _row_to_activity(row: sqlite3.Row, *, include_exact_location: bool = True) -> TennisActivityRecord:
    data = _row_dict(row)
    data["location"] = activity_location_from_row(row, include_exact=include_exact_location)
    return TennisActivityRecord(**data)


def _activity_location_values(payload: UploadIntentCreate | TennisActivityCreate) -> dict[str, object | None]:
    location = payload.location
    source = location.source if location else ("manual_legacy" if payload.location_name else "unavailable")
    return {
        "location_name": activity_location_display_name(location, payload.location_name),
        "location_source": source,
        "location_latitude": location.latitude if location else None,
        "location_longitude": location.longitude if location else None,
        "location_accuracy_m": location.accuracy_m if location else None,
        "location_captured_at": location.captured_at if location else None,
        "location_country_code": location.country_code if location else None,
        "location_region": location.region if location else None,
        "location_city": location.city if location else None,
        "location_district": location.district if location else None,
        "location_address_label": location.address_label if location else None,
        "location_coordinate_system": location.coordinate_system if location else None,
    }


def _row_to_activity_detail_lesson(row: sqlite3.Row | None) -> ActivityDetailLesson | None:
    if row is None:
        return None
    return ActivityDetailLesson(**_row_dict(row))


def _raise_not_found(code: str, message: str) -> None:
    raise_api_error(status.HTTP_404_NOT_FOUND, code, message)


def _select_activity(connection: sqlite3.Connection, tennis_activity_id: str) -> sqlite3.Row:
    row = connection.execute(
        """
        SELECT *
        FROM tennis_activities
        WHERE tennis_activity_id = ?
        LIMIT 1;
        """,
        (tennis_activity_id,),
    ).fetchone()
    if row is None:
        _raise_not_found("TENNIS_ACTIVITY_NOT_FOUND", "Tennis activity was not found.")
    return row


def _select_owned_activity(
    connection: sqlite3.Connection,
    tennis_activity_id: str,
    user_id: str,
) -> sqlite3.Row:
    row = connection.execute(
        """
        SELECT *
        FROM tennis_activities
        WHERE tennis_activity_id = ?
          AND owner_user_id = ?
          AND deleted_at IS NULL
        LIMIT 1;
        """,
        (tennis_activity_id, user_id),
    ).fetchone()
    if row is None:
        _raise_not_found("TENNIS_ACTIVITY_NOT_FOUND", "Tennis activity was not found.")
    return row


def _select_upload_video(
    connection: sqlite3.Connection,
    video_id: str,
    uploader_user_id: str,
) -> sqlite3.Row:
    row = connection.execute(
        """
        SELECT *
        FROM videos
        WHERE video_id = ?
          AND uploader_user_id = ?
          AND deleted_at IS NULL
        LIMIT 1;
        """,
        (video_id, uploader_user_id),
    ).fetchone()
    if row is None:
        _raise_not_found("VIDEO_NOT_FOUND", "Video upload was not found.")
    return row


def _select_activity_videos(connection: sqlite3.Connection, tennis_activity_id: str) -> list[sqlite3.Row]:
    return connection.execute(
        """
        SELECT *
        FROM videos
        WHERE tennis_activity_id = ?
          AND deleted_at IS NULL
        ORDER BY created_at ASC, video_id ASC;
        """,
        (tennis_activity_id,),
    ).fetchall()


def _select_activity_lesson_context(
    connection: sqlite3.Connection,
    lesson_id: str | None,
    user_id: str,
) -> sqlite3.Row | None:
    if lesson_id is None:
        return None

    row = connection.execute(
        """
        SELECT
            lessons.lesson_id,
            lessons.coach_user_id,
            lessons.title,
            lessons.lesson_type,
            lessons.status,
            lessons.started_at,
            lessons.ended_at,
            lessons.location_name,
            lessons.court_surface,
            lessons.training_content,
            lessons.coach_summary,
            lessons.homework,
            lessons.next_focus,
            CASE
                WHEN lessons.coach_user_id = ? THEN 'coach'
                WHEN lesson_students.student_user_id IS NOT NULL THEN 'student'
                ELSE NULL
            END AS viewer_role
        FROM lessons
        LEFT JOIN lesson_students ON lesson_students.lesson_id = lessons.lesson_id
            AND lesson_students.student_user_id = ?
            AND lesson_students.deleted_at IS NULL
        WHERE lessons.lesson_id = ?
          AND lessons.deleted_at IS NULL
        LIMIT 1;
        """,
        (user_id, user_id, lesson_id),
    ).fetchone()
    if row is None:
        _raise_not_found("LESSON_NOT_FOUND", "Lesson was not found.")
    return row


def _effective_video_visibility(activity_row: sqlite3.Row, video_row: sqlite3.Row) -> str:
    video_visibility = video_row["visibility"]
    if video_visibility == "inherit":
        return activity_row["default_visibility"]
    return video_visibility


def _can_view_video(
    *,
    activity_row: sqlite3.Row,
    lesson_row: sqlite3.Row | None,
    user_id: str,
    video_row: sqlite3.Row,
) -> bool:
    if video_row["owner_user_id"] == user_id or activity_row["owner_user_id"] == user_id:
        return True

    visibility = _effective_video_visibility(activity_row, video_row)
    if visibility == "public":
        return True

    viewer_role = lesson_row["viewer_role"] if lesson_row is not None else None
    if viewer_role == "coach" and visibility in {"lesson_coach", "lesson_participants"}:
        return True
    if viewer_role == "student" and visibility == "lesson_participants":
        return True

    return False


def _can_view_activity(
    *,
    activity_row: sqlite3.Row,
    lesson_row: sqlite3.Row | None,
    user_id: str,
    all_video_rows: list[sqlite3.Row],
) -> bool:
    if activity_row["owner_user_id"] == user_id:
        return True
    if activity_row["default_visibility"] == "public":
        return True

    viewer_role = lesson_row["viewer_role"] if lesson_row is not None else None
    if viewer_role == "coach" and activity_row["default_visibility"] in {
        "lesson_coach",
        "lesson_participants",
    }:
        return True
    if viewer_role == "student" and activity_row["default_visibility"] == "lesson_participants":
        return True

    return any(
        _can_view_video(
            activity_row=activity_row,
            lesson_row=lesson_row,
            user_id=user_id,
            video_row=video_row,
        )
        for video_row in all_video_rows
    )


def _activity_status(values: list[str], *, empty_value: str) -> str:
    if not values:
        return empty_value
    unique_values = set(values)
    if len(unique_values) == 1:
        return values[0]
    return "mixed"


def _activity_detail_summary(video_rows: list[sqlite3.Row]) -> ActivityDetailSummary:
    return ActivityDetailSummary(
        video_count=len(video_rows),
        uploaded_video_count=sum(1 for row in video_rows if row["upload_status"] == "uploaded"),
        upload_status=_activity_status(
            [row["upload_status"] for row in video_rows],
            empty_value="pending",
        ),
        analysis_status=_activity_status(
            [row["analysis_status"] for row in video_rows],
            empty_value="none",
        ),
    )


def _ensure_active_coach(connection: sqlite3.Connection, user_id: str) -> None:
    row = connection.execute(
        """
        SELECT 1
        FROM coach_profiles
        WHERE user_id = ?
          AND status = 'active'
        LIMIT 1;
        """,
        (user_id,),
    ).fetchone()
    if row is None:
        raise_api_error(
            status.HTTP_403_FORBIDDEN,
            "COACH_PERMISSION_REQUIRED",
            "Only active coaches can upload coach demo videos.",
        )


def _lesson_role(connection: sqlite3.Connection, lesson_id: str, user_id: str) -> str:
    lesson_row = connection.execute(
        """
        SELECT *
        FROM lessons
        WHERE lesson_id = ?
          AND deleted_at IS NULL
        LIMIT 1;
        """,
        (lesson_id,),
    ).fetchone()
    if lesson_row is None:
        _raise_not_found("LESSON_NOT_FOUND", "Lesson was not found.")
    if lesson_row["coach_user_id"] == user_id:
        return "coach"

    student_row = connection.execute(
        """
        SELECT 1
        FROM lesson_students
        WHERE lesson_id = ?
          AND student_user_id = ?
          AND deleted_at IS NULL
        LIMIT 1;
        """,
        (lesson_id, user_id),
    ).fetchone()
    if student_row is not None:
        return "student"

    raise_api_error(
        status.HTTP_403_FORBIDDEN,
        "LESSON_UPLOAD_PERMISSION_REQUIRED",
        "You can only upload videos to lessons you participate in.",
    )
    return "student"


def _validate_upload_intent(
    connection: sqlite3.Connection,
    user_id: str,
    payload: UploadIntentCreate,
) -> None:
    if payload.default_visibility in LESSON_VISIBILITIES and not payload.lesson_id:
        raise_api_error(
            status.HTTP_400_BAD_REQUEST,
            "LESSON_VISIBILITY_REQUIRES_LESSON",
            "Lesson visibility requires lesson_id.",
        )

    if payload.activity_type == "lesson_practice" and not payload.lesson_id:
        raise_api_error(
            status.HTTP_400_BAD_REQUEST,
            "LESSON_REQUIRED_FOR_LESSON_PRACTICE",
            "lesson_practice uploads must be linked to a lesson.",
        )

    if payload.activity_type == "coach_demo":
        _ensure_active_coach(connection, user_id)

    if payload.lesson_id:
        role = _lesson_role(connection, payload.lesson_id, user_id)
        if payload.activity_type == "coach_demo" and role != "coach":
            raise_api_error(
                status.HTTP_403_FORBIDDEN,
                "LESSON_COACH_REQUIRED",
                "Only the lesson coach can upload coach demo videos for this lesson.",
            )

    if payload.opponent_user_id == user_id:
        raise_api_error(
            status.HTTP_400_BAD_REQUEST,
            "OPPONENT_CANNOT_BE_OWNER",
            "opponent_user_id cannot equal owner_user_id.",
        )

    for video in payload.videos:
        if video.visibility in LESSON_VISIBILITIES and not payload.lesson_id:
            raise_api_error(
                status.HTTP_400_BAD_REQUEST,
                "LESSON_VISIBILITY_REQUIRES_LESSON",
                "Lesson visibility requires lesson_id.",
            )
        if video.file_size_bytes is not None and video.file_size_bytes > settings.max_upload_video_size_bytes:
            raise_api_error(
                status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                "VIDEO_FILE_TOO_LARGE",
                "One or more selected videos exceed the upload size limit.",
            )


def _validate_activity_create(
    connection: sqlite3.Connection,
    user_id: str,
    payload: TennisActivityCreate,
) -> None:
    if payload.default_visibility in LESSON_VISIBILITIES and not payload.lesson_id:
        raise_api_error(
            status.HTTP_400_BAD_REQUEST,
            "LESSON_VISIBILITY_REQUIRES_LESSON",
            "Lesson visibility requires lesson_id.",
        )

    if payload.lesson_id and payload.activity_type not in {"lesson_practice", "coach_demo"}:
        raise_api_error(
            status.HTTP_400_BAD_REQUEST,
            "LESSON_ACTIVITY_TYPE_REQUIRED",
            "Lesson activities must use lesson_practice or coach_demo activity_type.",
        )

    if payload.activity_type == "lesson_practice" and not payload.lesson_id:
        raise_api_error(
            status.HTTP_400_BAD_REQUEST,
            "LESSON_REQUIRED_FOR_LESSON_PRACTICE",
            "lesson_practice activities must be linked to a lesson.",
        )

    if payload.activity_type == "coach_demo":
        _ensure_active_coach(connection, user_id)

    if payload.lesson_id:
        role = _lesson_role(connection, payload.lesson_id, user_id)
        if payload.activity_type == "coach_demo" and role != "coach":
            raise_api_error(
                status.HTTP_403_FORBIDDEN,
                "LESSON_COACH_REQUIRED",
                "Only the lesson coach can create coach demo activities for this lesson.",
            )

    if payload.opponent_user_id == user_id:
        raise_api_error(
            status.HTTP_400_BAD_REQUEST,
            "OPPONENT_CANNOT_BE_OWNER",
            "opponent_user_id cannot equal owner_user_id.",
        )


def _normalize_content_type(content_type: str | None) -> str:
    return (content_type or "").split(";", 1)[0].strip().lower()


def safe_video_suffix(original_filename: str, mime_type: str | None = None) -> str:
    normalized = unquote(original_filename.replace("\\", "/").rsplit("/", 1)[-1])
    normalized = normalized.split("?", 1)[0].split("#", 1)[0]
    suffix = Path(normalized).suffix.lower()
    if suffix in ALLOWED_VIDEO_SUFFIXES:
        return suffix
    normalized_mime_type = _normalize_content_type(mime_type)
    if normalized_mime_type in VIDEO_SUFFIX_BY_MIME_TYPE:
        return VIDEO_SUFFIX_BY_MIME_TYPE[normalized_mime_type]
    return ".mp4"


def _safe_video_suffix(original_filename: str, mime_type: str | None = None) -> str:
    return safe_video_suffix(original_filename, mime_type)


def reserved_public_video_path(folder: str, filename: str) -> str:
    normalized_folder = "/".join(
        part
        for part in folder.replace("\\", "/").split("/")
        if part and part not in {".", ".."}
    )
    return f"{settings.public_video_path_prefix.rstrip('/')}/{normalized_folder}/{filename}"


def _reserved_public_video_path(activity_id: str, filename: str) -> str:
    return reserved_public_video_path(activity_id, filename)


def _local_path_for_public_video_path(video_path: str) -> Path:
    prefix = settings.public_video_path_prefix.rstrip("/") + "/"
    if not video_path.startswith(prefix):
        raise_api_error(
            status.HTTP_400_BAD_REQUEST,
            "INVALID_VIDEO_STORAGE_PATH",
            "Video storage path is not managed by this service.",
        )

    relative_path = video_path[len(prefix) :]
    if not relative_path or ".." in Path(relative_path).parts:
        raise_api_error(
            status.HTTP_400_BAD_REQUEST,
            "INVALID_VIDEO_STORAGE_PATH",
            "Video storage path is invalid.",
        )

    storage_root = settings.video_storage_dir.resolve()
    local_path = (storage_root / relative_path).resolve()
    try:
        local_path.relative_to(storage_root)
    except ValueError:
        raise_api_error(
            status.HTTP_400_BAD_REQUEST,
            "INVALID_VIDEO_STORAGE_PATH",
            "Video storage path escapes the configured storage directory.",
        )
    return local_path


def _mark_video_failed(video_id: str, message: str) -> None:
    with transaction() as connection:
        connection.execute(
            """
            UPDATE videos
            SET upload_status = 'failed',
                upload_error_message = ?
            WHERE video_id = ?;
            """,
            (message[:500], video_id),
        )


def delete_local_video_if_present(video_path: str) -> None:
    local_path = _local_path_for_public_video_path(video_path)
    if local_path.exists() and local_path.is_file():
        local_path.unlink()


def _delete_local_video_if_present(video_path: str) -> None:
    delete_local_video_if_present(video_path)


def _select_draft_post_video_upload(
    connection: sqlite3.Connection,
    video_id: str,
    user_id: str,
) -> sqlite3.Row:
    row = connection.execute(
        """
        SELECT social_posts.*
        FROM post_media
        JOIN social_posts ON social_posts.social_post_id = post_media.social_post_id
        WHERE post_media.video_id = ?
          AND post_media.deleted_at IS NULL
          AND social_posts.author_user_id = ?
          AND social_posts.status = 'draft'
          AND social_posts.deleted_at IS NULL
        LIMIT 1;
        """,
        (video_id, user_id),
    ).fetchone()
    if row is None:
        _raise_not_found("VIDEO_NOT_FOUND", "Video upload was not found.")
    return row


def create_activity_record(user_id: str, payload: TennisActivityCreate) -> TennisActivityRecord:
    activity_id = str(uuid.uuid4())
    location_values = _activity_location_values(payload)

    try:
        with transaction() as connection:
            _validate_activity_create(connection, user_id, payload)
            connection.execute(
                """
                INSERT INTO tennis_activities (
                    tennis_activity_id,
                    owner_user_id,
                    lesson_id,
                    title,
                    activity_type,
                    default_visibility,
                    started_at,
                    ended_at,
                    location_name,
                    location_source,
                    location_latitude,
                    location_longitude,
                    location_accuracy_m,
                    location_captured_at,
                    location_country_code,
                    location_region,
                    location_city,
                    location_district,
                    location_address_label,
                    location_coordinate_system,
                    court_surface,
                    opponent_user_id,
                    opponent_name,
                    note,
                    analysis_summary_status
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL);
                """,
                (
                    activity_id,
                    user_id,
                    payload.lesson_id,
                    payload.title,
                    payload.activity_type,
                    payload.default_visibility,
                    payload.started_at,
                    payload.ended_at,
                    location_values["location_name"],
                    location_values["location_source"],
                    location_values["location_latitude"],
                    location_values["location_longitude"],
                    location_values["location_accuracy_m"],
                    location_values["location_captured_at"],
                    location_values["location_country_code"],
                    location_values["location_region"],
                    location_values["location_city"],
                    location_values["location_district"],
                    location_values["location_address_label"],
                    location_values["location_coordinate_system"],
                    payload.court_surface,
                    payload.opponent_user_id,
                    payload.opponent_name,
                    payload.note,
                ),
            )
            return _row_to_activity(_select_owned_activity(connection, activity_id, user_id))
    except sqlite3.IntegrityError as error:
        raise_api_error(
            status.HTTP_400_BAD_REQUEST,
            "TENNIS_ACTIVITY_INTEGRITY_ERROR",
            f"Tennis activity constraint failed: {error}",
        )


def _validate_upload_file(video_row: sqlite3.Row, file: UploadFile) -> None:
    content_type = _normalize_content_type(file.content_type)
    if content_type and not content_type.startswith("video/") and content_type not in ALLOWED_VIDEO_CONTENT_TYPES:
        raise_api_error(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            "UNSUPPORTED_VIDEO_TYPE",
            "Only video files can be uploaded.",
        )

    suffix = _safe_video_suffix(
        video_row["original_filename"] or video_row["filename"],
        file.content_type or video_row["mime_type"],
    )
    if suffix not in ALLOWED_VIDEO_SUFFIXES:
        raise_api_error(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            "UNSUPPORTED_VIDEO_EXTENSION",
            "Only common video file formats are supported.",
        )


def create_upload_intent(user_id: str, payload: UploadIntentCreate) -> UploadIntentResponse:
    activity_id = str(uuid.uuid4())
    location_values = _activity_location_values(payload)

    try:
        with transaction() as connection:
            _validate_upload_intent(connection, user_id, payload)
            connection.execute(
                """
                INSERT INTO tennis_activities (
                    tennis_activity_id,
                    owner_user_id,
                    lesson_id,
                    title,
                    activity_type,
                    default_visibility,
                    started_at,
                    ended_at,
                    location_name,
                    location_source,
                    location_latitude,
                    location_longitude,
                    location_accuracy_m,
                    location_captured_at,
                    location_country_code,
                    location_region,
                    location_city,
                    location_district,
                    location_address_label,
                    location_coordinate_system,
                    court_surface,
                    opponent_user_id,
                    opponent_name,
                    note,
                    analysis_summary_status
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending');
                """,
                (
                    activity_id,
                    user_id,
                    payload.lesson_id,
                    payload.title,
                    payload.activity_type,
                    payload.default_visibility,
                    payload.started_at,
                    payload.ended_at,
                    location_values["location_name"],
                    location_values["location_source"],
                    location_values["location_latitude"],
                    location_values["location_longitude"],
                    location_values["location_accuracy_m"],
                    location_values["location_captured_at"],
                    location_values["location_country_code"],
                    location_values["location_region"],
                    location_values["location_city"],
                    location_values["location_district"],
                    location_values["location_address_label"],
                    location_values["location_coordinate_system"],
                    payload.court_surface,
                    payload.opponent_user_id,
                    payload.opponent_name,
                    payload.note,
                ),
            )

            for video in payload.videos:
                video_id = str(uuid.uuid4())
                filename = f"{video_id}{_safe_video_suffix(video.original_filename, video.mime_type)}"
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
                        camera_view_angle,
                        camera_view_position,
                        player_a_name,
                        player_b_name,
                        primary_player_slot,
                        visibility,
                        upload_status,
                        analysis_status,
                        captured_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', 'uploaded', ?);
                    """,
                    (
                        video_id,
                        activity_id,
                        user_id,
                        user_id,
                        filename,
                        video.original_filename,
                        _reserved_public_video_path(activity_id, filename),
                        video.mime_type,
                        video.file_size_bytes,
                        video.camera_view_angle,
                        video.camera_view_position,
                        video.player_a_name,
                        video.player_b_name,
                        video.primary_player_slot,
                        video.visibility,
                        video.captured_at,
                    ),
                )

            activity = _row_to_activity(_select_owned_activity(connection, activity_id, user_id))
            videos = [_row_to_video(row) for row in _select_activity_videos(connection, activity_id)]
            return UploadIntentResponse(activity=activity, videos=videos)
    except sqlite3.IntegrityError as error:
        raise_api_error(
            status.HTTP_400_BAD_REQUEST,
            "UPLOAD_INTENT_INTEGRITY_ERROR",
            f"Upload intent constraint failed: {error}",
        )


async def upload_video_file(user_id: str, video_id: str, file: UploadFile) -> VideoFileUploadResponse:
    with transaction() as connection:
        video_row = _select_upload_video(connection, video_id, user_id)
        if video_row["upload_status"] == "canceled":
            raise_api_error(
                status.HTTP_409_CONFLICT,
                "VIDEO_UPLOAD_CANCELED",
                "Canceled videos cannot be uploaded.",
            )
        if video_row["upload_status"] == "uploaded":
            raise_api_error(
                status.HTTP_409_CONFLICT,
                "VIDEO_ALREADY_UPLOADED",
                "Uploaded videos cannot be overwritten.",
            )
        if video_row["tennis_activity_id"] is None:
            _select_draft_post_video_upload(connection, video_id, user_id)
        else:
            _select_owned_activity(connection, video_row["tennis_activity_id"], user_id)
        _validate_upload_file(video_row, file)
        connection.execute(
            """
            UPDATE videos
            SET upload_status = 'uploading',
                upload_error_message = NULL
            WHERE video_id = ?;
            """,
            (video_id,),
        )

    local_path = _local_path_for_public_video_path(video_row["video_path"])
    local_path.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    bytes_written = 0

    try:
        with local_path.open("wb") as output:
            while True:
                chunk = await file.read(STREAM_CHUNK_SIZE)
                if not chunk:
                    break
                bytes_written += len(chunk)
                if bytes_written > settings.max_upload_video_size_bytes:
                    output.close()
                    _delete_local_video_if_present(video_row["video_path"])
                    _mark_video_failed(video_id, "Video file is too large.")
                    raise_api_error(
                        status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        "VIDEO_FILE_TOO_LARGE",
                        "Video file exceeds the upload size limit.",
                    )
                digest.update(chunk)
                output.write(chunk)
    except Exception as error:
        if local_path.exists():
            local_path.unlink()
        if error.__class__.__name__ != "HTTPException":
            _mark_video_failed(video_id, "Video upload failed while saving the file.")
        raise
    finally:
        await file.close()

    video_data = _row_dict(video_row)
    video_data["upload_status"] = "uploaded"
    thumbnail_path = ensure_video_thumbnail_path(video_data)
    now = utc_now_iso()
    with transaction() as connection:
        connection.execute(
            """
            UPDATE videos
            SET upload_status = 'uploaded',
                upload_error_message = NULL,
                uploaded_at = ?,
                file_size_bytes = ?,
                file_hash = ?,
                mime_type = COALESCE(?, mime_type),
                thumbnail_path = COALESCE(?, thumbnail_path)
            WHERE video_id = ?;
            """,
            # Mobile media libraries can report the original asset size, while
            # multipart upload sends the exported file bytes. Persist the bytes
            # actually received by the backend.
            (now, bytes_written, digest.hexdigest(), file.content_type, thumbnail_path, video_id),
        )
        video = _row_to_video(_select_upload_video(connection, video_id, user_id))

    return VideoFileUploadResponse(video=video)


def complete_activity_upload(user_id: str, tennis_activity_id: str) -> UploadCompleteResponse:
    with transaction() as connection:
        activity_row = _select_owned_activity(connection, tennis_activity_id, user_id)
        video_rows = _select_activity_videos(connection, tennis_activity_id)
        if not video_rows:
            raise_api_error(
                status.HTTP_409_CONFLICT,
                "UPLOAD_HAS_NO_VIDEOS",
                "Upload cannot be completed without videos.",
            )

        incomplete = [row for row in video_rows if row["upload_status"] != "uploaded"]
        if incomplete:
            raise_api_error(
                status.HTTP_409_CONFLICT,
                "UPLOAD_INCOMPLETE",
                "All videos must finish uploading before the activity can be completed.",
            )

        connection.execute(
            """
            UPDATE videos
            SET analysis_status = 'queued'
            WHERE tennis_activity_id = ?
              AND upload_status = 'uploaded'
              AND analysis_status = 'uploaded'
              AND deleted_at IS NULL;
            """,
            (tennis_activity_id,),
        )
        queued_count = connection.execute(
            """
            SELECT COUNT(*) AS queued_count
            FROM videos
            WHERE tennis_activity_id = ?
              AND upload_status = 'uploaded'
              AND analysis_status = 'queued'
              AND deleted_at IS NULL;
            """,
            (tennis_activity_id,),
        ).fetchone()["queued_count"]
        connection.execute(
            """
            UPDATE tennis_activities
            SET analysis_summary_status = 'pending'
            WHERE tennis_activity_id = ?;
            """,
            (tennis_activity_id,),
        )

        activity = _row_to_activity(_select_activity(connection, activity_row["tennis_activity_id"]))
        videos = [_row_to_video(row) for row in _select_activity_videos(connection, tennis_activity_id)]
        return UploadCompleteResponse(activity=activity, videos=videos, queued_count=int(queued_count))


def cancel_activity_upload(user_id: str, tennis_activity_id: str) -> UploadCancelResponse:
    now = utc_now_iso()
    with transaction() as connection:
        activity_row = _select_owned_activity(connection, tennis_activity_id, user_id)
        video_rows = _select_activity_videos(connection, tennis_activity_id)
        if any(row["analysis_status"] != "uploaded" for row in video_rows):
            raise_api_error(
                status.HTTP_409_CONFLICT,
                "UPLOAD_ALREADY_SUBMITTED",
                "Submitted uploads cannot be canceled from the draft flow.",
            )
        for row in video_rows:
            if row["upload_status"] == "uploaded":
                _delete_local_video_if_present(row["video_path"])
                delete_public_storage_file_if_present(row["thumbnail_path"])

        connection.execute(
            """
            UPDATE videos
            SET upload_status = 'canceled',
                analysis_status = 'canceled',
                deleted_at = ?
            WHERE tennis_activity_id = ?
              AND deleted_at IS NULL;
            """,
            (now, tennis_activity_id),
        )
        connection.execute(
            """
            UPDATE tennis_activities
            SET analysis_summary_status = 'failed',
                deleted_at = ?
            WHERE tennis_activity_id = ?;
            """,
            (now, tennis_activity_id),
        )
        activity = _row_to_activity(_select_activity(connection, activity_row["tennis_activity_id"]))
        videos = [
            _row_to_video(row)
            for row in connection.execute(
                """
                SELECT *
                FROM videos
                WHERE tennis_activity_id = ?
                ORDER BY created_at ASC, video_id ASC;
                """,
                (tennis_activity_id,),
            ).fetchall()
        ]
        return UploadCancelResponse(success=True, activity=activity, videos=videos)


def get_activity_detail(user_id: str, tennis_activity_id: str) -> ActivityDetailResponse:
    with get_connection() as connection:
        activity_row = _select_activity(connection, tennis_activity_id)
        if activity_row["deleted_at"] is not None:
            _raise_not_found("TENNIS_ACTIVITY_NOT_FOUND", "Tennis activity was not found.")

        lesson_row = _select_activity_lesson_context(
            connection,
            activity_row["lesson_id"],
            user_id,
        )
        all_video_rows = _select_activity_videos(connection, tennis_activity_id)
        if not _can_view_activity(
            activity_row=activity_row,
            lesson_row=lesson_row,
            user_id=user_id,
            all_video_rows=all_video_rows,
        ):
            _raise_not_found("TENNIS_ACTIVITY_NOT_FOUND", "Tennis activity was not found.")

        visible_video_rows = [
            row
            for row in all_video_rows
            if _can_view_video(
                activity_row=activity_row,
                lesson_row=lesson_row,
                user_id=user_id,
                video_row=row,
            )
        ]
        visible_video_records = ensure_video_thumbnail_records(
            connection,
            visible_video_rows,
        )
        is_owner = activity_row["owner_user_id"] == user_id
        videos = [VideoRecord(**record) for record in visible_video_records]
        return ActivityDetailResponse(
            activity=_row_to_activity(activity_row, include_exact_location=is_owner),
            videos=videos,
            lesson=_row_to_activity_detail_lesson(lesson_row),
            permissions=ActivityDetailPermissions(
                can_view=True,
                can_manage=is_owner,
                can_play_videos=any(row["upload_status"] == "uploaded" for row in visible_video_rows),
            ),
            summary=_activity_detail_summary(visible_video_rows),
        )


def list_upload_lesson_options(user_id: str) -> list[LessonOption]:
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT
                lessons.lesson_id,
                lessons.coach_user_id,
                lessons.title,
                lessons.lesson_type,
                lessons.status,
                lessons.started_at,
                lessons.ended_at,
                lessons.location_name,
                'coach' AS role
            FROM lessons
            WHERE lessons.coach_user_id = ?
              AND lessons.deleted_at IS NULL

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
                'student' AS role
            FROM lesson_students
            JOIN lessons ON lessons.lesson_id = lesson_students.lesson_id
            WHERE lesson_students.student_user_id = ?
              AND lesson_students.deleted_at IS NULL
              AND lessons.deleted_at IS NULL

            ORDER BY started_at DESC, lesson_id DESC
            LIMIT 50;
            """,
            (user_id, user_id),
        ).fetchall()

    return [LessonOption(**_row_dict(row)) for row in rows]
