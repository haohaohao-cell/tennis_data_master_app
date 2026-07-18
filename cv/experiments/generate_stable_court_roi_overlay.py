"""Generate a fixed court ROI from a stable multi-frame court estimate."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

import cv2
import numpy as np
import torch
import torch.nn.functional as F


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from cv.config import DEFAULT_COURT_MODEL_PATH, INPUT_DIR, OUTPUT_DIR
from cv.court.homography import get_trans_matrix
from cv.court.postprocess import postprocess, refine_kps
from cv.court.reference import CourtReference
from cv.court.stability import StableCourtEstimate, select_stable_court_matrix
from cv.models.court_detection import BallTrackerNet


DEFAULT_INPUT_VIDEO = INPUT_DIR / "real_court/real02.mp4"


def load_court_model(model_path: Path, device: torch.device) -> BallTrackerNet:
    model = BallTrackerNet(out_channels=15).to(device)
    state_dict = torch.load(model_path, map_location=device, weights_only=True)
    if isinstance(state_dict, dict) and "state_dict" in state_dict:
        state_dict = state_dict["state_dict"]
    model.load_state_dict(state_dict)
    model.eval()
    return model


def sample_frame_indices(total_frames: int, sample_count: int) -> list[int]:
    if total_frames <= 0:
        raise ValueError("total_frames must be positive")
    count = min(max(2, sample_count), total_frames)
    return sorted({int(round(value)) for value in np.linspace(0, total_frames - 1, count)})


def detect_court_matrix(
    frame: np.ndarray,
    model: BallTrackerNet,
    device: torch.device,
    court_ref: CourtReference,
) -> tuple[np.ndarray | None, str, int]:
    """Run the production detector, then its all-keypoint RANSAC fallback."""
    height, width = frame.shape[:2]
    resized = cv2.resize(frame, (640, 360))
    tensor = torch.tensor(
        np.rollaxis(resized.astype(np.float32) / 255.0, 2, 0)
    ).unsqueeze(0).to(device)
    with torch.no_grad():
        prediction = F.sigmoid(model(tensor.float())[0]).cpu().numpy()

    scale_x, scale_y = width / 640.0, height / 360.0
    points: list[tuple[int | None, int | None]] = []
    for keypoint_index in range(14):
        heatmap = (prediction[keypoint_index] * 255).astype(np.uint8)
        x_pred, y_pred = postprocess(
            heatmap,
            scale=1,
            low_thresh=170,
            max_radius=25,
        )
        if x_pred is None or y_pred is None:
            points.append((None, None))
            continue

        x_image = int(x_pred * scale_x)
        y_image = int(y_pred * scale_y)
        if keypoint_index not in (8, 9, 12):
            y_image, x_image = refine_kps(frame, y_image, x_image)
        points.append((x_image, y_image))

    detected_count = sum(point[0] is not None for point in points)
    matrix = get_trans_matrix(points, court_ref=court_ref)
    if matrix is not None:
        return matrix, "production", detected_count

    reference_points = []
    image_points = []
    for keypoint_index, point in enumerate(points):
        if point[0] is None or point[1] is None:
            continue
        reference_points.append(court_ref.key_points[keypoint_index])
        image_points.append(point)
    if len(reference_points) < 4:
        return None, "failed", detected_count

    matrix, inlier_mask = cv2.findHomography(
        np.float32(reference_points),
        np.float32(image_points),
        cv2.RANSAC,
        5.0,
    )
    if matrix is None or inlier_mask is None or int(inlier_mask.sum()) < 4:
        return None, "failed", detected_count
    return matrix, "fallback", detected_count


def detect_stable_matrix(
    cap: cv2.VideoCapture,
    model: BallTrackerNet,
    device: torch.device,
    court_ref: CourtReference,
    *,
    total_frames: int,
    sample_count: int,
    max_deviation_px: float,
    min_consensus_size: int,
) -> StableCourtEstimate:
    candidates: list[tuple[int, np.ndarray | None]] = []
    indices = sample_frame_indices(total_frames, sample_count)
    for position, frame_index in enumerate(indices, start=1):
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
        ok, frame = cap.read()
        if not ok:
            candidates.append((frame_index, None))
            continue
        matrix, mode, detected_count = detect_court_matrix(frame, model, device, court_ref)
        candidates.append((frame_index, matrix))
        print(
            f"court sample {position}/{len(indices)}: frame {frame_index} "
            f"({mode}, keypoints={detected_count}/14)"
        )

    return select_stable_court_matrix(
        candidates,
        court_ref=court_ref,
        max_deviation_px=max_deviation_px,
        min_consensus_size=min(min_consensus_size, len(indices)),
    )


def build_fixed_roi(
    matrix: np.ndarray,
    court_ref: CourtReference,
    frame_width: int,
    frame_height: int,
    *,
    top_extra_px: int,
    far_width_scale: float,
) -> tuple[np.ndarray, np.ndarray]:
    reference_boundary = np.float32(
        [
            court_ref.baseline_top[0],
            court_ref.baseline_top[1],
            court_ref.baseline_bottom[1],
            court_ref.baseline_bottom[0],
        ]
    ).reshape(-1, 1, 2)
    court_boundary = cv2.perspectiveTransform(reference_boundary, matrix).reshape(-1, 2)
    far_left, far_right = court_boundary[:2]
    far_center_x = float((far_left[0] + far_right[0]) / 2.0)
    far_half_width = float(abs(far_right[0] - far_left[0]) / 2.0)
    top_y = max(0, int(min(far_left[1], far_right[1]) - top_extra_px))

    roi = np.float32(
        [
            [np.clip(far_center_x - far_half_width * far_width_scale, 0, frame_width - 1), top_y],
            [np.clip(far_center_x + far_half_width * far_width_scale, 0, frame_width - 1), top_y],
            [frame_width - 1, frame_height - 1],
            [0, frame_height - 1],
        ]
    )
    return roi, court_boundary


def render_overlay(
    frame: np.ndarray,
    roi: np.ndarray,
    court_boundary: np.ndarray,
    *,
    frame_index: int,
    estimate: StableCourtEstimate,
    outside_brightness: float,
) -> np.ndarray:
    contour = np.round(roi).astype(np.int32).reshape(-1, 1, 2)
    boundary_contour = np.round(court_boundary).astype(np.int32).reshape(-1, 1, 2)
    mask = np.zeros(frame.shape[:2], dtype=np.uint8)
    cv2.fillPoly(mask, [contour], 255)

    output = frame.copy()
    outside = mask == 0
    output[outside] = (output[outside].astype(np.float32) * outside_brightness).astype(np.uint8)
    cv2.polylines(output, [boundary_contour], True, (255, 200, 0), 3, cv2.LINE_AA)
    cv2.polylines(output, [contour], True, (0, 210, 255), 5, cv2.LINE_AA)
    label = (
        f"Stable ROI: source frame {estimate.frame_index} | "
        f"consensus {len(estimate.consensus_frame_indices)} | frame {frame_index}"
    )
    cv2.putText(
        output,
        label,
        (28, frame.shape[0] - 28),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        (245, 245, 245),
        2,
        cv2.LINE_AA,
    )
    return output


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT_VIDEO)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--preview", type=Path)
    parser.add_argument("--court-model", type=Path, default=DEFAULT_COURT_MODEL_PATH)
    parser.add_argument("--sample-count", type=int, default=15)
    parser.add_argument("--min-consensus-size", type=int, default=5)
    parser.add_argument("--max-deviation-px", type=float, default=30.0)
    parser.add_argument("--top-extra-px", type=int, default=300)
    parser.add_argument("--far-width-scale", type=float, default=1.5)
    parser.add_argument("--outside-brightness", type=float, default=0.3)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_path = args.output or OUTPUT_DIR / f"{args.input.stem}_court_roi_overlay.mp4"
    preview_path = args.preview or OUTPUT_DIR / f"{args.input.stem}_court_roi_first_frame.jpg"
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    cap = cv2.VideoCapture(str(args.input))
    if not cap.isOpened():
        raise FileNotFoundError(f"Could not open input video: {args.input}")

    fps = float(cap.get(cv2.CAP_PROP_FPS))
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    court_ref = CourtReference()
    court_ref.build_court_reference()
    model = load_court_model(args.court_model, device)

    estimate = detect_stable_matrix(
        cap,
        model,
        device,
        court_ref,
        total_frames=total_frames,
        sample_count=args.sample_count,
        max_deviation_px=args.max_deviation_px,
        min_consensus_size=args.min_consensus_size,
    )
    roi, court_boundary = build_fixed_roi(
        estimate.matrix,
        court_ref,
        frame_width,
        frame_height,
        top_extra_px=args.top_extra_px,
        far_width_scale=args.far_width_scale,
    )
    print(
        "stable court:",
        {
            "source_frame": estimate.frame_index,
            "consensus_frames": estimate.consensus_frame_indices,
            "median_deviation_px": round(estimate.median_deviation_px, 2),
            "max_deviation_px": round(estimate.max_deviation_px, 2),
        },
    )

    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
    ok, first_frame = cap.read()
    if not ok:
        cap.release()
        raise RuntimeError("Could not read frame 0 for preview.")
    preview = render_overlay(
        first_frame,
        roi,
        court_boundary,
        frame_index=0,
        estimate=estimate,
        outside_brightness=args.outside_brightness,
    )
    preview_path.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(preview_path), preview):
        cap.release()
        raise RuntimeError(f"Could not write preview image: {preview_path}")

    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    writer = cv2.VideoWriter(
        str(output_path),
        cv2.VideoWriter_fourcc(*"mp4v"),
        fps,
        (frame_width, frame_height),
    )
    if not writer.isOpened():
        cap.release()
        raise RuntimeError(f"Could not create output video: {output_path}")

    written = 0
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            writer.write(
                render_overlay(
                    frame,
                    roi,
                    court_boundary,
                    frame_index=written,
                    estimate=estimate,
                    outside_brightness=args.outside_brightness,
                )
            )
            written += 1
    finally:
        cap.release()
        writer.release()

    if written != total_frames:
        raise RuntimeError(f"Expected {total_frames} frames, wrote {written}.")
    print("preview:", preview_path)
    print("output:", output_path)
    print("frames written:", written)


if __name__ == "__main__":
    main()
