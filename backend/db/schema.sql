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
    published_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at TEXT,
    FOREIGN KEY (author_user_id) REFERENCES users(user_id),
    FOREIGN KEY (source_tennis_activity_id) REFERENCES tennis_activities(tennis_activity_id) ON DELETE SET NULL
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

CREATE UNIQUE INDEX IF NOT EXISTS idx_post_media_post_sort_active
    ON post_media(social_post_id, sort_order)
    WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_post_media_post_sort
    ON post_media(social_post_id, sort_order);

CREATE INDEX IF NOT EXISTS idx_post_media_video
    ON post_media(video_id);

CREATE INDEX IF NOT EXISTS idx_post_media_type
    ON post_media(media_type);

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
