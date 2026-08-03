from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
import shutil
import sqlite3
import struct
import subprocess
from typing import Any
import zlib

from backend.app.core.config import settings


THUMBNAIL_FOLDER = "thumbnails"
THUMBNAIL_WIDTH = 640
THUMBNAIL_HEIGHT = 360


def _storage_root() -> Path:
    return settings.video_storage_dir.resolve()


def _public_prefix() -> str:
    return settings.public_video_path_prefix.rstrip("/")


def _public_path(*parts: str) -> str:
    safe_parts = [
        part
        for raw_part in parts
        for part in raw_part.replace("\\", "/").split("/")
        if part and part not in {".", ".."}
    ]
    return f"{_public_prefix()}/{'/'.join(safe_parts)}"


def _local_path_for_public_path(public_path: str) -> Path | None:
    if public_path.startswith(("http://", "https://")):
        return None
    prefix = _public_prefix() + "/"
    if not public_path.startswith(prefix):
        return None

    relative_path = public_path[len(prefix) :]
    if not relative_path or ".." in Path(relative_path).parts:
        return None

    local_path = (_storage_root() / relative_path).resolve()
    try:
        local_path.relative_to(_storage_root())
    except ValueError:
        return None
    return local_path


def public_storage_file_exists(public_path: str | None) -> bool:
    if not public_path:
        return False
    local_path = _local_path_for_public_path(public_path)
    if local_path is None:
        return True
    return local_path.is_file() and local_path.stat().st_size > 0


def delete_public_storage_file_if_present(public_path: str | None) -> None:
    if not public_path:
        return
    local_path = _local_path_for_public_path(public_path)
    if local_path is not None and local_path.exists() and local_path.is_file():
        local_path.unlink()


def _candidate_thumbnail_paths(video_id: str) -> tuple[str, str]:
    return (
        _public_path(THUMBNAIL_FOLDER, f"{video_id}.jpg"),
        _public_path(THUMBNAIL_FOLDER, f"{video_id}.png"),
    )


def _png_chunk(chunk_type: bytes, data: bytes) -> bytes:
    return (
        struct.pack(">I", len(data))
        + chunk_type
        + data
        + struct.pack(">I", zlib.crc32(chunk_type + data) & 0xFFFFFFFF)
    )


def _placeholder_png_bytes() -> bytes:
    rows: list[bytes] = []
    center_x = THUMBNAIL_WIDTH // 2
    center_y = THUMBNAIL_HEIGHT // 2
    service_y = THUMBNAIL_HEIGHT // 3
    for y in range(THUMBNAIL_HEIGHT):
        row = bytearray([0])
        for x in range(THUMBNAIL_WIDTH):
            line = (
                abs(x - center_x) <= 2
                or abs(y - center_y) <= 2
                or abs(y - service_y) <= 2
                or abs(y - (THUMBNAIL_HEIGHT - service_y)) <= 2
                or x <= 5
                or y <= 5
                or x >= THUMBNAIL_WIDTH - 6
                or y >= THUMBNAIL_HEIGHT - 6
            )
            if line:
                row.extend((230, 238, 232))
            else:
                shade = 12 if ((x // 32) + (y // 32)) % 2 == 0 else 0
                row.extend((45 + shade, 104 + shade, 82 + shade))
        rows.append(bytes(row))

    raw = b"".join(rows)
    header = struct.pack(">IIBBBBB", THUMBNAIL_WIDTH, THUMBNAIL_HEIGHT, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", header)
        + _png_chunk(b"IDAT", zlib.compress(raw, 9))
        + _png_chunk(b"IEND", b"")
    )


def _write_placeholder_thumbnail(video_id: str) -> str:
    _, public_png_path = _candidate_thumbnail_paths(video_id)
    local_png_path = _local_path_for_public_path(public_png_path)
    if local_png_path is None:
        return public_png_path
    local_png_path.parent.mkdir(parents=True, exist_ok=True)
    if not local_png_path.exists() or local_png_path.stat().st_size == 0:
        local_png_path.write_bytes(_placeholder_png_bytes())
    return public_png_path


def _extract_video_frame(video_path: str, output_public_path: str) -> bool:
    ffmpeg_path = shutil.which("ffmpeg")
    local_video_path = _local_path_for_public_path(video_path)
    local_output_path = _local_path_for_public_path(output_public_path)
    if ffmpeg_path is None or local_video_path is None or local_output_path is None:
        return False
    if not local_video_path.is_file() or local_video_path.stat().st_size == 0:
        return False

    local_output_path.parent.mkdir(parents=True, exist_ok=True)
    for seek in ("00:00:00.500", "00:00:00"):
        if local_output_path.exists():
            local_output_path.unlink()
        try:
            result = subprocess.run(
                [
                    ffmpeg_path,
                    "-y",
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-ss",
                    seek,
                    "-i",
                    str(local_video_path),
                    "-frames:v",
                    "1",
                    "-vf",
                    "scale=640:-2",
                    "-q:v",
                    "3",
                    str(local_output_path),
                ],
                capture_output=True,
                check=False,
                timeout=15,
            )
        except (OSError, subprocess.SubprocessError):
            return False
        if result.returncode == 0 and local_output_path.is_file() and local_output_path.stat().st_size > 0:
            return True
    return False


def ensure_video_thumbnail_path(video: Mapping[str, Any]) -> str | None:
    current_thumbnail = video.get("thumbnail_path")
    if isinstance(current_thumbnail, str) and public_storage_file_exists(current_thumbnail):
        return current_thumbnail

    video_id = video.get("video_id")
    if not isinstance(video_id, str) or not video_id:
        return current_thumbnail if isinstance(current_thumbnail, str) else None

    public_jpg_path, public_png_path = _candidate_thumbnail_paths(video_id)
    if public_storage_file_exists(public_jpg_path):
        return public_jpg_path
    if public_storage_file_exists(public_png_path):
        return public_png_path

    if video.get("upload_status") != "uploaded":
        return current_thumbnail if isinstance(current_thumbnail, str) else None

    video_path = video.get("video_path")
    if isinstance(video_path, str) and _extract_video_frame(video_path, public_jpg_path):
        return public_jpg_path

    return _write_placeholder_thumbnail(video_id)


def ensure_video_thumbnail_records(
    connection: sqlite3.Connection,
    rows: Sequence[sqlite3.Row],
    *,
    commit: bool = False,
    persist_to_database: bool = False,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    changed = False
    for row in rows:
        record = {key: row[key] for key in row.keys()}
        thumbnail_path = ensure_video_thumbnail_path(record)
        if thumbnail_path and thumbnail_path != record.get("thumbnail_path"):
            if persist_to_database:
                connection.execute(
                    """
                    UPDATE videos
                    SET thumbnail_path = ?
                    WHERE video_id = ?;
                    """,
                    (thumbnail_path, record["video_id"]),
                )
                changed = True
            record["thumbnail_path"] = thumbnail_path
        records.append(record)

    if changed and commit:
        connection.commit()
    return records
