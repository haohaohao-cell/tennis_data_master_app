from __future__ import annotations

from dataclasses import dataclass
from typing import Any
import sqlite3
import uuid

from fastapi import status

from backend.app.auth.service import raise_api_error
from backend.app.coach.schemas import (
    AdminCoachApplicationRecord,
    AdminCoachReviewPayload,
    AdminCoachStatusPayload,
    CoachApplicationCreate,
    CoachApplicationRecord,
    CoachCapabilities,
    CoachIdentityResponse,
    CoachProfileRecord,
)
from backend.app.core.database import get_connection, transaction
from backend.app.core.time import utc_now_iso


@dataclass(frozen=True)
class PageResult:
    items: list[Any]
    total: int
    page: int
    page_size: int


def _row_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {key: row[key] for key in row.keys()}


def _row_to_application(row: sqlite3.Row) -> CoachApplicationRecord:
    return CoachApplicationRecord(**_row_dict(row))


def _row_to_admin_application(row: sqlite3.Row) -> AdminCoachApplicationRecord:
    return AdminCoachApplicationRecord(**_row_dict(row))


def _row_to_profile(row: sqlite3.Row) -> CoachProfileRecord:
    return CoachProfileRecord(**_row_dict(row))


def _raise_not_found(code: str, message: str) -> None:
    raise_api_error(status.HTTP_404_NOT_FOUND, code, message)


def _ensure_active_user(connection: sqlite3.Connection, user_id: str) -> sqlite3.Row:
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
        _raise_not_found("USER_NOT_FOUND", "User was not found.")
    return row


def _select_application(
    connection: sqlite3.Connection,
    coach_application_id: str,
) -> sqlite3.Row:
    row = connection.execute(
        """
        SELECT *
        FROM coach_applications
        WHERE coach_application_id = ?
        LIMIT 1;
        """,
        (coach_application_id,),
    ).fetchone()
    if row is None:
        _raise_not_found("COACH_APPLICATION_NOT_FOUND", "Coach application was not found.")
    return row


def _select_admin_application(
    connection: sqlite3.Connection,
    coach_application_id: str,
) -> sqlite3.Row:
    row = connection.execute(
        """
        SELECT
            coach_applications.*,
            users.nickname AS applicant_nickname,
            users.phone AS applicant_phone,
            coach_profiles.coach_type AS current_coach_type,
            coach_profiles.status AS current_coach_status
        FROM coach_applications
        JOIN users ON users.user_id = coach_applications.applicant_user_id
        LEFT JOIN coach_profiles ON coach_profiles.user_id = coach_applications.applicant_user_id
        WHERE coach_applications.coach_application_id = ?
        LIMIT 1;
        """,
        (coach_application_id,),
    ).fetchone()
    if row is None:
        _raise_not_found("COACH_APPLICATION_NOT_FOUND", "Coach application was not found.")
    return row


def _select_profile_by_user(
    connection: sqlite3.Connection,
    user_id: str,
) -> sqlite3.Row | None:
    return connection.execute(
        """
        SELECT *
        FROM coach_profiles
        WHERE user_id = ?
        LIMIT 1;
        """,
        (user_id,),
    ).fetchone()


def _select_latest_application(
    connection: sqlite3.Connection,
    user_id: str,
) -> sqlite3.Row | None:
    return connection.execute(
        """
        SELECT *
        FROM coach_applications
        WHERE applicant_user_id = ?
        ORDER BY created_at DESC, coach_application_id DESC
        LIMIT 1;
        """,
        (user_id,),
    ).fetchone()


def _select_pending_application(
    connection: sqlite3.Connection,
    user_id: str,
) -> sqlite3.Row | None:
    return connection.execute(
        """
        SELECT *
        FROM coach_applications
        WHERE applicant_user_id = ?
          AND status = 'pending'
        LIMIT 1;
        """,
        (user_id,),
    ).fetchone()


def _capabilities_for(coach_type: str | None, profile_status: str | None) -> CoachCapabilities:
    active = profile_status == "active"
    certified = active and coach_type == "certified"
    non_professional = active and coach_type == "non_professional"
    return CoachCapabilities(
        coach_homepage=active,
        course_management=certified,
        student_management=certified,
        video_review=certified or non_professional,
        service_publishing=certified or non_professional,
        student_consultation=certified or non_professional,
    )


def _identity_from_rows(
    application_row: sqlite3.Row | None,
    profile_row: sqlite3.Row | None,
) -> CoachIdentityResponse:
    application = _row_to_application(application_row) if application_row is not None else None
    profile = _row_to_profile(profile_row) if profile_row is not None else None

    if profile is not None and profile.status == "active":
        if profile.coach_type == "certified":
            return CoachIdentityResponse(
                status="certified_coach",
                label="认证教练",
                is_coach=True,
                coach_type=profile.coach_type,
                application=application,
                profile=profile,
                capabilities=_capabilities_for(profile.coach_type, profile.status),
            )
        return CoachIdentityResponse(
            status="non_professional_coach",
            label="非职业教练",
            is_coach=True,
            coach_type=profile.coach_type,
            application=application,
            profile=profile,
            capabilities=_capabilities_for(profile.coach_type, profile.status),
        )

    if application is not None and application.status == "pending":
        return CoachIdentityResponse(
            status="pending_review",
            label="申请审核中",
            is_coach=False,
            coach_type=application.application_type,
            application=application,
            profile=profile,
            capabilities=_capabilities_for(None, None),
        )

    if profile is not None and profile.status == "suspended":
        return CoachIdentityResponse(
            status="coach_suspended",
            label="教练身份已暂停",
            is_coach=False,
            coach_type=profile.coach_type,
            application=application,
            profile=profile,
            capabilities=_capabilities_for(profile.coach_type, profile.status),
        )

    if profile is not None and profile.status == "revoked":
        return CoachIdentityResponse(
            status="coach_revoked",
            label="教练身份已撤销",
            is_coach=False,
            coach_type=profile.coach_type,
            application=application,
            profile=profile,
            capabilities=_capabilities_for(profile.coach_type, profile.status),
        )

    if application is not None and application.status == "rejected":
        return CoachIdentityResponse(
            status="review_rejected",
            label="审核拒绝",
            is_coach=False,
            coach_type=application.application_type,
            application=application,
            profile=profile,
            rejection_reason=application.rejection_reason,
            capabilities=_capabilities_for(None, None),
        )

    return CoachIdentityResponse(
        status="normal_user",
        label="普通用户",
        is_coach=False,
        coach_type=None,
        application=application,
        profile=profile,
        capabilities=_capabilities_for(None, None),
    )


def get_user_coach_identity(user_id: str) -> CoachIdentityResponse:
    with get_connection() as connection:
        _ensure_active_user(connection, user_id)
        return _identity_from_rows(
            _select_latest_application(connection, user_id),
            _select_profile_by_user(connection, user_id),
        )


def create_coach_application(
    user_id: str,
    payload: CoachApplicationCreate,
) -> tuple[CoachApplicationRecord, CoachIdentityResponse]:
    data = payload.model_dump()
    application_id = str(uuid.uuid4())
    try:
        with transaction() as connection:
            _ensure_active_user(connection, user_id)
            if _select_pending_application(connection, user_id) is not None:
                raise_api_error(
                    status.HTTP_409_CONFLICT,
                    "COACH_APPLICATION_PENDING_EXISTS",
                    "A coach application is already pending review.",
                )

            profile_row = _select_profile_by_user(connection, user_id)
            if profile_row is not None and profile_row["status"] in {"active", "suspended"}:
                raise_api_error(
                    status.HTTP_409_CONFLICT,
                    "COACH_IDENTITY_ALREADY_EXISTS",
                    "This user already has a coach identity.",
                )

            connection.execute(
                """
                INSERT INTO coach_applications (
                    coach_application_id,
                    applicant_user_id,
                    application_type,
                    status,
                    display_name,
                    real_name,
                    phone,
                    city,
                    specialties,
                    coaching_experience,
                    certification_title,
                    certification_file_path,
                    verification_video_path,
                    note
                )
                VALUES (?, ?, ?, 'pending', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    application_id,
                    user_id,
                    data["application_type"],
                    data["display_name"],
                    data["real_name"],
                    data["phone"],
                    data["city"],
                    data["specialties"],
                    data["coaching_experience"],
                    data["certification_title"],
                    data["certification_file_path"],
                    data["verification_video_path"],
                    data["note"],
                ),
            )
            connection.execute(
                """
                UPDATE users
                SET is_coach = 1,
                    coach_status = 'pending',
                    coach_verified_at = NULL
                WHERE user_id = ?;
                """,
                (user_id,),
            )
            application_row = _select_application(connection, application_id)
            identity = _identity_from_rows(application_row, profile_row)
            return _row_to_application(application_row), identity
    except sqlite3.IntegrityError as error:
        raise_api_error(
            status.HTTP_400_BAD_REQUEST,
            "COACH_APPLICATION_INTEGRITY_ERROR",
            f"Coach application constraint failed: {error}",
        )


def list_admin_coach_applications(
    *,
    page: int,
    page_size: int,
    q: str | None = None,
    status_filter: str | None = None,
    application_type: str | None = None,
) -> PageResult:
    where: list[str] = []
    params: list[object] = []
    if status_filter:
        where.append("coach_applications.status = ?")
        params.append(status_filter)
    if application_type:
        where.append("coach_applications.application_type = ?")
        params.append(application_type)
    if q and q.strip():
        like = f"%{q.strip()}%"
        where.append(
            """
            (
                coach_applications.coach_application_id LIKE ?
                OR coach_applications.applicant_user_id LIKE ?
                OR coach_applications.display_name LIKE ?
                OR coach_applications.real_name LIKE ?
                OR users.nickname LIKE ?
                OR users.phone LIKE ?
                OR coach_applications.city LIKE ?
                OR coach_applications.specialties LIKE ?
            )
            """
        )
        params.extend([like] * 8)

    where_sql = " AND ".join(where) if where else "1 = 1"
    offset = (page - 1) * page_size
    with get_connection() as connection:
        total = connection.execute(
            f"""
            SELECT COUNT(*) AS total
            FROM coach_applications
            JOIN users ON users.user_id = coach_applications.applicant_user_id
            LEFT JOIN coach_profiles ON coach_profiles.user_id = coach_applications.applicant_user_id
            WHERE {where_sql};
            """,
            tuple(params),
        ).fetchone()["total"]
        rows = connection.execute(
            f"""
            SELECT
                coach_applications.*,
                users.nickname AS applicant_nickname,
                users.phone AS applicant_phone,
                coach_profiles.coach_type AS current_coach_type,
                coach_profiles.status AS current_coach_status
            FROM coach_applications
            JOIN users ON users.user_id = coach_applications.applicant_user_id
            LEFT JOIN coach_profiles ON coach_profiles.user_id = coach_applications.applicant_user_id
            WHERE {where_sql}
            ORDER BY coach_applications.created_at DESC, coach_applications.coach_application_id DESC
            LIMIT ? OFFSET ?;
            """,
            (*params, page_size, offset),
        ).fetchall()

    return PageResult([_row_to_admin_application(row) for row in rows], int(total), page, page_size)


def get_admin_coach_application(coach_application_id: str) -> AdminCoachApplicationRecord:
    with get_connection() as connection:
        return _row_to_admin_application(_select_admin_application(connection, coach_application_id))


def approve_coach_application(
    coach_application_id: str,
    reviewer_user_id: str,
) -> AdminCoachApplicationRecord:
    now = utc_now_iso()
    try:
        with transaction() as connection:
            application_row = _select_application(connection, coach_application_id)
            if application_row["status"] != "pending":
                raise_api_error(
                    status.HTTP_409_CONFLICT,
                    "COACH_APPLICATION_NOT_PENDING",
                    "Only pending coach applications can be approved.",
                )

            applicant_user_id = application_row["applicant_user_id"]
            _ensure_active_user(connection, applicant_user_id)
            _ensure_active_user(connection, reviewer_user_id)

            connection.execute(
                """
                UPDATE coach_applications
                SET status = 'approved',
                    reviewer_user_id = ?,
                    reviewed_at = ?,
                    rejection_reason = NULL
                WHERE coach_application_id = ?;
                """,
                (reviewer_user_id, now, coach_application_id),
            )
            connection.execute(
                """
                INSERT INTO coach_profiles (
                    coach_profile_id,
                    user_id,
                    coach_type,
                    status,
                    display_name,
                    city,
                    specialties,
                    coaching_experience,
                    certification_title,
                    certification_file_path,
                    verification_video_path,
                    approved_application_id,
                    approved_by_user_id,
                    approved_at,
                    suspended_at,
                    revoked_at,
                    status_reason
                )
                VALUES (?, ?, ?, 'active', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, NULL)
                ON CONFLICT(user_id) DO UPDATE SET
                    coach_type = excluded.coach_type,
                    status = 'active',
                    display_name = excluded.display_name,
                    city = excluded.city,
                    specialties = excluded.specialties,
                    coaching_experience = excluded.coaching_experience,
                    certification_title = excluded.certification_title,
                    certification_file_path = excluded.certification_file_path,
                    verification_video_path = excluded.verification_video_path,
                    approved_application_id = excluded.approved_application_id,
                    approved_by_user_id = excluded.approved_by_user_id,
                    approved_at = excluded.approved_at,
                    suspended_at = NULL,
                    revoked_at = NULL,
                    status_reason = NULL;
                """,
                (
                    str(uuid.uuid4()),
                    applicant_user_id,
                    application_row["application_type"],
                    application_row["display_name"],
                    application_row["city"],
                    application_row["specialties"],
                    application_row["coaching_experience"],
                    application_row["certification_title"],
                    application_row["certification_file_path"],
                    application_row["verification_video_path"],
                    coach_application_id,
                    reviewer_user_id,
                    now,
                ),
            )
            connection.execute(
                """
                UPDATE users
                SET is_coach = 1,
                    coach_status = 'active',
                    coach_verified_at = ?
                WHERE user_id = ?;
                """,
                (now, applicant_user_id),
            )
            return _row_to_admin_application(_select_admin_application(connection, coach_application_id))
    except sqlite3.IntegrityError as error:
        raise_api_error(
            status.HTTP_400_BAD_REQUEST,
            "COACH_REVIEW_INTEGRITY_ERROR",
            f"Coach review constraint failed: {error}",
        )


def reject_coach_application(
    coach_application_id: str,
    reviewer_user_id: str,
    payload: AdminCoachReviewPayload,
) -> AdminCoachApplicationRecord:
    if not payload.rejection_reason:
        raise_api_error(
            status.HTTP_400_BAD_REQUEST,
            "COACH_REJECTION_REASON_REQUIRED",
            "Rejection reason is required.",
        )

    now = utc_now_iso()
    with transaction() as connection:
        application_row = _select_application(connection, coach_application_id)
        if application_row["status"] != "pending":
            raise_api_error(
                status.HTTP_409_CONFLICT,
                "COACH_APPLICATION_NOT_PENDING",
                "Only pending coach applications can be rejected.",
            )

        applicant_user_id = application_row["applicant_user_id"]
        _ensure_active_user(connection, reviewer_user_id)
        connection.execute(
            """
            UPDATE coach_applications
            SET status = 'rejected',
                reviewer_user_id = ?,
                reviewed_at = ?,
                rejection_reason = ?
            WHERE coach_application_id = ?;
            """,
            (reviewer_user_id, now, payload.rejection_reason, coach_application_id),
        )
        connection.execute(
            """
            UPDATE users
            SET is_coach = 0,
                coach_status = NULL,
                coach_verified_at = NULL
            WHERE user_id = ?;
            """,
            (applicant_user_id,),
        )
        return _row_to_admin_application(_select_admin_application(connection, coach_application_id))


def suspend_coach(
    user_id: str,
    payload: AdminCoachStatusPayload,
) -> CoachProfileRecord:
    now = utc_now_iso()
    with transaction() as connection:
        profile_row = _select_profile_by_user(connection, user_id)
        if profile_row is None:
            _raise_not_found("COACH_PROFILE_NOT_FOUND", "Coach profile was not found.")
        if profile_row["status"] == "revoked":
            raise_api_error(
                status.HTTP_409_CONFLICT,
                "COACH_PROFILE_REVOKED",
                "Revoked coach identities cannot be suspended.",
            )

        connection.execute(
            """
            UPDATE coach_profiles
            SET status = 'suspended',
                suspended_at = ?,
                status_reason = ?
            WHERE user_id = ?;
            """,
            (now, payload.reason, user_id),
        )
        connection.execute(
            """
            UPDATE users
            SET is_coach = 1,
                coach_status = 'disabled',
                coach_verified_at = NULL
            WHERE user_id = ?;
            """,
            (user_id,),
        )
        return _row_to_profile(_select_profile_by_user(connection, user_id))


def restore_coach(
    user_id: str,
    payload: AdminCoachStatusPayload,
) -> CoachProfileRecord:
    with transaction() as connection:
        profile_row = _select_profile_by_user(connection, user_id)
        if profile_row is None:
            _raise_not_found("COACH_PROFILE_NOT_FOUND", "Coach profile was not found.")
        if profile_row["status"] != "suspended":
            raise_api_error(
                status.HTTP_409_CONFLICT,
                "COACH_PROFILE_NOT_SUSPENDED",
                "Only suspended coach identities can be restored.",
            )

        connection.execute(
            """
            UPDATE coach_profiles
            SET status = 'active',
                suspended_at = NULL,
                status_reason = ?
            WHERE user_id = ?;
            """,
            (payload.reason, user_id),
        )
        connection.execute(
            """
            UPDATE users
            SET is_coach = 1,
                coach_status = 'active',
                coach_verified_at = ?
            WHERE user_id = ?;
            """,
            (profile_row["approved_at"], user_id),
        )
        return _row_to_profile(_select_profile_by_user(connection, user_id))


def revoke_coach(
    user_id: str,
    payload: AdminCoachStatusPayload,
) -> CoachProfileRecord:
    now = utc_now_iso()
    with transaction() as connection:
        profile_row = _select_profile_by_user(connection, user_id)
        if profile_row is None:
            _raise_not_found("COACH_PROFILE_NOT_FOUND", "Coach profile was not found.")
        if profile_row["status"] == "revoked":
            raise_api_error(
                status.HTTP_409_CONFLICT,
                "COACH_PROFILE_ALREADY_REVOKED",
                "Coach identity has already been revoked.",
            )

        connection.execute(
            """
            UPDATE coach_profiles
            SET status = 'revoked',
                revoked_at = ?,
                suspended_at = NULL,
                status_reason = ?
            WHERE user_id = ?;
            """,
            (now, payload.reason, user_id),
        )
        connection.execute(
            """
            UPDATE users
            SET is_coach = 0,
                coach_status = NULL,
                coach_verified_at = NULL
            WHERE user_id = ?;
            """,
            (user_id,),
        )
        return _row_to_profile(_select_profile_by_user(connection, user_id))

