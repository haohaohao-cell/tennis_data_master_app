def _build_rally_analysis(
        fps,
        total_frames,
        ball_shot_frames,
        bounce_frames,
        shot_classifications,
        shot_speeds,
        cumulative_distances,
        player_detections,
        player_detections_court,
        ball_detections,
        ball_detections_court,
        bounces,
        court_matrices,
        new_rally_gap_sec=3.0,
        continuation_gap_sec=2.5,
        min_rally_sec=2.0,
        rally_start_pre_roll_sec=0.4,
        rally_end_grace_sec=1.2,
):
    """Build rally summaries from run_inference outputs only."""

    def average_values(values):
        values = [value for value in values if value is not None]
        if not values:
            return None
        return round(sum(values) / len(values), 3)

    def first_frame_in_range(frames, start, end=None):
        for frame in frames:
            if frame <= start:
                continue
            if end is not None and frame >= end:
                continue
            return frame
        return None

    # 💥 新增防越界小工具：安全获取某帧的累计距离
    def get_safe_dist(p_id, frame_idx):
        dist_array = cumulative_distances.get(p_id)
        if not dist_array:
            return 0.0
        safe_idx = min(max(0, frame_idx), len(dist_array) - 1)
        return dist_array[safe_idx]

    def get_position(frame_idx, player_id):
        """获取球员位置（像素+场地米）"""
        p_frame = player_detections.get(frame_idx, {})
        bbox = p_frame.get(player_id)
        if bbox and len(bbox) >= 4:
            pixel = [(bbox[0] + bbox[2]) / 2.0, bbox[3]]
            court_m = player_detections_court.get(frame_idx, {}).get(player_id)
            return {"pixel": [round(pixel[0], 1), round(pixel[1], 1)], "court_m": court_m}
        return None

    def get_ball_position(frame_idx):
        """获取球位置（像素+场地米）"""
        if frame_idx >= len(ball_detections):
            return None
        b_box = ball_detections[frame_idx].get(1)
        if b_box and len(b_box) >= 4:
            pixel = [(b_box[0] + b_box[2]) / 2.0, (b_box[1] + b_box[3]) / 2.0]
            court_m = ball_detections_court.get(frame_idx)
            return {"pixel": [round(pixel[0], 1), round(pixel[1], 1)], "court_m": court_m}
        return None

    def get_bounce_info(frame_idx):
        """获取落点坐标和in/out状态"""
        for b in bounces:
            if b.get("frame") == frame_idx:
                coord = b.get("sub_coord") or b.get("coord")
                bounce_type = b.get("bounce_type", "in")
                if coord:
                    import numpy as np
                    matrix = court_matrices[frame_idx] if frame_idx < len(court_matrices) else None
                    try:
                        H_inv = np.linalg.inv(matrix) if matrix is not None else None
                        if H_inv is not None:
                            pt = np.array([[coord[0]], [coord[1]], [1.0]])
                            res = np.dot(H_inv, pt)
                            canvas_x, canvas_y = res[0, 0] / res[2, 0], res[1, 0] / res[2, 0]
                            real_x = (canvas_x - 120.0) / 30.0
                            real_y = (canvas_y - 150.0) / 30.0
                            court_m = [round(float(real_x), 2), round(float(real_y), 2)]
                        else:
                            court_m = None
                        pos = {"pixel": [round(coord[0], 1), round(coord[1], 1)], "court_m": court_m}
                    except:
                        pos = {"pixel": [round(coord[0], 1), round(coord[1], 1)], "court_m": None}
                    return pos, bounce_type
                return None, bounce_type
        return None, None

    ordered_shots = sorted(int(frame) for frame in ball_shot_frames)
    bounce_frames = sorted(int(frame) for frame in bounce_frames if frame is not None)
    speed_by_hit = {
        int(item["hit_frame"]): item
        for item in shot_speeds
        if item.get("hit_frame") is not None
    }

    shot_events = []
    for idx, shot_frame in enumerate(ordered_shots):
        prev_frame = ordered_shots[idx - 1] if idx > 0 else None
        next_frame = ordered_shots[idx + 1] if idx + 1 < len(ordered_shots) else None
        shot_info = shot_classifications.get(shot_frame, {})
        speed_info = speed_by_hit.get(shot_frame, {})
        next_bounce_frame = speed_info.get("bounce_frame")
        if next_bounce_frame is None:
            next_bounce_frame = first_frame_in_range(bounce_frames, shot_frame, next_frame)

        player_id = shot_info.get("player_id")
        opponent_id = 2 if player_id == 1 else 1 if player_id == 2 else None

        hitter_pos = get_position(shot_frame, player_id) if player_id else None
        ball_pos = get_ball_position(shot_frame)
        opponent_pos = get_position(shot_frame, opponent_id) if opponent_id else None

        bounce_coord, bounce_type = get_bounce_info(next_bounce_frame) if next_bounce_frame else (None, None)

        prev_speed = None
        if prev_frame and prev_frame in speed_by_hit:
            prev_speed = speed_by_hit[prev_frame].get("speed_kmh")

        shot_events.append(
            {
                "shot_index": idx + 1,
                "frame": shot_frame,
                "time_sec": round(shot_frame / fps, 3) if fps else 0,
                "player_id": player_id,
                "shot_type": shot_info.get("shot_type", "Unknown"),
                "hitter_position": hitter_pos,
                "ball_position": ball_pos,
                "opponent_position": opponent_pos,
                "incoming_speed_kmh": prev_speed,
                "post_hit_speed_kmh": speed_info.get("speed_kmh"),
                "post_hit_distance_m": speed_info.get("distance_m"),
                "post_hit_flight_time_sec": speed_info.get("time_sec"),
                "next_bounce_frame": next_bounce_frame,
                "next_bounce_position": bounce_coord,
                "bounce_result": bounce_type,
                "prev_shot_gap_sec": None if prev_frame is None else round((shot_frame - prev_frame) / fps, 3),
                "next_shot_gap_sec": None if next_frame is None else round((next_frame - shot_frame) / fps, 3),
                "is_likely_serve": shot_info.get("shot_type") == "Serve",
            }
        )

    if not shot_events:
        return {
            "fps": fps,
            "total_frames": total_frames,
            "video_duration_sec": round(total_frames / fps, 3) if fps else 0.0,
            "shot_event_count": 0,
            "rally_count": 0,
            "shot_events": [],
            "rallies": [],
        }

    rally_start_indices = [0]
    for idx in range(1, len(shot_events)):
        event = shot_events[idx]
        prev_gap_sec = event.get("prev_shot_gap_sec")
        if event.get("is_likely_serve") and prev_gap_sec is not None and prev_gap_sec >= 1.0:
            rally_start_indices.append(idx)
        elif prev_gap_sec is not None and prev_gap_sec >= new_rally_gap_sec:
            rally_start_indices.append(idx)

    rallies = []
    pre_roll_frames = max(0, int(round(rally_start_pre_roll_sec * fps))) if fps else 0
    end_grace_frames = max(1, int(round(rally_end_grace_sec * fps))) if fps else 1

    for start_pos, start_idx in enumerate(rally_start_indices):
        end_idx = (
            rally_start_indices[start_pos + 1] - 1
            if start_pos + 1 < len(rally_start_indices)
            else len(shot_events) - 1
        )
        rally_shots = shot_events[start_idx:end_idx + 1]
        next_rally_first_shot = (
            shot_events[rally_start_indices[start_pos + 1]]
            if start_pos + 1 < len(rally_start_indices)
            else None
        )
        first_shot = rally_shots[0]
        last_shot = rally_shots[-1]
        start_frame = max(0, first_shot["frame"] - pre_roll_frames)

        next_bounce_frame = first_frame_in_range(
            bounce_frames,
            last_shot["frame"],
            next_rally_first_shot["frame"] if next_rally_first_shot else None,
        )
        if next_bounce_frame is not None:
            end_frame = next_bounce_frame
            end_source = "next_valid_bounce"
        elif next_rally_first_shot is not None:
            end_frame = min(next_rally_first_shot["frame"] - 1, last_shot["frame"] + end_grace_frames)
            end_source = "timeout_before_next_rally"
        else:
            video_end_frame = max(0, total_frames - 1)
            end_frame = min(video_end_frame, last_shot["frame"] + end_grace_frames)
            end_source = "video_end" if end_frame == video_end_frame else "tail_grace_window"
        end_frame = max(last_shot["frame"], end_frame)

        shot_frames = [item["frame"] for item in rally_shots]
        shot_intervals_sec = [
            round((shot_frames[idx + 1] - shot_frames[idx]) / fps, 3)
            for idx in range(len(shot_frames) - 1)
        ] if fps else []
        speed_values = [item.get("post_hit_speed_kmh") for item in rally_shots]
        serve_frame = next(
            (item["frame"] for item in rally_shots if item.get("shot_type") == "Serve"),
            first_shot["frame"],
        )
        next_gap_sec = last_shot.get("next_shot_gap_sec")
        if next_gap_sec is None:
            termination_reason = "video_end_or_no_following_shot"
        elif next_gap_sec >= new_rally_gap_sec:
            termination_reason = "long_gap_before_next_rally"
        elif next_gap_sec >= continuation_gap_sec:
            termination_reason = "continuation_timeout"
        else:
            termination_reason = "merged_until_next_start_rule"

        duration_sec = round((end_frame - start_frame) / fps, 3) if fps else 0
        if duration_sec < min_rally_sec:
            continue

        # ==============================================================
        # 💥 核心注入区：提取当前回合的独立跑动距离和专属球速
        # ==============================================================
        # 1. 计算当前回合的跑动距离 (结束里程 - 初始里程)
        p1_rally_dist = get_safe_dist(1, end_frame) - get_safe_dist(1, start_frame)
        p2_rally_dist = get_safe_dist(2, end_frame) - get_safe_dist(2, start_frame)

        # 2. 分离 P1 和 P2 的击球速度
        p1_speeds = [item.get("post_hit_speed_kmh") for item in rally_shots if
                     item.get("player_id") == 1 and item.get("post_hit_speed_kmh") is not None]
        p2_speeds = [item.get("post_hit_speed_kmh") for item in rally_shots if
                     item.get("player_id") == 2 and item.get("post_hit_speed_kmh") is not None]

        p1_max_speed = max(p1_speeds) if p1_speeds else 0.0
        p1_avg_speed = average_values(p1_speeds) or 0.0
        p2_max_speed = max(p2_speeds) if p2_speeds else 0.0
        p2_avg_speed = average_values(p2_speeds) or 0.0
        # ==============================================================

        rallies.append(
            {
                "rally_id": len(rallies) + 1,
                "start_frame": start_frame,
                "end_frame": end_frame,
                "start_time_sec": round(start_frame / fps, 3) if fps else 0,
                "end_time_sec": round(end_frame / fps, 3) if fps else 0,
                "duration_sec": duration_sec,
                "p1_distance_m": round(p1_rally_dist, 1),
                "p2_distance_m": round(p2_rally_dist, 1),
                "p1_max_speed_kmh": round(p1_max_speed, 1),
                "p1_avg_speed_kmh": round(p1_avg_speed, 1),
                "p2_max_speed_kmh": round(p2_max_speed, 1),
                "p2_avg_speed_kmh": round(p2_avg_speed, 1),
                "shot_count": len(rally_shots),
                "avg_interval_sec": average_values(shot_intervals_sec) or 0.0,
                "serve_frame": serve_frame,
                "start_source": "serve_pre_roll" if first_shot.get("is_likely_serve") else "first_shot_pre_roll",
                "end_source": end_source,
                "termination_reason": termination_reason,
                "shots": rally_shots,
            }
        )

    return {
        "fps": fps,
        "total_frames": total_frames,
        "video_duration_sec": round(total_frames / fps, 3) if fps else 0.0,
        "min_rally_sec": min_rally_sec,
        "rally_count": len(rallies),
        "rallies": rallies,
    }