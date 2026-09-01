"""Isolated Stage 13C-D object-reference forward and lifecycle regression."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
import sys
import tempfile
from urllib.parse import parse_qsl, quote, urlsplit, urlunsplit

ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT_DIR))

from backend.tests.activity_detail_api_smoke import login_phone
from backend.tests.auth_api_smoke import asgi_request


async def request(app, method: str, path: str, headers: dict[str, str], body: dict | None = None):
    return await asgi_request(app, method, path, body, headers=headers)


async def main() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        postgres_schema = os.environ.get("STAGE13CD_POSTGRES_SCHEMA")
        database_path = Path(temp_dir) / "stage13cd.sqlite3"
        if postgres_schema:
            source_dsn = os.environ["TENNIS_DATABASE_URL"]
            parts = urlsplit(source_dsn)
            query = [(key, value) for key, value in parse_qsl(parts.query, keep_blank_values=True) if key != "options"]
            query.append(("options", f"-c search_path={postgres_schema},pg_catalog"))
            scoped_dsn = urlunsplit((parts.scheme, parts.netloc, parts.path, "&".join(f"{quote(key)}={quote(value)}" for key, value in query), parts.fragment))
            os.environ["TENNIS_DATABASE_URL"] = scoped_dsn
            os.environ["TENNIS_POSTGRES_DSN"] = scoped_dsn
        else:
            os.environ["TENNIS_DB_PATH"] = str(database_path)
            os.environ.pop("TENNIS_DATABASE_URL", None)
            os.environ.pop("TENNIS_POSTGRES_DSN", None)

        from backend.app.core import config
        from backend.app.core.database import get_connection, initialize_database, initialize_sqlite_database, transaction
        from backend.app.main import app

        if postgres_schema:
            object.__setattr__(config.settings, "database_url", os.environ["TENNIS_DATABASE_URL"])
        (initialize_database if postgres_schema else initialize_sqlite_database)()
        accounts = [await login_phone(app, phone) for phone in ("13954000001", "13954000002", "13954000003")]
        (alice_token, alice_id), (bob_token, bob_id), (carol_token, carol_id) = accounts
        alice = {"authorization": f"Bearer {alice_token}"}
        bob = {"authorization": f"Bearer {bob_token}"}
        carol = {"authorization": f"Bearer {carol_token}"}
        source = await request(app, "POST", "/api/v1/messages/groups", alice, {"title": "Stage 13C source", "member_user_ids": [bob_id]})
        target = await request(app, "POST", "/api/v1/messages/groups", alice, {"title": "Stage 13C target", "member_user_ids": [bob_id]})
        denied_target = await request(app, "POST", "/api/v1/messages/groups", alice, {"title": "Stage 13C denied", "member_user_ids": [carol_id]})
        assert source.status == target.status == denied_target.status == 201
        source_id = source.json_body["conversation"]["conversation_id"]
        target_id = target.json_body["conversation"]["conversation_id"]
        denied_target_id = denied_target.json_body["conversation"]["conversation_id"]

        with transaction() as connection:
            connection.execute("INSERT INTO tennis_activities (tennis_activity_id, owner_user_id, title, activity_type, default_visibility) VALUES ('forward-activity', ?, 'Public forward activity', 'serve_training', 'public');", (alice_id,))
            connection.execute("INSERT INTO tennis_activities (tennis_activity_id, owner_user_id, title, activity_type, default_visibility) VALUES ('private-activity', ?, 'SECRET_FORWARD_ACTIVITY', 'match', 'private');", (alice_id,))
            connection.execute("INSERT INTO lessons (lesson_id, coach_user_id, created_by_user_id, title, lesson_type, status) VALUES ('forward-lesson', ?, ?, 'Forward lesson', 'private', 'completed');", (alice_id, alice_id))
            connection.execute("INSERT INTO lesson_students (lesson_student_id, lesson_id, student_user_id, created_by_user_id) VALUES ('forward-student', 'forward-lesson', ?, ?);", (bob_id, alice_id))
            connection.execute("INSERT INTO videos (video_id, tennis_activity_id, owner_user_id, uploader_user_id, filename, video_path, visibility, upload_status) VALUES ('forward-video', 'forward-activity', ?, ?, 'internal-source.mp4', '/private/forward.mp4', 'inherit', 'uploaded');", (alice_id, alice_id))
            connection.execute("INSERT INTO videos (video_id, tennis_activity_id, owner_user_id, uploader_user_id, filename, video_path, visibility, upload_status) VALUES ('pending-video', 'forward-activity', ?, ?, 'pending.mp4', '/private/pending.mp4', 'inherit', 'pending');", (alice_id, alice_id))

        async def create_reference(name: str, object_type: str, object_id: str) -> str:
            response = await request(app, "POST", f"/api/v1/messages/conversations/{source_id}/messages", alice, {"message_type": "text", "text_content": name, "target_object_type": object_type, "target_object_id": object_id, "client_message_id": f"stage13cd-{name}"})
            assert response.status == 201, (name, response)
            return response.json_body["message"]["message_id"]

        activity_message = await create_reference("activity", "tennis_activity", "forward-activity")
        lesson_message = await create_reference("lesson", "lesson", "forward-lesson")
        video_message = await create_reference("video", "video", "forward-video")
        private_message = await create_reference("private", "tennis_activity", "private-activity")
        pending_message = await create_reference("pending", "video", "pending-video")
        analysis_message = await create_reference("analysis", "analysis", "missing-analysis")
        media_source = await request(app, "POST", f"/api/v1/messages/conversations/{source_id}/messages", alice, {"message_type": "text", "text_content": "media", "client_message_id": "stage13cd-media"})
        assert media_source.status == 201
        media_message = media_source.json_body["message"]["message_id"]
        with transaction() as connection:
            connection.execute("UPDATE chat_messages SET message_type = 'image' WHERE message_id = ?;", (media_message,))

        forwarded: dict[str, str] = {}
        for name, message_id in (("activity", activity_message), ("lesson", lesson_message), ("video", video_message)):
            response = await request(app, "POST", f"/api/v1/messages/conversations/{source_id}/messages/{message_id}/forward", alice, {"target_conversation_ids": [target_id], "client_forward_id": f"stage13cd-{name}-forward"})
            assert response.status == 200, (name, response)
            item = response.json_body["items"][0]
            assert item["message"]["target_object_id"] and item["message"]["business_object_card"]["can_forward"]
            assert item["message"]["business_object_card"]["metadata"].get("video_path") is None
            forwarded[name] = item["message"]["message_id"]
            retry = await request(app, "POST", f"/api/v1/messages/conversations/{source_id}/messages/{message_id}/forward", alice, {"target_conversation_ids": [target_id], "client_forward_id": f"stage13cd-{name}-forward"})
            assert retry.status == 200 and retry.json_body["items"][0]["message"]["message_id"] == forwarded[name]

        before = (await request(app, "GET", f"/api/v1/messages/conversations/{target_id}/messages", alice)).json_body["items"]
        partial = await request(app, "POST", f"/api/v1/messages/conversations/{source_id}/messages/{private_message}/forward", alice, {"target_conversation_ids": [target_id, denied_target_id], "client_forward_id": "stage13cd-private-multi"})
        after = (await request(app, "GET", f"/api/v1/messages/conversations/{target_id}/messages", alice)).json_body["items"]
        assert partial.status == 403 and partial.json_body["detail"]["code"] == "MESSAGE_FORWARD_TARGET_OBJECT_FORBIDDEN" and len(before) == len(after)
        for message_id, code in ((pending_message, "MESSAGE_FORWARD_OBJECT_UNAVAILABLE"), (analysis_message, "MESSAGE_FORWARD_OBJECT_UNSUPPORTED"), (media_message, "MESSAGE_FORWARD_TYPE_UNSUPPORTED")):
            response = await request(app, "POST", f"/api/v1/messages/conversations/{source_id}/messages/{message_id}/forward", alice, {"target_conversation_ids": [target_id], "client_forward_id": f"stage13cd-reject-{message_id}"})
            assert response.status in {400, 409} and response.json_body["detail"]["code"] == code, response

        with transaction() as connection:
            connection.execute("UPDATE tennis_activities SET deleted_at = CURRENT_TIMESTAMP WHERE tennis_activity_id = 'forward-activity';")
            event_types = {row["event_type"] for row in connection.execute("SELECT event_type FROM user_sync_events WHERE conversation_id = ?;", (target_id,)).fetchall()}
            assert "message.forwarded" in event_types
        history = await request(app, "GET", f"/api/v1/messages/conversations/{target_id}/messages", bob)
        assert history.status == 200
        deleted_card = next(item["business_object_card"] for item in history.json_body["items"] if item["message_id"] == forwarded["activity"])
        assert deleted_card["object_state"] == "deleted" and deleted_card["title"] is None and deleted_card["summary"] is None
        reconcile = await request(app, "POST", f"/api/v1/messages/conversations/{target_id}/messages/reconcile", bob, {"message_ids": list(forwarded.values())})
        assert reconcile.status == 200 and all("private/" not in str(item["business_object_card"]) for item in reconcile.json_body["items"])
        assert carol and (postgres_schema or database_path.exists())
        print("Stage 13C-D forward and lifecycle test passed.")


if __name__ == "__main__":
    asyncio.run(main())
