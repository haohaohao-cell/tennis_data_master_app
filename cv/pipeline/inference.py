"""End-to-end tennis analysis pipeline v2.

This version uses GridTrackNet for ball coordinates and keeps the existing
court/player/event orchestration:
1. Run frame-level detection / tracking / event inference.
2. Build an in-memory `match_frames` style payload.
3. Segment points with the custom heuristic from `split_video_by_point.py`.
4. Impute missing court coordinates.
5. Build final shot-level and point-level JSON payloads.

Primary backend entry point:
`run_inference_v2(input_video_path=...) -> (shots_json, points_json)`
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Callable

import cv2
import numpy as np
import torch
from tqdm import tqdm
from ultralytics import YOLO

from cv.analytics.player_distance import calculate_player_distances
from cv.analytics.rally import _build_rally_analysis
from cv.analytics.shot_speed import calculate_shot_speeds_true_meters
from cv.builders.imputation import impute_match_frames
from cv.builders.match import (
    build_match_frames_payload,
    build_match_tactics_payload,
    build_metadata,
    build_points_index_payload,
    build_shots_and_points_payloads,
)
from cv.builders.shots import slugify_upload_id
from cv.config import (
    DEFAULT_COURT_MODEL_PATH as COURT_MODEL_PATH,
    DEFAULT_GRIDTRACKNET_MODEL_PATH as BALL_MODEL_PATH,
    DEFAULT_PLAYER_MODEL_PATH as PLAYER_MODEL_PATH,
)
from cv.device import get_torch_device
from cv.court.keypoints import get_matrix_from_model_with_ransac, project_reference_keypoints
from cv.court.reference import CourtReference
from cv.court.stability import estimate_stable_court_matrix
from cv.events.hit_detection import standalone_get_ball_shot_frames
from cv.events.in_out import evaluate_bounces_in_out
from cv.events.net_hit.detector import NetHitConfig, detect_net_hits, make_horizontal_net_line
from cv.events.shot_classifier import ShotClassifier
from cv.models.court_detection import BallTrackerNet
from cv.segmentation.points import SegmentationConfig
from cv.tracking.bounce import BounceDetectorManager
from cv.tracking.person import PersonTrackerManager


DEFAULT_BALL_MODEL_PATH = str(BALL_MODEL_PATH)
DEFAULT_PLAYER_MODEL_PATH = str(PLAYER_MODEL_PATH)
DEFAULT_COURT_MODEL_PATH = str(COURT_MODEL_PATH)
MIN_VISIBLE_COURT_KEYPOINTS = 9
CONSECUTIVE_NO_COURT_END_FRAMES = 10
COURT_STABILITY_SAMPLE_COUNT = 15
COURT_STABILITY_MAX_DEVIATION_PX = 30.0
COURT_STABILITY_MIN_CONSENSUS_SIZE = 5


class YoloDetectionWrapper:
    def __init__(self, model_path: str, device: str) -> None:
        self.model = YOLO(model_path)
        self.model.to(device)

    def _detect(self, frame: np.ndarray, person_min_score: float = 0.5) -> tuple[list[list[float]], list[float]]:
        results = self.model(frame, classes=[0], conf=person_min_score, verbose=False)
        boxes: list[list[float]] = []
        probs: list[float] = []
        for result in results:
            for box in result.boxes:
                boxes.append(box.xyxy[0].cpu().numpy().tolist())
                probs.append(float(box.conf[0]))
        return boxes, probs


class DummyCourtDetector:
    def __init__(self, court_ref: Any) -> None:
        self.court_reference = court_ref
        self.court_warp_matrix: list[np.ndarray] = []



def save_json(path: Path, payload: dict[str, Any], *, pretty: bool = True) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        if pretty:
            json.dump(payload, handle, ensure_ascii=False, indent=4)
        else:
            json.dump(payload, handle, ensure_ascii=False, separators=(",", ":"))


def run_inference_v2(
    input_video_path: str | Path,
    *,
    ball_model_path: str = DEFAULT_BALL_MODEL_PATH,
    player_model_path: str = DEFAULT_PLAYER_MODEL_PATH,
    court_model_path: str = DEFAULT_COURT_MODEL_PATH,
    upload_id: str | None = None,
    output_dir: str | Path | None = None,
    segmentation_config: SegmentationConfig | None = None,
    persist_intermediate_json: bool = False,
    persist_final_json: bool = False,
    progress_callback: Callable[[str, int, int, str | None], None] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Run the full v2 pipeline and return `(shots_json, points_json)`.

    The returned payloads are intended to be written into the `shots` and
    `points` database tables by the backend layer.
    """

    device = get_torch_device()
    input_video_path = str(input_video_path)
    effective_upload_id = upload_id or slugify_upload_id(Path(input_video_path).name)
    output_dir_path = Path(output_dir) if output_dir is not None else Path(input_video_path).resolve().parent

    cap = cv2.VideoCapture(input_video_path)
    if not cap.isOpened():
        raise FileNotFoundError(f"Video file could not be opened: {input_video_path}")

    fps = float(cap.get(cv2.CAP_PROP_FPS))
    frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if fps <= 0 or total_frames <= 0:
        cap.release()
        raise RuntimeError("Invalid video metadata detected.")

    court_ref_instance = CourtReference()
    court_ref_instance.build_court_reference()
    dummy_court = DummyCourtDetector(court_ref_instance)

    court_model = BallTrackerNet(out_channels=15).to(device)
    court_model.load_state_dict(torch.load(court_model_path, map_location="cpu", weights_only=True))
    court_model.eval()

    def detect_court_matrix(frame: np.ndarray) -> np.ndarray | None:
        matrix, _ = get_matrix_from_model_with_ransac(frame, court_model, device, court_ref_instance)
        return matrix

    if progress_callback is not None:
        progress_callback("court_stability", 0, COURT_STABILITY_SAMPLE_COUNT, "正在建立稳定球场坐标系")
    stable_court = estimate_stable_court_matrix(
        cap,
        detect_court_matrix,
        total_frames=total_frames,
        sample_count=COURT_STABILITY_SAMPLE_COUNT,
        court_ref=court_ref_instance,
        max_deviation_px=COURT_STABILITY_MAX_DEVIATION_PX,
        min_consensus_size=COURT_STABILITY_MIN_CONSENSUS_SIZE,
    )
    stable_court_matrix = stable_court.matrix
    stable_court_points = project_reference_keypoints(stable_court_matrix, court_ref_instance)
    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
    if progress_callback is not None:
        progress_callback(
            "court_stability",
            COURT_STABILITY_SAMPLE_COUNT,
            COURT_STABILITY_SAMPLE_COUNT,
            "稳定球场坐标系已建立",
        )

    ball_model_file = Path(ball_model_path)
    if not ball_model_file.exists():
        raise FileNotFoundError(
            "GridTrackNet H5 model not found. Set --ball_model_path or GRIDTRACKNET_MODEL_PATH. "
            f"Current value: {ball_model_file}"
        )
    try:
        from cv.models.ball_tracking.gridtracknet import (
            GridTrackNet,
            extract_gridtracknet_coords,
            load_gridtracknet_h5,
        )
    except ModuleNotFoundError as exc:
        raise RuntimeError("GridTrackNet production inference requires TensorFlow.") from exc

    gridtracknet_model = GridTrackNet()
    load_gridtracknet_h5(gridtracknet_model, ball_model_file)

    def report_gridtracknet_progress(current: int, total: int) -> None:
        if progress_callback is not None:
            progress_callback("ball_tracking", current, total, "正在运行 GridTrackNet 球坐标推理")

    if progress_callback is not None:
        progress_callback("ball_tracking", 0, total_frames, "正在运行 GridTrackNet 球坐标推理")
    grid_ball_records, _ = extract_gridtracknet_coords(
        input_video_path,
        gridtracknet_model,
        confidence_threshold=0.5,
        progress_callback=report_gridtracknet_progress if progress_callback is not None else None,
    )
    if len(grid_ball_records) != total_frames:
        raise RuntimeError(
            "GridTrackNet returned coordinates for an unexpected number of frames: "
            f"expected {total_frames}, got {len(grid_ball_records)}"
        )
    grid_ball_coords = [
        tuple(record["pixel"]) if record.get("pixel") is not None else None
        for record in grid_ball_records
    ]
    yolo_detector = YoloDetectionWrapper(model_path=player_model_path, device=device)
    person_tracker = PersonTrackerManager(detection_model=yolo_detector)

    court_points_all: list[Any] = []
    court_matrices_all: list[np.ndarray | None] = []
    player_detections: dict[int, dict[int, list[float]]] = {}
    player_detections_court: dict[int, dict[int, list[float] | None]] = {}
    ball_detections_court: dict[int, list[float] | None] = {}
    raw_coords: list[Any] = []

    frame_idx = 0
    last_good_matrix = stable_court_matrix
    track_id_to_player_id: dict[int, int] = {}
    progress_update_interval = max(1, total_frames // 200)

    progress = tqdm(total=total_frames, desc="run_inference_v2 pass1")
    if progress_callback is not None:
        progress_callback("pass1", 0, total_frames, "正在读取视频帧")
    while True:
        ret, frame = cap.read()
        if not ret:
            break

        court_points_all.append(stable_court_points)
        court_matrices_all.append(stable_court_matrix)
        dummy_court.court_warp_matrix.append(last_good_matrix)

        tracks = person_tracker.update(frame, dummy_court)
        frame_player_dict: dict[int, list[float]] = {}

        active_confirmed = {track.track_id for track in tracks if track.is_confirmed()}
        already_used = {player_id for track_id, player_id in track_id_to_player_id.items() if track_id in active_confirmed}

        for track in tracks:
            if not track.is_confirmed():
                continue
            if track.track_id in track_id_to_player_id:
                continue

            role = track.det_class
            candidate = 1 if role == "bottom_player" else 2 if role == "top_player" else None
            if candidate is not None and candidate not in already_used:
                track_id_to_player_id[track.track_id] = candidate
                already_used.add(candidate)

        for track in tracks:
            if not track.is_confirmed():
                continue
            player_id = track_id_to_player_id.get(track.track_id)
            if player_id is not None:
                frame_player_dict[player_id] = [float(value) for value in track.to_ltrb()]

        player_detections[frame_idx] = frame_player_dict

        player_court_dict: dict[int, list[float] | None] = {}
        for player_id, bbox in frame_player_dict.items():
            feet_pixel = [(bbox[0] + bbox[2]) / 2.0, bbox[3]]
            try:
                h_inv = np.linalg.inv(last_good_matrix)
                point = np.array([[feet_pixel[0]], [feet_pixel[1]], [1.0]])
                transformed = np.dot(h_inv, point)
                canvas_x = transformed[0, 0] / transformed[2, 0]
                canvas_y = transformed[1, 0] / transformed[2, 0]
                real_x = (canvas_x - 120.0) / 30.0
                real_y = (canvas_y - 150.0) / 30.0
                player_court_dict[player_id] = [round(float(real_x), 2), round(float(real_y), 2)]
            except Exception:
                player_court_dict[player_id] = None
        player_detections_court[frame_idx] = player_court_dict

        ball_xy = grid_ball_coords[frame_idx]
        raw_coords.append(ball_xy)

        if ball_xy is not None:
            try:
                h_inv = np.linalg.inv(last_good_matrix)
                point = np.array([[ball_xy[0]], [ball_xy[1]], [1.0]])
                transformed = np.dot(h_inv, point)
                canvas_x = transformed[0, 0] / transformed[2, 0]
                canvas_y = transformed[1, 0] / transformed[2, 0]
                real_x = (canvas_x - 120.0) / 30.0
                real_y = (canvas_y - 150.0) / 30.0
                ball_detections_court[frame_idx] = [round(float(real_x), 2), round(float(real_y), 2)]
            except Exception:
                ball_detections_court[frame_idx] = None

        frame_idx += 1
        progress.update(1)
        if progress_callback is not None and (frame_idx % progress_update_interval == 0 or frame_idx == total_frames):
            progress_callback("pass1", frame_idx, total_frames, "正在逐帧分析视频")

    cap.release()
    progress.close()
    if progress_callback is not None:
        progress_callback("postprocess", 0, 4, "正在后处理轨迹")

    # GridTrackNet coordinates are the production source of truth. Do not let
    # legacy trajectory cleanup remove real hit or bounce discontinuities.
    final_coords = list(raw_coords)
    bounce_detector = BounceDetectorManager(score_thresh=15.0)
    raw_bounces, _, _ = bounce_detector.detect(final_coords)
    enhanced_bounces = bounce_detector.enhance_subpixel(final_coords, raw_bounces)
    if progress_callback is not None:
        progress_callback("postprocess", 1, 4, "正在检测落点候选")

    adapted_for_detector: list[dict[int, list[float]]] = []
    adapted_for_classifier: dict[int, dict[int, list[float]]] = {}
    for index, point in enumerate(final_coords):
        if point is not None and not np.isnan(point).any():
            cx, cy = float(point[0]), float(point[1])
            adapted_for_detector.append({1: [cx - 5, cy - 5, cx + 5, cy + 5]})
            adapted_for_classifier[index] = {1: [cx, cy]}
        else:
            adapted_for_detector.append({})
            adapted_for_classifier[index] = {}

    ball_shot_frames, candidate_frames, _ = standalone_get_ball_shot_frames(
        adapted_for_detector,
        player_detections,
        frame_height,
    )
    shot_frames_set = set(ball_shot_frames)

    suppression_window = 6
    final_valid_bounces = []
    for bounce in enhanced_bounces:
        bounce_frame = bounce.get("frame")
        if bounce_frame is not None and not any(abs(bounce_frame - hit_frame) <= suppression_window for hit_frame in shot_frames_set):
            final_valid_bounces.append(bounce)

    final_valid_bounces = evaluate_bounces_in_out(
        bounces=final_valid_bounces,
        court_matrices_all=court_matrices_all,
        match_type="singles",
        padding_x=120,
        padding_y=150,
        ppm=30,
    )
    if progress_callback is not None:
        progress_callback("postprocess", 2, 4, "正在判断界内界外")

    court_lines_pixel_y: dict[int, dict[str, int]] = {}
    player_pixel_bottom: dict[int, dict[int, list[float]]] = {}
    for index in range(frame_idx):
        points = court_points_all[index]
        valid_y = [point[1] for point in points if point is not None and point[1] is not None]
        if valid_y:
            top_y = min(valid_y)
            bottom_y = max(valid_y)
            net_y = int(top_y + (bottom_y - top_y) * 0.35)
            court_lines_pixel_y[index] = {
                "net_y": net_y,
                "top_baseline_y": int(top_y),
                "bottom_baseline_y": int(bottom_y),
            }
        else:
            court_lines_pixel_y[index] = court_lines_pixel_y.get(
                index - 1,
                {"net_y": int(frame_height * 0.45), "top_baseline_y": 200, "bottom_baseline_y": 900},
            )

        player_frame = player_detections.get(index, {})
        player_pixel_bottom[index] = {
            player_id: [(bbox[0] + bbox[2]) / 2.0, bbox[3]]
            for player_id, bbox in player_frame.items()
            if bbox is not None
        }

    median_net_y = None
    if court_lines_pixel_y:
        net_ys = [item["net_y"] for item in court_lines_pixel_y.values() if "net_y" in item]
        if net_ys:
            median_net_y = int(np.median(net_ys))

    net_hit_events: list[Any] = []
    if median_net_y is not None:
        net_config = NetHitConfig(
            net_line=make_horizontal_net_line(median_net_y, frame_width),
            fps=fps,
            near_net_px=35.0,
            min_confidence=0.55,
        )
        net_hit_events = detect_net_hits(final_coords, net_config)
    if progress_callback is not None:
        progress_callback("postprocess", 3, 4, "正在识别击球类型")

    shot_classifier = ShotClassifier()
    shot_classifications = shot_classifier.classify_shots(
        player_pixel_detections=player_pixel_bottom,
        ball_pixel_detections=adapted_for_classifier,
        ball_shot_frames=ball_shot_frames,
        frame_height=frame_height,
        court_lines_pixel_y=court_lines_pixel_y,
    )

    shot_speed = calculate_shot_speeds_true_meters(
        shot_classifications=shot_classifications,
        bounces=final_valid_bounces,
        player_detections=player_detections,
        court_matrices_all=court_matrices_all,
        fps=fps,
        min_speed_kmh=30.0,
    )
    player_distances = calculate_player_distances(player_detections, court_matrices_all)
    rally_analysis = _build_rally_analysis(
        fps=fps,
        total_frames=frame_idx,
        ball_shot_frames=ball_shot_frames,
        bounce_frames=[bounce.get("frame") for bounce in final_valid_bounces],
        shot_classifications=shot_classifications,
        shot_speeds=shot_speed,
        cumulative_distances=player_distances,
        player_detections=player_detections,
        player_detections_court=player_detections_court,
        ball_detections=adapted_for_detector,
        ball_detections_court=ball_detections_court,
        bounces=final_valid_bounces,
        court_matrices=court_matrices_all,
    )
    if progress_callback is not None:
        progress_callback("postprocess", 4, 4, "正在生成比赛分析数据")

    metadata = build_metadata(fps, frame_width, frame_height, frame_idx)
    metadata["court_stability"] = {
        "source_frame": stable_court.frame_index,
        "consensus_frames": list(stable_court.consensus_frame_indices),
        "median_deviation_px": round(stable_court.median_deviation_px, 4),
        "max_deviation_px": round(stable_court.max_deviation_px, 4),
        "homography": stable_court_matrix.tolist(),
        "keypoints": [
            [round(float(point[0]), 2), round(float(point[1]), 2)]
            for point in stable_court_points
        ],
    }
    match_tactics_payload = build_match_tactics_payload(metadata, rally_analysis, net_hit_events)
    match_frames_payload = build_match_frames_payload(
        metadata,
        fps,
        court_points_all,
        court_matrices_all,
        adapted_for_detector,
        player_detections,
        final_valid_bounces,
        shot_frames_set,
        shot_classifications,
        net_hit_events,
    )
    if progress_callback is not None:
        progress_callback("build", 1, 3, "正在切分回合")

    points_index_payload = build_points_index_payload(match_frames_payload, input_video_path, config=segmentation_config)
    imputed_frames_payload, imputation_report = impute_match_frames(match_frames_payload, windows=[2, 4, 6, 10, 15], min_points=4)
    if progress_callback is not None:
        progress_callback("build", 2, 3, "正在生成回合和击球结果")
    intermediate_payload, shots_payload, points_payload = build_shots_and_points_payloads(
        imputed_frames_payload,
        points_index_payload,
        match_tactics_payload,
        effective_upload_id,
    )
    if progress_callback is not None:
        progress_callback("build", 3, 3, "正在整理最终结果")

    if output_dir_path and persist_final_json:
        save_json(output_dir_path / "shots_v2.json", shots_payload, pretty=True)
        save_json(output_dir_path / "points_v2.json", points_payload, pretty=True)

    if output_dir_path and persist_intermediate_json:
        save_json(output_dir_path / "match_tactics_v2.json", match_tactics_payload, pretty=True)
        save_json(output_dir_path / "match_frames_v2.json", match_frames_payload, pretty=False)
        save_json(output_dir_path / "match_frames_v2_imputed.json", imputed_frames_payload, pretty=False)
        save_json(output_dir_path / "match_frames_v2_imputation_report.json", imputation_report, pretty=True)
        save_json(output_dir_path / "points_heuristic_v2_index_v2.json", points_index_payload, pretty=True)
        save_json(output_dir_path / "shots_v2_intermediate.json", intermediate_payload, pretty=True)

    return shots_payload, points_payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the end-to-end tennis analysis v2 pipeline.")
    parser.add_argument("--input_video_path", type=str, required=True, help="Path to the source tennis match video.")
    parser.add_argument("--ball_model_path", type=str, default=DEFAULT_BALL_MODEL_PATH)
    parser.add_argument("--player_model_path", type=str, default=DEFAULT_PLAYER_MODEL_PATH)
    parser.add_argument("--court_model_path", type=str, default=DEFAULT_COURT_MODEL_PATH)
    parser.add_argument("--output_dir", type=str, default=None, help="Directory for output JSON files.")
    parser.add_argument("--persist_intermediate_json", action="store_true", help="Also save intermediate JSON payloads.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    shots_payload, points_payload = run_inference_v2(
        input_video_path=args.input_video_path,
        ball_model_path=args.ball_model_path,
        player_model_path=args.player_model_path,
        court_model_path=args.court_model_path,
        output_dir=args.output_dir,
        persist_intermediate_json=args.persist_intermediate_json,
        persist_final_json=True,
    )
    print(json.dumps({"shots": shots_payload["metadata"], "points": points_payload["metadata"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
