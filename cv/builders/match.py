"""Build match-frame, point-index, shot, and point payloads."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from cv.builders.shots import (
    build_point_row,
    build_points_and_events,
    build_raw_shots_for_point,
    convert_linked_shot_to_final_row,
    link_shot_context,
)
from cv.segmentation.points import (
    CONSECUTIVE_NO_COURT_END_FRAMES,
    MIN_VISIBLE_COURT_KEYPOINTS,
    SegmentationConfig,
    count_visible_court_keypoints,
    detect_segments_with_court_visibility,
    filter_segments,
    summarize_segments_with_court_visibility,
)


def build_metadata(fps: float, frame_width: int, frame_height: int, total_frames: int) -> dict[str, Any]:
    return {
        "version": "2.0.0",
        "fps": fps,
        "video_width": frame_width,
        "video_height": frame_height,
        "total_frames": total_frames,
        "court_dimensions": {"unit": "meters", "width": 10.97, "length": 23.77},
    }


def build_match_tactics_payload(
    metadata: dict[str, Any],
    rally_analysis: dict[str, Any],
    net_hit_events: list[Any],
) -> dict[str, Any]:
    return {
        "metadata": metadata,
        "rally_analysis": rally_analysis or {},
        "net_hits": [
            {
                "frame": event.frame,
                "time_sec": event.time_sec,
                "confidence": round(event.confidence, 3),
                "reason": event.reason,
                "ball_position": [round(event.ball[0], 1), round(event.ball[1], 1)],
                "signed_distance_px": round(event.signed_distance_px, 1),
            }
            for event in (net_hit_events or [])
        ],
    }


def build_match_frames_payload(
    metadata: dict[str, Any],
    fps: float,
    court_points: list[Any],
    court_matrices: list[Any | None],
    adapted_for_detector: list[dict[int, list[float]]],
    player_detections: dict[int, dict[int, list[float]]],
    final_valid_bounces: list[dict[str, Any]],
    shot_frames_set: set[int],
    shot_classifications: dict[int, dict[str, Any]],
    net_hit_events: list[Any],
) -> dict[str, Any]:
    from cv.io.json import pixel_to_meters

    total_frames = metadata["total_frames"]
    frames_list: list[dict[str, Any]] = []
    bounce_dict = {bounce["frame"]: bounce for bounce in final_valid_bounces if bounce.get("frame") is not None}
    net_hit_by_frame = {event.frame: event for event in (net_hit_events or [])}

    for frame_index in range(total_frames):
        current_matrix = (
            court_matrices[frame_index]
            if frame_index < len(court_matrices) and court_matrices[frame_index] is not None
            else (court_matrices[frame_index - 1] if frame_index > 0 else None)
        )

        frame_payload: dict[str, Any] = {
            "frame_index": frame_index,
            "time_sec": round(frame_index / fps, 3) if fps > 0 else 0.0,
            "court_visible": False,
            "court_keypoints_detected": 0,
            "ball": None,
            "players": [],
            "events": {
                "is_bounce": False,
                "is_hit": False,
                "is_net_hit": False,
            },
        }

        if frame_index < len(court_points):
            court_keypoint_count = count_visible_court_keypoints(court_points[frame_index])
            frame_payload["court_keypoints_detected"] = court_keypoint_count
            frame_payload["court_visible"] = court_keypoint_count >= MIN_VISIBLE_COURT_KEYPOINTS

        ball_box = adapted_for_detector[frame_index].get(1) if frame_index < len(adapted_for_detector) else None
        if ball_box is not None and len(ball_box) >= 4:
            cx = (ball_box[0] + ball_box[2]) / 2.0
            cy = (ball_box[1] + ball_box[3]) / 2.0
            frame_payload["ball"] = {
                "pixel": [round(cx, 1), round(cy, 1)],
                "court": pixel_to_meters([cx, cy], current_matrix),
            }

        player_frame = player_detections.get(frame_index, {})
        for player_id, player_box in player_frame.items():
            if player_box is None or len(player_box) < 4:
                continue
            fx = (player_box[0] + player_box[2]) / 2.0
            fy = player_box[3]
            frame_payload["players"].append(
                {
                    "id": player_id,
                    "bbox_pixel": [int(player_box[0]), int(player_box[1]), int(player_box[2]), int(player_box[3])],
                    "feet_court": pixel_to_meters([fx, fy], current_matrix),
                }
            )

        if frame_index in bounce_dict:
            bounce = bounce_dict[frame_index]
            frame_payload["events"]["is_bounce"] = True
            frame_payload["events"]["bounce_type"] = bounce.get("bounce_type", "in")
            raw_coord = bounce.get("sub_coord") or bounce.get("coord")
            if raw_coord:
                frame_payload["events"]["bounce_pixel"] = [round(raw_coord[0], 1), round(raw_coord[1], 1)]
                frame_payload["events"]["bounce_court"] = pixel_to_meters([raw_coord[0], raw_coord[1]], current_matrix)

        if frame_index in shot_frames_set:
            frame_payload["events"]["is_hit"] = True
            if frame_index in shot_classifications:
                frame_payload["events"]["hitter_id"] = shot_classifications[frame_index].get("player_id")
                frame_payload["events"]["shot_type"] = shot_classifications[frame_index].get("shot_type")

        net_event = net_hit_by_frame.get(frame_index)
        if net_event is not None:
            frame_payload["events"]["is_net_hit"] = True
            frame_payload["events"]["net_confidence"] = round(net_event.confidence, 3)

        frames_list.append(frame_payload)

    return {
        "metadata": metadata,
        "frames": frames_list,
    }


def build_points_index_payload(
    frames_payload: dict[str, Any],
    source_video_path: str | Path,
    config: SegmentationConfig | None = None,
) -> dict[str, Any]:
    segmentation_config = config or SegmentationConfig()
    frames = frames_payload["frames"]
    fps = float(frames_payload["metadata"]["fps"])
    raw_segments = detect_segments_with_court_visibility(frames, fps, segmentation_config)
    summarized = [summarize_segments_with_court_visibility(frames, fps, segment) for segment in raw_segments]
    filtered = filter_segments(summarized, fps, segmentation_config)

    return {
        "source_video": Path(source_video_path).name,
        "fps": fps,
        "config": {
            "ball_break_sec": segmentation_config.ball_break_sec,
            "ball_break_sec_with_players": segmentation_config.ball_break_sec_with_players,
            "players_break_sec": segmentation_config.players_break_sec,
            "court_break_sec": segmentation_config.court_break_sec,
            "min_segment_sec": segmentation_config.min_segment_sec,
            "start_ball_ratio": segmentation_config.start_ball_ratio,
            "start_players_ratio": segmentation_config.start_players_ratio,
            "start_court_ratio": segmentation_config.start_court_ratio,
            "min_ball_frames": segmentation_config.min_ball_frames,
            "min_player_frames": segmentation_config.min_player_frames,
            "min_court_frames": segmentation_config.min_court_frames,
            "no_ball_support_ratio_for_extension": segmentation_config.no_ball_support_ratio_for_extension,
            "min_both_players_ratio": segmentation_config.min_both_players_ratio,
            "min_both_players_total_sec": segmentation_config.min_both_players_total_sec,
            "court_visible_min_keypoints": MIN_VISIBLE_COURT_KEYPOINTS,
            "court_gap_consecutive_frames": CONSECUTIVE_NO_COURT_END_FRAMES,
        },
        "segment_count": len(filtered),
        "segments": filtered,
    }


def build_shots_and_points_payloads(
    frames_payload: dict[str, Any],
    points_index_payload: dict[str, Any],
    tactics_payload: dict[str, Any],
    upload_id: str,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    frames = frames_payload["frames"]
    fps = float(frames_payload["metadata"]["fps"])
    segments = points_index_payload["segments"]
    net_hits = tactics_payload.get("net_hits", [])

    points_summary, frames_by_index = build_points_and_events(frames, segments, net_hits, upload_id)
    raw_shots_by_point: list[dict[str, Any]] = []
    linked_shots_by_point: list[dict[str, Any]] = []
    point_rows: list[dict[str, Any]] = []
    shot_rows: list[dict[str, Any]] = []

    for point_info in points_summary:
        raw_shots = build_raw_shots_for_point(point_info, frames_by_index, net_hits, fps)
        linked_shots = link_shot_context(raw_shots, point_info, frames_by_index, net_hits, fps)
        point_row = build_point_row(point_info, linked_shots, upload_id)

        raw_shots_by_point.append({"point_id": point_info["point_id"], "shots": raw_shots})
        linked_shots_by_point.append({"point_id": point_info["point_id"], "shots": linked_shots})
        point_rows.append(point_row)
        shot_rows.extend(convert_linked_shot_to_final_row(shot) for shot in linked_shots)

    summary = Counter()
    for row in shot_rows:
        summary["shot_count"] += 1
        if row.get("point_ending"):
            summary["point_ending_shots"] += 1
        if row.get("trajectory_end_type") == "net":
            summary["net_endings"] += 1
        if row.get("first_bounce_frame") is not None:
            summary["shots_with_bounce"] += 1

    intermediate_payload = {
        "metadata": {
            "source_video": points_index_payload.get("source_video"),
            "fps": fps,
            "upload_id": upload_id,
            "point_count": len(point_rows),
            "shot_count": len(shot_rows),
        },
        "points": points_summary,
        "point_rows": point_rows,
        "raw_shots_by_point": raw_shots_by_point,
        "linked_shots_by_point": linked_shots_by_point,
        "summary": dict(summary),
    }

    shots_payload = {
        "metadata": {
            "source_video": points_index_payload.get("source_video"),
            "fps": fps,
            "upload_id": upload_id,
            "shot_count": len(shot_rows),
        },
        "shots": shot_rows,
    }

    points_payload = {
        "metadata": {
            "source_video": points_index_payload.get("source_video"),
            "fps": fps,
            "upload_id": upload_id,
            "point_count": len(point_rows),
        },
        "points": point_rows,
    }
    return intermediate_payload, shots_payload, points_payload
