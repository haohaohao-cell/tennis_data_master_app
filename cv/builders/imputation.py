"""Fill missing court-coordinate values in match_frames-derived data.

This script is a dedicated repair pipeline for cases where pixel coordinates
exist in `match_frames.json` but the projected court coordinates are missing.

Pipeline:
1. Try to impute missing `court` values from nearby frames by fitting a local
   pixel->court mapping from existing observations.
2. If local fitting still fails, fall back to deterministic default values that
   are tailored to ball / player / bounce contexts.

The source JSON is never modified. The script writes a new imputed JSON plus a
report that records how many values were repaired by local fitting versus
default fallback.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from copy import deepcopy
from pathlib import Path
from typing import Any

import numpy as np

from cv.config import OUTPUT_DIR

DEFAULT_INPUT = OUTPUT_DIR / "match_frames.json"
DEFAULT_OUTPUT = OUTPUT_DIR / "match_frames_imputed.json"
DEFAULT_REPORT = OUTPUT_DIR / "match_frames_imputed_report.json"
COURT_WIDTH_M = 10.97
COURT_LENGTH_M = 23.77
CONTACT_Y_OFFSET_M = 2.0


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


def feet_pixel_from_bbox(bbox: list[int] | list[float] | None) -> list[float] | None:
    if not isinstance(bbox, list) or len(bbox) < 4:
        return None
    return [round((bbox[0] + bbox[2]) / 2.0, 3), round(float(bbox[3]), 3)]


def round_pair(values: list[float] | tuple[float, float]) -> list[float]:
    return [round(float(values[0]), 2), round(float(values[1]), 2)]


def clamp_pair(pair: list[float], *, allow_outside_baseline: bool) -> list[float]:
    x = min(max(pair[0], 0.0), COURT_WIDTH_M)
    if allow_outside_baseline:
        y = min(max(pair[1], -1.5), COURT_LENGTH_M + 1.5)
    else:
        y = min(max(pair[1], 0.0), COURT_LENGTH_M)
    return round_pair([x, y])


def median_pair(pairs: list[list[float]]) -> list[float] | None:
    if not pairs:
        return None
    array = np.array(pairs, dtype=np.float64)
    return round_pair(np.median(array, axis=0).tolist())


def top_or_bottom_from_pixel(pixel: list[float] | None, frame_height: float) -> str:
    if pixel is None or len(pixel) < 2:
        return "bottom"
    return "top" if pixel[1] < frame_height / 2.0 else "bottom"


def collect_correspondences(
    frames: list[dict[str, Any]],
    target_frame: int,
    window: int,
) -> list[tuple[list[float], list[float], int, str]]:
    start = max(0, target_frame - window)
    end = min(len(frames) - 1, target_frame + window)
    correspondences: list[tuple[list[float], list[float], int, str]] = []

    for frame_idx in range(start, end + 1):
        frame = frames[frame_idx]

        ball = frame.get("ball")
        if isinstance(ball, dict) and is_valid_pair(ball.get("pixel")) and is_valid_pair(ball.get("court")):
            correspondences.append((ball["pixel"], ball["court"], frame_idx, "ball"))

        for player in frame.get("players", []):
            feet_pixel = feet_pixel_from_bbox(player.get("bbox_pixel"))
            feet_court = player.get("feet_court")
            if feet_pixel is not None and is_valid_pair(feet_court):
                correspondences.append((feet_pixel, feet_court, frame_idx, f"player_{player.get('id')}"))

        events = frame.get("events", {})
        if is_valid_pair(events.get("bounce_pixel")) and is_valid_pair(events.get("bounce_court")):
            correspondences.append((events["bounce_pixel"], events["bounce_court"], frame_idx, "bounce"))

    return correspondences


def compute_homography_dlt(src_points: np.ndarray, dst_points: np.ndarray) -> np.ndarray | None:
    if len(src_points) < 4:
        return None

    rows = []
    for (x, y), (u, v) in zip(src_points, dst_points):
        rows.append([-x, -y, -1.0, 0.0, 0.0, 0.0, x * u, y * u, u])
        rows.append([0.0, 0.0, 0.0, -x, -y, -1.0, x * v, y * v, v])

    design = np.array(rows, dtype=np.float64)
    if np.linalg.matrix_rank(design) < 8:
        return None

    _, _, vh = np.linalg.svd(design)
    model = vh[-1].reshape(3, 3)
    if np.isclose(model[2, 2], 0.0):
        return None
    return model / model[2, 2]


def reprojection_errors(model: np.ndarray, src_points: np.ndarray, dst_points: np.ndarray) -> np.ndarray:
    errors = []
    for (x, y), (u, v) in zip(src_points, dst_points):
        vector = np.array([x, y, 1.0], dtype=np.float64)
        transformed = model @ vector
        if transformed[2] == 0:
            errors.append(np.inf)
            continue
        pred_u = transformed[0] / transformed[2]
        pred_v = transformed[1] / transformed[2]
        errors.append(float(np.hypot(pred_u - u, pred_v - v)))
    return np.array(errors, dtype=np.float64)


def fit_homography(
    correspondences: list[tuple[list[float], list[float], int, str]],
    target_frame: int,
) -> tuple[np.ndarray | None, int]:
    if len(correspondences) < 4:
        return None, 0

    src_points = np.array([item[0] for item in correspondences], dtype=np.float64)
    dst_points = np.array([item[1] for item in correspondences], dtype=np.float64)

    rng = np.random.default_rng(42 + target_frame)
    threshold = 1.0
    best_model: np.ndarray | None = None
    best_mask: np.ndarray | None = None
    best_inlier_count = 0

    sample_count = min(80, max(20, len(correspondences) * 4))
    for _ in range(sample_count):
        sample_indices = rng.choice(len(correspondences), size=4, replace=False)
        candidate = compute_homography_dlt(src_points[sample_indices], dst_points[sample_indices])
        if candidate is None:
            continue

        errors = reprojection_errors(candidate, src_points, dst_points)
        mask = errors <= threshold
        count = int(mask.sum())
        if count > best_inlier_count:
            best_model = candidate
            best_mask = mask
            best_inlier_count = count

    if best_model is None or best_mask is None or best_inlier_count < 4:
        return None, 0

    refined = compute_homography_dlt(src_points[best_mask], dst_points[best_mask])
    return refined if refined is not None else best_model, best_inlier_count


def fit_affine(
    correspondences: list[tuple[list[float], list[float], int, str]],
    target_frame: int,
) -> tuple[np.ndarray | None, int]:
    if len(correspondences) < 3:
        return None, 0

    src_points = np.array([item[0] for item in correspondences], dtype=np.float64)
    dst_points = np.array([item[1] for item in correspondences], dtype=np.float64)
    weights = np.array(
        [1.0 / (1.0 + abs(frame_idx - target_frame)) for _, _, frame_idx, _ in correspondences],
        dtype=np.float64,
    )

    design = np.column_stack((src_points, np.ones(len(src_points), dtype=np.float64)))
    weighted_design = design * weights[:, None]
    weighted_targets = dst_points * weights[:, None]

    if np.linalg.matrix_rank(weighted_design) < 3:
        return None, 0

    solution, _, _, _ = np.linalg.lstsq(weighted_design, weighted_targets, rcond=None)
    predicted = design @ solution
    residuals = np.linalg.norm(predicted - dst_points, axis=1)
    inliers = int(np.sum(residuals <= 1.0))
    return solution, inliers


def predict_with_homography(model: np.ndarray, pixel: list[float]) -> list[float] | None:
    vector = np.array([pixel[0], pixel[1], 1.0], dtype=np.float64)
    transformed = model @ vector
    if transformed[2] == 0:
        return None
    x, y = transformed[0] / transformed[2], transformed[1] / transformed[2]
    if not np.isfinite(x) or not np.isfinite(y):
        return None
    return round_pair([x, y])


def predict_with_affine(model: np.ndarray, pixel: list[float]) -> list[float] | None:
    vector = np.array([pixel[0], pixel[1], 1.0], dtype=np.float64)
    transformed = vector @ model
    x, y = transformed
    if not np.isfinite(x) or not np.isfinite(y):
        return None
    return round_pair([x, y])


def estimate_court_position(
    frames: list[dict[str, Any]],
    target_frame: int,
    pixel: list[float] | None,
    windows: list[int],
    min_points: int,
) -> tuple[list[float] | None, dict[str, Any] | None]:
    if pixel is None:
        return None, None

    for window in windows:
        correspondences = collect_correspondences(frames, target_frame, window)
        if len(correspondences) < min_points:
            continue

        homography, homography_inliers = fit_homography(correspondences, target_frame)
        if homography is not None and homography_inliers >= 4:
            prediction = predict_with_homography(homography, pixel)
            if prediction is not None:
                return prediction, {
                    "method": "local_homography",
                    "window": window,
                    "candidate_points": len(correspondences),
                    "inliers": homography_inliers,
                }

        affine, affine_inliers = fit_affine(correspondences, target_frame)
        if affine is not None and affine_inliers >= 3:
            prediction = predict_with_affine(affine, pixel)
            if prediction is not None:
                return prediction, {
                    "method": "local_affine",
                    "window": window,
                    "candidate_points": len(correspondences),
                    "inliers": affine_inliers,
                }

    return None, None


def build_missing_stats(frames: list[dict[str, Any]]) -> dict[str, int]:
    stats = Counter()
    for frame in frames:
        ball = frame.get("ball")
        if isinstance(ball, dict) and is_valid_pair(ball.get("pixel")) and not is_valid_pair(ball.get("court")):
            stats["ball_court_missing"] += 1

        for player in frame.get("players", []):
            if feet_pixel_from_bbox(player.get("bbox_pixel")) is not None and not is_valid_pair(player.get("feet_court")):
                stats["player_feet_court_missing"] += 1

        events = frame.get("events", {})
        if is_valid_pair(events.get("bounce_pixel")) and not is_valid_pair(events.get("bounce_court")):
            stats["bounce_court_missing"] += 1
    return dict(stats)


def build_defaults(frames: list[dict[str, Any]], frame_height: float) -> dict[str, Any]:
    player_points: dict[int, list[list[float]]] = {1: [], 2: []}
    ball_points: dict[str, list[list[float]]] = {"top": [], "bottom": []}
    bounce_points: dict[str, list[list[float]]] = {"top": [], "bottom": []}

    for frame in frames:
        ball = frame.get("ball")
        if isinstance(ball, dict) and is_valid_pair(ball.get("pixel")) and is_valid_pair(ball.get("court")):
            side = top_or_bottom_from_pixel(ball["pixel"], frame_height)
            ball_points[side].append(ball["court"])

        for player in frame.get("players", []):
            player_id = player.get("id")
            if player_id in player_points and is_valid_pair(player.get("feet_court")):
                player_points[player_id].append(player["feet_court"])

        events = frame.get("events", {})
        if is_valid_pair(events.get("bounce_pixel")) and is_valid_pair(events.get("bounce_court")):
            side = top_or_bottom_from_pixel(events["bounce_pixel"], frame_height)
            bounce_points[side].append(events["bounce_court"])

    generic_top = [COURT_WIDTH_M / 2.0, COURT_LENGTH_M * 0.25]
    generic_bottom = [COURT_WIDTH_M / 2.0, COURT_LENGTH_M * 0.75]
    player1_default = median_pair(player_points[1]) or [COURT_WIDTH_M / 2.0, COURT_LENGTH_M + 0.8]
    player2_default = median_pair(player_points[2]) or [COURT_WIDTH_M / 2.0, -0.8]

    defaults = {
        "player_feet": {
            1: clamp_pair(player1_default, allow_outside_baseline=True),
            2: clamp_pair(player2_default, allow_outside_baseline=True),
        },
        "ball": {
            "top": clamp_pair(median_pair(ball_points["top"]) or generic_top, allow_outside_baseline=False),
            "bottom": clamp_pair(median_pair(ball_points["bottom"]) or generic_bottom, allow_outside_baseline=False),
        },
        "bounce": {
            "top": clamp_pair(median_pair(bounce_points["top"]) or generic_top, allow_outside_baseline=False),
            "bottom": clamp_pair(median_pair(bounce_points["bottom"]) or generic_bottom, allow_outside_baseline=False),
        },
    }
    return defaults


def default_player_feet(player_id: int | None, defaults: dict[str, Any]) -> list[float]:
    if player_id in defaults["player_feet"]:
        return defaults["player_feet"][player_id]
    return clamp_pair([COURT_WIDTH_M / 2.0, COURT_LENGTH_M / 2.0], allow_outside_baseline=True)


def default_ball_court(frame: dict[str, Any], defaults: dict[str, Any], frame_height: float) -> list[float]:
    events = frame.get("events", {})
    hitter_id = events.get("hitter_id")

    if events.get("is_hit") and hitter_id in (1, 2):
        players = {player.get("id"): player for player in frame.get("players", [])}
        hitter = players.get(hitter_id)
        if hitter and is_valid_pair(hitter.get("feet_court")):
            hitter_feet = hitter["feet_court"]
            y_offset = -CONTACT_Y_OFFSET_M if hitter_id == 1 else CONTACT_Y_OFFSET_M
            return clamp_pair([hitter_feet[0], hitter_feet[1] + y_offset], allow_outside_baseline=False)

    ball = frame.get("ball")
    pixel = ball.get("pixel") if isinstance(ball, dict) else None
    side = top_or_bottom_from_pixel(pixel, frame_height)
    return defaults["ball"][side]


def default_bounce_court(frame: dict[str, Any], defaults: dict[str, Any], frame_height: float) -> list[float]:
    events = frame.get("events", {})
    if is_valid_pair(events.get("bounce_pixel")):
        side = top_or_bottom_from_pixel(events["bounce_pixel"], frame_height)
        return defaults["bounce"][side]

    ball = frame.get("ball")
    if isinstance(ball, dict) and is_valid_pair(ball.get("court")):
        return clamp_pair(ball["court"], allow_outside_baseline=False)

    return defaults["bounce"]["bottom"]


def impute_match_frames(
    data: dict[str, Any],
    windows: list[int],
    min_points: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    imputed = deepcopy(data)
    frames = imputed["frames"]
    metadata = imputed.get("metadata", {})
    frame_height = float(metadata.get("video_height", 1080))
    defaults = build_defaults(frames, frame_height)

    local_fill_counts = Counter()
    default_fill_counts = Counter()
    fill_details: list[dict[str, Any]] = []

    for frame in frames:
        frame_index = frame["frame_index"]

        ball = frame.get("ball")
        if isinstance(ball, dict) and is_valid_pair(ball.get("pixel")) and not is_valid_pair(ball.get("court")):
            predicted, info = estimate_court_position(frames, frame_index, ball["pixel"], windows, min_points)
            if predicted is not None and info is not None:
                ball["court"] = clamp_pair(predicted, allow_outside_baseline=False)
                local_fill_counts["ball_court"] += 1
                fill_details.append({"frame_index": frame_index, "field": "ball.court", **info})
            else:
                ball["court"] = default_ball_court(frame, defaults, frame_height)
                default_fill_counts["ball_court"] += 1
                fill_details.append({"frame_index": frame_index, "field": "ball.court", "method": "default"})

        for player in frame.get("players", []):
            feet_pixel = feet_pixel_from_bbox(player.get("bbox_pixel"))
            if feet_pixel is not None and not is_valid_pair(player.get("feet_court")):
                predicted, info = estimate_court_position(frames, frame_index, feet_pixel, windows, min_points)
                if predicted is not None and info is not None:
                    player["feet_court"] = clamp_pair(predicted, allow_outside_baseline=True)
                    local_fill_counts["player_feet_court"] += 1
                    fill_details.append(
                        {
                            "frame_index": frame_index,
                            "field": f"players[{player.get('id')}].feet_court",
                            **info,
                        }
                    )
                else:
                    player["feet_court"] = default_player_feet(player.get("id"), defaults)
                    default_fill_counts["player_feet_court"] += 1
                    fill_details.append(
                        {
                            "frame_index": frame_index,
                            "field": f"players[{player.get('id')}].feet_court",
                            "method": "default",
                        }
                    )

        events = frame.get("events", {})
        if is_valid_pair(events.get("bounce_pixel")) and not is_valid_pair(events.get("bounce_court")):
            predicted, info = estimate_court_position(frames, frame_index, events["bounce_pixel"], windows, min_points)
            if predicted is not None and info is not None:
                events["bounce_court"] = clamp_pair(predicted, allow_outside_baseline=False)
                local_fill_counts["bounce_court"] += 1
                fill_details.append({"frame_index": frame_index, "field": "events.bounce_court", **info})
            else:
                events["bounce_court"] = default_bounce_court(frame, defaults, frame_height)
                default_fill_counts["bounce_court"] += 1
                fill_details.append({"frame_index": frame_index, "field": "events.bounce_court", "method": "default"})

    report = {
        "windows": windows,
        "min_points": min_points,
        "defaults": defaults,
        "before": build_missing_stats(data["frames"]),
        "after": build_missing_stats(frames),
        "local_fill_counts": dict(local_fill_counts),
        "default_fill_counts": dict(default_fill_counts),
        "sample_fill_details": fill_details[:200],
        "total_fill_events": len(fill_details),
    }
    return imputed, report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Impute missing court-coordinate values in match_frames.json.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT, help="Path to source match_frames.json.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Path to output imputed JSON.")
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT, help="Path to output report JSON.")
    parser.add_argument(
        "--windows",
        type=int,
        nargs="+",
        default=[2, 4, 6, 10, 15],
        help="Symmetric frame windows to try, in order.",
    )
    parser.add_argument(
        "--min-points",
        type=int,
        default=4,
        help="Minimum nearby pixel->court correspondences required before fitting.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    data = load_json(args.input)
    imputed, report = impute_match_frames(data, args.windows, args.min_points)

    save_json(args.output, imputed, pretty=False)
    save_json(args.report, report, pretty=True)

    print(f"Source kept untouched: {args.input}")
    print(f"Imputed JSON written to: {args.output}")
    print(f"Report written to: {args.report}")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
