"""TensorFlow/Keras GridTrackNet inference helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Sequence

import cv2
import numpy as np
import tensorflow as tf


def GridTrackNet(
    imgs_per_instance: int = 5,
    input_height: int = 432,
    input_width: int = 768,
) -> tf.keras.Model:
    """Build a CPU-compatible graph equivalent to the published H5 model.

    The checkpoint was trained with NCHW convolutions and default Keras BN.
    In that graph BN statistics are indexed by width.  This implementation
    uses NHWC convolutions (which TensorFlow CPU supports) and explicitly
    keeps BN on axis 2, the width axis, so the learned H5 statistics retain
    their original meaning.
    """

    inputs = tf.keras.Input(shape=(input_height, input_width, imgs_per_instance * 3))

    tensor = inputs
    conv_channels = [
        64, 64, 128, 128, 256, 256, 256, 256, 256, 512, 512, 512,
    ]
    pool_after = {1, 3, 5, 8}
    pool_index = 0

    for index, filters in enumerate(conv_channels):
        tensor = tf.keras.layers.Conv2D(
            filters,
            (3, 3),
            kernel_initializer="random_uniform",
            padding="same",
            name="conv2d" if index == 0 else f"conv2d_{index}",
        )(tensor)
        tensor = tf.keras.layers.Activation(
            "relu", name="activation" if index == 0 else f"activation_{index}"
        )(tensor)
        tensor = tf.keras.layers.BatchNormalization(
            axis=2,
            name="batch_normalization" if index == 0 else f"batch_normalization_{index}",
        )(tensor)
        if index in pool_after:
            pool_name = "max_pooling2d" if pool_index == 0 else f"max_pooling2d_{pool_index}"
            tensor = tf.keras.layers.MaxPooling2D((2, 2), strides=(2, 2), name=pool_name)(tensor)
            pool_index += 1

    tensor = tf.keras.layers.Conv2D(
        imgs_per_instance * 3,
        (3, 3),
        kernel_initializer="random_uniform",
        padding="same",
        name="conv2d_12",
    )(tensor)
    outputs = tf.keras.layers.Activation("sigmoid", name="activation_12")(tensor)
    return tf.keras.Model(inputs, outputs)


def load_gridtracknet_h5(model: tf.keras.Model, model_path: str | Path) -> tf.keras.Model:
    """Load the published H5 weights into a GridTrackNet graph."""

    model.load_weights(str(model_path))
    return model


def preprocess_grid_frames(frames: Sequence[np.ndarray]) -> np.ndarray:
    """Convert BGR OpenCV frames to normalized NHWC GridTrackNet input."""

    if len(frames) != 5:
        raise ValueError(f"GridTrackNet requires exactly 5 frames, got {len(frames)}")
    resized_rgb = [
        cv2.cvtColor(cv2.resize(frame, (768, 432)), cv2.COLOR_BGR2RGB)
        for frame in frames
    ]
    tensor = np.concatenate(resized_rgb, axis=2)
    return np.ascontiguousarray(tensor, dtype=np.float32) / 255.0


def decode_grid_output(
    output: np.ndarray,
    *,
    original_width: int,
    original_height: int,
    confidence_threshold: float = 0.5,
) -> list[dict[str, object]]:
    """Decode one NHWC ``[1, 27, 48, 15]`` output into five records."""

    if tuple(output.shape) != (1, 27, 48, 15):
        raise ValueError(f"Unexpected GridTrackNet output shape: {tuple(output.shape)}")
    grids = output[0].reshape(27, 48, 5, 3).transpose(2, 3, 0, 1)
    scale_x = original_width / 768.0
    scale_y = original_height / 432.0
    records: list[dict[str, object]] = []

    for frame_grid in grids:
        confidence_grid = frame_grid[0]
        flat_index = int(np.argmax(confidence_grid))
        row, column = divmod(flat_index, 48)
        confidence = float(confidence_grid[row, column])
        if confidence < confidence_threshold:
            records.append({
                "pixel": None,
                "confidence": None,
                "frame_peak_probability": round(confidence, 4),
                "candidates": [],
            })
            continue

        x_offset = float(frame_grid[1, row, column])
        y_offset = float(frame_grid[2, row, column])
        pixel = [
            round((column + x_offset) * 16.0 * scale_x, 2),
            round((row + y_offset) * 16.0 * scale_y, 2),
        ]
        candidate = {
            "pixel": pixel,
            "confidence": round(confidence, 4),
            "peak_confidence": round(confidence, 4),
            "mean_confidence": round(confidence, 4),
            "heat_mass": round(confidence, 4),
            "cluster_pixels": 1,
            "bbox": [
                round(column * 16.0 * scale_x, 2),
                round(row * 16.0 * scale_y, 2),
                round(16.0 * scale_x, 2),
                round(16.0 * scale_y, 2),
            ],
            "rank": 1,
        }
        records.append({
            "pixel": pixel,
            "confidence": round(confidence, 4),
            "frame_peak_probability": round(confidence, 4),
            "candidates": [candidate],
        })
    return records


def extract_gridtracknet_coords(
    input_video_path: str | Path,
    model: tf.keras.Model,
    *,
    device: str | None = None,
    max_frames: int | None = None,
    confidence_threshold: float = 0.5,
    progress_callback: Callable[[int, int], None] | None = None,
) -> tuple[list[dict[str, object]], dict[str, object]]:
    """Extract one coordinate record per source frame, including 60 FPS input."""

    del device  # TensorFlow selects the configured device itself.
    cap = cv2.VideoCapture(str(input_video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Could not open video: {input_video_path}")

    fps = float(cap.get(cv2.CAP_PROP_FPS))
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    target_frames = min(total_frames, max_frames) if max_frames is not None else total_frames
    is_60fps = 57.0 <= fps <= 63.0
    buffers: dict[int, list[tuple[int, np.ndarray]]] = {0: [], 1: []} if is_60fps else {0: []}
    records_by_index: dict[int, dict[str, object]] = {}

    def infer_buffer(frames: list[tuple[int, np.ndarray]]) -> None:
        padded = [frame for _, frame in frames]
        while len(padded) < 5:
            padded.append(padded[-1].copy())
        batch = np.expand_dims(preprocess_grid_frames(padded), axis=0)
        output = model(batch, training=False).numpy()
        decoded = decode_grid_output(
            output,
            original_width=width,
            original_height=height,
            confidence_threshold=confidence_threshold,
        )
        for (frame_index, _), item in zip(frames, decoded):
            records_by_index[frame_index] = {
                "frame_index": frame_index,
                "time_sec": round(frame_index / fps, 3) if fps > 0 else 0.0,
                "pixel": item["pixel"],
                "confidence": item["confidence"],
                "candidates": item["candidates"],
                "candidate_count": len(item["candidates"]),
                "frame_peak_probability": item["frame_peak_probability"],
                "pixel_probability_threshold": confidence_threshold,
                "coordinate_method": "gridtracknet_grid_offset",
            }

    frame_index = 0
    while frame_index < target_frames:
        ok, frame = cap.read()
        if not ok:
            break
        phase = frame_index % 2 if is_60fps else 0
        buffers[phase].append((frame_index, frame.copy()))
        if len(buffers[phase]) == 5:
            infer_buffer(buffers[phase])
            buffers[phase].clear()
        frame_index += 1
        if progress_callback is not None:
            progress_callback(frame_index, target_frames)
    cap.release()

    for frames in buffers.values():
        if frames:
            infer_buffer(frames)

    ball_coords = [records_by_index[index] for index in sorted(records_by_index)]
    return ball_coords, {
        "fps": fps,
        "video_width": width,
        "video_height": height,
        "total_frames": len(ball_coords),
        "sampling": "even_odd_30fps_phases" if is_60fps else "sequential_30fps",
    }
