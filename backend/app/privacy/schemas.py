from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


DirectMessagePolicy = Literal["everyone", "following", "friends"]
DefaultPostVisibility = Literal["private", "friends", "followers", "public"]


class PrivacySettingsRecord(BaseModel):
    user_id: str
    direct_message_policy: DirectMessagePolicy
    allow_message_requests: bool
    default_post_visibility: DefaultPostVisibility
    show_profile_to_strangers: bool
    created_at: str
    updated_at: str


class PrivacySettingsUpdate(BaseModel):
    direct_message_policy: DirectMessagePolicy | None = None
    allow_message_requests: bool | None = None
    default_post_visibility: DefaultPostVisibility | None = None
    show_profile_to_strangers: bool | None = None
