-- SQLite schema for the tennis data master app core business model.
-- Source of truth: docs/data/tennis_global_data_dictionary.md
-- Business boundaries:
-- users -> tennis_activities -> videos -> points -> shots
-- lessons organize teaching relationships; social_posts publish selected content.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
    user_id TEXT PRIMARY KEY,
    nickname TEXT NOT NULL CHECK (length(nickname) <= 50),
    avatar_path TEXT,
    phone TEXT CHECK (phone IS NULL OR length(phone) <= 30),
    email TEXT CHECK (email IS NULL OR length(email) <= 255),
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'disabled', 'deleted')),
    profile_completed INTEGER NOT NULL DEFAULT 0 CHECK (profile_completed IN (0, 1)),
    playing_hand TEXT NOT NULL DEFAULT 'right'
        CHECK (playing_hand IN ('right', 'left', 'unknown')),
    is_coach INTEGER NOT NULL DEFAULT 0 CHECK (is_coach IN (0, 1)),
    coach_status TEXT CHECK (
        coach_status IN ('pending', 'active', 'disabled', 'rejected')
        OR coach_status IS NULL
    ),
    coach_verified_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at TEXT,
    CHECK (is_coach = 1 OR coach_status IS NULL),
    CHECK (coach_verified_at IS NULL OR (is_coach = 1 AND coach_status = 'active'))
);

CREATE TABLE IF NOT EXISTS admin_users (
    admin_user_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL UNIQUE,
    role TEXT NOT NULL DEFAULT 'operator'
        CHECK (role IN ('owner', 'admin', 'operator', 'viewer')),
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'disabled')),
    note TEXT CHECK (note IS NULL OR length(note) <= 255),
    created_by_user_id TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    disabled_at TEXT,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    FOREIGN KEY (created_by_user_id) REFERENCES users(user_id)
);

CREATE TABLE IF NOT EXISTS admin_credentials (
    admin_credential_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL UNIQUE,
    username TEXT NOT NULL CHECK (length(username) <= 50),
    username_normalized TEXT NOT NULL CHECK (length(username_normalized) <= 50),
    password_hash TEXT NOT NULL CHECK (length(password_hash) <= 255),
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'disabled')),
    last_login_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS auth_identities (
    identity_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    provider TEXT NOT NULL
        CHECK (provider IN ('phone', 'wechat', 'apple')),
    provider_subject TEXT NOT NULL CHECK (length(provider_subject) <= 255),
    provider_subject_normalized TEXT NOT NULL CHECK (length(provider_subject_normalized) <= 255),
    is_verified INTEGER NOT NULL DEFAULT 0 CHECK (is_verified IN (0, 1)),
    verified_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at TEXT,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS auth_sessions (
    session_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    access_token_hash TEXT NOT NULL CHECK (length(access_token_hash) = 64),
    refresh_token_hash TEXT NOT NULL CHECK (length(refresh_token_hash) = 64),
    device_name TEXT CHECK (device_name IS NULL OR length(device_name) <= 120),
    platform TEXT CHECK (platform IS NULL OR length(platform) <= 50),
    ip_address TEXT CHECK (ip_address IS NULL OR length(ip_address) <= 64),
    user_agent TEXT CHECK (user_agent IS NULL OR length(user_agent) <= 255),
    access_expires_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    revoked_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS auth_verification_codes (
    verification_code_id TEXT PRIMARY KEY,
    provider TEXT NOT NULL DEFAULT 'phone'
        CHECK (provider IN ('phone')),
    recipient TEXT NOT NULL CHECK (length(recipient) <= 255),
    recipient_normalized TEXT NOT NULL CHECK (length(recipient_normalized) <= 255),
    code_hash TEXT NOT NULL CHECK (length(code_hash) = 64),
    purpose TEXT NOT NULL DEFAULT 'login'
        CHECK (purpose IN ('login', 'bind_identity')),
    expires_at TEXT NOT NULL,
    consumed_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS coach_applications (
    coach_application_id TEXT PRIMARY KEY,
    applicant_user_id TEXT NOT NULL,
    application_type TEXT NOT NULL
        CHECK (application_type IN ('certified', 'non_professional')),
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'approved', 'rejected', 'canceled')),
    display_name TEXT NOT NULL CHECK (length(display_name) <= 50),
    real_name TEXT CHECK (real_name IS NULL OR length(real_name) <= 50),
    phone TEXT CHECK (phone IS NULL OR length(phone) <= 30),
    city TEXT CHECK (city IS NULL OR length(city) <= 80),
    specialties TEXT CHECK (specialties IS NULL OR length(specialties) <= 255),
    coaching_experience TEXT,
    certification_title TEXT CHECK (certification_title IS NULL OR length(certification_title) <= 120),
    certification_file_path TEXT,
    verification_video_path TEXT,
    note TEXT,
    reviewer_user_id TEXT,
    reviewed_at TEXT,
    rejection_reason TEXT CHECK (rejection_reason IS NULL OR length(rejection_reason) <= 500),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (application_type <> 'certified' OR certification_file_path IS NOT NULL),
    CHECK (application_type <> 'non_professional' OR verification_video_path IS NOT NULL),
    FOREIGN KEY (applicant_user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    FOREIGN KEY (reviewer_user_id) REFERENCES users(user_id)
);

CREATE TABLE IF NOT EXISTS coach_profiles (
    coach_profile_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL UNIQUE,
    coach_type TEXT NOT NULL
        CHECK (coach_type IN ('certified', 'non_professional')),
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'suspended', 'revoked')),
    display_name TEXT NOT NULL CHECK (length(display_name) <= 50),
    city TEXT CHECK (city IS NULL OR length(city) <= 80),
    specialties TEXT CHECK (specialties IS NULL OR length(specialties) <= 255),
    coaching_experience TEXT,
    certification_title TEXT CHECK (certification_title IS NULL OR length(certification_title) <= 120),
    certification_file_path TEXT,
    verification_video_path TEXT,
    approved_application_id TEXT,
    approved_by_user_id TEXT,
    approved_at TEXT NOT NULL,
    suspended_at TEXT,
    revoked_at TEXT,
    status_reason TEXT CHECK (status_reason IS NULL OR length(status_reason) <= 500),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    FOREIGN KEY (approved_application_id) REFERENCES coach_applications(coach_application_id),
    FOREIGN KEY (approved_by_user_id) REFERENCES users(user_id)
);

CREATE TABLE IF NOT EXISTS lessons (
    lesson_id TEXT PRIMARY KEY,
    coach_user_id TEXT NOT NULL,
    title TEXT CHECK (title IS NULL OR length(title) <= 120),
    lesson_type TEXT NOT NULL DEFAULT 'private'
        CHECK (lesson_type IN ('private', 'group', 'camp', 'trial', 'other')),
    status TEXT NOT NULL DEFAULT 'draft'
        CHECK (status IN ('draft', 'scheduled', 'completed', 'canceled')),
    started_at TEXT,
    ended_at TEXT,
    location_name TEXT CHECK (location_name IS NULL OR length(location_name) <= 120),
    court_surface TEXT CHECK (
        court_surface IN ('hard', 'clay', 'grass', 'carpet', 'unknown')
        OR court_surface IS NULL
    ),
    training_content TEXT,
    coach_summary TEXT,
    homework TEXT,
    next_focus TEXT,
    created_by_user_id TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at TEXT,
    CHECK (ended_at IS NULL OR started_at IS NULL OR ended_at >= started_at),
    FOREIGN KEY (coach_user_id) REFERENCES users(user_id),
    FOREIGN KEY (created_by_user_id) REFERENCES users(user_id)
);

CREATE TABLE IF NOT EXISTS lesson_students (
    lesson_student_id TEXT PRIMARY KEY,
    lesson_id TEXT NOT NULL,
    student_user_id TEXT NOT NULL,
    attendance_status TEXT NOT NULL DEFAULT 'planned'
        CHECK (attendance_status IN ('planned', 'attended', 'absent', 'canceled')),
    performance_summary TEXT,
    coach_feedback TEXT,
    homework TEXT,
    next_focus TEXT,
    technical_issues TEXT,
    created_by_user_id TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at TEXT,
    FOREIGN KEY (lesson_id) REFERENCES lessons(lesson_id) ON DELETE CASCADE,
    FOREIGN KEY (student_user_id) REFERENCES users(user_id),
    FOREIGN KEY (created_by_user_id) REFERENCES users(user_id)
);

CREATE TABLE IF NOT EXISTS tennis_activities (
    tennis_activity_id TEXT PRIMARY KEY,
    owner_user_id TEXT NOT NULL,
    lesson_id TEXT,
    title TEXT CHECK (title IS NULL OR length(title) <= 120),
    activity_type TEXT NOT NULL DEFAULT 'other'
        CHECK (activity_type IN (
            'casual_hit',
            'match',
            'serve_training',
            'forehand_training',
            'backhand_training',
            'multi_ball_drill',
            'stroke_recording',
            'post_match_review',
            'lesson_practice',
            'coach_demo',
            'other'
        )),
    default_visibility TEXT NOT NULL DEFAULT 'private'
        CHECK (default_visibility IN (
            'private',
            'friends',
            'specified_users',
            'lesson_coach',
            'lesson_participants',
            'public'
        )),
    started_at TEXT,
    ended_at TEXT,
    location_name TEXT CHECK (location_name IS NULL OR length(location_name) <= 120),
    location_source TEXT CHECK (
        location_source IN ('device_gps', 'video_metadata', 'manual_legacy', 'unavailable')
        OR location_source IS NULL
    ),
    location_latitude REAL CHECK (
        location_latitude IS NULL
        OR (location_latitude >= -90 AND location_latitude <= 90)
    ),
    location_longitude REAL CHECK (
        location_longitude IS NULL
        OR (location_longitude >= -180 AND location_longitude <= 180)
    ),
    location_accuracy_m REAL CHECK (location_accuracy_m IS NULL OR location_accuracy_m >= 0),
    location_captured_at TEXT,
    location_country_code TEXT CHECK (location_country_code IS NULL OR length(location_country_code) <= 8),
    location_region TEXT CHECK (location_region IS NULL OR length(location_region) <= 80),
    location_city TEXT CHECK (location_city IS NULL OR length(location_city) <= 80),
    location_district TEXT CHECK (location_district IS NULL OR length(location_district) <= 80),
    location_address_label TEXT CHECK (location_address_label IS NULL OR length(location_address_label) <= 255),
    location_coordinate_system TEXT CHECK (
        location_coordinate_system IN ('wgs84', 'gcj02')
        OR location_coordinate_system IS NULL
    ),
    court_surface TEXT CHECK (
        court_surface IN ('hard', 'clay', 'grass', 'carpet', 'unknown')
        OR court_surface IS NULL
    ),
    opponent_user_id TEXT,
    opponent_name TEXT CHECK (opponent_name IS NULL OR length(opponent_name) <= 50),
    note TEXT,
    analysis_summary_status TEXT CHECK (
        analysis_summary_status IN ('pending', 'processing', 'completed', 'failed')
        OR analysis_summary_status IS NULL
    ),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at TEXT,
    CHECK (ended_at IS NULL OR started_at IS NULL OR ended_at >= started_at),
    CHECK (opponent_user_id IS NULL OR opponent_user_id <> owner_user_id),
    FOREIGN KEY (owner_user_id) REFERENCES users(user_id),
    FOREIGN KEY (lesson_id) REFERENCES lessons(lesson_id),
    FOREIGN KEY (opponent_user_id) REFERENCES users(user_id)
);

CREATE TABLE IF NOT EXISTS videos (
    video_id TEXT PRIMARY KEY,
    tennis_activity_id TEXT,
    owner_user_id TEXT NOT NULL,
    uploader_user_id TEXT NOT NULL,
    filename TEXT NOT NULL CHECK (length(filename) <= 255),
    original_filename TEXT,
    video_path TEXT NOT NULL,
    thumbnail_path TEXT,
    mime_type TEXT CHECK (mime_type IS NULL OR length(mime_type) <= 100),
    file_size_bytes INTEGER CHECK (file_size_bytes IS NULL OR file_size_bytes >= 0),
    file_hash TEXT CHECK (file_hash IS NULL OR length(file_hash) <= 128),
    video_duration_ms INTEGER CHECK (video_duration_ms IS NULL OR video_duration_ms >= 0),
    video_frame_count INTEGER CHECK (video_frame_count IS NULL OR video_frame_count >= 0),
    video_fps REAL CHECK (video_fps IS NULL OR video_fps > 0),
    video_width_px INTEGER CHECK (video_width_px IS NULL OR video_width_px > 0),
    video_height_px INTEGER CHECK (video_height_px IS NULL OR video_height_px > 0),
    camera_view_angle TEXT CHECK (
        camera_view_angle IN ('overhead', 'horizontal')
        OR camera_view_angle IS NULL
    ),
    camera_view_position TEXT CHECK (
        camera_view_position IN ('side', 'rear', 'front', 'rear_side', 'front_side')
        OR camera_view_position IS NULL
    ),
    frame_data_path TEXT,
    frame_data_version TEXT CHECK (frame_data_version IS NULL OR length(frame_data_version) <= 30),
    player_a_user_id TEXT,
    player_b_user_id TEXT,
    player_a_name TEXT CHECK (player_a_name IS NULL OR length(player_a_name) <= 50),
    player_b_name TEXT CHECK (player_b_name IS NULL OR length(player_b_name) <= 50),
    primary_player_slot TEXT CHECK (primary_player_slot IN ('A', 'B') OR primary_player_slot IS NULL),
    visibility TEXT NOT NULL DEFAULT 'inherit'
        CHECK (visibility IN (
            'inherit',
            'private',
            'friends',
            'specified_users',
            'lesson_coach',
            'lesson_participants',
            'public'
        )),
    upload_status TEXT NOT NULL DEFAULT 'pending'
        CHECK (upload_status IN ('pending', 'uploading', 'uploaded', 'failed', 'canceled')),
    upload_error_message TEXT,
    uploaded_at TEXT,
    analysis_status TEXT NOT NULL DEFAULT 'uploaded'
        CHECK (analysis_status IN ('uploaded', 'queued', 'processing', 'completed', 'failed', 'canceled')),
    analysis_version TEXT CHECK (analysis_version IS NULL OR length(analysis_version) <= 50),
    error_message TEXT,
    captured_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at TEXT,
    CHECK (player_a_user_id IS NULL OR player_b_user_id IS NULL OR player_a_user_id <> player_b_user_id),
    FOREIGN KEY (tennis_activity_id) REFERENCES tennis_activities(tennis_activity_id),
    FOREIGN KEY (owner_user_id) REFERENCES users(user_id),
    FOREIGN KEY (uploader_user_id) REFERENCES users(user_id),
    FOREIGN KEY (player_a_user_id) REFERENCES users(user_id),
    FOREIGN KEY (player_b_user_id) REFERENCES users(user_id)
);

CREATE TABLE IF NOT EXISTS video_shares (
    video_share_id TEXT PRIMARY KEY,
    video_id TEXT NOT NULL,
    shared_by_user_id TEXT NOT NULL,
    target_type TEXT NOT NULL
        CHECK (target_type IN ('user', 'lesson_coach', 'lesson_students', 'lesson_participants', 'public_link')),
    target_user_id TEXT,
    target_lesson_id TEXT,
    permission TEXT NOT NULL DEFAULT 'view'
        CHECK (permission IN ('view', 'comment', 'annotate', 'download')),
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'revoked', 'expired')),
    expires_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at TEXT,
    CHECK (
        (target_type = 'user' AND target_user_id IS NOT NULL AND target_lesson_id IS NULL)
        OR (
            target_type IN ('lesson_coach', 'lesson_students', 'lesson_participants')
            AND target_lesson_id IS NOT NULL
            AND target_user_id IS NULL
        )
        OR (target_type = 'public_link' AND target_user_id IS NULL AND target_lesson_id IS NULL)
    ),
    FOREIGN KEY (video_id) REFERENCES videos(video_id) ON DELETE CASCADE,
    FOREIGN KEY (shared_by_user_id) REFERENCES users(user_id),
    FOREIGN KEY (target_user_id) REFERENCES users(user_id),
    FOREIGN KEY (target_lesson_id) REFERENCES lessons(lesson_id)
);

CREATE TABLE IF NOT EXISTS social_posts (
    social_post_id TEXT PRIMARY KEY,
    author_user_id TEXT NOT NULL,
    source_tennis_activity_id TEXT,
    title TEXT CHECK (title IS NULL OR length(title) <= 120),
    content TEXT,
    visibility TEXT NOT NULL DEFAULT 'private'
        CHECK (visibility IN ('private', 'friends', 'followers', 'specified_users', 'public')),
    status TEXT NOT NULL DEFAULT 'draft'
        CHECK (status IN ('draft', 'published', 'hidden', 'deleted')),
    review_status TEXT NOT NULL DEFAULT 'approved'
        CHECK (review_status IN ('pending', 'approved', 'rejected')),
    reviewed_at TEXT,
    reviewer_user_id TEXT,
    review_reason TEXT CHECK (review_reason IS NULL OR length(review_reason) <= 500),
    location_scope TEXT NOT NULL DEFAULT 'none'
        CHECK (location_scope IN ('none', 'region', 'city')),
    location_region TEXT CHECK (location_region IS NULL OR length(location_region) <= 80),
    location_city TEXT CHECK (location_city IS NULL OR length(location_city) <= 80),
    published_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at TEXT,
    CHECK (location_scope <> 'region' OR location_region IS NOT NULL),
    CHECK (location_scope <> 'city' OR location_city IS NOT NULL),
    FOREIGN KEY (author_user_id) REFERENCES users(user_id),
    FOREIGN KEY (source_tennis_activity_id) REFERENCES tennis_activities(tennis_activity_id) ON DELETE SET NULL,
    FOREIGN KEY (reviewer_user_id) REFERENCES users(user_id)
);

CREATE TABLE IF NOT EXISTS social_post_stats (
    social_post_id TEXT PRIMARY KEY,
    like_count INTEGER NOT NULL DEFAULT 0 CHECK (like_count >= 0),
    comment_count INTEGER NOT NULL DEFAULT 0 CHECK (comment_count >= 0),
    favorite_count INTEGER NOT NULL DEFAULT 0 CHECK (favorite_count >= 0),
    share_count INTEGER NOT NULL DEFAULT 0 CHECK (share_count >= 0),
    view_count INTEGER NOT NULL DEFAULT 0 CHECK (view_count >= 0),
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (social_post_id) REFERENCES social_posts(social_post_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS post_reactions (
    reaction_id TEXT PRIMARY KEY,
    social_post_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    reaction_type TEXT NOT NULL DEFAULT 'like'
        CHECK (reaction_type IN ('like')),
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'canceled')),
    source TEXT CHECK (source IS NULL OR length(source) <= 50),
    reacted_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    canceled_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (status = 'active' OR canceled_at IS NOT NULL),
    FOREIGN KEY (social_post_id) REFERENCES social_posts(social_post_id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS post_favorites (
    favorite_id TEXT PRIMARY KEY,
    social_post_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'canceled')),
    source TEXT CHECK (source IS NULL OR length(source) <= 50),
    favorited_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    canceled_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (status = 'active' OR canceled_at IS NOT NULL),
    FOREIGN KEY (social_post_id) REFERENCES social_posts(social_post_id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS post_comments (
    comment_id TEXT PRIMARY KEY,
    social_post_id TEXT NOT NULL,
    author_user_id TEXT NOT NULL,
    parent_comment_id TEXT,
    root_comment_id TEXT,
    content TEXT CHECK (content IS NULL OR length(content) <= 2000),
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'deleted', 'hidden')),
    source TEXT CHECK (source IS NULL OR length(source) <= 50),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at TEXT,
    CHECK (parent_comment_id IS NULL OR parent_comment_id <> comment_id),
    CHECK (root_comment_id IS NULL OR root_comment_id <> comment_id),
    CHECK (status <> 'active' OR content IS NOT NULL),
    CHECK (status = 'active' OR deleted_at IS NOT NULL),
    FOREIGN KEY (social_post_id) REFERENCES social_posts(social_post_id) ON DELETE CASCADE,
    FOREIGN KEY (author_user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    FOREIGN KEY (parent_comment_id) REFERENCES post_comments(comment_id),
    FOREIGN KEY (root_comment_id) REFERENCES post_comments(comment_id)
);

CREATE TABLE IF NOT EXISTS post_media (
    post_media_id TEXT PRIMARY KEY,
    social_post_id TEXT NOT NULL,
    media_type TEXT NOT NULL
        CHECK (media_type IN ('video', 'video_clip', 'image', 'data_card')),
    video_id TEXT,
    image_path TEXT,
    data_card_type TEXT CHECK (data_card_type IS NULL OR length(data_card_type) <= 50),
    data_payload_json TEXT,
    clip_start_ms INTEGER CHECK (clip_start_ms IS NULL OR clip_start_ms >= 0),
    clip_end_ms INTEGER CHECK (clip_end_ms IS NULL OR clip_end_ms >= 0),
    sort_order INTEGER NOT NULL DEFAULT 0 CHECK (sort_order >= 0),
    caption TEXT CHECK (caption IS NULL OR length(caption) <= 255),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at TEXT,
    CHECK (
        (
            media_type = 'video'
            AND video_id IS NOT NULL
            AND image_path IS NULL
            AND data_card_type IS NULL
            AND data_payload_json IS NULL
            AND clip_start_ms IS NULL
            AND clip_end_ms IS NULL
        )
        OR (
            media_type = 'video_clip'
            AND video_id IS NOT NULL
            AND clip_start_ms IS NOT NULL
            AND clip_end_ms IS NOT NULL
            AND clip_end_ms > clip_start_ms
            AND image_path IS NULL
            AND data_card_type IS NULL
            AND data_payload_json IS NULL
        )
        OR (
            media_type = 'image'
            AND image_path IS NOT NULL
            AND video_id IS NULL
            AND data_card_type IS NULL
            AND data_payload_json IS NULL
            AND clip_start_ms IS NULL
            AND clip_end_ms IS NULL
        )
        OR (
            media_type = 'data_card'
            AND data_card_type IS NOT NULL
            AND data_payload_json IS NOT NULL
            AND video_id IS NULL
            AND image_path IS NULL
            AND clip_start_ms IS NULL
            AND clip_end_ms IS NULL
        )
    ),
    FOREIGN KEY (social_post_id) REFERENCES social_posts(social_post_id) ON DELETE CASCADE,
    FOREIGN KEY (video_id) REFERENCES videos(video_id)
);

CREATE TABLE IF NOT EXISTS user_follows (
    follow_id TEXT PRIMARY KEY,
    follower_user_id TEXT NOT NULL,
    following_user_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'canceled')),
    source TEXT CHECK (source IS NULL OR length(source) <= 50),
    followed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    canceled_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (follower_user_id <> following_user_id),
    CHECK (status = 'active' OR canceled_at IS NOT NULL),
    FOREIGN KEY (follower_user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    FOREIGN KEY (following_user_id) REFERENCES users(user_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS user_social_stats (
    user_id TEXT PRIMARY KEY,
    follower_count INTEGER NOT NULL DEFAULT 0 CHECK (follower_count >= 0),
    following_count INTEGER NOT NULL DEFAULT 0 CHECK (following_count >= 0),
    friend_count INTEGER NOT NULL DEFAULT 0 CHECK (friend_count >= 0),
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS user_blocks (
    user_block_id TEXT PRIMARY KEY,
    blocker_user_id TEXT NOT NULL,
    blocked_user_id TEXT NOT NULL,
    reason TEXT CHECK (reason IS NULL OR length(reason) <= 255),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at TEXT,
    CHECK (blocker_user_id <> blocked_user_id),
    FOREIGN KEY (blocker_user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    FOREIGN KEY (blocked_user_id) REFERENCES users(user_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS user_privacy_settings (
    user_id TEXT PRIMARY KEY,
    direct_message_policy TEXT NOT NULL DEFAULT 'friends'
        CHECK (direct_message_policy IN ('everyone', 'following', 'friends')),
    allow_message_requests INTEGER NOT NULL DEFAULT 1 CHECK (allow_message_requests IN (0, 1)),
    default_post_visibility TEXT NOT NULL DEFAULT 'public'
        CHECK (default_post_visibility IN ('private', 'friends', 'followers', 'public')),
    show_profile_to_strangers INTEGER NOT NULL DEFAULT 1 CHECK (show_profile_to_strangers IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS user_notification_preferences (
    user_id TEXT PRIMARY KEY,
    direct_message_notifications INTEGER NOT NULL DEFAULT 1
        CHECK (direct_message_notifications IN (0, 1)),
    message_request_notifications INTEGER NOT NULL DEFAULT 1
        CHECK (message_request_notifications IN (0, 1)),
    like_comment_notifications INTEGER NOT NULL DEFAULT 1
        CHECK (like_comment_notifications IN (0, 1)),
    follow_notifications INTEGER NOT NULL DEFAULT 1
        CHECK (follow_notifications IN (0, 1)),
    course_notifications INTEGER NOT NULL DEFAULT 1
        CHECK (course_notifications IN (0, 1)),
    ai_analysis_notifications INTEGER NOT NULL DEFAULT 1
        CHECK (ai_analysis_notifications IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS user_post_views (
    user_post_view_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    social_post_id TEXT NOT NULL,
    first_viewed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_viewed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    first_view_source TEXT CHECK (first_view_source IS NULL OR length(first_view_source) <= 50),
    last_view_source TEXT CHECK (last_view_source IS NULL OR length(last_view_source) <= 50),
    view_count INTEGER NOT NULL DEFAULT 1 CHECK (view_count >= 1),
    total_dwell_time_ms INTEGER NOT NULL DEFAULT 0 CHECK (total_dwell_time_ms >= 0),
    last_dwell_time_ms INTEGER NOT NULL DEFAULT 0 CHECK (last_dwell_time_ms >= 0),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (user_id, social_post_id),
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    FOREIGN KEY (social_post_id) REFERENCES social_posts(social_post_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS user_post_hides (
    user_post_hide_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    social_post_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'canceled')),
    source TEXT CHECK (source IS NULL OR length(source) <= 50),
    reason TEXT CHECK (reason IS NULL OR length(reason) <= 255),
    hidden_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    canceled_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (status = 'active' OR canceled_at IS NOT NULL),
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    FOREIGN KEY (social_post_id) REFERENCES social_posts(social_post_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS chat_conversations (
    conversation_id TEXT PRIMARY KEY,
    conversation_type TEXT NOT NULL
        CHECK (conversation_type IN ('direct', 'group')),
    group_type TEXT CHECK (
        group_type IN ('friend_group', 'lesson_group', 'training_group', 'coach_course_group', 'custom')
        OR group_type IS NULL
    ),
    direct_pair_key TEXT CHECK (direct_pair_key IS NULL OR length(direct_pair_key) <= 100),
    title TEXT CHECK (title IS NULL OR length(title) <= 120),
    avatar_path TEXT,
    created_by_user_id TEXT,
    context_type TEXT CHECK (
        context_type IN ('lesson', 'tennis_activity', 'video', 'social_post', 'custom')
        OR context_type IS NULL
    ),
    context_id TEXT,
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'archived', 'deleted')),
    last_message_id TEXT,
    last_message_seq INTEGER NOT NULL DEFAULT 0 CHECK (last_message_seq >= 0),
    last_message_preview TEXT CHECK (last_message_preview IS NULL OR length(last_message_preview) <= 255),
    last_message_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at TEXT,
    CHECK (
        (conversation_type = 'direct' AND direct_pair_key IS NOT NULL AND group_type IS NULL)
        OR (conversation_type = 'group' AND direct_pair_key IS NULL)
    ),
    CHECK ((context_type IS NULL AND context_id IS NULL) OR (context_type IS NOT NULL AND context_id IS NOT NULL)),
    FOREIGN KEY (created_by_user_id) REFERENCES users(user_id)
);

CREATE TABLE IF NOT EXISTS chat_conversation_members (
    conversation_member_id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    member_role TEXT NOT NULL DEFAULT 'member'
        CHECK (member_role IN ('owner', 'admin', 'member', 'coach', 'student')),
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'left', 'removed')),
    joined_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    left_at TEXT,
    last_read_message_id TEXT,
    last_read_message_seq INTEGER NOT NULL DEFAULT 0 CHECK (last_read_message_seq >= 0),
    last_read_at TEXT,
    unread_count INTEGER NOT NULL DEFAULT 0 CHECK (unread_count >= 0),
    muted_until TEXT,
    pinned_at TEXT,
    archived_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at TEXT,
    CHECK (status = 'active' OR left_at IS NOT NULL),
    FOREIGN KEY (conversation_id) REFERENCES chat_conversations(conversation_id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    FOREIGN KEY (last_read_message_id) REFERENCES chat_messages(message_id)
);

CREATE TABLE IF NOT EXISTS chat_message_requests (
    message_request_id TEXT PRIMARY KEY,
    requester_user_id TEXT NOT NULL,
    recipient_user_id TEXT NOT NULL,
    conversation_id TEXT,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'accepted', 'declined', 'blocked', 'canceled')),
    request_message TEXT CHECK (request_message IS NULL OR length(request_message) <= 500),
    source TEXT CHECK (source IS NULL OR length(source) <= 50),
    requested_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    responded_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (requester_user_id <> recipient_user_id),
    CHECK (status = 'pending' OR responded_at IS NOT NULL OR status = 'canceled'),
    FOREIGN KEY (requester_user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    FOREIGN KEY (recipient_user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    FOREIGN KEY (conversation_id) REFERENCES chat_conversations(conversation_id)
);

CREATE TABLE IF NOT EXISTS chat_messages (
    message_id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL,
    message_seq INTEGER NOT NULL CHECK (message_seq >= 1),
    sender_user_id TEXT,
    sender_type TEXT NOT NULL DEFAULT 'user'
        CHECK (sender_type IN ('user', 'system', 'ai', 'admin')),
    message_type TEXT NOT NULL DEFAULT 'text'
        CHECK (message_type IN (
            'text',
            'image',
            'video',
            'audio',
            'file',
            'post_share',
            'video_share',
            'activity_share',
            'lesson_share',
            'analysis_card',
            'system_event',
            'custom'
        )),
    text_content TEXT CHECK (text_content IS NULL OR length(text_content) <= 5000),
    payload_json TEXT,
    target_object_type TEXT CHECK (
        target_object_type IN ('user', 'video', 'social_post', 'tennis_activity', 'lesson', 'analysis', 'custom')
        OR target_object_type IS NULL
    ),
    target_object_id TEXT,
    context_object_type TEXT CHECK (
        context_object_type IN ('video', 'social_post', 'tennis_activity', 'lesson', 'custom')
        OR context_object_type IS NULL
    ),
    context_object_id TEXT,
    reply_to_message_id TEXT,
    client_message_id TEXT CHECK (client_message_id IS NULL OR length(client_message_id) <= 120),
    status TEXT NOT NULL DEFAULT 'sent'
        CHECK (status IN ('sent', 'revoked', 'deleted')),
    sent_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at TEXT,
    CHECK (sender_type <> 'user' OR sender_user_id IS NOT NULL),
    CHECK (message_type <> 'text' OR text_content IS NOT NULL),
    CHECK ((target_object_type IS NULL AND target_object_id IS NULL) OR (target_object_type IS NOT NULL AND target_object_id IS NOT NULL)),
    CHECK ((context_object_type IS NULL AND context_object_id IS NULL) OR (context_object_type IS NOT NULL AND context_object_id IS NOT NULL)),
    FOREIGN KEY (conversation_id) REFERENCES chat_conversations(conversation_id) ON DELETE CASCADE,
    FOREIGN KEY (sender_user_id) REFERENCES users(user_id),
    FOREIGN KEY (reply_to_message_id) REFERENCES chat_messages(message_id)
);

CREATE TABLE IF NOT EXISTS post_shares (
    post_share_id TEXT PRIMARY KEY,
    social_post_id TEXT NOT NULL,
    shared_by_user_id TEXT NOT NULL,
    share_target_type TEXT NOT NULL
        CHECK (share_target_type IN ('conversation', 'user', 'external', 'copy_link')),
    target_user_id TEXT,
    conversation_id TEXT,
    message_id TEXT,
    channel TEXT CHECK (channel IS NULL OR length(channel) <= 50),
    payload_json TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (
        (
            share_target_type = 'conversation'
            AND conversation_id IS NOT NULL
            AND target_user_id IS NULL
        )
        OR (
            share_target_type = 'user'
            AND target_user_id IS NOT NULL
            AND conversation_id IS NULL
        )
        OR (
            share_target_type IN ('external', 'copy_link')
            AND target_user_id IS NULL
            AND conversation_id IS NULL
        )
    ),
    FOREIGN KEY (social_post_id) REFERENCES social_posts(social_post_id) ON DELETE CASCADE,
    FOREIGN KEY (shared_by_user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    FOREIGN KEY (target_user_id) REFERENCES users(user_id),
    FOREIGN KEY (conversation_id) REFERENCES chat_conversations(conversation_id),
    FOREIGN KEY (message_id) REFERENCES chat_messages(message_id)
);

CREATE TABLE IF NOT EXISTS chat_message_attachments (
    attachment_id TEXT PRIMARY KEY,
    message_id TEXT NOT NULL,
    attachment_type TEXT NOT NULL
        CHECK (attachment_type IN ('image', 'video', 'audio', 'file', 'object_card', 'data_card', 'link')),
    media_path TEXT,
    thumbnail_path TEXT,
    mime_type TEXT CHECK (mime_type IS NULL OR length(mime_type) <= 100),
    file_size_bytes INTEGER CHECK (file_size_bytes IS NULL OR file_size_bytes >= 0),
    duration_ms INTEGER CHECK (duration_ms IS NULL OR duration_ms >= 0),
    width_px INTEGER CHECK (width_px IS NULL OR width_px > 0),
    height_px INTEGER CHECK (height_px IS NULL OR height_px > 0),
    object_type TEXT CHECK (
        object_type IN ('user', 'video', 'social_post', 'tennis_activity', 'lesson', 'analysis', 'custom')
        OR object_type IS NULL
    ),
    object_id TEXT,
    payload_json TEXT,
    sort_order INTEGER NOT NULL DEFAULT 0 CHECK (sort_order >= 0),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK ((object_type IS NULL AND object_id IS NULL) OR (object_type IS NOT NULL AND object_id IS NOT NULL)),
    FOREIGN KEY (message_id) REFERENCES chat_messages(message_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS notification_events (
    notification_event_id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL
        CHECK (event_type IN (
            'follow',
            'post_like',
            'post_comment',
            'comment_reply',
            'mention',
            'video_shared',
            'ai_analysis_completed',
            'lesson_created',
            'lesson_updated',
            'coach_application_reviewed',
            'system_announcement',
            'custom'
        )),
    category TEXT NOT NULL DEFAULT 'system'
        CHECK (category IN ('interaction', 'system', 'ai', 'coach', 'lesson')),
    actor_user_id TEXT,
    object_type TEXT CHECK (
        object_type IN ('user', 'video', 'social_post', 'comment', 'tennis_activity', 'lesson', 'coach_application', 'analysis', 'custom')
        OR object_type IS NULL
    ),
    object_id TEXT,
    context_type TEXT CHECK (
        context_type IN ('video', 'social_post', 'tennis_activity', 'lesson', 'custom')
        OR context_type IS NULL
    ),
    context_id TEXT,
    title TEXT CHECK (title IS NULL OR length(title) <= 120),
    body TEXT CHECK (body IS NULL OR length(body) <= 500),
    deep_link TEXT CHECK (deep_link IS NULL OR length(deep_link) <= 255),
    payload_json TEXT,
    dedup_key TEXT CHECK (dedup_key IS NULL OR length(dedup_key) <= 160),
    aggregation_key TEXT CHECK (aggregation_key IS NULL OR length(aggregation_key) <= 160),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK ((object_type IS NULL AND object_id IS NULL) OR (object_type IS NOT NULL AND object_id IS NOT NULL)),
    CHECK ((context_type IS NULL AND context_id IS NULL) OR (context_type IS NOT NULL AND context_id IS NOT NULL)),
    FOREIGN KEY (actor_user_id) REFERENCES users(user_id)
);

CREATE TABLE IF NOT EXISTS user_notifications (
    user_notification_id TEXT PRIMARY KEY,
    notification_event_id TEXT NOT NULL,
    recipient_user_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'visible'
        CHECK (status IN ('visible', 'deleted')),
    priority TEXT NOT NULL DEFAULT 'normal'
        CHECK (priority IN ('normal', 'high')),
    delivered_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    seen_at TEXT,
    read_at TEXT,
    dismissed_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at TEXT,
    FOREIGN KEY (notification_event_id) REFERENCES notification_events(notification_event_id) ON DELETE CASCADE,
    FOREIGN KEY (recipient_user_id) REFERENCES users(user_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS user_inbox_counters (
    user_id TEXT PRIMARY KEY,
    unread_direct_message_count INTEGER NOT NULL DEFAULT 0 CHECK (unread_direct_message_count >= 0),
    unread_group_message_count INTEGER NOT NULL DEFAULT 0 CHECK (unread_group_message_count >= 0),
    unread_notification_count INTEGER NOT NULL DEFAULT 0 CHECK (unread_notification_count >= 0),
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS content_reports (
    content_report_id TEXT PRIMARY KEY,
    reporter_user_id TEXT NOT NULL,
    target_type TEXT NOT NULL
        CHECK (target_type IN ('user', 'social_post', 'post_comment', 'chat_message', 'chat_conversation', 'video')),
    target_id TEXT NOT NULL,
    reason_type TEXT NOT NULL
        CHECK (reason_type IN ('spam', 'harassment', 'inappropriate', 'fraud', 'privacy', 'other')),
    reason_text TEXT CHECK (reason_text IS NULL OR length(reason_text) <= 1000),
    source TEXT CHECK (source IS NULL OR length(source) <= 50),
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'reviewing', 'resolved', 'rejected')),
    reviewer_user_id TEXT,
    reviewed_at TEXT,
    resolution_note TEXT CHECK (resolution_note IS NULL OR length(resolution_note) <= 1000),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (reporter_user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    FOREIGN KEY (reviewer_user_id) REFERENCES users(user_id)
);

CREATE TABLE IF NOT EXISTS points (
    point_id TEXT PRIMARY KEY,
    video_id TEXT NOT NULL,
    point_index INTEGER NOT NULL CHECK (point_index >= 1),
    start_frame INTEGER NOT NULL CHECK (start_frame >= 0),
    end_frame INTEGER CHECK (end_frame IS NULL OR end_frame >= start_frame),
    start_time_ms INTEGER NOT NULL CHECK (start_time_ms >= 0),
    end_time_ms INTEGER CHECK (end_time_ms IS NULL OR end_time_ms >= start_time_ms),
    server_slot TEXT CHECK (server_slot IN ('A', 'B') OR server_slot IS NULL),
    winner_slot TEXT CHECK (winner_slot IN ('A', 'B') OR winner_slot IS NULL),
    terminal_shot_id TEXT,
    set_index INTEGER CHECK (set_index IS NULL OR set_index >= 1),
    game_index_in_set INTEGER CHECK (game_index_in_set IS NULL OR game_index_in_set >= 1),
    a_sets_before INTEGER CHECK (a_sets_before IS NULL OR a_sets_before >= 0),
    b_sets_before INTEGER CHECK (b_sets_before IS NULL OR b_sets_before >= 0),
    a_games_before INTEGER CHECK (a_games_before IS NULL OR a_games_before >= 0),
    b_games_before INTEGER CHECK (b_games_before IS NULL OR b_games_before >= 0),
    a_points_before INTEGER CHECK (a_points_before IS NULL OR a_points_before >= 0),
    b_points_before INTEGER CHECK (b_points_before IS NULL OR b_points_before >= 0),
    is_tiebreak INTEGER CHECK (is_tiebreak IN (0, 1) OR is_tiebreak IS NULL),
    first_serve_in INTEGER CHECK (first_serve_in IN (0, 1) OR first_serve_in IS NULL),
    second_serve_used INTEGER CHECK (second_serve_used IN (0, 1) OR second_serve_used IS NULL),
    second_serve_in INTEGER CHECK (second_serve_in IN (0, 1) OR second_serve_in IS NULL),
    serve_let_count INTEGER NOT NULL DEFAULT 0 CHECK (serve_let_count >= 0),
    is_double_fault INTEGER CHECK (is_double_fault IN (0, 1) OR is_double_fault IS NULL),
    total_shot_count INTEGER CHECK (total_shot_count IS NULL OR total_shot_count >= 0),
    in_play_shot_count INTEGER CHECK (in_play_shot_count IS NULL OR in_play_shot_count >= 0),
    point_result TEXT CHECK (
        point_result IN (
            'ace',
            'service_winner',
            'winner',
            'forced_error',
            'unforced_error',
            'double_fault',
            'unknown'
        )
        OR point_result IS NULL
    ),
    ending_reason TEXT CHECK (ending_reason IN ('net', 'out', 'unreturned', 'unknown') OR ending_reason IS NULL),
    confidence REAL CHECK (confidence IS NULL OR confidence BETWEEN 0 AND 1),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (total_shot_count IS NULL OR in_play_shot_count IS NULL OR total_shot_count >= in_play_shot_count),
    CHECK (
        first_serve_in IS NULL
        OR first_serve_in = 0
        OR (
            ifnull(second_serve_used, -1) = 0
            AND second_serve_in IS NULL
            AND ifnull(is_double_fault, -1) = 0
        )
    ),
    CHECK (
        second_serve_used IS NULL
        OR second_serve_used = 1
        OR (
            second_serve_in IS NULL
            AND ifnull(is_double_fault, -1) = 0
        )
    ),
    CHECK (second_serve_in IS NULL OR ifnull(second_serve_used, -1) = 1),
    CHECK (
        ifnull(is_double_fault, 0) = 0
        OR (
            ifnull(first_serve_in, -1) = 0
            AND ifnull(second_serve_used, -1) = 1
            AND ifnull(second_serve_in, -1) = 0
            AND point_result = 'double_fault'
        )
    ),
    FOREIGN KEY (video_id) REFERENCES videos(video_id) ON DELETE CASCADE,
    FOREIGN KEY (terminal_shot_id) REFERENCES shots(shot_id) DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE IF NOT EXISTS shots (
    shot_id TEXT PRIMARY KEY,
    point_id TEXT NOT NULL,
    shot_index INTEGER NOT NULL CHECK (shot_index >= 1),
    hitter_slot TEXT CHECK (hitter_slot IN ('A', 'B') OR hitter_slot IS NULL),
    shot_role TEXT CHECK (shot_role IN ('serve', 'return', 'rally') OR shot_role IS NULL),
    serve_number INTEGER CHECK (serve_number IN (1, 2) OR serve_number IS NULL),
    contact_frame INTEGER NOT NULL CHECK (contact_frame >= 0),
    contact_time_ms INTEGER NOT NULL CHECK (contact_time_ms >= 0),
    contact_projected_x_m REAL,
    contact_projected_y_m REAL,
    hitter_x_m REAL,
    hitter_y_m REAL,
    opponent_x_m REAL,
    opponent_y_m REAL,
    bounce_count_before_hit INTEGER CHECK (
        bounce_count_before_hit IS NULL
        OR (bounce_count_before_hit >= 0 AND bounce_count_before_hit <= 1)
    ),
    contact_confidence REAL CHECK (contact_confidence IS NULL OR contact_confidence BETWEEN 0 AND 1),
    stroke_type TEXT CHECK (
        stroke_type IN ('serve', 'groundstroke', 'volley', 'overhead', 'unknown')
        OR stroke_type IS NULL
    ),
    stroke_side TEXT CHECK (stroke_side IN ('forehand', 'backhand', 'unknown') OR stroke_side IS NULL),
    stroke_confidence REAL CHECK (stroke_confidence IS NULL OR stroke_confidence BETWEEN 0 AND 1),
    incoming_speed_mps REAL CHECK (incoming_speed_mps IS NULL OR incoming_speed_mps >= 0),
    outgoing_speed_mps REAL CHECK (outgoing_speed_mps IS NULL OR outgoing_speed_mps >= 0),
    outgoing_angle_deg REAL CHECK (
        outgoing_angle_deg IS NULL
        OR (outgoing_angle_deg > -180 AND outgoing_angle_deg <= 180)
    ),
    first_bounce_frame INTEGER CHECK (first_bounce_frame IS NULL OR first_bounce_frame >= contact_frame),
    first_bounce_time_ms INTEGER CHECK (first_bounce_time_ms IS NULL OR first_bounce_time_ms >= contact_time_ms),
    first_bounce_x_m REAL,
    first_bounce_y_m REAL,
    bounce_result TEXT CHECK (bounce_result IN ('in', 'out', 'unknown') OR bounce_result IS NULL),
    bounce_confidence REAL CHECK (bounce_confidence IS NULL OR bounce_confidence BETWEEN 0 AND 1),
    trajectory_end_type TEXT CHECK (
        trajectory_end_type IN (
            'opponent_hit',
            'second_bounce',
            'net',
            'out',
            'lost',
            'video_end',
            'unknown'
        )
        OR trajectory_end_type IS NULL
    ),
    shot_result TEXT CHECK (
        shot_result IN ('continue', 'winner', 'error', 'serve_fault', 'let', 'unknown')
        OR shot_result IS NULL
    ),
    error_forcedness TEXT CHECK (
        error_forcedness IN ('forced', 'unforced', 'unknown')
        OR error_forcedness IS NULL
    ),
    error_type TEXT CHECK (error_type IN ('net', 'long', 'wide', 'unknown') OR error_type IS NULL),
    is_point_ending INTEGER CHECK (is_point_ending IN (0, 1) OR is_point_ending IS NULL),
    point_winner_slot TEXT CHECK (point_winner_slot IN ('A', 'B') OR point_winner_slot IS NULL),
    result_confidence REAL CHECK (result_confidence IS NULL OR result_confidence BETWEEN 0 AND 1),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (serve_number IS NULL OR ifnull(shot_role, '') = 'serve'),
    CHECK (
        shot_role IS NULL
        OR shot_role <> 'serve'
        OR (ifnull(serve_number, -1) IN (1, 2) AND ifnull(stroke_type, '') = 'serve')
    ),
    CHECK (
        stroke_type IS NULL
        OR stroke_type <> 'serve'
        OR (ifnull(shot_role, '') = 'serve' AND stroke_side IS NULL)
    ),
    CHECK (ifnull(is_point_ending, 0) = 1 OR point_winner_slot IS NULL),
    CHECK (ifnull(is_point_ending, 0) = 0 OR ifnull(point_winner_slot, '') IN ('A', 'B')),
    CHECK (
        shot_result IS NULL
        OR shot_result <> 'serve_fault'
        OR (ifnull(shot_role, '') = 'serve' AND ifnull(serve_number, -1) IN (1, 2))
    ),
    CHECK (
        shot_result IS NULL
        OR shot_result <> 'let'
        OR (ifnull(shot_role, '') = 'serve' AND ifnull(is_point_ending, -1) = 0)
    ),
    FOREIGN KEY (point_id) REFERENCES points(point_id) ON DELETE CASCADE
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email_active
    ON users(lower(email))
    WHERE email IS NOT NULL AND deleted_at IS NULL;

CREATE UNIQUE INDEX IF NOT EXISTS idx_users_phone_active
    ON users(phone)
    WHERE phone IS NOT NULL AND deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_users_status
    ON users(status);

CREATE INDEX IF NOT EXISTS idx_users_is_coach
    ON users(is_coach, coach_status);

CREATE INDEX IF NOT EXISTS idx_users_created_at
    ON users(created_at DESC);

CREATE INDEX IF NOT EXISTS idx_admin_users_status_role
    ON admin_users(status, role);

CREATE INDEX IF NOT EXISTS idx_admin_users_created_by
    ON admin_users(created_by_user_id, created_at DESC);

CREATE UNIQUE INDEX IF NOT EXISTS idx_admin_credentials_username
    ON admin_credentials(username_normalized);

CREATE INDEX IF NOT EXISTS idx_admin_credentials_user_status
    ON admin_credentials(user_id, status);

CREATE UNIQUE INDEX IF NOT EXISTS idx_auth_identities_provider_subject_active
    ON auth_identities(provider, provider_subject_normalized)
    WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_auth_identities_user_provider
    ON auth_identities(user_id, provider);

CREATE INDEX IF NOT EXISTS idx_auth_identities_provider_created
    ON auth_identities(provider, created_at DESC);

CREATE UNIQUE INDEX IF NOT EXISTS idx_auth_sessions_access_token_hash
    ON auth_sessions(access_token_hash);

CREATE UNIQUE INDEX IF NOT EXISTS idx_auth_sessions_refresh_token_hash
    ON auth_sessions(refresh_token_hash);

CREATE INDEX IF NOT EXISTS idx_auth_sessions_user_active
    ON auth_sessions(user_id, expires_at DESC)
    WHERE revoked_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_auth_sessions_expires
    ON auth_sessions(expires_at);

CREATE INDEX IF NOT EXISTS idx_auth_verification_codes_recipient_created
    ON auth_verification_codes(provider, recipient_normalized, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_auth_verification_codes_expires
    ON auth_verification_codes(expires_at);

CREATE UNIQUE INDEX IF NOT EXISTS idx_coach_applications_user_pending
    ON coach_applications(applicant_user_id)
    WHERE status = 'pending';

CREATE INDEX IF NOT EXISTS idx_coach_applications_status_created
    ON coach_applications(status, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_coach_applications_type_status
    ON coach_applications(application_type, status);

CREATE INDEX IF NOT EXISTS idx_coach_profiles_status_type
    ON coach_profiles(status, coach_type);

CREATE INDEX IF NOT EXISTS idx_coach_profiles_user_status
    ON coach_profiles(user_id, status);

CREATE INDEX IF NOT EXISTS idx_lessons_coach_started
    ON lessons(coach_user_id, started_at DESC);

CREATE INDEX IF NOT EXISTS idx_lessons_status_started
    ON lessons(status, started_at DESC);

CREATE INDEX IF NOT EXISTS idx_lessons_created_by
    ON lessons(created_by_user_id, created_at DESC);

CREATE UNIQUE INDEX IF NOT EXISTS idx_lesson_students_lesson_student_active
    ON lesson_students(lesson_id, student_user_id)
    WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_lesson_students_lesson
    ON lesson_students(lesson_id);

CREATE INDEX IF NOT EXISTS idx_lesson_students_student
    ON lesson_students(student_user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_lesson_students_attendance
    ON lesson_students(attendance_status);

CREATE INDEX IF NOT EXISTS idx_activities_owner_created
    ON tennis_activities(owner_user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_activities_lesson_created
    ON tennis_activities(lesson_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_activities_type_started
    ON tennis_activities(activity_type, started_at DESC);

CREATE INDEX IF NOT EXISTS idx_activities_location_city_started
    ON tennis_activities(location_city, location_district, started_at DESC, tennis_activity_id DESC)
    WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_activities_visibility
    ON tennis_activities(default_visibility);

CREATE UNIQUE INDEX IF NOT EXISTS idx_videos_filename
    ON videos(filename);

CREATE UNIQUE INDEX IF NOT EXISTS idx_videos_video_path
    ON videos(video_path);

CREATE INDEX IF NOT EXISTS idx_videos_activity_created
    ON videos(tennis_activity_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_videos_owner_created
    ON videos(owner_user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_videos_uploader_created
    ON videos(uploader_user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_videos_analysis_status
    ON videos(analysis_status, created_at);

CREATE INDEX IF NOT EXISTS idx_videos_upload_status
    ON videos(upload_status, created_at);

CREATE INDEX IF NOT EXISTS idx_videos_visibility
    ON videos(visibility);

CREATE INDEX IF NOT EXISTS idx_videos_captured_at
    ON videos(captured_at DESC);

CREATE INDEX IF NOT EXISTS idx_videos_file_hash
    ON videos(file_hash)
    WHERE file_hash IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_videos_camera_view
    ON videos(camera_view_angle, camera_view_position);

CREATE INDEX IF NOT EXISTS idx_videos_player_a_created
    ON videos(player_a_user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_videos_player_b_created
    ON videos(player_b_user_id, created_at DESC);

CREATE UNIQUE INDEX IF NOT EXISTS idx_video_shares_user_active
    ON video_shares(video_id, target_user_id, permission)
    WHERE target_type = 'user'
      AND status = 'active'
      AND deleted_at IS NULL;

CREATE UNIQUE INDEX IF NOT EXISTS idx_video_shares_lesson_active
    ON video_shares(video_id, target_lesson_id, target_type, permission)
    WHERE target_type IN ('lesson_coach', 'lesson_students', 'lesson_participants')
      AND status = 'active'
      AND deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_video_shares_video
    ON video_shares(video_id, status);

CREATE INDEX IF NOT EXISTS idx_video_shares_target_user
    ON video_shares(target_user_id, status);

CREATE INDEX IF NOT EXISTS idx_video_shares_target_lesson
    ON video_shares(target_lesson_id, status);

CREATE INDEX IF NOT EXISTS idx_video_shares_expires
    ON video_shares(expires_at);

CREATE INDEX IF NOT EXISTS idx_social_posts_author_created
    ON social_posts(author_user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_social_posts_source_activity
    ON social_posts(source_tennis_activity_id);

CREATE INDEX IF NOT EXISTS idx_social_posts_status_published
    ON social_posts(status, published_at DESC);

CREATE INDEX IF NOT EXISTS idx_social_posts_visibility
    ON social_posts(visibility);

CREATE INDEX IF NOT EXISTS idx_social_posts_feed_published
    ON social_posts(review_status, status, published_at DESC, social_post_id DESC)
    WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_social_posts_location_published
    ON social_posts(location_city, location_region, published_at DESC, social_post_id DESC)
    WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_social_post_stats_updated
    ON social_post_stats(updated_at DESC);

CREATE UNIQUE INDEX IF NOT EXISTS idx_post_media_post_sort_active
    ON post_media(social_post_id, sort_order)
    WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_post_media_post_sort
    ON post_media(social_post_id, sort_order);

CREATE INDEX IF NOT EXISTS idx_post_media_video
    ON post_media(video_id);

CREATE INDEX IF NOT EXISTS idx_post_media_type
    ON post_media(media_type);

CREATE UNIQUE INDEX IF NOT EXISTS idx_user_follows_active_pair
    ON user_follows(follower_user_id, following_user_id)
    WHERE status = 'active';

CREATE INDEX IF NOT EXISTS idx_user_follows_follower_created
    ON user_follows(follower_user_id, followed_at DESC);

CREATE INDEX IF NOT EXISTS idx_user_follows_following_created
    ON user_follows(following_user_id, followed_at DESC);

CREATE INDEX IF NOT EXISTS idx_user_follows_mutual_lookup
    ON user_follows(following_user_id, follower_user_id, status);

CREATE UNIQUE INDEX IF NOT EXISTS idx_user_blocks_active_pair
    ON user_blocks(blocker_user_id, blocked_user_id)
    WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_user_blocks_blocked
    ON user_blocks(blocked_user_id, blocker_user_id)
    WHERE deleted_at IS NULL;

CREATE UNIQUE INDEX IF NOT EXISTS idx_post_reactions_active_user_post_type
    ON post_reactions(user_id, social_post_id, reaction_type)
    WHERE status = 'active';

CREATE INDEX IF NOT EXISTS idx_post_reactions_post_active
    ON post_reactions(social_post_id, reaction_type, status, reacted_at DESC);

CREATE INDEX IF NOT EXISTS idx_post_reactions_user_created
    ON post_reactions(user_id, reacted_at DESC);

CREATE UNIQUE INDEX IF NOT EXISTS idx_post_favorites_active_user_post
    ON post_favorites(user_id, social_post_id)
    WHERE status = 'active';

CREATE INDEX IF NOT EXISTS idx_post_favorites_post_active
    ON post_favorites(social_post_id, status, favorited_at DESC);

CREATE INDEX IF NOT EXISTS idx_post_favorites_user_created
    ON post_favorites(user_id, favorited_at DESC);

CREATE INDEX IF NOT EXISTS idx_post_comments_post_status_created
    ON post_comments(social_post_id, status, created_at ASC, comment_id ASC);

CREATE INDEX IF NOT EXISTS idx_post_comments_parent_created
    ON post_comments(parent_comment_id, created_at ASC, comment_id ASC);

CREATE INDEX IF NOT EXISTS idx_post_comments_root_created
    ON post_comments(root_comment_id, created_at ASC, comment_id ASC);

CREATE INDEX IF NOT EXISTS idx_post_comments_author_created
    ON post_comments(author_user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_user_post_views_user_last_viewed
    ON user_post_views(user_id, last_viewed_at DESC, social_post_id DESC);

CREATE INDEX IF NOT EXISTS idx_user_post_views_post
    ON user_post_views(social_post_id, last_viewed_at DESC);

CREATE UNIQUE INDEX IF NOT EXISTS idx_user_post_hides_active_pair
    ON user_post_hides(user_id, social_post_id)
    WHERE status = 'active';

CREATE INDEX IF NOT EXISTS idx_user_post_hides_user_hidden
    ON user_post_hides(user_id, hidden_at DESC);

CREATE UNIQUE INDEX IF NOT EXISTS idx_chat_conversations_direct_pair
    ON chat_conversations(direct_pair_key)
    WHERE conversation_type = 'direct'
      AND deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_chat_conversations_context
    ON chat_conversations(context_type, context_id);

CREATE INDEX IF NOT EXISTS idx_chat_conversations_last_message
    ON chat_conversations(last_message_at DESC);

CREATE UNIQUE INDEX IF NOT EXISTS idx_chat_members_conversation_user_active
    ON chat_conversation_members(conversation_id, user_id)
    WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_chat_members_user_status
    ON chat_conversation_members(user_id, status, pinned_at DESC, archived_at, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_chat_members_user_unread
    ON chat_conversation_members(user_id, unread_count);

CREATE INDEX IF NOT EXISTS idx_chat_members_conversation
    ON chat_conversation_members(conversation_id, status);

CREATE UNIQUE INDEX IF NOT EXISTS idx_chat_message_requests_pending_pair
    ON chat_message_requests(requester_user_id, recipient_user_id)
    WHERE status = 'pending';

CREATE INDEX IF NOT EXISTS idx_chat_message_requests_recipient_status
    ON chat_message_requests(recipient_user_id, status, requested_at DESC);

CREATE INDEX IF NOT EXISTS idx_chat_message_requests_requester_status
    ON chat_message_requests(requester_user_id, status, requested_at DESC);

CREATE INDEX IF NOT EXISTS idx_chat_message_requests_conversation
    ON chat_message_requests(conversation_id)
    WHERE conversation_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS idx_chat_messages_conversation_seq
    ON chat_messages(conversation_id, message_seq);

CREATE UNIQUE INDEX IF NOT EXISTS idx_chat_messages_client_message
    ON chat_messages(sender_user_id, client_message_id)
    WHERE client_message_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_post_shares_post_created
    ON post_shares(social_post_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_post_shares_user_created
    ON post_shares(shared_by_user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_post_shares_conversation
    ON post_shares(conversation_id, created_at DESC)
    WHERE conversation_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_chat_messages_conversation_created
    ON chat_messages(conversation_id, message_seq DESC);

CREATE INDEX IF NOT EXISTS idx_chat_messages_sender_created
    ON chat_messages(sender_user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_chat_messages_target_object
    ON chat_messages(target_object_type, target_object_id);

CREATE INDEX IF NOT EXISTS idx_chat_attachments_message_sort
    ON chat_message_attachments(message_id, sort_order);

CREATE INDEX IF NOT EXISTS idx_chat_attachments_object
    ON chat_message_attachments(object_type, object_id);

CREATE UNIQUE INDEX IF NOT EXISTS idx_notification_events_dedup
    ON notification_events(dedup_key)
    WHERE dedup_key IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_notification_events_object
    ON notification_events(object_type, object_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_notification_events_actor_created
    ON notification_events(actor_user_id, created_at DESC);

CREATE UNIQUE INDEX IF NOT EXISTS idx_user_notifications_recipient_event
    ON user_notifications(recipient_user_id, notification_event_id);

CREATE INDEX IF NOT EXISTS idx_user_notifications_recipient_unread
    ON user_notifications(recipient_user_id, read_at, created_at DESC)
    WHERE status = 'visible' AND deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_user_notifications_recipient_created
    ON user_notifications(recipient_user_id, created_at DESC)
    WHERE status = 'visible' AND deleted_at IS NULL;

CREATE UNIQUE INDEX IF NOT EXISTS idx_content_reports_active_reporter_target
    ON content_reports(reporter_user_id, target_type, target_id)
    WHERE status IN ('pending', 'reviewing');

CREATE INDEX IF NOT EXISTS idx_content_reports_target_created
    ON content_reports(target_type, target_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_content_reports_status_created
    ON content_reports(status, created_at DESC);

CREATE UNIQUE INDEX IF NOT EXISTS idx_points_video_point_index
    ON points(video_id, point_index);

CREATE INDEX IF NOT EXISTS idx_points_video_start_time
    ON points(video_id, start_time_ms);

CREATE INDEX IF NOT EXISTS idx_points_video_winner
    ON points(video_id, winner_slot);

CREATE INDEX IF NOT EXISTS idx_points_video_server
    ON points(video_id, server_slot);

CREATE INDEX IF NOT EXISTS idx_points_terminal_shot_id
    ON points(terminal_shot_id);

CREATE UNIQUE INDEX IF NOT EXISTS idx_shots_point_shot_index
    ON shots(point_id, shot_index);

CREATE INDEX IF NOT EXISTS idx_shots_point_contact_time
    ON shots(point_id, contact_time_ms);

CREATE INDEX IF NOT EXISTS idx_shots_hitter_slot
    ON shots(hitter_slot);

CREATE INDEX IF NOT EXISTS idx_shots_stroke_type_side
    ON shots(stroke_type, stroke_side);

CREATE INDEX IF NOT EXISTS idx_shots_shot_result
    ON shots(shot_result);

CREATE INDEX IF NOT EXISTS idx_shots_first_bounce_coords
    ON shots(first_bounce_x_m, first_bounce_y_m)
    WHERE first_bounce_x_m IS NOT NULL
      AND first_bounce_y_m IS NOT NULL;

CREATE TRIGGER IF NOT EXISTS trg_users_set_updated_at
AFTER UPDATE ON users
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE users
    SET updated_at = CURRENT_TIMESTAMP
    WHERE user_id = OLD.user_id;
END;

CREATE TRIGGER IF NOT EXISTS trg_admin_users_set_updated_at
AFTER UPDATE ON admin_users
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE admin_users
    SET updated_at = CURRENT_TIMESTAMP
    WHERE admin_user_id = OLD.admin_user_id;
END;

CREATE TRIGGER IF NOT EXISTS trg_admin_credentials_set_updated_at
AFTER UPDATE ON admin_credentials
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE admin_credentials
    SET updated_at = CURRENT_TIMESTAMP
    WHERE admin_credential_id = OLD.admin_credential_id;
END;

CREATE TRIGGER IF NOT EXISTS trg_auth_identities_set_updated_at
AFTER UPDATE ON auth_identities
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE auth_identities
    SET updated_at = CURRENT_TIMESTAMP
    WHERE identity_id = OLD.identity_id;
END;

CREATE TRIGGER IF NOT EXISTS trg_auth_sessions_set_updated_at
AFTER UPDATE ON auth_sessions
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE auth_sessions
    SET updated_at = CURRENT_TIMESTAMP
    WHERE session_id = OLD.session_id;
END;

CREATE TRIGGER IF NOT EXISTS trg_auth_verification_codes_set_updated_at
AFTER UPDATE ON auth_verification_codes
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE auth_verification_codes
    SET updated_at = CURRENT_TIMESTAMP
    WHERE verification_code_id = OLD.verification_code_id;
END;

CREATE TRIGGER IF NOT EXISTS trg_coach_applications_set_updated_at
AFTER UPDATE ON coach_applications
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE coach_applications
    SET updated_at = CURRENT_TIMESTAMP
    WHERE coach_application_id = OLD.coach_application_id;
END;

CREATE TRIGGER IF NOT EXISTS trg_coach_profiles_set_updated_at
AFTER UPDATE ON coach_profiles
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE coach_profiles
    SET updated_at = CURRENT_TIMESTAMP
    WHERE coach_profile_id = OLD.coach_profile_id;
END;

CREATE TRIGGER IF NOT EXISTS trg_lessons_set_updated_at
AFTER UPDATE ON lessons
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE lessons
    SET updated_at = CURRENT_TIMESTAMP
    WHERE lesson_id = OLD.lesson_id;
END;

CREATE TRIGGER IF NOT EXISTS trg_lesson_students_set_updated_at
AFTER UPDATE ON lesson_students
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE lesson_students
    SET updated_at = CURRENT_TIMESTAMP
    WHERE lesson_student_id = OLD.lesson_student_id;
END;

CREATE TRIGGER IF NOT EXISTS trg_tennis_activities_set_updated_at
AFTER UPDATE ON tennis_activities
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE tennis_activities
    SET updated_at = CURRENT_TIMESTAMP
    WHERE tennis_activity_id = OLD.tennis_activity_id;
END;

CREATE TRIGGER IF NOT EXISTS trg_videos_set_updated_at
AFTER UPDATE ON videos
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE videos
    SET updated_at = CURRENT_TIMESTAMP
    WHERE video_id = OLD.video_id;
END;

CREATE TRIGGER IF NOT EXISTS trg_video_shares_set_updated_at
AFTER UPDATE ON video_shares
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE video_shares
    SET updated_at = CURRENT_TIMESTAMP
    WHERE video_share_id = OLD.video_share_id;
END;

CREATE TRIGGER IF NOT EXISTS trg_social_posts_set_updated_at
AFTER UPDATE ON social_posts
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE social_posts
    SET updated_at = CURRENT_TIMESTAMP
    WHERE social_post_id = OLD.social_post_id;
END;

CREATE TRIGGER IF NOT EXISTS trg_post_media_set_updated_at
AFTER UPDATE ON post_media
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE post_media
    SET updated_at = CURRENT_TIMESTAMP
    WHERE post_media_id = OLD.post_media_id;
END;

CREATE TRIGGER IF NOT EXISTS trg_user_follows_set_updated_at
AFTER UPDATE ON user_follows
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE user_follows
    SET updated_at = CURRENT_TIMESTAMP
    WHERE follow_id = OLD.follow_id;
END;

CREATE TRIGGER IF NOT EXISTS trg_user_social_stats_set_updated_at
AFTER UPDATE ON user_social_stats
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE user_social_stats
    SET updated_at = CURRENT_TIMESTAMP
    WHERE user_id = OLD.user_id;
END;

CREATE TRIGGER IF NOT EXISTS trg_user_blocks_set_updated_at
AFTER UPDATE ON user_blocks
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE user_blocks
    SET updated_at = CURRENT_TIMESTAMP
    WHERE user_block_id = OLD.user_block_id;
END;

CREATE TRIGGER IF NOT EXISTS trg_user_privacy_settings_set_updated_at
AFTER UPDATE ON user_privacy_settings
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE user_privacy_settings
    SET updated_at = CURRENT_TIMESTAMP
    WHERE user_id = OLD.user_id;
END;

CREATE TRIGGER IF NOT EXISTS trg_user_notification_preferences_set_updated_at
AFTER UPDATE ON user_notification_preferences
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE user_notification_preferences
    SET updated_at = CURRENT_TIMESTAMP
    WHERE user_id = OLD.user_id;
END;

CREATE TRIGGER IF NOT EXISTS trg_social_post_stats_set_updated_at
AFTER UPDATE ON social_post_stats
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE social_post_stats
    SET updated_at = CURRENT_TIMESTAMP
    WHERE social_post_id = OLD.social_post_id;
END;

CREATE TRIGGER IF NOT EXISTS trg_post_reactions_set_updated_at
AFTER UPDATE ON post_reactions
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE post_reactions
    SET updated_at = CURRENT_TIMESTAMP
    WHERE reaction_id = OLD.reaction_id;
END;

CREATE TRIGGER IF NOT EXISTS trg_post_favorites_set_updated_at
AFTER UPDATE ON post_favorites
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE post_favorites
    SET updated_at = CURRENT_TIMESTAMP
    WHERE favorite_id = OLD.favorite_id;
END;

CREATE TRIGGER IF NOT EXISTS trg_post_comments_set_updated_at
AFTER UPDATE ON post_comments
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE post_comments
    SET updated_at = CURRENT_TIMESTAMP
    WHERE comment_id = OLD.comment_id;
END;

CREATE TRIGGER IF NOT EXISTS trg_user_post_views_set_updated_at
AFTER UPDATE ON user_post_views
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE user_post_views
    SET updated_at = CURRENT_TIMESTAMP
    WHERE user_post_view_id = OLD.user_post_view_id;
END;

CREATE TRIGGER IF NOT EXISTS trg_user_post_hides_set_updated_at
AFTER UPDATE ON user_post_hides
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE user_post_hides
    SET updated_at = CURRENT_TIMESTAMP
    WHERE user_post_hide_id = OLD.user_post_hide_id;
END;

CREATE TRIGGER IF NOT EXISTS trg_chat_conversations_set_updated_at
AFTER UPDATE ON chat_conversations
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE chat_conversations
    SET updated_at = CURRENT_TIMESTAMP
    WHERE conversation_id = OLD.conversation_id;
END;

CREATE TRIGGER IF NOT EXISTS trg_chat_members_set_updated_at
AFTER UPDATE ON chat_conversation_members
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE chat_conversation_members
    SET updated_at = CURRENT_TIMESTAMP
    WHERE conversation_member_id = OLD.conversation_member_id;
END;

CREATE TRIGGER IF NOT EXISTS trg_chat_message_requests_set_updated_at
AFTER UPDATE ON chat_message_requests
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE chat_message_requests
    SET updated_at = CURRENT_TIMESTAMP
    WHERE message_request_id = OLD.message_request_id;
END;

CREATE TRIGGER IF NOT EXISTS trg_chat_messages_set_updated_at
AFTER UPDATE ON chat_messages
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE chat_messages
    SET updated_at = CURRENT_TIMESTAMP
    WHERE message_id = OLD.message_id;
END;

CREATE TRIGGER IF NOT EXISTS trg_user_notifications_set_updated_at
AFTER UPDATE ON user_notifications
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE user_notifications
    SET updated_at = CURRENT_TIMESTAMP
    WHERE user_notification_id = OLD.user_notification_id;
END;

CREATE TRIGGER IF NOT EXISTS trg_user_inbox_counters_set_updated_at
AFTER UPDATE ON user_inbox_counters
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE user_inbox_counters
    SET updated_at = CURRENT_TIMESTAMP
    WHERE user_id = OLD.user_id;
END;

CREATE TRIGGER IF NOT EXISTS trg_content_reports_set_updated_at
AFTER UPDATE ON content_reports
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE content_reports
    SET updated_at = CURRENT_TIMESTAMP
    WHERE content_report_id = OLD.content_report_id;
END;

CREATE TRIGGER IF NOT EXISTS trg_points_set_updated_at
AFTER UPDATE ON points
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE points
    SET updated_at = CURRENT_TIMESTAMP
    WHERE point_id = OLD.point_id;
END;

CREATE TRIGGER IF NOT EXISTS trg_shots_set_updated_at
AFTER UPDATE ON shots
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE shots
    SET updated_at = CURRENT_TIMESTAMP
    WHERE shot_id = OLD.shot_id;
END;

CREATE TRIGGER IF NOT EXISTS trg_points_terminal_shot_same_point_update
BEFORE UPDATE OF terminal_shot_id ON points
FOR EACH ROW
WHEN NEW.terminal_shot_id IS NOT NULL
BEGIN
    SELECT
        CASE
            WHEN NOT EXISTS (
                SELECT 1
                FROM shots
                WHERE shot_id = NEW.terminal_shot_id
                  AND point_id = NEW.point_id
            )
            THEN RAISE(ABORT, 'terminal_shot_id must reference a shot in the same point')
        END;
END;
