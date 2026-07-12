import numpy as np
import cv2


class ServeDetector:
    """
    专业的网球发球检测器
    通过分析球员位置、球轨迹和发球区域来识别发球动作
    """

    def __init__(self):
        # 发球检测阈值
        self.SERVE_ZONE_THRESHOLD = 0.15  # 发球区域距离底线的相对阈值
        self.BALL_HEIGHT_THRESHOLD = 0.25  # 球的初始高度阈值（相对于画面高度）
        self.MIN_FRAMES_BETWEEN_SERVES = 50  # 两次发球之间的最小帧数
        self.TRAJECTORY_WINDOW = 10  # 轨迹分析窗口（帧数）

    def detect_serves(self, player_detections, ball_detections, ball_shot_frames,
                     court_keypoints, frame_height):
        """
        检测视频中的所有发球动作

        Args:
            player_detections: 球员检测结果 {frame_idx: {player_id: [x1,y1,x2,y2]}}
            ball_detections: 球检测结果 {frame_idx: {1: [x1,y1,x2,y2]}}
            ball_shot_frames: 击球帧列表
            court_keypoints: 球场关键点
            frame_height: 视频帧高度

        Returns:
            serve_frames: 发球帧字典 {frame_idx: {'player_id': int, 'serve_type': str}}
        """
        serve_frames = {}
        last_serve_frame = -self.MIN_FRAMES_BETWEEN_SERVES

        # 计算球场底线位置（用于判断发球区域）
        baseline_y_top, baseline_y_bottom = self._get_baseline_positions(
            court_keypoints, frame_height
        )

        for i, shot_frame in enumerate(ball_shot_frames):
            # 检查是否满足最小间隔
            if shot_frame - last_serve_frame < self.MIN_FRAMES_BETWEEN_SERVES:
                continue

            # 获取当前帧的球和球员数据
            ball_pos = ball_detections.get(shot_frame, {}).get(1)
            player_positions = player_detections.get(shot_frame, {})

            if ball_pos is None or not player_positions:
                continue

            # 找到离球最近的球员
            player_id = self._get_closest_player(player_positions, ball_pos)
            player_pos = player_positions[player_id]

            # 兼容两种格式：[x, y] 中心点 或 [x1, y1, x2, y2] 边界框
            if len(player_pos) == 2:
                player_y = player_pos[1]  # 直接使用中心点Y坐标
            else:
                player_y = (player_pos[1] + player_pos[3]) / 2  # 计算边界框中心Y

            # 判断是否在发球区域
            is_in_serve_zone = self._is_in_serve_zone(
                player_y, baseline_y_top, baseline_y_bottom, frame_height
            )

            if not is_in_serve_zone:
                continue

            # 分析球的轨迹特征
            trajectory_features = self._analyze_trajectory(
                ball_detections, shot_frame, frame_height
            )

            # 综合判断是否为发球
            if self._is_serve(trajectory_features, i == 0):
                serve_type = self._classify_serve_type(trajectory_features)
                serve_frames[shot_frame] = {
                    'player_id': player_id,
                    'serve_type': serve_type,
                    'confidence': trajectory_features.get('confidence', 0.8)
                }
                last_serve_frame = shot_frame

        return serve_frames

    def _get_baseline_positions(self, court_keypoints, frame_height):
        """计算球场上下底线的Y坐标"""
        if court_keypoints is None or len(court_keypoints) == 0:
            # 如果没有球场关键点，使用默认值
            return frame_height * 0.15, frame_height * 0.85

        # court_keypoints 可能是一维数组 [x1, y1, x2, y2, ...] 交错排列
        # 需要提取所有 y 坐标（奇数索引位置）
        if isinstance(court_keypoints, np.ndarray):
            # 一维数组格式：每两个元素为一组坐标 [x, y, x, y, ...]
            y_coords = court_keypoints[1::2].tolist()  # 取奇数索引（y坐标）
        else:
            # 可能是 [[x1,y1], [x2,y2], ...] 格式
            y_coords = [kp[1] for kp in court_keypoints if len(kp) >= 2]

        if len(y_coords) >= 2:
            baseline_y_top = min(y_coords)
            baseline_y_bottom = max(y_coords)
        else:
            baseline_y_top = frame_height * 0.15
            baseline_y_bottom = frame_height * 0.85

        return baseline_y_top, baseline_y_bottom

    def _get_closest_player(self, player_positions, ball_pos):
        """找到离球最近的球员"""
        # 兼容两种格式：[x, y] 中心点 或 [x1, y1, x2, y2] 边界框
        if len(ball_pos) == 2:
            ball_center = ball_pos  # 已经是中心点
        else:
            ball_center = [(ball_pos[0] + ball_pos[2]) / 2,
                           (ball_pos[1] + ball_pos[3]) / 2]

        min_dist = float('inf')
        closest_player = None

        for player_id, pos in player_positions.items():
            # 兼容两种格式
            if len(pos) == 2:
                player_center = pos  # 已经是中心点
            else:
                player_center = [(pos[0] + pos[2]) / 2, (pos[1] + pos[3]) / 2]

            dist = np.sqrt((ball_center[0] - player_center[0])**2 +
                          (ball_center[1] - player_center[1])**2)
            if dist < min_dist:
                min_dist = dist
                closest_player = player_id

        return closest_player

    def _is_in_serve_zone(self, player_y, baseline_y_top, baseline_y_bottom, frame_height):
        """判断球员是否在发球区域（底线附近）"""
        # 计算发球区域范围
        serve_zone_top = baseline_y_top - frame_height * self.SERVE_ZONE_THRESHOLD
        serve_zone_bottom = baseline_y_bottom + frame_height * self.SERVE_ZONE_THRESHOLD

        # 判断球员是否在上方或下方发球区
        is_top_serve_zone = (player_y <= baseline_y_top + frame_height * 0.1)
        is_bottom_serve_zone = (player_y >= baseline_y_bottom - frame_height * 0.1)

        return is_top_serve_zone or is_bottom_serve_zone

    def _analyze_trajectory(self, ball_detections, shot_frame, frame_height):
        """分析球的轨迹特征"""
        features = {
            'initial_height': 0,
            'height_change': 0,
            'trajectory_curve': 0,
            'confidence': 0.5
        }

        # 获取击球前后的球位置
        start_frame = max(0, shot_frame - self.TRAJECTORY_WINDOW)
        end_frame = shot_frame + self.TRAJECTORY_WINDOW

        trajectory_y = []
        for frame_idx in range(start_frame, min(end_frame, shot_frame + 1)):
            ball_pos = ball_detections.get(frame_idx, {}).get(1)
            if ball_pos is not None:
                # 兼容两种格式：[x, y] 中心点 或 [x1, y1, x2, y2] 边界框
                if len(ball_pos) == 2:
                    ball_y = ball_pos[1]  # 直接使用中心点Y
                else:
                    ball_y = (ball_pos[1] + ball_pos[3]) / 2
                trajectory_y.append(ball_y / frame_height)  # 归一化

        if len(trajectory_y) < 3:
            return features

        # 计算初始高度（发球时球通常在较高位置）
        features['initial_height'] = trajectory_y[0]

        # 计算高度变化（发球轨迹通常先上升后下降）
        if len(trajectory_y) >= 2:
            features['height_change'] = trajectory_y[-1] - trajectory_y[0]

        # 计算轨迹曲率（发球轨迹通常呈抛物线）
        if len(trajectory_y) >= 3:
            # 简单的二阶差分来估计曲率
            diffs = np.diff(trajectory_y)
            if len(diffs) >= 2:
                features['trajectory_curve'] = np.mean(np.abs(np.diff(diffs)))

        # 计算置信度
        confidence = 0.5
        # 发球时球通常在较高位置
        if features['initial_height'] < 0.4:
            confidence += 0.2
        # 发球轨迹向下
        if features['height_change'] > 0:
            confidence += 0.2
        # 有明显的抛物线特征
        if features['trajectory_curve'] > 0.01:
            confidence += 0.1

        features['confidence'] = min(confidence, 1.0)

        return features

    def _is_serve(self, trajectory_features, is_first_shot):
        """综合判断是否为发球"""
        # 如果是第一拍，大概率是发球
        if is_first_shot:
            return True

        # 基于轨迹特征判断
        confidence = trajectory_features.get('confidence', 0)

        # 置信度阈值
        return confidence >= 0.7

    def _classify_serve_type(self, trajectory_features):
        """分类发球类型（一发/二发）"""
        # 根据轨迹特征判断发球类型
        # 一发通常速度更快，轨迹更平
        # 二发通常有更多旋转，轨迹更弯曲

        curve = trajectory_features.get('trajectory_curve', 0)

        if curve > 0.02:
            return "Second Serve"  # 二发（更多旋转）
        else:
            return "First Serve"   # 一发（更平直）


def draw_serve_detections(frames, serve_frames, ball_shot_frames):
    """
    在视频帧上绘制发球检测结果

    Args:
        frames: 视频帧列表
        serve_frames: 发球帧字典
        ball_shot_frames: 击球帧列表

    Returns:
        绘制了发球标记的视频帧
    """
    font = cv2.FONT_HERSHEY_SIMPLEX

    for i, frame in enumerate(frames):
        height, width = frame.shape[:2]

        # 如果当前帧是发球帧，绘制醒目提示
        if i in serve_frames:
            serve_info = serve_frames[i]
            player_id = serve_info['player_id']
            serve_type = serve_info['serve_type']
            confidence = serve_info.get('confidence', 0.8)

            # 绘制发球提示框（右上角）
            box_width = 350
            box_height = 80
            box_x = width - box_width - 20
            box_y = 20

            # 半透明背景
            overlay = frame.copy()
            cv2.rectangle(overlay, (box_x, box_y),
                         (box_x + box_width, box_y + box_height),
                         (0, 100, 255), -1)  # 橙红色
            cv2.addWeighted(overlay, 0.7, frame, 0.3, 0, frame)

            # 边框
            cv2.rectangle(frame, (box_x, box_y),
                         (box_x + box_width, box_y + box_height),
                         (255, 255, 255), 3)

            # 标题
            cv2.putText(frame, "SERVE DETECTED!",
                       (box_x + 20, box_y + 30),
                       font, 0.8, (255, 255, 255), 2)

            # 详细信息
            info_text = f"Player {player_id} - {serve_type}"
            cv2.putText(frame, info_text,
                       (box_x + 20, box_y + 60),
                       font, 0.6, (255, 255, 255), 2)

            # 在球员附近绘制发球标记
            serve_marker_y = 100 if player_id == 1 else height - 100
            cv2.circle(frame, (width // 2, serve_marker_y), 30, (0, 100, 255), -1)
            cv2.putText(frame, "S", (width // 2 - 12, serve_marker_y + 12),
                       font, 1.2, (255, 255, 255), 3)

    return frames
