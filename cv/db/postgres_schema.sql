-- PostgreSQL schema for CV analysis persistence.
-- The historical CV table/column contract is intentionally unchanged.
-- Runtime setup normally uses cv.persistence.postgres.initialize_schema().

CREATE SCHEMA IF NOT EXISTS cv_analysis;
SET search_path TO cv_analysis, pg_catalog;

CREATE TABLE IF NOT EXISTS users (
    user_id TEXT PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    display_name TEXT,
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'disabled')),
    created_at TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP AT TIME ZONE 'UTC')::text,
    updated_at TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP AT TIME ZONE 'UTC')::text
);

CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);

CREATE TABLE IF NOT EXISTS uploads (
    upload_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    original_filename TEXT NOT NULL,
    stored_path TEXT NOT NULL,
    file_size_bytes INTEGER CHECK (file_size_bytes IS NULL OR file_size_bytes >= 0),
    duration_sec double precision CHECK (duration_sec IS NULL OR duration_sec >= 0),
    fps double precision CHECK (fps IS NULL OR fps > 0),
    width INTEGER CHECK (width IS NULL OR width > 0),
    height INTEGER CHECK (height IS NULL OR height > 0),
    status TEXT NOT NULL DEFAULT 'uploaded'
        CHECK (status IN ('uploaded', 'processing', 'completed', 'failed')),
    created_at TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP AT TIME ZONE 'UTC')::text,
    started_at TEXT,
    finished_at TEXT,
    error_message TEXT,
    progress_percent INTEGER NOT NULL DEFAULT 0,
    progress_stage TEXT,
    progress_message TEXT,
    processed_frames INTEGER,
    total_frames INTEGER,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_uploads_user_id ON uploads(user_id);
CREATE INDEX IF NOT EXISTS idx_uploads_status ON uploads(status);
CREATE INDEX IF NOT EXISTS idx_uploads_created_at ON uploads(created_at);
CREATE INDEX IF NOT EXISTS idx_uploads_original_filename ON uploads(original_filename);

CREATE TABLE IF NOT EXISTS points (
    point_id TEXT PRIMARY KEY,
    upload_id TEXT NOT NULL,
    point_index INTEGER NOT NULL,
    start_frame INTEGER NOT NULL,
    end_frame INTEGER NOT NULL,
    start_time double precision NOT NULL,
    end_time double precision NOT NULL,
    duration_sec double precision NOT NULL,
    server_id TEXT,
    receiver_id TEXT,
    serve_count INTEGER CHECK (serve_count IN (1, 2)),
    first_serve_in INTEGER CHECK (first_serve_in IN (0, 1)),
    second_serve_in INTEGER CHECK (second_serve_in IN (0, 1)),
    rally_shot_count INTEGER,
    winner_id TEXT,
    loser_id TEXT,
    point_won_by_server INTEGER CHECK (point_won_by_server IN (0, 1)),
    ending_shot_id TEXT,
    ending_hitter_id TEXT,
    ending_type TEXT,
    ending_reason TEXT,
    a_shot_count INTEGER,
    b_shot_count INTEGER,
    UNIQUE(upload_id, point_index),
    FOREIGN KEY (upload_id) REFERENCES uploads(upload_id) ON DELETE CASCADE,
    CHECK (point_index >= 1),
    CHECK (start_frame >= 0),
    CHECK (end_frame >= start_frame),
    CHECK (start_time >= 0),
    CHECK (end_time >= start_time),
    CHECK (duration_sec >= 0),
    CHECK (server_id IS NULL OR server_id IN ('A', 'B')),
    CHECK (receiver_id IS NULL OR receiver_id IN ('A', 'B')),
    CHECK (winner_id IS NULL OR winner_id IN ('A', 'B')),
    CHECK (loser_id IS NULL OR loser_id IN ('A', 'B')),
    CHECK (ending_hitter_id IS NULL OR ending_hitter_id IN ('A', 'B')),
    CHECK (a_shot_count IS NULL OR a_shot_count >= 0),
    CHECK (b_shot_count IS NULL OR b_shot_count >= 0),
    CHECK (rally_shot_count IS NULL OR rally_shot_count >= 0)
);

CREATE INDEX IF NOT EXISTS idx_points_upload_id ON points(upload_id);
CREATE INDEX IF NOT EXISTS idx_points_start_frame ON points(start_frame);
CREATE INDEX IF NOT EXISTS idx_points_server_id ON points(server_id);
CREATE INDEX IF NOT EXISTS idx_points_winner_id ON points(winner_id);
CREATE INDEX IF NOT EXISTS idx_points_ending_shot_id ON points(ending_shot_id);

CREATE TABLE IF NOT EXISTS shots (
    shot_id TEXT PRIMARY KEY,
    point_id TEXT NOT NULL,
    shot_index INTEGER NOT NULL,
    hitter_id TEXT,
    contact_frame INTEGER NOT NULL,
    contact_time double precision NOT NULL,
    contact_x double precision,
    contact_y double precision,
    hitter_x double precision,
    hitter_y double precision,
    opponent_at_contact_x double precision,
    opponent_at_contact_y double precision,
    opponent_at_bounce_x double precision,
    opponent_at_bounce_y double precision,
    opponent_at_next_hit_x double precision,
    opponent_at_next_hit_y double precision,
    shot_phase TEXT,
    serve_number TEXT,
    stroke_type TEXT,
    stroke_side TEXT,
    bounce_count_before_hit INTEGER,
    incoming_speed_kmh double precision,
    outgoing_speed_kmh double precision,
    first_bounce_frame INTEGER,
    first_bounce_time double precision,
    first_bounce_x double precision,
    first_bounce_y double precision,
    trajectory_end_type TEXT,
    direction TEXT,
    depth_zone TEXT,
    width_zone TEXT,
    legality TEXT,
    fault_type TEXT,
    shot_outcome TEXT,
    error_forcedness TEXT,
    point_ending INTEGER NOT NULL DEFAULT 0 CHECK (point_ending IN (0, 1)),
    point_winner TEXT,
    ending_reason TEXT,
    UNIQUE(point_id, shot_index),
    FOREIGN KEY (point_id) REFERENCES points(point_id) ON DELETE CASCADE,
    CHECK (shot_index >= 1),
    CHECK (contact_frame >= 0),
    CHECK (contact_time >= 0),
    CHECK (first_bounce_frame IS NULL OR first_bounce_frame >= contact_frame),
    CHECK (first_bounce_time IS NULL OR first_bounce_time >= contact_time),
    CHECK (hitter_id IS NULL OR hitter_id IN ('A', 'B')),
    CHECK (point_winner IS NULL OR point_winner IN ('A', 'B')),
    CHECK (bounce_count_before_hit IS NULL OR bounce_count_before_hit >= 0)
);

CREATE INDEX IF NOT EXISTS idx_shots_point_id ON shots(point_id);
CREATE INDEX IF NOT EXISTS idx_shots_contact_frame ON shots(contact_frame);
CREATE INDEX IF NOT EXISTS idx_shots_first_bounce_frame ON shots(first_bounce_frame);
CREATE INDEX IF NOT EXISTS idx_shots_hitter_id ON shots(hitter_id);
