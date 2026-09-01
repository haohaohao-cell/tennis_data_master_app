"""Stage 13A isolated SQLite/PostgreSQL regression for message object cards."""

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
        postgres_schema = os.environ.get("STAGE13A_POSTGRES_SCHEMA")
        database_path = Path(temp_dir) / "stage13a.sqlite3"
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
        from backend.app.core.database import get_connection, initialize_database, transaction
        from backend.app.main import app
        from backend.app.messages.business_object_access import resolve_business_object_access

        if postgres_schema:
            object.__setattr__(config.settings, "database_url", os.environ["TENNIS_DATABASE_URL"])
        initialize_database()
        accounts = [await login_phone(app, phone) for phone in ("13953000001", "13953000002", "13953000003")]
        (alice_token, alice_id), (bob_token, bob_id), (_, carol_id) = accounts
        alice = {"authorization": f"Bearer {alice_token}"}
        bob = {"authorization": f"Bearer {bob_token}"}
        group = await request(app, "POST", "/api/v1/messages/groups", alice, {"title": "Stage 13A", "member_user_ids": [bob_id]})
        assert group.status == 201, group
        conversation_id = group.json_body["conversation"]["conversation_id"]

        with transaction() as connection:
            connection.execute("INSERT INTO tennis_activities (tennis_activity_id, owner_user_id, title, activity_type, default_visibility) VALUES (?, ?, ?, ?, ?);", ("activity-public", alice_id, "Public practice", "serve_training", "public"))
            connection.execute("INSERT INTO tennis_activities (tennis_activity_id, owner_user_id, title, activity_type, default_visibility) VALUES (?, ?, ?, ?, ?);", ("activity-private", alice_id, "SECRET_ACTIVITY_TITLE", "match", "private"))
            connection.execute("INSERT INTO tennis_activities (tennis_activity_id, owner_user_id, title, activity_type, default_visibility) VALUES (?, ?, ?, ?, ?);", ("activity-deleted", alice_id, "DELETED_ACTIVITY_TITLE", "match", "public"))
            connection.execute("INSERT INTO lessons (lesson_id, coach_user_id, created_by_user_id, title, lesson_type, status) VALUES (?, ?, ?, ?, ?, ?);", ("lesson-archived", alice_id, alice_id, "Archived lesson", "private", "completed"))
            connection.execute("INSERT INTO lesson_students (lesson_student_id, lesson_id, student_user_id, created_by_user_id) VALUES (?, ?, ?, ?);", ("student-bob", "lesson-archived", bob_id, alice_id))
            connection.execute("INSERT INTO lessons (lesson_id, coach_user_id, created_by_user_id, title, lesson_type, status) VALUES (?, ?, ?, ?, ?, ?);", ("lesson-private", alice_id, alice_id, "SECRET_LESSON_TITLE", "private", "scheduled"))
            for video_id, activity_id, visibility, upload_status in (("video-ready", "activity-public", "inherit", "uploaded"), ("video-pending", "activity-public", "inherit", "pending"), ("video-private", "activity-private", "inherit", "uploaded")):
                connection.execute("INSERT INTO videos (video_id, tennis_activity_id, owner_user_id, uploader_user_id, filename, video_path, visibility, upload_status) VALUES (?, ?, ?, ?, ?, ?, ?, ?);", (video_id, activity_id, alice_id, alice_id, f"{video_id}.mp4", f"/private/{video_id}.mp4", visibility, upload_status))
            missing = resolve_business_object_access(connection, "video", "missing-video", bob_id)
            assert missing.access == "not_found" and missing.state == "unavailable"
            assert resolve_business_object_access(connection, "tennis_activity", "activity-private", bob_id).access == "denied"
            assert resolve_business_object_access(connection, "lesson", "lesson-archived", bob_id).state == "archived"
            assert resolve_business_object_access(connection, "video", "video-pending", bob_id).state == "unavailable"
            assert resolve_business_object_access(connection, "analysis", "analysis-id", bob_id).access == "not_found"

        messages: dict[str, str] = {}
        targets = {
            "activity_public": ("tennis_activity", "activity-public"),
            "activity_private": ("tennis_activity", "activity-private"),
            "activity_deleted": ("tennis_activity", "activity-deleted"),
            "lesson_archived": ("lesson", "lesson-archived"),
            "lesson_denied": ("lesson", "lesson-private"),
            "video_ready": ("video", "video-ready"),
            "video_pending": ("video", "video-pending"),
            "video_denied": ("video", "video-private"),
            "analysis_missing": ("analysis", "analysis-id"),
            "unknown": ("custom", "legacy-unknown"),
        }
        for name, (object_type, object_id) in targets.items():
            created = await request(app, "POST", f"/api/v1/messages/conversations/{conversation_id}/messages", alice, {"message_type": "text", "text_content": f"card {name}", "target_object_type": object_type, "target_object_id": object_id, "client_message_id": f"stage13a-{name}"})
            assert created.status == 201, (name, created)
            messages[name] = created.json_body["message"]["message_id"]
        with transaction() as connection:
            connection.execute("UPDATE tennis_activities SET deleted_at = CURRENT_TIMESTAMP WHERE tennis_activity_id = 'activity-deleted';")

        history = await request(app, "GET", f"/api/v1/messages/conversations/{conversation_id}/messages", bob)
        assert history.status == 200, history
        cards = {item["text_content"].removeprefix("card "): item["business_object_card"] for item in history.json_body["items"] if item["text_content"]}
        expected = {
            "activity_public": ("allowed", "active", True), "activity_private": ("denied", "unavailable", False),
            "activity_deleted": ("denied", "deleted", False), "lesson_archived": ("allowed", "archived", True),
            "lesson_denied": ("denied", "unavailable", False), "video_ready": ("allowed", "active", True),
            "video_pending": ("allowed", "unavailable", False), "video_denied": ("denied", "unavailable", False),
            "analysis_missing": ("not_found", "unavailable", False), "unknown": ("not_found", "unavailable", False),
        }
        for name, (access, object_state, preview) in expected.items():
            card = cards[name]
            assert card["access"] == access and card["object_state"] == object_state and card["can_preview"] is preview, (name, card)
            assert card["can_forward"] is (name in {"activity_public", "lesson_archived", "video_ready"})
            assert "private/" not in str(card) and "SECRET_" not in str(card), card
        assert cards["unknown"]["state"] == "unsupported"
        assert cards["video_pending"]["unavailable_reason"] == "media_unavailable"

        searched = await request(app, "GET", f"/api/v1/messages/conversations/{conversation_id}/messages/search?q=card", bob)
        reconciled = await request(app, "POST", f"/api/v1/messages/conversations/{conversation_id}/messages/reconcile", bob, {"message_ids": list(messages.values())})
        assert searched.status == reconciled.status == 200
        for response in (searched, reconciled):
            returned = {item["message_id"]: item["business_object_card"] for item in response.json_body["items"]}
            for name, message_id in messages.items():
                assert returned[message_id]["access"] == expected[name][0]
                assert returned[message_id]["object_state"] == expected[name][1]

        forward = await request(app, "POST", f"/api/v1/messages/conversations/{conversation_id}/messages/{messages['activity_public']}/forward", alice, {"target_conversation_ids": [conversation_id], "client_forward_id": "stage13a-object-forward"})
        assert forward.status == 200 and forward.json_body["items"][0]["message"]["target_object_id"] == "activity-public"
        analysis_forward = await request(app, "POST", f"/api/v1/messages/conversations/{conversation_id}/messages/{messages['analysis_missing']}/forward", alice, {"target_conversation_ids": [conversation_id], "client_forward_id": "stage13a-analysis-forward"})
        assert analysis_forward.status == 400 and analysis_forward.json_body["detail"]["code"] == "MESSAGE_FORWARD_OBJECT_UNSUPPORTED"
        assert carol_id  # Keep the third user available for cross-user fixture expansion.
        assert postgres_schema or database_path.exists()
        print("Stage 13A business-object card test passed.")


if __name__ == "__main__":
    asyncio.run(main())
