"""Robust selection of a fixed court homography from multiple frames."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable

import cv2
import numpy as np

from .reference import CourtReference


@dataclass(frozen=True)
class StableCourtEstimate:
    """The most representative homography in a multi-frame consensus set."""

    matrix: np.ndarray
    frame_index: int
    consensus_frame_indices: tuple[int, ...]
    median_deviation_px: float
    max_deviation_px: float


def sample_frame_indices(total_frames: int, sample_count: int) -> list[int]:
    if total_frames <= 0:
        raise ValueError("total_frames must be positive")
    count = min(max(2, int(sample_count)), total_frames)
    return sorted({int(round(value)) for value in np.linspace(0, total_frames - 1, count)})


def estimate_stable_court_matrix(
    capture: cv2.VideoCapture,
    detect_matrix: Callable[[np.ndarray], np.ndarray | None],
    *,
    total_frames: int,
    sample_count: int = 15,
    court_ref: CourtReference | None = None,
    max_deviation_px: float = 30.0,
    min_consensus_size: int = 5,
) -> StableCourtEstimate:
    """Sample a fixed-camera video and select one consensus court matrix."""
    candidates: list[tuple[int, np.ndarray | None]] = []
    for frame_index in sample_frame_indices(total_frames, sample_count):
        capture.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
        ok, frame = capture.read()
        candidates.append((frame_index, detect_matrix(frame) if ok else None))
    return select_stable_court_matrix(
        candidates,
        court_ref=court_ref,
        max_deviation_px=max_deviation_px,
        min_consensus_size=min(min_consensus_size, len(candidates)),
    )


def _project_reference_keypoints(
    matrix: np.ndarray,
    court_ref: CourtReference,
) -> np.ndarray:
    reference_points = np.asarray(court_ref.key_points, dtype=np.float32).reshape(-1, 1, 2)
    return cv2.perspectiveTransform(reference_points, matrix).reshape(-1, 2)


def select_stable_court_matrix(
    candidates: Iterable[tuple[int, np.ndarray | None]],
    *,
    court_ref: CourtReference | None = None,
    max_deviation_px: float = 20.0,
    min_consensus_size: int = 5,
) -> StableCourtEstimate:
    """Select the medoid of the largest mutually similar set of detections.

    Homographies are compared in image space by projecting all 14 reference
    keypoints. This avoids averaging matrix coefficients, which does not
    preserve projective geometry.
    """
    if max_deviation_px <= 0:
        raise ValueError("max_deviation_px must be positive")
    if min_consensus_size < 2:
        raise ValueError("min_consensus_size must be at least 2")

    reference = court_ref or CourtReference()
    valid = [
        (int(frame_index), np.asarray(matrix, dtype=np.float64))
        for frame_index, matrix in candidates
        if matrix is not None and np.asarray(matrix).shape == (3, 3)
    ]
    if len(valid) < min_consensus_size:
        raise RuntimeError(
            f"Only {len(valid)} valid court detections; "
            f"need at least {min_consensus_size}."
        )

    projections = np.stack(
        [_project_reference_keypoints(matrix, reference) for _, matrix in valid]
    )
    point_distances = np.linalg.norm(
        projections[:, None, :, :] - projections[None, :, :, :],
        axis=-1,
    )
    pairwise_deviation = np.median(point_distances, axis=-1)

    # Each detection proposes a consensus neighborhood. Prefer the largest
    # neighborhood, then the one with the smallest internal median deviation.
    neighborhoods = [
        np.flatnonzero(pairwise_deviation[index] <= max_deviation_px)
        for index in range(len(valid))
    ]

    def neighborhood_rank(indices: np.ndarray) -> tuple[int, float]:
        internal = pairwise_deviation[np.ix_(indices, indices)]
        return len(indices), -float(np.median(internal))

    consensus = max(neighborhoods, key=neighborhood_rank)
    if len(consensus) < min_consensus_size:
        counts = sorted((len(indices) for indices in neighborhoods), reverse=True)
        raise RuntimeError(
            "Court detections did not form a stable consensus: "
            f"best group has {counts[0]} frames, need {min_consensus_size}, "
            f"threshold={max_deviation_px:.1f}px."
        )

    internal = pairwise_deviation[np.ix_(consensus, consensus)]
    medoid_local_index = int(np.argmin(np.median(internal, axis=1)))
    medoid_index = int(consensus[medoid_local_index])
    medoid_distances = pairwise_deviation[medoid_index, consensus]

    return StableCourtEstimate(
        matrix=valid[medoid_index][1].copy(),
        frame_index=valid[medoid_index][0],
        consensus_frame_indices=tuple(valid[index][0] for index in consensus),
        median_deviation_px=float(np.median(medoid_distances)),
        max_deviation_px=float(np.max(medoid_distances)),
    )
