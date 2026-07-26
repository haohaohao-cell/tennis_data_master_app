# modules/person_tracker.py
import cv2
import numpy as np
from deep_sort_realtime.deepsort_tracker import DeepSort
from time import perf_counter

from cv.device import get_torch_device
from .player_identity import PlayerIdentityManager


class PersonTrackerManager:
    def __init__(self, detection_model):
        self.detection_model = detection_model
        use_cuda = get_torch_device().type == "cuda"

        # 初始化 DeepSort 追踪器 (完全复刻你提供的参数)
        self.tracker = DeepSort(
            max_age=20,
            n_init=2,
            nms_max_overlap=1.0,
            max_cosine_distance=0.3,
            nn_budget=None,
            gating_only_position=False,
            override_track_class=None,
            embedder="mobilenet",
            half=use_cuda,
            bgr=True,
            embedder_gpu=use_cuda,
            polygon=False,
            today=None,
        )
        self.identity_manager = PlayerIdentityManager()
        self.timing_seconds = {
            "court_masks": 0.0,
            "yolo_detection": 0.0,
            "candidate_classification": 0.0,
            "deep_sort_tracking": 0.0,
            "identity_assignment": 0.0,
        }

    def _record_timing(self, stage, started_at):
        self.timing_seconds[stage] += perf_counter() - started_at

    def update(self, frame, court_detector, frame_idx=0):
        """核心流转方法：供 main.py 每帧调用"""
        # 1. 收集并在逻辑上对人员进行分类判定
        detections = self._collect_person_detections(frame, court_detector)
        # 2. 将附带了身份标签(role)的数据送入 DeepSort 进行 ID 更新
        started_at = perf_counter()
        tracks = self.tracker.update_tracks(detections, frame=frame)
        self._record_timing("deep_sort_tracking", started_at)
        started_at = perf_counter()
        tracks = self.identity_manager.update(tracks, frame, frame_idx)
        self._record_timing("identity_assignment", started_at)
        return tracks

    # ==========================================
    # 以下为私有方法：完全保留你的原始启发式分类逻辑
    # ==========================================

    def _is_valid_box(self, box):
        if box is None or len(box) < 4: return False
        return all(b is not None for b in box[:4])

    def _to_ltwh(self, box):
        x1, y1, x2, y2 = map(float, box[:4])
        width = x2 - x1
        height = y2 - y1
        if width <= 0 or height <= 0: return None
        return [x1, y1, width, height]

    def _ball_boy_color_ratio(self, frame, box):
        x1, y1, x2, y2 = map(int, box[:4])
        x1 = max(0, x1)
        y1 = max(0, y1)
        x2 = min(frame.shape[1], x2)
        y2 = min(frame.shape[0], y2)
        if x2 <= x1 or y2 <= y1: return 0.0

        crop = frame[y1:y2, x1:x2]
        if crop.size == 0: return 0.0

        lower_col = np.array((27, 5, 40), dtype=np.uint8)
        upper_col = np.array((47, 40, 168), dtype=np.uint8)
        mask = cv2.inRange(crop, lower_col, upper_col)
        return float(np.count_nonzero(mask)) / float(mask.size)

    def _court_masks(self, court_detector, frame_shape):
        if court_detector is None or not court_detector.court_warp_matrix:
            return None

        matrix = court_detector.court_warp_matrix[-1]
        masks = {}
        for mask_type in (1, 2, 3):
            mask_ref = court_detector.court_reference.get_court_mask(mask_type)
            masks[mask_type] = cv2.warpPerspective(mask_ref, matrix, frame_shape[1::-1])
        return masks

    def _point_in_mask(self, mask, x, y):
        if mask is None: return False
        x = min(max(int(x), 0), mask.shape[1] - 1)
        y = min(max(int(y), 0), mask.shape[0] - 1)
        return mask[y, x] > 0

    def _court_bounds(self, mask):
        ys, xs = np.where(mask > 0)
        if len(xs) == 0 or len(ys) == 0: return None
        return {
            "left": int(xs.min()), "right": int(xs.max()),
            "top": int(ys.min()), "bottom": int(ys.max()),
            "center_x": float(xs.mean()), "center_y": float(ys.mean()),
        }

    def _point_in_expanded_half(self, bounds, foot_x, foot_y, half_name):
        if bounds is None: return False

        x_margin = 160
        y_margin = 220
        net_y = (bounds["top"] + bounds["bottom"]) / 2.0

        in_x = bounds["left"] - x_margin <= foot_x <= bounds["right"] + x_margin
        if half_name == "top":
            in_y = bounds["top"] - y_margin <= foot_y <= net_y + 120
        else:
            in_y = net_y - 120 <= foot_y <= bounds["bottom"] + y_margin

        return in_x and in_y

    def _player_candidate_score(self, box, frame, bounds):
        x1, y1, x2, y2 = map(float, box[:4])
        width = x2 - x1
        height = y2 - y1
        if width <= 0 or height <= 0: return None

        foot_x = (x1 + x2) / 2.0
        foot_y = y2
        center_x = (x1 + x2) / 2.0
        center_y = (y1 + y2) / 2.0
        area = width * height
        color_ratio = self._ball_boy_color_ratio(frame, box)

        if bounds is None: return area

        center_penalty = abs(center_x - bounds["center_x"]) / max(bounds["right"] - bounds["left"], 1)
        corner_penalty = 0.0
        if foot_y < bounds["top"] + 120 or foot_y > bounds["bottom"] - 120:
            corner_penalty += 1.0
        if foot_x < bounds["left"] + 60 or foot_x > bounds["right"] - 60:
            corner_penalty += 1.0
        net_penalty = abs(center_y - ((bounds["top"] + bounds["bottom"]) / 2.0)) / max(bounds["bottom"] - bounds["top"],
                                                                                       1)

        return (
                area * 0.02
                - center_penalty * 220.0
                - corner_penalty * 180.0
                - net_penalty * 40.0
                - color_ratio * 1400.0
        )

    def _classify_person(self, box, score, frame, masks, bounds, role_override=None):
        x1, y1, x2, y2 = map(float, box[:4])
        width = x2 - x1
        height = y2 - y1
        if width <= 0 or height <= 0: return None

        foot_x = (x1 + x2) / 2.0
        foot_y = y2
        center_x = (x1 + x2) / 2.0
        center_y = (y1 + y2) / 2.0
        area = width * height
        color_ratio = self._ball_boy_color_ratio(frame, box)

        if role_override is not None:
            ltwh = self._to_ltwh(box)
            if ltwh is None: return None
            confidence = max(float(score), 0.9 if "player" in role_override else 0.7)
            return (ltwh, confidence, role_override)

        if bounds is None:
            return (self._to_ltwh(box), float(score), "person")

        near_sideline = abs(center_x - bounds["left"]) < 120 or abs(center_x - bounds["right"]) < 120
        near_net_band = abs(center_y - ((bounds["top"] + bounds["bottom"]) / 2.0)) < 140
        near_court = bounds["left"] - 120 <= foot_x <= bounds["right"] + 120 and bounds["top"] - 120 <= foot_y <= \
                     bounds["bottom"] + 120
        corner_zone = foot_y < bounds["top"] + 160 or foot_y > bounds["bottom"] - 160 or foot_x < bounds[
            "left"] + 90 or foot_x > bounds["right"] - 90

        if near_sideline and near_net_band and area > 12000:
            return (self._to_ltwh(box), max(float(score), 0.75), "referee")

        if near_court and (corner_zone or color_ratio > 0.01):
            return (self._to_ltwh(box), max(float(score), 0.7), "ball_kid")

        return (self._to_ltwh(box), float(score), "audience")

    def _collect_person_detections(self, frame, court_detector):
        detections = []
        started_at = perf_counter()
        masks = self._court_masks(court_detector, frame.shape)
        bounds = self._court_bounds(masks[3]) if masks is not None else None
        self._record_timing("court_masks", started_at)

        # 调用底层检测模型 (你提供的 DetectionModel)
        started_at = perf_counter()
        person_boxes, probs = self.detection_model._detect(frame, person_min_score=0.5)
        self._record_timing("yolo_detection", started_at)

        started_at = perf_counter()

        top_candidates = []
        bottom_candidates = []

        for box, score in zip(person_boxes, probs):
            foot_x = (box[0] + box[2]) / 2.0
            foot_y = box[3]
            in_bottom = masks is not None and self._point_in_mask(masks[1], foot_x, foot_y)
            in_top = masks is not None and self._point_in_mask(masks[2], foot_x, foot_y)
            near_bottom = self._point_in_expanded_half(bounds, foot_x, foot_y, "bottom")
            near_top = self._point_in_expanded_half(bounds, foot_x, foot_y, "top")

            if in_bottom or near_bottom:
                player_score = self._player_candidate_score(box, frame, bounds)
                if player_score is not None:
                    bottom_candidates.append((player_score, box, score))
                continue

            if in_top or near_top:
                player_score = self._player_candidate_score(box, frame, bounds)
                if player_score is not None:
                    top_candidates.append((player_score, box, score))
                continue

            classified = self._classify_person(box, score, frame, masks, bounds)
            if classified is None: continue

            ltwh, confidence, role = classified
            if ltwh is None: continue
            detections.append((ltwh, confidence, role))

        for candidates, player_role in ((bottom_candidates, "bottom_player"), (top_candidates, "top_player")):
            if not candidates: continue

            candidates.sort(key=lambda item: item[0], reverse=True)
            best_box = candidates[0][1]
            best_score = candidates[0][2]

            classified = self._classify_person(best_box, best_score, frame, masks, bounds, role_override=player_role)
            if classified is not None:
                detections.append(classified)

            for _, box, score in candidates[1:]:
                classified = self._classify_person(box, score, frame, masks, bounds)
                if classified is None: continue
                ltwh, confidence, role = classified
                if ltwh is None: continue

                if role in ("top_player", "bottom_player"):
                    role = "ball_kid"
                    confidence = max(confidence, 0.7)
                detections.append((ltwh, confidence, role))

        self._record_timing("candidate_classification", started_at)
        return detections
