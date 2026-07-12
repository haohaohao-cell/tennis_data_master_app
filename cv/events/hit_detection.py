import pandas as pd
import numpy as np


def standalone_get_ball_shot_frames(ball_positions, player_detections, frame_height=1080):
    ball_positions_list = [x.get(1, []) for x in ball_positions]
    df = pd.DataFrame(ball_positions_list, columns=['x1', 'y1', 'x2', 'y2'])

    df['ball_hit'] = 0
    df['mid_y'] = (df['y1'] + df['y2']) / 2
    df['mid_x'] = (df['x1'] + df['x2']) / 2

    df['prev_3_y_mean'] = df['mid_y'].rolling(window=3).mean().shift(1)
    df['next_3_y_mean'] = df['mid_y'].iloc[::-1].rolling(window=3).mean().shift(1).iloc[::-1]
    df['prev_3_x_mean'] = df['mid_x'].rolling(window=3).mean().shift(1)
    df['next_3_x_mean'] = df['mid_x'].iloc[::-1].rolling(window=3).mean().shift(1).iloc[::-1]

    max_dist_bottom = 150
    max_dist_top = 30
    W_SCORE = 5
    W_DIST = 0.5

    last_hit_frame = -100
    candidate_hits = []

    for i in range(3, len(df) - 3):
        if i - last_hit_frame < 15: continue
        mid_y, prev_y, next_y = df['mid_y'].iloc[i], df['prev_3_y_mean'].iloc[i], df['next_3_y_mean'].iloc[i]
        mid_x, prev_x, next_x = df['mid_x'].iloc[i], df['prev_3_x_mean'].iloc[i], df['next_3_x_mean'].iloc[i]

        if pd.isna(mid_y) or pd.isna(prev_y) or pd.isna(next_y) or pd.isna(mid_x): continue

        score_y = (mid_y - prev_y) + (mid_y - next_y)
        score_x = (mid_x - prev_x) + (mid_x - next_x)
        abs_total_score = abs(score_y) + abs(score_x)

        is_bottom = score_y > 10.0
        is_top = score_y < -3.0
        is_left = score_x > 3.0
        is_right = score_x < -3.0
        is_reversal = is_bottom or is_top or is_left or is_right

        if is_reversal:
            current_players = player_detections[i] if isinstance(player_detections, list) else player_detections.get(i,
                                                                                                                     {})
            min_dist_in_frame = float('inf')
            best_player_box = None
            best_player_id = None

            for player_id, p_box in current_players.items():
                if p_box is None or len(p_box) < 4: continue
                px1, py1, px2, py2 = p_box
                dx = max(px1 - mid_x, 0, mid_x - px2)
                dy = max(py1 - mid_y, 0, mid_y - py2)
                rect_distance = np.sqrt(dx ** 2 + dy ** 2)

                if rect_distance < min_dist_in_frame:
                    min_dist_in_frame = rect_distance
                    best_player_box = p_box
                    best_player_id = player_id

            if best_player_box is not None:
                px1, py1, px2, py2 = best_player_box
                y_ratio = min(max(py2 / frame_height, 0), 1)
                dynamic_threshold = max_dist_top + y_ratio * (max_dist_bottom - max_dist_top)

                if min_dist_in_frame < dynamic_threshold:
                    is_near_player = (py2 > frame_height * 0.5)
                    if not is_near_player and is_bottom: continue
                    candidate_hits.append((i, min_dist_in_frame, abs_total_score, best_player_id))

    # ---------------- 原始聚合逻辑 ----------------
    raw_final_hits = []
    raw_hit_players = []

    if candidate_hits:
        current_group = [candidate_hits[0]]
        for idx in range(1, len(candidate_hits)):
            frame_num, dist, score, p_id = candidate_hits[idx]
            if frame_num - current_group[-1][0] < 12:
                current_group.append(candidate_hits[idx])
            else:
                best_candidate = max(current_group, key=lambda x: (x[2] * W_SCORE) + ((200 - x[1]) * W_DIST))
                raw_final_hits.append(best_candidate[0])
                raw_hit_players.append(best_candidate[3])
                current_group = [(frame_num, dist, score, p_id)]

        if current_group:
            best_candidate = max(current_group, key=lambda x: (x[2] * W_SCORE) + ((200 - x[1]) * W_DIST))
            raw_final_hits.append(best_candidate[0])
            raw_hit_players.append(best_candidate[3])

    # ==========================================
    # 💥 新增核心：基于球员 ID 的“同拍剪枝”去重逻辑
    # ==========================================
    clean_final_hits = []
    clean_hit_players = []
    MAX_FRAME_GAP = 30  # 时间阈值：60帧（约2秒）。同一个人在 2 秒内的重复击球，视为同一次挥拍

    for i in range(len(raw_final_hits)):
        curr_frame = raw_final_hits[i]
        curr_player = raw_hit_players[i]
        is_last = True  # 默认假设它是本次挥拍的最后一个动作

        # 往后看一次击球事件
        if i < len(raw_final_hits) - 1:
            next_frame = raw_final_hits[i + 1]
            next_player = raw_hit_players[i + 1]

            # 如果下一次击球还是这名球员，并且时间间隔很短
            if curr_player == next_player and (next_frame - curr_frame) < MAX_FRAME_GAP:
                is_last = False  # 那么当前这个动作只是前摇/重复识别，抛弃它！

        if is_last:
            clean_final_hits.append(curr_frame)
            clean_hit_players.append(curr_player)

    # 用清洗后最纯净的帧在 DF 上打标签
    for hit_frame in clean_final_hits:
        df.loc[hit_frame, 'ball_hit'] = 1

    candidate_frames = [item[0] for item in candidate_hits]

    # 最终返回完全清洗干净的一一对应列表
    return clean_final_hits, candidate_frames, clean_hit_players