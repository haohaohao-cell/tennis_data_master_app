from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


ConversationType = Literal["direct", "group"]
GroupType = Literal["friend_group", "lesson_group", "training_group", "coach_course_group", "custom"]
ConversationContextType = Literal["lesson", "tennis_activity", "video", "social_post", "custom"]
MessageType = Literal[
    "text",
    "image",
    "video",
    "audio",
    "file",
    "post_share",
    "video_share",
    "activity_share",
    "lesson_share",
    "analysis_card",
    "system_event",
    "custom",
]
AttachmentType = Literal["image", "video", "audio", "file", "object_card", "data_card", "link"]
ObjectType = Literal["user", "video", "social_post", "tennis_activity", "lesson", "analysis", "custom"]
NotificationCategory = Literal["interaction", "system", "ai", "coach", "lesson"]


def _strip_text(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


class MessageUserSummary(BaseModel):
    user_id: str
    nickname: str
    avatar_path: str | None = None
    is_coach: bool
    coach_status: str | None = None


class DirectConversationCreate(BaseModel):
    target_user_id: str


class MessageRequestCreate(BaseModel):
    target_user_id: str
    request_message: str | None = Field(default=None, max_length=500)
    source: str | None = Field(default=None, max_length=50)

    @field_validator("target_user_id")
    @classmethod
    def normalize_target_user_id(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("target_user_id is required.")
        return normalized

    @field_validator("request_message", "source")
    @classmethod
    def normalize_text(cls, value: str | None) -> str | None:
        return _strip_text(value)


class GroupConversationCreate(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    group_type: GroupType = "custom"
    member_user_ids: list[str] = Field(min_length=1, max_length=200)
    context_type: ConversationContextType | None = None
    context_id: str | None = None

    @field_validator("title", "context_type", "context_id")
    @classmethod
    def normalize_text(cls, value: str | None) -> str | None:
        return _strip_text(value)


class MessageAttachmentCreate(BaseModel):
    attachment_type: AttachmentType
    media_path: str | None = None
    thumbnail_path: str | None = None
    mime_type: str | None = Field(default=None, max_length=100)
    file_size_bytes: int | None = Field(default=None, ge=0)
    duration_ms: int | None = Field(default=None, ge=0)
    width_px: int | None = Field(default=None, gt=0)
    height_px: int | None = Field(default=None, gt=0)
    object_type: ObjectType | None = None
    object_id: str | None = None
    payload: dict[str, Any] | None = None

    @field_validator("media_path", "thumbnail_path", "mime_type", "object_id")
    @classmethod
    def normalize_text(cls, value: str | None) -> str | None:
        return _strip_text(value)

    @model_validator(mode="after")
    def validate_object_pair(self) -> "MessageAttachmentCreate":
        if (self.object_type is None) != (self.object_id is None):
            raise ValueError("object_type and object_id must be provided together.")
        return self


class MessageCreate(BaseModel):
    message_type: MessageType = "text"
    text_content: str | None = Field(default=None, max_length=5000)
    payload: dict[str, Any] | None = None
    target_object_type: ObjectType | None = None
    target_object_id: str | None = None
    context_object_type: ObjectType | None = None
    context_object_id: str | None = None
    reply_to_message_id: str | None = None
    client_message_id: str | None = Field(default=None, max_length=120)
    attachments: list[MessageAttachmentCreate] = Field(default_factory=list, max_length=10)

    @field_validator(
        "text_content",
        "target_object_id",
        "context_object_id",
        "reply_to_message_id",
        "client_message_id",
    )
    @classmethod
    def normalize_text(cls, value: str | None) -> str | None:
        return _strip_text(value)

    @model_validator(mode="after")
    def validate_message(self) -> "MessageCreate":
        if self.message_type == "text" and not self.text_content:
            raise ValueError("text_content is required for text messages.")
        if (self.target_object_type is None) != (self.target_object_id is None):
            raise ValueError("target_object_type and target_object_id must be provided together.")
        if (self.context_object_type is None) != (self.context_object_id is None):
            raise ValueError("context_object_type and context_object_id must be provided together.")
        return self


class ChatConversationRecord(BaseModel):
    conversation_id: str
    conversation_type: ConversationType
    group_type: GroupType | None = None
    title: str | None = None
    avatar_path: str | None = None
    context_type: str | None = None
    context_id: str | None = None
    status: str
    last_message_id: str | None = None
    last_message_seq: int
    last_message_preview: str | None = None
    last_message_at: str | None = None
    created_at: str
    updated_at: str


class ConversationMemberRecord(BaseModel):
    conversation_member_id: str
    conversation_id: str
    user_id: str
    member_role: str
    status: str
    joined_at: str
    left_at: str | None = None
    last_read_message_id: str | None = None
    last_read_message_seq: int
    last_read_at: str | None = None
    unread_count: int
    muted_until: str | None = None
    pinned_at: str | None = None
    archived_at: str | None = None


class MessageAttachmentRecord(BaseModel):
    attachment_id: str
    message_id: str
    attachment_type: AttachmentType
    media_path: str | None = None
    thumbnail_path: str | None = None
    mime_type: str | None = None
    file_size_bytes: int | None = None
    duration_ms: int | None = None
    width_px: int | None = None
    height_px: int | None = None
    object_type: ObjectType | None = None
    object_id: str | None = None
    payload_json: str | None = None
    sort_order: int
    created_at: str


class ChatMessageRecord(BaseModel):
    message_id: str
    conversation_id: str
    message_seq: int
    sender_user_id: str | None = None
    sender_type: str
    message_type: MessageType
    text_content: str | None = None
    payload_json: str | None = None
    target_object_type: ObjectType | None = None
    target_object_id: str | None = None
    context_object_type: ObjectType | None = None
    context_object_id: str | None = None
    reply_to_message_id: str | None = None
    client_message_id: str | None = None
    status: str
    sent_at: str
    created_at: str
    updated_at: str
    deleted_at: str | None = None
    sender: MessageUserSummary | None = None
    attachments: list[MessageAttachmentRecord] = Field(default_factory=list)


class ConversationListItem(BaseModel):
    conversation: ChatConversationRecord
    member: ConversationMemberRecord
    other_members: list[MessageUserSummary] = Field(default_factory=list)


class ConversationListResponse(BaseModel):
    items: list[ConversationListItem]
    page: int
    page_size: int


class MessageListResponse(BaseModel):
    items: list[ChatMessageRecord]
    conversation_id: str
    next_before_seq: int | None = None


class ConversationCreateResponse(BaseModel):
    conversation: ChatConversationRecord
    member: ConversationMemberRecord
    other_members: list[MessageUserSummary] = Field(default_factory=list)


class MessageRequestRecord(BaseModel):
    message_request_id: str
    requester_user_id: str
    recipient_user_id: str
    conversation_id: str | None = None
    status: str
    request_message: str | None = None
    source: str | None = None
    requested_at: str
    responded_at: str | None = None
    created_at: str
    updated_at: str
    requester: MessageUserSummary
    recipient: MessageUserSummary


class MessageRequestListResponse(BaseModel):
    items: list[MessageRequestRecord]
    page: int
    page_size: int


class MessageRequestActionResponse(BaseModel):
    success: bool
    request: MessageRequestRecord
    conversation: ChatConversationRecord | None = None
    member: ConversationMemberRecord | None = None
    other_members: list[MessageUserSummary] = Field(default_factory=list)


class MessageSendResponse(BaseModel):
    message: ChatMessageRecord


class MarkReadResponse(BaseModel):
    success: bool
    conversation_id: str
    unread_count: int


class UnreadCountsResponse(BaseModel):
    unread_direct_message_count: int
    unread_group_message_count: int
    unread_notification_count: int
    total_unread_count: int


class NotificationEventRecord(BaseModel):
    notification_event_id: str
    event_type: str
    category: NotificationCategory
    actor_user_id: str | None = None
    object_type: str | None = None
    object_id: str | None = None
    context_type: str | None = None
    context_id: str | None = None
    title: str | None = None
    body: str | None = None
    deep_link: str | None = None
    payload_json: str | None = None
    created_at: str


class UserNotificationRecord(BaseModel):
    user_notification_id: str
    notification_event_id: str
    recipient_user_id: str
    status: str
    priority: str
    delivered_at: str
    seen_at: str | None = None
    read_at: str | None = None
    dismissed_at: str | None = None
    created_at: str
    event: NotificationEventRecord
    actor: MessageUserSummary | None = None


class NotificationListResponse(BaseModel):
    items: list[UserNotificationRecord]
    page: int
    page_size: int
    unread_count: int
