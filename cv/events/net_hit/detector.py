import math
from dataclasses import dataclass
from statistics import median
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


Point = Optional[Tuple[float, float]]
Line = Tuple[Tuple[float, float], Tuple[float, float]]


@dataclass
class NetHitConfig:
    """Parameters for top-down single-camera net-hit detection."""

    net_line: Line
    fps: float = 25.0
    near_net_px: float = 35.0
    lookback_frames: int = 6
    lookahead_frames: int = 10
    min_side_motion_px: float = 3.0
    speed_drop_ratio: float = 0.45
    missing_after_frames: int = 5
    merge_gap_frames: int = 12
    min_confidence: float = 0.55


@dataclass
class NetHitEvent:
    frame: int
    time_sec: float
    confidence: float
    reason: str
    ball: Tuple[float, float]
    signed_distance_px: float
    details: Dict[str, Any]


def make_horizontal_net_line(net_y: float, frame_width: float = 99999.0) -> Line:
    return ((0.0, float(net_y)), (float(frame_width), float(net_y)))


def clean_point(point: Any) -> Point:
    if point is None:
        return None
    if isinstance(point, dict):
        x = point.get("x")
        y = point.get("y")
    else:
        if len(point) < 2:
            return None
        x, y = point[0], point[1]

    try:
        x = float(x)
        y = float(y)
    except (TypeError, ValueError):
        return None

    if not math.isfinite(x) or not math.isfinite(y):
        return None
    return (x, y)


def normalize_track(coords: Iterable[Any]) -> List[Point]:
    return [clean_point(point) for point in coords]


def interpolate_short_gaps(coords: Sequence[Point], max_gap_frames: int = 4) -> List[Point]:
    filled = list(coords)
    idx = 0
    while idx < len(filled):
        if filled[idx] is not None:
            idx += 1
            continue

        start = idx - 1
        while idx < len(filled) and filled[idx] is None:
            idx += 1
        end = idx
        gap = end - start - 1

        if start < 0 or end >= len(filled) or gap <= 0 or gap > max_gap_frames:
            continue
        if filled[start] is None or filled[end] is None:
            continue

        x0, y0 = filled[start]
        x1, y1 = filled[end]
        for offset in range(1, gap + 1):
            ratio = offset / (gap + 1)
            filled[start + offset] = (
                x0 + (x1 - x0) * ratio,
                y0 + (y1 - y0) * ratio,
            )
    return filled


def median_smooth(coords: Sequence[Point], window_size: int = 3) -> List[Point]:
    if window_size <= 1:
        return list(coords)

    half = window_size // 2
    smoothed = list(coords)
    for idx in range(len(coords)):
        window = [
            p
            for p in coords[max(0, idx - half): idx + half + 1]
            if p is not None
        ]
        if len(window) < 3:
            continue
        smoothed[idx] = (
            float(median([p[0] for p in window])),
            float(median([p[1] for p in window])),
        )
    return smoothed


def signed_distance_to_line(point: Tuple[float, float], line: Line) -> float:
    (x1, y1), (x2, y2) = line
    px, py = point
    dx = x2 - x1
    dy = y2 - y1
    length = math.hypot(dx, dy)
    if length == 0:
        raise ValueError("net_line points must be different")
    return ((px - x1) * dy - (py - y1) * dx) / length


def point_projection_ratio(point: Tuple[float, float], line: Line) -> float:
    (x1, y1), (x2, y2) = line
    px, py = point
    dx = x2 - x1
    dy = y2 - y1
    denom = dx * dx + dy * dy
    if denom == 0:
        raise ValueError("net_line points must be different")
    return ((px - x1) * dx + (py - y1) * dy) / denom


def point_distance(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def nearest_valid_index(coords: Sequence[Point], start: int, stop: int, step: int) -> Optional[int]:
    idx = start
    while 0 <= idx < len(coords) and ((step > 0 and idx <= stop) or (step < 0 and idx >= stop)):
        if coords[idx] is not None:
            return idx
        idx += step
    return None


def next_motion_index(
    signed_distances: Sequence[Optional[float]],
    frame: int,
    lookahead_frames: int,
    min_motion_px: float,
) -> Optional[int]:
    current = signed_distances[frame]
    if current is None:
        return None

    for idx in range(frame + 1, min(len(signed_distances), frame + lookahead_frames + 1)):
        dist = signed_distances[idx]
        if dist is None:
            continue
        if abs(dist - current) >= min_motion_px:
            return idx
    return None


def median_speed(coords: Sequence[Point], start: int, end: int) -> Optional[float]:
    speeds = []
    prev = None
    for idx in range(max(0, start), min(len(coords), end + 1)):
        point = coords[idx]
        if point is None:
            prev = None
            continue
        if prev is not None:
            speeds.append(point_distance(prev, point))
        prev = point
    if not speeds:
        return None
    return float(median(speeds))


def crosses_net_after(
    signed_distances: Sequence[Optional[float]],
    frame: int,
    initial_side: float,
    lookahead_frames: int,
    near_net_px: float,
) -> bool:
    side_sign = 1.0 if initial_side >= 0 else -1.0
    for idx in range(frame + 1, min(len(signed_distances), frame + lookahead_frames + 1)):
        dist = signed_distances[idx]
        if dist is None:
            continue
        if dist * side_sign < -near_net_px:
            return True
    return False


def detect_net_hits(coords: Sequence[Any], config: NetHitConfig) -> List[NetHitEvent]:
    track = median_smooth(interpolate_short_gaps(normalize_track(coords)), window_size=3)
    signed_distances = [
        signed_distance_to_line(point, config.net_line) if point is not None else None
        for point in track
    ]

    candidates: List[NetHitEvent] = []

    for frame, point in enumerate(track):
        if point is None:
            continue

        signed_dist = signed_distances[frame]
        if signed_dist is None or abs(signed_dist) > config.near_net_px:
            continue

        projection = point_projection_ratio(point, config.net_line)
        if projection < -0.1 or projection > 1.1:
            continue

        prev_idx = nearest_valid_index(
            track,
            frame - 1,
            max(0, frame - config.lookback_frames),
            -1,
        )
        next_idx = nearest_valid_index(
            track,
            frame + 1,
            min(len(track) - 1, frame + config.lookahead_frames),
            1,
        )
        next_turn_idx = next_motion_index(
            signed_distances,
            frame,
            config.lookahead_frames,
            config.min_side_motion_px,
        )
        if prev_idx is None:
            continue

        prev_dist = signed_distances[prev_idx]
        next_dist = signed_distances[next_idx] if next_idx is not None else None
        next_turn_dist = signed_distances[next_turn_idx] if next_turn_idx is not None else None
        if prev_dist is None:
            continue

        incoming_side_motion = signed_dist - prev_dist
        outgoing_side_motion = None if next_turn_dist is None else next_turn_dist - signed_dist
        approaching_net = abs(signed_dist) <= abs(prev_dist)

        reversed_near_net = (
            outgoing_side_motion is not None
            and incoming_side_motion * outgoing_side_motion < 0
            and abs(incoming_side_motion) >= config.min_side_motion_px
            and abs(outgoing_side_motion) >= config.min_side_motion_px
            and approaching_net
        )

        speed_before = median_speed(
            track,
            max(0, frame - config.lookback_frames),
            frame,
        )
        speed_after = median_speed(
            track,
            frame,
            min(len(track) - 1, frame + config.lookahead_frames),
        )
        speed_drop = (
            speed_before is not None
            and speed_after is not None
            and speed_before > 0
            and speed_after <= speed_before * config.speed_drop_ratio
        )

        missing_after = next_idx is None and any(
            idx < len(track) and track[idx] is None
            for idx in range(frame + 1, min(len(track), frame + config.missing_after_frames + 1))
        )
        crossed_after = crosses_net_after(
            signed_distances,
            frame,
            prev_dist,
            config.lookahead_frames,
            config.near_net_px,
        )
        stayed_same_side = not crossed_after and abs(prev_dist) > config.near_net_px * 0.6

        confidence = 0.0
        reasons = []
        if reversed_near_net:
            confidence += 0.42
            reasons.append("reversed_near_net")
        if speed_drop:
            confidence += 0.28
            reasons.append("speed_drop_near_net")
        if missing_after:
            confidence += 0.18
            reasons.append("ball_missing_after_net")
        if stayed_same_side:
            confidence += 0.18
            reasons.append("did_not_cross_net")
        if abs(signed_dist) <= config.near_net_px * 0.45:
            confidence += 0.08
            reasons.append("very_close_to_net")

        if crossed_after and not reversed_near_net:
            confidence -= 0.25
            reasons.append("crossed_net_after")

        confidence = max(0.0, min(1.0, confidence))
        if confidence < config.min_confidence:
            continue

        candidates.append(
            NetHitEvent(
                frame=frame,
                time_sec=round(frame / config.fps, 3) if config.fps > 0 else 0.0,
                confidence=round(confidence, 3),
                reason="+".join(reasons),
                ball=(round(point[0], 2), round(point[1], 2)),
                signed_distance_px=round(signed_dist, 2),
                details={
                    "prev_frame": prev_idx,
                    "next_frame": next_idx,
                    "next_turn_frame": next_turn_idx,
                    "prev_signed_distance_px": round(prev_dist, 2),
                    "next_signed_distance_px": None if next_dist is None else round(next_dist, 2),
                    "next_turn_signed_distance_px": None if next_turn_dist is None else round(next_turn_dist, 2),
                    "speed_before_px_per_frame": None if speed_before is None else round(speed_before, 2),
                    "speed_after_px_per_frame": None if speed_after is None else round(speed_after, 2),
                    "crossed_after": crossed_after,
                },
            )
        )

    return merge_events(candidates, config.merge_gap_frames)


def merge_events(events: Sequence[NetHitEvent], merge_gap_frames: int) -> List[NetHitEvent]:
    if not events:
        return []

    merged: List[NetHitEvent] = []
    group = [events[0]]
    for event in events[1:]:
        if event.frame - group[-1].frame <= merge_gap_frames:
            group.append(event)
        else:
            merged.append(max(group, key=lambda item: item.confidence))
            group = [event]
    merged.append(max(group, key=lambda item: item.confidence))
    return merged

