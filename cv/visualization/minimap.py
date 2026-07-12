import cv2
import numpy as np


def render_with_minimap(video_path, output_path, final_coords, bounces, player_detections, court_ref,
                        court_matrices_all, shot_speeds=None):
    """
    鹰眼级单应矩阵验证与 2D 沙盘渲染器 (完全体：含转播级测速HUD + IN/OUT落点甄别)
    """
    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(output_path, fourcc, fps, (width, height))

    # --- 1. 准备右上角沙盘背景 ---
    ref_base = court_ref.court.copy()
    kernel = np.ones((7, 7), np.uint8)
    ref_base = cv2.dilate(ref_base, kernel, iterations=1)

    ref_h, ref_w = ref_base.shape
    mini_h = 350
    mini_w = int(mini_h * (ref_w / ref_h))

    mini_resized = cv2.resize(ref_base, (mini_w, mini_h), interpolation=cv2.INTER_AREA)
    mini_bg = cv2.cvtColor(mini_resized, cv2.COLOR_GRAY2BGR)
    mini_bg[mini_bg > 0] = 255

    standard_2d_lines = court_ref.get_important_lines()
    frame_idx = 0

    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break

        current_matrix = court_matrices_all[frame_idx] if frame_idx < len(court_matrices_all) else None

        if current_matrix is not None:
            H_2d_to_pixel = current_matrix
            try:
                H_pixel_to_2d = np.linalg.inv(current_matrix)
            except np.linalg.LinAlgError:
                H_pixel_to_2d = None

            # ==========================================
            # 绘制层 1: 在原画面画出反向投影的绿线
            # ==========================================
            if H_2d_to_pixel is not None:
                for i in range(0, len(standard_2d_lines), 2):
                    pt1, pt2 = standard_2d_lines[i], standard_2d_lines[i + 1]
                    p1 = np.dot(H_2d_to_pixel, [pt1[0], pt1[1], 1])
                    p2 = np.dot(H_2d_to_pixel, [pt2[0], pt2[1], 1])
                    cv2.line(frame, (int(p1[0] / p1[2]), int(p1[1] / p1[2])),
                             (int(p2[0] / p2[2]), int(p2[1] / p2[2])), (0, 255, 0), 2)

            # ==========================================
            # 绘制层 2: 右上角沙盘内容 (球员 + 鹰眼落点)
            # ==========================================
            curr_minimap = mini_bg.copy()
            if H_pixel_to_2d is not None:

                # 💥 2.1 绘制球员 (P1 / P2)
                frame_players = player_detections[frame_idx] if isinstance(player_detections, list) and frame_idx < len(
                    player_detections) else (
                    player_detections.get(frame_idx, {}) if isinstance(player_detections, dict) else {})
                for p_id, bbox in frame_players.items():
                    if bbox is not None and len(bbox) >= 4:
                        feet_pt = np.array([[(bbox[0] + bbox[2]) / 2.0], [bbox[3]], [1.0]])
                        res_p = np.dot(H_pixel_to_2d, feet_pt)
                        if res_p[2, 0] != 0:
                            rx, ry = (res_p[0, 0] / res_p[2, 0]) * (mini_w / ref_w), (res_p[1, 0] / res_p[2, 0]) * (
                                        mini_h / ref_h)
                            if 0 <= rx < mini_w and 0 <= ry < mini_h:
                                color = (255, 0, 0) if p_id == 1 else (0, 255, 0)
                                cv2.circle(curr_minimap, (int(rx), int(ry)), 6, color, -1)
                                cv2.putText(curr_minimap, f"P{p_id}", (int(rx) + 8, int(ry) + 5),
                                            cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1)

                # 💥 2.2 升级版绘制落点：鹰眼级 IN/OUT 视觉区分
                for b in bounces:
                    if frame_idx >= b['frame']:
                        raw_pt = b.get('sub_coord') or b.get('coord')
                        bounce_type = b.get('bounce_type', 'in')  # 安全提取界内外属性

                        if raw_pt and not np.isnan(raw_pt[0]):
                            res_b = np.dot(H_pixel_to_2d, [[raw_pt[0]], [raw_pt[1]], [1.0]])
                            if res_b[2, 0] != 0:
                                rx, ry = (res_b[0, 0] / res_b[2, 0]) * (mini_w / ref_w), (res_b[1, 0] / res_b[2, 0]) * (
                                            mini_h / ref_h)

                                if 0 <= rx < mini_w and 0 <= ry < mini_h:
                                    cx, cy = int(rx), int(ry)
                                    if bounce_type == 'out':
                                        # ❌ 界外球：红色实心圆 + 红色警告外圈
                                        cv2.circle(curr_minimap, (cx, cy), 4, (0, 0, 255), -1)
                                        cv2.circle(curr_minimap, (cx, cy), 8, (0, 0, 255), 2)
                                    else:
                                        # ✅ 界内球：亮青色实心圆
                                        cv2.circle(curr_minimap, (cx, cy), 5, (255, 255, 0), -1)

            # ==========================================
            # 绘制层 3: 合成画面与原图网球轨迹
            # ==========================================
            margin = 20
            roi = frame[margin:margin + mini_h, -(margin + mini_w):-margin]
            cv2.addWeighted(curr_minimap, 0.85, roi, 0.15, 0, roi)

            if frame_idx < len(final_coords) and final_coords[frame_idx] is not None and not np.isnan(
                    final_coords[frame_idx][0]):
                cv2.circle(frame, (int(final_coords[frame_idx][0]), int(final_coords[frame_idx][1])), 4, (255, 255, 0),
                           -1)

        # ==========================================
        # 💥 绘制层 4: 电视转播级测速雷达面板 (HUD)
        # ==========================================
        if shot_speeds is not None:
            for shot in shot_speeds:
                # 触发条件：在击球瞬间出现，并在落地后额外停留 30 帧 (约 1 秒) 供观众阅读
                if shot['hit_frame'] <= frame_idx <= (shot['bounce_frame'] + 30):
                    speed_kmh = shot.get('speed_kmh', 0)
                    dist_m = shot.get('distance_m', 0)

                    # 1. 绘制半透明黑色面板底框 (放在左上角)
                    overlay = frame.copy()
                    panel_w, panel_h = 320, 90
                    cv2.rectangle(overlay, (30, 30), (30 + panel_w, 30 + panel_h), (0, 0, 0), -1)
                    # 混合透明度 (60% 不透明度)
                    cv2.addWeighted(overlay, 0.6, frame, 0.4, 0, frame)

                    # 2. 绘制面板左侧的高亮装饰条 (青色)
                    cv2.line(frame, (30, 30), (30, 30 + panel_h), (255, 255, 0), 4)

                    # 3. 写入速度文字
                    cv2.putText(frame, f"SHOT SPEED: {speed_kmh} km/h", (50, 70),
                                cv2.FONT_HERSHEY_DUPLEX, 0.7, (255, 255, 255), 2)

                    # 4. 写入辅助信息 (比如飞行距离)
                    cv2.putText(frame, f"Distance: {dist_m} m", (50, 100),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)

                    break  # 同一时间通常只有一个球在飞，画完就跳出循环

        out.write(frame)
        frame_idx += 1
        if frame_idx % 100 == 0:
            print(f"正在渲染战术复盘画面: 第 {frame_idx} 帧...")

    cap.release()
    out.release()
    print("\n✅ 战术复盘视频（含电视转播级测速面板与鹰眼落点）渲染完成！")