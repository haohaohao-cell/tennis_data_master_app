from __future__ import annotations

import asyncio
import os
from pathlib import Path
import sys
import tempfile
import uuid


ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT_DIR))

from backend.tests.activity_detail_api_smoke import login_phone
from backend.tests.auth_api_smoke import asgi_request


async def main() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        os.environ["TENNIS_DB_PATH"] = str(Path(temp_dir) / "message_notification_target.sqlite3")
        os.environ["TENNIS_VIDEO_STORAGE_DIR"] = str(Path(temp_dir) / "videos")

        from backend.app.core.database import initialize_database, transaction
        from backend.app.main import app
        from backend.app.messages import service

        initialize_database()
        recipient_token, recipient_id = await login_phone(app, "13931000001")
        requester_token, requester_id = await login_phone(app, "13931000002")
        _, legacy_requester_id = await login_phone(app, "13931000003")
        recipient_headers = {"authorization": f"Bearer {recipient_token}"}
        requester_headers = {"authorization": f"Bearer {requester_token}"}

        post_id = "post-target-1"
        activity_id = "activity-target-1"
        event_specs = (
            ("follow", "interaction", "user", requester_id, None, None, "follow"),
            ("post_like", "interaction", "social_post", post_id, None, None, "like"),
            ("post_comment", "interaction", "comment", "comment-1", "social_post", post_id, "comment"),
            ("comment_reply", "interaction", "comment", "comment-2", "social_post", post_id, "reply"),
            ("system_announcement", "system", None, None, None, None, "system"),
            ("post_like", "interaction", "social_post", "   ", None, None, "malformed"),
            (
                "ai_analysis_completed",
                "ai",
                "analysis",
                "analysis-1",
                "tennis_activity",
                activity_id,
                "ai",
            ),
            ("lesson_updated", "lesson", "lesson", "lesson-1", None, None, "lesson"),
            ("coach_application_reviewed", "coach", None, None, None, None, "coach"),
        )
        with transaction() as connection:
            for event_type, category, object_type, object_id, context_type, context_id, title in event_specs:
                service.create_notification_in_transaction(
                    connection,
                    recipient_user_id=recipient_id,
                    event_type=event_type,
                    category=category,
                    actor_user_id=requester_id,
                    object_type=object_type,
                    object_id=object_id,
                    context_type=context_type,
                    context_id=context_id,
                    title=title,
                    dedup_key=f"target-test:{title}",
                )

        new_request = await asgi_request(
            app,
            "POST",
            "/api/v1/messages/requests",
            {"target_user_id": recipient_id},
            headers=requester_headers,
        )
        assert new_request.status == 201, new_request
        new_request_id = new_request.json_body["request"]["message_request_id"]

        legacy_request_id = str(uuid.uuid4())
        with transaction() as connection:
            connection.execute(
                """
                INSERT INTO chat_message_requests (
                    message_request_id, requester_user_id, recipient_user_id, request_message, source
                ) VALUES (?, ?, ?, ?, ?);
                """,
                (legacy_request_id, legacy_requester_id, recipient_id, "legacy", "test"),
            )
            service.create_notification_in_transaction(
                connection,
                recipient_user_id=recipient_id,
                event_type="custom",
                category="interaction",
                actor_user_id=legacy_requester_id,
                object_type="user",
                object_id=legacy_requester_id,
                title="legacy-request",
                deep_link="/messages/requests",
                dedup_key=f"message_request:{legacy_request_id}",
                payload={"message_request_id": legacy_request_id},
            )

        response = await asgi_request(
            app, "GET", "/api/v1/notifications?page_size=50", headers=recipient_headers
        )
        assert response.status == 200, response
        events = {item["event"]["title"]: item["event"] for item in response.json_body["items"]}
        assert events["follow"]["target"] == {"type": "user_profile", "user_id": requester_id}
        assert events["like"]["target"] == {"type": "post_detail", "post_id": post_id}
        assert events["comment"]["target"] == {"type": "post_comments", "post_id": post_id}
        assert events["reply"]["target"] == {"type": "post_comments", "post_id": post_id}
        assert events["system"]["target"] == {"type": "none"}
        assert events["malformed"]["target"] == {"type": "none"}
        assert events["ai"]["target"] == {"type": "activity_detail", "activity_id": activity_id}
        assert events["lesson"]["target"] == {"type": "none"}
        assert events["coach"]["target"] == {"type": "coach_identity"}

        request_targets = {
            event["target"]["request_id"]: event["target"]
            for event in events.values()
            if event["notification_type"] == "message_request"
        }
        assert request_targets == {
            new_request_id: {"type": "message_request", "request_id": new_request_id},
            legacy_request_id: {"type": "message_request", "request_id": legacy_request_id},
        }

        # The additive target does not replace compatibility metadata.
        assert events["legacy-request"]["deep_link"] == "/messages/requests"
        assert "object_type" in events["like"]
        assert "payload_json" in events["legacy-request"]

        print("Message notification target API test passed.")


if __name__ == "__main__":
    asyncio.run(main())
