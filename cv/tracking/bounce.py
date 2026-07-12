# modules/bounce_detector.py
import numpy as np
import math


class BounceDetectorManager:
    def __init__(self, score_thresh=15.0):
        self.score_thresh = score_thresh

    def detect(self, coords, half_window=5):
        """寻找突变点 (基于你优化的向量夹角与动态窗口打分)"""
        bounces = []
        n = len(coords)
        scores = np.zeros(n)
        angles = np.zeros(n)

        for i in range(half_window, n - half_window):
            window = coords[i - half_window: i + half_window + 1]
            if any(p is None or np.isnan(p[0]) for p in window): continue

            y = [p[1] for p in window]
            base_score = 2.0 * y[half_window] - np.mean(y[:half_window]) - np.mean(y[half_window + 1:])

            prev_3 = np.array(coords[i - 3: i])
            next_3 = np.array(coords[i + 1: i + 4])
            v_in = np.array(coords[i]) - np.mean(prev_3, axis=0)
            v_out = np.mean(next_3, axis=0) - np.array(coords[i])

            angle = self._calculate_angle(v_in, v_out)
            angles[i] = angle

            modifier = -30 if angle < 5 else (10 if angle > 20.0 else 0.0)
            scores[i] = base_score + modifier

        for i in range(half_window, n - half_window):
            if scores[i] > self.score_thresh:
                local_scores = scores[i - half_window: i + half_window + 1]
                if scores[i] == np.max(local_scores):  # NMS
                    bounces.append({
                        'frame': i,
                        'coord': coords[i],
                        'score': scores[i],
                        'angle': angles[i]
                    })
        return bounces, scores, angles

    def enhance_subpixel(self, sg_coords, bounces, window=4):
        """基于直线拟合求解亚像素精确落点"""
        enhanced_bounces = []
        for b in bounces:
            frame = b['frame']
            sub_data = self._calculate_intersection(sg_coords, frame, window)
            coord = sub_data['coord']

            if coord is not None and np.isfinite(coord[0]) and np.isfinite(coord[1]):
                b['sub_coord'] = (int(coord[0]), int(coord[1]))
                b['line_in'] = sub_data['line_in']
                b['line_out'] = sub_data['line_out']
            else:
                b['sub_coord'] = None
                b['line_in'] = None
                b['line_out'] = None

            enhanced_bounces.append(b)
        return enhanced_bounces

    # ==========================================
    # 内部数学辅助方法
    # ==========================================
    def _calculate_angle(self, v1, v2):
        norm_v1 = np.linalg.norm(v1)
        norm_v2 = np.linalg.norm(v2)
        if norm_v1 == 0 or norm_v2 == 0: return 0.0
        cos_theta = np.clip(np.dot(v1, v2) / (norm_v1 * norm_v2), -1.0, 1.0)
        return math.degrees(math.acos(cos_theta))

    def _calculate_intersection(self, sg_coords, bounce_frame, window=3):
        in_pts = [p for p in sg_coords[bounce_frame - window: bounce_frame] if p is not None]
        out_pts = [p for p in sg_coords[bounce_frame + 1: bounce_frame + 1 + window] if p is not None]

        if len(in_pts) < 2 or len(out_pts) < 2:
            return {'coord': sg_coords[bounce_frame], 'line_in': None, 'line_out': None}

        in_x, in_y = zip(*in_pts)
        out_x, out_y = zip(*out_pts)

        t_in = np.arange(bounce_frame - len(in_pts), bounce_frame)
        t_out = np.arange(bounce_frame + 1, bounce_frame + 1 + len(out_pts))

        vx_in, bx_in = np.polyfit(t_in, in_x, 1)
        vy_in, by_in = np.polyfit(t_in, in_y, 1)
        vx_out, bx_out = np.polyfit(t_out, out_x, 1)
        vy_out, by_out = np.polyfit(t_out, out_y, 1)

        try:
            denom = vy_in - vy_out
            if abs(denom) < 1e-6:
                return {'coord': sg_coords[bounce_frame], 'line_in': None, 'line_out': None}

            t_cross = (by_out - by_in) / denom
            sub_x = vx_in * t_cross + bx_in
            sub_y = vy_in * t_cross + by_in

            if not np.isfinite(sub_x) or not np.isfinite(sub_y) or abs(t_cross - bounce_frame) > 3:
                return {'coord': sg_coords[bounce_frame], 'line_in': None, 'line_out': None}

            sub_pt = (int(sub_x), int(sub_y))
            in_start_x, in_start_y = int(vx_in * t_in[0] + bx_in), int(vy_in * t_in[0] + by_in)
            out_end_x, out_end_y = int(vx_out * t_out[-1] + bx_out), int(vy_out * t_out[-1] + by_out)

            return {
                'coord': sub_pt,
                'line_in': ((in_start_x, in_start_y), sub_pt),
                'line_out': (sub_pt, (out_end_x, out_end_y))
            }
        except Exception:
            return {'coord': sg_coords[bounce_frame], 'line_in': None, 'line_out': None}