import csv
import json
from typing import Any, List, Optional, Tuple

from .detector import Point, clean_point, normalize_track


def load_track_from_json(path: str) -> Tuple[List[Point], Optional[float], Optional[int]]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if isinstance(data, list):
        return normalize_track(data), None, None

    if isinstance(data.get("ball_coords"), list):
        indexed: dict[int, Any] = {}
        for position, record in enumerate(data["ball_coords"]):
            if not isinstance(record, dict):
                raise ValueError("Each ball_coords item must be an object")
            try:
                frame_index = int(record.get("frame_index", position))
            except (TypeError, ValueError) as error:
                raise ValueError("ball_coords.frame_index must be an integer") from error
            if frame_index < 0 or frame_index in indexed:
                raise ValueError("ball_coords.frame_index values must be unique non-negative integers")
            indexed[frame_index] = record.get("pixel")

        metadata = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}
        dense_track = [indexed.get(frame) for frame in range(max(indexed) + 1)] if indexed else []
        return normalize_track(dense_track), metadata.get("fps"), metadata.get("video_width")

    for key in ("ball_track", "coords", "track", "ball_positions"):
        if key in data:
            frame_width = None
            frame_size = data.get("frame_size")
            if isinstance(frame_size, dict):
                frame_width = frame_size.get("width")
            return normalize_track(data[key]), data.get("fps"), frame_width

    raise ValueError("JSON must contain one of: ball_track, coords, track, ball_positions")


def load_track_from_csv(path: str) -> List[Point]:
    coords: List[Point] = []
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise ValueError("CSV must have headers")

        x_key = "x" if "x" in reader.fieldnames else "ball_x"
        y_key = "y" if "y" in reader.fieldnames else "ball_y"
        for row in reader:
            coords.append(clean_point((row.get(x_key), row.get(y_key))))
    return coords
