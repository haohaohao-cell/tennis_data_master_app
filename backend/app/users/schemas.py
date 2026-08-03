from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from backend.app.social.schemas import RelationshipResponse


class UserProfileUpdate(BaseModel):
    nickname: str | None = Field(default=None, max_length=50)
    avatar_path: str | None = None
    playing_hand: Literal["right", "left", "unknown"] | None = None

    @field_validator("nickname")
    @classmethod
    def normalize_nickname(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("Nickname cannot be empty.")
        return normalized

    @model_validator(mode="after")
    def ensure_has_update(self) -> "UserProfileUpdate":
        if self.nickname is None and self.avatar_path is None and self.playing_hand is None:
            raise ValueError("At least one profile field is required.")
        return self


class UserSearchSummary(BaseModel):
    user_id: str
    nickname: str
    avatar_path: str | None = None
    is_coach: bool
    coach_status: str | None = None


class UserSearchItem(BaseModel):
    user: UserSearchSummary
    relationship: RelationshipResponse
    is_self: bool
    match_type: Literal["user_id", "nickname"]


class UserSearchResponse(BaseModel):
    items: list[UserSearchItem]
    page: int
    page_size: int
    query: str
