"""Centralized PostgreSQL CRUD helpers for the tennis analysis system.

This module keeps all database operations in one place and covers the current
core tables:
- users
- uploads
- points
- shots

Most important entry points:
1. `save_upload_analysis_bundle(...)`
   Save one complete upload plus all derived point / shot analysis rows.
2. `get_upload_analysis_bundle(upload_id)`
   Query one previous upload and return its upload / point / shot data together.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

from .connection import DEFAULT_DB_PATH, get_connection
from .schema import initialize_all_tables


USER_COLUMNS = (
    "user_id",
    "email",
    "password_hash",
    "display_name",
    "status",
    "created_at",
    "updated_at",
)

UPLOAD_COLUMNS = (
    "upload_id",
    "user_id",
    "original_filename",
    "stored_path",
    "file_size_bytes",
    "duration_sec",
    "fps",
    "width",
    "height",
    "status",
    "created_at",
    "started_at",
    "finished_at",
    "error_message",
    "progress_percent",
    "progress_stage",
    "progress_message",
    "processed_frames",
    "total_frames",
)

POINT_COLUMNS = (
    "point_id",
    "upload_id",
    "point_index",
    "start_frame",
    "end_frame",
    "start_time",
    "end_time",
    "duration_sec",
    "server_id",
    "receiver_id",
    "serve_count",
    "first_serve_in",
    "second_serve_in",
    "rally_shot_count",
    "winner_id",
    "loser_id",
    "point_won_by_server",
    "ending_shot_id",
    "ending_hitter_id",
    "ending_type",
    "ending_reason",
    "a_shot_count",
    "b_shot_count",
)

SHOT_COLUMNS = (
    "shot_id",
    "point_id",
    "shot_index",
    "hitter_id",
    "contact_frame",
    "contact_time",
    "contact_x",
    "contact_y",
    "hitter_x",
    "hitter_y",
    "opponent_at_contact_x",
    "opponent_at_contact_y",
    "opponent_at_bounce_x",
    "opponent_at_bounce_y",
    "opponent_at_next_hit_x",
    "opponent_at_next_hit_y",
    "shot_phase",
    "serve_number",
    "stroke_type",
    "stroke_side",
    "bounce_count_before_hit",
    "incoming_speed_kmh",
    "outgoing_speed_kmh",
    "first_bounce_frame",
    "first_bounce_time",
    "first_bounce_x",
    "first_bounce_y",
    "trajectory_end_type",
    "direction",
    "depth_zone",
    "width_zone",
    "legality",
    "fault_type",
    "shot_outcome",
    "error_forcedness",
    "point_ending",
    "point_winner",
    "ending_reason",
)


def _dict_from_row(row: Any | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return dict(row)


def _dicts_from_rows(rows: Iterable[Any]) -> list[dict[str, Any]]:
    return [dict(row) for row in rows]


def _pick_columns(payload: dict[str, Any], columns: tuple[str, ...]) -> dict[str, Any]:
    return {column: payload.get(column) for column in columns if column in payload}


def _normalize_columns(payload: dict[str, Any], columns: tuple[str, ...]) -> dict[str, Any]:
    return {column: payload.get(column) for column in columns}


def _load_json_payload(payload_or_path: dict[str, Any] | str | Path) -> dict[str, Any]:
    if isinstance(payload_or_path, dict):
        return payload_or_path
    path = Path(payload_or_path)
    return json.loads(path.read_text(encoding="utf-8"))


class TennisAnalysisRepository:
    """Single entry point for all CV PostgreSQL reads and writes."""

    def __init__(self, db_path: str | Path = DEFAULT_DB_PATH) -> None:
        self.db_path = Path(db_path)

    def connect(self):
        connection = get_connection(self.db_path)
        return connection

    def ensure_schema(self) -> Path:
        return initialize_all_tables(self.db_path)

    # ------------------------------------------------------------------
    # Generic helpers
    # ------------------------------------------------------------------
    def _fetch_one(self, sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(sql, params).fetchone()
        return _dict_from_row(row)

    def _fetch_all(self, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(sql, params).fetchall()
        return _dicts_from_rows(rows)

    def _execute(self, sql: str, params: tuple[Any, ...] = ()) -> int:
        with self.connect() as connection:
            cursor = connection.execute(sql, params)
            connection.commit()
            return cursor.rowcount

    # ------------------------------------------------------------------
    # Users CRUD
    # ------------------------------------------------------------------
    def create_user(self, user_row: dict[str, Any]) -> None:
        payload = _normalize_columns(user_row, USER_COLUMNS)
        required = ("user_id", "email", "password_hash")
        missing = [column for column in required if not payload.get(column)]
        if missing:
            raise ValueError(f"user_row missing required fields: {missing}")

        sql = """
        INSERT INTO users (user_id, email, password_hash, display_name, status, created_at, updated_at)
        VALUES (:user_id, :email, :password_hash, :display_name, COALESCE(:status, 'active'),
                COALESCE(:created_at, CURRENT_TIMESTAMP), COALESCE(:updated_at, CURRENT_TIMESTAMP))
        """
        with self.connect() as connection:
            connection.execute(sql, payload)
            connection.commit()

    def get_user(self, user_id: str) -> dict[str, Any] | None:
        return self._fetch_one("SELECT * FROM users WHERE user_id = ?", (user_id,))

    def list_users(self) -> list[dict[str, Any]]:
        return self._fetch_all("SELECT * FROM users ORDER BY created_at DESC, user_id")

    def update_user(self, user_id: str, updates: dict[str, Any]) -> int:
        allowed = {column: updates[column] for column in ("email", "password_hash", "display_name", "status", "updated_at") if column in updates}
        if not allowed:
            return 0
        assignments = ", ".join(f"{column} = :{column}" for column in allowed)
        allowed["user_id"] = user_id
        sql = f"UPDATE users SET {assignments} WHERE user_id = :user_id"
        with self.connect() as connection:
            cursor = connection.execute(sql, allowed)
            connection.commit()
            return cursor.rowcount

    def delete_user(self, user_id: str) -> int:
        return self._execute("DELETE FROM users WHERE user_id = ?", (user_id,))

    def ensure_user_exists(self, user_id: str, user_row: dict[str, Any] | None = None) -> dict[str, Any]:
        existing = self.get_user(user_id)
        if existing is not None:
            return existing

        fallback = {
            "user_id": user_id,
            "email": f"{user_id}@local.test",
            "password_hash": "placeholder",
            "display_name": user_id,
            "status": "active",
        }
        if user_row:
            fallback.update(_pick_columns(user_row, USER_COLUMNS))
            fallback["user_id"] = user_id
        self.create_user(fallback)
        return self.get_user(user_id) or fallback

    # ------------------------------------------------------------------
    # Uploads CRUD
    # ------------------------------------------------------------------
    def create_upload(self, upload_row: dict[str, Any], *, ensure_user: bool = True) -> None:
        payload = _normalize_columns(upload_row, UPLOAD_COLUMNS)
        required = ("upload_id", "user_id", "original_filename", "stored_path")
        missing = [column for column in required if not payload.get(column)]
        if missing:
            raise ValueError(f"upload_row missing required fields: {missing}")

        if ensure_user:
            self.ensure_user_exists(payload["user_id"])

        sql = """
        INSERT INTO uploads (
            upload_id, user_id, original_filename, stored_path, file_size_bytes,
            duration_sec, fps, width, height, status, created_at,
            started_at, finished_at, error_message, progress_percent,
            progress_stage, progress_message, processed_frames, total_frames
        ) VALUES (
            :upload_id, :user_id, :original_filename, :stored_path, :file_size_bytes,
            :duration_sec, :fps, :width, :height, COALESCE(:status, 'uploaded'),
            COALESCE(:created_at, CURRENT_TIMESTAMP), :started_at, :finished_at, :error_message,
            COALESCE(:progress_percent, 0), :progress_stage, :progress_message,
            :processed_frames, :total_frames
        )
        """
        with self.connect() as connection:
            connection.execute(sql, payload)
            connection.commit()

    def get_upload(self, upload_id: str) -> dict[str, Any] | None:
        return self._fetch_one("SELECT * FROM uploads WHERE upload_id = ?", (upload_id,))

    def list_uploads(self, user_id: str | None = None) -> list[dict[str, Any]]:
        if user_id is None:
            return self._fetch_all("SELECT * FROM uploads ORDER BY created_at DESC, upload_id")
        return self._fetch_all(
            "SELECT * FROM uploads WHERE user_id = ? ORDER BY created_at DESC, upload_id",
            (user_id,),
        )

    def update_upload(self, upload_id: str, updates: dict[str, Any]) -> int:
        allowed_columns = (
            "user_id",
            "original_filename",
            "stored_path",
            "file_size_bytes",
            "duration_sec",
            "fps",
            "width",
            "height",
            "status",
            "created_at",
            "started_at",
            "finished_at",
            "error_message",
            "progress_percent",
            "progress_stage",
            "progress_message",
            "processed_frames",
            "total_frames",
        )
        allowed = {column: updates[column] for column in allowed_columns if column in updates}
        if not allowed:
            return 0
        assignments = ", ".join(f"{column} = :{column}" for column in allowed)
        allowed["upload_id"] = upload_id
        sql = f"UPDATE uploads SET {assignments} WHERE upload_id = :upload_id"
        with self.connect() as connection:
            cursor = connection.execute(sql, allowed)
            connection.commit()
            return cursor.rowcount

    def upsert_upload(self, upload_row: dict[str, Any], *, ensure_user: bool = True) -> None:
        payload = _normalize_columns(upload_row, UPLOAD_COLUMNS)
        required = ("upload_id", "user_id", "original_filename", "stored_path")
        missing = [column for column in required if not payload.get(column)]
        if missing:
            raise ValueError(f"upload_row missing required fields: {missing}")

        if ensure_user:
            self.ensure_user_exists(payload["user_id"])

        sql = """
        INSERT INTO uploads (
            upload_id, user_id, original_filename, stored_path, file_size_bytes,
            duration_sec, fps, width, height, status, created_at,
            started_at, finished_at, error_message, progress_percent,
            progress_stage, progress_message, processed_frames, total_frames
        ) VALUES (
            :upload_id, :user_id, :original_filename, :stored_path, :file_size_bytes,
            :duration_sec, :fps, :width, :height, COALESCE(:status, 'uploaded'),
            COALESCE(:created_at, CURRENT_TIMESTAMP), :started_at, :finished_at, :error_message,
            COALESCE(:progress_percent, 0), :progress_stage, :progress_message,
            :processed_frames, :total_frames
        )
        ON CONFLICT(upload_id) DO UPDATE SET
            user_id = excluded.user_id,
            original_filename = excluded.original_filename,
            stored_path = excluded.stored_path,
            file_size_bytes = excluded.file_size_bytes,
            duration_sec = excluded.duration_sec,
            fps = excluded.fps,
            width = excluded.width,
            height = excluded.height,
            status = excluded.status,
            created_at = COALESCE(excluded.created_at, uploads.created_at),
            started_at = excluded.started_at,
            finished_at = excluded.finished_at,
            error_message = excluded.error_message,
            progress_percent = excluded.progress_percent,
            progress_stage = excluded.progress_stage,
            progress_message = excluded.progress_message,
            processed_frames = excluded.processed_frames,
            total_frames = excluded.total_frames
        """
        with self.connect() as connection:
            connection.execute(sql, payload)
            connection.commit()

    def delete_upload(self, upload_id: str) -> int:
        return self._execute("DELETE FROM uploads WHERE upload_id = ?", (upload_id,))

    # ------------------------------------------------------------------
    # Points CRUD
    # ------------------------------------------------------------------
    def insert_points(self, point_rows: list[dict[str, Any]]) -> None:
        if not point_rows:
            return
        sql = f"""
        INSERT INTO points ({", ".join(POINT_COLUMNS)})
        VALUES ({", ".join(f":{column}" for column in POINT_COLUMNS)})
        """
        payloads = [_normalize_columns(row, POINT_COLUMNS) for row in point_rows]
        with self.connect() as connection:
            connection.executemany(sql, payloads)
            connection.commit()

    def get_point(self, point_id: str) -> dict[str, Any] | None:
        return self._fetch_one("SELECT * FROM points WHERE point_id = ?", (point_id,))

    def get_points_by_upload(self, upload_id: str) -> list[dict[str, Any]]:
        return self._fetch_all(
            "SELECT * FROM points WHERE upload_id = ? ORDER BY point_index, point_id",
            (upload_id,),
        )

    def update_point(self, point_id: str, updates: dict[str, Any]) -> int:
        allowed = {column: updates[column] for column in POINT_COLUMNS if column in updates and column != "point_id"}
        if not allowed:
            return 0
        assignments = ", ".join(f"{column} = :{column}" for column in allowed)
        allowed["point_id"] = point_id
        sql = f"UPDATE points SET {assignments} WHERE point_id = :point_id"
        with self.connect() as connection:
            cursor = connection.execute(sql, allowed)
            connection.commit()
            return cursor.rowcount

    def delete_points_by_upload(self, upload_id: str) -> int:
        return self._execute("DELETE FROM points WHERE upload_id = ?", (upload_id,))

    # ------------------------------------------------------------------
    # Shots CRUD
    # ------------------------------------------------------------------
    def insert_shots(self, shot_rows: list[dict[str, Any]]) -> None:
        if not shot_rows:
            return
        sql = f"""
        INSERT INTO shots ({", ".join(SHOT_COLUMNS)})
        VALUES ({", ".join(f":{column}" for column in SHOT_COLUMNS)})
        """
        payloads = [_normalize_columns(row, SHOT_COLUMNS) for row in shot_rows]
        with self.connect() as connection:
            connection.executemany(sql, payloads)
            connection.commit()

    def get_shot(self, shot_id: str) -> dict[str, Any] | None:
        return self._fetch_one("SELECT * FROM shots WHERE shot_id = ?", (shot_id,))

    def get_shots_by_upload(self, upload_id: str) -> list[dict[str, Any]]:
        sql = """
        SELECT s.*
        FROM shots AS s
        JOIN points AS p ON p.point_id = s.point_id
        WHERE p.upload_id = ?
        ORDER BY p.point_index, s.shot_index, s.shot_id
        """
        return self._fetch_all(sql, (upload_id,))

    def update_shot(self, shot_id: str, updates: dict[str, Any]) -> int:
        allowed = {column: updates[column] for column in SHOT_COLUMNS if column in updates and column != "shot_id"}
        if not allowed:
            return 0
        assignments = ", ".join(f"{column} = :{column}" for column in allowed)
        allowed["shot_id"] = shot_id
        sql = f"UPDATE shots SET {assignments} WHERE shot_id = :shot_id"
        with self.connect() as connection:
            cursor = connection.execute(sql, allowed)
            connection.commit()
            return cursor.rowcount

    def delete_shots_by_upload(self, upload_id: str) -> int:
        sql = """
        DELETE FROM shots
        WHERE point_id IN (
            SELECT point_id FROM points WHERE upload_id = ?
        )
        """
        return self._execute(sql, (upload_id,))

    # ------------------------------------------------------------------
    # Bundle-level operations
    # ------------------------------------------------------------------
    def replace_analysis_rows(
        self,
        upload_id: str,
        point_rows: list[dict[str, Any]],
        shot_rows: list[dict[str, Any]],
    ) -> None:
        normalized_points = []
        for row in point_rows:
            point_payload = _normalize_columns(row, POINT_COLUMNS)
            point_payload["upload_id"] = upload_id
            normalized_points.append(point_payload)

        known_point_ids = {row["point_id"] for row in normalized_points}
        normalized_shots = []
        for row in shot_rows:
            shot_payload = _normalize_columns(row, SHOT_COLUMNS)
            if shot_payload.get("point_id") not in known_point_ids:
                raise ValueError(f"shot references unknown point_id: {shot_payload.get('point_id')}")
            normalized_shots.append(shot_payload)

        point_ids_sql = "SELECT point_id FROM points WHERE upload_id = ?"
        delete_shots_sql = f"DELETE FROM shots WHERE point_id IN ({point_ids_sql})"
        insert_points_sql = f"""
        INSERT INTO points ({", ".join(POINT_COLUMNS)})
        VALUES ({", ".join(f":{column}" for column in POINT_COLUMNS)})
        """
        insert_shots_sql = f"""
        INSERT INTO shots ({", ".join(SHOT_COLUMNS)})
        VALUES ({", ".join(f":{column}" for column in SHOT_COLUMNS)})
        """

        with self.connect() as connection:
            connection.execute(delete_shots_sql, (upload_id,))
            connection.execute("DELETE FROM points WHERE upload_id = ?", (upload_id,))
            if normalized_points:
                connection.executemany(insert_points_sql, normalized_points)
            if normalized_shots:
                connection.executemany(insert_shots_sql, normalized_shots)
            connection.commit()

    def save_upload_analysis_bundle(
        self,
        upload_row: dict[str, Any],
        points_payload: dict[str, Any] | str | Path,
        shots_payload: dict[str, Any] | str | Path,
        *,
        user_row: dict[str, Any] | None = None,
        ensure_schema: bool = True,
    ) -> dict[str, Any]:
        """Save one complete upload plus all point / shot results.

        Assumption for local testing:
        if the referenced user does not exist yet, a placeholder user row will
        be created automatically unless `user_row` is provided.
        """

        if ensure_schema:
            self.ensure_schema()

        upload_payload = _pick_columns(upload_row, UPLOAD_COLUMNS)
        required = ("upload_id", "user_id", "original_filename", "stored_path")
        missing = [column for column in required if not upload_payload.get(column)]
        if missing:
            raise ValueError(f"upload_row missing required fields: {missing}")

        points_data = _load_json_payload(points_payload)
        shots_data = _load_json_payload(shots_payload)
        point_rows = points_data.get("points", [])
        shot_rows = shots_data.get("shots", [])

        self.ensure_user_exists(upload_payload["user_id"], user_row=user_row)
        self.upsert_upload(upload_payload, ensure_user=False)
        self.replace_analysis_rows(upload_payload["upload_id"], point_rows, shot_rows)

        return self.get_upload_analysis_bundle(upload_payload["upload_id"])

    def get_upload_analysis_bundle(self, upload_id: str) -> dict[str, Any]:
        upload = self.get_upload(upload_id)
        if upload is None:
            raise ValueError(f"upload_id not found: {upload_id}")

        points = self.get_points_by_upload(upload_id)
        shots = self.get_shots_by_upload(upload_id)
        return {
            "upload": upload,
            "points": points,
            "shots": shots,
        }

    def delete_upload_analysis_bundle(self, upload_id: str) -> int:
        """Delete one upload and all dependent point / shot rows via cascade."""
        return self.delete_upload(upload_id)


__all__ = ["TennisAnalysisRepository"]
