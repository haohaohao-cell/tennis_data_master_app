from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


ActivityType = Literal[
    "casual_hit",
    "match",
    "serve_training",
    "forehand_training",
    "backhand_training",
    "multi_ball_drill",
    "stroke_recording",
    "post_match_review",
    "lesson_practice",
    "coach_demo",
    "other",
]
ActivityVisibility = Literal[
    "private",
    "friends",
    "specified_users",
    "lesson_coach",
    "lesson_participants",
    "public",
]
ActivityLocationSource = Literal["device_gps", "video_metadata", "manual_legacy", "unavailable"]
ActivityCoordinateSystem = Literal["wgs84", "gcj02"]
VideoVisibility = Literal[
    "inherit",
    "private",
    "friends",
    "specified_users",
    "lesson_coach",
    "lesson_participants",
    "public",
]
CourtSurface = Literal["hard", "clay", "grass", "carpet", "unknown"]
UploadStatus = Literal["pending", "uploading", "uploaded", "failed", "canceled"]
AnalysisStatus = Literal["uploaded", "queued", "processing", "completed", "failed", "canceled"]
CameraViewAngle = Literal["overhead", "horizontal"]
CameraViewPosition = Literal["side", "rear", "front", "rear_side", "front_side"]
PlayerSlot = Literal["A", "B"]


def _strip_text(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


class ActivityLocation(BaseModel):
    source: ActivityLocationSource
    latitude: float | None = None
    longitude: float | None = None
    accuracy_m: float | None = None
    captured_at: str | None = None
    country_code: str | None = Field(default=None, max_length=8)
    region: str | None = Field(default=None, max_length=80)
    city: str | None = Field(default=None, max_length=80)
    district: str | None = Field(default=None, max_length=80)
    address_label: str | None = Field(default=None, max_length=255)
    coordinate_system: ActivityCoordinateSystem | None = None


class ActivityLocationCreate(BaseModel):
    source: ActivityLocationSource = "unavailable"
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    accuracy_m: float | None = Field(default=None, ge=0)
    captured_at: str | None = None
    country_code: str | None = Field(default=None, max_length=8)
    region: str | None = Field(default=None, max_length=80)
    city: str | None = Field(default=None, max_length=80)
    district: str | None = Field(default=None, max_length=80)
    address_label: str | None = Field(default=None, max_length=255)
    coordinate_system: ActivityCoordinateSystem | None = "wgs84"

    @field_validator(
        "captured_at",
        "country_code",
        "region",
        "city",
        "district",
        "address_label",
    )
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        return _strip_text(value)

    @model_validator(mode="after")
    def validate_device_location(self) -> "ActivityLocationCreate":
        coordinate_sources = {"device_gps", "video_metadata"}
        if self.source in coordinate_sources and (self.latitude is None or self.longitude is None):
            raise ValueError(f"{self.source} location requires latitude and longitude.")
        if self.source not in coordinate_sources:
            self.latitude = None
            self.longitude = None
            self.accuracy_m = None
            self.coordinate_system = None
        return self


class VideoUploadIntentCreate(BaseModel):
    original_filename: str = Field(max_length=255)
    mime_type: str | None = Field(default=None, max_length=100)
    file_size_bytes: int | None = Field(default=None, ge=0)
    captured_at: str | None = None
    camera_view_angle: CameraViewAngle | None = None
    camera_view_position: CameraViewPosition | None = None
    player_a_name: str | None = Field(default=None, max_length=50)
    player_b_name: str | None = Field(default=None, max_length=50)
    primary_player_slot: PlayerSlot | None = None
    visibility: VideoVisibility = "inherit"

    @field_validator("original_filename")
    @classmethod
    def normalize_original_filename(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("original_filename is required.")
        return normalized

    @field_validator("mime_type", "captured_at", "player_a_name", "player_b_name")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        return _strip_text(value)


class UploadIntentCreate(BaseModel):
    title: str | None = Field(default=None, max_length=120)
    lesson_id: str | None = None
    activity_type: ActivityType = "other"
    default_visibility: ActivityVisibility = "private"
    started_at: str | None = None
    ended_at: str | None = None
    location_name: str | None = Field(default=None, max_length=120)
    location: ActivityLocationCreate | None = None
    court_surface: CourtSurface | None = None
    opponent_user_id: str | None = None
    opponent_name: str | None = Field(default=None, max_length=50)
    note: str | None = None
    videos: list[VideoUploadIntentCreate] = Field(min_length=1, max_length=20)

    @field_validator(
        "title",
        "lesson_id",
        "started_at",
        "ended_at",
        "location_name",
        "opponent_user_id",
        "opponent_name",
        "note",
    )
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        return _strip_text(value)

    @model_validator(mode="after")
    def validate_lesson_activity_pair(self) -> "UploadIntentCreate":
        if self.lesson_id and self.activity_type not in {"lesson_practice", "coach_demo"}:
            raise ValueError("lesson uploads must use lesson_practice or coach_demo activity_type.")
        return self


class TennisActivityCreate(BaseModel):
    lesson_id: str | None = None
    title: str | None = Field(default=None, max_length=120)
    activity_type: ActivityType = "other"
    default_visibility: ActivityVisibility = "private"
    started_at: str | None = None
    ended_at: str | None = None
    location_name: str | None = Field(default=None, max_length=120)
    location: ActivityLocationCreate | None = None
    court_surface: CourtSurface | None = None
    opponent_user_id: str | None = None
    opponent_name: str | None = Field(default=None, max_length=50)
    note: str | None = None

    @field_validator(
        "lesson_id",
        "title",
        "started_at",
        "ended_at",
        "location_name",
        "opponent_user_id",
        "opponent_name",
        "note",
    )
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        return _strip_text(value)


class TennisActivityRecord(BaseModel):
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
    court_surface: CourtSurface | None = None
    opponent_user_id: str | None = None
    opponent_name: str | None = None
    note: str | None = None
    analysis_summary_status: str | None = None
    created_at: str
    updated_at: str


class VideoRecord(BaseModel):
    video_id: str
    tennis_activity_id: str | None = None
    owner_user_id: str
    uploader_user_id: str
    filename: str
    original_filename: str | None = None
    video_path: str
    thumbnail_path: str | None = None
    mime_type: str | None = None
    file_size_bytes: int | None = None
    file_hash: str | None = None
    video_duration_ms: int | None = None
    video_frame_count: int | None = None
    video_fps: float | None = None
    video_width_px: int | None = None
    video_height_px: int | None = None
    camera_view_angle: CameraViewAngle | None = None
    camera_view_position: CameraViewPosition | None = None
    player_a_name: str | None = None
    player_b_name: str | None = None
    primary_player_slot: PlayerSlot | None = None
    visibility: VideoVisibility
    upload_status: UploadStatus
    upload_error_message: str | None = None
    uploaded_at: str | None = None
    analysis_status: AnalysisStatus
    analysis_version: str | None = None
    error_message: str | None = None
    captured_at: str | None = None
    created_at: str
    updated_at: str


class UploadIntentResponse(BaseModel):
    activity: TennisActivityRecord
    videos: list[VideoRecord]


class ActivityDetailLesson(BaseModel):
    lesson_id: str
    coach_user_id: str
    title: str | None = None
    lesson_type: str
    status: str
    started_at: str | None = None
    ended_at: str | None = None
    location_name: str | None = None
    court_surface: CourtSurface | None = None
    training_content: str | None = None
    coach_summary: str | None = None
    homework: str | None = None
    next_focus: str | None = None
    viewer_role: Literal["coach", "student"] | None = None


class ActivityDetailPermissions(BaseModel):
    can_view: bool
    can_manage: bool
    can_play_videos: bool


class ActivityDetailSummary(BaseModel):
    video_count: int
    uploaded_video_count: int
    upload_status: UploadStatus | Literal["mixed"]
    analysis_status: AnalysisStatus | Literal["mixed", "none"]


class ActivityDetailResponse(BaseModel):
    activity: TennisActivityRecord
    videos: list[VideoRecord]
    lesson: ActivityDetailLesson | None = None
    permissions: ActivityDetailPermissions
    summary: ActivityDetailSummary


class VideoFileUploadResponse(BaseModel):
    video: VideoRecord


class UploadCompleteResponse(BaseModel):
    activity: TennisActivityRecord
    videos: list[VideoRecord]
    queued_count: int


class UploadCancelResponse(BaseModel):
    success: bool
    activity: TennisActivityRecord
    videos: list[VideoRecord]


class LessonOption(BaseModel):
    lesson_id: str
    coach_user_id: str
    title: str | None = None
    lesson_type: str
    status: str
    started_at: str | None = None
    ended_at: str | None = None
    location_name: str | None = None
    role: Literal["coach", "student"]


class LessonOptionListResponse(BaseModel):
    items: list[LessonOption]
