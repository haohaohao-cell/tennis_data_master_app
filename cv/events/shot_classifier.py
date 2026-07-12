class ShotClassifier:
    """
    A professional shot classifier for tennis match analysis.
    Categorizes shots as serve, forehand, backhand, volley, or smash.
    Based on player position, ball trajectory, and timing.
    """
    
    def __init__(self):
        # Define shot types
        self.SHOT_TYPES = {
            'SERVE': 'Serve',
            'FOREHAND': 'Forehand',
            'BACKHAND': 'Backhand',
            'VOLLEY': 'Volley',
            'SMASH': 'Smash'
        }
        self.BASELINE_THRESHOLD = 0.15  # 距离底部或顶部 15% 区域认为是在底线
        self.NEW_POINT_TIME_THRESHOLD = 400  # 如果两拍之间超过 90 帧（约 3 秒），视为新回合
        self.last_processed_shot_frame = -1
        # Shot colors for visualization (BGR format)
        self.SHOT_COLORS = {
            self.SHOT_TYPES['SERVE']: (0, 165, 255),     # Orange
            self.SHOT_TYPES['FOREHAND']: (0, 255, 0),    # Green
            self.SHOT_TYPES['BACKHAND']: (255, 0, 0),    # Blue
            self.SHOT_TYPES['VOLLEY']: (255, 255, 0),    # Cyan
            self.SHOT_TYPES['SMASH']: (0, 0, 255)        # Red
        }
        
        # Shot classification thresholds
        self.VOLLEY_DISTANCE_THRESHOLD = 150  # Distance from net for volley detection
        self.SMASH_HEIGHT_THRESHOLD = 0.7     # Relative height threshold for smash detection
        self.NET_Y_POSITION_RELATIVE = 0.5    # Relative position of the net (middle of court)

    def classify_shots(self, player_pixel_detections, ball_pixel_detections,
                       ball_shot_frames, frame_height, court_lines_pixel_y):
        """
        对网球比赛中的每一次击球进行分类 (终极动态像素版)。
        参数 court_lines_pixel_y: 包含每一帧动态计算的 net_y, top_baseline_y, bottom_baseline_y 字典
        """
        shot_classifications = {}

        if len(ball_shot_frames) <= 1:
            return shot_classifications

        def get_distance(p1, p2):
            return ((p1[0] - p2[0]) ** 2 + (p1[1] - p2[1]) ** 2) ** 0.5

        for i in range(len(ball_shot_frames) - 1):
            shot_frame = ball_shot_frames[i]
            next_shot_frame = ball_shot_frames[i + 1]

            # 1. 获取当前帧的球和球员数据
            ball_pos = ball_pixel_detections.get(shot_frame, {}).get(1)
            player_positions = player_pixel_detections.get(shot_frame, {})

            # 2. 【核心】提取当前击球帧专属的球场物理基准线
            current_court = court_lines_pixel_y.get(shot_frame)
            if ball_pos is None or not player_positions or not current_court:
                continue

            net_pixel_y = current_court['net_y']
            top_baseline_pixel_y = current_court['top_baseline_y']
            bottom_baseline_pixel_y = current_court['bottom_baseline_y']

            # 3. 动态判定击球者 ID
            try:
                player_shot_id = min(
                    player_positions.keys(),
                    key=lambda p_id: get_distance(player_positions[p_id], ball_pos)
                )
            except (ValueError, KeyError):
                continue

            player_pos = player_positions[player_shot_id]

            # 4. 计算轨迹趋势 (ball_trajectory_y)
            ball_next_pos = ball_pixel_detections.get(next_shot_frame, {}).get(1)
            if ball_next_pos:
                ball_trajectory_y = ball_next_pos[1] - ball_pos[1]
            else:
                ball_trajectory_y = 0

            # 5. 调用判定逻辑 (参数已严谨对齐)
            try:
                shot_type = self._determine_shot_type_pixel(
                    i=i,
                    player_id=player_shot_id,  # 补上 player_id
                    player_x=player_pos[0],
                    player_y=player_pos[1],
                    ball_x=ball_pos[0],
                    ball_y=ball_pos[1],
                    ball_trajectory_y=ball_trajectory_y,
                    net_pixel_y=net_pixel_y,
                    top_baseline_pixel_y=top_baseline_pixel_y,
                    bottom_baseline_pixel_y=bottom_baseline_pixel_y,
                    frame_height=frame_height,
                    shot_frame=shot_frame,
                    ball_pixel_detections=ball_pixel_detections
                )
            except Exception as e:
                shot_type = "unknown"

            shot_classifications[shot_frame] = {
                'shot_type': shot_type,
                'player_id': player_shot_id,
                'frame_index': i,
                'ball_trajectory_y': ball_trajectory_y
            }

        return shot_classifications

    def _is_ball_thrown_up_pixel(self, shot_frame, ball_pixel_detections):
        """
        像素坐标系下的抛球检测。
        注意：画面中往上抛球，Y的像素值是减小的！
        """
        look_back_frames = 15
        y_coords = []
        x_coords = []

        for frame in range(shot_frame - look_back_frames, shot_frame):
            ball_pos = ball_pixel_detections.get(frame, {}).get(1)
            if ball_pos:
                x_coords.append(ball_pos[0])
                y_coords.append(ball_pos[1])

        if len(y_coords) < 5:
            return False

        y_movement = max(y_coords) - min(y_coords)
        x_movement = max(x_coords) - min(x_coords)

        # 验证方向：最早帧的Y应该大于最晚帧的Y（证明球在往屏幕上方走）
        is_moving_upwards = y_coords[0] > y_coords[-1]

        # 阈值需要根据你的视频分辨率（如 1080p）大幅调高
        # 假设 1080p，抛球通常有至少 50 像素高度差，水平抖动不超过 30 像素
        is_y_moving_vertically = y_movement > 50 and is_moving_upwards
        is_x_stable = x_movement < 30

        return is_y_moving_vertically and is_x_stable

    def _determine_shot_type_pixel(self, i, player_id, player_x, player_y, ball_x, ball_y,
                                   ball_trajectory_y, net_pixel_y,
                                   top_baseline_pixel_y, bottom_baseline_pixel_y,
                                   frame_height, shot_frame, ball_pixel_detections):
        """
        基于视频动态像素边界的综合判定逻辑
        """
        # 允许一定的像素缓冲误差
        buffer = 40
        is_near_top_baseline = player_y < (top_baseline_pixel_y + buffer)
        is_near_bottom_baseline = player_y > (bottom_baseline_pixel_y - buffer)
        is_at_baseline = is_near_top_baseline or is_near_bottom_baseline

        # 判定是否为下方球员（不再依赖写死的 ID，而是基于真实场地网高）
        is_bottom_player = player_y > net_pixel_y

        is_time_gap_large = False
        if self.last_processed_shot_frame != -1:
            if (shot_frame - self.last_processed_shot_frame) > self.NEW_POINT_TIME_THRESHOLD:
                is_time_gap_large = True

        is_thrown = self._is_ball_thrown_up_pixel(shot_frame, ball_pixel_detections)

        final_type = None

        # 发球
        if is_at_baseline and i == 0:
            final_type = self.SHOT_TYPES['SERVE']

        # 截击
        elif abs(player_y - net_pixel_y) < 150:
            final_type = self.SHOT_TYPES['VOLLEY']

        # 扣杀
        elif not is_at_baseline and abs(ball_trajectory_y) > 100:
            final_type = self.SHOT_TYPES['SMASH']

        # 正反手
        else:
            delta_x = ball_x - player_x
            if is_bottom_player:
                final_type = self.SHOT_TYPES['FOREHAND'] if delta_x > 0 else self.SHOT_TYPES['BACKHAND']
            else:
                final_type = self.SHOT_TYPES['FOREHAND'] if delta_x < 0 else self.SHOT_TYPES['BACKHAND']

        self.last_processed_shot_frame = shot_frame
        return final_type

    def get_shot_color(self, shot_type):
        """Get the color associated with a shot type for visualization"""
        return self.SHOT_COLORS.get(shot_type, (255, 255, 255))  # Default to white


def draw_shot_classifications(frames, shot_classifications, ball_shot_frames):
    """
    Draw shot classification information showing the last 2 shots for each player.

    Args:
        frames: List of video frames to draw on
        shot_classifications: Dictionary of shot classifications by frame
        ball_shot_frames: List of frame numbers where shots occur

    Returns:
        Frames with shot statistics board
    """
    import cv2

    # Initialize shot classifier for color mapping
    shot_classifier = ShotClassifier()

    # Font settings
    font = cv2.FONT_HERSHEY_SIMPLEX
    font_scale = 0.6
    thickness = 2

    # Process each frame
    for i, frame in enumerate(frames):
        height, width = frame.shape[:2]

        # Create player shot histories up to the current frame (最近2次)
        player_shots = {1: [], 2: []}
        max_shots_to_display = 2  # 只显示最近2次

        # Only include shots that have happened up to this frame
        for frame_num, shot_info in shot_classifications.items():
            if frame_num <= i:  # Only include shots up to the current frame
                player_id = shot_info['player_id']
                shot_type = shot_info['shot_type']

                # Add to player's shot history (newest first)
                player_shots[player_id].insert(0, {'frame': frame_num, 'type': shot_type})

                # Keep only the most recent shots
                if len(player_shots[player_id]) > max_shots_to_display:
                    player_shots[player_id] = player_shots[player_id][:max_shots_to_display]

        # Create shot statistics board - top left corner
        board_width = 420
        board_height = 150
        board_x = 20
        board_y = 20

        # Draw semi-transparent background
        overlay = frame.copy()
        cv2.rectangle(overlay, (board_x, board_y),
                     (board_x + board_width, board_y + board_height),
                     (20, 20, 20), -1)
        cv2.addWeighted(overlay, 0.75, frame, 0.25, 0, frame)

        # Draw board border
        cv2.rectangle(frame, (board_x, board_y),
                     (board_x + board_width, board_y + board_height),
                     (100, 100, 100), 2)

        # Draw board title
        title_height = 40
        cv2.rectangle(frame, (board_x, board_y),
                     (board_x + board_width, board_y + title_height),
                     (50, 50, 120), -1)
        cv2.putText(frame, "RECENT SHOTS (Last 2)", (board_x + 90, board_y + 28),
                   font, 0.75, (255, 255, 255), thickness)

        # Draw players and their shots
        for row, player_id in enumerate([1, 2]):
            y_pos = board_y + title_height + 30 + (row * 50)

            # Player name with colored background
            player_color = (0, 0, 255) if player_id == 1 else (0, 165, 255)
            cv2.rectangle(frame, (board_x + 10, y_pos - 22),
                         (board_x + 110, y_pos + 5), player_color, -1)
            cv2.rectangle(frame, (board_x + 10, y_pos - 22),
                         (board_x + 110, y_pos + 5), (255, 255, 255), 1)

            player_text = f"Player {player_id}"
            cv2.putText(frame, player_text, (board_x + 20, y_pos),
                       font, 0.65, (255, 255, 255), thickness)

            # Recent shots with enhanced visualization
            shots = player_shots.get(player_id, [])

            if not shots:
                # If no shots yet, display placeholder
                cv2.putText(frame, "No shots yet", (board_x + 130, y_pos),
                           font, 0.55, (150, 150, 150), 1)
            else:
                # Display shot indicators with labels
                for col, shot in enumerate(shots):
                    shot_type = shot['type']
                    shot_color = shot_classifier.get_shot_color(shot_type)

                    # Shot position
                    shot_x = board_x + 140 + (col * 130)
                    shot_y = y_pos - 10

                    # Draw shot type box
                    box_width = 110
                    box_height = 30
                    cv2.rectangle(frame, (shot_x, shot_y - 20),
                                 (shot_x + box_width, shot_y + 10),
                                 shot_color, -1)
                    cv2.rectangle(frame, (shot_x, shot_y - 20),
                                 (shot_x + box_width, shot_y + 10),
                                 (255, 255, 255), 2)

                    # Draw shot type text
                    label = f"#{col+1}: {shot_type}"
                    text_size = cv2.getTextSize(label, font, 0.5, 1)[0]
                    text_x = shot_x + (box_width - text_size[0]) // 2
                    text_y = shot_y
                    cv2.putText(frame, label, (text_x, text_y),
                              font, 0.5, (0, 0, 0), thickness-1)

        # Show "SHOT!" indicator when a shot is detected
        if i in ball_shot_frames and i in shot_classifications:
            shot_info = shot_classifications[i]
            player_id = shot_info['player_id']
            shot_type = shot_info['shot_type']

            # Message and color
            shot_message = f"Player {player_id}: {shot_type.upper()}!"
            shot_color = shot_classifier.get_shot_color(shot_type)

            # Draw attention-grabbing notification at the top center
            notification_width = 400
            notification_height = 50
            notification_x = (width - notification_width) // 2
            notification_y = 20

            # Animated pulsing effect (optional, based on frame proximity to shot)
            pulse = 1.0

            # Background with shot color
            cv2.rectangle(frame,
                         (notification_x, notification_y),
                         (notification_x + notification_width, notification_y + notification_height),
                         shot_color, -1)
            cv2.rectangle(frame,
                         (notification_x, notification_y),
                         (notification_x + notification_width, notification_y + notification_height),
                         (255, 255, 255), 3)

            # Shot text
            text_size = cv2.getTextSize(shot_message, font, 0.9, thickness+1)[0]
            text_x = notification_x + (notification_width - text_size[0]) // 2
            text_y = notification_y + (notification_height + text_size[1]) // 2
            cv2.putText(frame, shot_message, (text_x, text_y),
                       font, 0.9, (0, 0, 0), thickness+1)

    return frames 