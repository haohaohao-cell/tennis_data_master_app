from __future__ import annotations

from datetime import timedelta
import hashlib
import os
from pathlib import Path
import uuid
from typing import Any

from fastapi import UploadFile, status
from fastapi.responses import FileResponse

from backend.app.auth.service import raise_api_error
from backend.app.core.config import settings
from backend.app.core.database import advisory_lock, get_connection, transaction
from backend.app.core.time import utc_now, utc_now_iso
from backend.app.messages.media_storage import (
    create_thumbnail,
    delete_storage_files,
    inspect_image,
    original_storage_key,
    storage_path,
    thumbnail_storage_key,
    video_thumbnail_storage_key,
)
from backend.app.messages.video_probe import create_video_thumbnail, inspect_video
from backend.app.messages.schemas import (
    MessageMediaRecord,
    MessageMediaResponse,
    MessageMediaUploadIntentCreate,
    MessageMediaUploadIntentResponse,
)


def _row_dict(row: Any) -> dict[str, Any]:
    return {key: row[key] for key in row.keys()}


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _ensure_active_user(connection, user_id: str) -> None:
    row = connection.execute(
        "SELECT 1 FROM users WHERE user_id = ? AND status = 'active' AND deleted_at IS NULL LIMIT 1;",
        (user_id,),
    ).fetchone()
    if row is None:
        raise_api_error(status.HTTP_404_NOT_FOUND, "USER_NOT_FOUND", "User was not found.")


def _select_media(connection, media_id: str, owner_user_id: str | None = None):
    query = "SELECT * FROM chat_message_media WHERE media_id = ?"
    params: list[object] = [media_id]
    if owner_user_id is not None:
        query += " AND owner_user_id = ?"
        params.append(owner_user_id)
    query += " LIMIT 1;"
    row = connection.execute(query, tuple(params)).fetchone()
    if row is None:
        raise_api_error(status.HTTP_404_NOT_FOUND, "MESSAGE_MEDIA_NOT_FOUND", "Message media was not found.")
    return row


def _is_expired(row: Any) -> bool:
    return row["expires_at"] <= utc_now_iso() and row["upload_status"] not in {"attached", "deleted"}


def _expire_if_needed(connection, row: Any) -> Any:
    if not _is_expired(row):
        return row
    connection.execute(
        "UPDATE chat_message_media SET upload_status = 'expired', failure_code = 'MEDIA_EXPIRED' WHERE media_id = ? AND upload_status NOT IN ('attached', 'deleted');",
        (row["media_id"],),
    )
    return connection.execute("SELECT * FROM chat_message_media WHERE media_id = ? LIMIT 1;", (row["media_id"],)).fetchone()


def _record(row: Any, *, include_urls: bool = True) -> MessageMediaRecord:
    media_id = row["media_id"]
    state = row["upload_status"]
    thumbnail_available = False
    if row["thumbnail_storage_key"]:
        try:
            thumbnail_available = storage_path(row["thumbnail_storage_key"]).is_file()
        except (OSError, ValueError):
            thumbnail_available = False
    return MessageMediaRecord(
        **{
            **_row_dict(row),
            "media_url": f"/api/v1/messages/media/{media_id}/content?variant=original" if include_urls and state in {"uploaded", "attached"} else None,
            "thumbnail_url": f"/api/v1/messages/media/{media_id}/content?variant=thumbnail" if include_urls and state in {"uploaded", "attached"} and thumbnail_available else None,
        }
    )


def create_upload_intent(user_id: str, payload: MessageMediaUploadIntentCreate) -> MessageMediaUploadIntentResponse:
    now = utc_now()
    expires_at = (now + timedelta(hours=settings.message_media_ttl_hours)).isoformat(timespec="seconds").replace("+00:00", "Z")
    with transaction(immediate=True, lock_key=f"media-upload:{user_id}:{payload.client_upload_id}") as connection:
        _ensure_active_user(connection, user_id)
        existing = connection.execute(
            "SELECT * FROM chat_message_media WHERE owner_user_id = ? AND client_upload_id = ? LIMIT 1;",
            (user_id, payload.client_upload_id),
        ).fetchone()
        if existing is not None:
            if (
                existing["media_type"] != payload.media_type
                or existing["mime_type"] != payload.mime_type
                or existing["file_size_bytes"] != payload.file_size_bytes
                or existing["width_px"] != payload.width_px
                or existing["height_px"] != payload.height_px
                or existing["duration_ms"] != payload.duration_ms
                or existing["expected_checksum_sha256"] != payload.expected_checksum_sha256
            ):
                raise_api_error(status.HTTP_409_CONFLICT, "CLIENT_UPLOAD_ID_CONFLICT", "client_upload_id is already bound to different media.")
            existing = _expire_if_needed(connection, existing)
            record = _record(existing)
            return MessageMediaUploadIntentResponse(
                media=record,
                upload_url=f"/api/v1/messages/media/{record.media_id}/file",
                complete_url=f"/api/v1/messages/media/{record.media_id}/complete",
            )
        media_id = str(uuid.uuid4())
        storage_key = original_storage_key(media_id, payload.mime_type)
        connection.execute(
            """
            INSERT INTO chat_message_media (
                media_id, owner_user_id, media_type, upload_status, storage_key,
                mime_type, file_size_bytes, width_px, height_px, duration_ms,
                expected_checksum_sha256, client_upload_id, expires_at
            ) VALUES (?, ?, ?, 'created', ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (media_id, user_id, payload.media_type, storage_key, payload.mime_type, payload.file_size_bytes, payload.width_px, payload.height_px, payload.duration_ms, payload.expected_checksum_sha256.lower() if payload.expected_checksum_sha256 else None, payload.client_upload_id, expires_at),
        )
        row = connection.execute("SELECT * FROM chat_message_media WHERE media_id = ? LIMIT 1;", (media_id,)).fetchone()
    record = _record(row)
    return MessageMediaUploadIntentResponse(
        media=record,
        upload_url=f"/api/v1/messages/media/{media_id}/file",
        complete_url=f"/api/v1/messages/media/{media_id}/complete",
    )


async def upload_media_file(user_id: str, media_id: str, file: UploadFile) -> MessageMediaResponse:
    with transaction(immediate=True, lock_key=f"media:{media_id}") as connection:
        row = _expire_if_needed(connection, _select_media(connection, media_id, user_id))
        if row["upload_status"] == "expired":
            connection.commit()
            raise_api_error(status.HTTP_409_CONFLICT, "MESSAGE_MEDIA_EXPIRED", "The media upload intent has expired.")
        if row["upload_status"] in {"uploaded", "attached"}:
            return MessageMediaResponse(media=_record(row))
        if row["upload_status"] == "uploading":
            raise_api_error(status.HTTP_409_CONFLICT, "MESSAGE_MEDIA_UPLOAD_IN_PROGRESS", "The media upload is already in progress.")
        if row["upload_status"] == "deleted":
            raise_api_error(status.HTTP_409_CONFLICT, "MESSAGE_MEDIA_DELETED", "The media upload is no longer available.")
        connection.execute("UPDATE chat_message_media SET upload_status = 'uploading', failure_code = NULL WHERE media_id = ?;", (media_id,))
        storage_key = row["storage_key"]
    destination = storage_path(storage_key)
    partial = destination.with_name(f"{destination.name}.{uuid.uuid4().hex}.part")
    destination.parent.mkdir(parents=True, exist_ok=True)
    bytes_written = 0
    digest = hashlib.sha256()
    try:
        with partial.open("wb") as output:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                bytes_written += len(chunk)
                digest.update(chunk)
                max_size = settings.max_message_video_size_bytes if row["media_type"] == "video" else settings.max_message_image_size_bytes
                if bytes_written > max_size:
                    raise ValueError("VIDEO_FILE_TOO_LARGE" if row["media_type"] == "video" else "IMAGE_FILE_TOO_LARGE")
                output.write(chunk)
        info = inspect_video(partial) if row["media_type"] == "video" else inspect_image(partial)
        if (info["mime_type"] != row["mime_type"] or info["file_size_bytes"] != row["file_size_bytes"] or info["width_px"] != row["width_px"] or info["height_px"] != row["height_px"] or (row["media_type"] == "video" and info["duration_ms"] != row["duration_ms"])):
            raise ValueError("VIDEO_METADATA_MISMATCH" if row["media_type"] == "video" else "IMAGE_METADATA_MISMATCH")
        if row["expected_checksum_sha256"] and digest.hexdigest() != row["expected_checksum_sha256"].lower():
            raise ValueError("VIDEO_CHECKSUM_MISMATCH" if row["media_type"] == "video" else "IMAGE_CHECKSUM_MISMATCH")
        with transaction(immediate=True, lock_key=f"media:{media_id}") as connection:
            current = _select_media(connection, media_id, user_id)
            if current["upload_status"] != "uploading":
                raise ValueError("MESSAGE_MEDIA_NOT_READY")
            partial.replace(destination)
    except Exception as error:
        if partial.exists():
            partial.unlink()
        if destination.exists():
            destination.unlink()
        code = str(error) if isinstance(error, ValueError) else ("VIDEO_UPLOAD_FAILED" if row["media_type"] == "video" else "IMAGE_UPLOAD_FAILED")
        with transaction(immediate=True, lock_key=f"media:{media_id}") as connection:
            connection.execute("UPDATE chat_message_media SET upload_status = 'failed', failure_code = ? WHERE media_id = ? AND owner_user_id = ? AND upload_status = 'uploading';", (code[:80], media_id, user_id))
        raise_api_error(status.HTTP_400_BAD_REQUEST, code[:80], "The media upload could not be validated.")
    finally:
        await file.close()
    with transaction() as connection:
        row = _select_media(connection, media_id, user_id)
    return MessageMediaResponse(media=_record(row))


def complete_upload(user_id: str, media_id: str) -> MessageMediaResponse:
    with transaction(immediate=True, lock_key=f"media:{media_id}") as connection:
        row = _expire_if_needed(connection, _select_media(connection, media_id, user_id))
        if row["upload_status"] == "attached":
            return MessageMediaResponse(media=_record(row))
        if row["upload_status"] == "uploaded":
            return MessageMediaResponse(media=_record(row))
        if row["upload_status"] == "expired":
            raise_api_error(status.HTTP_409_CONFLICT, "MESSAGE_MEDIA_EXPIRED", "The media upload intent has expired.")
        if row["upload_status"] != "uploading":
            raise_api_error(status.HTTP_409_CONFLICT, "MESSAGE_MEDIA_NOT_READY", "The image file has not been uploaded.")
        source = storage_path(row["storage_key"])
        if not source.is_file():
            raise_api_error(status.HTTP_409_CONFLICT, "MESSAGE_MEDIA_NOT_READY", "The image file has not finished uploading.")
        try:
            info = inspect_video(source) if row["media_type"] == "video" else inspect_image(source)
            if (info["mime_type"] != row["mime_type"] or info["file_size_bytes"] != row["file_size_bytes"] or info["width_px"] != row["width_px"] or info["height_px"] != row["height_px"] or (row["media_type"] == "video" and info["duration_ms"] != row["duration_ms"])):
                raise ValueError("VIDEO_METADATA_MISMATCH" if row["media_type"] == "video" else "IMAGE_METADATA_MISMATCH")
            thumb_key = video_thumbnail_storage_key(media_id) if row["media_type"] == "video" else thumbnail_storage_key(media_id)
            thumbnail_status = "generated"
            thumbnail_failure_code = None
            try:
                (create_video_thumbnail if row["media_type"] == "video" else create_thumbnail)(source, storage_path(thumb_key))
            except Exception as error:
                thumbnail_status = "failed"
                thumbnail_failure_code = f"THUMBNAIL_{type(error).__name__.upper()}"[:80]
                thumb_key = None
        except ValueError as error:
            code = str(error)[:80]
            connection.execute("UPDATE chat_message_media SET upload_status = 'failed', failure_code = ? WHERE media_id = ?;", (code, media_id))
            connection.commit()
            raise_api_error(status.HTTP_400_BAD_REQUEST, code, "The uploaded media could not be completed.")
        now = utc_now_iso()
        connection.execute(
            "UPDATE chat_message_media SET upload_status = 'uploaded', thumbnail_storage_key = ?, thumbnail_status = ?, thumbnail_failure_code = ?, uploaded_at = ?, checksum_sha256 = COALESCE(checksum_sha256, ?), container = ?, codec = ?, duration_ms = COALESCE(?, duration_ms), failure_code = NULL WHERE media_id = ?;",
            (thumb_key, thumbnail_status, thumbnail_failure_code, now, _sha256_file(source), info.get("container"), info.get("codec"), info.get("duration_ms"), media_id),
        )
        row = connection.execute("SELECT * FROM chat_message_media WHERE media_id = ? LIMIT 1;", (media_id,)).fetchone()
    return MessageMediaResponse(media=_record(row))


def cancel_upload(user_id: str, media_id: str) -> MessageMediaResponse:
    with transaction(immediate=True, lock_key=f"media:{media_id}") as connection:
        row = _select_media(connection, media_id, user_id)
        if row["upload_status"] == "attached":
            raise_api_error(status.HTTP_409_CONFLICT, "MESSAGE_MEDIA_ATTACHED", "Attached media cannot be canceled.")
        if row["upload_status"] == "deleted" and row["storage_deleted_at"]:
            return MessageMediaResponse(media=_record(row, include_urls=False))
        connection.execute("UPDATE chat_message_media SET upload_status = 'deleted', deleted_at = COALESCE(deleted_at, ?), failure_code = 'MEDIA_CANCELED' WHERE media_id = ?;", (utc_now_iso(), media_id))
        row = connection.execute("SELECT * FROM chat_message_media WHERE media_id = ? LIMIT 1;", (media_id,)).fetchone()
    errors = delete_storage_files(row["storage_key"], row["thumbnail_storage_key"])
    with transaction() as connection:
        connection.execute(
            "UPDATE chat_message_media SET storage_deleted_at = ?, last_cleanup_error = ? WHERE media_id = ? AND upload_status = 'deleted';",
            (utc_now_iso() if not errors else None, "; ".join(errors)[:255] if errors else None, media_id),
        )
        row = connection.execute("SELECT * FROM chat_message_media WHERE media_id = ? LIMIT 1;", (media_id,)).fetchone()
    return MessageMediaResponse(media=_record(row, include_urls=False))


def _authorized_media_row(connection, user_id: str, media_id: str):
    row = _select_media(connection, media_id)
    if row["message_id"] is None:
        if row["owner_user_id"] != user_id:
            raise_api_error(status.HTTP_404_NOT_FOUND, "MESSAGE_MEDIA_NOT_FOUND", "Message media was not found.")
    else:
        member = connection.execute(
            """
            SELECT 1 FROM chat_conversation_members cm
            JOIN chat_messages m ON m.conversation_id = cm.conversation_id
            WHERE m.message_id = ? AND cm.user_id = ? AND cm.status = 'active' AND cm.deleted_at IS NULL
              AND m.status = 'sent' AND m.deleted_at IS NULL LIMIT 1;
            """,
            (row["message_id"], user_id),
        ).fetchone()
        if member is None:
            raise_api_error(status.HTTP_404_NOT_FOUND, "MESSAGE_MEDIA_NOT_FOUND", "Message media was not found.")
    row = _expire_if_needed(connection, row)
    if row["upload_status"] in {"expired", "deleted", "failed"}:
        if row["upload_status"] == "expired":
            connection.commit()
        raise_api_error(status.HTTP_404_NOT_FOUND, "MESSAGE_MEDIA_UNAVAILABLE", "Message media is no longer available.")
    if row["upload_status"] not in {"uploaded", "attached"}:
        raise_api_error(status.HTTP_409_CONFLICT, "MESSAGE_MEDIA_NOT_READY", "Message media is not ready.")
    return row


def get_media(user_id: str, media_id: str) -> MessageMediaResponse:
    with transaction() as connection:
        row = _authorized_media_row(connection, user_id, media_id)
    return MessageMediaResponse(media=_record(row))


def serve_media(user_id: str, media_id: str, variant: str) -> FileResponse:
    with transaction() as connection:
        row = _authorized_media_row(connection, user_id, media_id)
    key = row["thumbnail_storage_key"] if variant == "thumbnail" else row["storage_key"]
    if variant not in {"original", "thumbnail"} or not key:
        raise_api_error(status.HTTP_404_NOT_FOUND, "MESSAGE_MEDIA_VARIANT_NOT_FOUND", "Message media variant was not found.")
    path = storage_path(key)
    if not path.is_file():
        raise_api_error(status.HTTP_404_NOT_FOUND, "MESSAGE_MEDIA_UNAVAILABLE", "Message media is no longer available.")
    return FileResponse(path, media_type="image/jpeg" if variant == "thumbnail" else row["mime_type"])


def validate_media_for_message(connection, user_id: str, media_ids: list[str], expected_type: str = "image") -> list[Any]:
    if len(media_ids) != len(set(media_ids)):
        raise_api_error(status.HTTP_400_BAD_REQUEST, "MESSAGE_MEDIA_DUPLICATE", "An image attachment cannot be repeated.")
    rows = []
    for media_id in media_ids:
        row = _expire_if_needed(connection, _select_media(connection, media_id, user_id))
        if row["media_type"] != expected_type:
            raise_api_error(status.HTTP_400_BAD_REQUEST, "MESSAGE_MEDIA_TYPE_INVALID", "The attachment media type does not match the message type.")
        if row["message_id"] is not None or row["upload_status"] == "attached":
            raise_api_error(status.HTTP_409_CONFLICT, "MESSAGE_MEDIA_ALREADY_ATTACHED", "The media is already attached to a message.")
        if row["upload_status"] != "uploaded":
            code = "MESSAGE_MEDIA_EXPIRED" if row["upload_status"] == "expired" else "MESSAGE_MEDIA_NOT_READY"
            raise_api_error(status.HTTP_409_CONFLICT, code, "The media must finish uploading before it can be sent.")
        rows.append(row)
    return rows


def attach_media_to_message(connection, user_id: str, message_id: str, media_ids: list[str]) -> None:
    for media_id in media_ids:
        advisory_lock(connection, f"media:{media_id}")
        updated = connection.execute(
            "UPDATE chat_message_media SET message_id = ?, upload_status = 'attached', attached_at = ? WHERE media_id = ? AND owner_user_id = ? AND upload_status = 'uploaded' AND message_id IS NULL;",
            (message_id, utc_now_iso(), media_id, user_id),
        ).rowcount
        if updated != 1:
            raise_api_error(status.HTTP_409_CONFLICT, "MESSAGE_MEDIA_ALREADY_ATTACHED", "The image is already attached to a message.")
