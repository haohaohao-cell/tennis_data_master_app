from __future__ import annotations

from pathlib import Path
import sqlite3
import uuid
from urllib.parse import unquote

from fastapi import UploadFile, status

from backend.app.auth.schemas import UserPublic
from backend.app.auth.service import raise_api_error
from backend.app.core.config import settings
from backend.app.core.database import get_connection, transaction
from backend.app.social.schemas import RelationshipResponse
from backend.app.users.schemas import UserSearchItem, UserSearchResponse, UserSearchSummary, UserProfileUpdate


ALLOWED_AVATAR_CONTENT_TYPES = {
    "image/gif": ".gif",
    "image/heic": ".heic",
    "image/heif": ".heif",
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}
ALLOWED_AVATAR_SUFFIXES = {".gif", ".heic", ".heif", ".jpeg", ".jpg", ".png", ".webp"}
AVATAR_STREAM_CHUNK_SIZE = 1024 * 1024


def _row_to_user(row: sqlite3.Row) -> UserPublic:
    return UserPublic(
        user_id=row["user_id"],
        nickname=row["nickname"],
        avatar_path=row["avatar_path"],
        phone=row["phone"],
        email=row["email"],
        status=row["status"],
        profile_completed=bool(row["profile_completed"]),
        playing_hand=row["playing_hand"],
        is_coach=bool(row["is_coach"]),
        coach_status=row["coach_status"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _row_to_user_search_summary(row: sqlite3.Row) -> UserSearchSummary:
    return UserSearchSummary(
        user_id=row["user_id"],
        nickname=row["nickname"],
        avatar_path=row["avatar_path"],
        is_coach=bool(row["is_coach"]),
        coach_status=row["coach_status"],
    )


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _relationship_from_search_row(viewer_user_id: str, row: sqlite3.Row) -> RelationshipResponse:
    target_user_id = row["user_id"]
    is_self = viewer_user_id == target_user_id
    is_following = bool(row["following_follow_id"]) if not is_self else False
    is_followed_by = bool(row["followed_by_follow_id"]) if not is_self else False
    return RelationshipResponse(
        user_id=viewer_user_id,
        target_user_id=target_user_id,
        is_following=is_following,
        is_followed_by=is_followed_by,
        is_friend=is_following and is_followed_by,
    )


def _normalize_content_type(content_type: str | None) -> str:
    return (content_type or "").split(";", 1)[0].strip().lower()


def _safe_avatar_suffix(original_filename: str | None, mime_type: str | None = None) -> str:
    filename = unquote((original_filename or "").replace("\\", "/").rsplit("/", 1)[-1])
    filename = filename.split("?", 1)[0].split("#", 1)[0]
    suffix = Path(filename).suffix.lower()
    if suffix in ALLOWED_AVATAR_SUFFIXES:
        return ".jpg" if suffix == ".jpeg" else suffix

    content_type = _normalize_content_type(mime_type)
    if content_type in ALLOWED_AVATAR_CONTENT_TYPES:
        return ALLOWED_AVATAR_CONTENT_TYPES[content_type]

    return ""


def _validate_avatar_file(file: UploadFile) -> str:
    content_type = _normalize_content_type(file.content_type)
    if content_type and content_type not in ALLOWED_AVATAR_CONTENT_TYPES:
        raise_api_error(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            "UNSUPPORTED_AVATAR_TYPE",
            "Only common image files can be uploaded as avatars.",
        )

    suffix = _safe_avatar_suffix(file.filename, file.content_type)
    if suffix not in ALLOWED_AVATAR_SUFFIXES:
        raise_api_error(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            "UNSUPPORTED_AVATAR_EXTENSION",
            "Only common image file formats are supported for avatars.",
        )
    return suffix


def _reserved_public_avatar_path(user_id: str, filename: str) -> str:
    normalized_user_id = "/".join(
        part
        for part in user_id.replace("\\", "/").split("/")
        if part and part not in {".", ".."}
    )
    return f"{settings.public_avatar_path_prefix.rstrip('/')}/{normalized_user_id}/{filename}"


def _local_path_for_public_avatar_path(avatar_path: str) -> Path:
    prefix = settings.public_avatar_path_prefix.rstrip("/") + "/"
    if not avatar_path.startswith(prefix):
        raise_api_error(
            status.HTTP_400_BAD_REQUEST,
            "INVALID_AVATAR_STORAGE_PATH",
            "Avatar storage path is not managed by this service.",
        )

    relative_path = avatar_path[len(prefix) :]
    if not relative_path or ".." in Path(relative_path).parts:
        raise_api_error(
            status.HTTP_400_BAD_REQUEST,
            "INVALID_AVATAR_STORAGE_PATH",
            "Avatar storage path is invalid.",
        )

    storage_root = settings.avatar_storage_dir.resolve()
    local_path = (storage_root / relative_path).resolve()
    try:
        local_path.relative_to(storage_root)
    except ValueError:
        raise_api_error(
            status.HTTP_400_BAD_REQUEST,
            "INVALID_AVATAR_STORAGE_PATH",
            "Avatar storage path escapes the configured storage directory.",
        )
    return local_path


def _delete_managed_avatar_if_present(avatar_path: str | None) -> None:
    if not avatar_path:
        return
    prefix = settings.public_avatar_path_prefix.rstrip("/") + "/"
    if not avatar_path.startswith(prefix):
        return
    local_path = _local_path_for_public_avatar_path(avatar_path)
    if local_path.exists() and local_path.is_file():
        local_path.unlink()


def update_current_user_profile(user_id: str, payload: UserProfileUpdate) -> UserPublic:
    assignments: list[str] = []
    values: list[object] = []

    if payload.nickname is not None:
        assignments.append("nickname = ?")
        values.append(payload.nickname)
    if payload.avatar_path is not None:
        assignments.append("avatar_path = ?")
        values.append(payload.avatar_path)
    if payload.playing_hand is not None:
        assignments.append("playing_hand = ?")
        values.append(payload.playing_hand)

    assignments.append("profile_completed = 1")
    values.append(user_id)

    with transaction() as connection:
        connection.execute(
            f"""
            UPDATE users
            SET {", ".join(assignments)}
            WHERE user_id = ?
              AND status = 'active'
              AND deleted_at IS NULL;
            """,
            tuple(values),
        )
        row = connection.execute(
            """
            SELECT *
            FROM users
            WHERE user_id = ?
              AND status = 'active'
              AND deleted_at IS NULL
            LIMIT 1;
            """,
            (user_id,),
        ).fetchone()

    if row is None:
        raise_api_error(
            status.HTTP_404_NOT_FOUND,
            "USER_NOT_FOUND",
            "Current user was not found.",
        )

    return _row_to_user(row)


def search_users(viewer_user_id: str, query: str, page: int, page_size: int) -> UserSearchResponse:
    normalized_query = query.strip()
    if len(normalized_query) < 2:
        raise_api_error(
            status.HTTP_400_BAD_REQUEST,
            "USER_SEARCH_QUERY_TOO_SHORT",
            "Search query must be at least 2 characters.",
        )

    escaped_query = _escape_like(normalized_query)
    user_id_prefix = f"{escaped_query}%"
    nickname_pattern = f"%{escaped_query}%"
    offset = (page - 1) * page_size

    with get_connection() as connection:
        current_user = connection.execute(
            """
            SELECT 1
            FROM users
            WHERE user_id = ?
              AND status = 'active'
              AND deleted_at IS NULL
            LIMIT 1;
            """,
            (viewer_user_id,),
        ).fetchone()
        if current_user is None:
            raise_api_error(
                status.HTTP_404_NOT_FOUND,
                "USER_NOT_FOUND",
                "Current user was not found.",
            )

        rows = connection.execute(
            """
            SELECT
                users.user_id,
                users.nickname,
                users.avatar_path,
                users.is_coach,
                users.coach_status,
                following.follow_id AS following_follow_id,
                followed_by.follow_id AS followed_by_follow_id
            FROM users
            LEFT JOIN user_follows AS following
              ON following.follower_user_id = ?
             AND following.following_user_id = users.user_id
             AND following.status = 'active'
            LEFT JOIN user_follows AS followed_by
              ON followed_by.follower_user_id = users.user_id
             AND followed_by.following_user_id = ?
             AND followed_by.status = 'active'
            LEFT JOIN user_privacy_settings AS privacy
              ON privacy.user_id = users.user_id
            WHERE users.status = 'active'
              AND users.deleted_at IS NULL
              AND (
                  users.user_id = ?
                  OR users.user_id LIKE ? ESCAPE '\\'
                  OR users.nickname LIKE ? ESCAPE '\\'
              )
              AND (
                  users.user_id = ?
                  OR COALESCE(privacy.show_profile_to_strangers, 1) = 1
                  OR following.follow_id IS NOT NULL
                  OR followed_by.follow_id IS NOT NULL
              )
              AND (
                  users.user_id = ?
                  OR NOT EXISTS (
                      SELECT 1
                      FROM user_blocks
                      WHERE user_blocks.deleted_at IS NULL
                        AND (
                            (user_blocks.blocker_user_id = ? AND user_blocks.blocked_user_id = users.user_id)
                            OR (user_blocks.blocker_user_id = users.user_id AND user_blocks.blocked_user_id = ?)
                        )
                      LIMIT 1
                  )
              )
            ORDER BY
                CASE
                    WHEN users.user_id = ? THEN 0
                    WHEN users.user_id LIKE ? ESCAPE '\\' THEN 1
                    ELSE 2
                END,
                users.nickname COLLATE NOCASE ASC,
                users.created_at DESC
            LIMIT ? OFFSET ?;
            """,
            (
                viewer_user_id,
                viewer_user_id,
                normalized_query,
                user_id_prefix,
                nickname_pattern,
                viewer_user_id,
                viewer_user_id,
                viewer_user_id,
                viewer_user_id,
                normalized_query,
                user_id_prefix,
                page_size,
                offset,
            ),
        ).fetchall()

    items = [
        UserSearchItem(
            user=_row_to_user_search_summary(row),
            relationship=_relationship_from_search_row(viewer_user_id, row),
            is_self=row["user_id"] == viewer_user_id,
            match_type="user_id" if row["user_id"] == normalized_query or row["user_id"].startswith(normalized_query) else "nickname",
        )
        for row in rows
    ]
    return UserSearchResponse(
        items=items,
        page=page,
        page_size=page_size,
        query=normalized_query,
    )


async def upload_current_user_avatar(user_id: str, file: UploadFile) -> UserPublic:
    suffix = _validate_avatar_file(file)
    filename = f"{uuid.uuid4()}{suffix}"
    public_path = _reserved_public_avatar_path(user_id, filename)
    local_path = _local_path_for_public_avatar_path(public_path)
    local_path.parent.mkdir(parents=True, exist_ok=True)
    bytes_written = 0

    try:
        with local_path.open("wb") as output:
            while True:
                chunk = await file.read(AVATAR_STREAM_CHUNK_SIZE)
                if not chunk:
                    break
                bytes_written += len(chunk)
                if bytes_written > settings.max_upload_avatar_size_bytes:
                    output.close()
                    if local_path.exists():
                        local_path.unlink()
                    raise_api_error(
                        status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        "AVATAR_FILE_TOO_LARGE",
                        "Avatar image exceeds the upload size limit.",
                    )
                output.write(chunk)
    except Exception:
        if local_path.exists():
            local_path.unlink()
        raise
    finally:
        await file.close()

    if bytes_written == 0:
        _delete_managed_avatar_if_present(public_path)
        raise_api_error(
            status.HTTP_400_BAD_REQUEST,
            "EMPTY_AVATAR_FILE",
            "Avatar image cannot be empty.",
        )

    old_avatar_path: str | None = None
    try:
        with transaction() as connection:
            old_row = connection.execute(
                """
                SELECT avatar_path
                FROM users
                WHERE user_id = ?
                  AND status = 'active'
                  AND deleted_at IS NULL
                LIMIT 1;
                """,
                (user_id,),
            ).fetchone()
            if old_row is None:
                _delete_managed_avatar_if_present(public_path)
                raise_api_error(
                    status.HTTP_404_NOT_FOUND,
                    "USER_NOT_FOUND",
                    "Current user was not found.",
                )

            old_avatar_path = old_row["avatar_path"]
            connection.execute(
                """
                UPDATE users
                SET avatar_path = ?
                WHERE user_id = ?
                  AND status = 'active'
                  AND deleted_at IS NULL;
                """,
                (public_path, user_id),
            )
            row = connection.execute(
                """
                SELECT *
                FROM users
                WHERE user_id = ?
                  AND status = 'active'
                  AND deleted_at IS NULL
                LIMIT 1;
                """,
                (user_id,),
            ).fetchone()
    except Exception:
        _delete_managed_avatar_if_present(public_path)
        raise

    if row is None:
        _delete_managed_avatar_if_present(public_path)
        raise_api_error(
            status.HTTP_404_NOT_FOUND,
            "USER_NOT_FOUND",
            "Current user was not found.",
        )

    if old_avatar_path != public_path:
        _delete_managed_avatar_if_present(old_avatar_path)

    return _row_to_user(row)
