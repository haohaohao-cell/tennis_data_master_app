"""Shot-level PostgreSQL schema helpers.

This module only initializes the shot table for now.
Future extraction can read `match_frames.json` plus the net-hit subset from
`match_tactics.json` and insert one row per shot.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from .connection import DEFAULT_DB_PATH, get_connection



CREATE_SHOTS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS shots (
    shot_id TEXT PRIMARY KEY,
    point_id TEXT NOT NULL,
    shot_index INTEGER NOT NULL,
    hitter_id TEXT,
    contact_frame INTEGER NOT NULL,
    contact_time REAL NOT NULL,
    contact_x REAL,
    contact_y REAL,
    hitter_x REAL,
    hitter_y REAL,
    opponent_at_contact_x REAL,
    opponent_at_contact_y REAL,
    opponent_at_bounce_x REAL,
    opponent_at_bounce_y REAL,
    opponent_at_next_hit_x REAL,
    opponent_at_next_hit_y REAL,
    shot_phase TEXT,
    serve_number TEXT,
    stroke_type TEXT,
    stroke_side TEXT,
    bounce_count_before_hit INTEGER,
    incoming_speed_kmh REAL,
    outgoing_speed_kmh REAL,
    first_bounce_frame INTEGER,
    first_bounce_time REAL,
    first_bounce_x REAL,
    first_bounce_y REAL,
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

CREATE INDEX IF NOT EXISTS idx_shots_point_id
ON shots(point_id);

CREATE INDEX IF NOT EXISTS idx_shots_contact_frame
ON shots(contact_frame);

CREATE INDEX IF NOT EXISTS idx_shots_first_bounce_frame
ON shots(first_bounce_frame);

CREATE INDEX IF NOT EXISTS idx_shots_hitter_id
ON shots(hitter_id);
"""


def create_shots_table(db_path: str | Path = DEFAULT_DB_PATH) -> Path:
    path = Path(db_path)

    with get_connection(path) as connection:
        connection.executescript(CREATE_SHOTS_TABLE_SQL)
        connection.commit()

    return path


def main() -> None:
    parser = argparse.ArgumentParser(description="Create the CV PostgreSQL shots table.")
    parser.add_argument(
        "--db-path",
        type=Path,
        default=DEFAULT_DB_PATH,
        help="Deprecated compatibility path; PostgreSQL DSN comes from environment.",
    )
    args = parser.parse_args()

    db_path = create_shots_table(args.db_path)
    print(f"CV PostgreSQL shots table is ready (schema from environment); path ignored: {db_path}")


if __name__ == "__main__":
    main()
