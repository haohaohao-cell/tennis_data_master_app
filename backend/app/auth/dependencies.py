from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header, status

from backend.app.auth.schemas import UserPublic
from backend.app.auth.service import AuthSession, authenticate_access_token, raise_api_error


def _extract_bearer_token(authorization: str | None) -> str:
    if not authorization:
        raise_api_error(
            status.HTTP_401_UNAUTHORIZED,
            "MISSING_ACCESS_TOKEN",
            "Authorization header is required.",
        )

    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise_api_error(
            status.HTTP_401_UNAUTHORIZED,
            "INVALID_AUTHORIZATION_HEADER",
            "Authorization header must use Bearer token.",
        )
    return token


def get_auth_session(authorization: Annotated[str | None, Header()] = None) -> AuthSession:
    return authenticate_access_token(_extract_bearer_token(authorization))


def get_current_user(session: Annotated[AuthSession, Depends(get_auth_session)]) -> UserPublic:
    return session.user


def get_optional_current_user(
    authorization: Annotated[str | None, Header()] = None,
) -> UserPublic | None:
    if not authorization:
        return None
    return authenticate_access_token(_extract_bearer_token(authorization)).user
