"""Video-backed curved-net localization for production net-hit detection.

The functions here only load the court model. Ball coordinates are supplied by
the caller so the main pipeline can reuse its existing ball-tracking result.
"""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any, Sequence

import cv2
import numpy as np
import torch

from cv.config import DEFAULT_COURT_MODEL_PATH
from cv.court.keypoints import get_matrix_from_model_with_ransac
from cv.court.reference import CourtReference
from cv.device import resolve_torch_device
from cv.models.court_detection import BallTrackerNet

from .curved_detector import CurvedNetHitConfig, detect_curved_net_hits, event_to_json, normalize_track
from .curved_geometry import NetBandConfig, NetBandModel, fit_net_band_from_samples


def _load_court_model(model_path: str | Path, device: torch.device) -> BallTrackerNet:
    model = BallTrackerNet(out_channels=15).to(device)
    model.load_state_dict(torch.load(str(model_path), map_location=device, weights_only=True))
    model.eval()
    return model


def extract_net_calibration_inputs(
    input_video: str | Path,
    *,
    court_model_path: str | Path = DEFAULT_COURT_MODEL_PATH,
    device: str | torch.device | None = "auto",
    start_frame: int = 0,
    end_frame: int | None = None,
    calibration_stride: int = 20,
    max_calibration_frames: int = 30,
) -> dict[str, Any]:
    """Extract sampled frames and court geometry needed to localize the net."""

    video_path = Path(input_video)
    if not video_path.is_file():
        raise FileNotFoundError(f"Input video not found: {video_path}")
    if calibration_stride <= 0 or max_calibration_frames <= 0:
        raise ValueError("calibration_stride and max_calibration_frames must be positive")

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Could not open video: {video_path}")
    fps = float(cap.get(cv2.CAP_PROP_FPS))
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    if fps <= 0 or total_frames <= 0 or frame_width <= 0 or frame_height <= 0:
        cap.release()
        raise RuntimeError("Invalid video metadata")

    start_frame = max(0, int(start_frame))
    final_frame = total_frames if end_frame is None else min(max(start_frame, int(end_frame)), total_frames)
    if start_frame >= final_frame:
        cap.release()
        raise ValueError("Selected video frame range is empty")
    cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)

    selected_device = resolve_torch_device(device)
    court_reference = CourtReference()
    court_model = _load_court_model(court_model_path, selected_device)
    frames: list[np.ndarray] = []
    matrices: list[np.ndarray | None] = []
    keypoints: list[list[Any] | None] = []
    frame_idx = start_frame
    processed = 0
    try:
        while frame_idx < final_frame:
            ok, frame = cap.read()
            if not ok:
                break
            if processed % calibration_stride == 0 and len(frames) < max_calibration_frames:
                try:
                    matrix, points = get_matrix_from_model_with_ransac(
                        frame, court_model, selected_device, court_reference
                    )
                except Exception:
                    matrix, points = None, None
                frames.append(frame.copy())
                matrices.append(matrix)
                keypoints.append(points)
            frame_idx += 1
            processed += 1
    finally:
        cap.release()

    return {
        "fps": fps,
        "total_frames": total_frames,
        "frame_width": frame_width,
        "frame_height": frame_height,
        "start_frame": start_frame,
        "end_frame": frame_idx,
        "processed_frames": processed,
        "frames": frames,
        "matrices": matrices,
        "keypoints": keypoints,
    }


def run_curved_net_hit_detection(
    input_video: str | Path,
    ball_track: Sequence[Any],
    *,
    court_model_path: str | Path = DEFAULT_COURT_MODEL_PATH,
    device: str | torch.device | None = "auto",
    start_frame: int = 0,
    end_frame: int | None = None,
    calibration_stride: int = 20,
    max_calibration_frames: int = 30,
    net_config: NetBandConfig | None = None,
    detector_config: CurvedNetHitConfig | None = None,
) -> dict[str, Any]:
    """Detect net hits from a full-video aligned ball track and automatic net model."""

    extracted = extract_net_calibration_inputs(
        input_video,
        court_model_path=court_model_path,
        device=device,
        start_frame=start_frame,
        end_frame=end_frame,
        calibration_stride=calibration_stride,
        max_calibration_frames=max_calibration_frames,
    )
    if len(ball_track) < extracted["end_frame"]:
        raise ValueError(
            f"Ball track has {len(ball_track)} frames but the selected video range ends at frame "
            f"{extracted['end_frame']}"
        )
    selected_track = normalize_track(ball_track[extracted["start_frame"] : extracted["end_frame"]])
    net_model = fit_net_band_from_samples(
        extracted["frames"],
        extracted["matrices"],
        (extracted["frame_width"], extracted["frame_height"]),
        config=net_config,
        keypoints=extracted["keypoints"],
    )
    config = detector_config or CurvedNetHitConfig(fps=extracted["fps"])
    config.fps = extracted["fps"]
    config.band_margin_px = max(config.band_margin_px, net_model.band_margin_px)
    events = detect_curved_net_hits(selected_track, net_model, config)
    for event in events:
        event.frame += extracted["start_frame"]
        event.time_sec = round(event.frame / extracted["fps"], 3)

    return {
        "input_video_path": str(Path(input_video).resolve()),
        "fps": extracted["fps"],
        "total_frames": extracted["total_frames"],
        "start_frame": extracted["start_frame"],
        "end_frame": extracted["end_frame"],
        "processed_frames": extracted["processed_frames"],
        "frame_size": {"width": extracted["frame_width"], "height": extracted["frame_height"]},
        "net_model": net_model.to_json(),
        "net_hit_count": len(events),
        "events": [event_to_json(event) for event in events],
        "parameters": {"net": asdict(net_config or NetBandConfig()), "detector": asdict(config)},
        "ball_track": [None if point is None else [point[0], point[1]] for point in selected_track],
    }
