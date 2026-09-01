from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator


ReportTargetType = Literal["user", "social_post", "post_comment", "chat_message", "chat_conversation", "video"]
ReportReasonType = Literal["spam", "harassment", "inappropriate", "fraud", "privacy", "other"]
ReportStatus = Literal["pending", "reviewing", "resolved", "rejected"]
MessageReportTargetKind = Literal["message", "business_object", "media"]
MessageReportStatus = Literal["open", "under_review", "resolved", "rejected", "closed"]


def _strip_text(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


class ContentReportCreate(BaseModel):
    target_type: ReportTargetType
    target_id: str
    reason_type: ReportReasonType
    reason_text: str | None = Field(default=None, max_length=1000)
    source: str | None = Field(default=None, max_length=50)

    @field_validator("target_id", "reason_text", "source")
    @classmethod
    def normalize_text(cls, value: str | None) -> str | None:
        return _strip_text(value)


class ContentReportRecord(BaseModel):
    content_report_id: str
    reporter_user_id: str
    target_type: ReportTargetType
    target_id: str
    reason_type: ReportReasonType
    reason_text: str | None = None
    source: str | None = None
    status: ReportStatus
    reviewer_user_id: str | None = None
    reviewed_at: str | None = None
    resolution_note: str | None = None
    created_at: str
    updated_at: str


class ContentReportCreateResponse(BaseModel):
    success: bool
    report: ContentReportRecord


class MessageReportCreate(BaseModel):
    target_kind: MessageReportTargetKind
    target_id: str = Field(min_length=1, max_length=120)
    reason_code: ReportReasonType
    description: str | None = Field(default=None, max_length=1000)
    idempotency_key: str = Field(min_length=1, max_length=120)

    @field_validator("target_id", "description", "idempotency_key")
    @classmethod
    def normalize_message_report_text(cls, value: str | None) -> str | None:
        return _strip_text(value)


class MessageReportRecord(BaseModel):
    report_id: str
    reporter_user_id: str
    target_kind: MessageReportTargetKind
    target_id: str
    conversation_id: str
    message_id: str
    object_type: str | None = None
    reason_code: ReportReasonType
    description: str | None = None
    status: MessageReportStatus
    resolved_at: str | None = None
    resolved_by: str | None = None
    resolution_code: str | None = None
    idempotency_key: str
    created_at: str
    updated_at: str


class MessageReportResponse(BaseModel):
    success: bool
    report: MessageReportRecord


class MessageReportListResponse(BaseModel):
    items: list[MessageReportRecord]
    page: int
    page_size: int


class MessageReportUpdate(BaseModel):
    status: MessageReportStatus
    resolution_code: str = Field(min_length=1, max_length=80)

    @field_validator("resolution_code")
    @classmethod
    def normalize_resolution_code(cls, value: str) -> str:
        return value.strip()
