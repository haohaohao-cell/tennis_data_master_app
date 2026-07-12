import numpy as np
import math


def calculate_player_distances(player_detections, court_matrices_all, padding_x=120, padding_y=150, ppm=30):
    """
    计算球员的累计跑动距离 (加入防抖阈值)
    返回: { 球员ID: [第0帧累计距离, 第1帧累计距离...] }
    """
    # 阈值：相邻两帧位移小于 5 厘米 (0.05米)，视为噪点不累加
    THRESHOLD_M = 0.5

    total_frames = len(court_matrices_all)
    # 初始化累计字典：假设有 P1 和 P2 两个球员
    cumulative_distances = {1: [0.0] * total_frames, 2: [0.0] * total_frames}

    # 记录每个球员上一次“有效”站立的物理坐标
    last_valid_pos = {1: None, 2: None}

    for i in range(total_frames):
        current_matrix = court_matrices_all[i] if i < len(court_matrices_all) else None
        frame_players = player_detections[i] if isinstance(player_detections, list) and i < len(
            player_detections) else (player_detections.get(i, {}) if isinstance(player_detections, dict) else {})

        try:
            H_inv = np.linalg.inv(current_matrix) if current_matrix is not None else None
        except:
            H_inv = None

        # 遍历 P1, P2
        for p_id in [1, 2]:
            current_dist = cumulative_distances[p_id][i - 1] if i > 0 else 0.0

            if H_inv is not None and p_id in frame_players and frame_players[p_id] is not None:
                bbox = frame_players[p_id]
                if len(bbox) >= 4:
                    # 1. 取脚底中心像素坐标
                    feet_px = (bbox[0] + bbox[2]) / 2.0
                    feet_py = bbox[3]

                    # 2. 映射到 2D 图纸
                    pt = np.array([[feet_px], [feet_py], [1.0]])
                    res = np.dot(H_inv, pt)

                    if res[2, 0] != 0:
                        canvas_x = res[0, 0] / res[2, 0]
                        canvas_y = res[1, 0] / res[2, 0]

                        # 3. 换算为纯净的物理米数
                        real_m_x = (canvas_x - padding_x) / ppm
                        real_m_y = (canvas_y - padding_y) / ppm
                        curr_pos = (real_m_x, real_m_y)

                        # 4. 计算与上一帧的距离
                        if last_valid_pos[p_id] is not None:
                            dx = curr_pos[0] - last_valid_pos[p_id][0]
                            dy = curr_pos[1] - last_valid_pos[p_id][1]
                            dist = math.sqrt(dx ** 2 + dy ** 2)

                            # 💥 核心防抖逻辑：超过阈值才累加
                            if dist > THRESHOLD_M:
                                current_dist += dist
                                last_valid_pos[p_id] = curr_pos  # 更新上一次有效坐标
                        else:
                            # 第一帧出现，记录初始位置
                            last_valid_pos[p_id] = curr_pos

            # 把当前累加结果存入数组
            cumulative_distances[p_id][i] = current_dist

    return cumulative_distances