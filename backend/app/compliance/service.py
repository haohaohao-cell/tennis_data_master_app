from __future__ import annotations
import hashlib, json, uuid
from datetime import timedelta
from typing import Any
from fastapi import status
from backend.app.auth.service import raise_api_error
from backend.app.core.database import get_connection, transaction
from backend.app.core.time import utc_now_iso
from backend.app.compliance.export_storage import get_export_storage
from backend.app.compliance.schemas import DeletionRequestRecord, ExportRequestRecord, GovernanceRequestCreate, GovernanceResponse

def _dict(row: Any) -> dict[str, Any]: return {key: row[key] for key in row.keys()}
def _audit(connection: Any, actor: str, action: str, kind: str, target: str, request_id: str | None, before: Any, after: Any, result: str) -> None:
    connection.execute("INSERT INTO compliance_audit_logs (audit_id, actor_user_id, action, target_kind, target_id, request_id, before_state_hash, after_state_hash, reason_code, result) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);", (str(uuid.uuid4()), actor, action, kind, target, request_id, hashlib.sha256(json.dumps(before, sort_keys=True, default=str).encode()).hexdigest(), hashlib.sha256(json.dumps(after, sort_keys=True, default=str).encode()).hexdigest(), action[:80], result[:80]))
def _summary(connection: Any, user_id: str) -> dict[str, int]:
    queries = {"messages": "SELECT COUNT(*) AS n FROM chat_messages WHERE sender_user_id = ?", "reactions": "SELECT COUNT(*) AS n FROM chat_message_reactions WHERE user_id = ?", "forwards": "SELECT COUNT(*) AS n FROM chat_message_forwards WHERE sender_user_id = ?", "reports": "SELECT COUNT(*) AS n FROM content_reports WHERE reporter_user_id = ?", "activities": "SELECT COUNT(*) AS n FROM tennis_activities WHERE owner_user_id = ? AND deleted_at IS NULL", "media": "SELECT COUNT(*) AS n FROM chat_message_media WHERE owner_user_id = ?", "devices": "SELECT COUNT(*) AS n FROM messaging_devices WHERE user_id = ?"}
    return {key: int(connection.execute(sql, (user_id,)).fetchone()["n"]) for key, sql in queries.items()}

def _export_record(row: Any) -> ExportRequestRecord:
    data = _dict(row)
    summary = json.loads(data.pop("dry_run_summary") or "{}")
    expires = data.get("expires_at")
    available = data.get("status") == "ready" and bool(data.get("file_key")) and bool(expires) and expires > utc_now_iso()
    data.pop("file_key", None)
    return ExportRequestRecord(**data, dry_run_summary=summary, download_available=available)

def create_export(user_id: str, payload: GovernanceRequestCreate) -> GovernanceResponse:
    with transaction() as c:
        existing = c.execute("SELECT * FROM export_requests WHERE requester_user_id = ? AND idempotency_key = ?;", (user_id, payload.idempotency_key)).fetchone()
        if existing: return GovernanceResponse(success=True, request=_export_record(existing))
        now = utc_now_iso(); rid = str(uuid.uuid4()); summary = _summary(c, user_id)
        c.execute("INSERT INTO export_requests (export_request_id, requester_user_id, status, idempotency_key, dry_run_summary, created_at, updated_at) VALUES (?, ?, 'requested', ?, ?, ?, ?);", (rid, user_id, payload.idempotency_key, json.dumps(summary), now, now))
        _audit(c, user_id, "export_requested", "export_request", rid, rid, {}, summary, "accepted")
        row = c.execute("SELECT * FROM export_requests WHERE export_request_id = ?;", (rid,)).fetchone()
    return GovernanceResponse(success=True, request=_export_record(row))

def create_deletion(user_id: str, payload: GovernanceRequestCreate) -> GovernanceResponse:
    with transaction() as c:
        existing = c.execute("SELECT * FROM deletion_requests WHERE requester_user_id = ? AND idempotency_key = ?;", (user_id, payload.idempotency_key)).fetchone()
        if existing: return GovernanceResponse(success=True, request=DeletionRequestRecord(**_dict(existing), dry_run_summary=json.loads(existing["dry_run_summary"] or "{}")))
        now = utc_now_iso(); rid = str(uuid.uuid4()); summary = _summary(c, user_id)
        c.execute("INSERT INTO deletion_requests (deletion_request_id, requester_user_id, status, idempotency_key, requested_scope, dry_run_summary, created_at, updated_at) VALUES (?, ?, 'review_required', ?, 'user_owned_data', ?, ?, ?);", (rid, user_id, payload.idempotency_key, json.dumps(summary), now, now))
        _audit(c, user_id, "deletion_requested", "deletion_request", rid, rid, {}, summary, "review_required")
        row = c.execute("SELECT * FROM deletion_requests WHERE deletion_request_id = ?;", (rid,)).fetchone()
    data = _dict(row); data.pop("dry_run_summary", None)
    return GovernanceResponse(success=True, request=DeletionRequestRecord(**data, dry_run_summary=summary))

def list_requests(user_id: str, kind: str) -> list[Any]:
    table = "export_requests" if kind == "export" else "deletion_requests"; key = "export_request_id" if kind == "export" else "deletion_request_id"
    with get_connection() as c:
        rows = c.execute(f"SELECT * FROM {table} WHERE requester_user_id = ? ORDER BY created_at DESC;", (user_id,)).fetchall()
    cls = ExportRequestRecord if kind == "export" else DeletionRequestRecord
    return [_export_record(row) if kind == "export" else cls(**_dict(row), dry_run_summary=json.loads(row["dry_run_summary"] or "{}")) for row in rows]

def generate_export(user_id: str, request_id: str) -> ExportRequestRecord:
    with transaction(immediate=True) as c:
        row = c.execute("SELECT * FROM export_requests WHERE export_request_id = ? AND requester_user_id = ?", (request_id, user_id)).fetchone()
        if not row: raise_api_error(404, "EXPORT_REQUEST_NOT_FOUND", "Export request was not found.")
        if row["status"] == "ready" and row["expires_at"] and row["expires_at"] > utc_now_iso(): return _export_record(row)
        now = utc_now_iso(); c.execute("UPDATE export_requests SET status='processing', updated_at=?, error_code=NULL WHERE export_request_id=?", (now, request_id))
    try:
        with get_connection() as c:
            user = c.execute("SELECT user_id, nickname, phone, email, status, created_at FROM users WHERE user_id=?", (user_id,)).fetchone()
            payload = {"version": 1, "scope": "user_owned_data", "profile": dict(user) if user else {}, "messages": [dict(r) for r in c.execute("SELECT message_id, conversation_id, text_content, message_type, created_at FROM chat_messages WHERE sender_user_id=? ORDER BY created_at", (user_id,)).fetchall()], "reactions": [dict(r) for r in c.execute("SELECT message_id, reaction_type, created_at FROM chat_message_reactions WHERE user_id=?", (user_id,)).fetchall()], "forwards": [dict(r) for r in c.execute("SELECT source_message_id, forwarded_message_id, created_at FROM chat_message_forwards WHERE sender_user_id=?", (user_id,)).fetchall()], "reports": [dict(r) for r in c.execute("SELECT content_report_id, target_type, target_id, status, created_at FROM content_reports WHERE reporter_user_id=?", (user_id,)).fetchall()], "notification_preferences": [dict(r) for r in c.execute("SELECT * FROM user_notification_preferences WHERE user_id=?", (user_id,)).fetchall()]}
        key = get_export_storage().put_export(
            request_id,
            json.dumps(payload, ensure_ascii=True, default=str).encode("utf-8"),
        )
        expires = ( __import__('backend.app.core.time', fromlist=['utc_now']).utc_now() + timedelta(hours=24)).isoformat(timespec="seconds").replace("+00:00", "Z")
        with transaction(immediate=True) as c:
            c.execute("UPDATE export_requests SET status='ready', file_key=?, expires_at=?, completed_at=?, updated_at=? WHERE export_request_id=?", (key, expires, utc_now_iso(), utc_now_iso(), request_id)); row = c.execute("SELECT * FROM export_requests WHERE export_request_id=?", (request_id,)).fetchone()
        return _export_record(row)
    except Exception:
        with transaction(immediate=True) as c: c.execute("UPDATE export_requests SET status='failed', error_code='EXPORT_GENERATION_FAILED', updated_at=? WHERE export_request_id=?", (utc_now_iso(), request_id))
        raise_api_error(500, "EXPORT_GENERATION_FAILED", "Export generation failed.")

def export_file_path(user_id: str, request_id: str, *, allow_admin: bool = False):
    with get_connection() as c:
        row = c.execute("SELECT * FROM export_requests WHERE export_request_id=?" + ("" if allow_admin else " AND requester_user_id=?"), (request_id,) if allow_admin else (request_id, user_id)).fetchone()
    if not row: raise_api_error(404, "EXPORT_REQUEST_NOT_FOUND", "Export request was not found.")
    if row["status"] != "ready" or not row["file_key"]: raise_api_error(409, "EXPORT_FILE_UNAVAILABLE", "Export file is not available.")
    if not row["expires_at"] or row["expires_at"] <= utc_now_iso(): raise_api_error(409, "EXPORT_EXPIRED", "Export file has expired.")
    try:
        return get_export_storage().open_export(row["file_key"])
    except (FileNotFoundError, ValueError):
        raise_api_error(409, "EXPORT_FILE_UNAVAILABLE", "Export file is not available.")

def process_deletion(user_id: str, request_id: str) -> GovernanceResponse:
    with transaction(immediate=True) as c:
        row = c.execute("SELECT * FROM deletion_requests WHERE deletion_request_id = ? AND requester_user_id = ?;", (request_id, user_id)).fetchone()
        if not row: raise_api_error(404, "DELETION_REQUEST_NOT_FOUND", "Deletion request was not found.")
        if row["status"] == "completed":
            data = _dict(row); data.pop("dry_run_summary", None)
            return GovernanceResponse(success=True, request=DeletionRequestRecord(**data, dry_run_summary=json.loads(row["dry_run_summary"] or "{}")))
        if row["status"] != "review_required": raise_api_error(409, "DELETION_REQUEST_STATUS_INVALID", "Deletion request is not ready for processing.")
        now = utc_now_iso(); c.execute("UPDATE messaging_devices SET revoked_at = COALESCE(revoked_at, ?) WHERE user_id = ? AND revoked_at IS NULL;", (now, user_id)); c.execute("UPDATE push_device_tokens SET status = 'revoked', revoked_at = COALESCE(revoked_at, ?), updated_at = ? WHERE user_id = ? AND status = 'active';", (now, now, user_id)); c.execute("UPDATE push_deliveries SET status = 'cancelled', updated_at = ? WHERE user_id = ? AND status IN ('pending','leased','retryable');", (now, user_id)); c.execute("UPDATE deletion_requests SET status = 'completed', completed_at = ?, updated_at = ? WHERE deletion_request_id = ?;", (now, now, request_id)); _audit(c, user_id, "deletion_processed", "deletion_request", request_id, request_id, {"status": row["status"]}, {"status": "completed"}, "orchestrated_only")
        updated = c.execute("SELECT * FROM deletion_requests WHERE deletion_request_id = ?;", (request_id,)).fetchone()
    from backend.app.messages.realtime import registry
    registry.disconnect_user(user_id)
    data = _dict(updated); data.pop("dry_run_summary", None)
    return GovernanceResponse(success=True, request=DeletionRequestRecord(**data, dry_run_summary=json.loads(updated["dry_run_summary"] or "{}")))
