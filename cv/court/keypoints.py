import cv2
import torch
import numpy as np
import torch.nn.functional as F
from .postprocess import postprocess, refine_kps
from .homography import get_trans_matrix
from .reference import CourtReference

def get_matrix_from_model(frame, model, device):
    h_orig, w_orig = frame.shape[:2]
    img_resized = cv2.resize(frame, (640, 360))
    inp = (img_resized.astype(np.float32) / 255.)
    inp = torch.tensor(np.rollaxis(inp, 2, 0)).unsqueeze(0).to(device)

    with torch.no_grad():
        out = model(inp.float())[0]
        pred = F.sigmoid(out).cpu().numpy()

    scale_x, scale_y = w_orig / 640.0, h_orig / 360.0

    points = []
    for kps_num in range(14):
        heatmap = (pred[kps_num] * 255).astype(np.uint8)
        x_pred, y_pred = postprocess(heatmap, scale=1, low_thresh=170, max_radius=25)

        if x_pred is not None and y_pred is not None:
            x_orig, y_orig = int(x_pred * scale_x), int(y_pred * scale_y)
            if kps_num not in [8, 12, 9]:
                y_orig, x_orig = refine_kps(frame, y_orig, x_orig)
            points.append((x_orig, y_orig))
        else:
            points.append((None, None))

    matrix = get_trans_matrix(points)

    # 刚体防抖覆盖
    if matrix is not None:
        court_ref = CourtReference()
        refer_kps = np.array(court_ref.key_points, dtype=np.float32).reshape((-1, 1, 2))
        points = [np.squeeze(x) for x in cv2.perspectiveTransform(refer_kps, matrix)]

    return matrix, points
