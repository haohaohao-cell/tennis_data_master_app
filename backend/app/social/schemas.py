from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


def _strip_text(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


class SocialUserSummary(BaseModel):
    user_id: str
    nickname: str
    avatar_path: str | None = None
    is_coach: bool
    coach_status: str | None = None


class FollowCreate(BaseModel):
    source: str | None = Field(default=None, max_length=50)

    @field_validator("source")
    @classmethod
    def normalize_source(cls, value: str | None) -> str | None:
        return _strip_text(value)


class FollowRecord(BaseModel):
    follow_id: str
    follower_user_id: str
    following_user_id: str
    status: str
    source: str | None = None
    followed_at: str
    canceled_at: str | None = None
    created_at: str
    updated_at: str


class RelationshipResponse(BaseModel):
    user_id: str
    target_user_id: str
    is_following: bool
    is_followed_by: bool
    is_friend: bool


class FollowActionResponse(BaseModel):
    success: bool
    relationship: RelationshipResponse
    follow: FollowRecord | None = None


class FollowListItem(BaseModel):
    user: SocialUserSummary
    follow: FollowRecord
    is_friend: bool


class FollowListResponse(BaseModel):
    items: list[FollowListItem]
    page: int
    page_size: int


class SocialStatsResponse(BaseModel):
    user_id: str
    follower_count: int
    following_count: int
    friend_count: int


class BlockCreate(BaseModel):
    reason: str | None = Field(default=None, max_length=255)

    @field_validator("reason")
    @classmethod
    def normalize_reason(cls, value: str | None) -> str | None:
        return _strip_text(value)


class BlockRecord(BaseModel):
    user_block_id: str
    blocker_user_id: str
    blocked_user_id: str
    reason: str | None = None
    created_at: str
    updated_at: str
    deleted_at: str | None = None


class BlockActionResponse(BaseModel):
    success: bool
    block: BlockRecord | None = None


class BlockListItem(BaseModel):
    user: SocialUserSummary
    block: BlockRecord


class BlockListResponse(BaseModel):
    items: list[BlockListItem]
    page: int
    page_size: int
