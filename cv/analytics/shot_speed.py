import math
import numpy as np

def calculate_shot_speeds_true_meters(shot_classifications, bounces, player_detections, court_matrices_all, fps,
                                      min_speed_kmh=30.0, padding_x=120, padding_y=150, ppm=30):
    """
    带严格物理单位换算的网球测速函数
    输入：基础击球分类字典 (shot_classifications)
    输出：兼容下游旧函数的 shot_speeds 列表，完美解决 AttributeError 报错！
    """
    shot_speeds = []

    # 按帧号升序遍历击球事件
    for hit_frame in sorted(shot_classifications.keys()):
        info = shot_classifications[hit_frame]
        p_id = info.get('player_id')

        # 如果连球员 ID 都没有，直接扔掉
        if p_id is None:
            continue

        # 1. 寻找当前击球后，紧接着的【第一个】有效落点
        next_bounce = None
        for b in bounces:
            if b['frame'] > hit_frame:
                next_bounce = b
                break

        if next_bounce is not None:
            bounce_frame = next_bounce['frame']

            # 确保不越界且矩阵有效
            if hit_frame < len(court_matrices_all) and bounce_frame < len(court_matrices_all):
                matrix_hit = court_matrices_all[hit_frame]
                matrix_bounce = court_matrices_all[bounce_frame]

                if matrix_hit is not None and matrix_bounce is not None:
                    try:
                        H_inv_hit = np.linalg.inv(matrix_hit)
                        H_inv_bounce = np.linalg.inv(matrix_bounce)

                        # 💥 获取击球球员的【脚底像素坐标】
                        current_players = player_detections.get(hit_frame, {})
                        player_bbox = current_players.get(p_id)

                        if player_bbox is None or len(player_bbox) < 4:
                            continue

                        feet_x_raw = (player_bbox[0] + player_bbox[2]) / 2.0
                        feet_y_raw = player_bbox[3]

                        # 获取落点坐标
                        pt_bounce_raw = next_bounce.get('sub_coord') or next_bounce.get('coord')

                        if pt_bounce_raw is not None:

                            # 2. 击球起点 (人脚)：像素 -> 沙盘 -> 真实米数
                            pt1_px = np.array([[feet_x_raw], [feet_y_raw], [1.0]])
                            res1 = np.dot(H_inv_hit, pt1_px)
                            real_x1 = (res1[0, 0] / res1[2, 0] - padding_x) / ppm
                            real_y1 = (res1[1, 0] / res1[2, 0] - padding_y) / ppm

                            # 3. 终点 (网球落点)：像素 -> 沙盘 -> 真实米数
                            pt2_px = np.array([[pt_bounce_raw[0]], [pt_bounce_raw[1]], [1.0]])
                            res2 = np.dot(H_inv_bounce, pt2_px)
                            real_x2 = (res2[0, 0] / res2[2, 0] - padding_x) / ppm
                            real_y2 = (res2[1, 0] / res2[2, 0] - padding_y) / ppm

                            # 4. 算真实距离和速度
                            distance_m = math.sqrt((real_x2 - real_x1) ** 2 + (real_y2 - real_y1) ** 2)
                            time_sec = (bounce_frame - hit_frame) / fps

                            if time_sec > 0:
                                speed_kmh = (distance_m / time_sec) * 3.6

                                # 💥 5. 组装成旧版格式并剔除低速
                                if speed_kmh >= min_speed_kmh:
                                    # 直接组装成你熟悉的字典，塞进列表里
                                    shot_speeds.append({
                                        'hit_frame': hit_frame,
                                        'bounce_frame': bounce_frame,
                                        'distance_m': round(distance_m, 2),
                                        'time_sec': round(time_sec, 3),
                                        'speed_kmh': round(speed_kmh, 1)
                                    })

                    except np.linalg.LinAlgError:
                        pass

    # 最终返回的是一个列表: [{'hit_frame': ..., 'speed_kmh': ...}, ...]
    return shot_speeds