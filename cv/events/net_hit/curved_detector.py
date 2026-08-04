from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from statistics import median
from typing import Any, Sequence

from .curved_geometry import NetBandModel, Point, signed_distance_to_line


TrackPoint = Point | None


@dataclass
class CurvedNetHitConfig:
    fps: float = 25.0
    lookback_frames: int = 6
    lookahead_frames: int = 12
    min_normal_motion_px: float = 3.0
    min_drop_after_px: float = 6.0
    speed_drop_ratio: float = 0.50
    missing_after_frames: int = 5
    merge_gap_frames: int = 12
    min_confidence: float = 0.55
    band_margin_px: float = 10.0
    require_failure_cue: bool = True


@dataclass
class CurvedNetHitEvent:
    frame: int
    time_sec: float
    confidence: float
    reason: str
    ball: Point
    signed_distance_px: float
    distance_to_band_px: float
    details: dict[str, Any]


def clean_point(point: Any) -> TrackPoint:
    if point is None:
        return None
    try:
        if isinstance(point, dict):
            x = point.get("x")
            y = point.get("y")
        else:
            if len(point) < 2:
                return None
            x, y = point[0], point[1]
        x = float(x)
        y = float(y)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(x) or not math.isfinite(y):
        return None
    return (x, y)


def normalize_track(coords: Sequence[Any]) -> list[TrackPoint]:
    return [clean_point(point) for point in coords]


def interpolate_short_gaps(coords: Sequence[TrackPoint], max_gap_frames: int = 4) -> list[TrackPoint]:
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

        p0 = filled[start]
        p1 = filled[end]
        if p0 is None or p1 is None:
            continue
        for offset in range(1, gap + 1):
            ratio = offset / (gap + 1)
            filled[start + offset] = (
                p0[0] + (p1[0] - p0[0]) * ratio,
                p0[1] + (p1[1] - p0[1]) * ratio,
            )
    return filled


def median_smooth(coords: Sequence[TrackPoint], window_size: int = 3) -> list[TrackPoint]:
    if window_size <= 1:
        return list(coords)
    half = window_size // 2
    smoothed = list(coords)
    for idx in range(len(coords)):
        window = [p for p in coords[max(0, idx - half) : idx + half + 1] if p is not None]
        if len(window) < 3:
            continue
        smoothed[idx] = (
            float(median([p[0] for p in window])),
            float(median([p[1] for p in window])),
        )
    return smoothed


def point_distance(a: Point, b: Point) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def nearest_valid_index(coords: Sequence[TrackPoint], start: int, stop: int, step: int) -> int | None:
    idx = start
    while 0 <= idx < len(coords) and ((step > 0 and idx <= stop) or (step < 0 and idx >= stop)):
        if coords[idx] is not None:
            return idx
        idx += step
    return None


def median_speed(coords: Sequence[TrackPoint], start: int, end: int) -> float | None:
    speeds: list[float] = []
    previous: TrackPoint = None
    for idx in range(max(0, start), min(len(coords), end + 1)):
        point = coords[idx]
        if point is None:
            previous = None
            continue
        if previous is not None:
            speeds.append(point_distance(previous, point))
        previous = point
    if not speeds:
        return None
    return float(median(speeds))


def crosses_lower_line_after(
    distances: Sequence[float | None],
    frame: int,
    initial_distance: float,
    lookahead_frames: int,
    margin_px: float,
) -> bool:
    sign = 1.0 if initial_distance >= 0 else -1.0
    for idx in range(frame + 1, min(len(distances), frame + lookahead_frames + 1)):
        dist = distances[idx]
        if dist is None:
            continue
        if dist * sign < -margin_px:
            return True
    return False


def drops_after(
    coords: Sequence[TrackPoint],
    frame: int,
    lookahead_frames: int,
    min_drop_px: float,
) -> bool:
    current = coords[frame]
    if current is None:
        return False
    for idx in range(frame + 1, min(len(coords), frame + lookahead_frames + 1)):
        point = coords[idx]
        if point is None:
            continue
        if point[1] - current[1] >= min_drop_px:
            return True
    return False


def detect_curved_net_hits(
    coords: Sequence[Any],
    net_model: NetBandModel,
    config: CurvedNetHitConfig | None = None,
) -> list[CurvedNetHitEvent]:
    config = config or CurvedNetHitConfig()
    track = median_smooth(interpolate_short_gaps(normalize_track(coords)), window_size=3)
    normal_distances = [
        signed_distance_to_line(point, net_model.lower_line) if point is not None else None
        for point in track
    ]

    events: list[CurvedNetHitEvent] = []
    for frame, point in enumerate(track):
        if point is None:
            continue
        if not net_model.contains(point, margin_px=config.band_margin_px):
            continue

        prev_idx = nearest_valid_index(track, frame - 1, max(0, frame - config.lookback_frames), -1)
        next_idx = nearest_valid_index(track, frame + 1, min(len(track) - 1, frame + config.lookahead_frames), 1)
        if prev_idx is None:
            continue

        current_dist = normal_distances[frame]
        prev_dist = normal_distances[prev_idx]
        next_dist = normal_distances[next_idx] if next_idx is not None else None
        if current_dist is None or prev_dist is None:
            continue

        incoming_motion = current_dist - prev_dist
        outgoing_motion = None if next_dist is None else next_dist - current_dist
        reversed_near_net = (
            outgoing_motion is not None
            and incoming_motion * outgoing_motion < 0
            and abs(incoming_motion) >= config.min_normal_motion_px
            and abs(outgoing_motion) >= config.min_normal_motion_px
        )

        speed_before = median_speed(track, max(0, frame - config.lookback_frames), frame)
        speed_after = median_speed(track, frame, min(len(track) - 1, frame + config.lookahead_frames))
        speed_drop = (
            speed_before is not None
            and speed_after is not None
            and speed_before > 0.0
            and speed_after <= speed_before * config.speed_drop_ratio
        )

        missing_after = next_idx is None and any(
            idx < len(track) and track[idx] is None
            for idx in range(frame + 1, min(len(track), frame + config.missing_after_frames + 1))
        )
        crossed_after = crosses_lower_line_after(
            normal_distances,
            frame,
            prev_dist,
            config.lookahead_frames,
            margin_px=max(config.band_margin_px, 8.0),
        )
        stayed_same_side = not crossed_after and abs(prev_dist) > max(config.band_margin_px, 8.0)
        dropped_after = drops_after(track, frame, config.lookahead_frames, config.min_drop_after_px)
        failure_cue = reversed_near_net or missing_after or dropped_after
        if config.require_failure_cue and not failure_cue:
            continue

        very_inside_band = net_model.contains(point, margin_px=0.0)
        distance_to_band = net_model.vertical_distance_to_band(point)

        confidence = 0.0
        reasons: list[str] = []
        if very_inside_band:
            confidence += 0.28
            reasons.append("inside_curved_net_band")
        else:
            confidence += 0.16
            reasons.append("near_curved_net_band")
        if reversed_near_net:
            confidence += 0.28
            reasons.append("trajectory_reversed_near_net")
        if speed_drop:
            confidence += 0.18
            reasons.append("speed_drop")
        if missing_after:
            confidence += 0.18
            reasons.append("ball_missing_after_net")
        if stayed_same_side:
            confidence += 0.08
            reasons.append("did_not_cross_lower_net_line")
        if dropped_after:
            confidence += 0.18
            reasons.append("dropped_after_net")
        if crossed_after and not reversed_near_net:
            confidence -= 0.22
            reasons.append("crossed_lower_net_line_after")

        confidence = max(0.0, min(1.0, confidence))
        if confidence < config.min_confidence:
            continue

        events.append(
            CurvedNetHitEvent(
                frame=frame,
                time_sec=round(frame / config.fps, 3) if config.fps > 0 else 0.0,
                confidence=round(confidence, 3),
                reason="+".join(reasons),
                ball=(round(point[0], 2), round(point[1], 2)),
                signed_distance_px=round(current_dist, 2),
                distance_to_band_px=round(distance_to_band, 2),
                details={
                    "prev_frame": prev_idx,
                    "next_frame": next_idx,
                    "prev_normal_distance_px": round(prev_dist, 2),
                    "current_normal_distance_px": round(current_dist, 2),
                    "next_normal_distance_px": None if next_dist is None else round(next_dist, 2),
                    "speed_before_px_per_frame": None if speed_before is None else round(speed_before, 2),
                    "speed_after_px_per_frame": None if speed_after is None else round(speed_after, 2),
                    "crossed_after": crossed_after,
                    "dropped_after": dropped_after,
                },
            )
        )

    return merge_events(events, config.merge_gap_frames)


def merge_events(events: Sequence[CurvedNetHitEvent], merge_gap_frames: int) -> list[CurvedNetHitEvent]:
    if not events:
        return []
    merged: list[CurvedNetHitEvent] = []
    group = [events[0]]
    for event in events[1:]:
        if event.frame - group[-1].frame <= merge_gap_frames:
            group.append(event)
        else:
            merged.append(max(group, key=lambda item: item.confidence))
            group = [event]
    merged.append(max(group, key=lambda item: item.confidence))
    return merged


def event_to_json(event: CurvedNetHitEvent) -> dict[str, Any]:
    payload = asdict(event)
    payload["ball"] = list(event.ball)
    return payload
