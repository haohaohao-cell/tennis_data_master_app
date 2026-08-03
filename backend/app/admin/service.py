from __future__ import annotations

from dataclasses import dataclass
import hashlib
import secrets
import hmac
from typing import Any
import sqlite3
import uuid

from fastapi import status
from pydantic import BaseModel

from backend.app.auth.schemas import DeviceInfo

from backend.app.admin.schemas import (
    AdminPostCreate,
    AdminPostRecord,
    AdminPostUpdate,
    AdminTennisActivityCreate,
    AdminTennisActivityRecord,
    AdminTennisActivityUpdate,
    AdminUserCreate,
    AdminUserRecord,
    AdminUserUpdate,
    AdminVideoCreate,
    AdminVideoRecord,
    AdminVideoUpdate,
)
from backend.app.auth.service import TokenIssue, issue_tokens_for_user, raise_api_error
from backend.app.core.database import get_connection, transaction
from backend.app.core.time import utc_now_iso


PASSWORD_HASH_ALGORITHM = "pbkdf2_sha256"
PASSWORD_HASH_ITERATIONS = 120_000


@dataclass(frozen=True)
class PageResult:
    items: list[Any]
    total: int
    page: int
    page_size: int


@dataclass(frozen=True)
class AdminLoginResult:
    token_issue: TokenIssue
    admin_role: str


USER_COLUMNS = {
    "nickname",
    "avatar_path",
    "phone",
    "email",
    "status",
    "profile_completed",
    "playing_hand",
    "is_coach",
    "coach_status",
    "coach_verified_at",
    "deleted_at",
}

ACTIVITY_COLUMNS = {
    "owner_user_id",
    "lesson_id",
    "title",
    "activity_type",
    "default_visibility",
    "started_at",
    "ended_at",
    "location_name",
    "location_source",
    "location_latitude",
    "location_longitude",
    "location_accuracy_m",
    "location_captured_at",
    "location_country_code",
    "location_region",
    "location_city",
    "location_district",
    "location_address_label",
    "location_coordinate_system",
    "court_surface",
    "opponent_user_id",
    "opponent_name",
    "note",
    "analysis_summary_status",
    "deleted_at",
}

VIDEO_COLUMNS = {
    "tennis_activity_id",
    "owner_user_id",
    "uploader_user_id",
    "filename",
    "original_filename",
    "video_path",
    "thumbnail_path",
    "mime_type",
    "file_size_bytes",
    "file_hash",
    "video_duration_ms",
    "video_frame_count",
    "video_fps",
    "video_width_px",
    "video_height_px",
    "camera_view_angle",
    "camera_view_position",
    "frame_data_path",
    "frame_data_version",
    "player_a_user_id",
    "player_b_user_id",
    "player_a_name",
    "player_b_name",
    "primary_player_slot",
    "visibility",
    "upload_status",
    "upload_error_message",
    "uploaded_at",
    "analysis_status",
    "analysis_version",
    "error_message",
    "captured_at",
    "deleted_at",
}

POST_COLUMNS = {
    "author_user_id",
    "source_tennis_activity_id",
    "title",
    "content",
    "visibility",
    "status",
    "review_status",
    "reviewed_at",
    "reviewer_user_id",
    "review_reason",
    "location_scope",
    "location_region",
    "location_city",
    "published_at",
    "deleted_at",
}


def _as_bool(value: object) -> bool:
    return bool(value)


def _row_value(row: sqlite3.Row, key: str) -> Any:
    return row[key] if key in row.keys() else None


def _row_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {key: row[key] for key in row.keys()}


def _payload_dict(payload: BaseModel) -> dict[str, Any]:
    return payload.model_dump(exclude_unset=True)


def normalize_admin_username(username: str) -> str:
    normalized = username.strip().casefold()
    if not normalized:
        raise_api_error(
            status.HTTP_400_BAD_REQUEST,
            "ADMIN_INVALID_USERNAME",
            "Admin username is required.",
        )
    if len(normalized) > 50:
        raise_api_error(
            status.HTTP_400_BAD_REQUEST,
            "ADMIN_INVALID_USERNAME",
            "Admin username is too long.",
        )
    return normalized


def hash_admin_password(password: str) -> str:
    if not password:
        raise_api_error(
            status.HTTP_400_BAD_REQUEST,
            "ADMIN_INVALID_PASSWORD",
            "Admin password is required.",
        )
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("ascii"),
        PASSWORD_HASH_ITERATIONS,
    ).hex()
    return f"{PASSWORD_HASH_ALGORITHM}${PASSWORD_HASH_ITERATIONS}${salt}${digest}"


def verify_admin_password(password: str, password_hash: str) -> bool:
    try:
        algorithm, iterations_raw, salt, expected_digest = password_hash.split("$", 3)
        iterations = int(iterations_raw)
    except ValueError:
        return False

    if algorithm != PASSWORD_HASH_ALGORITHM or iterations <= 0:
        return False

    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("ascii"),
        iterations,
    ).hex()
    return hmac.compare_digest(digest, expected_digest)


def _raise_not_found(code: str, message: str) -> None:
    raise_api_error(status.HTTP_404_NOT_FOUND, code, message)


def _raise_integrity_error(error: sqlite3.IntegrityError) -> None:
    raise_api_error(
        status.HTTP_400_BAD_REQUEST,
        "ADMIN_DATA_INTEGRITY_ERROR",
        f"Data constraint failed: {error}",
    )


def _append_like_filter(
    where: list[str],
    params: list[object],
    q: str | None,
    fields: list[str],
) -> None:
    normalized = q.strip() if q else ""
    if not normalized:
        return

    where.append("(" + " OR ".join(f"{field} LIKE ?" for field in fields) + ")")
    params.extend([f"%{normalized}%"] * len(fields))


def _select_page(
    connection: sqlite3.Connection,
    select_clause: str,
    from_clause: str,
    where: list[str],
    params: list[object],
    order_by: str,
    page: int,
    page_size: int,
) -> tuple[list[sqlite3.Row], int]:
    where_sql = " AND ".join(where) if where else "1 = 1"
    total = connection.execute(
        f"SELECT COUNT(*) AS total FROM {from_clause} WHERE {where_sql};",
        tuple(params),
    ).fetchone()["total"]
    offset = (page - 1) * page_size
    rows = connection.execute(
        f"""
        SELECT {select_clause}
        FROM {from_clause}
        WHERE {where_sql}
        ORDER BY {order_by}
        LIMIT ? OFFSET ?;
        """,
        (*params, page_size, offset),
    ).fetchall()
    return rows, int(total)


def _execute_update(
    connection: sqlite3.Connection,
    table_name: str,
    id_column: str,
    record_id: str,
    fields: dict[str, Any],
    allowed_columns: set[str],
) -> None:
    assignments: list[str] = []
    values: list[object] = []
    for key, value in fields.items():
        if key not in allowed_columns:
            continue
        assignments.append(f"{key} = ?")
        if isinstance(value, bool):
            values.append(1 if value else 0)
        else:
            values.append(value)

    if not assignments:
        return

    values.append(record_id)
    connection.execute(
        f"""
        UPDATE {table_name}
        SET {", ".join(assignments)}
        WHERE {id_column} = ?;
        """,
        tuple(values),
    )


def _ensure_user_reference(connection: sqlite3.Connection, user_id: str, label: str) -> None:
    row = connection.execute(
        """
        SELECT 1
        FROM users
        WHERE user_id = ?
          AND deleted_at IS NULL
        LIMIT 1;
        """,
        (user_id,),
    ).fetchone()
    if row is None:
        _raise_not_found("ADMIN_USER_REFERENCE_NOT_FOUND", f"{label} was not found.")


def _ensure_optional_user_reference(
    connection: sqlite3.Connection,
    user_id: str | None,
    label: str,
) -> None:
    if user_id is not None:
        _ensure_user_reference(connection, user_id, label)


def _ensure_lesson_reference(connection: sqlite3.Connection, lesson_id: str | None) -> None:
    if lesson_id is None:
        return
    row = connection.execute(
        """
        SELECT 1
        FROM lessons
        WHERE lesson_id = ?
          AND deleted_at IS NULL
        LIMIT 1;
        """,
        (lesson_id,),
    ).fetchone()
    if row is None:
        _raise_not_found("ADMIN_LESSON_REFERENCE_NOT_FOUND", "lesson_id was not found.")


def _ensure_activity_reference(
    connection: sqlite3.Connection,
    tennis_activity_id: str | None,
) -> None:
    if tennis_activity_id is None:
        return
    row = connection.execute(
        """
        SELECT 1
        FROM tennis_activities
        WHERE tennis_activity_id = ?
          AND deleted_at IS NULL
        LIMIT 1;
        """,
        (tennis_activity_id,),
    ).fetchone()
    if row is None:
        _raise_not_found(
            "ADMIN_ACTIVITY_REFERENCE_NOT_FOUND",
            "tennis_activity_id was not found.",
        )


def login_admin_with_password(
    username: str,
    password: str,
    device: DeviceInfo | None,
    ip_address: str | None,
    user_agent: str | None,
) -> AdminLoginResult:
    username_normalized = normalize_admin_username(username)
    now = utc_now_iso()
    with transaction() as connection:
        row = connection.execute(
            """
            SELECT
                admin_credentials.user_id,
                admin_credentials.password_hash,
                admin_users.role
            FROM admin_credentials
            JOIN admin_users ON admin_users.user_id = admin_credentials.user_id
            JOIN users ON users.user_id = admin_credentials.user_id
            WHERE admin_credentials.username_normalized = ?
              AND admin_credentials.status = 'active'
              AND admin_users.status = 'active'
              AND users.status = 'active'
              AND users.deleted_at IS NULL
            LIMIT 1;
            """,
            (username_normalized,),
        ).fetchone()

        if row is None or not verify_admin_password(password, row["password_hash"]):
            raise_api_error(
                status.HTTP_401_UNAUTHORIZED,
                "INVALID_ADMIN_CREDENTIALS",
                "Admin username or password is incorrect.",
            )

        connection.execute(
            """
            UPDATE admin_credentials
            SET last_login_at = ?
            WHERE user_id = ?;
            """,
            (now, row["user_id"]),
        )
        user_id = row["user_id"]
        admin_role = row["role"]

    token_issue = issue_tokens_for_user(user_id, device, ip_address, user_agent)
    return AdminLoginResult(token_issue=token_issue, admin_role=admin_role)


def ensure_test_admin_account(
    username: str,
    password: str,
    role: str = "owner",
) -> str:
    username_normalized = normalize_admin_username(username)
    password_hash = hash_admin_password(password)
    with transaction() as connection:
        row = connection.execute(
            """
            SELECT users.user_id
            FROM admin_credentials
            JOIN users ON users.user_id = admin_credentials.user_id
            WHERE admin_credentials.username_normalized = ?
            LIMIT 1;
            """,
            (username_normalized,),
        ).fetchone()

        if row is None:
            user_id = str(uuid.uuid4())
            connection.execute(
                """
                INSERT INTO users (
                    user_id,
                    nickname,
                    status,
                    profile_completed,
                    playing_hand
                )
                VALUES (?, ?, 'active', 1, 'unknown');
                """,
                (user_id, username.strip()),
            )
            connection.execute(
                """
                INSERT INTO admin_users (
                    admin_user_id,
                    user_id,
                    role,
                    status,
                    note,
                    created_by_user_id
                )
                VALUES (?, ?, ?, 'active', ?, ?);
                """,
                (
                    str(uuid.uuid4()),
                    user_id,
                    role,
                    "Local development test admin account.",
                    user_id,
                ),
            )
            connection.execute(
                """
                INSERT INTO admin_credentials (
                    admin_credential_id,
                    user_id,
                    username,
                    username_normalized,
                    password_hash,
                    status
                )
                VALUES (?, ?, ?, ?, ?, 'active');
                """,
                (
                    str(uuid.uuid4()),
                    user_id,
                    username.strip(),
                    username_normalized,
                    password_hash,
                ),
            )
            return user_id

        user_id = row["user_id"]
        connection.execute(
            """
            UPDATE users
            SET nickname = ?,
                status = 'active',
                deleted_at = NULL
            WHERE user_id = ?;
            """,
            (username.strip(), user_id),
        )
        connection.execute(
            """
            INSERT INTO admin_users (
                admin_user_id,
                user_id,
                role,
                status,
                note,
                created_by_user_id
            )
            VALUES (?, ?, ?, 'active', ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                role = excluded.role,
                status = 'active',
                disabled_at = NULL,
                note = excluded.note;
            """,
            (
                str(uuid.uuid4()),
                user_id,
                role,
                "Local development test admin account.",
                user_id,
            ),
        )
        connection.execute(
            """
            UPDATE admin_credentials
            SET username = ?,
                password_hash = ?,
                status = 'active'
            WHERE user_id = ?;
            """,
            (username.strip(), password_hash, user_id),
        )
        return user_id


def _row_to_user(row: sqlite3.Row) -> AdminUserRecord:
    return AdminUserRecord(
        user_id=row["user_id"],
        nickname=row["nickname"],
        avatar_path=row["avatar_path"],
        phone=row["phone"],
        email=row["email"],
        status=row["status"],
        profile_completed=_as_bool(row["profile_completed"]),
        playing_hand=row["playing_hand"],
        is_coach=_as_bool(row["is_coach"]),
        coach_status=row["coach_status"],
        coach_verified_at=row["coach_verified_at"],
        admin_role=_row_value(row, "admin_role"),
        admin_status=_row_value(row, "admin_status"),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        deleted_at=row["deleted_at"],
    )


def _select_user(connection: sqlite3.Connection, user_id: str) -> sqlite3.Row:
    row = connection.execute(
        """
        SELECT
            users.*,
            admin_users.role AS admin_role,
            admin_users.status AS admin_status
        FROM users
        LEFT JOIN admin_users ON admin_users.user_id = users.user_id
        WHERE users.user_id = ?
        LIMIT 1;
        """,
        (user_id,),
    ).fetchone()
    if row is None:
        _raise_not_found("ADMIN_USER_NOT_FOUND", "User was not found.")
    return row


def _validate_user_values(values: dict[str, Any]) -> None:
    is_coach = bool(values.get("is_coach"))
    coach_status = values.get("coach_status")
    coach_verified_at = values.get("coach_verified_at")

    if not is_coach and coach_status is not None:
        raise_api_error(
            status.HTTP_400_BAD_REQUEST,
            "ADMIN_INVALID_USER_COACH_STATE",
            "coach_status requires is_coach=true.",
        )

    if coach_verified_at is not None and (not is_coach or coach_status != "active"):
        raise_api_error(
            status.HTTP_400_BAD_REQUEST,
            "ADMIN_INVALID_USER_COACH_STATE",
            "coach_verified_at requires active coach status.",
        )


def list_users(
    *,
    page: int,
    page_size: int,
    q: str | None = None,
    status_filter: str | None = None,
    is_coach: bool | None = None,
    coach_status: str | None = None,
) -> PageResult:
    where: list[str] = []
    params: list[object] = []
    if status_filter:
        where.append("users.status = ?")
        params.append(status_filter)
    if is_coach is not None:
        where.append("users.is_coach = ?")
        params.append(1 if is_coach else 0)
    if coach_status:
        where.append("users.coach_status = ?")
        params.append(coach_status)
    _append_like_filter(
        where,
        params,
        q,
        [
            "users.user_id",
            "users.nickname",
            "users.phone",
            "users.email",
            "users.status",
            "users.coach_status",
        ],
    )

    with get_connection() as connection:
        rows, total = _select_page(
            connection,
            "users.*, admin_users.role AS admin_role, admin_users.status AS admin_status",
            "users LEFT JOIN admin_users ON admin_users.user_id = users.user_id",
            where,
            params,
            "users.created_at DESC",
            page,
            page_size,
        )
    return PageResult([_row_to_user(row) for row in rows], total, page, page_size)


def get_user(user_id: str) -> AdminUserRecord:
    with get_connection() as connection:
        return _row_to_user(_select_user(connection, user_id))


def create_user(payload: AdminUserCreate) -> AdminUserRecord:
    data = payload.model_dump()
    data["user_id"] = str(uuid.uuid4())
    data["profile_completed"] = 1 if data["profile_completed"] else 0
    data["is_coach"] = 1 if data["is_coach"] else 0
    data["deleted_at"] = utc_now_iso() if data["status"] == "deleted" else None
    _validate_user_values(data)

    try:
        with transaction() as connection:
            connection.execute(
                """
                INSERT INTO users (
                    user_id,
                    nickname,
                    avatar_path,
                    phone,
                    email,
                    status,
                    profile_completed,
                    playing_hand,
                    is_coach,
                    coach_status,
                    coach_verified_at,
                    deleted_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    data["user_id"],
                    data["nickname"],
                    data["avatar_path"],
                    data["phone"],
                    data["email"],
                    data["status"],
                    data["profile_completed"],
                    data["playing_hand"],
                    data["is_coach"],
                    data["coach_status"],
                    data["coach_verified_at"],
                    data["deleted_at"],
                ),
            )
            return _row_to_user(_select_user(connection, data["user_id"]))
    except sqlite3.IntegrityError as error:
        _raise_integrity_error(error)


def update_user(user_id: str, payload: AdminUserUpdate, actor_user_id: str) -> AdminUserRecord:
    fields = _payload_dict(payload)
    if user_id == actor_user_id and fields.get("status") in {"disabled", "deleted"}:
        raise_api_error(
            status.HTTP_400_BAD_REQUEST,
            "ADMIN_SELF_LOCK_NOT_ALLOWED",
            "Admins cannot disable or delete their own user account.",
        )

    try:
        with transaction() as connection:
            row = _select_user(connection, user_id)
            if fields.get("is_coach") is False:
                fields["coach_status"] = None
                fields["coach_verified_at"] = None
            if "coach_status" in fields and fields["coach_status"] != "active":
                fields["coach_verified_at"] = None
            if "status" in fields:
                fields["deleted_at"] = utc_now_iso() if fields["status"] == "deleted" else None

            merged = _row_dict(row)
            merged.update(fields)
            _validate_user_values(merged)
            _execute_update(connection, "users", "user_id", user_id, fields, USER_COLUMNS)

            if fields.get("status") == "deleted":
                connection.execute(
                    """
                    UPDATE admin_users
                    SET status = 'disabled',
                        disabled_at = COALESCE(disabled_at, ?)
                    WHERE user_id = ?;
                    """,
                    (utc_now_iso(), user_id),
                )

            return _row_to_user(_select_user(connection, user_id))
    except sqlite3.IntegrityError as error:
        _raise_integrity_error(error)


def delete_user(user_id: str, actor_user_id: str) -> None:
    if user_id == actor_user_id:
        raise_api_error(
            status.HTTP_400_BAD_REQUEST,
            "ADMIN_SELF_DELETE_NOT_ALLOWED",
            "Admins cannot delete their own user account.",
        )

    now = utc_now_iso()
    with transaction() as connection:
        _select_user(connection, user_id)
        connection.execute(
            """
            UPDATE users
            SET status = 'deleted',
                deleted_at = ?
            WHERE user_id = ?;
            """,
            (now, user_id),
        )
        connection.execute(
            """
            UPDATE admin_users
            SET status = 'disabled',
                disabled_at = COALESCE(disabled_at, ?)
            WHERE user_id = ?;
            """,
            (now, user_id),
        )


def _row_to_activity(row: sqlite3.Row) -> AdminTennisActivityRecord:
    return AdminTennisActivityRecord(**_row_dict(row))


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
        _raise_not_found("ADMIN_ACTIVITY_NOT_FOUND", "Tennis activity was not found.")
    return row


def _validate_activity_references(
    connection: sqlite3.Connection,
    values: dict[str, Any],
) -> None:
    _ensure_user_reference(connection, values["owner_user_id"], "owner_user_id")
    _ensure_lesson_reference(connection, values.get("lesson_id"))
    _ensure_optional_user_reference(connection, values.get("opponent_user_id"), "opponent_user_id")
    if values.get("opponent_user_id") is not None and values["opponent_user_id"] == values["owner_user_id"]:
        raise_api_error(
            status.HTTP_400_BAD_REQUEST,
            "ADMIN_INVALID_ACTIVITY_PLAYERS",
            "opponent_user_id cannot equal owner_user_id.",
        )


def list_activities(
    *,
    page: int,
    page_size: int,
    q: str | None = None,
    activity_type: str | None = None,
    default_visibility: str | None = None,
    analysis_summary_status: str | None = None,
    owner_user_id: str | None = None,
    include_deleted: bool = False,
) -> PageResult:
    where: list[str] = []
    params: list[object] = []
    if not include_deleted:
        where.append("deleted_at IS NULL")
    if activity_type:
        where.append("activity_type = ?")
        params.append(activity_type)
    if default_visibility:
        where.append("default_visibility = ?")
        params.append(default_visibility)
    if analysis_summary_status:
        where.append("analysis_summary_status = ?")
        params.append(analysis_summary_status)
    if owner_user_id:
        where.append("owner_user_id = ?")
        params.append(owner_user_id)
    _append_like_filter(
        where,
        params,
        q,
        [
            "tennis_activity_id",
            "owner_user_id",
            "title",
            "activity_type",
            "default_visibility",
            "analysis_summary_status",
            "location_name",
            "location_region",
            "location_city",
            "location_district",
            "location_address_label",
        ],
    )

    with get_connection() as connection:
        rows, total = _select_page(
            connection,
            "*",
            "tennis_activities",
            where,
            params,
            "created_at DESC",
            page,
            page_size,
        )
    return PageResult([_row_to_activity(row) for row in rows], total, page, page_size)


def get_activity(tennis_activity_id: str) -> AdminTennisActivityRecord:
    with get_connection() as connection:
        return _row_to_activity(_select_activity(connection, tennis_activity_id))


def create_activity(payload: AdminTennisActivityCreate) -> AdminTennisActivityRecord:
    data = payload.model_dump()
    data["tennis_activity_id"] = str(uuid.uuid4())
    try:
        with transaction() as connection:
            _validate_activity_references(connection, data)
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
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    data["tennis_activity_id"],
                    data["owner_user_id"],
                    data["lesson_id"],
                    data["title"],
                    data["activity_type"],
                    data["default_visibility"],
                    data["started_at"],
                    data["ended_at"],
                    data["location_name"],
                    data["location_source"],
                    data["location_latitude"],
                    data["location_longitude"],
                    data["location_accuracy_m"],
                    data["location_captured_at"],
                    data["location_country_code"],
                    data["location_region"],
                    data["location_city"],
                    data["location_district"],
                    data["location_address_label"],
                    data["location_coordinate_system"],
                    data["court_surface"],
                    data["opponent_user_id"],
                    data["opponent_name"],
                    data["note"],
                    data["analysis_summary_status"],
                ),
            )
            return _row_to_activity(_select_activity(connection, data["tennis_activity_id"]))
    except sqlite3.IntegrityError as error:
        _raise_integrity_error(error)


def update_activity(
    tennis_activity_id: str,
    payload: AdminTennisActivityUpdate,
) -> AdminTennisActivityRecord:
    fields = _payload_dict(payload)
    try:
        with transaction() as connection:
            row = _select_activity(connection, tennis_activity_id)
            merged = _row_dict(row)
            merged.update(fields)
            _validate_activity_references(connection, merged)
            _execute_update(
                connection,
                "tennis_activities",
                "tennis_activity_id",
                tennis_activity_id,
                fields,
                ACTIVITY_COLUMNS,
            )
            return _row_to_activity(_select_activity(connection, tennis_activity_id))
    except sqlite3.IntegrityError as error:
        _raise_integrity_error(error)


def delete_activity(tennis_activity_id: str) -> None:
    with transaction() as connection:
        _select_activity(connection, tennis_activity_id)
        connection.execute(
            """
            UPDATE tennis_activities
            SET deleted_at = ?
            WHERE tennis_activity_id = ?;
            """,
            (utc_now_iso(), tennis_activity_id),
        )


def _row_to_video(row: sqlite3.Row) -> AdminVideoRecord:
    return AdminVideoRecord(**_row_dict(row))


def _select_video(connection: sqlite3.Connection, video_id: str) -> sqlite3.Row:
    row = connection.execute(
        """
        SELECT *
        FROM videos
        WHERE video_id = ?
        LIMIT 1;
        """,
        (video_id,),
    ).fetchone()
    if row is None:
        _raise_not_found("ADMIN_VIDEO_NOT_FOUND", "Video was not found.")
    return row


def _validate_video_references(connection: sqlite3.Connection, values: dict[str, Any]) -> None:
    _ensure_activity_reference(connection, values.get("tennis_activity_id"))
    _ensure_user_reference(connection, values["owner_user_id"], "owner_user_id")
    _ensure_user_reference(connection, values["uploader_user_id"], "uploader_user_id")
    _ensure_optional_user_reference(connection, values.get("player_a_user_id"), "player_a_user_id")
    _ensure_optional_user_reference(connection, values.get("player_b_user_id"), "player_b_user_id")
    if values.get("player_a_user_id") and values.get("player_a_user_id") == values.get("player_b_user_id"):
        raise_api_error(
            status.HTTP_400_BAD_REQUEST,
            "ADMIN_INVALID_VIDEO_PLAYERS",
            "player_a_user_id cannot equal player_b_user_id.",
        )


def list_videos(
    *,
    page: int,
    page_size: int,
    q: str | None = None,
    analysis_status: str | None = None,
    visibility: str | None = None,
    owner_user_id: str | None = None,
    include_deleted: bool = False,
) -> PageResult:
    where: list[str] = []
    params: list[object] = []
    if not include_deleted:
        where.append("deleted_at IS NULL")
    if analysis_status:
        where.append("analysis_status = ?")
        params.append(analysis_status)
    if visibility:
        where.append("visibility = ?")
        params.append(visibility)
    if owner_user_id:
        where.append("owner_user_id = ?")
        params.append(owner_user_id)
    _append_like_filter(
        where,
        params,
        q,
        [
            "video_id",
            "tennis_activity_id",
            "owner_user_id",
            "uploader_user_id",
            "filename",
            "original_filename",
            "video_path",
            "analysis_status",
            "visibility",
        ],
    )

    with get_connection() as connection:
        rows, total = _select_page(
            connection,
            "*",
            "videos",
            where,
            params,
            "created_at DESC",
            page,
            page_size,
        )
    return PageResult([_row_to_video(row) for row in rows], total, page, page_size)


def get_video(video_id: str) -> AdminVideoRecord:
    with get_connection() as connection:
        return _row_to_video(_select_video(connection, video_id))


def create_video(payload: AdminVideoCreate) -> AdminVideoRecord:
    data = payload.model_dump()
    data["video_id"] = str(uuid.uuid4())
    try:
        with transaction() as connection:
            _validate_video_references(connection, data)
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
                    thumbnail_path,
                    mime_type,
                    file_size_bytes,
                    file_hash,
                    video_duration_ms,
                    video_frame_count,
                    video_fps,
                    video_width_px,
                    video_height_px,
                    camera_view_angle,
                    camera_view_position,
                    frame_data_path,
                    frame_data_version,
                    player_a_user_id,
                    player_b_user_id,
                    player_a_name,
                    player_b_name,
                    primary_player_slot,
                    visibility,
                    upload_status,
                    upload_error_message,
                    uploaded_at,
                    analysis_status,
                    analysis_version,
                    error_message,
                    captured_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    data["video_id"],
                    data["tennis_activity_id"],
                    data["owner_user_id"],
                    data["uploader_user_id"],
                    data["filename"],
                    data["original_filename"],
                    data["video_path"],
                    data["thumbnail_path"],
                    data["mime_type"],
                    data["file_size_bytes"],
                    data["file_hash"],
                    data["video_duration_ms"],
                    data["video_frame_count"],
                    data["video_fps"],
                    data["video_width_px"],
                    data["video_height_px"],
                    data["camera_view_angle"],
                    data["camera_view_position"],
                    data["frame_data_path"],
                    data["frame_data_version"],
                    data["player_a_user_id"],
                    data["player_b_user_id"],
                    data["player_a_name"],
                    data["player_b_name"],
                    data["primary_player_slot"],
                    data["visibility"],
                    data["upload_status"],
                    data["upload_error_message"],
                    data["uploaded_at"],
                    data["analysis_status"],
                    data["analysis_version"],
                    data["error_message"],
                    data["captured_at"],
                ),
            )
            return _row_to_video(_select_video(connection, data["video_id"]))
    except sqlite3.IntegrityError as error:
        _raise_integrity_error(error)


def update_video(video_id: str, payload: AdminVideoUpdate) -> AdminVideoRecord:
    fields = _payload_dict(payload)
    try:
        with transaction() as connection:
            row = _select_video(connection, video_id)
            merged = _row_dict(row)
            merged.update(fields)
            _validate_video_references(connection, merged)
            _execute_update(connection, "videos", "video_id", video_id, fields, VIDEO_COLUMNS)
            return _row_to_video(_select_video(connection, video_id))
    except sqlite3.IntegrityError as error:
        _raise_integrity_error(error)


def delete_video(video_id: str) -> None:
    with transaction() as connection:
        _select_video(connection, video_id)
        connection.execute(
            """
            UPDATE videos
            SET deleted_at = ?
            WHERE video_id = ?;
            """,
            (utc_now_iso(), video_id),
        )


def _row_to_post(row: sqlite3.Row) -> AdminPostRecord:
    return AdminPostRecord(**_row_dict(row))


def _select_post(connection: sqlite3.Connection, social_post_id: str) -> sqlite3.Row:
    row = connection.execute(
        """
        SELECT *
        FROM social_posts
        WHERE social_post_id = ?
        LIMIT 1;
        """,
        (social_post_id,),
    ).fetchone()
    if row is None:
        _raise_not_found("ADMIN_POST_NOT_FOUND", "Post was not found.")
    return row


def _validate_post_references(connection: sqlite3.Connection, values: dict[str, Any]) -> None:
    _ensure_user_reference(connection, values["author_user_id"], "author_user_id")
    _ensure_activity_reference(connection, values.get("source_tennis_activity_id"))


def _apply_post_status_side_effects(fields: dict[str, Any]) -> None:
    if fields.get("status") == "published" and not fields.get("published_at"):
        fields["published_at"] = utc_now_iso()
    if fields.get("status") == "deleted":
        fields["deleted_at"] = utc_now_iso()
    elif "status" in fields:
        fields["deleted_at"] = None


def list_posts(
    *,
    page: int,
    page_size: int,
    q: str | None = None,
    status_filter: str | None = None,
    visibility: str | None = None,
    author_user_id: str | None = None,
) -> PageResult:
    where: list[str] = []
    params: list[object] = []
    if status_filter:
        where.append("status = ?")
        params.append(status_filter)
    if visibility:
        where.append("visibility = ?")
        params.append(visibility)
    if author_user_id:
        where.append("author_user_id = ?")
        params.append(author_user_id)
    _append_like_filter(
        where,
        params,
        q,
        [
            "social_post_id",
            "author_user_id",
            "source_tennis_activity_id",
            "title",
            "content",
            "visibility",
            "status",
        ],
    )

    with get_connection() as connection:
        rows, total = _select_page(
            connection,
            "*",
            "social_posts",
            where,
            params,
            "created_at DESC",
            page,
            page_size,
        )
    return PageResult([_row_to_post(row) for row in rows], total, page, page_size)


def get_post(social_post_id: str) -> AdminPostRecord:
    with get_connection() as connection:
        return _row_to_post(_select_post(connection, social_post_id))


def create_post(payload: AdminPostCreate) -> AdminPostRecord:
    data = payload.model_dump()
    data["social_post_id"] = str(uuid.uuid4())
    _apply_post_status_side_effects(data)
    try:
        with transaction() as connection:
            _validate_post_references(connection, data)
            connection.execute(
                """
                INSERT INTO social_posts (
                    social_post_id,
                    author_user_id,
                    source_tennis_activity_id,
                    title,
                    content,
                    visibility,
                    status,
                    review_status,
                    reviewed_at,
                    reviewer_user_id,
                    review_reason,
                    location_scope,
                    location_region,
                    location_city,
                    published_at,
                    deleted_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    data["social_post_id"],
                    data["author_user_id"],
                    data["source_tennis_activity_id"],
                    data["title"],
                    data["content"],
                    data["visibility"],
                    data["status"],
                    data["review_status"],
                    data["reviewed_at"],
                    data["reviewer_user_id"],
                    data["review_reason"],
                    data["location_scope"],
                    data["location_region"],
                    data["location_city"],
                    data["published_at"],
                    data.get("deleted_at"),
                ),
            )
            connection.execute(
                "INSERT OR IGNORE INTO social_post_stats (social_post_id) VALUES (?);",
                (data["social_post_id"],),
            )
            return _row_to_post(_select_post(connection, data["social_post_id"]))
    except sqlite3.IntegrityError as error:
        _raise_integrity_error(error)


def update_post(social_post_id: str, payload: AdminPostUpdate) -> AdminPostRecord:
    fields = _payload_dict(payload)
    _apply_post_status_side_effects(fields)
    try:
        with transaction() as connection:
            row = _select_post(connection, social_post_id)
            merged = _row_dict(row)
            merged.update(fields)
            _validate_post_references(connection, merged)
            _execute_update(
                connection,
                "social_posts",
                "social_post_id",
                social_post_id,
                fields,
                POST_COLUMNS,
            )
            return _row_to_post(_select_post(connection, social_post_id))
    except sqlite3.IntegrityError as error:
        _raise_integrity_error(error)


def delete_post(social_post_id: str) -> None:
    now = utc_now_iso()
    with transaction() as connection:
        _select_post(connection, social_post_id)
        connection.execute(
            """
            UPDATE social_posts
            SET status = 'deleted',
                deleted_at = ?
            WHERE social_post_id = ?;
            """,
            (now, social_post_id),
        )
