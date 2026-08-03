from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


CoachType = Literal["certified", "non_professional"]
CoachApplicationStatus = Literal["pending", "approved", "rejected", "canceled"]
CoachProfileStatus = Literal["active", "suspended", "revoked"]
CoachIdentityStatus = Literal[
    "normal_user",
    "pending_review",
    "certified_coach",
    "non_professional_coach",
    "review_rejected",
    "coach_suspended",
    "coach_revoked",
]


def _strip_text(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


class CoachApplicationCreate(BaseModel):
    application_type: CoachType
    display_name: str = Field(max_length=50)
    real_name: str | None = Field(default=None, max_length=50)
    phone: str | None = Field(default=None, max_length=30)
    city: str | None = Field(default=None, max_length=80)
    specialties: str | None = Field(default=None, max_length=255)
    coaching_experience: str | None = None
    certification_title: str | None = Field(default=None, max_length=120)
    certification_file_path: str | None = None
    verification_video_path: str | None = None
    note: str | None = None

    @field_validator("display_name")
    @classmethod
    def normalize_display_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("display_name is required.")
        return normalized

    @field_validator(
        "real_name",
        "phone",
        "city",
        "specialties",
        "coaching_experience",
        "certification_title",
        "certification_file_path",
        "verification_video_path",
        "note",
    )
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        return _strip_text(value)

    @model_validator(mode="after")
    def validate_materials(self) -> "CoachApplicationCreate":
        if self.application_type == "certified" and not self.certification_file_path:
            raise ValueError("certification_file_path is required for certified coach applications.")
        if self.application_type == "non_professional" and not self.verification_video_path:
            raise ValueError("verification_video_path is required for non-professional coach applications.")
        return self


class CoachApplicationRecord(BaseModel):
    coach_application_id: str
    applicant_user_id: str
    application_type: CoachType
    status: CoachApplicationStatus
    display_name: str
    real_name: str | None = None
    phone: str | None = None
    city: str | None = None
    specialties: str | None = None
    coaching_experience: str | None = None
    certification_title: str | None = None
    certification_file_path: str | None = None
    verification_video_path: str | None = None
    note: str | None = None
    reviewer_user_id: str | None = None
    reviewed_at: str | None = None
    rejection_reason: str | None = None
    created_at: str
    updated_at: str


class CoachProfileRecord(BaseModel):
    coach_profile_id: str
    user_id: str
    coach_type: CoachType
    status: CoachProfileStatus
    display_name: str
    city: str | None = None
    specialties: str | None = None
    coaching_experience: str | None = None
    certification_title: str | None = None
    certification_file_path: str | None = None
    verification_video_path: str | None = None
    approved_application_id: str | None = None
    approved_by_user_id: str | None = None
    approved_at: str
    suspended_at: str | None = None
    revoked_at: str | None = None
    status_reason: str | None = None
    created_at: str
    updated_at: str


class CoachCapabilities(BaseModel):
    coach_homepage: bool
    course_management: bool
    student_management: bool
    video_review: bool
    service_publishing: bool
    student_consultation: bool


class CoachIdentityResponse(BaseModel):
    status: CoachIdentityStatus
    label: str
    is_coach: bool
    coach_type: CoachType | None = None
    application: CoachApplicationRecord | None = None
    profile: CoachProfileRecord | None = None
    rejection_reason: str | None = None
    capabilities: CoachCapabilities


class CoachApplicationCreateResponse(BaseModel):
    application: CoachApplicationRecord
    identity: CoachIdentityResponse


class AdminCoachApplicationRecord(CoachApplicationRecord):
    applicant_nickname: str
    applicant_phone: str | None = None
    current_coach_type: CoachType | None = None
    current_coach_status: CoachProfileStatus | None = None


class AdminCoachApplicationListResponse(BaseModel):
    items: list[AdminCoachApplicationRecord]
    total: int
    page: int
    page_size: int


class AdminCoachReviewPayload(BaseModel):
    rejection_reason: str | None = Field(default=None, max_length=500)

    @field_validator("rejection_reason")
    @classmethod
    def normalize_rejection_reason(cls, value: str | None) -> str | None:
        return _strip_text(value)


class AdminCoachStatusPayload(BaseModel):
    reason: str | None = Field(default=None, max_length=500)

    @field_validator("reason")
    @classmethod
    def normalize_reason(cls, value: str | None) -> str | None:
        return _strip_text(value)

