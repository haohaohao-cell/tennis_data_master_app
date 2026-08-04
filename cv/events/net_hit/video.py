import json
import os
from dataclasses import asdict
from typing import List, Optional, Tuple

import cv2

from .detector import NetHitConfig, detect_net_hits, make_horizontal_net_line


Point = Optional[Tuple[float, float]]


def choose_device(device: str) -> str:
    del device
    return "tensorflow"


def extract_ball_track(
    video_path: str,
    model_path: str,
    device: str,
    start_frame: int = 0,
    end_frame: Optional[int] = None,
) -> dict:
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise FileNotFoundError(f"Unable to open video: {video_path}")

    fps = float(cap.get(cv2.CAP_PROP_FPS))
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    if start_frame > 0:
        cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)

    cap.release()
    try:
        from cv.models.ball_tracking.gridtracknet import (
            GridTrackNet,
            extract_gridtracknet_coords,
            load_gridtracknet_h5,
        )
    except ModuleNotFoundError as exc:
        raise RuntimeError("Net-hit detection with GridTrackNet requires TensorFlow.") from exc

    grid_model = GridTrackNet()
    load_gridtracknet_h5(grid_model, model_path)
    records, _ = extract_gridtracknet_coords(video_path, grid_model)
    effective_end = min(end_frame, len(records)) if end_frame is not None else len(records)
    effective_start = min(max(start_frame, 0), effective_end)
    coords: List[Point] = [
        tuple(record["pixel"]) if record.get("pixel") is not None else None
        for record in records[effective_start:effective_end]
    ]
    frame_idx = effective_end
    processed_frames = len(coords)
    return {
        "fps": fps,
        "total_frames": total_frames,
        "start_frame": start_frame,
        "end_frame": frame_idx,
        "processed_frames": processed_frames,
        "frame_width": frame_width,
        "frame_height": frame_height,
        "coords": coords,
        "device": device,
    }


def run_video_net_hit_detection(
    input_video: str,
    model_path: str,
    device: str = "auto",
    start_frame: int = 0,
    end_frame: Optional[int] = None,
    net_y: Optional[float] = None,
    net_line: Optional[Tuple[float, float, float, float]] = None,
    near_net_px: float = 35.0,
    min_confidence: float = 0.55,
) -> dict:
    resolved_device = choose_device(device)
    track = extract_ball_track(
        input_video,
        model_path,
        resolved_device,
        start_frame=start_frame,
        end_frame=end_frame,
    )

    if net_line is not None:
        x1, y1, x2, y2 = net_line
        line = ((x1, y1), (x2, y2))
    elif net_y is not None:
        line = make_horizontal_net_line(net_y, track["frame_width"])
    else:
        raise ValueError("Either net_y or net_line must be provided")

    config = NetHitConfig(
        net_line=line,
        fps=track["fps"],
        near_net_px=near_net_px,
        min_confidence=min_confidence,
    )
    events = detect_net_hits(track["coords"], config)
    for event in events:
        event.frame += track["start_frame"]
        event.time_sec = round(event.frame / track["fps"], 3) if track["fps"] else 0.0

    return {
        "input_video_path": input_video,
        "model_path": model_path,
        "device": track["device"],
        "fps": track["fps"],
        "total_frames": track["total_frames"],
        "start_frame": track["start_frame"],
        "end_frame": track["end_frame"],
        "processed_frames": track["processed_frames"],
        "video_duration_sec": round(track["total_frames"] / track["fps"], 3) if track["fps"] else 0.0,
        "frame_size": {"width": track["frame_width"], "height": track["frame_height"]},
        "net_hit_count": len(events),
        "events": [asdict(event) for event in events],
        "parameters": asdict(config),
        "ball_track": [
            None if point is None else [round(point[0], 3), round(point[1], 3)]
            for point in track["coords"]
        ],
    }


def save_result_json(result: dict, output_json: str) -> None:
    output_dir = os.path.dirname(output_json)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
    with open(output_json, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
