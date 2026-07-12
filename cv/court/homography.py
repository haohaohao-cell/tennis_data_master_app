
import cv2
import numpy as np
from scipy.spatial import distance


def get_trans_matrix(points, court_ref=None):
    """计算透视变换矩阵"""
    if court_ref is None:
        from .court_reference import CourtReference
        court_ref = CourtReference()

    refer_kps = np.array(court_ref.key_points, dtype=np.float32).reshape((-1, 1, 2))

    court_conf_ind = {}
    for i in range(len(court_ref.court_conf)):
        conf = court_ref.court_conf[i + 1]
        inds = []
        for j in range(4):
            inds.append(court_ref.key_points.index(conf[j]))
        court_conf_ind[i + 1] = inds

    matrix_trans = None
    dist_max = np.inf
    for conf_ind in range(1, 13):
        conf = court_ref.court_conf[conf_ind]

        inds = court_conf_ind[conf_ind]
        inters = [points[inds[0]], points[inds[1]], points[inds[2]], points[inds[3]]]

        if not any([None in x for x in inters]):
            matrix, _ = cv2.findHomography(np.float32(conf), np.float32(inters), method=0)

            # 使用 perspectiveTransform 得到形状为 (14, 1, 2) 的数据
            trans_kps = cv2.perspectiveTransform(refer_kps, matrix)

            # ⬇️ 【关键修复 1】：使用 squeeze 挤掉多余维度，变成 (14, 2)，完美适配 Scipy
            trans_kps = np.squeeze(trans_kps)

            dists = []

            # ⬇️ 【关键修复 2】：把写死的 12 改为 len(points)，覆盖全部 14 个点
            for i in range(len(points)):
                if i not in inds and points[i][0] is not None:
                    # 此时 trans_kps[i] 是干净的一维数组 [x, y]
                    dists.append(distance.euclidean(points[i], trans_kps[i]))

            # ⬇️ 【关键修复 3】：特写镜头容错，如果没有多余的点用来算误差，直接跳过防报错
            if not dists:
                continue

            dist_median = np.mean(dists)
            if dist_median < dist_max:
                matrix_trans = matrix
                dist_max = dist_median

    return matrix_trans

