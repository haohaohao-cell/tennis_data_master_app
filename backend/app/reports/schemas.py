from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator


ReportTargetType = Literal["user", "social_post", "post_comment", "chat_message", "chat_conversation", "video"]
ReportReasonType = Literal["spam", "harassment", "inappropriate", "fraud", "privacy", "other"]
ReportStatus = Literal["pending", "reviewing", "resolved", "rejected"]


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
