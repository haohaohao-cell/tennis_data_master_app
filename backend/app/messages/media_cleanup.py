"""Auditable cleanup for message-image derived and temporary files."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from backend.app.core.config import settings
from backend.app.core.database import get_connection, transaction
from backend.app.core.time import utc_now_iso
from backend.app.messages.media_storage import delete_storage_files, storage_path


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def _cleanup_reason(row: Any, current: datetime, grace_hours: int) -> tuple[str | None, list[str]]:
    """Return a deletion reason only when timestamps are valid and still eligible."""
    errors: list[str] = []
    expires_at = _parse_time(row["expires_at"])
    created_at = _parse_time(row["created_at"])
    if row["expires_at"] and expires_at is None:
        errors.append("INVALID_EXPIRES_AT")
    if row["created_at"] and created_at is None:
        errors.append("INVALID_CREATED_AT")
    if errors:
        return None, errors
    if row["upload_status"] == "deleted" and not row["storage_deleted_at"]:
        return "deleted_media", errors
    if (
        row["message_id"] is None
        and row["upload_status"] != "uploading"
        and expires_at is not None
        and expires_at <= current
    ):
        return "expired_unbound", errors
    if (
        row["upload_status"] == "failed"
        and created_at is not None
        and created_at + timedelta(hours=grace_hours) <= current
    ):
        return "failed_media", errors
    return None, errors


def cleanup_message_media(*, dry_run: bool = True, now: datetime | None = None, grace_hours: int = 24) -> dict[str, Any]:
    """Scan the isolated message-media root; execute mode is explicit and retryable."""
    if grace_hours < 0:
        raise ValueError("grace_hours must be non-negative")
    current = now or datetime.now(timezone.utc)
    cutoff = current - timedelta(hours=grace_hours)
    root = settings.message_media_storage_dir.resolve()
    root.mkdir(parents=True, exist_ok=True)
    report: dict[str, Any] = {
        "dry_run": dry_run, "storage_root": str(root), "candidate_media": [],
        "missing_files": [], "orphan_files": [], "temporary_files": [],
        "deleted_files": [], "errors": [],
    }
    with get_connection() as connection:
        rows = connection.execute("SELECT * FROM chat_message_media ORDER BY media_id;").fetchall()
    referenced = {row[field] for row in rows for field in ("storage_key", "thumbnail_storage_key") if row[field]}
    uploading_media_ids = {row["media_id"] for row in rows if row["upload_status"] == "uploading"}
    candidates: list[tuple[Any, str]] = []
    for row in rows:
        reason, reason_errors = _cleanup_reason(row, current, grace_hours)
        report["errors"].extend({"media_id": row["media_id"], "error": error} for error in reason_errors)
        if reason:
            candidates.append((row, reason))
            report["candidate_media"].append({"media_id": row["media_id"], "reason": reason})
        for field in ("storage_key", "thumbnail_storage_key"):
            key = row[field]
            if key:
                try:
                    if not storage_path(key).is_file():
                        report["missing_files"].append({"media_id": row["media_id"], "storage_key": key, "field": field})
                except (OSError, ValueError):
                    report["errors"].append({"media_id": row["media_id"], "storage_key": key, "error": "INVALID_STORAGE_KEY"})
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        if not (relative.startswith("images/") or relative.startswith("videos/")):
            continue
        if relative.endswith(".part"):
            # Upload partials live under images|videos/{media_id}/.  A stale
            # wall-clock timestamp alone cannot prove that a still-uploading
            # request is abandoned, so preserve it while its media row is live.
            media_id = path.parent.name
            if media_id not in uploading_media_ids and datetime.fromtimestamp(path.stat().st_mtime, timezone.utc) <= cutoff:
                report["temporary_files"].append(relative)
        elif relative not in referenced:
            report["orphan_files"].append(relative)
    if dry_run:
        return report
    for row, reason in candidates:
        with transaction(immediate=True, lock_key=f"media:{row['media_id']}") as connection:
            current_row = connection.execute("SELECT * FROM chat_message_media WHERE media_id = ? LIMIT 1;", (row["media_id"],)).fetchone()
            current_reason, reason_errors = (
                _cleanup_reason(current_row, current, grace_hours)
                if current_row is not None
                else (None, [])
            )
            if current_row is None or current_reason != reason:
                continue
            errors = delete_storage_files(current_row["storage_key"], current_row["thumbnail_storage_key"])
            if errors:
                message = "; ".join(errors)[:255]
                connection.execute("UPDATE chat_message_media SET last_cleanup_error = ? WHERE media_id = ?;", (message, row["media_id"]))
                report["errors"].append({"media_id": row["media_id"], "error": message})
                continue
            connection.execute("UPDATE chat_message_media SET upload_status = 'deleted', deleted_at = COALESCE(deleted_at, ?), storage_deleted_at = ?, last_cleanup_error = NULL WHERE media_id = ?;", (utc_now_iso(), utc_now_iso(), row["media_id"]))
            report["deleted_files"].append({"media_id": row["media_id"], "reason": reason})
    # Re-read references after the scan. An upload may have committed while the
    # filesystem walk was in progress; those keys must not be deleted.
    with get_connection() as connection:
        latest_rows = connection.execute(
            "SELECT storage_key, thumbnail_storage_key FROM chat_message_media;"
        ).fetchall()
    latest_referenced = {
        row[field]
        for row in latest_rows
        for field in ("storage_key", "thumbnail_storage_key")
        if row[field]
    }
    for relative in report["temporary_files"] + report["orphan_files"]:
        if relative in latest_referenced:
            continue
        path = root / relative
        try:
            path.relative_to(root)
            if path.is_file():
                path.unlink()
                report["deleted_files"].append({"storage_key": relative, "reason": "temporary_file" if relative.endswith(".part") else "orphan_file"})
        except (OSError, ValueError) as error:
            report["errors"].append({"storage_key": relative, "error": type(error).__name__})
    return report
