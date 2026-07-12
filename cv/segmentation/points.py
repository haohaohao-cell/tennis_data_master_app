"""Pure point-segmentation rules with no model/runtime dependencies."""

from __future__ import annotations

import json
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any


MIN_VISIBLE_COURT_KEYPOINTS = 9
CONSECUTIVE_NO_COURT_END_FRAMES = 10


@dataclass
class SegmentationConfig:
    ball_break_sec: float = 1.2
    ball_break_sec_with_players: float = 2.2
    players_break_sec: float = 0.8
    court_break_sec: float = 0.32
    min_segment_sec: float = 2.0
    start_ball_ratio: float = 0.28
    start_players_ratio: float = 0.50
    start_court_ratio: float = 0.50
    min_ball_frames: int = 6
    min_player_frames: int = 8
    min_court_frames: int = 8
    no_ball_support_ratio_for_extension: float = 0.70
    min_both_players_ratio: float = 0.45
    min_both_players_total_sec: float = 2.0
    output_dir_name: str = "points_heuristic_v2"
    summary_name: str = "points_heuristic_v2_index.json"


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def save_json(path: Path, payload: dict[str, Any], *, pretty: bool = True) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        if pretty:
            json.dump(payload, handle, ensure_ascii=False, indent=4)
        else:
            json.dump(payload, handle, ensure_ascii=False, separators=(",", ":"))


def format_seconds(seconds: float) -> str:
    minutes = int(seconds // 60)
    secs = seconds - minutes * 60
    return f"{minutes:02d}:{secs:06.3f}"


def has_tracknet_output(frame: dict) -> bool:
    ball = frame.get("ball")
    return bool(ball and ball.get("pixel") is not None)


def has_both_players(frame: dict) -> bool:
    ids = {player.get("id") for player in frame.get("players", [])}
    return 1 in ids and 2 in ids


def count_visible_court_keypoints(points: Any) -> int:
    if not points:
        return 0

    visible = 0
    for point in points:
        if point is None or len(point) < 2:
            continue
        x, y = point[0], point[1]
        if x is None or y is None:
            continue
        visible += 1
    return visible


def has_visible_court(points: Any, *, min_keypoints: int = MIN_VISIBLE_COURT_KEYPOINTS) -> bool:
    return count_visible_court_keypoints(points) >= min_keypoints


def frame_has_visible_court(frame: dict[str, Any]) -> bool:
    return bool(frame.get("court_visible"))


def detect_segments_with_court_visibility(
    frames: list[dict[str, Any]],
    fps: float,
    config: SegmentationConfig,
) -> list[dict[str, Any]]:
    ball_break_frames = max(1, round(config.ball_break_sec * fps))
    ball_break_with_players_frames = max(1, round(config.ball_break_sec_with_players * fps))
    player_break_frames = max(1, round(config.players_break_sec * fps))
    court_break_frames = CONSECUTIVE_NO_COURT_END_FRAMES
    min_segment_frames = max(1, round(config.min_segment_sec * fps))

    start_ball_frames = max(config.min_ball_frames, round(config.start_ball_ratio * ball_break_frames))
    start_player_frames = max(config.min_player_frames, round(config.start_players_ratio * player_break_frames))
    start_court_frames = max(config.min_court_frames, round(config.start_court_ratio * ball_break_frames))
    inactive_reset_frames = max(player_break_frames, court_break_frames)

    ball_hist: deque[int] = deque()
    player_hist: deque[int] = deque()
    court_hist: deque[int] = deque()

    segments: list[dict[str, Any]] = []
    active = False
    candidate_start: int | None = None
    inactive_dead_streak = 0
    active_start: int | None = None
    no_ball_streak = 0
    no_player_streak = 0
    no_court_streak = 0
    no_ball_with_both_count = 0

    for frame_idx, frame in enumerate(frames):
        tracknet_ok = has_tracknet_output(frame)
        players_ok = has_both_players(frame)
        court_ok = frame_has_visible_court(frame)
        support_ok = tracknet_ok or players_ok or court_ok

        ball_hist.append(1 if tracknet_ok else 0)
        if len(ball_hist) > ball_break_frames:
            ball_hist.popleft()

        player_hist.append(1 if players_ok else 0)
        if len(player_hist) > player_break_frames:
            player_hist.popleft()

        court_hist.append(1 if court_ok else 0)
        if len(court_hist) > ball_break_frames:
            court_hist.popleft()

        if not active:
            if support_ok and candidate_start is None:
                candidate_start = frame_idx

            if support_ok:
                inactive_dead_streak = 0
            else:
                inactive_dead_streak += 1
                if inactive_dead_streak >= inactive_reset_frames:
                    candidate_start = None

            if (
                sum(ball_hist) >= start_ball_frames
                and sum(player_hist) >= start_player_frames
                and sum(court_hist) >= start_court_frames
            ):
                active = True
                active_start = candidate_start if candidate_start is not None else frame_idx
                no_ball_streak = 0
                no_player_streak = 0
                no_court_streak = 0
                no_ball_with_both_count = 0
        else:
            if tracknet_ok:
                no_ball_streak = 0
                no_ball_with_both_count = 0
            else:
                no_ball_streak += 1
                if players_ok:
                    no_ball_with_both_count += 1

            no_player_streak = 0 if players_ok else no_player_streak + 1
            no_court_streak = 0 if court_ok else no_court_streak + 1

            extend_ball_gap = False
            if no_ball_streak > 0:
                support_ratio = no_ball_with_both_count / no_ball_streak
                extend_ball_gap = support_ratio >= config.no_ball_support_ratio_for_extension

            effective_ball_break_frames = (
                ball_break_with_players_frames if extend_ball_gap else ball_break_frames
            )

            end_candidates = []
            end_reasons = []

            if no_ball_streak >= effective_ball_break_frames:
                end_candidates.append(frame_idx - no_ball_streak)
                end_reasons.append(
                    "tracknet_gap_extended" if extend_ball_gap else "tracknet_gap"
                )
            if no_player_streak >= player_break_frames:
                end_candidates.append(frame_idx - no_player_streak)
                end_reasons.append("players_gap")
            if no_court_streak >= court_break_frames:
                end_candidates.append(frame_idx - no_court_streak)
                end_reasons.append("court_gap")

            if end_candidates:
                end_frame = min(end_candidates)
                if active_start is not None and (end_frame - active_start + 1) >= min_segment_frames:
                    segments.append(
                        {
                            "segment_id": len(segments) + 1,
                            "start_frame": active_start,
                            "end_frame": end_frame,
                            "duration_frames": end_frame - active_start + 1,
                            "end_reasons": end_reasons,
                        }
                    )

                active = False
                candidate_start = None
                inactive_dead_streak = 0
                active_start = None
                no_ball_streak = 0
                no_player_streak = 0
                no_court_streak = 0
                no_ball_with_both_count = 0
                ball_hist.clear()
                player_hist.clear()
                court_hist.clear()

    if active and active_start is not None:
        end_frame = len(frames) - 1
        if (end_frame - active_start + 1) >= min_segment_frames:
            segments.append(
                {
                    "segment_id": len(segments) + 1,
                    "start_frame": active_start,
                    "end_frame": end_frame,
                    "duration_frames": end_frame - active_start + 1,
                    "end_reasons": ["video_end"],
                }
            )

    return segments


def summarize_segments_with_court_visibility(
    frames: list[dict[str, Any]],
    fps: float,
    segment: dict[str, Any],
) -> dict[str, Any]:
    start_frame = segment["start_frame"]
    end_frame = segment["end_frame"]
    segment_frames = frames[start_frame:end_frame + 1]

    tracknet_count = sum(1 for frame in segment_frames if has_tracknet_output(frame))
    both_players_count = sum(1 for frame in segment_frames if has_both_players(frame))
    court_count = sum(1 for frame in segment_frames if frame_has_visible_court(frame))
    hit_count = sum(1 for frame in segment_frames if (frame.get("events") or {}).get("is_hit"))
    bounce_count = sum(1 for frame in segment_frames if (frame.get("events") or {}).get("is_bounce"))

    duration_frames = segment["duration_frames"]
    start_time = start_frame / fps
    end_time = (end_frame + 1) / fps

    return {
        **segment,
        "start_time_sec": round(start_time, 3),
        "end_time_sec": round(end_time, 3),
        "duration_sec": round(duration_frames / fps, 3),
        "tracknet_frames": tracknet_count,
        "tracknet_ratio": round(tracknet_count / duration_frames, 3),
        "both_players_frames": both_players_count,
        "both_players_ratio": round(both_players_count / duration_frames, 3),
        "court_signal_frames": court_count,
        "court_signal_ratio": round(court_count / duration_frames, 3),
        "hit_count": hit_count,
        "bounce_count": bounce_count,
    }


def filter_segments(segments: list[dict], fps: float, config: SegmentationConfig) -> list[dict]:
    min_both_players_frames = max(1, round(config.min_both_players_total_sec * fps))
    filtered = []

    for segment in segments:
        if segment["both_players_frames"] < min_both_players_frames:
            continue
        if segment["both_players_ratio"] < config.min_both_players_ratio:
            continue
        filtered.append(segment)

    for idx, segment in enumerate(filtered, start=1):
        segment["segment_id"] = idx

    return filtered
