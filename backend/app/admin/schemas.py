from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from backend.app.auth.schemas import DeviceInfo, UserPublic


AdminRole = Literal["owner", "admin", "operator", "viewer"]
AdminStatus = Literal["active", "disabled"]
UserStatus = Literal["active", "disabled", "deleted"]
PlayingHand = Literal["right", "left", "unknown"]
CoachStatus = Literal["pending", "active", "disabled", "rejected"]
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
CourtSurface = Literal["hard", "clay", "grass", "carpet", "unknown"]
AnalysisSummaryStatus = Literal["pending", "processing", "completed", "failed"]
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
UploadStatus = Literal["pending", "uploading", "uploaded", "failed", "canceled"]
AnalysisStatus = Literal["uploaded", "queued", "processing", "completed", "failed", "canceled"]
CameraViewAngle = Literal["overhead", "horizontal"]
CameraViewPosition = Literal["side", "rear", "front", "rear_side", "front_side"]
PlayerSlot = Literal["A", "B"]
PostVisibility = Literal["private", "friends", "followers", "specified_users", "public"]
PostStatus = Literal["draft", "published", "hidden", "deleted"]
PostReviewStatus = Literal["pending", "approved", "rejected"]
PostLocationScope = Literal["none", "region", "city"]


def _strip_text(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


class PaginationResponse(BaseModel):
    total: int
    page: int
    page_size: int


class AdminDeleteResponse(BaseModel):
    success: bool
    id: str


class AdminLoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=1, max_length=128)
    device: DeviceInfo | None = None

    @field_validator("username")
    @classmethod
    def normalize_username(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Username cannot be empty.")
        return normalized


class AdminLoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    access_expires_at: str
    refresh_expires_at: str
    user: UserPublic
    admin_role: AdminRole


class AdminUserRecord(BaseModel):
    user_id: str
    nickname: str
    avatar_path: str | None = None
    phone: str | None = None
    email: str | None = None
    status: UserStatus
    profile_completed: bool
    playing_hand: PlayingHand
    is_coach: bool
    coach_status: CoachStatus | None = None
    coach_verified_at: str | None = None
    admin_role: AdminRole | None = None
    admin_status: AdminStatus | None = None
    created_at: str
    updated_at: str
    deleted_at: str | None = None


class AdminUserListResponse(PaginationResponse):
    items: list[AdminUserRecord]


class AdminUserCreate(BaseModel):
    nickname: str = Field(max_length=50)
    avatar_path: str | None = None
    phone: str | None = Field(default=None, max_length=30)
    email: str | None = Field(default=None, max_length=255)
    status: UserStatus = "active"
    profile_completed: bool = False
    playing_hand: PlayingHand = "right"
    is_coach: bool = False
    coach_status: CoachStatus | None = None
    coach_verified_at: str | None = None

    @field_validator("nickname")
    @classmethod
    def normalize_nickname(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Nickname cannot be empty.")
        return normalized

    @field_validator("avatar_path", "phone", "email", "coach_verified_at")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        return _strip_text(value)

    @model_validator(mode="after")
    def validate_coach_fields(self) -> "AdminUserCreate":
        if not self.is_coach and self.coach_status is not None:
            raise ValueError("coach_status requires is_coach=true.")
        if self.coach_verified_at is not None and (
            not self.is_coach or self.coach_status != "active"
        ):
            raise ValueError("coach_verified_at requires active coach status.")
        return self


class AdminUserUpdate(BaseModel):
    nickname: str | None = Field(default=None, max_length=50)
    avatar_path: str | None = None
    phone: str | None = Field(default=None, max_length=30)
    email: str | None = Field(default=None, max_length=255)
    status: UserStatus | None = None
    profile_completed: bool | None = None
    playing_hand: PlayingHand | None = None
    is_coach: bool | None = None
    coach_status: CoachStatus | None = None
    coach_verified_at: str | None = None

    @field_validator("nickname")
    @classmethod
    def normalize_nickname(cls, value: str | None) -> str | None:
        normalized = _strip_text(value)
        if value is not None and normalized is None:
            raise ValueError("Nickname cannot be empty.")
        return normalized

    @field_validator("avatar_path", "phone", "email", "coach_verified_at")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        return _strip_text(value)

    @model_validator(mode="after")
    def ensure_has_update(self) -> "AdminUserUpdate":
        if not self.model_fields_set:
            raise ValueError("At least one field is required.")
        return self


class AdminTennisActivityRecord(BaseModel):
    tennis_activity_id: str
    owner_user_id: str
    lesson_id: str | None = None
    title: str | None = None
    activity_type: ActivityType
    default_visibility: ActivityVisibility
    started_at: str | None = None
    ended_at: str | None = None
    location_name: str | None = None
    location_source: ActivityLocationSource | None = None
    location_latitude: float | None = None
    location_longitude: float | None = None
    location_accuracy_m: float | None = None
    location_captured_at: str | None = None
    location_country_code: str | None = None
    location_region: str | None = None
    location_city: str | None = None
    location_district: str | None = None
    location_address_label: str | None = None
    location_coordinate_system: ActivityCoordinateSystem | None = None
    court_surface: CourtSurface | None = None
    opponent_user_id: str | None = None
    opponent_name: str | None = None
    note: str | None = None
    analysis_summary_status: AnalysisSummaryStatus | None = None
    created_at: str
    updated_at: str
    deleted_at: str | None = None


class AdminTennisActivityListResponse(PaginationResponse):
    items: list[AdminTennisActivityRecord]


class AdminTennisActivityCreate(BaseModel):
    owner_user_id: str
    lesson_id: str | None = None
    title: str | None = Field(default=None, max_length=120)
    activity_type: ActivityType = "other"
    default_visibility: ActivityVisibility = "private"
    started_at: str | None = None
    ended_at: str | None = None
    location_name: str | None = Field(default=None, max_length=120)
    location_source: ActivityLocationSource | None = None
    location_latitude: float | None = Field(default=None, ge=-90, le=90)
    location_longitude: float | None = Field(default=None, ge=-180, le=180)
    location_accuracy_m: float | None = Field(default=None, ge=0)
    location_captured_at: str | None = None
    location_country_code: str | None = Field(default=None, max_length=8)
    location_region: str | None = Field(default=None, max_length=80)
    location_city: str | None = Field(default=None, max_length=80)
    location_district: str | None = Field(default=None, max_length=80)
    location_address_label: str | None = Field(default=None, max_length=255)
    location_coordinate_system: ActivityCoordinateSystem | None = None
    court_surface: CourtSurface | None = None
    opponent_user_id: str | None = None
    opponent_name: str | None = Field(default=None, max_length=50)
    note: str | None = None
    analysis_summary_status: AnalysisSummaryStatus | None = None

    @field_validator(
        "owner_user_id",
        "lesson_id",
        "title",
        "started_at",
        "ended_at",
        "location_name",
        "location_captured_at",
        "location_country_code",
        "location_region",
        "location_city",
        "location_district",
        "location_address_label",
        "opponent_user_id",
        "opponent_name",
        "note",
    )
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        return _strip_text(value)

    @model_validator(mode="after")
    def validate_owner(self) -> "AdminTennisActivityCreate":
        if not self.owner_user_id:
            raise ValueError("owner_user_id is required.")
        if self.opponent_user_id is not None and self.opponent_user_id == self.owner_user_id:
            raise ValueError("opponent_user_id cannot equal owner_user_id.")
        return self


class AdminTennisActivityUpdate(BaseModel):
    owner_user_id: str | None = None
    lesson_id: str | None = None
    title: str | None = Field(default=None, max_length=120)
    activity_type: ActivityType | None = None
    default_visibility: ActivityVisibility | None = None
    started_at: str | None = None
    ended_at: str | None = None
    location_name: str | None = Field(default=None, max_length=120)
    location_source: ActivityLocationSource | None = None
    location_latitude: float | None = Field(default=None, ge=-90, le=90)
    location_longitude: float | None = Field(default=None, ge=-180, le=180)
    location_accuracy_m: float | None = Field(default=None, ge=0)
    location_captured_at: str | None = None
    location_country_code: str | None = Field(default=None, max_length=8)
    location_region: str | None = Field(default=None, max_length=80)
    location_city: str | None = Field(default=None, max_length=80)
    location_district: str | None = Field(default=None, max_length=80)
    location_address_label: str | None = Field(default=None, max_length=255)
    location_coordinate_system: ActivityCoordinateSystem | None = None
    court_surface: CourtSurface | None = None
    opponent_user_id: str | None = None
    opponent_name: str | None = Field(default=None, max_length=50)
    note: str | None = None
    analysis_summary_status: AnalysisSummaryStatus | None = None

    @field_validator(
        "owner_user_id",
        "lesson_id",
        "title",
        "started_at",
        "ended_at",
        "location_name",
        "location_captured_at",
        "location_country_code",
        "location_region",
        "location_city",
        "location_district",
        "location_address_label",
        "opponent_user_id",
        "opponent_name",
        "note",
    )
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        return _strip_text(value)

    @model_validator(mode="after")
    def ensure_has_update(self) -> "AdminTennisActivityUpdate":
        if not self.model_fields_set:
            raise ValueError("At least one field is required.")
        return self


class AdminVideoRecord(BaseModel):
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
    frame_data_path: str | None = None
    frame_data_version: str | None = None
    player_a_user_id: str | None = None
    player_b_user_id: str | None = None
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
    deleted_at: str | None = None


class AdminVideoListResponse(PaginationResponse):
    items: list[AdminVideoRecord]


class AdminVideoCreate(BaseModel):
    tennis_activity_id: str | None = None
    owner_user_id: str
    uploader_user_id: str
    filename: str = Field(max_length=255)
    original_filename: str | None = None
    video_path: str
    thumbnail_path: str | None = None
    mime_type: str | None = Field(default=None, max_length=100)
    file_size_bytes: int | None = Field(default=None, ge=0)
    file_hash: str | None = Field(default=None, max_length=128)
    video_duration_ms: int | None = Field(default=None, ge=0)
    video_frame_count: int | None = Field(default=None, ge=0)
    video_fps: float | None = Field(default=None, gt=0)
    video_width_px: int | None = Field(default=None, gt=0)
    video_height_px: int | None = Field(default=None, gt=0)
    camera_view_angle: CameraViewAngle | None = None
    camera_view_position: CameraViewPosition | None = None
    frame_data_path: str | None = None
    frame_data_version: str | None = Field(default=None, max_length=30)
    player_a_user_id: str | None = None
    player_b_user_id: str | None = None
    player_a_name: str | None = Field(default=None, max_length=50)
    player_b_name: str | None = Field(default=None, max_length=50)
    primary_player_slot: PlayerSlot | None = None
    visibility: VideoVisibility = "inherit"
    upload_status: UploadStatus = "uploaded"
    upload_error_message: str | None = None
    uploaded_at: str | None = None
    analysis_status: AnalysisStatus = "uploaded"
    analysis_version: str | None = Field(default=None, max_length=50)
    error_message: str | None = None
    captured_at: str | None = None

    @field_validator("*")
    @classmethod
    def normalize_text_fields(cls, value: object) -> object:
        return _strip_text(value) if isinstance(value, str) else value

    @model_validator(mode="after")
    def validate_required_ids(self) -> "AdminVideoCreate":
        if not self.owner_user_id:
            raise ValueError("owner_user_id is required.")
        if not self.uploader_user_id:
            raise ValueError("uploader_user_id is required.")
        if self.player_a_user_id and self.player_b_user_id and self.player_a_user_id == self.player_b_user_id:
            raise ValueError("player_a_user_id cannot equal player_b_user_id.")
        return self


class AdminVideoUpdate(BaseModel):
    tennis_activity_id: str | None = None
    owner_user_id: str | None = None
    uploader_user_id: str | None = None
    filename: str | None = Field(default=None, max_length=255)
    original_filename: str | None = None
    video_path: str | None = None
    thumbnail_path: str | None = None
    mime_type: str | None = Field(default=None, max_length=100)
    file_size_bytes: int | None = Field(default=None, ge=0)
    file_hash: str | None = Field(default=None, max_length=128)
    video_duration_ms: int | None = Field(default=None, ge=0)
    video_frame_count: int | None = Field(default=None, ge=0)
    video_fps: float | None = Field(default=None, gt=0)
    video_width_px: int | None = Field(default=None, gt=0)
    video_height_px: int | None = Field(default=None, gt=0)
    camera_view_angle: CameraViewAngle | None = None
    camera_view_position: CameraViewPosition | None = None
    frame_data_path: str | None = None
    frame_data_version: str | None = Field(default=None, max_length=30)
    player_a_user_id: str | None = None
    player_b_user_id: str | None = None
    player_a_name: str | None = Field(default=None, max_length=50)
    player_b_name: str | None = Field(default=None, max_length=50)
    primary_player_slot: PlayerSlot | None = None
    visibility: VideoVisibility | None = None
    upload_status: UploadStatus | None = None
    upload_error_message: str | None = None
    uploaded_at: str | None = None
    analysis_status: AnalysisStatus | None = None
    analysis_version: str | None = Field(default=None, max_length=50)
    error_message: str | None = None
    captured_at: str | None = None

    @field_validator("*")
    @classmethod
    def normalize_text_fields(cls, value: object) -> object:
        return _strip_text(value) if isinstance(value, str) else value

    @model_validator(mode="after")
    def ensure_has_update(self) -> "AdminVideoUpdate":
        if not self.model_fields_set:
            raise ValueError("At least one field is required.")
        return self


class AdminPostRecord(BaseModel):
    social_post_id: str
    author_user_id: str
    source_tennis_activity_id: str | None = None
    title: str | None = None
    content: str | None = None
    visibility: PostVisibility
    status: PostStatus
    review_status: PostReviewStatus = "approved"
    reviewed_at: str | None = None
    reviewer_user_id: str | None = None
    review_reason: str | None = None
    location_scope: PostLocationScope = "none"
    location_region: str | None = None
    location_city: str | None = None
    published_at: str | None = None
    created_at: str
    updated_at: str
    deleted_at: str | None = None


class AdminPostListResponse(PaginationResponse):
    items: list[AdminPostRecord]


class AdminPostCreate(BaseModel):
    author_user_id: str
    source_tennis_activity_id: str | None = None
    title: str | None = Field(default=None, max_length=120)
    content: str | None = None
    visibility: PostVisibility = "private"
    status: PostStatus = "draft"
    review_status: PostReviewStatus = "approved"
    reviewed_at: str | None = None
    reviewer_user_id: str | None = None
    review_reason: str | None = Field(default=None, max_length=500)
    location_scope: PostLocationScope = "none"
    location_region: str | None = Field(default=None, max_length=80)
    location_city: str | None = Field(default=None, max_length=80)
    published_at: str | None = None

    @field_validator(
        "author_user_id",
        "source_tennis_activity_id",
        "title",
        "content",
        "reviewed_at",
        "reviewer_user_id",
        "review_reason",
        "location_region",
        "location_city",
        "published_at",
    )
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        return _strip_text(value)

    @model_validator(mode="after")
    def validate_author(self) -> "AdminPostCreate":
        if not self.author_user_id:
            raise ValueError("author_user_id is required.")
        return self


class AdminPostUpdate(BaseModel):
    author_user_id: str | None = None
    source_tennis_activity_id: str | None = None
    title: str | None = Field(default=None, max_length=120)
    content: str | None = None
    visibility: PostVisibility | None = None
    status: PostStatus | None = None
    review_status: PostReviewStatus | None = None
    reviewed_at: str | None = None
    reviewer_user_id: str | None = None
    review_reason: str | None = Field(default=None, max_length=500)
    location_scope: PostLocationScope | None = None
    location_region: str | None = Field(default=None, max_length=80)
    location_city: str | None = Field(default=None, max_length=80)
    published_at: str | None = None

    @field_validator(
        "author_user_id",
        "source_tennis_activity_id",
        "title",
        "content",
        "reviewed_at",
        "reviewer_user_id",
        "review_reason",
        "location_region",
        "location_city",
        "published_at",
    )
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        return _strip_text(value)

    @model_validator(mode="after")
    def ensure_has_update(self) -> "AdminPostUpdate":
        if not self.model_fields_set:
            raise ValueError("At least one field is required.")
        return self
