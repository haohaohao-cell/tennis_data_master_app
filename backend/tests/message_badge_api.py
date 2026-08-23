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


async def unread_counts(app, headers: dict[str, str]) -> dict[str, int]:
    response = await asgi_request(app, "GET", "/api/v1/messages/unread-counts", headers=headers)
    assert response.status == 200, response
    return response.json_body


async def mark_all_notifications_read(app, headers: dict[str, str]) -> None:
    response = await asgi_request(app, "POST", "/api/v1/notifications/read-all", headers=headers)
    assert response.status == 200, response


async def main() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        os.environ["TENNIS_DB_PATH"] = str(Path(temp_dir) / "message_badge.sqlite3")
        os.environ["TENNIS_VIDEO_STORAGE_DIR"] = str(Path(temp_dir) / "videos")

        from backend.app.core.database import initialize_database, transaction
        from backend.app.main import app
        from backend.app.messages import service

        initialize_database()
        alice_token, alice_id = await login_phone(app, "13910000001")
        bob_token, bob_id = await login_phone(app, "13910000002")
        carol_token, carol_id = await login_phone(app, "13910000003")
        dave_token, dave_id = await login_phone(app, "13910000004")
        alice_headers = {"authorization": f"Bearer {alice_token}"}
        bob_headers = {"authorization": f"Bearer {bob_token}"}
        carol_headers = {"authorization": f"Bearer {carol_token}"}
        dave_headers = {"authorization": f"Bearer {dave_token}"}

        # Zero state.
        counts = await unread_counts(app, alice_headers)
        assert counts == {
            "unread_direct_message_count": 0,
            "unread_group_message_count": 0,
            "unread_notification_count": 0,
            "pending_message_request_count": 0,
            "total_unread_count": 0,
            "messages_tab_badge_count": 0,
        }, counts

        # Establish a direct conversation, clear follow notifications, then prove direct-only counting.
        for headers, target_id in ((alice_headers, bob_id), (bob_headers, alice_id)):
            response = await asgi_request(app, "POST", f"/api/v1/social/follows/{target_id}", headers=headers)
            assert response.status == 201, response
        await mark_all_notifications_read(app, alice_headers)
        conversation = await asgi_request(
            app, "POST", "/api/v1/messages/direct-conversations", {"target_user_id": alice_id}, headers=bob_headers
        )
        assert conversation.status == 201, conversation
        conversation_id = conversation.json_body["conversation"]["conversation_id"]
        response = await asgi_request(
            app,
            "POST",
            f"/api/v1/messages/conversations/{conversation_id}/messages",
            {"message_type": "text", "text_content": "direct", "client_message_id": "badge-direct-1"},
            headers=bob_headers,
        )
        assert response.status == 201, response
        counts = await unread_counts(app, alice_headers)
        assert counts["unread_direct_message_count"] == counts["messages_tab_badge_count"] == 1, counts

        # Notification-only counting.
        response = await asgi_request(app, "POST", f"/api/v1/messages/conversations/{conversation_id}/read", headers=alice_headers)
        assert response.status == 200, response
        with transaction() as connection:
            service.create_notification_in_transaction(
                connection,
                recipient_user_id=alice_id,
                event_type="custom",
                category="interaction",
                actor_user_id=bob_id,
                object_type="user",
                object_id=bob_id,
                title="Badge notification",
                dedup_key="badge-notification-only",
            )
        counts = await unread_counts(app, alice_headers)
        assert counts["unread_notification_count"] == counts["messages_tab_badge_count"] == 1, counts
        await mark_all_notifications_read(app, alice_headers)

        # A natural incoming request keeps its notification unread but contributes only once to the product badge.
        response = await asgi_request(
            app, "POST", "/api/v1/messages/requests", {"target_user_id": alice_id}, headers=carol_headers
        )
        assert response.status == 201, response
        carol_request_id = response.json_body["request"]["message_request_id"]
        counts = await unread_counts(app, alice_headers)
        assert counts["unread_notification_count"] == 1, counts
        assert counts["pending_message_request_count"] == 1, counts
        assert counts["messages_tab_badge_count"] == 1, counts
        assert counts["total_unread_count"] == 1, counts

        # Outgoing requests must not affect the sender's badge.
        before_outgoing = await unread_counts(app, alice_headers)
        response = await asgi_request(
            app, "POST", "/api/v1/messages/requests", {"target_user_id": dave_id}, headers=alice_headers
        )
        assert response.status == 201, response
        assert await unread_counts(app, alice_headers) == before_outgoing

        # Combined direct, notification, and pending-request values.
        response = await asgi_request(
            app,
            "POST",
            f"/api/v1/messages/conversations/{conversation_id}/messages",
            {"message_type": "text", "text_content": "combined", "client_message_id": "badge-direct-2"},
            headers=bob_headers,
        )
        assert response.status == 201, response
        with transaction() as connection:
            service.create_notification_in_transaction(
                connection,
                recipient_user_id=alice_id,
                event_type="custom",
                category="interaction",
                actor_user_id=bob_id,
                object_type="user",
                object_id=bob_id,
                title="Combined notification",
                dedup_key="badge-combined-notification",
            )
        counts = await unread_counts(app, alice_headers)
        assert (counts["unread_direct_message_count"], counts["unread_notification_count"], counts["pending_message_request_count"]) == (1, 2, 1), counts
        assert counts["messages_tab_badge_count"] == 3, counts

        # Accept removes the request contribution while its unread request notification stays excluded.
        response = await asgi_request(app, "POST", f"/api/v1/messages/requests/{carol_request_id}/accept", headers=alice_headers)
        assert response.status == 200, response
        counts = await unread_counts(app, alice_headers)
        assert counts["unread_notification_count"] == 2, counts
        assert counts["pending_message_request_count"] == 0, counts
        assert counts["messages_tab_badge_count"] == 2, counts

        # Decline has the same behavior: its stale unread request notification never becomes ordinary.
        response = await asgi_request(
            app, "POST", "/api/v1/messages/requests", {"target_user_id": alice_id}, headers=dave_headers
        )
        assert response.status == 201, response
        dave_request_id = response.json_body["request"]["message_request_id"]
        response = await asgi_request(app, "POST", f"/api/v1/messages/requests/{dave_request_id}/decline", headers=alice_headers)
        assert response.status == 200, response
        counts = await unread_counts(app, alice_headers)
        assert counts["unread_notification_count"] == 3, counts
        assert counts["pending_message_request_count"] == 0, counts
        assert counts["messages_tab_badge_count"] == 2, counts

        # More than the first page of incoming requests proves the server count is pagination-independent.
        await mark_all_notifications_read(app, alice_headers)
        response = await asgi_request(app, "POST", f"/api/v1/messages/conversations/{conversation_id}/read", headers=alice_headers)
        assert response.status == 200, response
        for index in range(31):
            token, _ = await login_phone(app, f"1392{index:07d}")
            response = await asgi_request(
                app,
                "POST",
                "/api/v1/messages/requests",
                {"target_user_id": alice_id},
                headers={"authorization": f"Bearer {token}"},
            )
            assert response.status == 201, response
        counts = await unread_counts(app, alice_headers)
        assert counts["unread_notification_count"] == 31, counts
        assert counts["pending_message_request_count"] == counts["messages_tab_badge_count"] == 31, counts
        assert counts["total_unread_count"] == 31, counts

        # Group unread remains in the legacy total, but is excluded from the product badge.
        group = await asgi_request(
            app,
            "POST",
            "/api/v1/messages/groups",
            {"title": "Badge group", "group_type": "custom", "member_user_ids": [alice_id]},
            headers=bob_headers,
        )
        assert group.status == 201, group
        group_id = group.json_body["conversation"]["conversation_id"]
        response = await asgi_request(
            app,
            "POST",
            f"/api/v1/messages/conversations/{group_id}/messages",
            {"message_type": "text", "text_content": "group", "client_message_id": "badge-group-1"},
            headers=bob_headers,
        )
        assert response.status == 201, response
        counts = await unread_counts(app, alice_headers)
        assert counts["unread_group_message_count"] == 1
        assert counts["total_unread_count"] == 32
        assert counts["messages_tab_badge_count"] == 31

        print("Message badge API test passed.")


if __name__ == "__main__":
    asyncio.run(main())
