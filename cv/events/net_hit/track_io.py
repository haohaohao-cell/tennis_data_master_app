import csv
import json
from typing import List, Optional, Tuple

from .detector import Point, clean_point, normalize_track


def load_track_from_json(path: str) -> Tuple[List[Point], Optional[float], Optional[int]]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if isinstance(data, list):
        return normalize_track(data), None, None

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
