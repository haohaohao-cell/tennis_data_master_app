from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request

from backend.app.auth.dependencies import get_auth_session, get_current_user
from backend.app.auth.schemas import (
    AuthTokensResponse,
    CurrentUserResponse,
    LogoutResponse,
    PhoneLoginRequest,
    RefreshTokenRequest,
    SendVerificationCodeRequest,
    SendVerificationCodeResponse,
    UserPublic,
)
from backend.app.auth.service import (
    AuthSession,
    login_with_phone_code,
    logout_session,
    refresh_tokens,
    send_phone_verification_code,
)
from backend.app.core.config import settings


router = APIRouter(prefix="/auth", tags=["auth"])


def _client_ip(request: Request) -> str | None:
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",", maxsplit=1)[0].strip()
    return request.client.host if request.client else None


def _user_agent(request: Request) -> str | None:
    user_agent = request.headers.get("user-agent")
    return user_agent[:255] if user_agent else None


@router.post("/verification-codes", response_model=SendVerificationCodeResponse)
def send_verification_code(payload: SendVerificationCodeRequest) -> SendVerificationCodeResponse:
    _, expires_at = send_phone_verification_code(payload.phone)
    return SendVerificationCodeResponse(
        success=True,
        expires_at=expires_at,
        dev_code=settings.dev_sms_code if settings.is_development else None,
    )


@router.post("/phone-login", response_model=AuthTokensResponse)
def phone_login(payload: PhoneLoginRequest, request: Request) -> AuthTokensResponse:
    token_issue = login_with_phone_code(
        phone=payload.phone,
        code=payload.code,
        device=payload.device,
        ip_address=_client_ip(request),
        user_agent=_user_agent(request),
    )
    return AuthTokensResponse(
        access_token=token_issue.access_token,
        refresh_token=token_issue.refresh_token,
        access_expires_at=token_issue.access_expires_at,
        refresh_expires_at=token_issue.refresh_expires_at,
        user=token_issue.user,
    )


@router.get("/me", response_model=CurrentUserResponse)
def me(current_user: Annotated[UserPublic, Depends(get_current_user)]) -> CurrentUserResponse:
    return CurrentUserResponse(user=current_user)


@router.post("/refresh", response_model=AuthTokensResponse)
def refresh(payload: RefreshTokenRequest, request: Request) -> AuthTokensResponse:
    token_issue = refresh_tokens(
        refresh_token=payload.refresh_token,
        device=payload.device,
        ip_address=_client_ip(request),
        user_agent=_user_agent(request),
    )
    return AuthTokensResponse(
        access_token=token_issue.access_token,
        refresh_token=token_issue.refresh_token,
        access_expires_at=token_issue.access_expires_at,
        refresh_expires_at=token_issue.refresh_expires_at,
        user=token_issue.user,
    )


@router.post("/logout", response_model=LogoutResponse)
def logout(session: Annotated[AuthSession, Depends(get_auth_session)]) -> LogoutResponse:
    logout_session(session.session_id)
    return LogoutResponse(success=True)
