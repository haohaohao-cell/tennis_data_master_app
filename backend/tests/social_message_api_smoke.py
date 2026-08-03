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


async def main() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        os.environ["TENNIS_DB_PATH"] = str(Path(temp_dir) / "social_message_api_smoke.sqlite3")
        os.environ["TENNIS_VIDEO_STORAGE_DIR"] = str(Path(temp_dir) / "videos")

        from backend.app.core.database import initialize_database
        from backend.app.main import app

        initialize_database()

        alice_token, alice_id = await login_phone(app, "13900000001")
        bob_token, bob_id = await login_phone(app, "13900000002")
        alice_headers = {"authorization": f"Bearer {alice_token}"}
        bob_headers = {"authorization": f"Bearer {bob_token}"}

        follow = await asgi_request(
            app,
            "POST",
            f"/api/v1/social/follows/{bob_id}",
            {"source": "profile"},
            headers=alice_headers,
        )
        assert follow.status == 201, follow
        assert follow.json_body["relationship"]["is_following"] is True
        assert follow.json_body["relationship"]["is_friend"] is False

        notifications = await asgi_request(
            app,
            "GET",
            "/api/v1/notifications",
            headers=bob_headers,
        )
        assert notifications.status == 200, notifications
        assert notifications.headers.get("x-request-id") or notifications.headers.get("X-Request-ID"), notifications.headers
        assert notifications.json_body["unread_count"] == 1
        assert notifications.json_body["items"][0]["event"]["event_type"] == "follow"

        reciprocal = await asgi_request(
            app,
            "POST",
            f"/api/v1/social/follows/{alice_id}",
            headers=bob_headers,
        )
        assert reciprocal.status == 201, reciprocal
        assert reciprocal.json_body["relationship"]["is_friend"] is True

        relationship = await asgi_request(
            app,
            "GET",
            f"/api/v1/social/users/{alice_id}/relationship",
            headers=bob_headers,
        )
        assert relationship.status == 200, relationship
        assert relationship.json_body["is_friend"] is True

        conversation = await asgi_request(
            app,
            "POST",
            "/api/v1/messages/direct-conversations",
            {"target_user_id": bob_id},
            headers=alice_headers,
        )
        assert conversation.status == 201, conversation
        conversation_id = conversation.json_body["conversation"]["conversation_id"]

        sent = await asgi_request(
            app,
            "POST",
            f"/api/v1/messages/conversations/{conversation_id}/messages",
            {
                "message_type": "text",
                "text_content": "训练结束后一起复盘吗？",
                "client_message_id": "alice-message-1",
            },
            headers=alice_headers,
        )
        assert sent.status == 201, sent
        message_id = sent.json_body["message"]["message_id"]

        retry = await asgi_request(
            app,
            "POST",
            f"/api/v1/messages/conversations/{conversation_id}/messages",
            {
                "message_type": "text",
                "text_content": "训练结束后一起复盘吗？",
                "client_message_id": "alice-message-1",
            },
            headers=alice_headers,
        )
        assert retry.status == 201, retry
        assert retry.json_body["message"]["message_id"] == message_id

        bob_counts = await asgi_request(
            app,
            "GET",
            "/api/v1/messages/unread-counts",
            headers=bob_headers,
        )
        assert bob_counts.status == 200, bob_counts
        assert bob_counts.json_body["unread_direct_message_count"] == 1

        bob_conversations = await asgi_request(
            app,
            "GET",
            "/api/v1/messages/conversations",
            headers=bob_headers,
        )
        assert bob_conversations.status == 200, bob_conversations
        assert bob_conversations.json_body["items"][0]["member"]["unread_count"] == 1

        bob_messages = await asgi_request(
            app,
            "GET",
            f"/api/v1/messages/conversations/{conversation_id}/messages",
            headers=bob_headers,
        )
        assert bob_messages.status == 200, bob_messages
        assert bob_messages.json_body["items"][0]["message_id"] == message_id

        message_center_paths = (
            "/api/v1/messages/conversations?page=1&page_size=30",
            "/api/v1/notifications?page=1&page_size=30",
            "/api/v1/messages/requests?box=inbox&page=1&page_size=30&status=pending",
            "/api/v1/messages/unread-counts",
        )
        for _ in range(20):
            responses = await asyncio.gather(
                *(asgi_request(app, "GET", path, headers=bob_headers) for path in message_center_paths)
            )
            assert all(response.status == 200 for response in responses), responses

        marked = await asgi_request(
            app,
            "POST",
            f"/api/v1/messages/conversations/{conversation_id}/read",
            headers=bob_headers,
        )
        assert marked.status == 200, marked
        assert marked.json_body["unread_count"] == 0

        bob_counts_after_read = await asgi_request(
            app,
            "GET",
            "/api/v1/messages/unread-counts",
            headers=bob_headers,
        )
        assert bob_counts_after_read.json_body["unread_direct_message_count"] == 0

        group = await asgi_request(
            app,
            "POST",
            "/api/v1/messages/groups",
            {
                "title": "周末训练群",
                "group_type": "training_group",
                "member_user_ids": [bob_id],
            },
            headers=alice_headers,
        )
        assert group.status == 201, group

        print("Social and message API smoke test passed.")


if __name__ == "__main__":
    asyncio.run(main())
