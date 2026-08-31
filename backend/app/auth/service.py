from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import hashlib
import secrets
import sqlite3
import uuid

from fastapi import HTTPException, status

from backend.app.auth.schemas import DeviceInfo, UserPublic
from backend.app.core.config import settings
from backend.app.core.database import get_connection, transaction
from backend.app.core.time import days_from_now, minutes_from_now, utc_now_iso


PHONE_PROVIDER = "phone"
SESSION_LAST_SEEN_TOUCH_INTERVAL = timedelta(minutes=5)


@dataclass(frozen=True)
class AuthSession:
    session_id: str
    user: UserPublic


@dataclass(frozen=True)
class TokenIssue:
    access_token: str
    refresh_token: str
    access_expires_at: str
    refresh_expires_at: str
    user: UserPublic


def raise_api_error(status_code: int, code: str, message: str) -> None:
    raise HTTPException(
        status_code=status_code,
        detail={
            "code": code,
            "message": message,
        },
    )


def normalize_phone(phone: str) -> str:
    normalized = "".join(
        char for char in phone.strip() if char not in {" ", "-", "(", ")"}
    )
    if not normalized:
        raise_api_error(status.HTTP_400_BAD_REQUEST, "INVALID_PHONE", "Phone number is required.")
    if len(normalized) > 30:
        raise_api_error(status.HTTP_400_BAD_REQUEST, "INVALID_PHONE", "Phone number is too long.")
    return normalized


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _new_token() -> str:
    return secrets.token_urlsafe(48)


def _parse_session_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None

    normalized = value.strip()
    if not normalized:
        return None

    try:
        if normalized.endswith("Z"):
            parsed = datetime.fromisoformat(normalized.replace("Z", "+00:00"))
        else:
            parsed = datetime.fromisoformat(normalized)
    except ValueError:
        try:
            parsed = datetime.strptime(normalized, "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
        except ValueError:
            return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _should_touch_session(last_seen_at: str | None, now: str) -> bool:
    last_seen = _parse_session_timestamp(last_seen_at)
    current_time = _parse_session_timestamp(now)
    if current_time is None:
        return False
    if last_seen is None:
        return True
    return current_time - last_seen >= SESSION_LAST_SEEN_TOUCH_INTERVAL


def _touch_session_last_seen(session_id: str, now: str) -> None:
    try:
        with transaction() as connection:
            connection.execute(
                "UPDATE auth_sessions SET last_seen_at = ? WHERE session_id = ?;",
                (now, session_id),
            )
    except sqlite3.OperationalError as error:
        if "database is locked" not in str(error).lower():
            raise


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


def _select_user_by_identity(
    connection: sqlite3.Connection,
    provider: str,
    provider_subject_normalized: str,
) -> sqlite3.Row | None:
    return connection.execute(
        """
        SELECT users.*
        FROM auth_identities
        JOIN users ON users.user_id = auth_identities.user_id
        WHERE auth_identities.provider = ?
          AND auth_identities.provider_subject_normalized = ?
          AND auth_identities.deleted_at IS NULL
          AND users.deleted_at IS NULL
        LIMIT 1;
        """,
        (provider, provider_subject_normalized),
    ).fetchone()


def _select_legacy_user_by_phone(
    connection: sqlite3.Connection,
    phone_normalized: str,
) -> sqlite3.Row | None:
    return connection.execute(
        """
        SELECT *
        FROM users
        WHERE phone = ?
          AND deleted_at IS NULL
        LIMIT 1;
        """,
        (phone_normalized,),
    ).fetchone()


def _ensure_active_user(row: sqlite3.Row) -> None:
    if row["status"] != "active":
        raise_api_error(
            status.HTTP_403_FORBIDDEN,
            "USER_DISABLED",
            "This account is not available.",
        )


def _default_nickname(phone_normalized: str) -> str:
    suffix = phone_normalized[-4:] if len(phone_normalized) >= 4 else phone_normalized
    return f"Tennis User {suffix}"


def _create_user_with_phone_identity(
    connection: sqlite3.Connection,
    phone_normalized: str,
) -> sqlite3.Row:
    user_id = str(uuid.uuid4())
    connection.execute(
        """
        INSERT INTO users (user_id, nickname, phone, profile_completed)
        VALUES (?, ?, ?, 0);
        """,
        (user_id, _default_nickname(phone_normalized), phone_normalized),
    )
    _insert_phone_identity(connection, user_id, phone_normalized)
    return connection.execute(
        "SELECT * FROM users WHERE user_id = ?;",
        (user_id,),
    ).fetchone()


def _insert_phone_identity(
    connection: sqlite3.Connection,
    user_id: str,
    phone_normalized: str,
) -> None:
    now = utc_now_iso()
    connection.execute(
        """
        INSERT INTO auth_identities (
            identity_id,
            user_id,
            provider,
            provider_subject,
            provider_subject_normalized,
            is_verified,
            verified_at
        )
        VALUES (?, ?, ?, ?, ?, 1, ?);
        """,
        (
            str(uuid.uuid4()),
            user_id,
            PHONE_PROVIDER,
            phone_normalized,
            phone_normalized,
            now,
        ),
    )


def _get_or_create_user_for_phone(
    connection: sqlite3.Connection,
    phone_normalized: str,
) -> sqlite3.Row:
    user_row = _select_user_by_identity(connection, PHONE_PROVIDER, phone_normalized)
    if user_row is not None:
        _ensure_active_user(user_row)
        return user_row

    legacy_user_row = _select_legacy_user_by_phone(connection, phone_normalized)
    if legacy_user_row is not None:
        _ensure_active_user(legacy_user_row)
        _insert_phone_identity(connection, legacy_user_row["user_id"], phone_normalized)
        return legacy_user_row

    return _create_user_with_phone_identity(connection, phone_normalized)


def _issue_tokens(
    connection: sqlite3.Connection,
    user: UserPublic,
    device: DeviceInfo | None,
    ip_address: str | None,
    user_agent: str | None,
) -> TokenIssue:
    session_id = str(uuid.uuid4())
    access_token = _new_token()
    refresh_token = _new_token()
    access_expires_at = minutes_from_now(settings.access_token_ttl_minutes)
    refresh_expires_at = days_from_now(settings.refresh_token_ttl_days)

    connection.execute(
        """
        INSERT INTO auth_sessions (
            session_id,
            user_id,
            access_token_hash,
            refresh_token_hash,
            device_name,
            platform,
            ip_address,
            user_agent,
            access_expires_at,
            expires_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """,
        (
            session_id,
            user.user_id,
            _hash(access_token),
            _hash(refresh_token),
            device.device_name if device else None,
            device.platform if device else None,
            ip_address,
            user_agent,
            access_expires_at,
            refresh_expires_at,
        ),
    )

    return TokenIssue(
        access_token=access_token,
        refresh_token=refresh_token,
        access_expires_at=access_expires_at,
        refresh_expires_at=refresh_expires_at,
        user=user,
    )


def send_phone_verification_code(phone: str) -> tuple[str, str]:
    phone_normalized = normalize_phone(phone)
    expires_at = minutes_from_now(settings.verification_code_ttl_minutes)
    with transaction() as connection:
        connection.execute(
            """
            INSERT INTO auth_verification_codes (
                verification_code_id,
                provider,
                recipient,
                recipient_normalized,
                code_hash,
                purpose,
                expires_at
            )
            VALUES (?, ?, ?, ?, ?, 'login', ?);
            """,
            (
                str(uuid.uuid4()),
                PHONE_PROVIDER,
                phone,
                phone_normalized,
                _hash(settings.dev_sms_code),
                expires_at,
            ),
        )
    return phone_normalized, expires_at


def login_with_phone_code(
    phone: str,
    code: str,
    device: DeviceInfo | None,
    ip_address: str | None,
    user_agent: str | None,
) -> TokenIssue:
    phone_normalized = normalize_phone(phone)
    if code != settings.dev_sms_code:
        raise_api_error(
            status.HTTP_400_BAD_REQUEST,
            "INVALID_VERIFICATION_CODE",
            "Verification code is incorrect.",
        )

    now = utc_now_iso()
    # Login may create the user and identity. Acquire SQLite's writer lock
    # before the initial lookup so concurrent first-time logins do not both
    # read and then race while upgrading a deferred transaction.
    with transaction(immediate=True, lock_key=f"login-phone:{phone_normalized}") as connection:
        user_row = _get_or_create_user_for_phone(connection, phone_normalized)
        connection.execute(
            """
            UPDATE auth_verification_codes
            SET consumed_at = ?
            WHERE provider = ?
              AND recipient_normalized = ?
              AND purpose = 'login'
              AND consumed_at IS NULL;
            """,
            (now, PHONE_PROVIDER, phone_normalized),
        )
        user = _row_to_user(user_row)
        return _issue_tokens(connection, user, device, ip_address, user_agent)


def authenticate_access_token(access_token: str) -> AuthSession:
    now = utc_now_iso()
    token_hash = _hash(access_token)
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT
                auth_sessions.session_id,
                auth_sessions.last_seen_at,
                users.*
            FROM auth_sessions
            JOIN users ON users.user_id = auth_sessions.user_id
            WHERE auth_sessions.access_token_hash = ?
              AND auth_sessions.revoked_at IS NULL
              AND auth_sessions.access_expires_at > ?
              AND auth_sessions.expires_at > ?
              AND users.status = 'active'
              AND users.deleted_at IS NULL
            LIMIT 1;
            """,
            (token_hash, now, now),
        ).fetchone()

        if row is None:
            raise_api_error(
                status.HTTP_401_UNAUTHORIZED,
                "INVALID_ACCESS_TOKEN",
                "Login has expired. Please sign in again.",
            )

    if _should_touch_session(row["last_seen_at"], now):
        _touch_session_last_seen(row["session_id"], now)
    return AuthSession(session_id=row["session_id"], user=_row_to_user(row))


def refresh_tokens(
    refresh_token: str,
    device: DeviceInfo | None,
    ip_address: str | None,
    user_agent: str | None,
) -> TokenIssue:
    now = utc_now_iso()
    token_hash = _hash(refresh_token)
    with transaction() as connection:
        row = connection.execute(
            """
            SELECT
                auth_sessions.session_id,
                users.*
            FROM auth_sessions
            JOIN users ON users.user_id = auth_sessions.user_id
            WHERE auth_sessions.refresh_token_hash = ?
              AND auth_sessions.revoked_at IS NULL
              AND auth_sessions.expires_at > ?
              AND users.status = 'active'
              AND users.deleted_at IS NULL
            LIMIT 1;
            """,
            (token_hash, now),
        ).fetchone()

        if row is None:
            raise_api_error(
                status.HTTP_401_UNAUTHORIZED,
                "INVALID_REFRESH_TOKEN",
                "Login has expired. Please sign in again.",
            )

        access_token = _new_token()
        next_refresh_token = _new_token()
        access_expires_at = minutes_from_now(settings.access_token_ttl_minutes)
        refresh_expires_at = days_from_now(settings.refresh_token_ttl_days)

        connection.execute(
            """
            UPDATE auth_sessions
            SET access_token_hash = ?,
                refresh_token_hash = ?,
                access_expires_at = ?,
                expires_at = ?,
                last_seen_at = ?,
                device_name = COALESCE(?, device_name),
                platform = COALESCE(?, platform),
                ip_address = COALESCE(?, ip_address),
                user_agent = COALESCE(?, user_agent)
            WHERE session_id = ?;
            """,
            (
                _hash(access_token),
                _hash(next_refresh_token),
                access_expires_at,
                refresh_expires_at,
                now,
                device.device_name if device else None,
                device.platform if device else None,
                ip_address,
                user_agent,
                row["session_id"],
            ),
        )

        return TokenIssue(
            access_token=access_token,
            refresh_token=next_refresh_token,
            access_expires_at=access_expires_at,
            refresh_expires_at=refresh_expires_at,
            user=_row_to_user(row),
        )


def get_user_by_id(user_id: str) -> UserPublic | None:
    with get_connection() as connection:
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
    return _row_to_user(row) if row is not None else None


def issue_tokens_for_user(
    user_id: str,
    device: DeviceInfo | None,
    ip_address: str | None,
    user_agent: str | None,
) -> TokenIssue:
    with transaction() as connection:
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
                status.HTTP_401_UNAUTHORIZED,
                "INVALID_ACCESS_TOKEN",
                "Login has expired. Please sign in again.",
            )

        return _issue_tokens(connection, _row_to_user(row), device, ip_address, user_agent)


def logout_session(session_id: str) -> None:
    now = utc_now_iso()
    with transaction() as connection:
        connection.execute(
            """
            UPDATE auth_sessions
            SET revoked_at = ?
            WHERE session_id = ?
              AND revoked_at IS NULL;
            """,
            (now, session_id),
        )
