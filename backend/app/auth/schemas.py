from __future__ import annotations

from pydantic import BaseModel, Field


class UserPublic(BaseModel):
    user_id: str
    nickname: str
    avatar_path: str | None = None
    phone: str | None = None
    email: str | None = None
    status: str
    profile_completed: bool
    playing_hand: str
    is_coach: bool
    coach_status: str | None = None
    created_at: str
    updated_at: str


class DeviceInfo(BaseModel):
    device_name: str | None = Field(default=None, max_length=120)
    platform: str | None = Field(default=None, max_length=50)


class SendVerificationCodeRequest(BaseModel):
    phone: str = Field(min_length=1, max_length=30)


class SendVerificationCodeResponse(BaseModel):
    success: bool
    expires_at: str
    dev_code: str | None = None


class PhoneLoginRequest(BaseModel):
    phone: str = Field(min_length=1, max_length=30)
    code: str = Field(min_length=1, max_length=12)
    device: DeviceInfo | None = None


class RefreshTokenRequest(BaseModel):
    refresh_token: str = Field(min_length=1)
    device: DeviceInfo | None = None


class AuthTokensResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    access_expires_at: str
    refresh_expires_at: str
    user: UserPublic


class CurrentUserResponse(BaseModel):
    user: UserPublic


class LogoutResponse(BaseModel):
    success: bool
