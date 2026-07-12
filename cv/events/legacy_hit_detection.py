import pandas as pd
import numpy as np

import pandas as pd
import numpy as np

def standalone_get_ball_shot_frames(ball_positions, player_detections, frame_height=1080):
    """
    独立测试版：终极网球击球检测 (加权综合评分优选版)
    """
    ball_positions_list = [x.get(1, []) for x in ball_positions]
    df = pd.DataFrame(ball_positions_list, columns=['x1', 'y1', 'x2', 'y2'])

    df['ball_hit'] = 0
    df['mid_y'] = (df['y1'] + df['y2']) / 2
    df['mid_x'] = (df['x1'] + df['x2']) / 2

    # 1. 计算前后均值
    df['prev_3_y_mean'] = df['mid_y'].rolling(window=3).mean().shift(1)
    df['next_3_y_mean'] = df['mid_y'].iloc[::-1].rolling(window=3).mean().shift(1).iloc[::-1]
    df['prev_3_x_mean'] = df['mid_x'].rolling(window=3).mean().shift(1)
    df['next_3_x_mean'] = df['mid_x'].iloc[::-1].rolling(window=3).mean().shift(1).iloc[::-1]

    # --- 核心判定参数 ---
    min_y_change = 2
    min_x_change = 3
    max_dist_bottom = 150
    max_dist_top = 30

    # --- 【新增】综合打分权重 ---
    W_SCORE = 5  # 轨迹折角能量的权重
    W_DIST = 0.5   # 距离的权重

    last_hit_frame = -100
    candidate_hits = []

    for i in range(3, len(df) - 3):
        if i - last_hit_frame < 15:
            continue

        mid_y, prev_y, next_y = df['mid_y'].iloc[i], df['prev_3_y_mean'].iloc[i], df['next_3_y_mean'].iloc[i]
        mid_x, prev_x, next_x = df['mid_x'].iloc[i], df['prev_3_x_mean'].iloc[i], df['next_3_x_mean'].iloc[i]

        if pd.isna(mid_y) or pd.isna(prev_y) or pd.isna(next_y) or pd.isna(mid_x):
            continue

        # 2. 物理轨迹拐点判定
        score_y = (mid_y - prev_y) + (mid_y - next_y)
        score_x = (mid_x - prev_x) + (mid_x - next_x)

        # 【新增】：计算绝对值总能量，用于后续加权打分
        abs_total_score = abs(score_y) + abs(score_x)

        # 只要总分达标就算发生反转
        is_bottom = score_y > 10.0    # V型反转
        is_top    = score_y < -3.0    # ^型反转
        is_left   = score_x > 3.0     # <型反转
        is_right  = score_x < -3.0    # >型反转

        is_reversal = is_bottom or is_top or is_left or is_right

        # ==========================================
        # 3. 寻找最近的击球球员并进行身份判定
        # ==========================================
        if is_reversal:
            current_players = player_detections[i] if isinstance(player_detections, list) else player_detections.get(i, {})

            min_dist_in_frame = float('inf')
            best_player_box = None

            for player_id, p_box in current_players.items():
                if p_box is None or len(p_box) < 4:
                    continue

                px1, py1, px2, py2 = p_box
                dx = max(px1 - mid_x, 0, mid_x - px2)
                dy = max(py1 - mid_y, 0, mid_y - py2)
                rect_distance = np.sqrt(dx**2 + dy**2)

                if rect_distance < min_dist_in_frame:
                    min_dist_in_frame = rect_distance
                    best_player_box = p_box

            if best_player_box is not None:
                px1, py1, px2, py2 = best_player_box
                y_ratio = min(max(py2 / frame_height, 0), 1)
                dynamic_threshold = max_dist_top + y_ratio * (max_dist_bottom - max_dist_top)

                if min_dist_in_frame < dynamic_threshold:
                    is_near_player = (py2 > frame_height * 0.5)

                    if not is_near_player and is_bottom:
                        continue

                    # 【修改点 1】：把 abs_total_score 作为第三个参数存入群组！
                    candidate_hits.append((i, min_dist_in_frame, abs_total_score))

    # ==========================================
    # 4. 局部最小距离精细过滤 (变更为：加权综合评分最高者胜出)
    # ==========================================
    final_hits = []
    if candidate_hits:
        current_group = [candidate_hits[0]]

        for idx in range(1, len(candidate_hits)):
            frame_num, dist, score = candidate_hits[idx]
            if frame_num - current_group[-1][0] < 12:
                current_group.append(candidate_hits[idx])
            else:
                # 【修改点 2】：用加权公式选出群组内得分最高的！
                # 公式：(轨迹折角能量 * 0.7) + ((200 - 人球距离) * 0.3)
                best_frame = max(current_group,
                                 key=lambda x: (x[2] * W_SCORE) + ((200 - x[1]) * W_DIST))[0]
                final_hits.append(best_frame)
                current_group = [(frame_num, dist, score)]

        if current_group:
            best_frame = max(current_group,
                             key=lambda x: (x[2] * W_SCORE) + ((200 - x[1]) * W_DIST))[0]
            final_hits.append(best_frame)

    for hit_frame in final_hits:
         df.loc[hit_frame, 'ball_hit'] = 1

    candidate_frames = [item[0] for item in candidate_hits]

    return df[df['ball_hit'] == 1].index.tolist(), candidate_frames