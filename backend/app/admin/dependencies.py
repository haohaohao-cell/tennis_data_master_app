from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, status

from backend.app.auth.dependencies import get_current_user
from backend.app.auth.schemas import UserPublic
from backend.app.auth.service import raise_api_error
from backend.app.core.database import get_connection


@dataclass(frozen=True)
class AdminActor:
    user: UserPublic
    role: str


def require_admin_actor(
    current_user: Annotated[UserPublic, Depends(get_current_user)],
) -> AdminActor:
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT role
            FROM admin_users
            WHERE user_id = ?
              AND status = 'active'
            LIMIT 1;
            """,
            (current_user.user_id,),
        ).fetchone()

    if row is None:
        raise_api_error(
            status.HTTP_403_FORBIDDEN,
            "ADMIN_PERMISSION_REQUIRED",
            "Admin permission is required.",
        )

    return AdminActor(user=current_user, role=row["role"])
