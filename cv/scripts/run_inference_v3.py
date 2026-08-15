"""Deprecated compatibility entry point for the legacy pipeline."""

from __future__ import annotations

import argparse
import sys
from typing import Any


def _build_help_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="网球视频分析推理脚本")
    parser.add_argument("--input_video_path", type=str, default=None, help="输入视频路径（默认：data/input/long5.mp4）")
    parser.add_argument("--ball_model_path", type=str, default=None, help="球检测模型路径（默认：models/weights/model_best.pt）")
    parser.add_argument("--player_model_path", type=str, default=None, help="球员检测模型路径（默认：models/weights/yolov8x.pt）")
    parser.add_argument("--court_model_path", type=str, default=None, help="球场检测模型路径（默认：models/weights/model_tennis_court_det.pt）")
    parser.add_argument("--output_video_path", type=str, default=None, help="输出视频路径（默认：data/output/<input>_processed.mp4）")
    return parser


def main() -> None:
    if any(arg in {"-h", "--help"} for arg in sys.argv[1:]):
        _build_help_parser().parse_args()
        return

    from cv.legacy.run_inference import main as _legacy_main

    _legacy_main()


def __getattr__(name: str) -> Any:
    from cv.legacy import run_inference as _legacy

    return getattr(_legacy, name)


__all__ = ["main"]


if __name__ == "__main__":
    main()
