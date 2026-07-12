import json
import cv2
import numpy as np
import os

from cv.config import OUTPUT_DIR


def pixel_to_meters(pixel_coord, matrix):
    """
    核心转换函数：将像素坐标(x,y)通过单应矩阵转换为真实的物理坐标(米)
    """
    if matrix is None or pixel_coord is None or np.isnan(pixel_coord).any():
        return None

    try:
        # 求逆：沙盘→像素 变为 像素→沙盘
        H_inv = np.linalg.inv(matrix)
        pt = np.array([[pixel_coord[0]], [pixel_coord[1]], [1.0]])
        res = np.dot(H_inv, pt)
        canvas_x = res[0, 0] / res[2, 0]
        canvas_y = res[1, 0] / res[2, 0]
    except:
        return None

    # 换算为米 (基于 CourtReference: PAD_X=120, PAD_Y=150, PPM=30)
    real_x = (canvas_x - 120.0) / 30.0
    real_y = (canvas_y - 150.0) / 30.0

    return [round(float(real_x), 2), round(float(real_y), 2)]


def export_analysis_to_separated_json(
        fps, frame_width, frame_height, total_frames,
        court_matrices,
        adapted_for_detector,
        player_detections,
        final_valid_bounces,
        shot_frames_set,
        shot_classifications,
        shot_speeds=None,
        rally_analysis=None,
        net_hit_events=None,
        output_dir=str(OUTPUT_DIR)
):
    """
    将分析数据拆分为两个 JSON 文件：
    1. match_tactics.json: 存储回合分析、球速统计等轻量化战术数据。
    2. match_frames.json: 存储逐帧的球、球员追踪坐标等重量级渲染数据 (全字段版)。
    """
    print(f"\n>>> 正在执行数据拆分打包 (全拼版)...")

    # 共享的元数据
    metadata = {
        "version": "1.1.0",
        "fps": fps,
        "video_width": frame_width,
        "video_height": frame_height,
        "total_frames": total_frames,
        "court_dimensions": {"unit": "meters", "width": 10.97, "length": 23.77}
    }

    # ==========================================
    # 📁 文件 1: 战术统计数据 (match_tactics.json)
    # ==========================================
    tactics_data = {
        "metadata": metadata,
        "rally_analysis": rally_analysis or {},
        "net_hits": [
            {
                "frame": e.frame,
                "time_sec": e.time_sec,
                "confidence": round(e.confidence, 3),
                "reason": e.reason,
                "ball_position": [round(e.ball[0], 1), round(e.ball[1], 1)],
                "signed_distance_px": round(e.signed_distance_px, 1)
            }
            for e in (net_hit_events or [])
        ]
    }

    tactics_path = os.path.join(output_dir, "match_tactics.json")
    os.makedirs(output_dir, exist_ok=True)
    with open(tactics_path, 'w', encoding='utf-8') as f:
        json.dump(tactics_data, f, indent=4, ensure_ascii=False)
    print(f"✅ 战术统计数据已保存: {tactics_path} ({os.path.getsize(tactics_path) / 1024:.2f} KB)")

    # ==========================================
    # 📁 文件 2: 逐帧追踪数据 (match_frames.json)
    # ==========================================
    frames_list = []
    bounce_dict = {b['frame']: b for b in final_valid_bounces if b.get('frame') is not None}

    for i in range(total_frames):
        current_matrix = court_matrices[i] if i < len(court_matrices) and court_matrices[i] is not None else (
            court_matrices[i - 1] if i > 0 else None)

        frame_data = {
            "frame_index": i,
            "time_sec": round(i / fps, 3) if fps > 0 else 0,
            "ball": None,
            "players": [],
            "events": {
                "is_bounce": False,
                "is_hit": False,
                "is_net_hit": False
            }
        }

        # --- A. 网球数据 ---
        b_box = adapted_for_detector[i].get(1) if i < len(adapted_for_detector) else None
        if b_box is not None and len(b_box) >= 4:
            cx, cy = (b_box[0] + b_box[2]) / 2.0, (b_box[1] + b_box[3]) / 2.0
            frame_data["ball"] = {
                "pixel": [round(cx, 1), round(cy, 1)],
                "court": pixel_to_meters([cx, cy], current_matrix)
            }

        # --- B. 球员数据 ---
        p_frame = player_detections[i] if isinstance(player_detections, list) else player_detections.get(i, {})
        for p_id, p_box in p_frame.items():
            if p_box is not None and len(p_box) >= 4:
                fx, fy = (p_box[0] + p_box[2]) / 2.0, p_box[3]
                frame_data["players"].append({
                    "id": p_id,
                    "bbox_pixel": [int(p_box[0]), int(p_box[1]), int(p_box[2]), int(p_box[3])],
                    "feet_court": pixel_to_meters([fx, fy], current_matrix)
                })

        # --- C. 落点与击球事件 ---
        if i in bounce_dict:
            b_info = bounce_dict[i]
            frame_data["events"]["is_bounce"] = True
            frame_data["events"]["bounce_type"] = b_info.get('bounce_type', 'in')

            raw_c = b_info.get('sub_coord') or b_info.get('coord')
            if raw_c:
                frame_data["events"]["bounce_pixel"] = [round(raw_c[0], 1), round(raw_c[1], 1)]
                frame_data["events"]["bounce_court"] = pixel_to_meters([raw_c[0], raw_c[1]], current_matrix)

        if i in shot_frames_set:
            frame_data["events"]["is_hit"] = True
            if i in shot_classifications:
                frame_data["events"]["hitter_id"] = shot_classifications[i].get('player_id')
                frame_data["events"]["shot_type"] = shot_classifications[i].get('shot_type')

        # 检查是否为落网帧
        if net_hit_events:
            for net_event in net_hit_events:
                if net_event.frame == i:
                    frame_data["events"]["is_net_hit"] = True
                    frame_data["events"]["net_confidence"] = round(net_event.confidence, 3)
                    break

        frames_list.append(frame_data)

    frames_final_data = {
        "metadata": metadata,
        "frames": frames_list
    }

    frames_path = os.path.join(output_dir, "match_frames.json")
    with open(frames_path, 'w', encoding='utf-8') as f:
        # 依然使用 separators=(',', ':') 来去除不必要的空格，这样可以在不缩写字段名的情况下尽量压缩体积
        json.dump(frames_final_data, f, ensure_ascii=False, separators=(',', ':'))

    print(f"✅ 逐帧追踪数据已保存: {frames_path} ({os.path.getsize(frames_path) / (1024 * 1024):.2f} MB)")
