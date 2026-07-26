"""Event-safe trajectory optimization for stable TrackNet/GridTrackNet output.

Observed detector coordinates are authoritative. This experiment does not use
RANSAC and never deletes an observed point. It only replaces a point when
independent left/right robust local models agree that it is an isolated spike.
Trajectory discontinuities are retained as event boundaries.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


@dataclass(frozen=True)
class GuardedTrajectoryConfig:
    context_half: int = 5
    min_side_points: int = 3
    max_fill_gap: int = 2
    base_threshold_px: float = 12.0
    far_threshold_scale: float = 0.65
    near_threshold_scale: float = 2.30
    consensus_scale: float = 1.5
    spike_scale: float = 2.5
    event_angle_deg: float = 25.0
    event_speed_ratio: float = 1.8
    min_event_speed_px: float = 1.0


@dataclass(frozen=True)
class SideModel:
    prediction: np.ndarray
    velocity: np.ndarray
    support_frames: tuple[int, ...]


def as_point(value: Any) -> np.ndarray | None:
    if not isinstance(value, (list, tuple, np.ndarray)) or len(value) < 2:
        return None
    try:
        point = np.asarray([float(value[0]), float(value[1])], dtype=np.float64)
    except (TypeError, ValueError):
        return None
    return point if np.all(np.isfinite(point)) else None


def json_point(point: np.ndarray | None) -> list[float] | None:
    if point is None or not np.all(np.isfinite(point)):
        return None
    return [round(float(point[0]), 3), round(float(point[1]), 3)]


def dynamic_threshold(point_y: float, frame_height: int, config: GuardedTrajectoryConfig) -> float:
    if frame_height <= 0 or not np.isfinite(point_y):
        return float(config.base_threshold_px)
    ratio = float(np.clip(point_y / frame_height, 0.0, 1.0))
    scale = config.far_threshold_scale + ratio * (config.near_threshold_scale - config.far_threshold_scale)
    return float(config.base_threshold_px * scale)


def robust_side_model(
    coords: list[np.ndarray | None],
    target_index: int,
    *,
    direction: int,
    config: GuardedTrajectoryConfig,
) -> SideModel | None:
    if direction not in (-1, 1):
        raise ValueError("direction must be -1 or 1")
    start = max(0, target_index - config.context_half)
    end = min(len(coords), target_index + config.context_half + 1)
    indices = [
        index
        for index in range(start, end)
        if index != target_index and (index < target_index if direction < 0 else index > target_index)
        and coords[index] is not None
    ]
    if len(indices) < config.min_side_points:
        return None

    slopes = []
    for left_pos, left_index in enumerate(indices[:-1]):
        for right_index in indices[left_pos + 1 :]:
            delta_t = right_index - left_index
            if delta_t <= 0:
                continue
            slopes.append((coords[right_index] - coords[left_index]) / delta_t)
    if not slopes:
        return None
    velocity = np.median(np.asarray(slopes, dtype=np.float64), axis=0)
    intercepts = np.asarray(
        [coords[index] - velocity * index for index in indices],
        dtype=np.float64,
    )
    intercept = np.median(intercepts, axis=0)
    prediction = intercept + velocity * target_index
    if not np.all(np.isfinite(prediction)) or not np.all(np.isfinite(velocity)):
        return None
    return SideModel(prediction=prediction, velocity=velocity, support_frames=tuple(indices))


def velocity_metrics(left: SideModel | None, right: SideModel | None) -> tuple[float | None, float | None]:
    if left is None or right is None:
        return None, None
    left_speed = float(np.linalg.norm(left.velocity))
    right_speed = float(np.linalg.norm(right.velocity))
    if left_speed <= 1e-9 or right_speed <= 1e-9:
        return None, None
    cosine = float(np.clip(np.dot(left.velocity, right.velocity) / (left_speed * right_speed), -1.0, 1.0))
    angle = float(np.degrees(np.arccos(cosine)))
    speed_ratio = max(left_speed, right_speed) / min(left_speed, right_speed)
    return angle, speed_ratio


def short_gap_length(coords: list[np.ndarray | None], index: int) -> int:
    if coords[index] is not None:
        return 0
    left = index
    while left > 0 and coords[left - 1] is None:
        left -= 1
    right = index
    while right + 1 < len(coords) and coords[right + 1] is None:
        right += 1
    return right - left + 1


def optimize_trajectory(
    raw_coords: list[Any],
    *,
    frame_height: int,
    config: GuardedTrajectoryConfig = GuardedTrajectoryConfig(),
) -> dict[str, Any]:
    coords = [as_point(point) for point in raw_coords]
    optimized: list[np.ndarray | None] = []
    diagnostics: list[dict[str, Any]] = []

    for index, actual in enumerate(coords):
        left = robust_side_model(coords, index, direction=-1, config=config)
        right = robust_side_model(coords, index, direction=1, config=config)
        prediction = None
        threshold = None
        consensus_distance = None
        angle, speed_ratio = velocity_metrics(left, right)
        event_boundary = False

        if left is not None and right is not None:
            prediction = (left.prediction + right.prediction) / 2.0
            threshold = dynamic_threshold(float(prediction[1]), frame_height, config)
            consensus_distance = float(np.linalg.norm(left.prediction - right.prediction))
            left_speed = float(np.linalg.norm(left.velocity))
            right_speed = float(np.linalg.norm(right.velocity))
            event_boundary = (
                min(left_speed, right_speed) >= config.min_event_speed_px
                and (
                    (angle is not None and angle >= config.event_angle_deg)
                    or (speed_ratio is not None and speed_ratio >= config.event_speed_ratio)
                )
            )

        if actual is None:
            gap_length = short_gap_length(coords, index)
            can_fill = (
                prediction is not None
                and threshold is not None
                and consensus_distance is not None
                and gap_length <= config.max_fill_gap
                and consensus_distance <= threshold * config.consensus_scale
                and not event_boundary
            )
            selected = prediction if can_fill else None
            status = "short_gap_filled" if can_fill else "missing"
            reason = "bilateral_consensus" if can_fill else "no_safe_bilateral_fill"
            actual_distance = None
        else:
            actual_distance = float(np.linalg.norm(actual - prediction)) if prediction is not None else None
            can_correct = (
                prediction is not None
                and threshold is not None
                and consensus_distance is not None
                and consensus_distance <= threshold * config.consensus_scale
                and actual_distance is not None
                and actual_distance > threshold * config.spike_scale
                and not event_boundary
            )
            if event_boundary:
                selected = actual
                status = "event_raw_kept"
                reason = "left_right_velocity_discontinuity"
            elif can_correct:
                selected = prediction
                status = "isolated_spike_corrected"
                reason = "bilateral_consensus_rejects_observed_point"
            elif prediction is None:
                selected = actual
                status = "raw_kept_insufficient_context"
                reason = "missing_left_or_right_support"
            elif consensus_distance is None or threshold is None or consensus_distance > threshold * config.consensus_scale:
                selected = actual
                status = "ambiguous_raw_kept"
                reason = "left_right_models_disagree"
            else:
                selected = actual
                status = "raw_kept"
                reason = "observed_point_not_an_isolated_spike"

        optimized.append(selected)
        diagnostics.append(
            {
                "raw_pixel": json_point(actual),
                "optimized_pixel": json_point(selected),
                "left_prediction": json_point(left.prediction) if left else None,
                "right_prediction": json_point(right.prediction) if right else None,
                "prediction": json_point(prediction),
                "left_support_frames": list(left.support_frames) if left else [],
                "right_support_frames": list(right.support_frames) if right else [],
                "actual_prediction_distance_px": None if actual_distance is None else round(actual_distance, 3),
                "left_right_prediction_distance_px": None if consensus_distance is None else round(consensus_distance, 3),
                "dynamic_threshold_px": None if threshold is None else round(threshold, 3),
                "turn_angle_deg": None if angle is None else round(angle, 3),
                "speed_ratio": None if speed_ratio is None else round(speed_ratio, 3),
                "event_boundary": event_boundary,
                "status": status,
                "reason": reason,
            }
        )

    summary = Counter(item["status"] for item in diagnostics)
    return {
        "optimized": [json_point(point) for point in optimized],
        "diagnostics": diagnostics,
        "summary": dict(summary),
    }


def load_coordinate_json(input_path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    metadata = dict(payload.get("metadata") or {})
    if isinstance(payload.get("ball_coords"), list):
        return metadata, [dict(row) for row in payload["ball_coords"] if isinstance(row, dict)]
    if isinstance(payload.get("frames"), list):
        rows = []
        for index, frame in enumerate(payload["frames"]):
            if not isinstance(frame, dict):
                continue
            ball = frame.get("ball") if isinstance(frame.get("ball"), dict) else {}
            rows.append(
                {
                    "frame_index": frame.get("frame_index", index),
                    "time_sec": frame.get("time_sec"),
                    "pixel": ball.get("pixel"),
                    "confidence": ball.get("confidence"),
                    "candidates": frame.get("ball_candidates", []),
                }
            )
        return metadata, rows
    raise ValueError("Input JSON must contain ball_coords or frames")


def run_file(input_json: Path, output_json: Path, config: GuardedTrajectoryConfig) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    metadata, rows = load_coordinate_json(input_json)
    frame_height = int(metadata.get("video_height") or 1080)
    raw_coords = [row.get("pixel") for row in rows]
    result = optimize_trajectory(raw_coords, frame_height=frame_height, config=config)
    output_rows = []
    for index, (row, diagnostic) in enumerate(zip(rows, result["diagnostics"])):
        frame_index = int(row.get("frame_index", index))
        output_rows.append(
            {
                "frame_index": frame_index,
                "time_sec": row.get("time_sec"),
                "pixel": diagnostic["optimized_pixel"],
                "confidence": row.get("confidence"),
                "candidates": row.get("candidates", []),
                **diagnostic,
            }
        )

    output_metadata = dict(metadata)
    output_metadata.update(
        {
            "algorithm": "event_safe_bilateral_trajectory_optimizer_v1",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "input_json_path": str(input_json),
            "config": asdict(config),
            "summary": result["summary"],
        }
    )
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(
        json.dumps({"metadata": output_metadata, "ball_coords": output_rows}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return result, rows


def render_overlay(
    input_video: Path,
    output_video: Path,
    rows: list[dict[str, Any]],
    result: dict[str, Any],
) -> dict[str, int | float]:
    import cv2

    cap = cv2.VideoCapture(str(input_video))
    if not cap.isOpened():
        raise FileNotFoundError(f"Could not open video: {input_video}")
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 25.0)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    output_video.parent.mkdir(parents=True, exist_ok=True)
    writer = cv2.VideoWriter(str(output_video), cv2.VideoWriter_fourcc(*"mp4v"), fps, (width, height))
    if not writer.isOpened():
        cap.release()
        raise RuntimeError(f"Could not create video: {output_video}")

    row_by_frame = {int(row.get("frame_index", index)): index for index, row in enumerate(rows)}

    def draw_point(frame: np.ndarray, point: list[float] | None, color: tuple[int, int, int], radius: int) -> None:
        if point is None:
            return
        cv2.circle(frame, (int(round(point[0])), int(round(point[1]))), radius, color, 2, cv2.LINE_AA)

    written = 0
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            row_index = row_by_frame.get(written)
            if row_index is not None:
                diagnostic = result["diagnostics"][row_index]
                draw_point(frame, diagnostic["raw_pixel"], (0, 190, 0), 6)
                draw_point(frame, diagnostic["left_prediction"], (255, 180, 0), 4)
                draw_point(frame, diagnostic["right_prediction"], (0, 0, 255), 4)
                draw_point(frame, diagnostic["optimized_pixel"], (0, 230, 255), 10)
                label = diagnostic["status"]
                if diagnostic["event_boundary"]:
                    label += " | event boundary"
                cv2.putText(frame, f"frame={written} {label}", (24, 36), cv2.FONT_HERSHEY_SIMPLEX, 0.68, (255, 255, 255), 2, cv2.LINE_AA)
                cv2.putText(frame, "green=raw cyan=left red=right yellow=output", (24, 64), cv2.FONT_HERSHEY_SIMPLEX, 0.52, (255, 255, 255), 2, cv2.LINE_AA)
            writer.write(frame)
            written += 1
    finally:
        cap.release()
        writer.release()
    return {"frames_written": written, "fps": fps, "width": width, "height": height}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-json", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--input-video", type=Path, default=None)
    parser.add_argument("--output-video", type=Path, default=None)
    parser.add_argument("--context-half", type=int, default=5)
    parser.add_argument("--max-fill-gap", type=int, default=2)
    parser.add_argument("--base-threshold", type=float, default=12.0)
    args = parser.parse_args()

    config = GuardedTrajectoryConfig(
        context_half=args.context_half,
        max_fill_gap=args.max_fill_gap,
        base_threshold_px=args.base_threshold,
    )
    result, rows = run_file(args.input_json, args.output_json, config)
    metadata, _ = load_coordinate_json(args.input_json)
    input_video = args.input_video
    if input_video is None and metadata.get("source_video_path"):
        candidate = Path(metadata["source_video_path"])
        input_video = candidate if candidate.exists() else None
    video_summary = None
    if input_video is not None:
        output_video = args.output_video or args.output_json.with_suffix(".mp4")
        video_summary = render_overlay(input_video, output_video, rows, result)
        video_summary["output"] = str(output_video)
    print(json.dumps({"output": str(args.output_json), "video": video_summary, "summary": result["summary"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
