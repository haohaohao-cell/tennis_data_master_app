# modules/visualizer.py 补充代码

# modules/visualizer.py
import cv2
import numpy as np

class TennisVisualizer:
    def __init__(self):
        # 定义各类角色的专属颜色 (BGR)
        self.color_map = {
            "bottom_player": (0, 255, 0),  # 绿
            "top_player": (0, 200, 0),  # 深绿
            "ball_kid": (0, 255, 255),  # 黄
            "referee": (255, 165, 0),  # 橙
            "audience": (255, 0, 0),  # 蓝
            "person": (200, 200, 200),  # 灰
        }

    def draw_court_lines(self, frame, static_lines):
        if static_lines is None:
            return frame

        for i in range(0, len(static_lines), 4):
            x1, y1, x2, y2 = static_lines[i:i + 4]
            cv2.line(frame, (int(x1), int(y1)), (int(x2), int(y2)), (0, 0, 255), 2)
        return frame

    def draw_tracks(self, frame, tracks):
        for track in tracks:
            if not track.is_confirmed():
                continue

            left, top, right, bottom = map(int, track.to_ltrb())
            label = getattr(track, "det_class", None) or "player"
            color = self.color_map.get(label, (0, 255, 0))

            # 画边界框
            cv2.rectangle(frame, (left, top), (right, bottom), color, 2)

            # 画文字标签
            cv2.putText(
                frame,
                f"{label}:{track.track_id}",
                (left, max(30, top - 10)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7, color, 2
            )
        return frame
def init_minimap(self, court_reference_img):
    """初始化右上角的小沙盘"""
    # 加粗线条
    kernel = np.ones((7, 7), np.uint8)
    ref_base = cv2.dilate(court_reference_img.copy(), kernel, iterations=1)

    self.ref_h, self.ref_w = ref_base.shape
    self.mini_h = 350
    self.mini_w = int(self.mini_h * (self.ref_w / self.ref_h))

    mini_resized = cv2.resize(ref_base, (self.mini_w, self.mini_h), interpolation=cv2.INTER_AREA)
    self.mini_bg = cv2.cvtColor(mini_resized, cv2.COLOR_GRAY2BGR)
    self.mini_bg[self.mini_bg > 0] = 255

    self.display_timer = 0
    self.active_bounce = None


def draw_ball_and_bounces(self, frame, frame_idx, current_ball_coord, enhanced_bounces, inv_H):
    """绘制网球蓝点、屏幕落点红圈、以及右上角沙盘"""
    # 1. 画当前网球
    if current_ball_coord is not None and not np.isnan(current_ball_coord[0]):
        bx, by = int(current_ball_coord[0]), int(current_ball_coord[1])
        cv2.circle(frame, (bx, by), 4, (255, 0, 0), -1)

    # 2. 检查当前帧是否是落点，触发特效倒计时
    for b in enhanced_bounces:
        if b['frame'] == frame_idx:
            self.active_bounce = b.get('sub_coord') or b['coord']
            self.display_timer = 15  # 屏幕停留 15 帧
            break

    # 3. 屏幕中央落点爆炸特效
    if self.display_timer > 0 and self.active_bounce is not None and not np.isnan(self.active_bounce[0]):
        bx, by = int(self.active_bounce[0]), int(self.active_bounce[1])
        cv2.circle(frame, (bx, by), 12, (0, 0, 255), 3)
        cv2.putText(frame, "BOUNCE", (bx + 15, by - 15), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
        self.display_timer -= 1

    # 4. 绘制右上角沙盘
    curr_minimap = self.mini_bg.copy()
    if inv_H is not None:
        for b in enhanced_bounces:
            if frame_idx >= b['frame']:
                raw_pt = b.get('sub_coord') or b['coord']
                if raw_pt and not np.isnan(raw_pt[0]):
                    pixel_pt = np.array([raw_pt[0] + 400, raw_pt[1] + 400, 1.0]).reshape(3, 1)
                    res = np.dot(inv_H, pixel_pt)
                    if res[2, 0] != 0:
                        rx = (res[0, 0] / res[2, 0]) * (self.mini_w / self.ref_w)
                        ry = (res[1, 0] / res[2, 0]) * (self.mini_h / self.ref_h)
                        if 0 <= rx < self.mini_w and 0 <= ry < self.mini_h:
                            cv2.circle(curr_minimap, (int(rx), int(ry)), 5, (0, 0, 255), -1)

    # 贴图
    margin = 20
    roi = frame[margin:margin + self.mini_h, -(margin + self.mini_w):-margin]
    cv2.addWeighted(curr_minimap, 0.9, roi, 0.1, 0, roi)

    return frame