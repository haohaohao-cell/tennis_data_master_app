"""
单文件版的网球视频分段脚本。

职责：
1. 若缓存中间数据存在，直接读取缓存。
2. 若缓存不存在，就在本文件内完成逐帧推理并生成完整缓存。
3. 使用与 run_inference_v2.py 一致的分段逻辑进行 point 切分。
4. 用 ffmpeg 将原视频切到输出目录。

注意：
- 本文件不再依赖“子进程调用 run_inference_v2.py”来生成缓存。
- 为了和现有主流程保持一致，缓存生成部分复用了 run_inference_v2.py 中的核心实现。
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from cv.config import (
    DEFAULT_COURT_MODEL_PATH as COURT_MODEL_PATH,
    DEFAULT_GRIDTRACKNET_MODEL_PATH as BALL_MODEL_PATH,
    DEFAULT_PLAYER_MODEL_PATH as PLAYER_MODEL_PATH,
)
from cv.segmentation.points import (
    CONSECUTIVE_NO_COURT_END_FRAMES,
    MIN_VISIBLE_COURT_KEYPOINTS,
    SegmentationConfig,
    detect_segments_with_court_visibility,
    filter_segments,
    format_seconds,
    load_json,
    summarize_segments_with_court_visibility,
)


DEFAULT_BALL_MODEL_PATH = str(BALL_MODEL_PATH)
DEFAULT_PLAYER_MODEL_PATH = str(PLAYER_MODEL_PATH)
DEFAULT_COURT_MODEL_PATH = str(COURT_MODEL_PATH)
EXPECTED_CACHE_FILES = (
    "shots_v2.json",
    "points_v2.json",
    "match_tactics_v2.json",
    "match_frames_v2.json",
    "match_frames_v2_imputed.json",
    "match_frames_v2_imputation_report.json",
    "points_heuristic_v2_index_v2.json",
    "shots_v2_intermediate.json",
)


def run_local_inference_cache_generation(
    input_video_path: str | Path,
    *,
    ball_model_path: str = DEFAULT_BALL_MODEL_PATH,
    player_model_path: str = DEFAULT_PLAYER_MODEL_PATH,
    court_model_path: str = DEFAULT_COURT_MODEL_PATH,
    output_dir: str | Path,
    segmentation_config: SegmentationConfig | None = None,
) -> None:
    """Generate split cache through the canonical inference pipeline."""
    from cv.pipeline.inference import run_inference_v2

    run_inference_v2(
        input_video_path=input_video_path,
        ball_model_path=ball_model_path,
        player_model_path=player_model_path,
        court_model_path=court_model_path,
        output_dir=output_dir,
        segmentation_config=segmentation_config,
        persist_intermediate_json=True,
        persist_final_json=True,
    )


def run_ffmpeg(input_video: Path, output_video: Path, start_time: float, duration: float) -> None:
    command = [
        "ffmpeg",
        "-y",
        "-ss",
        f"{start_time:.6f}",
        "-i",
        str(input_video),
        "-t",
        f"{duration:.6f}",
        "-c:v",
        "libx264",
        "-preset",
        "fast",
        "-crf",
        "18",
        "-c:a",
        "aac",
        "-movflags",
        "+faststart",
        str(output_video),
    ]

    completed = subprocess.run(command, capture_output=True, text=True)
    if completed.returncode != 0:
        raise RuntimeError(
            f"ffmpeg failed for {output_video.name}\n"
            f"stdout:\n{completed.stdout}\n"
            f"stderr:\n{completed.stderr}"
        )


def write_summary(
    path: Path,
    source_video: Path,
    frames_path: Path,
    fps: float,
    segments: list[dict[str, Any]],
    config: SegmentationConfig,
) -> None:
    payload = {
        "source_video": source_video.name,
        "frames_path": str(frames_path),
        "fps": fps,
        "config": {
            "ball_break_sec": config.ball_break_sec,
            "ball_break_sec_with_players": config.ball_break_sec_with_players,
            "players_break_sec": config.players_break_sec,
            "court_break_sec": config.court_break_sec,
            "min_segment_sec": config.min_segment_sec,
            "start_ball_ratio": config.start_ball_ratio,
            "start_players_ratio": config.start_players_ratio,
            "start_court_ratio": config.start_court_ratio,
            "min_ball_frames": config.min_ball_frames,
            "min_player_frames": config.min_player_frames,
            "min_court_frames": config.min_court_frames,
            "no_ball_support_ratio_for_extension": config.no_ball_support_ratio_for_extension,
            "min_both_players_ratio": config.min_both_players_ratio,
            "min_both_players_total_sec": config.min_both_players_total_sec,
            "court_visible_min_keypoints": MIN_VISIBLE_COURT_KEYPOINTS,
            "court_gap_consecutive_frames": CONSECUTIVE_NO_COURT_END_FRAMES,
        },
        "segment_count": len(segments),
        "segments": segments,
    }
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)


def cache_manifest_path(cache_dir: Path) -> Path:
    return cache_dir / "split_cache_manifest.json"


def default_cache_dir(source_video: Path) -> Path:
    return source_video.parent / f"{source_video.stem}_split_cache"


def cached_frames_path(cache_dir: Path) -> Path:
    return cache_dir / "match_frames_v2.json"


def expected_cache_paths(cache_dir: Path) -> list[Path]:
    return [cache_dir / filename for filename in EXPECTED_CACHE_FILES]


def missing_cache_files(cache_dir: Path) -> list[Path]:
    return [path for path in expected_cache_paths(cache_dir) if not path.exists()]


def write_cache_manifest(cache_dir: Path, source_video: Path) -> None:
    payload = {
        "source_video": str(source_video),
        "cache_dir": str(cache_dir),
        "required_files": list(EXPECTED_CACHE_FILES),
    }
    with cache_manifest_path(cache_dir).open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)


def generate_cached_frames(
    source_video: Path,
    cache_dir: Path,
    *,
    ball_model_path: str,
    player_model_path: str,
    court_model_path: str,
) -> Path:
    cache_dir.mkdir(parents=True, exist_ok=True)
    print("未找到缓存帧数据，开始在 split_video_by_point.py 内部生成完整缓存...")

    run_local_inference_cache_generation(
        input_video_path=source_video,
        ball_model_path=ball_model_path,
        player_model_path=player_model_path,
        court_model_path=court_model_path,
        output_dir=cache_dir,
    )

    frames_path = cached_frames_path(cache_dir)
    missing_files = missing_cache_files(cache_dir)
    if missing_files:
        missing_names = ", ".join(path.name for path in missing_files)
        raise FileNotFoundError(f"缓存生成不完整，缺少这些文件: {missing_names}")
    if not frames_path.exists():
        raise FileNotFoundError(f"缓存生成完成，但未找到帧数据文件: {frames_path}")

    write_cache_manifest(cache_dir, source_video)
    return frames_path


def resolve_frames_path(
    source_video: Path,
    frames_path_arg: Path | None,
    cache_dir: Path,
    *,
    ball_model_path: str,
    player_model_path: str,
    court_model_path: str,
) -> Path:
    if frames_path_arg is not None:
        frames_path = frames_path_arg.resolve()
        if not frames_path.exists():
            raise FileNotFoundError(f"指定的帧数据文件不存在: {frames_path}")
        return frames_path

    frames_path = cached_frames_path(cache_dir)
    missing_files = missing_cache_files(cache_dir)
    if not missing_files:
        print(f"检测到完整缓存，直接复用: {frames_path}")
        return frames_path

    if frames_path.exists():
        missing_names = ", ".join(path.name for path in missing_files)
        print(f"检测到缓存目录，但缓存不完整，缺少: {missing_names}")

    return generate_cached_frames(
        source_video,
        cache_dir,
        ball_model_path=ball_model_path,
        player_model_path=player_model_path,
        court_model_path=court_model_path,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="单文件版 point 分段与缓存脚本：缺缓存时自动在本文件内完成逐帧推理并保存完整中间数据。",
    )
    parser.add_argument("--source-video", type=Path, required=True, help="待切分的源视频路径。")
    parser.add_argument("--frames-path", type=Path, default=None, help="显式指定帧数据 JSON；传了就不走缓存生成。")
    parser.add_argument("--cache-dir", type=Path, default=None, help="缓存目录，默认 <视频名>_split_cache。")
    parser.add_argument("--output-dir", type=Path, default=None, help="切分后 point 视频输出目录。")
    parser.add_argument("--summary-path", type=Path, default=None, help="分段摘要 JSON 输出路径。")
    parser.add_argument("--ball-model-path", type=str, default=DEFAULT_BALL_MODEL_PATH)
    parser.add_argument("--player-model-path", type=str, default=DEFAULT_PLAYER_MODEL_PATH)
    parser.add_argument("--court-model-path", type=str, default=DEFAULT_COURT_MODEL_PATH)
    parser.add_argument("--skip-cutting", action="store_true", help="只做缓存和分段摘要，不执行 ffmpeg 切片。")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    source_video = args.source_video.resolve()
    config = SegmentationConfig()
    cache_dir = (args.cache_dir or default_cache_dir(source_video)).resolve()

    if not source_video.exists():
        raise FileNotFoundError(f"找不到源视频: {source_video}")
    if not args.skip_cutting and shutil.which("ffmpeg") is None:
        raise EnvironmentError("系统 PATH 中未找到 ffmpeg。")

    frames_path = resolve_frames_path(
        source_video,
        args.frames_path,
        cache_dir,
        ball_model_path=args.ball_model_path,
        player_model_path=args.player_model_path,
        court_model_path=args.court_model_path,
    )

    output_dir = (args.output_dir or (source_video.parent / f"{source_video.stem}_{config.output_dir_name}")).resolve()
    summary_path = (args.summary_path or (source_video.parent / f"{source_video.stem}_{config.summary_name}")).resolve()

    frames_data = load_json(frames_path)
    metadata = frames_data.get("metadata") or {}
    frames = frames_data.get("frames") or []
    fps = metadata.get("fps")

    if not frames:
        raise RuntimeError(f"帧数据为空: {frames_path.name}")
    if not fps or fps <= 0:
        raise RuntimeError(f"帧数据里的 fps 无效: {frames_path.name}")

    output_dir.mkdir(parents=True, exist_ok=True)
    summary_path.parent.mkdir(parents=True, exist_ok=True)

    raw_segments = detect_segments_with_court_visibility(frames, fps, config)
    summarized_segments = [
        summarize_segments_with_court_visibility(frames, fps, segment)
        for segment in raw_segments
    ]
    final_segments = filter_segments(summarized_segments, fps, config)

    print(f"Source video: {source_video}")
    print(f"Frame data:   {frames_path}")
    print(f"Cache dir:    {cache_dir}")
    print(f"Output dir:   {output_dir}")
    print(f"FPS:          {fps}")
    print(f"Raw segments: {len(raw_segments)}")
    print(f"Final cuts:   {len(final_segments)}")

    for segment in final_segments:
        segment_id = segment["segment_id"]
        start_frame = segment["start_frame"]
        end_frame = segment["end_frame"]
        start_time = start_frame / fps
        duration = (end_frame - start_frame + 1) / fps
        end_time = (end_frame + 1) / fps

        output_name = (
            f"point_{segment_id:03d}_"
            f"f{start_frame:06d}-{end_frame:06d}_"
            f"{start_time:08.3f}s-{end_time:08.3f}s.mp4"
        )
        output_path = output_dir / output_name

        print(
            f"[{segment_id:03d}/{len(final_segments):03d}] "
            f"frames {start_frame}-{end_frame} "
            f"({format_seconds(start_time)} -> {format_seconds(end_time)}) "
            f"reasons={','.join(segment['end_reasons'])} "
            f"ball_ratio={segment['tracknet_ratio']:.3f} "
            f"both_ratio={segment['both_players_ratio']:.3f} "
            f"court_ratio={segment['court_signal_ratio']:.3f}"
        )

        if not args.skip_cutting:
            run_ffmpeg(source_video, output_path, start_time, duration)

    write_summary(summary_path, source_video, frames_path, fps, final_segments, config)
    print(f"Summary:      {summary_path}")
    if args.skip_cutting:
        print("Done (skip cutting).")
    else:
        print("Done.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1)
