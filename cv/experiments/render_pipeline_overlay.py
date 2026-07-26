"""Render pipeline JSON results as an annotated test video.

This experiment consumes the persisted `match_frames_v2.json` and optional
`match_tactics_v2.json` files. It does not run detection or alter pipeline
outputs, so visual inspection can be repeated from the same analysis result.
"""

from __future__ import annotations

import argparse
import json
from collections import deque
from pathlib import Path
from typing import Any


def _as_point(value: Any) -> tuple[float, float] | None:
    if not isinstance(value, (list, tuple)) or len(value) < 2:
        return None
    try:
        return float(value[0]), float(value[1])
    except (TypeError, ValueError):
        return None


def load_pipeline_results(
    match_frames_path: str | Path,
    match_tactics_path: str | Path | None = None,
) -> tuple[dict[str, Any], dict[int, dict[str, Any]], dict[int, dict[str, Any]]]:
    """Load and index the frame and optional net-hit results by frame number."""

    with Path(match_frames_path).open("r", encoding="utf-8") as handle:
        frames_payload = json.load(handle)
    if not isinstance(frames_payload, dict) or not isinstance(frames_payload.get("frames"), list):
        raise ValueError("match_frames JSON must contain a frames list")

    metadata = frames_payload.get("metadata")
    if not isinstance(metadata, dict):
        raise ValueError("match_frames JSON must contain metadata")

    frames_by_index: dict[int, dict[str, Any]] = {}
    for position, frame in enumerate(frames_payload["frames"]):
        if not isinstance(frame, dict):
            raise ValueError("Each frame entry must be an object")
        try:
            frame_index = int(frame.get("frame_index", position))
        except (TypeError, ValueError) as error:
            raise ValueError("frame_index must be an integer") from error
        if frame_index < 0 or frame_index in frames_by_index:
            raise ValueError("frame_index values must be unique non-negative integers")
        frames_by_index[frame_index] = frame

    net_hits_by_frame: dict[int, dict[str, Any]] = {}
    if match_tactics_path is not None:
        with Path(match_tactics_path).open("r", encoding="utf-8") as handle:
            tactics_payload = json.load(handle)
        net_hits = tactics_payload.get("net_hits", []) if isinstance(tactics_payload, dict) else []
        if not isinstance(net_hits, list):
            raise ValueError("match_tactics.net_hits must be a list")
        for event in net_hits:
            if not isinstance(event, dict) or "frame" not in event:
                continue
            try:
                net_hits_by_frame[int(event["frame"])] = event
            except (TypeError, ValueError):
                continue

    return metadata, frames_by_index, net_hits_by_frame


def _draw_text(cv2: Any, canvas: Any, text: str, origin: tuple[int, int], color: tuple[int, int, int]) -> None:
    cv2.putText(canvas, text, origin, cv2.FONT_HERSHEY_SIMPLEX, 0.58, (0, 0, 0), 4, cv2.LINE_AA)
    cv2.putText(canvas, text, origin, cv2.FONT_HERSHEY_SIMPLEX, 0.58, color, 2, cv2.LINE_AA)


def _draw_players(cv2: Any, canvas: Any, players: Any) -> None:
    if not isinstance(players, list):
        return
    for player in players:
        if not isinstance(player, dict):
            continue
        bbox = player.get("bbox_pixel")
        if not isinstance(bbox, (list, tuple)) or len(bbox) < 4:
            continue
        try:
            x1, y1, x2, y2 = [int(round(float(value))) for value in bbox[:4]]
        except (TypeError, ValueError):
            continue
        color = (255, 180, 30) if player.get("id") == 1 else (255, 80, 180)
        cv2.rectangle(canvas, (x1, y1), (x2, y2), color, 2, cv2.LINE_AA)
        _draw_text(cv2, canvas, f"P{player.get('id', '?')}", (x1, max(24, y1 - 8)), color)


def render_pipeline_overlay(
    input_video: str | Path,
    match_frames_path: str | Path,
    output_video: str | Path,
    *,
    match_tactics_path: str | Path | None = None,
    trail_length: int = 8,
    event_display_frames: int = 12,
) -> Path:
    """Render ball tracking and event labels from persisted pipeline outputs."""

    try:
        import cv2
    except ModuleNotFoundError as error:
        raise RuntimeError("Overlay rendering requires OpenCV (cv2)") from error

    if trail_length < 1 or event_display_frames < 1:
        raise ValueError("trail_length and event_display_frames must be positive")

    metadata, frames_by_index, net_hits_by_frame = load_pipeline_results(
        match_frames_path, match_tactics_path
    )
    input_path = Path(input_video)
    output_path = Path(output_video)
    cap = cv2.VideoCapture(str(input_path))
    if not cap.isOpened():
        raise FileNotFoundError(f"Could not open input video: {input_path}")

    fps = float(cap.get(cv2.CAP_PROP_FPS))
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    expected_width = metadata.get("video_width")
    expected_height = metadata.get("video_height")
    if expected_width is not None and int(expected_width) != width:
        cap.release()
        raise ValueError("match_frames video_width does not match the input video")
    if expected_height is not None and int(expected_height) != height:
        cap.release()
        raise ValueError("match_frames video_height does not match the input video")
    if fps <= 0 or width <= 0 or height <= 0:
        cap.release()
        raise RuntimeError("Input video has invalid metadata")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    writer = cv2.VideoWriter(
        str(output_path),
        cv2.VideoWriter_fourcc(*"mp4v"),
        fps,
        (width, height),
    )
    if not writer.isOpened():
        cap.release()
        raise RuntimeError(f"Could not create output video: {output_path}")

    trail: deque[tuple[int, int]] = deque(maxlen=trail_length)
    active_labels: deque[tuple[int, str, tuple[int, int, int], tuple[int, int] | None]] = deque()
    frame_index = 0
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            canvas = frame.copy()
            frame_data = frames_by_index.get(frame_index, {})
            ball = frame_data.get("ball") if isinstance(frame_data, dict) else None
            ball_point = _as_point(ball.get("pixel")) if isinstance(ball, dict) else None
            if ball_point is not None:
                trail.append((int(round(ball_point[0])), int(round(ball_point[1]))))

            _draw_players(cv2, canvas, frame_data.get("players") if isinstance(frame_data, dict) else None)
            for point_index, point in enumerate(trail):
                radius = max(2, point_index + 2)
                cv2.circle(canvas, point, radius, (40, 220, 40), -1, cv2.LINE_AA)
            if ball_point is not None:
                current = (int(round(ball_point[0])), int(round(ball_point[1])))
                cv2.drawMarker(canvas, current, (0, 255, 255), cv2.MARKER_CROSS, 16, 2, cv2.LINE_AA)

            events = frame_data.get("events", {}) if isinstance(frame_data, dict) else {}
            if not isinstance(events, dict):
                events = {}
            if events.get("is_hit"):
                label = f"HIT P{events.get('hitter_id', '?')} {events.get('shot_type', 'unknown')}"
                active_labels.append((frame_index, label, (0, 220, 255), ball_point))
            if events.get("is_bounce"):
                bounce_point = _as_point(events.get("bounce_pixel")) or ball_point
                bounce_type = str(events.get("bounce_type", "unknown")).upper()
                color = (50, 210, 50) if bounce_type == "IN" else (0, 80, 255)
                active_labels.append((frame_index, f"BOUNCE {bounce_type}", color, bounce_point))
            if events.get("is_net_hit"):
                net_event = net_hits_by_frame.get(frame_index, {})
                confidence = net_event.get("confidence", events.get("net_confidence"))
                suffix = "" if confidence is None else f" {float(confidence):.2f}"
                active_labels.append((frame_index, f"NET HIT{suffix}", (0, 0, 255), ball_point))

            while active_labels and frame_index - active_labels[0][0] >= event_display_frames:
                active_labels.popleft()
            for label_index, (_, label, color, point) in enumerate(active_labels):
                if point is not None:
                    marker = (int(round(point[0])), int(round(point[1])))
                    cv2.circle(canvas, marker, 13, color, 2, cv2.LINE_AA)
                    _draw_text(cv2, canvas, label, (marker[0] + 16, max(26, marker[1] - 14)), color)
                else:
                    _draw_text(cv2, canvas, label, (24, 38 + label_index * 28), color)

            _draw_text(cv2, canvas, f"Frame {frame_index}  {frame_index / fps:.2f}s", (24, height - 24), (255, 255, 255))
            writer.write(canvas)
            frame_index += 1
    finally:
        cap.release()
        writer.release()

    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-video", required=True, type=Path)
    parser.add_argument("--match-frames", required=True, type=Path)
    parser.add_argument("--match-tactics", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--trail-length", type=int, default=8)
    parser.add_argument("--event-display-frames", type=int, default=12)
    args = parser.parse_args()

    tactics_path = args.match_tactics
    if tactics_path is None:
        candidate = args.match_frames.parent / "match_tactics_v2.json"
        tactics_path = candidate if candidate.is_file() else None
    output_path = args.output or args.match_frames.parent / f"{args.input_video.stem}_analysis_overlay.mp4"
    result = render_pipeline_overlay(
        args.input_video,
        args.match_frames,
        output_path,
        match_tactics_path=tactics_path,
        trail_length=args.trail_length,
        event_display_frames=args.event_display_frames,
    )
    print(f"Saved pipeline overlay video to {result}")


if __name__ == "__main__":
    main()
