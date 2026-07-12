import numpy as np
import cv2


def map_ball_to_court(ball_coords, matrix):
    """
    将网球的像素坐标映射为球场物理坐标
    ball_coords: (x, y) 像素坐标
    matrix: 3x3 单应矩阵 (get_matrix_from_model 返回的 M)
    """
    if matrix is None or ball_coords is None or np.isnan(ball_coords).any():
        return None

    # 1. 构造 OpenCV 要求的输入格式: (N, 1, 2)
    point = np.array([[[ball_coords[0], ball_coords[1]]]], dtype=np.float32)

    # 2. 执行透视变换
    # 注意：这里的 matrix 应该是从“像素”映射到“物理模型”的矩阵
    transformed_point = cv2.perspectiveTransform(point, matrix)

    # 3. 提取结果 [Real_X, Real_Y]
    real_x, real_y = transformed_point[0][0]

    return [round(float(real_x), 2), round(float(real_y), 2)]