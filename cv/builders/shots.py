"""Build shot-level JSON outputs from imputed frame data.

This script is a test-stage shot extraction pipeline for the current
`run_inference.py` outputs. It uses:
- `match_frames_imputed.json` as the primary per-frame source
- `points_heuristic_v2_index.json` as the point segmentation source
- `match_tactics.json` only for the net-hit events

It writes:
1. an intermediate JSON with point-level event grouping and per-shot linkage
2. a final JSON containing rows shaped to match the `shots` table fields
"""

from __future__ import annotations

import argparse
import json
import math
import re
from collections import Counter
from copy import deepcopy
from pathlib import Path
from typing import Any


from cv.config import OUTPUT_DIR as VIDEO_OUTPUT_DIR
DEFAULT_FRAMES_PATH = VIDEO_OUTPUT_DIR / "match_frames_imputed.json"
DEFAULT_POINTS_PATH = VIDEO_OUTPUT_DIR / "points_heuristic_v2_index.json"
DEFAULT_TACTICS_PATH = VIDEO_OUTPUT_DIR / "match_tactics.json"
DEFAULT_INTERMEDIATE_PATH = VIDEO_OUTPUT_DIR / "shots_build_intermediate.json"
DEFAULT_OUTPUT_PATH = VIDEO_OUTPUT_DIR / "shots_from_test_data.json"
DEFAULT_POINTS_OUTPUT_PATH = VIDEO_OUTPUT_DIR / "points_from_test_data.json"

COURT_WIDTH_M = 10.97
COURT_LENGTH_M = 23.77
HALF_COURT_M = COURT_LENGTH_M / 2.0
CENTER_X_M = COURT_WIDTH_M / 2.0


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, data: dict[str, Any], *, pretty: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        if pretty:
            json.dump(data, handle, ensure_ascii=False, indent=4)
        else:
            json.dump(data, handle, ensure_ascii=False, separators=(",", ":"))


def is_valid_pair(value: Any) -> bool:
    return (
        isinstance(value, list)
        and len(value) == 2
        and all(isinstance(item, (int, float)) for item in value)
    )


def map_player_to_side(player_id: int | None) -> str | None:
    if player_id == 1:
        return "A"
    if player_id == 2:
        return "B"
    return None


def map_side_to_player(side: str | None) -> int | None:
    if side == "A":
        return 1
    if side == "B":
        return 2
    return None


def round_or_none(value: float | None, digits: int = 2) -> float | None:
    if value is None or not math.isfinite(value):
        return None
    return round(float(value), digits)


def safe_pair_to_xy(value: list[float] | None) -> tuple[float | None, float | None]:
    if not is_valid_pair(value):
        return None, None
    return round_or_none(value[0]), round_or_none(value[1])


def get_players_by_id(frame: dict[str, Any]) -> dict[int, dict[str, Any]]:
    return {player["id"]: player for player in frame.get("players", []) if isinstance(player, dict) and "id" in player}


def get_player_court(frame: dict[str, Any], player_id: int | None) -> list[float] | None:
    if player_id is None:
        return None
    player = get_players_by_id(frame).get(player_id)
    if not player:
        return None
    feet_court = player.get("feet_court")
    return feet_court if is_valid_pair(feet_court) else None


def get_ball_court(frame: dict[str, Any]) -> list[float] | None:
    ball = frame.get("ball")
    if not isinstance(ball, dict):
        return None
    value = ball.get("court")
    return value if is_valid_pair(value) else None


def find_nearest_player_position(
    frames_by_index: dict[int, dict[str, Any]],
    player_id: int | None,
    target_frame: int | None,
    point_start: int,
    point_end: int,
    search_radius: int = 6,
) -> list[float] | None:
    if player_id is None or target_frame is None:
        return None

    for offset in range(0, search_radius + 1):
        candidates = [target_frame] if offset == 0 else [target_frame - offset, target_frame + offset]
        for frame_index in candidates:
            if frame_index < point_start or frame_index > point_end:
                continue
            frame = frames_by_index.get(frame_index)
            if not frame:
                continue
            position = get_player_court(frame, player_id)
            if is_valid_pair(position):
                return position
    return None


def find_ball_court_at_frame(
    frames_by_index: dict[int, dict[str, Any]],
    target_frame: int | None,
    point_start: int,
    point_end: int,
    search_radius: int = 4,
) -> list[float] | None:
    if target_frame is None:
        return None

    for offset in range(0, search_radius + 1):
        candidates = [target_frame] if offset == 0 else [target_frame - offset, target_frame + offset]
        for frame_index in candidates:
            if frame_index < point_start or frame_index > point_end:
                continue
            frame = frames_by_index.get(frame_index)
            if not frame:
                continue
            position = get_ball_court(frame)
            if is_valid_pair(position):
                return position
    return None


def euclidean_distance(a: list[float] | None, b: list[float] | None) -> float | None:
    if not is_valid_pair(a) or not is_valid_pair(b):
        return None
    return math.hypot(a[0] - b[0], a[1] - b[1])


def infer_stroke_type(raw_shot_type: str | None) -> str:
    if raw_shot_type == "Serve":
        return "serve"
    if raw_shot_type == "Smash":
        return "smash"
    if raw_shot_type == "Volley":
        return "volley"
    if raw_shot_type in {"Forehand", "Backhand"}:
        return "groundstroke"
    return "unknown"


def infer_stroke_side(raw_shot_type: str | None) -> str:
    if raw_shot_type == "Forehand":
        return "forehand"
    if raw_shot_type == "Backhand":
        return "backhand"
    return "unknown"


def infer_shot_phase(point_shots: list[dict[str, Any]], shot_index_zero_based: int) -> str | None:
    raw_shot_type = point_shots[shot_index_zero_based]["raw_shot_type"]
    if shot_index_zero_based == 0 and raw_shot_type == "Serve":
        return "serve"
    if shot_index_zero_based == 1 and point_shots and point_shots[0]["raw_shot_type"] == "Serve":
        if point_shots[1].get("hitter_id") == point_shots[0].get("hitter_id"):
            return "serve"
        return "return"
    if (
        shot_index_zero_based == 2
        and len(point_shots) > 2
        and point_shots[0]["raw_shot_type"] == "Serve"
        and point_shots[1].get("hitter_id") == point_shots[0].get("hitter_id")
        and point_shots[2].get("hitter_id") != point_shots[1].get("hitter_id")
    ):
        return "return"
    return "rally"


def infer_serve_number(point_shots: list[dict[str, Any]], shot_index_zero_based: int) -> str | None:
    if shot_index_zero_based == 0 and point_shots and point_shots[0].get("raw_shot_type") == "Serve":
        return "first"
    if (
        shot_index_zero_based == 1
        and len(point_shots) > 1
        and point_shots[0].get("raw_shot_type") == "Serve"
        and point_shots[1].get("hitter_id") == point_shots[0].get("hitter_id")
    ):
        return "second"
    return None


def classify_target_half(hitter_side: str | None) -> str | None:
    if hitter_side == "A":
        return "top"
    if hitter_side == "B":
        return "bottom"
    return None


def classify_hitter_own_half(hitter_side: str | None) -> str | None:
    if hitter_side == "A":
        return "bottom"
    if hitter_side == "B":
        return "top"
    return None


def infer_depth_zone(target_y: float | None, target_half: str | None) -> str | None:
    if target_y is None or target_half is None:
        return None

    if target_half == "top":
        depth_from_baseline = target_y
    else:
        depth_from_baseline = COURT_LENGTH_M - target_y

    if depth_from_baseline < 0 or depth_from_baseline > COURT_LENGTH_M:
        return None
    if depth_from_baseline <= 4.0:
        return "deep"
    if depth_from_baseline <= 8.0:
        return "medium"
    return "short"


def infer_width_zone(target_x: float | None, opponent_x: float | None) -> str | None:
    if target_x is None:
        return None

    if opponent_x is not None:
        delta = abs(target_x - opponent_x)
        if delta <= 0.8:
            return "body"
        if delta >= 2.5:
            return "wide"
        return "middle"

    if abs(target_x - CENTER_X_M) <= 1.1:
        return "middle"
    return "wide"


def classify_lateral_side(x_value: float | None) -> str | None:
    if x_value is None:
        return None
    if abs(x_value - CENTER_X_M) <= 0.8:
        return "center"
    return "left" if x_value < CENTER_X_M else "right"


def infer_direction(contact_x: float | None, target_x: float | None) -> str | None:
    if target_x is None:
        return None
    target_side = classify_lateral_side(target_x)
    if target_side == "center":
        return "middle"

    contact_side = classify_lateral_side(contact_x)
    if contact_side is None or contact_side == "center":
        return "middle"
    if contact_side != target_side:
        return "crosscourt"
    return "down_the_line"


def infer_fault_type(
    trajectory_end_type: str | None,
    target_x: float | None,
    target_y: float | None,
    hitter_side: str | None,
) -> str | None:
    if trajectory_end_type == "net":
        return "net"
    if trajectory_end_type != "bounce_out":
        return None
    if target_x is None or target_y is None or hitter_side is None:
        return "unknown"

    target_half = classify_target_half(hitter_side)
    if target_x < 0 or target_x > COURT_WIDTH_M:
        return "wide"

    if target_half == "top" and target_y < 0:
        return "long"
    if target_half == "top" and target_y > HALF_COURT_M:
        return "long"
    if target_half == "bottom" and target_y > COURT_LENGTH_M:
        return "long"
    if target_half == "bottom" and target_y < HALF_COURT_M:
        return "long"
    return "unknown"


def is_bounce_on_half(y_value: float | None, half_name: str | None) -> bool:
    if y_value is None or half_name is None:
        return False
    if half_name == "top":
        return y_value < HALF_COURT_M
    if half_name == "bottom":
        return y_value >= HALF_COURT_M
    return False


def slugify_upload_id(source_video: str | None) -> str:
    base = Path(source_video).stem if source_video else "test_upload"
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", base).strip("_").lower()
    return slug or "test_upload"


def compute_speed_kmh(
    start_frame: int,
    end_frame: int | None,
    start_court: list[float] | None,
    end_court: list[float] | None,
    fps: float,
) -> float | None:
    if end_frame is None or end_frame <= start_frame or fps <= 0:
        return None
    distance_m = euclidean_distance(start_court, end_court)
    if distance_m is None:
        return None
    duration_sec = (end_frame - start_frame) / fps
    if duration_sec <= 0:
        return None
    return round_or_none(distance_m / duration_sec * 3.6, 2)


def point_id_from_segment(segment_id: int, upload_id: str | None = None) -> str:
    prefix = f"{upload_id}_" if upload_id else ""
    return f"{prefix}point_{segment_id:03d}"


def shot_id_from_parts(point_id: str, shot_index: int) -> str:
    return f"{point_id}_shot_{shot_index:03d}"


def build_points_and_events(
    frames: list[dict[str, Any]],
    segments: list[dict[str, Any]],
    net_hits: list[dict[str, Any]],
    upload_id: str | None = None,
) -> tuple[list[dict[str, Any]], dict[int, dict[str, Any]]]:
    frames_by_index = {frame["frame_index"]: frame for frame in frames}
    points: list[dict[str, Any]] = []

    for segment in segments:
        point_id = point_id_from_segment(segment["segment_id"], upload_id)
        start_frame = segment["start_frame"]
        end_frame = segment["end_frame"]

        hit_frames = [
            frames_by_index[frame_index]
            for frame_index in range(start_frame, end_frame + 1)
            if frame_index in frames_by_index and frames_by_index[frame_index]["events"].get("is_hit")
        ]
        bounce_frames = [
            frames_by_index[frame_index]
            for frame_index in range(start_frame, end_frame + 1)
            if frame_index in frames_by_index and frames_by_index[frame_index]["events"].get("is_bounce")
        ]
        point_net_hits = [event for event in net_hits if start_frame <= event["frame"] <= end_frame]

        point_payload = {
            "point_id": point_id,
            "segment_id": segment["segment_id"],
            "start_frame": start_frame,
            "end_frame": end_frame,
            "start_time_sec": segment["start_time_sec"],
            "end_time_sec": segment["end_time_sec"],
            "duration_sec": segment["duration_sec"],
            "hit_frames": [frame["frame_index"] for frame in hit_frames],
            "bounce_frames": [frame["frame_index"] for frame in bounce_frames],
            "net_hit_frames": [event["frame"] for event in point_net_hits],
            "reported_hit_count": segment.get("hit_count"),
            "actual_hit_count": len(hit_frames),
        }
        points.append(point_payload)

    return points, frames_by_index


def build_raw_shots_for_point(
    point_info: dict[str, Any],
    frames_by_index: dict[int, dict[str, Any]],
    net_hits: list[dict[str, Any]],
    fps: float,
) -> list[dict[str, Any]]:
    start_frame = point_info["start_frame"]
    end_frame = point_info["end_frame"]
    hit_frames = point_info["hit_frames"]
    point_net_hits = [event for event in net_hits if start_frame <= event["frame"] <= end_frame]

    raw_shots: list[dict[str, Any]] = []
    for shot_index_zero_based, frame_index in enumerate(hit_frames):
        frame = frames_by_index[frame_index]
        hitter_player_id = frame["events"].get("hitter_id")
        hitter_side = map_player_to_side(hitter_player_id)
        opponent_player_id = 2 if hitter_player_id == 1 else 1 if hitter_player_id == 2 else None
        opponent_side = map_player_to_side(opponent_player_id)

        ball_court = get_ball_court(frame)
        hitter_court = get_player_court(frame, hitter_player_id)
        opponent_court = get_player_court(frame, opponent_player_id)

        raw_shots.append(
            {
                "point_id": point_info["point_id"],
                "segment_id": point_info["segment_id"],
                "shot_index": shot_index_zero_based + 1,
                "shot_id": shot_id_from_parts(point_info["point_id"], shot_index_zero_based + 1),
                "contact_frame": frame_index,
                "contact_time": round_or_none(frame["time_sec"], 3),
                "hitter_player_id": hitter_player_id,
                "hitter_id": hitter_side,
                "opponent_player_id": opponent_player_id,
                "opponent_id": opponent_side,
                "raw_shot_type": frame["events"].get("shot_type"),
                "contact_court": ball_court,
                "hitter_court": hitter_court,
                "opponent_contact_court": opponent_court,
                "point_start_frame": start_frame,
                "point_end_frame": end_frame,
                "point_net_hits": deepcopy(point_net_hits),
            }
        )
    return raw_shots


def link_shot_context(
    point_shots: list[dict[str, Any]],
    point_info: dict[str, Any],
    frames_by_index: dict[int, dict[str, Any]],
    net_hits: list[dict[str, Any]],
    fps: float,
) -> list[dict[str, Any]]:
    point_start = point_info["start_frame"]
    point_end = point_info["end_frame"]
    bounce_frames = point_info["bounce_frames"]
    point_net_hits = [event for event in net_hits if point_start <= event["frame"] <= point_end]

    linked: list[dict[str, Any]] = deepcopy(point_shots)
    for idx, shot in enumerate(linked):
        current_frame = shot["contact_frame"]
        next_shot = linked[idx + 1] if idx + 1 < len(linked) else None
        next_shot_frame = next_shot["contact_frame"] if next_shot else None

        prev_shot = linked[idx - 1] if idx > 0 else None
        prev_shot_frame = prev_shot["contact_frame"] if prev_shot else point_start - 1

        candidate_bounces = [frame for frame in bounce_frames if current_frame < frame < (next_shot_frame or point_end + 1)]
        first_bounce_frame = candidate_bounces[0] if candidate_bounces else None
        first_bounce_frame_data = frames_by_index.get(first_bounce_frame) if first_bounce_frame is not None else None
        first_bounce_court = None
        if first_bounce_frame_data:
            bounce_court = first_bounce_frame_data["events"].get("bounce_court")
            first_bounce_court = bounce_court if is_valid_pair(bounce_court) else None

        candidate_net_hits = [
            event for event in point_net_hits if current_frame < event["frame"] < (next_shot_frame or point_end + 1)
        ]
        first_net_hit = candidate_net_hits[0] if candidate_net_hits else None
        net_court = None
        if first_net_hit:
            net_court = find_ball_court_at_frame(frames_by_index, first_net_hit["frame"], point_start, point_end)

        opponent_next_hit = next(
            (
                future_shot
                for future_shot in linked[idx + 1 :]
                if future_shot.get("hitter_player_id") is not None
                and future_shot.get("hitter_player_id") != shot.get("hitter_player_id")
            ),
            None,
        )

        bounce_count_before_hit = sum(prev_shot_frame < frame < current_frame for frame in bounce_frames)
        shot_phase = infer_shot_phase(linked, idx)
        serve_number = infer_serve_number(linked, idx)

        if first_net_hit and (first_bounce_frame is None or first_net_hit["frame"] <= first_bounce_frame):
            trajectory_end_type = "net"
            trajectory_end_frame = first_net_hit["frame"]
            trajectory_target_court = net_court
        elif first_bounce_frame is not None:
            bounce_type = first_bounce_frame_data["events"].get("bounce_type")
            trajectory_end_type = "bounce_in" if bounce_type == "in" else "bounce_out"
            trajectory_end_frame = first_bounce_frame
            trajectory_target_court = first_bounce_court
        elif opponent_next_hit is not None:
            trajectory_end_type = "opponent_hit"
            trajectory_end_frame = opponent_next_hit["contact_frame"]
            trajectory_target_court = opponent_next_hit.get("contact_court")
        elif next_shot is not None:
            trajectory_end_type = "lost"
            trajectory_end_frame = next_shot["contact_frame"]
            trajectory_target_court = next_shot.get("contact_court")
        else:
            trajectory_end_type = "unknown"
            trajectory_end_frame = None
            trajectory_target_court = None

        outgoing_speed_kmh = compute_speed_kmh(
            shot["contact_frame"],
            trajectory_end_frame,
            shot.get("contact_court"),
            trajectory_target_court,
            fps,
        )
        incoming_speed_kmh = prev_shot.get("outgoing_speed_kmh") if prev_shot else None

        target_court_for_direction = first_bounce_court or trajectory_target_court
        target_x = target_court_for_direction[0] if is_valid_pair(target_court_for_direction) else None
        target_y = target_court_for_direction[1] if is_valid_pair(target_court_for_direction) else None

        opponent_at_bounce = find_nearest_player_position(
            frames_by_index,
            shot.get("opponent_player_id"),
            first_bounce_frame,
            point_start,
            point_end,
        )
        opponent_at_next_hit = (
            find_nearest_player_position(
                frames_by_index,
                shot.get("opponent_player_id"),
                opponent_next_hit["contact_frame"],
                point_start,
                point_end,
            )
            if opponent_next_hit
            else None
        )

        shot["prev_shot_frame"] = prev_shot["contact_frame"] if prev_shot else None
        shot["next_shot_frame"] = next_shot_frame
        shot["opponent_next_hit_frame"] = opponent_next_hit["contact_frame"] if opponent_next_hit else None
        shot["first_bounce_frame"] = first_bounce_frame
        shot["first_bounce_time"] = round_or_none(first_bounce_frame / fps, 3) if first_bounce_frame is not None else None
        shot["first_bounce_court"] = first_bounce_court
        shot["first_net_hit"] = deepcopy(first_net_hit)
        shot["net_court"] = net_court
        shot["trajectory_end_type"] = trajectory_end_type
        shot["trajectory_end_frame"] = trajectory_end_frame
        shot["trajectory_target_court"] = trajectory_target_court
        shot["shot_phase"] = shot_phase
        shot["serve_number"] = serve_number
        shot["stroke_type"] = "serve" if shot_phase == "serve" else infer_stroke_type(shot.get("raw_shot_type"))
        shot["stroke_side"] = "unknown" if shot_phase == "serve" else infer_stroke_side(shot.get("raw_shot_type"))
        shot["bounce_count_before_hit"] = bounce_count_before_hit
        shot["outgoing_speed_kmh"] = outgoing_speed_kmh
        shot["incoming_speed_kmh"] = incoming_speed_kmh
        shot["opponent_at_bounce_court"] = opponent_at_bounce
        shot["opponent_at_next_hit_court"] = opponent_at_next_hit
        shot["direction"] = infer_direction(
            shot["contact_court"][0] if is_valid_pair(shot.get("contact_court")) else None,
            target_x,
        )
        shot["depth_zone"] = infer_depth_zone(target_y, classify_target_half(shot.get("hitter_id")))
        shot["width_zone"] = infer_width_zone(
            target_x,
            opponent_at_bounce[0] if is_valid_pair(opponent_at_bounce) else None,
        )
        shot["fault_type"] = infer_fault_type(
            trajectory_end_type,
            target_x,
            target_y,
            shot.get("hitter_id"),
        )

        if shot_phase == "serve" and trajectory_end_type in {"bounce_out", "net"}:
            shot["legality"] = "fault"
        elif trajectory_end_type == "net":
            shot["legality"] = "net"
        elif trajectory_end_type == "bounce_out":
            shot["legality"] = "out"
        elif trajectory_end_type in {"bounce_in", "opponent_hit"}:
            shot["legality"] = "in"
        else:
            shot["legality"] = "unknown"

        shot["shot_outcome"] = "continue"
        shot["point_ending"] = 0
        shot["point_winner"] = None
        shot["ending_reason"] = None
        shot["error_forcedness"] = "unknown"

        if shot["shot_phase"] == "serve" and shot["legality"] == "fault":
            shot["shot_outcome"] = "fault"

    if linked:
        final_shot = linked[-1]
        final_shot["point_ending"] = 1
        final_shot["shot_outcome"] = final_shot.get("shot_outcome") or "unknown"
        final_shot["error_forcedness"] = "unknown"

    return linked


def build_point_row(
    point_info: dict[str, Any],
    linked_shots: list[dict[str, Any]],
    upload_id: str,
) -> dict[str, Any]:
    point_index = point_info["segment_id"]
    point_id = point_info["point_id"]
    start_frame = point_info["start_frame"]
    end_frame = point_info["end_frame"]

    first_shot = linked_shots[0] if linked_shots else None
    final_shot = linked_shots[-1] if linked_shots else None

    explicit_server = next((shot.get("hitter_id") for shot in linked_shots if shot.get("shot_phase") == "serve"), None)
    server_id = explicit_server or (first_shot.get("hitter_id") if first_shot else None)
    receiver_id = "B" if server_id == "A" else "A" if server_id == "B" else None

    serve_shots = [shot for shot in linked_shots if shot.get("shot_phase") == "serve"]
    serve_count = len(serve_shots) if serve_shots else None
    first_serve_in = None
    second_serve_in = None
    if serve_count and serve_shots:
        first_serve_in = 0 if serve_shots[0].get("legality") == "fault" else 1
    if serve_count and serve_count >= 2:
        second_serve_in = 0 if serve_shots[1].get("legality") == "fault" else 1

    a_shot_count = sum(1 for shot in linked_shots if shot.get("hitter_id") == "A")
    b_shot_count = sum(1 for shot in linked_shots if shot.get("hitter_id") == "B")

    winner_id = None
    loser_id = None
    point_won_by_server = None
    ending_type = "unknown"
    ending_reason = None

    if final_shot:
        hitter_id = final_shot.get("hitter_id")
        opponent_id = "B" if hitter_id == "A" else "A" if hitter_id == "B" else None
        shot_phase = final_shot.get("shot_phase")
        serve_number = final_shot.get("serve_number")
        first_bounce_y = final_shot.get("first_bounce_y")
        target_half = classify_target_half(hitter_id)
        own_half = classify_hitter_own_half(hitter_id)
        end_type = final_shot.get("trajectory_end_type")

        if end_type == "net":
            winner_id = opponent_id
            loser_id = hitter_id
            ending_type = "fault" if shot_phase == "serve" else "error"
            if shot_phase == "serve" and serve_number == "second":
                ending_reason = "double_fault"
            else:
                ending_reason = "net"
            final_shot["legality"] = "fault" if shot_phase == "serve" else "net"
            final_shot["fault_type"] = "net"
            final_shot["shot_outcome"] = "fault" if shot_phase == "serve" else "error"
        elif end_type == "bounce_out":
            winner_id = opponent_id
            loser_id = hitter_id
            ending_type = "fault" if shot_phase == "serve" else "error"
            if shot_phase == "serve" and serve_number == "second":
                ending_reason = "double_fault"
            else:
                ending_reason = "out"
            final_shot["legality"] = "fault" if shot_phase == "serve" else "out"
            final_shot["shot_outcome"] = "fault" if shot_phase == "serve" else "error"
        elif end_type == "bounce_in":
            if is_bounce_on_half(first_bounce_y, own_half):
                winner_id = opponent_id
                loser_id = hitter_id
                ending_type = "fault" if shot_phase == "serve" else "error"
                if shot_phase == "serve" and serve_number == "second":
                    ending_reason = "double_fault"
                else:
                    ending_reason = "out"
                final_shot["legality"] = "fault" if shot_phase == "serve" else "out"
                final_shot["shot_outcome"] = "fault" if shot_phase == "serve" else "error"
            elif is_bounce_on_half(first_bounce_y, target_half):
                winner_id = hitter_id
                loser_id = opponent_id
                ending_type = "winner"
                ending_reason = "ace" if shot_phase == "serve" else "winner"
                final_shot["legality"] = "in"
                final_shot["shot_outcome"] = "winner"
            else:
                winner_id = opponent_id
                loser_id = hitter_id
                ending_type = "fault" if shot_phase == "serve" else "error"
                ending_reason = "out"
                final_shot["legality"] = "fault" if shot_phase == "serve" else "out"
                final_shot["shot_outcome"] = "fault" if shot_phase == "serve" else "error"
        else:
            winner_id = opponent_id
            loser_id = hitter_id
            ending_type = "fault" if shot_phase == "serve" else "error"
            if shot_phase == "serve" and serve_number == "second":
                ending_reason = "double_fault"
            else:
                ending_reason = "out"
            final_shot["trajectory_end_type"] = "lost"
            final_shot["legality"] = "fault" if shot_phase == "serve" else "out"
            final_shot["fault_type"] = final_shot.get("fault_type") or "unknown"
            final_shot["shot_outcome"] = "fault" if shot_phase == "serve" else "error"

        final_shot["point_ending"] = 1
        final_shot["point_winner"] = winner_id
        final_shot["ending_reason"] = ending_reason
        final_shot["error_forcedness"] = "unknown"

        if server_id is not None and winner_id is not None:
            point_won_by_server = 1 if winner_id == server_id else 0

    return {
        "point_id": point_id,
        "upload_id": upload_id,
        "point_index": point_index,
        "start_frame": start_frame,
        "end_frame": end_frame,
        "start_time": point_info["start_time_sec"],
        "end_time": point_info["end_time_sec"],
        "duration_sec": point_info["duration_sec"],
        "server_id": server_id,
        "receiver_id": receiver_id,
        "serve_count": serve_count,
        "first_serve_in": first_serve_in,
        "second_serve_in": second_serve_in,
        "rally_shot_count": len(linked_shots),
        "winner_id": winner_id,
        "loser_id": loser_id,
        "point_won_by_server": point_won_by_server,
        "ending_shot_id": final_shot.get("shot_id") if final_shot else None,
        "ending_hitter_id": final_shot.get("hitter_id") if final_shot else None,
        "ending_type": ending_type,
        "ending_reason": ending_reason,
        "a_shot_count": a_shot_count,
        "b_shot_count": b_shot_count,
    }


def convert_linked_shot_to_final_row(shot: dict[str, Any]) -> dict[str, Any]:
    contact_x, contact_y = safe_pair_to_xy(shot.get("contact_court"))
    hitter_x, hitter_y = safe_pair_to_xy(shot.get("hitter_court"))
    opp_contact_x, opp_contact_y = safe_pair_to_xy(shot.get("opponent_contact_court"))
    opp_bounce_x, opp_bounce_y = safe_pair_to_xy(shot.get("opponent_at_bounce_court"))
    opp_next_hit_x, opp_next_hit_y = safe_pair_to_xy(shot.get("opponent_at_next_hit_court"))
    bounce_x, bounce_y = safe_pair_to_xy(shot.get("first_bounce_court"))

    return {
        "shot_id": shot.get("shot_id"),
        "point_id": shot.get("point_id"),
        "shot_index": shot.get("shot_index"),
        "hitter_id": shot.get("hitter_id"),
        "contact_frame": shot.get("contact_frame"),
        "contact_time": shot.get("contact_time"),
        "contact_x": contact_x,
        "contact_y": contact_y,
        "hitter_x": hitter_x,
        "hitter_y": hitter_y,
        "opponent_at_contact_x": opp_contact_x,
        "opponent_at_contact_y": opp_contact_y,
        "opponent_at_bounce_x": opp_bounce_x,
        "opponent_at_bounce_y": opp_bounce_y,
        "opponent_at_next_hit_x": opp_next_hit_x,
        "opponent_at_next_hit_y": opp_next_hit_y,
        "shot_phase": shot.get("shot_phase"),
        "serve_number": shot.get("serve_number"),
        "stroke_type": shot.get("stroke_type"),
        "stroke_side": shot.get("stroke_side"),
        "bounce_count_before_hit": shot.get("bounce_count_before_hit"),
        "incoming_speed_kmh": shot.get("incoming_speed_kmh"),
        "outgoing_speed_kmh": shot.get("outgoing_speed_kmh"),
        "first_bounce_frame": shot.get("first_bounce_frame"),
        "first_bounce_time": shot.get("first_bounce_time"),
        "first_bounce_x": bounce_x,
        "first_bounce_y": bounce_y,
        "trajectory_end_type": shot.get("trajectory_end_type"),
        "direction": shot.get("direction"),
        "depth_zone": shot.get("depth_zone"),
        "width_zone": shot.get("width_zone"),
        "legality": shot.get("legality"),
        "fault_type": shot.get("fault_type"),
        "shot_outcome": shot.get("shot_outcome"),
        "error_forcedness": shot.get("error_forcedness"),
        "point_ending": shot.get("point_ending", 0),
        "point_winner": shot.get("point_winner"),
        "ending_reason": shot.get("ending_reason"),
    }


def build_outputs(
    frames_path: Path,
    points_path: Path,
    tactics_path: Path,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    frames_data = load_json(frames_path)
    points_data = load_json(points_path)
    tactics_data = load_json(tactics_path)

    frames = frames_data["frames"]
    fps = float(frames_data["metadata"]["fps"])
    segments = points_data["segments"]
    net_hits = tactics_data.get("net_hits", [])
    upload_id = slugify_upload_id(points_data.get("source_video"))

    points_summary, frames_by_index = build_points_and_events(frames, segments, net_hits, upload_id)
    raw_shots_by_point: list[dict[str, Any]] = []
    linked_shots_by_point: list[dict[str, Any]] = []
    point_rows: list[dict[str, Any]] = []
    final_rows: list[dict[str, Any]] = []

    for point_info in points_summary:
        raw_shots = build_raw_shots_for_point(point_info, frames_by_index, net_hits, fps)
        linked_shots = link_shot_context(raw_shots, point_info, frames_by_index, net_hits, fps)
        point_row = build_point_row(point_info, linked_shots, upload_id)
        raw_shots_by_point.append({"point_id": point_info["point_id"], "shots": raw_shots})
        linked_shots_by_point.append({"point_id": point_info["point_id"], "shots": linked_shots})
        point_rows.append(point_row)
        final_rows.extend(convert_linked_shot_to_final_row(shot) for shot in linked_shots)

    summary = Counter()
    for row in final_rows:
        summary["shot_count"] += 1
        if row.get("point_ending"):
            summary["point_ending_shots"] += 1
        if row.get("trajectory_end_type") == "net":
            summary["net_endings"] += 1
        if row.get("first_bounce_frame") is not None:
            summary["shots_with_bounce"] += 1
        if row.get("legality") == "fault":
            summary["faults"] += 1

    intermediate = {
        "metadata": {
            "source_frames": str(frames_path),
            "source_points": str(points_path),
            "source_tactics": str(tactics_path),
            "fps": fps,
            "player_mapping": {"A": 1, "B": 2},
            "point_count": len(points_summary),
            "shot_count": len(final_rows),
            "upload_id": upload_id,
        },
        "points": points_summary,
        "point_rows": point_rows,
        "raw_shots_by_point": raw_shots_by_point,
        "linked_shots_by_point": linked_shots_by_point,
        "summary": dict(summary),
    }

    final_output = {
        "metadata": {
            "source_frames": str(frames_path),
            "source_points": str(points_path),
            "source_tactics": str(tactics_path),
            "fps": fps,
            "player_mapping": {"A": 1, "B": 2},
            "shot_count": len(final_rows),
            "upload_id": upload_id,
        },
        "shots": final_rows,
    }

    points_output = {
        "metadata": {
            "source_frames": str(frames_path),
            "source_points": str(points_path),
            "source_tactics": str(tactics_path),
            "fps": fps,
            "upload_id": upload_id,
            "point_count": len(point_rows),
        },
        "points": point_rows,
    }
    return intermediate, final_output, points_output


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build shot-level JSON from test-stage tennis CV outputs.")
    parser.add_argument("--frames", type=Path, default=DEFAULT_FRAMES_PATH, help="Path to match_frames_imputed.json.")
    parser.add_argument("--points", type=Path, default=DEFAULT_POINTS_PATH, help="Path to points_heuristic_v2_index.json.")
    parser.add_argument("--tactics", type=Path, default=DEFAULT_TACTICS_PATH, help="Path to match_tactics.json.")
    parser.add_argument(
        "--intermediate-output",
        type=Path,
        default=DEFAULT_INTERMEDIATE_PATH,
        help="Path to write the intermediate build JSON.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_PATH,
        help="Path to write the final shot rows JSON.",
    )
    parser.add_argument(
        "--points-output",
        type=Path,
        default=DEFAULT_POINTS_OUTPUT_PATH,
        help="Path to write the final point rows JSON.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    intermediate, final_output, points_output = build_outputs(args.frames, args.points, args.tactics)
    save_json(args.intermediate_output, intermediate, pretty=True)
    save_json(args.output, final_output, pretty=True)
    save_json(args.points_output, points_output, pretty=True)

    print(f"Intermediate JSON written to: {args.intermediate_output}")
    print(f"Final shots JSON written to: {args.output}")
    print(f"Final points JSON written to: {args.points_output}")
    print(json.dumps(intermediate["summary"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
