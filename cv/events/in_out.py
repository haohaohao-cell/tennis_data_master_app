import numpy as np


def evaluate_bounces_in_out(bounces, court_matrices_all, match_type="singles", padding_x=120, padding_y=150, ppm=30):
    """
    基于单应矩阵的网球落点界内/界外判定函数 (真实物理尺度法)

    参数:
        bounces: 落点序列列表 (字典格式，包含 frame 和 coord)
        court_matrices_all: 全局单应矩阵列表
        match_type: "singles" (单打) 或 "doubles" (双打)
        padding_x, padding_y, ppm: 2D沙盘的偏移量和比例尺 (与测速函数保持一致)

    返回:
        evaluated_bounces: 附加了 'is_in_bounds' 和 'bounce_type' 字段的新落点序列
    """
    # 国际网联 (ITF) 标准球场尺寸 (单位：米)
    COURT_LENGTH_M = 23.77
    COURT_WIDTH_M = 8.23 if match_type == "singles" else 10.97

    # 物理压线容错率：网球白线宽度通常为 5 厘米 (0.05米)
    TOLERANCE_M = 0.05

    evaluated_bounces = []

    for b in bounces:
        # 为了不污染原始数据，创建一个副本（或者直接修改原字典也可）
        bounce_info = b.copy()

        frame = bounce_info['frame']
        coord = bounce_info.get('sub_coord') or bounce_info.get('coord')

        # 默认兜底：如果矩阵失效或没识别到球，默认视为界内，避免程序崩溃
        is_in = True

        if coord is not None and frame < len(court_matrices_all):
            matrix = court_matrices_all[frame]
            if matrix is not None:
                try:
                    H_inv = np.linalg.inv(matrix)

                    # 1. 视频像素 (Pixel) -> 2D 模板像素 (Canvas)
                    pt_px = np.array([[coord[0]], [coord[1]], [1.0]])
                    res = np.dot(H_inv, pt_px)

                    if res[2, 0] != 0:
                        canvas_x = res[0, 0] / res[2, 0]
                        canvas_y = res[1, 0] / res[2, 0]

                        # 2. 2D 模板像素 (Canvas) -> 真实物理空间 (Meters)
                        real_x = (canvas_x - padding_x) / ppm
                        real_y = (canvas_y - padding_y) / ppm

                        # 3. 核心物理边界判定 (带容错率)
                        # 假设 padding_x 和 padding_y 对应的正好是球场物理边界的左上角 (0, 0)
                        if (-TOLERANCE_M <= real_x <= COURT_WIDTH_M + TOLERANCE_M) and \
                                (-TOLERANCE_M <= real_y <= COURT_LENGTH_M + TOLERANCE_M):
                            is_in = True
                        else:
                            is_in = False

                except np.linalg.LinAlgError:
                    pass  # 矩阵不可逆时，保留 is_in = True 的默认值

        # 4. 结果注入字典
        bounce_info['is_in_bounds'] = is_in
        bounce_info['bounce_type'] = "in" if is_in else "out"

        evaluated_bounces.append(bounce_info)

    return evaluated_bounces