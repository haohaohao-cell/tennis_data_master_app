-- SQLite schema for the first-version tennis data model.
-- Source of truth: docs/data/网球数据库设计.md

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
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at TEXT
);

CREATE TABLE IF NOT EXISTS uploads (
    upload_id TEXT PRIMARY KEY,
    owner_user_id TEXT NOT NULL,
    filename TEXT NOT NULL CHECK (length(filename) <= 255),
    original_filename TEXT,
    activity_type TEXT NOT NULL
        CHECK (activity_type IN ('match', 'training', 'drill')),
    video_path TEXT NOT NULL,
    video_duration_ms INTEGER CHECK (video_duration_ms >= 0),
    video_frame_count INTEGER CHECK (video_frame_count >= 0),
    video_fps REAL CHECK (video_fps > 0),
    video_width_px INTEGER CHECK (video_width_px > 0),
    video_height_px INTEGER CHECK (video_height_px > 0),
    camera_view_angle TEXT
        CHECK (camera_view_angle IN ('overhead', 'horizontal')),
    camera_view_position TEXT
        CHECK (camera_view_position IN (
            'side',
            'rear',
            'front',
            'rear_side',
            'front_side'
        )),
    frame_data_path TEXT,
    frame_data_version TEXT CHECK (frame_data_version IS NULL OR length(frame_data_version) <= 30),
    player_a_user_id TEXT,
    player_b_user_id TEXT,
    player_a_name TEXT CHECK (player_a_name IS NULL OR length(player_a_name) <= 50),
    player_b_name TEXT CHECK (player_b_name IS NULL OR length(player_b_name) <= 50),
    primary_player_slot TEXT CHECK (primary_player_slot IN ('A', 'B')),
    analysis_status TEXT NOT NULL DEFAULT 'uploaded'
        CHECK (analysis_status IN ('uploaded', 'processing', 'completed', 'failed')),
    analysis_version TEXT CHECK (analysis_version IS NULL OR length(analysis_version) <= 50),
    error_message TEXT,
    captured_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at TEXT,
    CHECK (player_a_user_id <> player_b_user_id),
    FOREIGN KEY (owner_user_id) REFERENCES users(user_id),
    FOREIGN KEY (player_a_user_id) REFERENCES users(user_id),
    FOREIGN KEY (player_b_user_id) REFERENCES users(user_id)
);

CREATE TABLE IF NOT EXISTS points (
    point_id TEXT PRIMARY KEY,
    upload_id TEXT NOT NULL,
    point_index INTEGER NOT NULL CHECK (point_index >= 1),
    start_frame INTEGER NOT NULL CHECK (start_frame >= 0),
    end_frame INTEGER CHECK (end_frame >= start_frame),
    start_time_ms INTEGER NOT NULL CHECK (start_time_ms >= 0),
    end_time_ms INTEGER CHECK (end_time_ms >= start_time_ms),
    server_slot TEXT CHECK (server_slot IN ('A', 'B')),
    winner_slot TEXT CHECK (winner_slot IN ('A', 'B')),
    terminal_shot_id TEXT,
    set_index INTEGER CHECK (set_index >= 1),
    game_index_in_set INTEGER CHECK (game_index_in_set >= 1),
    a_sets_before INTEGER CHECK (a_sets_before >= 0),
    b_sets_before INTEGER CHECK (b_sets_before >= 0),
    a_games_before INTEGER CHECK (a_games_before >= 0),
    b_games_before INTEGER CHECK (b_games_before >= 0),
    a_points_before INTEGER CHECK (a_points_before >= 0),
    b_points_before INTEGER CHECK (b_points_before >= 0),
    is_tiebreak INTEGER CHECK (is_tiebreak IN (0, 1)),
    first_serve_in INTEGER CHECK (first_serve_in IN (0, 1)),
    second_serve_used INTEGER CHECK (second_serve_used IN (0, 1)),
    second_serve_in INTEGER CHECK (second_serve_in IN (0, 1)),
    serve_let_count INTEGER NOT NULL DEFAULT 0 CHECK (serve_let_count >= 0),
    is_double_fault INTEGER CHECK (is_double_fault IN (0, 1)),
    total_shot_count INTEGER CHECK (total_shot_count >= 0),
    in_play_shot_count INTEGER CHECK (in_play_shot_count >= 0),
    point_result TEXT CHECK (point_result IN (
        'ace',
        'service_winner',
        'winner',
        'forced_error',
        'unforced_error',
        'double_fault',
        'unknown'
    )),
    ending_reason TEXT CHECK (ending_reason IN ('net', 'out', 'unreturned', 'unknown')),
    confidence REAL CHECK (confidence BETWEEN 0 AND 1),
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
    FOREIGN KEY (upload_id) REFERENCES uploads(upload_id) ON DELETE CASCADE,
    FOREIGN KEY (terminal_shot_id) REFERENCES shots(shot_id) DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE IF NOT EXISTS shots (
    shot_id TEXT PRIMARY KEY,
    point_id TEXT NOT NULL,
    shot_index INTEGER NOT NULL CHECK (shot_index >= 1),
    hitter_slot TEXT CHECK (hitter_slot IN ('A', 'B')),
    shot_role TEXT CHECK (shot_role IN ('serve', 'return', 'rally')),
    serve_number INTEGER CHECK (serve_number IN (1, 2)),
    contact_frame INTEGER NOT NULL CHECK (contact_frame >= 0),
    contact_time_ms INTEGER NOT NULL CHECK (contact_time_ms >= 0),
    contact_projected_x_m REAL,
    contact_projected_y_m REAL,
    hitter_x_m REAL,
    hitter_y_m REAL,
    opponent_x_m REAL,
    opponent_y_m REAL,
    bounce_count_before_hit INTEGER CHECK (bounce_count_before_hit >= 0 AND bounce_count_before_hit <= 1),
    contact_confidence REAL CHECK (contact_confidence BETWEEN 0 AND 1),
    stroke_type TEXT CHECK (stroke_type IN ('serve', 'groundstroke', 'volley', 'overhead', 'unknown')),
    stroke_side TEXT CHECK (stroke_side IN ('forehand', 'backhand', 'unknown')),
    stroke_confidence REAL CHECK (stroke_confidence BETWEEN 0 AND 1),
    incoming_speed_mps REAL CHECK (incoming_speed_mps >= 0),
    outgoing_speed_mps REAL CHECK (outgoing_speed_mps >= 0),
    outgoing_angle_deg REAL CHECK (outgoing_angle_deg > -180 AND outgoing_angle_deg <= 180),
    first_bounce_frame INTEGER CHECK (first_bounce_frame >= contact_frame),
    first_bounce_time_ms INTEGER CHECK (first_bounce_time_ms >= contact_time_ms),
    first_bounce_x_m REAL,
    first_bounce_y_m REAL,
    bounce_result TEXT CHECK (bounce_result IN ('in', 'out', 'unknown')),
    bounce_confidence REAL CHECK (bounce_confidence BETWEEN 0 AND 1),
    trajectory_end_type TEXT CHECK (trajectory_end_type IN (
        'opponent_hit',
        'second_bounce',
        'net',
        'out',
        'lost',
        'video_end',
        'unknown'
    )),
    shot_result TEXT CHECK (shot_result IN ('continue', 'winner', 'error', 'serve_fault', 'let', 'unknown')),
    error_forcedness TEXT CHECK (error_forcedness IN ('forced', 'unforced', 'unknown')),
    error_type TEXT CHECK (error_type IN ('net', 'long', 'wide', 'unknown')),
    is_point_ending INTEGER CHECK (is_point_ending IN (0, 1)),
    point_winner_slot TEXT CHECK (point_winner_slot IN ('A', 'B')),
    result_confidence REAL CHECK (result_confidence BETWEEN 0 AND 1),
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

CREATE UNIQUE INDEX IF NOT EXISTS idx_uploads_filename
    ON uploads(filename);

CREATE UNIQUE INDEX IF NOT EXISTS idx_uploads_video_path
    ON uploads(video_path);

CREATE INDEX IF NOT EXISTS idx_uploads_owner_created_at
    ON uploads(owner_user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_uploads_analysis_status_created_at
    ON uploads(analysis_status, created_at);

CREATE INDEX IF NOT EXISTS idx_uploads_camera_view
    ON uploads(camera_view_angle, camera_view_position);

CREATE INDEX IF NOT EXISTS idx_uploads_player_a_created_at
    ON uploads(player_a_user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_uploads_player_b_created_at
    ON uploads(player_b_user_id, created_at DESC);

CREATE UNIQUE INDEX IF NOT EXISTS idx_points_upload_point_index
    ON points(upload_id, point_index);

CREATE INDEX IF NOT EXISTS idx_points_upload_start_time
    ON points(upload_id, start_time_ms);

CREATE INDEX IF NOT EXISTS idx_points_upload_winner
    ON points(upload_id, winner_slot);

CREATE INDEX IF NOT EXISTS idx_points_upload_server
    ON points(upload_id, server_slot);

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

CREATE TRIGGER IF NOT EXISTS trg_uploads_set_updated_at
AFTER UPDATE ON uploads
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE uploads
    SET updated_at = CURRENT_TIMESTAMP
    WHERE upload_id = OLD.upload_id;
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

CREATE TRIGGER IF NOT EXISTS trg_points_terminal_shot_same_point
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
