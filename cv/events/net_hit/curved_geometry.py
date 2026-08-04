from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any, Sequence

import cv2
import numpy as np

from cv.court.reference import CourtReference


Point = tuple[float, float]
Line = tuple[Point, Point]


@dataclass
class NetBandConfig:
    """Settings for automatic curved net-band localization."""

    sample_count: int = 100
    polynomial_degree: int = 2
    min_band_height_px: float = 14.0
    max_band_height_px: float = 140.0
    search_height_px: float | None = None
    expected_height_px: float | None = None
    sample_half_width_px: int = 5
    fit_outlier_px: float = 16.0
    edge_prior_tolerance_px: float = 18.0
    prior_fit_weight: float = 0.45
    band_margin_px: float = 8.0
    line_extension_ratio: float = 0.04
    use_image_top_line: bool = True
    use_image_top_edges: bool = False
    image_top_prior_tolerance_px: float = 85.0
    image_top_prior_x_margin_ratio: float = 0.08
    center_line_anchor_tolerance_px: float = 38.0
    net_tape_sample_window_px: float = 24.0
    top_search_above_lower_px: float | None = None
    lower_line_refine_tolerance_px: float = 80.0
    lower_line_max_slope: float = 0.18
    net_top_min_offset_px: float = 12.0
    post_search_x_ratio: float = 0.14
    post_min_length_px: float = 35.0
    post_max_x_slope: float = 0.18
    post_max_above_net_factor: float = 1.95
    post_min_white_score: float = 0.42
    post_white_score_weight: float = 3.0
    post_hint_score_weight: float = 0.8
    use_post_bounds: bool = False
    top_tape_max_step_px: float = 16.0
    lower_from_top_height_ratio: float = 0.72
    lower_from_top_min_offset_ratio: float = 0.45
    lower_from_top_max_offset_ratio: float = 1.08
    court_net_width_m: float = 10.97
    net_center_height_m: float = 0.914
    net_post_height_m: float = 1.07


@dataclass
class NetBandModel:
    """A pixel-space model of the visible tennis net band.

    The lower edge is a projected court-plane line.  The upper edge is a
    polynomial in image x fitted from sampled image evidence, or a physics
    fallback when the image evidence is weak.
    """

    lower_line: Line
    top_coefficients: list[float]
    x_center: float
    x_scale: float
    top_points: list[Point]
    source: str
    frame_size: dict[str, int]
    expected_height_px: float
    search_height_px: float
    band_margin_px: float = 8.0

    def lower_y(self, x: float) -> float:
        return line_y_at_x(self.lower_line, x)

    def top_y(self, x: float) -> float:
        u = (float(x) - self.x_center) / self.x_scale
        return float(np.polyval(np.asarray(self.top_coefficients, dtype=np.float64), u))

    def clamp_top_below_lower(self, x: float) -> float:
        return min(self.top_y(x), self.lower_y(x) - 4.0)

    def contains(self, point: Sequence[float], *, margin_px: float | None = None) -> bool:
        if point is None or len(point) < 2:
            return False
        x = float(point[0])
        y = float(point[1])
        if not math.isfinite(x) or not math.isfinite(y):
            return False

        margin = self.band_margin_px if margin_px is None else float(margin_px)
        left_x = min(self.lower_line[0][0], self.lower_line[1][0]) - margin
        right_x = max(self.lower_line[0][0], self.lower_line[1][0]) + margin
        if x < left_x or x > right_x:
            return False

        top = self.clamp_top_below_lower(x)
        lower = self.lower_y(x)
        if top > lower:
            top, lower = lower, top
        return top - margin <= y <= lower + margin

    def vertical_distance_to_band(self, point: Sequence[float]) -> float:
        x = float(point[0])
        y = float(point[1])
        top = self.clamp_top_below_lower(x)
        lower = self.lower_y(x)
        if top <= y <= lower:
            return 0.0
        return min(abs(y - top), abs(y - lower))

    def top_polyline(self, count: int = 140) -> list[Point]:
        return [
            (float(x), self.clamp_top_below_lower(float(x)))
            for x in np.linspace(self.lower_line[0][0], self.lower_line[1][0], count)
        ]

    def lower_polyline(self, count: int = 140) -> list[Point]:
        return [
            (float(x), self.lower_y(float(x)))
            for x in np.linspace(self.lower_line[0][0], self.lower_line[1][0], count)
        ]

    def band_polygon(self, count: int = 140) -> list[Point]:
        top = self.top_polyline(count)
        lower = list(reversed(self.lower_polyline(count)))
        return top + lower

    def to_json(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["lower_line"] = [list(self.lower_line[0]), list(self.lower_line[1])]
        payload["top_points"] = [list(point) for point in self.top_points]
        payload["top_polyline"] = [list(point) for point in self.top_polyline()]
        payload["lower_polyline"] = [list(point) for point in self.lower_polyline()]
        return payload


def line_y_at_x(line: Line, x: float) -> float:
    (x1, y1), (x2, y2) = line
    if abs(x2 - x1) < 1e-6:
        return float((y1 + y2) / 2.0)
    ratio = (float(x) - x1) / (x2 - x1)
    return float(y1 + ratio * (y2 - y1))


def signed_distance_to_line(point: Sequence[float], line: Line) -> float:
    (x1, y1), (x2, y2) = line
    px, py = float(point[0]), float(point[1])
    dx = x2 - x1
    dy = y2 - y1
    length = math.hypot(dx, dy)
    if length <= 1e-9:
        return 0.0
    return ((px - x1) * dy - (py - y1) * dx) / length


def offset_line_y(line: Line, offset_px: float) -> Line:
    return (
        (float(line[0][0]), float(line[0][1] + offset_px)),
        (float(line[1][0]), float(line[1][1] + offset_px)),
    )


def extend_line(line: Line, ratio: float, frame_size: tuple[int, int]) -> Line:
    if ratio <= 0:
        return line

    width, height = frame_size
    (x1, y1), (x2, y2) = line
    dx = x2 - x1
    dy = y2 - y1
    x1_ext = x1 - dx * ratio
    y1_ext = y1 - dy * ratio
    x2_ext = x2 + dx * ratio
    y2_ext = y2 + dy * ratio

    # Keep the generated band inside the frame.  The line is nearly horizontal
    # in broadcast views, but clipping both axes avoids odd output on bad court
    # detections.
    return (
        (float(np.clip(x1_ext, 0.0, width - 1.0)), float(np.clip(y1_ext, 0.0, height - 1.0))),
        (float(np.clip(x2_ext, 0.0, width - 1.0)), float(np.clip(y2_ext, 0.0, height - 1.0))),
    )


def _merged_interval_width(intervals: Sequence[tuple[float, float]]) -> float:
    if not intervals:
        return 0.0
    ordered = sorted((min(a, b), max(a, b)) for a, b in intervals)
    total = 0.0
    start, end = ordered[0]
    for left, right in ordered[1:]:
        if left <= end:
            end = max(end, right)
        else:
            total += end - start
            start, end = left, right
    total += end - start
    return total


def _merge_intervals(intervals: Sequence[tuple[float, float]], *, gap_px: float = 20.0) -> list[tuple[float, float]]:
    if not intervals:
        return []

    ordered = sorted((min(a, b), max(a, b)) for a, b in intervals)
    merged: list[list[float]] = []
    for left, right in ordered:
        if not merged or left > merged[-1][1] + gap_px:
            merged.append([float(left), float(right)])
        else:
            merged[-1][1] = max(merged[-1][1], float(right))
    return [(left, right) for left, right in merged]


def _clip_segment_to_x_range(line: tuple[float, float, float, float], x_min: float, x_max: float) -> Line | None:
    x1, y1, x2, y2 = line
    left = max(min(x1, x2), x_min)
    right = min(max(x1, x2), x_max)
    if right <= left:
        return None
    return (
        (float(left), line_y_at_x(((x1, y1), (x2, y2)), left)),
        (float(right), line_y_at_x(((x1, y1), (x2, y2)), right)),
    )


def _interval_overlap(a: tuple[float, float], b: tuple[float, float]) -> float:
    return max(0.0, min(a[1], b[1]) - max(a[0], b[0]))


def clip_line_to_x_range(line: Line, x_min: float, x_max: float) -> Line:
    left = float(min(x_min, x_max))
    right = float(max(x_min, x_max))
    return ((left, line_y_at_x(line, left)), (right, line_y_at_x(line, right)))


def project_reference_line(matrix: np.ndarray, line: Line) -> Line | None:
    if matrix is None:
        return None
    pts = np.asarray([line[0], line[1]], dtype=np.float32).reshape(-1, 1, 2)
    try:
        projected = cv2.perspectiveTransform(pts, np.asarray(matrix, dtype=np.float32)).reshape(2, 2)
    except cv2.error:
        return None
    if not np.isfinite(projected).all():
        return None
    return (
        (float(projected[0, 0]), float(projected[0, 1])),
        (float(projected[1, 0]), float(projected[1, 1])),
    )


def estimate_lower_line_from_matrices(matrices: Sequence[np.ndarray | None], frame_size: tuple[int, int]) -> Line | None:
    court_ref = CourtReference()
    candidates: list[Line] = []
    for matrix in matrices:
        projected = project_reference_line(matrix, court_ref.net)
        if projected is None:
            continue
        (x1, y1), (x2, y2) = projected
        if abs(x2 - x1) < frame_size[0] * 0.2:
            continue
        candidates.append(projected)

    if not candidates:
        return None

    left_points = np.asarray([line[0] for line in candidates], dtype=np.float32)
    right_points = np.asarray([line[1] for line in candidates], dtype=np.float32)
    p1 = np.median(left_points, axis=0)
    p2 = np.median(right_points, axis=0)
    if p1[0] > p2[0]:
        p1, p2 = p2, p1
    return ((float(p1[0]), float(p1[1])), (float(p2[0]), float(p2[1])))


def _valid_point(point: Any) -> Point | None:
    if point is None:
        return None
    try:
        x = float(point[0])
        y = float(point[1])
    except (TypeError, ValueError, IndexError):
        return None
    if not np.isfinite([x, y]).all():
        return None
    return (x, y)


def estimate_lower_line_from_keypoints(
    keypoints: Sequence[Sequence[Any] | None],
    frame_size: tuple[int, int],
) -> Line | None:
    """Estimate the visible net bottom from court keypoints.

    Court keypoints 12 and 13 are the center service line endpoints.  The net
    ground line sits between those two endpoints, so this uses their midpoint
    as the main-court anchor and estimates a centered court-width span from
    available service-line keypoints.
    """

    width, _ = frame_size
    anchors: list[Point] = []
    half_spans: list[float] = []
    slopes: list[float] = []
    left_net_points: list[Point] = []
    right_net_points: list[Point] = []
    singles_to_doubles_half_width = 10.97 / 8.23

    for points in keypoints:
        if points is None or len(points) <= 13:
            continue

        top_center = _valid_point(points[12])
        bottom_center = _valid_point(points[13])
        if top_center is not None and bottom_center is not None:
            anchor = (
                (top_center[0] + bottom_center[0]) / 2.0,
                (top_center[1] + bottom_center[1]) / 2.0,
            )
            anchors.append(anchor)

            for side_index, center_point in ((8, top_center), (9, top_center), (10, bottom_center), (11, bottom_center)):
                side = _valid_point(points[side_index])
                if side is None:
                    continue
                half_span = abs(side[0] - center_point[0]) * singles_to_doubles_half_width
                if width * 0.08 <= half_span <= width * 0.45:
                    half_spans.append(float(half_span))

        top_left = _valid_point(points[8])
        top_right = _valid_point(points[9])
        bottom_left = _valid_point(points[10])
        bottom_right = _valid_point(points[11])
        if top_left is not None and bottom_left is not None:
            left_net_points.append(((top_left[0] + bottom_left[0]) / 2.0, (top_left[1] + bottom_left[1]) / 2.0))
        if top_right is not None and bottom_right is not None:
            right_net_points.append(((top_right[0] + bottom_right[0]) / 2.0, (top_right[1] + bottom_right[1]) / 2.0))
        for left, right in ((top_left, top_right), (bottom_left, bottom_right)):
            if left is None or right is None:
                continue
            dx = right[0] - left[0]
            if abs(dx) <= 1e-6:
                continue
            slope = (right[1] - left[1]) / dx
            if abs(slope) <= 0.18:
                slopes.append(float(slope))

    if not anchors:
        return None

    if left_net_points and right_net_points:
        left = tuple(np.median(np.asarray(left_net_points, dtype=np.float32), axis=0).tolist())
        right = tuple(np.median(np.asarray(right_net_points, dtype=np.float32), axis=0).tolist())
        if abs(right[0] - left[0]) > width * 0.16:
            slope = (right[1] - left[1]) / (right[0] - left[0])
            if abs(slope) <= 0.18:
                return (left, right) if left[0] <= right[0] else (right, left)

    anchor = tuple(np.median(np.asarray(anchors, dtype=np.float32), axis=0).tolist())
    half_span = float(np.median(np.asarray(half_spans, dtype=np.float32))) if half_spans else width * 0.22
    half_span = float(np.clip(half_span, width * 0.14, width * 0.36))
    slope = float(np.median(np.asarray(slopes, dtype=np.float32))) if slopes else 0.0
    return (
        (float(anchor[0] - half_span), float(anchor[1] - slope * half_span)),
        (float(anchor[0] + half_span), float(anchor[1] + slope * half_span)),
    )


def estimate_post_x_hints_from_keypoints(
    keypoints: Sequence[Sequence[Any] | None],
) -> tuple[float | None, float | None]:
    """Use detected side-line keypoints as weak x priors for the net posts."""

    left_hints: list[float] = []
    right_hints: list[float] = []
    for points in keypoints:
        if points is None or len(points) <= 13:
            continue
        for idx in (8, 10):
            point = _valid_point(points[idx])
            if point is not None:
                left_hints.append(point[0])
        for idx in (9, 11):
            point = _valid_point(points[idx])
            if point is not None:
                right_hints.append(point[0])

    left = float(np.median(np.asarray(left_hints, dtype=np.float32))) if left_hints else None
    right = float(np.median(np.asarray(right_hints, dtype=np.float32))) if right_hints else None
    return left, right


def estimate_expected_height_from_matrices(
    matrices: Sequence[np.ndarray | None],
    lower_line: Line,
    frame_size: tuple[int, int],
    config: NetBandConfig,
) -> float:
    if config.expected_height_px is not None:
        return float(np.clip(config.expected_height_px, config.min_band_height_px, config.max_band_height_px))

    court_ref = CourtReference()
    heights: list[float] = []
    for matrix in matrices:
        net_line = project_reference_line(matrix, court_ref.net)
        top_service = project_reference_line(matrix, court_ref.top_inner_line)
        bottom_service = project_reference_line(matrix, court_ref.bottom_inner_line)
        if net_line is None:
            continue

        net_mid_y = (net_line[0][1] + net_line[1][1]) / 2.0
        for service_line in (top_service, bottom_service):
            if service_line is None:
                continue
            service_mid_y = (service_line[0][1] + service_line[1][1]) / 2.0
            ground_px_per_meter = abs(service_mid_y - net_mid_y) / 6.40
            if math.isfinite(ground_px_per_meter) and ground_px_per_meter > 0:
                heights.append(ground_px_per_meter * 0.914)

    net_width_px = math.hypot(
        lower_line[1][0] - lower_line[0][0],
        lower_line[1][1] - lower_line[0][1],
    )
    aspect_expected = net_width_px * config.net_center_height_m / config.court_net_width_m

    if heights:
        ground_plane_expected = float(np.median(heights))
        # A ground-plane homography underestimates vertical height for this
        # camera angle.  Keep it only when it is consistent with the net's
        # physical height-to-width ratio in the image.
        if aspect_expected * 0.55 <= ground_plane_expected <= aspect_expected * 1.45:
            expected = ground_plane_expected
        else:
            expected = aspect_expected
    else:
        expected = aspect_expected or frame_size[1] * 0.06

    return float(np.clip(expected, config.min_band_height_px, config.max_band_height_px))


def build_background_frame(frames: Sequence[np.ndarray]) -> np.ndarray | None:
    if not frames:
        return None
    if len(frames) == 1:
        return frames[0].copy()
    stack = np.stack(frames, axis=0)
    return np.median(stack, axis=0).astype(np.uint8)


def _line_slope(line: Line) -> float:
    (x1, y1), (x2, y2) = line
    if abs(x2 - x1) <= 1e-6:
        return 0.0
    return float((y2 - y1) / (x2 - x1))


def _score_image_for_white_lines(background: np.ndarray) -> np.ndarray:
    hsv = cv2.cvtColor(background, cv2.COLOR_BGR2HSV)
    value = hsv[:, :, 2].astype(np.float32) / 255.0
    saturation = hsv[:, :, 1].astype(np.float32) / 255.0
    white_score = value * (1.0 - saturation)

    gray = cv2.cvtColor(background, cv2.COLOR_BGR2GRAY)
    grad_y = np.abs(cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3))
    grad_scale = float(np.percentile(grad_y, 98))
    if grad_scale <= 1e-6:
        grad_scale = 1.0
    grad_y = np.clip(grad_y / grad_scale, 0.0, 1.0)

    white_mask = ((value > 0.50) & (saturation < 0.55)).astype(np.uint8) * 255
    kernel_width = max(11, int(round(background.shape[1] * 0.006)))
    horizontal = cv2.morphologyEx(white_mask, cv2.MORPH_OPEN, np.ones((1, kernel_width), dtype=np.uint8))
    horizontal_score = horizontal.astype(np.float32) / 255.0

    return np.clip(white_score * 0.48 + grad_y * 0.32 + horizontal_score * 0.20, 0.0, 1.0)


def _sample_score_along_line(score_image: np.ndarray, line: Line, count: int = 80) -> float:
    height, width = score_image.shape[:2]
    x1, _ = line[0]
    x2, _ = line[1]
    values: list[float] = []
    for x in np.linspace(x1, x2, count):
        y = line_y_at_x(line, float(x))
        xi = int(round(np.clip(x, 0, width - 1)))
        yi = int(round(np.clip(y, 0, height - 1)))
        values.append(float(score_image[yi, xi]))
    return float(np.mean(values)) if values else 0.0


def _vertical_candidate_white_score(background: np.ndarray, x_mid: float, y_top: float, y_bottom: float) -> float:
    height, width = background.shape[:2]
    hsv = cv2.cvtColor(background, cv2.COLOR_BGR2HSV)
    value = hsv[:, :, 2].astype(np.float32) / 255.0
    saturation = hsv[:, :, 1].astype(np.float32) / 255.0
    white_score = value * (1.0 - saturation)

    x_min = int(max(0, round(x_mid - 5.0)))
    x_max = int(min(width - 1, round(x_mid + 5.0)))
    y_min = int(max(0, round(y_top)))
    y_max = int(min(height - 1, round(y_bottom)))
    if x_max <= x_min or y_max <= y_min:
        return 0.0
    patch = white_score[y_min : y_max + 1, x_min : x_max + 1]
    return float(max(float(patch.mean()), float(np.percentile(patch, 75)) * 0.82))


def refine_lower_line_near_court_line(
    background: np.ndarray,
    prior_line: Line,
    frame_size: tuple[int, int],
    config: NetBandConfig,
) -> Line | None:
    """Snap the court-derived net ground line to the nearest central white edge.

    The search is anchored only by the court-derived line.  It deliberately does
    not use fixed image-height bands, so a different camera height shifts the
    search naturally with the detected court.
    """

    width, height = frame_size
    x_left = float(np.clip(min(prior_line[0][0], prior_line[1][0]), 0.0, width - 1.0))
    x_right = float(np.clip(max(prior_line[0][0], prior_line[1][0]), 0.0, width - 1.0))
    if x_right - x_left <= width * 0.12:
        return None

    center_x = (x_left + x_right) / 2.0
    prior_center_y = line_y_at_x(prior_line, center_x)
    prior_slope = _line_slope(prior_line)
    tolerance = float(config.lower_line_refine_tolerance_px)

    gray = cv2.cvtColor(background, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(gray, 60, 160)
    min_length = max(90, int(round(width * 0.06)))
    max_gap = max(18, int(round(width * 0.015)))
    lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=70, minLineLength=min_length, maxLineGap=max_gap)
    if lines is None:
        return None

    score_image = _score_image_for_white_lines(background)
    center_margin = max(50.0, width * 0.045)
    prior_interval = (x_left, x_right)
    best_line: Line | None = None
    best_score = -np.inf

    for row in lines.reshape(-1, 4):
        x1, y1, x2, y2 = [float(v) for v in row]
        dx = x2 - x1
        dy = y2 - y1
        if abs(dx) <= 1e-6:
            continue

        slope = dy / dx
        if abs(slope) > config.lower_line_max_slope:
            continue

        seg_left, seg_right = sorted((x1, x2))
        if not (seg_left - center_margin <= center_x <= seg_right + center_margin):
            continue

        candidate_line: Line = ((x1, y1), (x2, y2))
        candidate_center_y = line_y_at_x(candidate_line, center_x)
        distance_to_prior = abs(candidate_center_y - prior_center_y)
        if distance_to_prior > tolerance:
            continue

        overlap = _interval_overlap(prior_interval, (seg_left, seg_right))
        length = math.hypot(dx, dy)
        strength = _sample_score_along_line(score_image, candidate_line)
        score = (
            (1.0 - distance_to_prior / max(tolerance, 1.0)) * 1.7
            + min(length / max(x_right - x_left, 1.0), 1.0) * 0.9
            + min(overlap / max(x_right - x_left, 1.0), 1.0) * 0.8
            + strength * 1.2
            - abs(slope - prior_slope) * 1.5
        )
        if score > best_score:
            best_score = score
            best_line = candidate_line

    if best_line is None:
        return None

    refined = (
        (x_left, float(np.clip(line_y_at_x(best_line, x_left), 0.0, height - 1.0))),
        (x_right, float(np.clip(line_y_at_x(best_line, x_right), 0.0, height - 1.0))),
    )
    return refined


def _find_inner_tape_connection_y(
    score_image: np.ndarray,
    post_x: float,
    lower_line: Line,
    *,
    inward_sign: int,
    search_height_px: float,
    config: NetBandConfig,
) -> tuple[float, float] | None:
    height, width = score_image.shape[:2]
    lower_y = line_y_at_x(lower_line, post_x)
    min_offset = max(float(config.net_top_min_offset_px), 4.0)
    y_min = int(max(0, round(lower_y - max(search_height_px, min_offset + 8.0))))
    y_max = int(min(height - 1, round(lower_y - min_offset)))
    if y_max <= y_min:
        return None

    inner_width = max(28, int(round(width * 0.035)))
    inner_gap = max(4, int(round(width * 0.003)))
    if inward_sign > 0:
        x_min = int(max(0, round(post_x + inner_gap)))
        x_max = int(min(width - 1, round(post_x + inner_width)))
    else:
        x_min = int(max(0, round(post_x - inner_width)))
        x_max = int(min(width - 1, round(post_x - inner_gap)))
    if x_max <= x_min:
        return None

    y_values = np.arange(y_min, y_max + 1, dtype=np.float32)
    row_strength = score_image[y_min : y_max + 1, x_min : x_max + 1].mean(axis=1)
    if len(row_strength) >= 5:
        row_strength = np.convolve(row_strength, np.ones(5, dtype=np.float32) / 5.0, mode="same")
    if len(row_strength) == 0:
        return None

    threshold = max(0.045, float(np.max(row_strength)) * 0.52)
    close_enough = np.flatnonzero(row_strength >= threshold)
    best_idx = int(close_enough[-1]) if len(close_enough) else int(np.argmax(row_strength))
    score = float(row_strength[best_idx])
    if score < 0.045:
        return None
    return float(y_values[best_idx]), score


def _vertical_post_candidates(
    background: np.ndarray,
    score_image: np.ndarray,
    lower_line: Line,
    frame_size: tuple[int, int],
    *,
    side: str,
    side_hint_x: float | None,
    search_height_px: float,
    config: NetBandConfig,
) -> list[tuple[float, float, Line, float | None]]:
    width, _ = frame_size
    prior_x = lower_line[0][0] if side == "left" else lower_line[1][0]
    inward_sign = 1 if side == "left" else -1
    x_window = max(width * config.post_search_x_ratio, abs(lower_line[1][0] - lower_line[0][0]) * 0.18)

    gray = cv2.cvtColor(background, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(gray, 60, 160)
    min_length = max(float(config.post_min_length_px), width * 0.015)
    max_gap = max(12, int(round(width * 0.008)))
    lines = cv2.HoughLinesP(
        edges,
        1,
        np.pi / 180,
        threshold=20,
        minLineLength=int(round(min_length)),
        maxLineGap=max(max_gap, 18),
    )
    if lines is None:
        return []

    candidates: list[tuple[float, float, Line, float | None]] = []
    for row in lines.reshape(-1, 4):
        x1, y1, x2, y2 = [float(v) for v in row]
        dx = x2 - x1
        dy = y2 - y1
        if abs(dy) <= 1e-6:
            continue
        x_slope = dx / dy
        if abs(x_slope) > config.post_max_x_slope:
            continue

        x_mid = (x1 + x2) / 2.0
        if abs(x_mid - prior_x) > x_window:
            continue
        if side_hint_x is not None and abs(x_mid - side_hint_x) > x_window * 0.58:
            continue

        y_top = min(y1, y2)
        y_bottom = max(y1, y2)
        lower_y = line_y_at_x(lower_line, x_mid)
        white_score = _vertical_candidate_white_score(background, x_mid, y_top, y_bottom)
        if white_score < config.post_min_white_score:
            continue
        if y_top < lower_y - search_height_px * config.post_max_above_net_factor:
            continue
        if y_bottom < lower_y - search_height_px * 1.25:
            continue
        if y_top > lower_y + search_height_px * 0.45:
            continue

        if y_top <= lower_y <= y_bottom:
            lower_distance = 0.0
        else:
            lower_distance = min(abs(y_top - lower_y), abs(y_bottom - lower_y))
        if lower_distance > max(search_height_px * 0.75, 45.0):
            continue

        connection = _find_inner_tape_connection_y(
            score_image,
            x_mid,
            lower_line,
            inward_sign=inward_sign,
            search_height_px=search_height_px,
            config=config,
        )
        connection_y = None if connection is None else connection[0]
        connection_score = 0.0 if connection is None else connection[1]

        length = math.hypot(dx, dy)
        length_score = min(length / max(search_height_px * 1.2, 1.0), 1.35)
        top_y_target = lower_y - search_height_px * 0.95
        top_score = 1.0 - min(abs(y_top - top_y_target) / max(search_height_px * 0.95, 1.0), 1.0)
        lower_score = 1.0 - min(lower_distance / max(search_height_px * 0.75, 1.0), 1.0)
        distance_score = 1.0 - min(abs(x_mid - prior_x) / max(x_window, 1.0), 1.0)
        hint_score = 0.0
        if side_hint_x is not None:
            hint_score = 1.0 - min(abs(x_mid - side_hint_x) / max(x_window, 1.0), 1.0)
        score = (
            length_score * 1.0
            + top_score * 0.8
            + lower_score * 1.25
            + distance_score * 0.25
            + hint_score * config.post_hint_score_weight
            + white_score * config.post_white_score_weight
            + connection_score * 1.6
        )
        candidates.append((float(score), float(x_mid), ((x1, y1), (x2, y2)), connection_y))

    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates


def detect_post_bounded_lower_line(
    background: np.ndarray,
    prior_line: Line,
    frame_size: tuple[int, int],
    *,
    search_height_px: float,
    config: NetBandConfig,
    side_hints: tuple[float | None, float | None] | None = None,
) -> Line | None:
    """Find net posts near the main court sides and bound the net line to them."""

    score_image = _score_image_for_white_lines(background)
    left_candidates = _vertical_post_candidates(
        background,
        score_image,
        prior_line,
        frame_size,
        side="left",
        side_hint_x=None if side_hints is None else side_hints[0],
        search_height_px=search_height_px,
        config=config,
    )
    right_candidates = _vertical_post_candidates(
        background,
        score_image,
        prior_line,
        frame_size,
        side="right",
        side_hint_x=None if side_hints is None else side_hints[1],
        search_height_px=search_height_px,
        config=config,
    )
    if not left_candidates or not right_candidates:
        return None

    left_x = left_candidates[0][1]
    right_x = right_candidates[0][1]
    if right_x <= left_x or right_x - left_x < frame_size[0] * 0.16:
        return None

    return (
        (float(left_x), float(line_y_at_x(prior_line, left_x))),
        (float(right_x), float(line_y_at_x(prior_line, right_x))),
    )


def sample_net_tape_points_above_lower_line(
    background: np.ndarray,
    lower_line: Line,
    *,
    count: int,
    search_height_px: float,
    config: NetBandConfig,
) -> list[Point]:
    """Sample the upper strong white/edge curve above the net ground line."""

    height, width = background.shape[:2]
    score_image = _score_image_for_white_lines(background)
    x1, _ = lower_line[0]
    x2, _ = lower_line[1]
    min_offset = max(float(config.net_top_min_offset_px), 4.0)
    max_search = max(float(search_height_px), min_offset + 6.0)
    half_x = max(5, int(round(width * 0.004)))

    points: list[Point] = []
    for x in np.linspace(x1, x2, count):
        lower_y = line_y_at_x(lower_line, float(x))
        y_min = int(max(0, round(lower_y - max_search)))
        y_max = int(min(height - 1, round(lower_y - min_offset)))
        if y_max <= y_min:
            continue

        x_min = int(max(0, round(x - half_x)))
        x_max = int(min(width - 1, round(x + half_x)))
        if x_max <= x_min:
            continue

        y_values = np.arange(y_min, y_max + 1, dtype=np.float32)
        offsets = lower_y - y_values
        patch = score_image[y_min : y_max + 1, x_min : x_max + 1]
        row_strength = patch.mean(axis=1)
        if len(row_strength) >= 5:
            row_strength = np.convolve(row_strength, np.ones(5, dtype=np.float32) / 5.0, mode="same")
        near_bias = np.exp(-offsets / max(max_search * 0.32, 10.0))
        score = row_strength * (0.28 + 0.72 * near_bias)
        threshold = max(0.045, float(np.max(score)) * 0.52)
        close_enough = np.flatnonzero(score >= threshold)
        if len(close_enough):
            runs: list[tuple[int, int]] = []
            run_start = int(close_enough[0])
            previous = run_start
            for idx in map(int, close_enough[1:]):
                if idx == previous + 1:
                    previous = idx
                else:
                    runs.append((run_start, previous))
                    run_start = previous = idx
            runs.append((run_start, previous))

            viable_runs = [(start, end) for start, end in runs if end - start + 1 >= 2]
            start, end = (viable_runs or runs)[0]
            best_idx = start + int(np.argmax(score[start : end + 1]))
        else:
            best_idx = int(np.argmax(score))
        if float(score[best_idx]) < 0.045:
            continue
        points.append((float(x), float(y_values[best_idx])))

    if len(points) < max(6, count // 6):
        return points

    offsets = np.asarray([line_y_at_x(lower_line, x) - y for x, y in points], dtype=np.float32)
    median_offset = float(np.median(offsets))
    mad = float(np.median(np.abs(offsets - median_offset)))
    tolerance = max(18.0, mad * 3.0)
    filtered = [
        point
        for point, offset in zip(points, offsets)
        if abs(float(offset) - median_offset) <= tolerance
    ]
    return filtered if len(filtered) >= max(6, count // 6) else points


def sample_net_tape_points_with_height_prior(
    background: np.ndarray,
    lower_line: Line,
    *,
    count: int,
    expected_height_px: float,
    search_height_px: float,
    config: NetBandConfig,
) -> list[Point]:
    """Sample the net top near the physical post-to-center height prior.

    This is used after the left/right posts have bounded the net.  In that
    case the nearest bright edge above the lower line is often the net bottom,
    so the score is pulled toward the expected top-tape height instead.
    """

    height, width = background.shape[:2]
    score_image = _score_image_for_white_lines(background)
    x1, _ = lower_line[0]
    x2, _ = lower_line[1]
    span = max(abs(x2 - x1), 1.0)
    min_offset = max(float(config.net_top_min_offset_px), 4.0)
    max_search = max(float(search_height_px), float(expected_height_px) * 1.35, min_offset + 8.0)
    half_x = max(6, int(round(width * 0.004)))
    sigma = max(float(expected_height_px) * 0.28, 16.0)

    points: list[Point] = []
    for x in np.linspace(x1, x2, count):
        x_float = float(x)
        lower_y = line_y_at_x(lower_line, x_float)
        y_min = int(max(0, round(lower_y - max_search)))
        y_max = int(min(height - 1, round(lower_y - min_offset)))
        if y_max <= y_min:
            continue

        x_min = int(max(0, round(x_float - half_x)))
        x_max = int(min(width - 1, round(x_float + half_x)))
        if x_max <= x_min:
            continue

        y_values = np.arange(y_min, y_max + 1, dtype=np.float32)
        offsets = lower_y - y_values
        patch = score_image[y_min : y_max + 1, x_min : x_max + 1]
        row_strength = patch.mean(axis=1)
        if len(row_strength) >= 5:
            row_strength = np.convolve(row_strength, np.ones(5, dtype=np.float32) / 5.0, mode="same")

        ratio = float(np.clip((x_float - x1) / span, 0.0, 1.0))
        expected_offset = float(expected_height_px) * net_sag_factor(ratio, config)
        prior = np.exp(-((offsets - expected_offset) ** 2) / (2.0 * sigma * sigma))
        score = row_strength * (0.18 + 0.82 * prior)
        best_idx = int(np.argmax(score))
        if float(score[best_idx]) < 0.045:
            continue
        points.append((x_float, float(y_values[best_idx])))

    if len(points) < max(6, count // 6):
        return points

    xs = np.asarray([p[0] for p in points], dtype=np.float64)
    ys = np.asarray([p[1] for p in points], dtype=np.float64)
    x_center = float((xs.min() + xs.max()) / 2.0)
    x_scale = float(max((xs.max() - xs.min()) / 2.0, 1.0))
    fit_degree = int(min(max(1, config.polynomial_degree), len(points) - 1))
    coeff = np.polyfit((xs - x_center) / x_scale, ys, deg=fit_degree)
    residual = np.abs(np.polyval(coeff, (xs - x_center) / x_scale) - ys)
    keep = residual <= max(config.fit_outlier_px, float(np.median(residual)) * 2.5)
    filtered = [point for point, keep_point in zip(points, keep) if bool(keep_point)]
    return filtered if len(filtered) >= max(6, count // 6) else points


def trim_top_tape_to_continuous_segment(
    points: Sequence[Point],
    config: NetBandConfig,
) -> list[Point]:
    """Keep the longest continuous run of top-tape samples.

    White posts and fence lines can produce valid-looking samples after the
    real tape ends.  The tape itself is continuous, so large frame-to-frame y
    jumps are used as endpoint evidence.
    """

    if len(points) < 3:
        return list(points)

    ordered = sorted(points, key=lambda point: point[0])
    max_step = float(config.top_tape_max_step_px)
    runs: list[list[Point]] = []
    current = [ordered[0]]
    for previous, point in zip(ordered, ordered[1:]):
        if abs(point[1] - previous[1]) <= max_step:
            current.append(point)
        else:
            runs.append(current)
            current = [point]
    runs.append(current)

    min_len = max(config.polynomial_degree + 1, len(ordered) // 3)
    valid_runs = [run for run in runs if len(run) >= min_len]
    if not valid_runs:
        return ordered
    return max(valid_runs, key=len)


def refine_lower_line_from_top_curve(
    background: np.ndarray,
    guide_lower_line: Line,
    top_coefficients: Sequence[float],
    x_center: float,
    x_scale: float,
    *,
    expected_height_px: float,
    config: NetBandConfig,
) -> Line | None:
    """Fit the visible bottom edge of the net from image edges below the top."""

    height, width = background.shape[:2]
    gray = cv2.cvtColor(background, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blur, 50, 150).astype(np.float32) / 255.0
    grad_y = np.abs(cv2.Sobel(blur, cv2.CV_32F, 0, 1, ksize=3))
    grad_scale = float(np.percentile(grad_y, 98))
    if grad_scale <= 1e-6:
        grad_scale = 1.0
    grad_y = np.clip(grad_y / grad_scale, 0.0, 1.0)
    edge_score = edges * 0.55 + grad_y * 0.45

    x1, _ = guide_lower_line[0]
    x2, _ = guide_lower_line[1]
    if abs(x2 - x1) <= width * 0.12:
        return None

    expected_offset = float(expected_height_px) * float(config.lower_from_top_height_ratio)
    min_offset = max(float(config.min_band_height_px), float(expected_height_px) * config.lower_from_top_min_offset_ratio)
    max_offset = max(min_offset + 8.0, float(expected_height_px) * config.lower_from_top_max_offset_ratio)
    sigma = max(float(expected_height_px) * 0.20, 12.0)
    half_x = max(6, int(round(width * 0.004)))
    coeff = np.asarray(top_coefficients, dtype=np.float64)

    points: list[Point] = []
    for x in np.linspace(x1, x2, max(config.sample_count, 24)):
        x_float = float(x)
        top_y = float(np.polyval(coeff, (x_float - float(x_center)) / max(float(x_scale), 1.0)))
        guide_y = line_y_at_x(guide_lower_line, x_float)
        y_min = int(max(0, round(top_y + min_offset)))
        y_max = int(min(height - 1, round(min(guide_y + 8.0, top_y + max_offset))))
        if y_max <= y_min:
            continue

        x_min = int(max(0, round(x_float - half_x)))
        x_max = int(min(width - 1, round(x_float + half_x)))
        if x_max <= x_min:
            continue

        y_values = np.arange(y_min, y_max + 1, dtype=np.float32)
        offsets = y_values - top_y
        row_strength = edge_score[y_min : y_max + 1, x_min : x_max + 1].mean(axis=1)
        if len(row_strength) >= 5:
            row_strength = np.convolve(row_strength, np.ones(5, dtype=np.float32) / 5.0, mode="same")
        prior = np.exp(-((offsets - expected_offset) ** 2) / (2.0 * sigma * sigma))
        score = row_strength * (0.18 + 0.82 * prior)
        best_idx = int(np.argmax(score))
        if float(score[best_idx]) < 0.045:
            continue
        points.append((x_float, float(y_values[best_idx])))

    if len(points) < max(8, config.sample_count // 6):
        return None

    xs = np.asarray([p[0] for p in points], dtype=np.float64)
    ys = np.asarray([p[1] for p in points], dtype=np.float64)
    coeff_line = np.polyfit(xs, ys, deg=1)
    residual = np.abs(np.polyval(coeff_line, xs) - ys)
    keep = residual <= max(config.fit_outlier_px, float(np.median(residual)) * 2.5)
    if int(keep.sum()) >= max(8, config.sample_count // 6):
        coeff_line = np.polyfit(xs[keep], ys[keep], deg=1)

    left_y = float(np.polyval(coeff_line, x1))
    right_y = float(np.polyval(coeff_line, x2))
    return (
        (float(x1), float(np.clip(left_y, 0.0, height - 1.0))),
        (float(x2), float(np.clip(right_y, 0.0, height - 1.0))),
    )


def sample_top_edge_points(
    background: np.ndarray,
    lower_line: Line,
    *,
    expected_height_px: float,
    search_height_px: float,
    config: NetBandConfig,
) -> list[Point]:
    height, width = background.shape[:2]
    gray = cv2.cvtColor(background, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(gray, 50, 150)
    grad_y = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
    grad_abs = np.abs(grad_y)
    grad_scale = float(np.percentile(grad_abs, 98))
    if grad_scale <= 1e-6:
        grad_scale = 1.0

    points: list[Point] = []
    x1, _ = lower_line[0]
    x2, _ = lower_line[1]
    for ratio in np.linspace(0.04, 0.96, config.sample_count):
        x = x1 + (x2 - x1) * float(ratio)
        lower_y = line_y_at_x(lower_line, x)
        y_min = int(max(0, round(lower_y - search_height_px)))
        y_max = int(min(height - 1, round(lower_y - max(config.min_band_height_px, expected_height_px * 0.35))))
        if y_max <= y_min:
            continue

        x_min = int(max(0, round(x - config.sample_half_width_px)))
        x_max = int(min(width - 1, round(x + config.sample_half_width_px)))
        if x_max <= x_min:
            continue

        edge_patch = edges[y_min : y_max + 1, x_min : x_max + 1].astype(np.float32) / 255.0
        grad_patch = np.clip(grad_abs[y_min : y_max + 1, x_min : x_max + 1] / grad_scale, 0.0, 1.0)
        gray_patch = gray[y_min : y_max + 1, x_min : x_max + 1].astype(np.float32) / 255.0
        row_strength = edge_patch.mean(axis=1) * 0.55 + grad_patch.mean(axis=1) * 0.35 + gray_patch.mean(axis=1) * 0.10

        y_values = np.arange(y_min, y_max + 1, dtype=np.float32)
        sag_factor = net_sag_factor(float(ratio), config)
        expected_y = lower_y - expected_height_px * sag_factor
        sigma = max(search_height_px * 0.16, 10.0)
        prior = np.exp(-((y_values - expected_y) ** 2) / (2.0 * sigma * sigma))
        score = row_strength * (0.20 + 0.80 * prior)

        best_idx = int(np.argmax(score))
        if float(score[best_idx]) < 0.055:
            continue
        points.append((float(x), float(y_values[best_idx])))

    return points


def net_sag_factor(ratio: float, config: NetBandConfig) -> float:
    center_height = max(config.net_center_height_m, 1e-6)
    post_extra_ratio = max(config.net_post_height_m / center_height - 1.0, 0.0)
    return 1.0 + post_extra_ratio * (2.0 * float(ratio) - 1.0) ** 2


def physical_top_y_at_x(
    lower_line: Line,
    x: float,
    expected_height_px: float,
    config: NetBandConfig,
) -> float:
    x1, _ = lower_line[0]
    x2, _ = lower_line[1]
    denom = max(abs(x2 - x1), 1.0)
    ratio = (float(x) - x1) / denom
    ratio = float(np.clip(ratio, 0.0, 1.0))
    return line_y_at_x(lower_line, x) - expected_height_px * net_sag_factor(ratio, config)


def filter_points_by_physical_prior(
    points: Sequence[Point],
    lower_line: Line,
    *,
    expected_height_px: float,
    config: NetBandConfig,
) -> list[Point]:
    if not points:
        return []

    filtered: list[Point] = []
    tolerance = max(config.edge_prior_tolerance_px, expected_height_px * 0.22)
    min_height = max(config.min_band_height_px, expected_height_px * 0.55)
    max_height = min(config.max_band_height_px, expected_height_px * 1.35)
    for x, y in points:
        lower_y = line_y_at_x(lower_line, x)
        height_px = lower_y - y
        if height_px < min_height or height_px > max_height:
            continue
        expected_y = physical_top_y_at_x(lower_line, x, expected_height_px, config)
        if abs(y - expected_y) > tolerance:
            continue
        filtered.append((x, y))
    return filtered


def fit_weighted_curve(
    edge_points: Sequence[Point],
    lower_line: Line,
    *,
    expected_height_px: float,
    x_center: float,
    x_scale: float,
    config: NetBandConfig,
) -> tuple[np.ndarray, list[Point]]:
    prior_points = physics_fallback_points(
        lower_line,
        expected_height_px,
        count=max(config.sample_count, 12),
        config=config,
    )
    all_points = list(edge_points) + prior_points
    xs = np.asarray([p[0] for p in all_points], dtype=np.float64)
    ys = np.asarray([p[1] for p in all_points], dtype=np.float64)
    us = (xs - x_center) / x_scale
    weights = np.concatenate(
        [
            np.ones(len(edge_points), dtype=np.float64),
            np.full(len(prior_points), config.prior_fit_weight, dtype=np.float64),
        ]
    )
    coeff = np.polyfit(us, ys, deg=config.polynomial_degree, w=weights)
    return coeff, list(edge_points)


def curve_is_physically_plausible(
    coeff: np.ndarray,
    lower_line: Line,
    x_center: float,
    x_scale: float,
) -> bool:
    x1, _ = lower_line[0]
    x2, _ = lower_line[1]
    xs = np.linspace(x1, x2, 9)
    ys = np.polyval(coeff, (xs - x_center) / x_scale)
    if not np.isfinite(ys).all():
        return False

    center_y = float(np.polyval(coeff, 0.0))
    endpoint_y = float((ys[0] + ys[-1]) / 2.0)
    # The center strap is lower than the posts, so in image coordinates the
    # center should be at least as low as the ends for the standard broadcast
    # view.  A small tolerance keeps near-flat nets valid.
    return center_y >= endpoint_y - 6.0


def fit_top_curve(
    points: Sequence[Point],
    lower_line: Line,
    *,
    expected_height_px: float,
    config: NetBandConfig,
) -> tuple[list[float], float, float, list[Point], str]:
    x1, _ = lower_line[0]
    x2, _ = lower_line[1]
    x_center = (x1 + x2) / 2.0
    x_scale = max(abs(x2 - x1) / 2.0, 1.0)

    prior_filtered = filter_points_by_physical_prior(
        points,
        lower_line,
        expected_height_px=expected_height_px,
        config=config,
    )

    if len(prior_filtered) >= max(config.polynomial_degree + 1, 5):
        coeff, used_points = fit_weighted_curve(
            prior_filtered,
            lower_line,
            expected_height_px=expected_height_px,
            x_center=x_center,
            x_scale=x_scale,
            config=config,
        )
        xs = np.asarray([p[0] for p in used_points], dtype=np.float64)
        ys = np.asarray([p[1] for p in used_points], dtype=np.float64)
        us = (xs - x_center) / x_scale
        pred = np.polyval(coeff, us)
        residual = np.abs(pred - ys)
        keep = residual <= max(config.fit_outlier_px, float(np.median(residual)) * 2.5)
        if int(keep.sum()) >= max(config.polynomial_degree + 1, 5):
            refined = [point for point, keep_point in zip(used_points, keep) if bool(keep_point)]
            coeff, used_points = fit_weighted_curve(
                refined,
                lower_line,
                expected_height_px=expected_height_px,
                x_center=x_center,
                x_scale=x_scale,
                config=config,
            )
        if curve_is_physically_plausible(coeff, lower_line, x_center, x_scale):
            return [float(v) for v in coeff], x_center, x_scale, list(used_points), "image_edges_physics_guided_polyfit"

    generated = physics_fallback_points(
        lower_line,
        expected_height_px,
        count=max(config.sample_count, 12),
        config=config,
    )
    xs = np.asarray([p[0] for p in generated], dtype=np.float64)
    ys = np.asarray([p[1] for p in generated], dtype=np.float64)
    us = (xs - x_center) / x_scale
    coeff = np.polyfit(us, ys, deg=config.polynomial_degree)
    return [float(v) for v in coeff], x_center, x_scale, generated, "physics_fallback"


def physics_fallback_points(
    lower_line: Line,
    expected_height_px: float,
    count: int = 20,
    config: NetBandConfig | None = None,
) -> list[Point]:
    config = config or NetBandConfig()
    x1, _ = lower_line[0]
    x2, _ = lower_line[1]
    points: list[Point] = []
    for ratio in np.linspace(0.04, 0.96, count):
        x = x1 + (x2 - x1) * float(ratio)
        points.append((float(x), float(physical_top_y_at_x(lower_line, x, expected_height_px, config))))
    return points


def fit_curve_from_points(
    points: Sequence[Point],
    degree: int,
    *,
    domain_line: Line | None = None,
) -> tuple[list[float], float, float]:
    if not points:
        raise ValueError("Cannot fit a curve without points.")

    xs = np.asarray([point[0] for point in points], dtype=np.float64)
    ys = np.asarray([point[1] for point in points], dtype=np.float64)
    if domain_line is None:
        x_center = float((xs.min() + xs.max()) / 2.0)
        x_scale = float(max((xs.max() - xs.min()) / 2.0, 1.0))
    else:
        x1, _ = domain_line[0]
        x2, _ = domain_line[1]
        x_center = float((x1 + x2) / 2.0)
        x_scale = float(max(abs(x2 - x1) / 2.0, 1.0))
    fit_degree = int(min(max(1, degree), len(points) - 1))
    coeff = np.polyfit((xs - x_center) / x_scale, ys, deg=fit_degree)
    return [float(v) for v in coeff], x_center, x_scale


def points_on_line(line: Line, count: int) -> list[Point]:
    x1, _ = line[0]
    x2, _ = line[1]
    return [(float(x), float(line_y_at_x(line, float(x)))) for x in np.linspace(x1, x2, count)]


def sample_net_tape_points(
    background: np.ndarray,
    guide_line: Line,
    *,
    count: int,
    search_window_px: float,
) -> list[Point]:
    """Sample the bright curved tape near a selected approximate net line."""

    height, width = background.shape[:2]
    hsv = cv2.cvtColor(background, cv2.COLOR_BGR2HSV)
    value = hsv[:, :, 2].astype(np.float32) / 255.0
    saturation = hsv[:, :, 1].astype(np.float32) / 255.0
    white_score = value * (1.0 - saturation)

    gray = cv2.cvtColor(background, cv2.COLOR_BGR2GRAY)
    grad_y = np.abs(cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3))
    grad_scale = float(np.percentile(grad_y, 98))
    if grad_scale <= 1e-6:
        grad_scale = 1.0
    grad_y = np.clip(grad_y / grad_scale, 0.0, 1.0)

    x1, _ = guide_line[0]
    x2, _ = guide_line[1]
    points: list[Point] = []
    sigma = max(float(search_window_px) * 0.38, 5.0)
    half_x = max(4, int(round(width * 0.003)))
    for x in np.linspace(x1, x2, count):
        guide_y = line_y_at_x(guide_line, float(x))
        y_min = int(max(0, round(guide_y - search_window_px)))
        y_max = int(min(height - 1, round(guide_y + search_window_px)))
        if y_max <= y_min:
            continue

        x_min = int(max(0, round(x - half_x)))
        x_max = int(min(width - 1, round(x + half_x)))
        if x_max <= x_min:
            continue

        y_values = np.arange(y_min, y_max + 1, dtype=np.float32)
        tape_score = white_score[y_min : y_max + 1, x_min : x_max + 1].mean(axis=1)
        edge_score = grad_y[y_min : y_max + 1, x_min : x_max + 1].mean(axis=1)
        proximity = np.exp(-((y_values - guide_y) ** 2) / (2.0 * sigma * sigma))
        score = (tape_score * 0.78 + edge_score * 0.22) * (0.20 + 0.80 * proximity)
        best_idx = int(np.argmax(score))
        points.append((float(x), float(y_values[best_idx])))

    if len(points) < max(5, count // 5):
        return points_on_line(guide_line, count)
    return points


def fit_net_band_from_samples(
    frames: Sequence[np.ndarray],
    matrices: Sequence[np.ndarray | None],
    frame_size: tuple[int, int],
    config: NetBandConfig | None = None,
    keypoints: Sequence[Sequence[Any] | None] | None = None,
) -> NetBandModel:
    config = config or NetBandConfig()
    matrix_lower_line = estimate_lower_line_from_matrices(matrices, frame_size)
    keypoint_lower_line = estimate_lower_line_from_keypoints(keypoints or [], frame_size)
    raw_lower_line = matrix_lower_line or keypoint_lower_line
    if raw_lower_line is None:
        raise RuntimeError("Could not estimate the net line from court detection.")

    expected_height = estimate_expected_height_from_matrices(matrices, raw_lower_line, frame_size, config)
    search_height = float(config.search_height_px or min(max(expected_height * 1.2, 48.0), config.max_band_height_px))
    background = build_background_frame(frames)

    line_source = "court_projected_lower" if matrix_lower_line is not None else "court_keypoint_lower"
    if background is not None and config.use_image_top_line:
        prior_lower_line = extend_line(raw_lower_line, config.line_extension_ratio, frame_size)
        post_lower_line = None
        if config.use_post_bounds:
            side_hints = estimate_post_x_hints_from_keypoints(keypoints or [])
            post_lower_line = detect_post_bounded_lower_line(
                background,
                prior_lower_line,
                frame_size,
                search_height_px=float(config.top_search_above_lower_px or search_height),
                config=config,
                side_hints=side_hints,
            )
        lower_line = post_lower_line or (
            refine_lower_line_near_court_line(background, prior_lower_line, frame_size, config)
            or prior_lower_line
        )
        if post_lower_line is not None:
            top_points = sample_net_tape_points_with_height_prior(
                background,
                lower_line,
                count=max(config.sample_count, 12),
                expected_height_px=expected_height,
                search_height_px=float(config.top_search_above_lower_px or search_height),
                config=config,
            )
        else:
            top_points = sample_net_tape_points_above_lower_line(
                background,
                lower_line,
                count=max(config.sample_count, 12),
                search_height_px=float(config.top_search_above_lower_px or search_height),
                config=config,
            )
        if len(top_points) >= max(config.polynomial_degree + 1, 6):
            if post_lower_line is not None:
                top_points = trim_top_tape_to_continuous_segment(top_points, config)
                if len(top_points) >= max(config.polynomial_degree + 1, 6):
                    top_xs = [point[0] for point in top_points]
                    lower_line = clip_line_to_x_range(lower_line, min(top_xs), max(top_xs))
            coeff, x_center, x_scale = fit_curve_from_points(
                top_points,
                config.polynomial_degree,
                domain_line=lower_line,
            )
            xs = np.asarray([p[0] for p in top_points], dtype=np.float64)
            ys = np.asarray([p[1] for p in top_points], dtype=np.float64)
            residual = np.abs(np.polyval(coeff, (xs - x_center) / x_scale) - ys)
            keep = residual <= max(config.fit_outlier_px, float(np.median(residual)) * 2.5)
            if int(keep.sum()) >= max(config.polynomial_degree + 1, 6):
                top_points = [point for point, keep_point in zip(top_points, keep) if bool(keep_point)]
                coeff, x_center, x_scale = fit_curve_from_points(
                    top_points,
                    config.polynomial_degree,
                    domain_line=lower_line,
                )
            source_prefix = (
                "post_bounded_height_prior_net_tape"
                if post_lower_line is not None
                else "center_line_image_net_tape_polyfit"
            )
            if post_lower_line is not None:
                lower_line = (
                    refine_lower_line_from_top_curve(
                        background,
                        lower_line,
                        coeff,
                        x_center,
                        x_scale,
                        expected_height_px=expected_height,
                        config=config,
                    )
                    or lower_line
                )
            source = f"{source_prefix}+{line_source}"
        else:
            top_points = physics_fallback_points(
                lower_line,
                expected_height,
                count=max(config.sample_count, 12),
                config=config,
            )
            coeff, x_center, x_scale = fit_curve_from_points(
                top_points,
                config.polynomial_degree,
                domain_line=lower_line,
            )
            source = f"physics_fallback+{line_source}"
        return NetBandModel(
            lower_line=lower_line,
            top_coefficients=coeff,
            x_center=float(x_center),
            x_scale=float(x_scale),
            top_points=[(round(p[0], 3), round(p[1], 3)) for p in top_points],
            source=source,
            frame_size={"width": int(frame_size[0]), "height": int(frame_size[1])},
            expected_height_px=round(float(expected_height), 3),
            search_height_px=round(float(search_height), 3),
            band_margin_px=float(config.band_margin_px),
        )

    lower_line = extend_line(raw_lower_line, config.line_extension_ratio, frame_size)

    top_points: list[Point] = []
    if background is not None and config.use_image_top_edges:
        top_points = sample_top_edge_points(
            background,
            lower_line,
            expected_height_px=expected_height,
            search_height_px=search_height,
            config=config,
        )

    coeff, x_center, x_scale, used_points, source = fit_top_curve(
        top_points,
        lower_line,
        expected_height_px=expected_height,
        config=config,
    )
    return NetBandModel(
        lower_line=lower_line,
        top_coefficients=coeff,
        x_center=float(x_center),
        x_scale=float(x_scale),
        top_points=[(round(p[0], 3), round(p[1], 3)) for p in used_points],
        source=f"{source}+{line_source}",
        frame_size={"width": int(frame_size[0]), "height": int(frame_size[1])},
        expected_height_px=round(float(expected_height), 3),
        search_height_px=round(float(search_height), 3),
        band_margin_px=float(config.band_margin_px),
    )
