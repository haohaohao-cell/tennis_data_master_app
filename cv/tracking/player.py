import cv2
import pickle
from ultralytics import YOLO
import sys
import os

from .bbox import get_center_of_bbox, measure_distance_between_points


class PlayerTracker:
    def __init__(self, model_path):
        # 照抄原版初始化
        self.model = YOLO(model_path)

    def choose_and_filter_players(self, player_detections, court_keypoints):
        """
        改进版逻辑：动态追踪法
        不再只看第一帧，而是每一帧都重新选出离球场最近的两个人。
        """
        filtered_player_detections = []

        for player_dict in player_detections:
            # 1. 调用你现有的 choose_players 逻辑，算出这一帧里离场点最近的 ID
            # 这个函数会返回当前帧最像球员的 [id1, id2]
            current_chosen_ids = self.choose_players(court_keypoints, player_dict)

            # 2. 只保留这几个被选中的 ID
            filtered_player_dict = {
                track_id: bbox for track_id, bbox in player_dict.items()
                if track_id in current_chosen_ids
            }

            filtered_player_detections.append(filtered_player_dict)

        return filtered_player_detections


    def choose_players(self, court_keypoints, player_dict):
        """完全照抄原版：计算到场地关键点的最短距离"""
        distances = []
        for track_id, bbox in player_dict.items():
            player_center = get_center_of_bbox(bbox)
            min_distance = float('inf')

            # 遍历 14 个关键点
            for i in range(0, len(court_keypoints), 2):
                court_keypoint = (court_keypoints[i], court_keypoints[i + 1])
                distance = measure_distance_between_points(player_center, court_keypoint)
                if distance < min_distance:
                    min_distance = distance
            distances.append((track_id, min_distance))

        # 按距离排序
        distances.sort(key=lambda x: x[1])

        # 核心：只取前两名。如果第一帧球员没进场，这里就会选错观众！
        # 修正建议：如果第一帧人不够，请确保输入视频的第一帧球员已经在场边。
        if len(distances) >= 2:
            chosen_players = [distances[0][0], distances[1][0]]
        elif len(distances) == 1:
            chosen_players = [distances[0][0]]
        else:
            chosen_players = []

        return chosen_players

    def detect_frames(self, frames, read_from_stub=False, stub_path=None):
        """完全照抄原版：带 track 功能"""
        player_detections = []

        if read_from_stub and stub_path and os.path.exists(stub_path):
            with open(stub_path, 'rb') as f:
                return pickle.load(f)

        for frame in frames:
            player_dict = self.detect_frame(frame)
            player_detections.append(player_dict)

        if stub_path:
            with open(stub_path, 'wb') as f:
                pickle.dump(player_detections, f)

        return player_detections

    def detect_frame(self, frame):
        """完全照抄原版：YOLO track 模式"""
        results = self.model.track(frame, persist=True)[0]
        id_name_dict = results.names

        player_dict = {}
        for box in results.boxes:
            if box.id is None: continue
            track_id = int(box.id.tolist()[0])
            result = box.xyxy.tolist()[0]
            object_cls_id = box.cls.tolist()[0]
            if id_name_dict[object_cls_id] == "person":
                player_dict[track_id] = result
        return player_dict

    def draw_bboxes(self, video_frames, player_detections):
        """完全照抄原版：颜色交替"""
        for i, (frame, player_dict) in enumerate(zip(video_frames, player_detections)):
            for track_id, bbox in player_dict.items():
                x1, y1, x2, y2 = map(int, bbox)
                # 原版逻辑：根据 key 的顺序定颜色
                color = (0, 0, 255) if track_id == list(player_dict.keys())[0] else (0, 165, 255)
                cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                cv2.putText(frame, f"Player", (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
        return video_frames
