from __future__ import annotations

import asyncio
import os
from pathlib import Path
import sys
import tempfile


ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT_DIR))

from backend.tests.activity_detail_api_smoke import login_phone
from backend.tests.auth_api_smoke import asgi_request


PREFERENCE_PATH = "/api/v1/notifications/preferences"
ALL_ENABLED = {
    "direct_message_notifications": True,
    "message_request_notifications": True,
    "like_comment_notifications": True,
    "follow_notifications": True,
    "course_notifications": True,
    "ai_analysis_notifications": True,
}


async def main() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        os.environ["TENNIS_DB_PATH"] = str(Path(temp_dir) / "message_notification_preferences.sqlite3")
        os.environ["TENNIS_VIDEO_STORAGE_DIR"] = str(Path(temp_dir) / "videos")

        from backend.app.core.database import get_connection, initialize_database
        from backend.app.main import app
        from backend.app.messages import service

        initialize_database()
        initialize_database()  # Incremental Messaging schema remains idempotent for existing databases.
        alice_token, alice_id = await login_phone(app, "13932000001")
        bob_token, bob_id = await login_phone(app, "13932000002")
        carol_token, carol_id = await login_phone(app, "13932000003")
        alice_headers = {"authorization": f"Bearer {alice_token}"}
        bob_headers = {"authorization": f"Bearer {bob_token}"}
        carol_headers = {"authorization": f"Bearer {carol_token}"}

        unauthorized = await asgi_request(app, "GET", PREFERENCE_PATH)
        assert unauthorized.status == 401, unauthorized

        # Defaults are effective without materializing one row per existing user.
        defaults = await asgi_request(app, "GET", PREFERENCE_PATH, headers=alice_headers)
        assert defaults.status == 200 and defaults.json_body == ALL_ENABLED, defaults
        with get_connection() as connection:
            assert connection.execute(
                "SELECT COUNT(*) FROM user_notification_preferences WHERE user_id = ?;",
                (alice_id,),
            ).fetchone()[0] == 0

        follow_off = await asgi_request(
            app,
            "PATCH",
            PREFERENCE_PATH,
            {"follow_notifications": False},
            headers=alice_headers,
        )
        assert follow_off.status == 200, follow_off
        assert follow_off.json_body == {**ALL_ENABLED, "follow_notifications": False}

        multi_patch = await asgi_request(
            app,
            "PATCH",
            PREFERENCE_PATH,
            {
                "direct_message_notifications": False,
                "ai_analysis_notifications": False,
            },
            headers=alice_headers,
        )
        expected_alice = {
            **ALL_ENABLED,
            "direct_message_notifications": False,
            "follow_notifications": False,
            "ai_analysis_notifications": False,
        }
        assert multi_patch.status == 200 and multi_patch.json_body == expected_alice, multi_patch

        # A new request/connection sees persisted values; another user retains defaults.
        persisted = await asgi_request(app, "GET", PREFERENCE_PATH, headers=alice_headers)
        bob_defaults = await asgi_request(app, "GET", PREFERENCE_PATH, headers=bob_headers)
        assert persisted.json_body == expected_alice, persisted
        assert bob_defaults.json_body == ALL_ENABLED, bob_defaults

        full_round_trip = {
            "direct_message_notifications": False,
            "message_request_notifications": False,
            "like_comment_notifications": True,
            "follow_notifications": False,
            "course_notifications": True,
            "ai_analysis_notifications": False,
        }
        updated = await asgi_request(
            app, "PATCH", PREFERENCE_PATH, full_round_trip, headers=alice_headers
        )
        reread = await asgi_request(app, "GET", PREFERENCE_PATH, headers=alice_headers)
        assert updated.json_body == reread.json_body == full_round_trip

        for invalid_body in ({}, {"follow_notifications": None}, {"follow_notifications": "false"}, {"unknown": False}):
            invalid = await asgi_request(
                app, "PATCH", PREFERENCE_PATH, invalid_body, headers=alice_headers
            )
            assert invalid.status == 422, (invalid_body, invalid)

        expected_mapping = {
            "follow": "follow",
            "post_like": "like_comment",
            "post_comment": "like_comment",
            "comment_reply": "like_comment",
            "message_request": "message_request",
            "lesson_created": "course",
            "lesson_updated": "course",
            "ai_analysis_completed": "ai_analysis",
        }
        for notification_type, preference_kind in expected_mapping.items():
            assert service.notification_preference_kind(notification_type) == preference_kind
        for notification_type in (
            "mention",
            "video_shared",
            "coach_application_reviewed",
            "system_announcement",
            "custom",
        ):
            assert service.notification_preference_kind(notification_type) is None
            assert service.is_notification_push_allowed_by_preferences(alice_id, notification_type) is True
        assert service.is_notification_preference_enabled(alice_id, "direct_message") is False
        assert service.is_notification_preference_enabled(bob_id, "direct_message") is True
        assert service.is_notification_push_allowed_by_preferences(alice_id, "follow") is False
        assert service.is_notification_push_allowed_by_preferences(alice_id, "post_like") is True

        # Follow preference OFF does not suppress the Notification Center or unread counters.
        bob_follows_alice = await asgi_request(
            app,
            "POST",
            f"/api/v1/social/follows/{alice_id}",
            {"source": "notification-preference-test"},
            headers=bob_headers,
        )
        assert bob_follows_alice.status == 201, bob_follows_alice
        notifications = await asgi_request(app, "GET", "/api/v1/notifications", headers=alice_headers)
        assert notifications.status == 200, notifications
        assert any(item["event"]["notification_type"] == "follow" for item in notifications.json_body["items"])
        assert notifications.json_body["unread_count"] == 1

        # Request preference OFF does not reject, hide, or remove the request from badge semantics.
        request = await asgi_request(
            app,
            "POST",
            "/api/v1/messages/requests",
            {"target_user_id": alice_id, "request_message": "Can we practice?"},
            headers=carol_headers,
        )
        assert request.status == 201, request
        request_id = request.json_body["request"]["message_request_id"]
        requests = await asgi_request(
            app,
            "GET",
            "/api/v1/messages/requests?box=inbox&status=pending",
            headers=alice_headers,
        )
        assert requests.status == 200, requests
        assert [item["message_request_id"] for item in requests.json_body["items"]] == [request_id]
        counts_after_request = await asgi_request(
            app, "GET", "/api/v1/messages/unread-counts", headers=alice_headers
        )
        assert counts_after_request.json_body["pending_message_request_count"] == 1
        assert counts_after_request.json_body["unread_notification_count"] == 2
        assert counts_after_request.json_body["messages_tab_badge_count"] == 2

        # Direct-message preference OFF does not affect conversation, persistence, or unread state.
        alice_follows_bob = await asgi_request(
            app,
            "POST",
            f"/api/v1/social/follows/{bob_id}",
            {"source": "notification-preference-test"},
            headers=alice_headers,
        )
        assert alice_follows_bob.status == 201, alice_follows_bob
        conversation = await asgi_request(
            app,
            "POST",
            "/api/v1/messages/direct-conversations",
            {"target_user_id": alice_id},
            headers=bob_headers,
        )
        assert conversation.status == 201, conversation
        conversation_id = conversation.json_body["conversation"]["conversation_id"]
        sent = await asgi_request(
            app,
            "POST",
            f"/api/v1/messages/conversations/{conversation_id}/messages",
            {
                "message_type": "text",
                "text_content": "Preference does not block messages.",
                "client_message_id": "preference-dm-1",
            },
            headers=bob_headers,
        )
        assert sent.status == 201, sent
        with get_connection() as connection:
            assert connection.execute(
                "SELECT COUNT(*) FROM chat_messages WHERE message_id = ?;",
                (sent.json_body["message"]["message_id"],),
            ).fetchone()[0] == 1
        final_counts = await asgi_request(
            app, "GET", "/api/v1/messages/unread-counts", headers=alice_headers
        )
        assert final_counts.json_body["unread_direct_message_count"] == 1
        assert final_counts.json_body["pending_message_request_count"] == 1
        assert final_counts.json_body["unread_notification_count"] == 2
        assert final_counts.json_body["messages_tab_badge_count"] == 3

        print("Message notification preferences API test passed.")


if __name__ == "__main__":
    asyncio.run(main())
