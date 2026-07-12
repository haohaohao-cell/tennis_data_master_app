import cv2
import numpy as np
import pandas as pd
import tqdm
# ==========================================
# 辅助 UI 绘制函数
# ==========================================
def draw_court_dots(frame, points):
    for pt in points:
        if pt is not None and len(pt) == 2 and pt[0] is not None:
            cv2.circle(frame, (int(pt[0]), int(pt[1])), 6, (0, 0, 255), -1)
    return frame


def draw_shot_announcements(frame, frame_num, shot_classifications, display_frames=60):
    # 💥 核心修复 1：缩短默认显示时间(90太长了，60帧即2秒刚好)，并改为【倒序遍历】！
    # 永远优先获取离当前帧最近（最新）的那次击球
    recent = next((f for f in range(frame_num, max(-1, frame_num - display_frames), -1)
                   if f in shot_classifications), None)

    if recent is not None:
        info = shot_classifications[recent]

        # 计算距离击球点过去了多少帧 (0 到 display_frames)
        age = frame_num - recent

        # 💥 核心升级 2：动态视觉冲击 (Impact Effect)
        # 击球后的前 5 帧，字体变大并加粗，模拟“暴击”的视觉效果
        scale = 1.6 if age < 5 else 1.2
        thickness = 5 if age < 5 else 3

        text = f"PLAYER {info['player_id']}: {info['shot_type'].upper()}!"
        font = cv2.FONT_HERSHEY_DUPLEX  # 换个更有科技感的厚重字体

        # 精准计算文字居中位置
        text_size = cv2.getTextSize(text, font, scale, thickness)[0]
        tx = (frame.shape[1] - text_size[0]) // 2

        # 颜色动态变化：击球瞬间(前5帧)闪烁纯白+红色描边，之后恢复常规颜色
        if age < 5:
            color = (255, 255, 255)  # 纯白实心
            border_color = (0, 0, 255)  # 红色描边
        else:
            color = (0, 255, 255) if info['player_id'] == 1 else (0, 165, 255)
            border_color = (0, 0, 0)  # 黑色描边

        # 1. 画黑色/红色厚描边 (制造立体感)
        cv2.putText(frame, text, (tx + 2, 102), font, scale, border_color, thickness + 2)
        # 2. 画实心亮色字
        cv2.putText(frame, text, (tx, 100), font, scale, color, thickness)

        # 💥 核心升级 3：增加消失倒计时进度条 (Tech UI 标配)
        # 在文字下方画一条会随着时间慢慢缩短的能量条
        bar_width = int(text_size[0] * (1 - age / display_frames))
        cv2.line(frame, (tx, 120), (tx + bar_width, 120), color, 4)

    return frame
def draw_advanced_analysis_ui(
        video_frames,
        player_detections,
        ball_detections,
        ball_shot_frames,
        candidate_frames,
        court_lines_pixel_y,
        court_points_all,
        shot_classifications,
        frame_height=1080
):
    """
    高级 UI 渲染函数：展示网球轨迹、击球判定逻辑及淘汰理由
    """
    # --- 1. 配置特效参数 ---
    HIT_VISUAL_DURATION = 15
    GROUP_WINDOW_THRESHOLD = 15

    shot_frames_set = set(ball_shot_frames)
    candidate_frames_set = set(candidate_frames)
    active_candidates_trace = []

    # --- 2. 预计算轨迹分值 (用于显示淘汰理由) ---
    # 这里的 ball_detections 传入格式应与 Phase 2 转换后一致
    ball_positions_list = []
    for x in ball_detections:
        # 兼容列表和字典格式
        b_data = x.get(1, []) if isinstance(x, dict) else (x[0] if x else [])
        ball_positions_list.append(b_data if len(b_data) == 4 else [np.nan] * 4)

    df = pd.DataFrame(ball_positions_list, columns=['x1', 'y1', 'x2', 'y2'])
    df['mid_y'] = (df['y1'] + df['y2']) / 2
    df['mid_x'] = (df['x1'] + df['x2']) / 2
    df['prev_3_mean'] = df['mid_y'].rolling(window=3).mean().shift(1)
    df['next_3_mean'] = df['mid_y'].iloc[::-1].rolling(window=3).mean().shift(1).iloc[::-1]
    df['prev_3_x_mean'] = df['mid_x'].rolling(window=3).mean().shift(1)
    df['next_3_x_mean'] = df['mid_x'].iloc[::-1].rolling(window=3).mean().shift(1).iloc[::-1]
    # 计算 Y 轴折角能量
    df['shot_score'] = (df['mid_y'] - df['prev_3_mean']) + (df['mid_y'] - df['next_3_mean'])

    final_frames = []
    print("\n>>> 正在叠加高级调试 UI 渲染...")

    for i, frame in enumerate(tqdm(video_frames)):
        canvas = frame.copy()
        fh, fw = canvas.shape[:2]

        # --- [A] 绘制场地参考线 ---
        current_court = court_lines_pixel_y.get(i, {})
        if 'net_y' in current_court:
            cv2.line(canvas, (0, int(current_court['net_y'])), (fw, int(current_court['net_y'])), (255, 255, 0), 2)
            cv2.line(canvas, (0, int(current_court['top_baseline_y'])), (fw, int(current_court['top_baseline_y'])),
                     (255, 105, 180), 1)
            cv2.line(canvas, (0, int(current_court['bottom_baseline_y'])),
                     (fw, int(current_court['bottom_baseline_y'])), (255, 105, 180), 1)

        # --- [B] 获取球坐标 ---
        b_item = ball_detections[i]
        b_box = b_item.get(1) if isinstance(b_item, dict) else None
        ball_valid = False
        cx, cy = -1, -1
        if b_box is not None and len(b_box) >= 4:
            cx, cy = int((b_box[0] + b_box[2]) / 2), int((b_box[1] + b_box[3]) / 2)
            ball_valid = True

        # --- [C] 球员信息与距离实时显示 ---
        p_frame = player_detections[i] if isinstance(player_detections, list) else player_detections.get(i, {})
        min_d = float('inf')
        best_py2 = 0

        for p_id, p_box in p_frame.items():
            if p_box is not None and len(p_box) >= 4:
                px1, py1, px2, py2 = p_box
                # 绘制 ID
                cv2.putText(canvas, f"ID: {p_id}", (int(px1), int(py1) - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                            (0, 255, 0), 2)
                # 计算与球的实时距离
                if ball_valid:
                    dx = max(px1 - cx, 0, cx - px2)
                    dy = max(py1 - cy, 0, cy - py2)
                    d = np.sqrt(dx ** 2 + dy ** 2)
                    if d < min_d:
                        min_d = d
                        best_py2 = py2
                    # 在球员上方显示距离
                    color = (0, 0, 255) if d < 180 else (255, 255, 0)
                    cv2.putText(canvas, f"Dist: {d:.1f}", (int(px1), int(py1) - 30), cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                                color, 2)

        # --- [D] 击球点留痕 (红色确诊点) ---
        if ball_valid and (i in candidate_frames_set):
            active_candidates_trace.append((cx, cy, i))
        # 清理过期的留痕数据
        active_candidates_trace = [t for t in active_candidates_trace if i - t[2] < GROUP_WINDOW_THRESHOLD]
        for tx, ty, tf in active_candidates_trace:
            if tf in shot_frames_set:
                cv2.circle(canvas, (tx, ty), 10, (0, 0, 255), -1)
                cv2.putText(canvas, "WINNER", (tx + 12, ty), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)

        # --- [E] 实时判定状态显示 (左上角状态栏) ---
        is_final_hit = i in shot_frames_set
        reason = "Scanning..."
        status_color = (180, 180, 180)

        if is_final_hit:
            reason = "WINNER: VALID SHOT POINT!"
            status_color = (0, 0, 255)
            cv2.rectangle(canvas, (0, 0), (fw - 1, fh - 1), (0, 0, 255), 10)
        elif i in candidate_frames_set:
            reason = "REJECTED: Lower Score in Group"
        elif ball_valid:
            # 复刻底层判定逻辑来显示理由
            mid_y, prev_y, next_y = df['mid_y'].iloc[i], df['prev_3_mean'].iloc[i], df['next_3_mean'].iloc[i]
            if pd.isna(prev_y):
                reason = "Wait for Trajectory..."
            else:
                is_rev = abs((mid_y - prev_y) + (mid_y - next_y)) > 3.0  # 简化版逻辑示意
                if not is_rev:
                    reason = "REJECTED: Smooth Trajectory"
                elif min_d > 180:
                    reason = f"REJECTED: Dist({min_d:.0f}) > Thresh"
                else:
                    reason = "REJECTED: Logic Conflict"

        cv2.putText(canvas, f"STATUS: {reason}", (30, 60), cv2.FONT_HERSHEY_DUPLEX, 1.0, (0, 0, 0), 4)
        cv2.putText(canvas, f"STATUS: {reason}", (30, 60), cv2.FONT_HERSHEY_DUPLEX, 1.0, status_color, 2)

        # --- [F] 绘制当前球与 Score ---
        if ball_valid:
            cv2.drawMarker(canvas, (cx, cy), (0, 255, 255), cv2.MARKER_CROSS, 15, 2)
            cur_s = df['shot_score'].iloc[i]
            s_txt = f"Score: {cur_s:.2f}" if pd.notna(cur_s) else "Score: N/A"
            cv2.putText(canvas, s_txt, (cx + 15, cy - 15), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)

        final_frames.append(canvas)

    return final_frames