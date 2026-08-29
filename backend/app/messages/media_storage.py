from __future__ import annotations

from pathlib import Path
from typing import Any
import uuid

from backend.app.core.config import settings

from PIL import Image, ImageOps


IMAGE_FORMAT_MIME = {
    "JPEG": "image/jpeg",
    "PNG": "image/png",
    "WEBP": "image/webp",
    "GIF": "image/gif",
}


def storage_path(storage_key: str) -> Path:
    root = settings.message_media_storage_dir.resolve()
    path = (root / storage_key).resolve()
    path.relative_to(root)
    return path


def original_storage_key(media_id: str, mime_type: str) -> str:
    suffix = {
        "image/jpeg": "jpg", "image/png": "png", "image/webp": "webp", "image/gif": "gif",
        "video/mp4": "mp4", "video/quicktime": "mov", "video/webm": "webm",
        "video/x-matroska": "mkv", "video/3gpp": "3gp",
    }[mime_type]
    return f"{'videos' if mime_type.startswith('video/') else 'images'}/{media_id}/original.{suffix}"


def thumbnail_storage_key(media_id: str) -> str:
    return f"images/{media_id}/thumbnail.jpg"


def video_thumbnail_storage_key(media_id: str) -> str:
    return f"videos/{media_id}/thumbnail.jpg"


def _jpeg_size(data: bytes) -> tuple[int, int] | None:
    if not data.startswith(b"\xff\xd8"):
        return None
    index = 2
    while index + 9 < len(data):
        if data[index] != 0xFF:
            index += 1
            continue
        marker = data[index + 1]
        index += 2
        if marker in {0xD8, 0xD9} or 0xD0 <= marker <= 0xD7:
            continue
        if index + 2 > len(data):
            return None
        length = int.from_bytes(data[index:index + 2], "big")
        if length < 2 or index + length > len(data):
            return None
        if marker in {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}:
            return int.from_bytes(data[index + 5:index + 7], "big"), int.from_bytes(data[index + 3:index + 5], "big")
        index += length
    return None


def _image_dimensions(data: bytes, mime_type: str) -> tuple[int, int] | None:
    if mime_type == "image/png" and data.startswith(b"\x89PNG\r\n\x1a\n") and len(data) >= 24:
        return int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")
    if mime_type == "image/gif" and data[:6] in {b"GIF87a", b"GIF89a"} and len(data) >= 10:
        return int.from_bytes(data[6:8], "little"), int.from_bytes(data[8:10], "little")
    if mime_type == "image/webp" and data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        chunk = data[12:16]
        if chunk == b"VP8 " and len(data) >= 30:
            return int.from_bytes(data[26:28], "little") & 0x3FFF, int.from_bytes(data[28:30], "little") & 0x3FFF
        if chunk == b"VP8X" and len(data) >= 30:
            return 1 + int.from_bytes(data[24:27] + b"\0", "little"), 1 + int.from_bytes(data[27:30] + b"\0", "little")
    if mime_type == "image/jpeg":
        return _jpeg_size(data)
    return None


def inspect_image(path: Path) -> dict[str, Any]:
    file_size = path.stat().st_size
    if file_size <= 0 or file_size > settings.max_message_image_size_bytes:
        raise ValueError("IMAGE_FILE_SIZE_INVALID")
    data = path.read_bytes()
    if data.startswith(b"\xff\xd8"):
        mime_type = "image/jpeg"
    elif data.startswith(b"\x89PNG\r\n\x1a\n"):
        mime_type = "image/png"
    elif data[:6] in {b"GIF87a", b"GIF89a"}:
        mime_type = "image/gif"
    elif data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        mime_type = "image/webp"
    else:
        raise ValueError("IMAGE_CONTENT_INVALID")
    dimensions = _image_dimensions(data, mime_type)
    if dimensions is None:
        raise ValueError("IMAGE_DIMENSIONS_INVALID")
    width, height = dimensions
    if width <= 0 or height <= 0 or width * height > settings.max_message_image_pixels:
        raise ValueError("IMAGE_DIMENSIONS_INVALID")
    return {
        "mime_type": mime_type,
        "file_size_bytes": file_size,
        "width_px": width,
        "height_px": height,
    }


def create_thumbnail(source: Path, destination: Path) -> None:
    """Create a bounded JPEG without modifying the validated original."""
    temporary = destination.with_name(f".{destination.name}.{uuid.uuid4().hex}.part")
    try:
        with Image.open(source) as image:
            image = ImageOps.exif_transpose(image)
            image.load()
            image.thumbnail((640, 640), Image.Resampling.LANCZOS)
            if image.mode in {"RGBA", "LA", "P"}:
                rgba = image.convert("RGBA")
                background = Image.new("RGB", rgba.size, "white")
                background.paste(rgba, mask=rgba.getchannel("A"))
                image = background
            else:
                image = image.convert("RGB")
            temporary.parent.mkdir(parents=True, exist_ok=True)
            image.save(temporary, format="JPEG", quality=85, optimize=True)
        temporary.replace(destination)
    except Exception:
        if temporary.exists():
            temporary.unlink()
        raise


def delete_storage_files(storage_key: str | None, thumbnail_key: str | None) -> list[str]:
    errors: list[str] = []
    for key in (storage_key, thumbnail_key):
        if not key:
            continue
        try:
            path = storage_path(key)
        except (ValueError, OSError):
            errors.append(f"{key}:invalid_storage_key")
            continue
        if path.exists():
            try:
                path.unlink()
            except OSError as error:
                errors.append(f"{key}:{type(error).__name__}")
    if storage_key:
        parent = storage_path(storage_key).parent
        if parent.exists() and not any(parent.iterdir()):
            try:
                parent.rmdir()
            except OSError:
                pass
    return errors
