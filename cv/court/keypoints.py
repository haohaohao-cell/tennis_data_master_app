import cv2
import torch
import numpy as np
import torch.nn.functional as F
from .postprocess import postprocess, refine_kps
from .homography import get_trans_matrix
from .reference import CourtReference


def project_reference_keypoints(matrix, court_ref=None):
    reference = court_ref or CourtReference()
    reference_points = np.asarray(reference.key_points, dtype=np.float32).reshape((-1, 1, 2))
    return list(cv2.perspectiveTransform(reference_points, matrix).reshape(-1, 2))


def detect_court_keypoints(frame, model, device):
    h_orig, w_orig = frame.shape[:2]
    img_resized = cv2.resize(frame, (640, 360))
    inp = img_resized.astype(np.float32) / 255.0
    inp = torch.tensor(np.rollaxis(inp, 2, 0)).unsqueeze(0).to(device)

    with torch.no_grad():
        prediction = F.sigmoid(model(inp.float())[0]).cpu().numpy()

    scale_x, scale_y = w_orig / 640.0, h_orig / 360.0
    points = []
    for keypoint_index in range(14):
        heatmap = (prediction[keypoint_index] * 255).astype(np.uint8)
        x_pred, y_pred = postprocess(heatmap, scale=1, low_thresh=170, max_radius=25)
        if x_pred is None or y_pred is None:
            points.append((None, None))
            continue

        x_orig, y_orig = int(x_pred * scale_x), int(y_pred * scale_y)
        if keypoint_index not in (8, 9, 12):
            y_orig, x_orig = refine_kps(frame, y_orig, x_orig)
        points.append((x_orig, y_orig))
    return points

def get_matrix_from_model(frame, model, device):
    points = detect_court_keypoints(frame, model, device)
    court_ref = CourtReference()
    matrix = get_trans_matrix(points, court_ref=court_ref)

    if matrix is not None:
        points = project_reference_keypoints(matrix, court_ref)

    return matrix, points


def get_matrix_from_model_with_ransac(frame, model, device, court_ref=None):
    """Detect a court matrix with the production fit and all-keypoint fallback."""
    reference = court_ref or CourtReference()
    points = detect_court_keypoints(frame, model, device)
    matrix = get_trans_matrix(points, court_ref=reference)
    if matrix is None:
        reference_points = []
        image_points = []
        for keypoint_index, point in enumerate(points):
            if point[0] is None or point[1] is None:
                continue
            reference_points.append(reference.key_points[keypoint_index])
            image_points.append(point)
        if len(reference_points) >= 4:
            matrix, inlier_mask = cv2.findHomography(
                np.asarray(reference_points, dtype=np.float32),
                np.asarray(image_points, dtype=np.float32),
                cv2.RANSAC,
                5.0,
            )
            if matrix is None or inlier_mask is None or int(inlier_mask.sum()) < 4:
                matrix = None
    if matrix is not None:
        points = project_reference_keypoints(matrix, reference)
    return matrix, points
