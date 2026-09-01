"""Point-level PostgreSQL schema helpers."""

from __future__ import annotations

import argparse
from pathlib import Path

from .connection import DEFAULT_DB_PATH, get_connection


CREATE_POINTS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS points (
    point_id TEXT PRIMARY KEY,
    upload_id TEXT NOT NULL,
    point_index INTEGER NOT NULL,
    start_frame INTEGER NOT NULL,
    end_frame INTEGER NOT NULL,
    start_time REAL NOT NULL,
    end_time REAL NOT NULL,
    duration_sec REAL NOT NULL,
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

CREATE INDEX IF NOT EXISTS idx_points_upload_id
ON points(upload_id);

CREATE INDEX IF NOT EXISTS idx_points_start_frame
ON points(start_frame);

CREATE INDEX IF NOT EXISTS idx_points_server_id
ON points(server_id);

CREATE INDEX IF NOT EXISTS idx_points_winner_id
ON points(winner_id);

CREATE INDEX IF NOT EXISTS idx_points_ending_shot_id
ON points(ending_shot_id);
"""


def create_points_table(db_path: str | Path = DEFAULT_DB_PATH) -> Path:
    path = Path(db_path)

    with get_connection(path) as connection:
        connection.executescript(CREATE_POINTS_TABLE_SQL)
        connection.commit()

    return path


def main() -> None:
    parser = argparse.ArgumentParser(description="Create the CV PostgreSQL points table.")
    parser.add_argument(
        "--db-path",
        type=Path,
        default=DEFAULT_DB_PATH,
        help="Deprecated compatibility path; PostgreSQL DSN comes from environment.",
    )
    args = parser.parse_args()

    db_path = create_points_table(args.db_path)
    print(f"CV PostgreSQL points table is ready (schema from environment); path ignored: {db_path}")


if __name__ == "__main__":
    main()
