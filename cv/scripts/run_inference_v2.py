"""Stable public entry point for the v2 inference pipeline."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from cv.config import (
    DEFAULT_BALL_MODEL_PATH as BALL_MODEL_PATH,
    DEFAULT_COURT_MODEL_PATH as COURT_MODEL_PATH,
    DEFAULT_PLAYER_MODEL_PATH as PLAYER_MODEL_PATH,
)


DEFAULT_BALL_MODEL_PATH = str(BALL_MODEL_PATH)
DEFAULT_PLAYER_MODEL_PATH = str(PLAYER_MODEL_PATH)
DEFAULT_COURT_MODEL_PATH = str(COURT_MODEL_PATH)


def run_inference_v2(*args: Any, **kwargs: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    from cv.pipeline.inference import run_inference_v2 as _run_inference_v2

    return _run_inference_v2(*args, **kwargs)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the end-to-end tennis analysis v2 pipeline.")
    parser.add_argument("--input_video_path", type=str, required=True, help="Path to the source tennis match video.")
    parser.add_argument("--ball_model_path", type=str, default=DEFAULT_BALL_MODEL_PATH)
    parser.add_argument("--player_model_path", type=str, default=DEFAULT_PLAYER_MODEL_PATH)
    parser.add_argument("--court_model_path", type=str, default=DEFAULT_COURT_MODEL_PATH)
    parser.add_argument("--output_dir", type=str, default=None, help="Directory for output JSON files.")
    parser.add_argument("--persist_intermediate_json", action="store_true", help="Also save intermediate JSON payloads.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    shots_payload, points_payload = run_inference_v2(
        input_video_path=Path(args.input_video_path),
        ball_model_path=args.ball_model_path,
        player_model_path=args.player_model_path,
        court_model_path=args.court_model_path,
        output_dir=args.output_dir,
        persist_intermediate_json=args.persist_intermediate_json,
        persist_final_json=True,
    )
    print(json.dumps({"shots": shots_payload["metadata"], "points": points_payload["metadata"]}, ensure_ascii=False, indent=2))

__all__ = [
    "DEFAULT_BALL_MODEL_PATH",
    "DEFAULT_COURT_MODEL_PATH",
    "DEFAULT_PLAYER_MODEL_PATH",
    "run_inference_v2",
]

if __name__ == "__main__":
    main()
