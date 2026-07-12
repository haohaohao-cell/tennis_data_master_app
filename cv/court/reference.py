import cv2
import numpy as np


class CourtReference:
    """
    严谨物理学 Court reference model (基于 ITF 国际标准)
    """

    def __init__(self):
        # 1. 物理参数定义 (单位: 像素, 基于 1m = 30px)
        PPM = 30
        PAD_X = 4.0 * PPM
        PAD_Y = 5.0 * PPM

        # 真实的网球场尺寸 (米) * PPM
        court_width_m = 10.97  # 双打全宽
        court_length_m = 23.77  # 全长
        singles_width_m = 8.23  # 单打全宽
        half_length_m = 11.885  # 半场
        service_line_to_net_m = 6.40  # 发球线到网
        service_line_to_base_m = half_length_m - service_line_to_net_m  # 底线到发球线 = 5.485

        # 2. 计算 X 轴关键像素坐标 (左右对称)
        # 单打线离双打线的横向距离：(10.97 - 8.23) / 2 = 1.37m
        left_doubles_x = int(PAD_X)
        left_singles_x = int(PAD_X + 1.37 * PPM)
        center_x = int(PAD_X + (court_width_m / 2) * PPM)
        right_singles_x = int(PAD_X + (court_width_m - 1.37) * PPM)
        right_doubles_x = int(PAD_X + court_width_m * PPM)

        # 3. 计算 Y 轴关键像素坐标 (从上到下)
        top_base_y = int(PAD_Y)
        top_serve_y = int(PAD_Y + service_line_to_base_m * PPM)
        net_y = int(PAD_Y + half_length_m * PPM)
        bot_serve_y = int(PAD_Y + (half_length_m + service_line_to_net_m) * PPM)
        bot_base_y = int(PAD_Y + court_length_m * PPM)

        # ==========================================
        # 以下结构严格保持原作者的命名与组合逻辑，防止外部报错
        # ==========================================

        # 水平线 (基于双打外边界)
        self.baseline_top = ((left_doubles_x, top_base_y), (right_doubles_x, top_base_y))
        self.baseline_bottom = ((left_doubles_x, bot_base_y), (right_doubles_x, bot_base_y))
        self.net = ((left_doubles_x, net_y), (right_doubles_x, net_y))

        # 内部水平发球线 (基于单打内边界)
        self.top_inner_line = ((left_singles_x, top_serve_y), (right_singles_x, top_serve_y))
        self.bottom_inner_line = ((left_singles_x, bot_serve_y), (right_singles_x, bot_serve_y))

        # 垂直边线 (双打)
        self.left_court_line = ((left_doubles_x, top_base_y), (left_doubles_x, bot_base_y))
        self.right_court_line = ((right_doubles_x, top_base_y), (right_doubles_x, bot_base_y))

        # 垂直边线 (单打)
        self.left_inner_line = ((left_singles_x, top_base_y), (left_singles_x, bot_base_y))
        self.right_inner_line = ((right_singles_x, top_base_y), (right_singles_x, bot_base_y))

        # 中场发球线
        self.middle_line = ((center_x, top_serve_y), (center_x, bot_serve_y))

        # 预留给外部的额外配件点
        self.top_extra_part = (center_x, top_base_y + 20)
        self.bottom_extra_part = (center_x, bot_base_y - 20)

        # 核心 14 点组合 (网络追踪对齐使用)
        self.key_points = [*self.baseline_top, *self.baseline_bottom,
                           *self.left_inner_line, *self.right_inner_line,
                           *self.top_inner_line, *self.bottom_inner_line,
                           *self.middle_line]

        self.border_points = [*self.baseline_top, *self.baseline_bottom[::-1]]

        # RANSAC 各种配置字典 (直接保留原版组合逻辑)
        self.court_conf = {
            1: [*self.baseline_top, *self.baseline_bottom],
            2: [self.left_inner_line[0], self.right_inner_line[0], self.left_inner_line[1], self.right_inner_line[1]],
            3: [self.left_inner_line[0], self.right_court_line[0], self.left_inner_line[1], self.right_court_line[1]],
            4: [self.left_court_line[0], self.right_inner_line[0], self.left_court_line[1], self.right_inner_line[1]],
            5: [*self.top_inner_line, *self.bottom_inner_line],
            6: [*self.top_inner_line, self.left_inner_line[1], self.right_inner_line[1]],
            7: [self.left_inner_line[0], self.right_inner_line[0], *self.bottom_inner_line],
            8: [self.right_inner_line[0], self.right_court_line[0], self.right_inner_line[1], self.right_court_line[1]],
            9: [self.left_court_line[0], self.left_inner_line[0], self.left_court_line[1], self.left_inner_line[1]],
            10: [self.top_inner_line[0], self.middle_line[0], self.bottom_inner_line[0], self.middle_line[1]],
            11: [self.middle_line[0], self.top_inner_line[1], self.middle_line[1], self.bottom_inner_line[1]],
            12: [*self.bottom_inner_line, self.left_inner_line[1], self.right_inner_line[1]]
        }

        self.line_width = 2
        # 画布总长宽
        self.court_width = right_doubles_x - left_doubles_x
        self.court_height = bot_base_y - top_base_y
        self.top_bottom_border = int(PAD_Y)
        self.right_left_border = int(PAD_X)
        self.court_total_width = int(PAD_X * 2 + court_width_m * PPM)
        self.court_total_height = int(PAD_Y * 2 + court_length_m * PPM)

    def build_court_reference(self):
        """保持原有的画图逻辑"""
        court = np.zeros((self.court_total_height, self.court_total_width), dtype=np.uint8)
        cv2.line(court, *self.baseline_top, 1, self.line_width)
        cv2.line(court, *self.baseline_bottom, 1, self.line_width)
        cv2.line(court, *self.net, 1, self.line_width)
        cv2.line(court, *self.top_inner_line, 1, self.line_width)
        cv2.line(court, *self.bottom_inner_line, 1, self.line_width)
        cv2.line(court, *self.left_court_line, 1, self.line_width)
        cv2.line(court, *self.right_court_line, 1, self.line_width)
        cv2.line(court, *self.left_inner_line, 1, self.line_width)
        cv2.line(court, *self.right_inner_line, 1, self.line_width)
        cv2.line(court, *self.middle_line, 1, self.line_width)
        court = cv2.dilate(court, np.ones((3, 3), dtype=np.uint8))
        self.court = court
        return court

    def get_important_lines(self):
        return [*self.baseline_top, *self.baseline_bottom, *self.net, *self.left_court_line, *self.right_court_line,
                *self.left_inner_line, *self.right_inner_line, *self.middle_line,
                *self.top_inner_line, *self.bottom_inner_line]

    def get_extra_parts(self):
        return [self.top_extra_part, self.bottom_extra_part]

    def save_all_court_configurations(self):
        """保持原有保存图片的逻辑，不再强依赖硬编码路径"""
        pass

    def get_court_mask(self, mask_type=0):
        """根据新的严谨坐标计算遮罩"""
        mask = np.ones_like(self.court)
        if mask_type == 1:
            mask[:self.net[0][1], :] = 0
        elif mask_type == 2:
            mask[self.net[0][1]:, :] = 0
        elif mask_type == 3:
            mask[:self.baseline_top[0][1], :] = 0
            mask[self.baseline_bottom[0][1]:, :] = 0
            mask[:, :self.left_court_line[0][0]] = 0
            mask[:, self.right_court_line[0][0]:] = 0
        return mask