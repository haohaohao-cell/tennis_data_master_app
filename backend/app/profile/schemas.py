from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from backend.app.uploads.schemas import (
    ActivityLocation,
    ActivityType,
    ActivityVisibility,
    AnalysisStatus,
    UploadStatus,
)

ActivityUploadStatus = UploadStatus | Literal["mixed"]
ActivityAnalysisStatus = AnalysisStatus | Literal["mixed", "none"]


class ProfileContentVideoSummary(BaseModel):
    video_id: str
    original_filename: str | None = None
    video_path: str
    thumbnail_path: str | None = None
    mime_type: str | None = None
    file_size_bytes: int | None = None
    upload_status: UploadStatus
    analysis_status: AnalysisStatus
    uploaded_at: str | None = None
    created_at: str


class ProfileContentActivity(BaseModel):
    tennis_activity_id: str
    owner_user_id: str
    lesson_id: str | None = None
    title: str | None = None
    activity_type: ActivityType
    default_visibility: ActivityVisibility
    started_at: str | None = None
    ended_at: str | None = None
    location_name: str | None = None
    location: ActivityLocation | None = None
    note: str | None = None
    analysis_summary_status: str | None = None
    created_at: str
    updated_at: str
    video_count: int
    uploaded_video_count: int
    upload_status: ActivityUploadStatus
    analysis_status: ActivityAnalysisStatus
    first_video: ProfileContentVideoSummary | None = None


class ProfileContentPost(BaseModel):
    social_post_id: str
    source_tennis_activity_id: str | None = None
    title: str | None = None
    content: str | None = None
    visibility: str
    status: str
    published_at: str | None = None
    created_at: str
    updated_at: str
    media_count: int
    first_media_type: str | None = None
    first_image_path: str | None = None
    first_video_path: str | None = None
    first_video_thumbnail_path: str | None = None


class ProfileContentLesson(BaseModel):
    lesson_id: str
    coach_user_id: str
    title: str | None = None
    lesson_type: str
    status: str
    started_at: str | None = None
    ended_at: str | None = None
    location_name: str | None = None
    training_content: str | None = None
    coach_summary: str | None = None
    homework: str | None = None
    next_focus: str | None = None
    role: Literal["coach", "student"]
    activity_count: int
    video_count: int
    updated_at: str


class ProfileContentStats(BaseModel):
    posts: int
    matches: int
    training: int
    courses: int
    received_like_count: int
    friend_count: int
    following_count: int
    follower_count: int


class ProfileContentResponse(BaseModel):
    stats: ProfileContentStats
    posts: list[ProfileContentPost]
    matches: list[ProfileContentActivity]
    training: list[ProfileContentActivity]
    courses: list[ProfileContentLesson]
