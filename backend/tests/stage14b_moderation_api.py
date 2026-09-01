"""Isolated Stage 14B report and moderation contract test."""
from __future__ import annotations
import asyncio, os, sys, tempfile
from pathlib import Path
ROOT_DIR = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT_DIR))
from backend.tests.activity_detail_api_smoke import login_phone
from backend.tests.auth_api_smoke import asgi_request

async def main() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        os.environ["TENNIS_DB_PATH"] = str(Path(temp_dir) / "stage14b.sqlite3")
        os.environ.pop("TENNIS_DATABASE_URL", None); os.environ.pop("TENNIS_POSTGRES_DSN", None)
        from backend.app.core.database import get_connection, initialize_database, transaction
        from backend.app.main import app
        initialize_database()
        (admin_token, admin_id), (reporter_token, reporter_id), (outsider_token, outsider_id) = [await login_phone(app, p) for p in ("13956000001", "13956000002", "13956000003")]
        with transaction() as connection:
            connection.execute("INSERT INTO admin_users (admin_user_id, user_id, role, status) VALUES ('stage14b-admin', ?, 'operator', 'active');", (admin_id,))
        admin = {"authorization": f"Bearer {admin_token}"}; reporter = {"authorization": f"Bearer {reporter_token}"}; outsider = {"authorization": f"Bearer {outsider_token}"}
        group = await asgi_request(app, "POST", "/api/v1/messages/groups", {"title": "Stage 14B", "member_user_ids": [reporter_id]}, headers=reporter)
        assert group.status == 201
        conversation_id = group.json_body["conversation"]["conversation_id"]
        message = await asgi_request(app, "POST", f"/api/v1/messages/conversations/{conversation_id}/messages", {"message_type": "text", "text_content": "reportable message", "client_message_id": "stage14b-message"}, headers=reporter)
        assert message.status == 201
        message_id = message.json_body["message"]["message_id"]
        payload = {"target_kind": "message", "target_id": message_id, "reason_code": "spam", "description": "Repeated unwanted content", "idempotency_key": "stage14b-report-1"}
        first = await asgi_request(app, "POST", "/api/v1/reports/messages", payload, headers=reporter)
        retry = await asgi_request(app, "POST", "/api/v1/reports/messages", payload, headers=reporter)
        assert first.status == retry.status == 201 and first.json_body["report"]["report_id"] == retry.json_body["report"]["report_id"]
        report_id = first.json_body["report"]["report_id"]
        conflict = await asgi_request(app, "POST", "/api/v1/reports/messages", {**payload, "reason_code": "harassment"}, headers=reporter)
        assert conflict.status == 409
        forbidden = await asgi_request(app, "GET", "/api/v1/admin/message-reports", headers=outsider)
        assert forbidden.status == 403
        listed = await asgi_request(app, "GET", "/api/v1/admin/message-reports?status=open", headers=admin)
        assert listed.status == 200 and listed.json_body["items"][0]["report_id"] == report_id
        reviewing = await asgi_request(app, "PATCH", f"/api/v1/admin/message-reports/{report_id}", {"status": "under_review", "resolution_code": "triage"}, headers=admin)
        assert reviewing.status == 200
        processed = await asgi_request(app, "PATCH", f"/api/v1/admin/message-reports/{report_id}", {"status": "resolved", "resolution_code": "confirmed_spam"}, headers=admin)
        assert processed.status == 200 and processed.json_body["report"]["status"] == "resolved", processed
        repeated = await asgi_request(app, "PATCH", f"/api/v1/admin/message-reports/{report_id}", {"status": "resolved", "resolution_code": "confirmed_spam"}, headers=admin)
        assert repeated.status == 200
        invalid = await asgi_request(app, "PATCH", f"/api/v1/admin/message-reports/{report_id}", {"status": "open", "resolution_code": "reopen"}, headers=admin)
        assert invalid.status == 409
        with get_connection() as connection:
            assert connection.execute("SELECT COUNT(*) AS count FROM message_moderation_audit_logs WHERE report_id = ?;", (report_id,)).fetchone()["count"] == 2
        print("Stage 14B moderation API test passed.")

if __name__ == "__main__": asyncio.run(main())
