from __future__ import annotations

import sqlite3
from typing import Any

from fastapi import status

from backend.app.auth.service import raise_api_error
from backend.app.core.database import transaction
from backend.app.privacy.schemas import PrivacySettingsRecord, PrivacySettingsUpdate


def _row_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {key: row[key] for key in row.keys()}


def _ensure_active_user(connection: sqlite3.Connection, user_id: str) -> None:
    row = connection.execute(
        """
        SELECT 1
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


def _settings_record(row: sqlite3.Row) -> PrivacySettingsRecord:
    data = _row_dict(row)
    data["allow_message_requests"] = bool(data["allow_message_requests"])
    data["show_profile_to_strangers"] = bool(data["show_profile_to_strangers"])
    return PrivacySettingsRecord(**data)


def _select_or_create_settings(connection: sqlite3.Connection, user_id: str) -> sqlite3.Row:
    connection.execute(
        """
        INSERT OR IGNORE INTO user_privacy_settings (user_id)
        VALUES (?);
        """,
        (user_id,),
    )
    row = connection.execute(
        """
        SELECT *
        FROM user_privacy_settings
        WHERE user_id = ?
        LIMIT 1;
        """,
        (user_id,),
    ).fetchone()
    if row is None:
        raise_api_error(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "PRIVACY_SETTINGS_NOT_AVAILABLE",
            "Privacy settings could not be loaded.",
        )
    return row


def get_privacy_settings(user_id: str) -> PrivacySettingsRecord:
    with transaction() as connection:
        _ensure_active_user(connection, user_id)
        row = _select_or_create_settings(connection, user_id)
    return _settings_record(row)


def update_privacy_settings(user_id: str, payload: PrivacySettingsUpdate) -> PrivacySettingsRecord:
    fields = payload.model_dump(exclude_unset=True)
    if not fields:
        raise_api_error(
            status.HTTP_400_BAD_REQUEST,
            "PRIVACY_UPDATE_EMPTY",
            "At least one privacy setting is required.",
        )

    assignments: list[str] = []
    params: list[object] = []
    for column in (
        "direct_message_policy",
        "allow_message_requests",
        "default_post_visibility",
        "show_profile_to_strangers",
    ):
        if column in fields:
            assignments.append(f"{column} = ?")
            value = fields[column]
            if isinstance(value, bool):
                value = 1 if value else 0
            params.append(value)

    with transaction() as connection:
        _ensure_active_user(connection, user_id)
        _select_or_create_settings(connection, user_id)
        params.append(user_id)
        connection.execute(
            f"""
            UPDATE user_privacy_settings
            SET {", ".join(assignments)}
            WHERE user_id = ?;
            """,
            tuple(params),
        )
        row = _select_or_create_settings(connection, user_id)
    return _settings_record(row)
