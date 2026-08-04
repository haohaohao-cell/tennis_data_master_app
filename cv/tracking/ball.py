# modules/ball_tracker.py
import cv2
import numpy as np
from collections import deque
from scipy.signal import savgol_filter
from cv.models.ball_tracking.tracknet_runner import TrackNetRunner

# 从你专门的工具文件引入 (注意：请根据你实际存放的文件名修改 import 路径)
from .trajectory import interpolation, remove_outliers_improved, split_track_improved


class BallTrackerManager:
    def __init__(self, model_path, device=None):
        self.runner = TrackNetRunner(model_path=model_path, device=device)
        # 【新增】：为流式单帧处理准备一个专属的 3 帧缓存队列
        self.stream_buffer = deque(maxlen=3)

    # ==========================================
    # 【新增】：流式单帧处理接口 (吃一帧，吐一帧)
    # ==========================================
    def detect_single_frame(self, frame):
        """流式专用的推断口，主程序每次塞进一帧，满 3 帧才输出坐标"""
        self.stream_buffer.append(frame.copy())

        ball_xy = None
        # 必须攒够 3 帧，TrackNet 才会进行推理
        if len(self.stream_buffer) == 3:
            ball_xy = self.runner.infer_model_3_frames(
                self.stream_buffer[0],
                self.stream_buffer[1],
                self.stream_buffer[2]
            )
        return ball_xy

    def extract_raw_coords(self, video_path):
        """运行 TrackNet 模型，获取原始视频的所有球坐标"""
        video = cv2.VideoCapture(video_path)
        coords = []
        frame_buffer = deque(maxlen=3)

        while True:
            ret, frame = video.read()
            if not ret:
                break

            frame_buffer.append(frame.copy())
            ball_xy = None
            if len(frame_buffer) == 3:
                ball_xy = self.runner.infer_model_3_frames(frame_buffer[0], frame_buffer[1], frame_buffer[2])
            coords.append(ball_xy)

        video.release()
        return coords

    def process_trajectory(self, raw_coords, enable_smoothing=True):
        """严格按照原逻辑：按漏检帧分段 -> 插值 -> (可选)SG平滑"""
        # 1. 格式清洗与离群点去除
        dele_coords = [p if p is not None else (np.nan, np.nan) for p in raw_coords]
        try:
            # 直接调用你的外部工具函数进行离群点剔除
            remove_outliers_improved(dele_coords, v_threshold=20, a_threshold=20)
        except NameError:
            pass

        # 2. 核心：直接调用你外部的工具函数，按照连续漏检帧 (max_gap=10) 进行分段
        segments = split_track_improved(dele_coords, max_gap=10)

        final_coords = [(np.nan, np.nan)] * len(dele_coords)

        # 3. 遍历每个片段进行处理
        for start, end in segments:
            sub_section = [p[:] if p is not None else None for p in dele_coords[start: end + 1]]

            # A. 线性插值 (调用外部工具函数)
            try:
                interpolated_sub = interpolation(sub_section)
            except NameError:
                interpolated_sub = sub_section

            # B. SG 平滑 (根据原逻辑窗口设为 7)
            sub_array = np.array(interpolated_sub)
            window_size = 7

            if enable_smoothing and len(sub_array) >= window_size:
                smooth_x = savgol_filter(sub_array[:, 0], window_length=window_size, polyorder=2)
                smooth_y = savgol_filter(sub_array[:, 1], window_length=window_size, polyorder=2)
                processed_sub = list(zip(smooth_x, smooth_y))
            else:
                processed_sub = interpolated_sub

            # 放回总序列
            final_coords[start: end + 1] = processed_sub

        return final_coords
