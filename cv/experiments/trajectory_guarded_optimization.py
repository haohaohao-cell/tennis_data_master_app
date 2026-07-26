"""Event-safe trajectory optimization for stable TrackNet/GridTrackNet output.

The optimizer never deletes an observed detector coordinate.  It first finds a
left and a right stable anchor, freezes the interval between incompatible
anchors, and fits each anchor with a local RANSAC line.  A frozen point can
only be replaced by a prediction from its own confirmed branch; a trajectory
boundary is always retained as raw data.
"""

from __future__ import annotations

import argparse
from itertools import combinations
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
    anchor_window: int = 8
    min_ransac_inlier_ratio: float = 0.70
    ransac_degree: int = 2
    freeze_join_gap_frames: int = 1
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
    inlier_count: int
    sample_count: int
    median_residual_px: float


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


def fit_anchor_ransac(
    coords: list[np.ndarray | None],
    indices: list[int],
    target_index: int,
    *,
    frame_height: int,
    config: GuardedTrajectoryConfig,
) -> SideModel | None:
    """Fit a local 2D polynomial model using only trusted anchor points.

    The anchor window is deliberately small, so evaluating every two-point
    RANSAC hypothesis is deterministic and more reliable than random sampling.
    Candidate samples are never drawn from a frozen interval.
    """
    valid_indices = sorted(index for index in indices if coords[index] is not None)
    degree = max(int(config.ransac_degree), 1)
    sample_size = degree + 1
    if len(valid_indices) < max(config.min_side_points, sample_size):
        return None

    times = np.asarray(valid_indices, dtype=np.float64)
    points = np.asarray([coords[index] for index in valid_indices], dtype=np.float64)
    thresholds = np.asarray(
        [dynamic_threshold(float(point[1]), frame_height, config) for point in points],
        dtype=np.float64,
    )
    best_mask: np.ndarray | None = None
    best_count = -1
    best_median = math.inf

    for sample_indices in combinations(range(len(valid_indices)), sample_size):
        sample_indices_arr = np.asarray(sample_indices, dtype=np.int64)
        x_coefficients = np.polyfit(times[sample_indices_arr], points[sample_indices_arr, 0], degree)
        y_coefficients = np.polyfit(times[sample_indices_arr], points[sample_indices_arr, 1], degree)
        predicted = np.column_stack((np.polyval(x_coefficients, times), np.polyval(y_coefficients, times)))
        residuals = np.linalg.norm(points - predicted, axis=1)
        mask = residuals <= thresholds
        count = int(mask.sum())
        median = float(np.median(residuals[mask])) if count else math.inf
        if count > best_count or (count == best_count and median < best_median):
            best_mask = mask
            best_count = count
            best_median = median

    if best_mask is None or best_count < config.min_side_points:
        return None

    inlier_times = times[best_mask]
    inlier_points = points[best_mask]
    x_coefficients = np.polyfit(inlier_times, inlier_points[:, 0], degree)
    y_coefficients = np.polyfit(inlier_times, inlier_points[:, 1], degree)
    prediction = np.asarray(
        [np.polyval(x_coefficients, target_index), np.polyval(y_coefficients, target_index)],
        dtype=np.float64,
    )
    velocity = np.asarray(
        [np.polyval(np.polyder(x_coefficients), target_index), np.polyval(np.polyder(y_coefficients), target_index)],
        dtype=np.float64,
    )
    if not np.all(np.isfinite(prediction)) or not np.all(np.isfinite(velocity)):
        return None

    refit_predictions = np.column_stack((np.polyval(x_coefficients, times), np.polyval(y_coefficients, times)))
    refit_residuals = np.linalg.norm(points - refit_predictions, axis=1)
    refit_mask = refit_residuals <= thresholds
    if int(refit_mask.sum()) < config.min_side_points:
        return None
    inlier_frames = tuple(int(valid_indices[index]) for index in np.flatnonzero(refit_mask))
    return SideModel(
        prediction=prediction,
        velocity=velocity,
        support_frames=inlier_frames,
        inlier_count=len(inlier_frames),
        sample_count=len(valid_indices),
        median_residual_px=float(np.median(refit_residuals[refit_mask])),
    )


def strong_model(model: SideModel | None, config: GuardedTrajectoryConfig) -> bool:
    return bool(
        model is not None
        and model.inlier_count >= config.min_side_points
        and model.inlier_count / max(model.sample_count, 1) >= config.min_ransac_inlier_ratio
    )


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


def build_local_anchor_models(
    coords: list[np.ndarray | None],
    *,
    frame_height: int,
    config: GuardedTrajectoryConfig,
    excluded: np.ndarray | None = None,
) -> tuple[list[SideModel | None], list[SideModel | None]]:
    """Fit independent nearby left/right anchors for every target frame."""
    size = len(coords)
    left_models: list[SideModel | None] = []
    right_models: list[SideModel | None] = []
    for target_index in range(size):
        span = max(config.context_half, config.anchor_window)
        start = max(0, target_index - span)
        end = min(size, target_index + span + 1)
        left_indices = [
            index
            for index in range(start, target_index)
            if (excluded is None or not excluded[index]) and coords[index] is not None
        ]
        right_indices = [
            index
            for index in range(target_index + 1, end)
            if (excluded is None or not excluded[index]) and coords[index] is not None
        ]
        left_models.append(
            fit_anchor_ransac(coords, left_indices, target_index, frame_height=frame_height, config=config)
        )
        right_models.append(
            fit_anchor_ransac(coords, right_indices, target_index, frame_height=frame_height, config=config)
        )
    return left_models, right_models


def merge_frozen_ranges(suspect_indices: list[int], config: GuardedTrajectoryConfig) -> list[tuple[int, int]]:
    if not suspect_indices:
        return []
    ranges: list[tuple[int, int]] = []
    start = suspect_indices[0]
    end = start
    for index in suspect_indices[1:]:
        if index <= end + config.freeze_join_gap_frames + 1:
            end = index
            continue
        ranges.append((start, end))
        start = index
        end = index
    ranges.append((start, end))
    return ranges


def range_at(index: int, ranges: list[tuple[int, int]]) -> tuple[int, int] | None:
    for start, end in ranges:
        if start <= index <= end:
            return start, end
    return None


def optimize_trajectory(
    raw_coords: list[Any],
    *,
    frame_height: int,
    config: GuardedTrajectoryConfig = GuardedTrajectoryConfig(),
) -> dict[str, Any]:
    coords = [as_point(point) for point in raw_coords]
    preliminary_left, preliminary_right = build_local_anchor_models(
        coords,
        frame_height=frame_height,
        config=config,
    )
    suspect_indices: list[int] = []
    for index, actual in enumerate(coords):
        left = preliminary_left[index]
        right = preliminary_right[index]
        if actual is None:
            continue
        left_bad = bool(
            strong_model(left, config)
            and float(np.linalg.norm(actual - left.prediction))
            > dynamic_threshold(float(left.prediction[1]), frame_height, config) * config.spike_scale
        )
        right_bad = bool(
            strong_model(right, config)
            and float(np.linalg.norm(actual - right.prediction))
            > dynamic_threshold(float(right.prediction[1]), frame_height, config) * config.spike_scale
        )
        # A strong prediction can seed a frozen run when the opposite side has
        # no stable model yet.  A point close to either stable side is kept as
        # a possible physical boundary instead of becoming an anomaly.
        if (left_bad and (not strong_model(right, config) or right_bad)) or (
            right_bad and not strong_model(left, config)
        ):
            suspect_indices.append(index)

    frozen_ranges = merge_frozen_ranges(suspect_indices, config)
    frozen_mask = np.zeros(len(coords), dtype=bool)
    for start, end in frozen_ranges:
        frozen_mask[start : end + 1] = True
    left_models, right_models = build_local_anchor_models(
        coords,
        frame_height=frame_height,
        config=config,
        excluded=frozen_mask,
    )
    left_residuals = [
        None if point is None or model is None else float(np.linalg.norm(point - model.prediction))
        for point, model in zip(coords, left_models)
    ]
    right_residuals = [
        None if point is None or model is None else float(np.linalg.norm(point - model.prediction))
        for point, model in zip(coords, right_models)
    ]

    boundary_indices: set[int] = set()
    for _, end in frozen_ranges:
        candidate = end + 1
        if candidate >= len(coords) or coords[candidate] is None:
            continue
        left = left_models[candidate]
        right = right_models[candidate]
        angle, speed_ratio = velocity_metrics(left, right)
        if not strong_model(left, config) or not strong_model(right, config):
            continue
        threshold = dynamic_threshold(float(right.prediction[1]), frame_height, config)
        close_to_right = float(np.linalg.norm(coords[candidate] - right.prediction)) <= threshold * config.consensus_scale
        discontinuous = (
            (angle is not None and angle >= config.event_angle_deg)
            or (speed_ratio is not None and speed_ratio >= config.event_speed_ratio)
        )
        if close_to_right and discontinuous:
            boundary_indices.add(candidate)

    optimized: list[np.ndarray | None] = []
    diagnostics: list[dict[str, Any]] = []

    for index, actual in enumerate(coords):
        left = left_models[index]
        right = right_models[index]
        prediction = None
        threshold = None
        consensus_distance = None
        angle, speed_ratio = velocity_metrics(left, right)
        event_boundary = False

        if left is not None and right is not None:
            prediction = (left.prediction + right.prediction) / 2.0
            threshold = dynamic_threshold(float(prediction[1]), frame_height, config)
            consensus_distance = float(np.linalg.norm(left.prediction - right.prediction))

        # A boundary is only promoted after a frozen run has exposed two
        # independent branches.  Smooth curvature alone must never classify a
        # normal observation as an event, nor make it eligible for replacement.
        if index in boundary_indices:
            event_boundary = True

        frozen_range = range_at(index, frozen_ranges)
        in_frozen_range = frozen_range is not None
        frozen_range_value = list(frozen_range) if frozen_range is not None else None

        if actual is None:
            gap_length = short_gap_length(coords, index)
            can_fill = (
                prediction is not None
                and threshold is not None
                and consensus_distance is not None
                and gap_length <= config.max_fill_gap
                and consensus_distance <= threshold * config.consensus_scale
                and not event_boundary
                and not in_frozen_range
            )
            selected = prediction if can_fill else None
            status = "short_gap_filled" if can_fill else "missing"
            reason = "bilateral_consensus" if can_fill else "no_safe_bilateral_fill"
            actual_distance = None
        else:
            actual_distance = float(np.linalg.norm(actual - prediction)) if prediction is not None else None
            bilateral_correction = (
                prediction is not None
                and threshold is not None
                and consensus_distance is not None
                and consensus_distance <= threshold * config.consensus_scale
                and actual_distance is not None
                and actual_distance > threshold * config.spike_scale
                and not event_boundary
            )
            left_distance = float(np.linalg.norm(actual - left.prediction)) if left is not None else None
            # A frozen interval immediately before a confirmed branch boundary
            # belongs to the left anchor.  The right anchor is intentionally
            # not averaged in: it models the new physical branch.
            left_branch_correction = (
                in_frozen_range
                and frozen_range is not None
                and frozen_range[1] + 1 in boundary_indices
                and strong_model(left, config)
                and left_distance is not None
                and threshold is not None
                and left_distance > threshold * config.spike_scale
            )
            if event_boundary:
                selected = actual
                status = "boundary_raw_kept"
                reason = "stable_anchor_velocity_discontinuity"
            elif bilateral_correction:
                selected = prediction
                status = "isolated_spike_corrected"
                reason = "bilateral_consensus_rejects_observed_point"
            elif left_branch_correction:
                selected = left.prediction
                status = "frozen_left_ransac_corrected"
                reason = "left_anchor_rejects_frozen_observation"
            elif prediction is None:
                selected = actual
                status = "raw_kept_insufficient_context"
                reason = "missing_left_or_right_support"
            elif in_frozen_range:
                selected = actual
                status = "frozen_ambiguous_raw_kept"
                reason = "no_safe_anchor_branch_correction"
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
                "left_anchor_residual_px": None if left_residuals[index] is None else round(left_residuals[index], 3),
                "right_anchor_residual_px": None if right_residuals[index] is None else round(right_residuals[index], 3),
                "left_support_frames": list(left.support_frames) if left else [],
                "right_support_frames": list(right.support_frames) if right else [],
                "left_ransac_inlier_count": left.inlier_count if left else 0,
                "right_ransac_inlier_count": right.inlier_count if right else 0,
                "left_ransac_sample_count": left.sample_count if left else 0,
                "right_ransac_sample_count": right.sample_count if right else 0,
                "left_ransac_median_residual_px": None if left is None else round(left.median_residual_px, 3),
                "right_ransac_median_residual_px": None if right is None else round(right.median_residual_px, 3),
                "actual_prediction_distance_px": None if actual_distance is None else round(actual_distance, 3),
                "left_right_prediction_distance_px": None if consensus_distance is None else round(consensus_distance, 3),
                "dynamic_threshold_px": None if threshold is None else round(threshold, 3),
                "turn_angle_deg": None if angle is None else round(angle, 3),
                "speed_ratio": None if speed_ratio is None else round(speed_ratio, 3),
                "event_boundary": event_boundary,
                "frozen_range": frozen_range_value,
                "frozen_ranges": [list(item) for item in frozen_ranges],
                "boundary_frame": index if index in boundary_indices else None,
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
            "algorithm": "frozen_segment_local_ransac_trajectory_optimizer_v2",
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


def render_coordinate_plots(
    output_xt: Path,
    output_yt: Path,
    rows: list[dict[str, Any]],
    result: dict[str, Any],
) -> dict[str, str]:
    """Render coordinate-vs-time diagnostics for the raw and selected tracks."""
    import matplotlib.pyplot as plt

    time_values = np.asarray(
        [
            float(row["time_sec"]) if row.get("time_sec") is not None else float(row.get("frame_index", index))
            for index, row in enumerate(rows)
        ],
        dtype=np.float64,
    )
    raw_points = [as_point(item["raw_pixel"]) for item in result["diagnostics"]]
    optimized_points = [as_point(item["optimized_pixel"]) for item in result["diagnostics"]]
    statuses = [item["status"] for item in result["diagnostics"]]

    def coordinate_values(points: list[np.ndarray | None], axis: int) -> np.ndarray:
        return np.asarray([np.nan if point is None else point[axis] for point in points], dtype=np.float64)

    raw_x = coordinate_values(raw_points, 0)
    raw_y = coordinate_values(raw_points, 1)
    optimized_x = coordinate_values(optimized_points, 0)
    optimized_y = coordinate_values(optimized_points, 1)
    repaired = np.asarray([status.endswith("_corrected") for status in statuses], dtype=bool)
    boundaries = np.asarray([status == "boundary_raw_kept" for status in statuses], dtype=bool)

    def render(path: Path, raw: np.ndarray, optimized: np.ndarray, label: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fig, axis = plt.subplots(figsize=(14, 6), constrained_layout=True)
        axis.plot(time_values, raw, color="#6b7280", linewidth=1.2, alpha=0.70, label="raw")
        axis.plot(time_values, optimized, color="#0f766e", linewidth=1.8, alpha=0.95, label="optimized")
        if repaired.any():
            axis.scatter(time_values[repaired], optimized[repaired], s=34, color="#d97706", zorder=3, label="frozen RANSAC corrected")
        if boundaries.any():
            axis.scatter(time_values[boundaries], raw[boundaries], s=42, marker="s", color="#b91c1c", zorder=3, label="raw boundary kept")
        axis.set_xlabel("time (s)")
        axis.set_ylabel(f"{label} (pixel)")
        axis.set_title(f"Ball {label}-time coordinates")
        axis.grid(True, alpha=0.25)
        axis.legend(loc="best")
        fig.savefig(path, dpi=160)
        plt.close(fig)

    render(output_xt, raw_x, optimized_x, "x")
    render(output_yt, raw_y, optimized_y, "y")
    return {"xt": str(output_xt), "yt": str(output_yt)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-json", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--input-video", type=Path, default=None)
    parser.add_argument("--output-video", type=Path, default=None)
    parser.add_argument("--output-xt-plot", type=Path, default=None)
    parser.add_argument("--output-yt-plot", type=Path, default=None)
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
    output_xt = args.output_xt_plot or args.output_json.with_name(f"{args.output_json.stem}_xt.png")
    output_yt = args.output_yt_plot or args.output_json.with_name(f"{args.output_json.stem}_yt.png")
    plots = render_coordinate_plots(output_xt, output_yt, rows, result)
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
    print(
        json.dumps(
            {"output": str(args.output_json), "plots": plots, "video": video_summary, "summary": result["summary"]},
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
