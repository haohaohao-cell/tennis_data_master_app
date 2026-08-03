from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from backend.app.uploads.schemas import VideoRecord


PostVisibility = Literal["private", "friends", "followers", "specified_users", "public"]
PostStatus = Literal["draft", "published", "hidden", "deleted"]
PostMediaType = Literal["video", "video_clip", "image", "data_card"]


def _strip_text(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


class PostAuthor(BaseModel):
    user_id: str
    nickname: str
    avatar_path: str | None = None


class SocialPostRecord(BaseModel):
    social_post_id: str
    author_user_id: str
    source_tennis_activity_id: str | None = None
    title: str | None = None
    content: str | None = None
    visibility: PostVisibility
    status: PostStatus
    review_status: Literal["pending", "approved", "rejected"] = "approved"
    reviewed_at: str | None = None
    reviewer_user_id: str | None = None
    review_reason: str | None = None
    location_scope: Literal["none", "region", "city"] = "none"
    location_region: str | None = None
    location_city: str | None = None
    published_at: str | None = None
    created_at: str
    updated_at: str
    deleted_at: str | None = None


class PostMediaRecord(BaseModel):
    post_media_id: str
    social_post_id: str
    media_type: PostMediaType
    video_id: str | None = None
    image_path: str | None = None
    data_card_type: str | None = None
    data_payload_json: str | None = None
    clip_start_ms: int | None = None
    clip_end_ms: int | None = None
    sort_order: int
    caption: str | None = None
    created_at: str
    updated_at: str
    deleted_at: str | None = None


class PostStatsRecord(BaseModel):
    social_post_id: str
    like_count: int = 0
    comment_count: int = 0
    favorite_count: int = 0
    share_count: int = 0
    view_count: int = 0
    updated_at: str


class PostViewerState(BaseModel):
    is_liked: bool = False
    is_favorited: bool = False


class PostDetailResponse(BaseModel):
    post: SocialPostRecord
    author: PostAuthor
    media: list[PostMediaRecord]
    videos: list[VideoRecord]
    stats: PostStatsRecord | None = None
    viewer_state: PostViewerState | None = None


FeedType = Literal["recommended", "following", "nearby"]
PostCollectionKind = Literal["favorites", "likes"]
FeedSource = Literal[
    "recommended",
    "following",
    "nearby",
    "nearby_city_fallback",
    "nearby_region_fallback",
]


class PostFeedItem(PostDetailResponse):
    feed_source: FeedSource
    sort_strategy: str


class PostFeedResponse(BaseModel):
    feed_type: FeedType
    items: list[PostFeedItem]
    next_cursor: str | None = None
    has_more: bool
    strategy_version: str
    fallback_mode: str | None = None


class PostCollectionResponse(BaseModel):
    collection: PostCollectionKind
    items: list[PostDetailResponse]
    next_cursor: str | None = None
    has_more: bool


class PostViewItem(BaseModel):
    social_post_id: str
    source: str = Field(default="home_feed", max_length=50)
    dwell_time_ms: int = Field(default=0, ge=0, le=86_400_000)


class PostViewsBulkCreate(BaseModel):
    items: list[PostViewItem] = Field(min_length=1, max_length=100)


class PostViewsBulkResponse(BaseModel):
    accepted_post_ids: list[str]
    ignored_post_ids: list[str]


class PostHideCreate(BaseModel):
    source: str = Field(default="home_feed", max_length=50)
    reason: str | None = Field(default=None, max_length=255)


class PostHideResponse(BaseModel):
    success: bool
    social_post_id: str


class PostInteractionCreate(BaseModel):
    source: str | None = Field(default=None, max_length=50)

    @field_validator("source")
    @classmethod
    def normalize_source(cls, value: str | None) -> str | None:
        return _strip_text(value)


class PostLikeResponse(BaseModel):
    success: bool
    social_post_id: str
    is_liked: bool
    stats: PostStatsRecord


class PostFavoriteResponse(BaseModel):
    success: bool
    social_post_id: str
    is_favorited: bool
    stats: PostStatsRecord


class PostCommentCreate(BaseModel):
    content: str = Field(min_length=1, max_length=2000)
    parent_comment_id: str | None = None
    source: str | None = Field(default=None, max_length=50)

    @field_validator("content")
    @classmethod
    def normalize_content(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("content is required.")
        return normalized

    @field_validator("parent_comment_id", "source")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        return _strip_text(value)


class PostCommentRecord(BaseModel):
    comment_id: str
    social_post_id: str
    author_user_id: str
    parent_comment_id: str | None = None
    root_comment_id: str | None = None
    content: str | None = None
    status: str
    source: str | None = None
    created_at: str
    updated_at: str
    deleted_at: str | None = None
    author: PostAuthor
    reply_count: int = 0


class PostCommentListResponse(BaseModel):
    items: list[PostCommentRecord]
    page: int
    page_size: int


class PostCommentCreateResponse(BaseModel):
    comment: PostCommentRecord
    stats: PostStatsRecord


class PostCommentDeleteResponse(BaseModel):
    success: bool
    social_post_id: str
    comment_id: str
    stats: PostStatsRecord


PostShareTargetType = Literal["conversation", "external", "copy_link"]


class PostShareCreate(BaseModel):
    share_target_type: PostShareTargetType = "copy_link"
    conversation_id: str | None = None
    channel: str | None = Field(default=None, max_length=50)
    message_text: str | None = Field(default=None, max_length=500)
    payload: dict[str, Any] | None = None

    @field_validator("conversation_id", "channel", "message_text")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        return _strip_text(value)

    @model_validator(mode="after")
    def validate_target(self) -> "PostShareCreate":
        if self.share_target_type == "conversation" and not self.conversation_id:
            raise ValueError("conversation_id is required when sharing to a conversation.")
        if self.share_target_type != "conversation" and self.conversation_id:
            raise ValueError("conversation_id is only valid for conversation shares.")
        return self


class PostShareRecord(BaseModel):
    post_share_id: str
    social_post_id: str
    shared_by_user_id: str
    share_target_type: str
    target_user_id: str | None = None
    conversation_id: str | None = None
    message_id: str | None = None
    channel: str | None = None
    payload_json: str | None = None
    created_at: str


class PostShareResponse(BaseModel):
    success: bool
    share: PostShareRecord
    stats: PostStatsRecord


class PostFeedStateResponse(BaseModel):
    supported_feed_types: list[FeedType]
    recommended_strategy_version: str
    nearby_requires_location: bool
    nearby_location_privacy: str


class PostListResponse(BaseModel):
    items: list[PostDetailResponse]
    page: int
    page_size: int


class PostDeleteResponse(BaseModel):
    success: bool
    id: str


class PostVideoUploadIntentCreate(BaseModel):
    original_filename: str = Field(max_length=255)
    mime_type: str | None = Field(default=None, max_length=100)
    file_size_bytes: int | None = Field(default=None, ge=0)
    video_duration_ms: int = Field(ge=0)
    captured_at: str | None = None
    caption: str | None = Field(default=None, max_length=255)

    @field_validator("original_filename")
    @classmethod
    def normalize_original_filename(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("original_filename is required.")
        return normalized

    @field_validator("mime_type", "captured_at", "caption")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        return _strip_text(value)


class PostUploadIntentCreate(BaseModel):
    title: str | None = Field(default=None, max_length=120)
    content: str | None = Field(default=None, max_length=2200)
    visibility: PostVisibility = "public"
    location_scope: Literal["none", "region", "city"] = "none"
    location_region: str | None = Field(default=None, max_length=80)
    location_city: str | None = Field(default=None, max_length=80)
    videos: list[PostVideoUploadIntentCreate] = Field(min_length=1, max_length=1)

    @field_validator("title", "content", "location_region", "location_city")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        return _strip_text(value)


class PostUploadIntentResponse(PostDetailResponse):
    max_video_duration_ms: int


class PostClipMediaCreate(BaseModel):
    video_id: str
    clip_start_ms: int = Field(ge=0)
    clip_end_ms: int = Field(ge=0)
    caption: str | None = Field(default=None, max_length=255)

    @field_validator("video_id", "caption")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        return _strip_text(value)

    @model_validator(mode="after")
    def validate_clip_range(self) -> "PostClipMediaCreate":
        if self.clip_end_ms <= self.clip_start_ms:
            raise ValueError("clip_end_ms must be greater than clip_start_ms.")
        if not self.video_id:
            raise ValueError("video_id is required.")
        return self


class PostCreate(BaseModel):
    title: str | None = Field(default=None, max_length=120)
    content: str | None = Field(default=None, max_length=2200)
    visibility: PostVisibility = "public"
    location_scope: Literal["none", "region", "city"] = "none"
    location_region: str | None = Field(default=None, max_length=80)
    location_city: str | None = Field(default=None, max_length=80)
    status: Literal["draft", "published"] = "draft"
    source_tennis_activity_id: str | None = None
    media: list[PostClipMediaCreate] = Field(min_length=1, max_length=1)

    @field_validator("title", "content", "source_tennis_activity_id", "location_region", "location_city")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        return _strip_text(value)


class PostUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=120)
    content: str | None = Field(default=None, max_length=2200)
    visibility: PostVisibility | None = None
    location_scope: Literal["none", "region", "city"] | None = None
    location_region: str | None = Field(default=None, max_length=80)
    location_city: str | None = Field(default=None, max_length=80)

    @field_validator("title", "content", "location_region", "location_city")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        return _strip_text(value)

    @model_validator(mode="after")
    def ensure_has_update(self) -> "PostUpdate":
        if not self.model_fields_set:
            raise ValueError("At least one field is required.")
        return self
