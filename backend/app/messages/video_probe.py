from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
from typing import Any

from backend.app.core.config import settings


VIDEO_MIME_EXTENSIONS = {
    "video/mp4": "mp4",
    "video/quicktime": "mov",
    "video/webm": "webm",
    "video/x-matroska": "mkv",
    "video/3gpp": "3gp",
}


def _tool(name: str, configured: str | None) -> str:
    candidate = configured or shutil.which(name)
    if not candidate:
        raise ValueError(f"{name.upper()}_NOT_INSTALLED")
    return candidate


def inspect_video(path: Path) -> dict[str, Any]:
    if not path.is_file() or path.stat().st_size <= 0:
        raise ValueError("VIDEO_FILE_SIZE_INVALID")
    ffprobe = _tool("ffprobe", settings.ffprobe_path)
    command = [ffprobe, "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)]
    try:
        result = subprocess.run(command, check=True, capture_output=True, text=True, timeout=settings.video_probe_timeout_seconds)
        data = json.loads(result.stdout)
    except (subprocess.SubprocessError, OSError, ValueError, json.JSONDecodeError):
        raise ValueError("VIDEO_CONTENT_INVALID") from None
    streams = [item for item in data.get("streams", []) if item.get("codec_type") == "video"]
    if not streams:
        raise ValueError("VIDEO_STREAM_INVALID")
    stream = streams[0]
    width, height = int(stream.get("width") or 0), int(stream.get("height") or 0)
    if width <= 0 or height <= 0 or width * height > settings.max_message_video_pixels:
        raise ValueError("VIDEO_DIMENSIONS_INVALID")
    duration = float(stream.get("duration") or data.get("format", {}).get("duration") or 0)
    duration_ms = round(duration * 1000)
    if duration_ms <= 0 or duration_ms > settings.max_message_video_duration_ms:
        raise ValueError("VIDEO_DURATION_INVALID")
    raw_format_name = (data.get("format", {}).get("format_name") or "").lower()
    format_name = "mp4" if "mp4" in raw_format_name else raw_format_name.split(",")[0]
    return {
        "mime_type": data.get("format", {}).get("format_name") and _mime_from_format(format_name),
        "file_size_bytes": path.stat().st_size,
        "width_px": width,
        "height_px": height,
        "duration_ms": duration_ms,
        "container": format_name or None,
        "codec": stream.get("codec_name"),
    }


def _mime_from_format(format_name: str) -> str | None:
    return {"mov": "video/quicktime", "mp4": "video/mp4", "webm": "video/webm", "matroska": "video/x-matroska", "3gp": "video/3gpp"}.get(format_name)


def create_video_thumbnail(source: Path, destination: Path) -> None:
    ffmpeg = _tool("ffmpeg", settings.ffmpeg_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.{source.stat().st_ino}.part")
    command = [ffmpeg, "-y", "-v", "error", "-ss", "0", "-i", str(source), "-frames:v", "1", "-vf", "scale=w=640:h=640:force_original_aspect_ratio=decrease", "-q:v", "3", "-f", "image2", str(temporary)]
    try:
        subprocess.run(command, check=True, capture_output=True, timeout=settings.video_probe_timeout_seconds)
        if not temporary.is_file() or temporary.stat().st_size <= 0:
            raise ValueError("VIDEO_THUMBNAIL_EMPTY")
        temporary.replace(destination)
    except Exception:
        if temporary.exists():
            temporary.unlink()
        raise
