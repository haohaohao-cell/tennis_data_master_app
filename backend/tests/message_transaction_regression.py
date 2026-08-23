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


async def _follow(app, source_id: str, target_id: str, headers: dict[str, str]) -> None:
    response = await asgi_request(
        app,
        "POST",
        f"/api/v1/social/follows/{target_id}",
        {"source": "message-transaction-regression"},
        headers=headers,
    )
    assert response.status == 201, response


async def main() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        os.environ["TENNIS_DB_PATH"] = str(Path(temp_dir) / "message_transaction_regression.sqlite3")

        from backend.app.core.database import get_connection, initialize_database, transaction
        from backend.app.main import app
        from backend.app.messages import service

        initialize_database()
        users = [
            await login_phone(app, phone)
            for phone in ("13950000001", "13950000002", "13950000003")
        ]
        (alice_token, alice_id), (bob_token, bob_id), (carol_token, carol_id) = users
        alice_headers = {"authorization": f"Bearer {alice_token}"}
        bob_headers = {"authorization": f"Bearer {bob_token}"}
        carol_headers = {"authorization": f"Bearer {carol_token}"}

        await _follow(app, alice_id, bob_id, alice_headers)
        await _follow(app, bob_id, alice_id, bob_headers)
        await _follow(app, alice_id, carol_id, alice_headers)
        await _follow(app, carol_id, alice_id, carol_headers)

        direct_ab = await asgi_request(
            app,
            "POST",
            "/api/v1/messages/direct-conversations",
            {"target_user_id": bob_id},
            headers=alice_headers,
        )
        assert direct_ab.status == 201, direct_ab
        conversation_ab = direct_ab.json_body["conversation"]["conversation_id"]

        direct_ac = await asgi_request(
            app,
            "POST",
            "/api/v1/messages/direct-conversations",
            {"target_user_id": carol_id},
            headers=alice_headers,
        )
        assert direct_ac.status == 201, direct_ac
        conversation_ac = direct_ac.json_body["conversation"]["conversation_id"]

        # Concurrent mark-read calls must serialize without lock errors or counter drift.
        for index in range(2):
            response = await asgi_request(
                app,
                "POST",
                f"/api/v1/messages/conversations/{conversation_ab}/messages",
                {"message_type": "text", "text_content": f"bob-{index}", "client_message_id": f"bob-{index}"},
                headers=bob_headers,
            )
            assert response.status == 201, response
        mark_responses = await asyncio.gather(
            *(
                asgi_request(
                    app,
                    "POST",
                    f"/api/v1/messages/conversations/{conversation_ab}/read",
                    headers=alice_headers,
                )
                for _ in range(5)
            )
        )
        assert all(response.status == 200 for response in mark_responses), mark_responses

        with get_connection() as connection:
            member = connection.execute(
                "SELECT unread_count FROM chat_conversation_members WHERE conversation_id = ? AND user_id = ?;",
                (conversation_ab, alice_id),
            ).fetchone()
            counter = connection.execute(
                "SELECT unread_direct_message_count FROM user_inbox_counters WHERE user_id = ?;",
                (alice_id,),
            ).fetchone()
        assert member["unread_count"] == 0
        assert counter["unread_direct_message_count"] == 0
        unread = await asgi_request(app, "GET", "/api/v1/messages/unread-counts", headers=alice_headers)
        assert unread.status == 200 and unread.json_body["unread_direct_message_count"] == 0, unread

        # Two conversations must retain independent unread counts.
        for index in range(3):
            response = await asgi_request(
                app,
                "POST",
                f"/api/v1/messages/conversations/{conversation_ac}/messages",
                {"message_type": "text", "text_content": f"carol-{index}", "client_message_id": f"carol-{index}"},
                headers=carol_headers,
            )
            assert response.status == 201, response
        for index in range(2):
            response = await asgi_request(
                app,
                "POST",
                f"/api/v1/messages/conversations/{conversation_ab}/messages",
                {"message_type": "text", "text_content": f"bob-again-{index}", "client_message_id": f"bob-again-{index}"},
                headers=bob_headers,
            )
            assert response.status == 201, response
        with get_connection() as connection:
            rows = connection.execute(
                "SELECT conversation_id, unread_count FROM chat_conversation_members WHERE user_id = ? AND status = 'active';",
                (alice_id,),
            ).fetchall()
            counter = connection.execute(
                "SELECT unread_direct_message_count FROM user_inbox_counters WHERE user_id = ?;",
                (alice_id,),
            ).fetchone()
        unread_by_conversation = {row["conversation_id"]: row["unread_count"] for row in rows}
        assert unread_by_conversation[conversation_ab] == 2
        assert unread_by_conversation[conversation_ac] == 3
        assert counter["unread_direct_message_count"] == 5
        unread = await asgi_request(app, "GET", "/api/v1/messages/unread-counts", headers=alice_headers)
        assert unread.json_body["unread_direct_message_count"] == 5, unread
        for _ in range(2):
            response = await asgi_request(
                app,
                "POST",
                f"/api/v1/messages/conversations/{conversation_ab}/read",
                headers=alice_headers,
            )
            assert response.status == 200, response
        with get_connection() as connection:
            rows = connection.execute(
                "SELECT conversation_id, unread_count FROM chat_conversation_members WHERE user_id = ? AND status = 'active';",
                (alice_id,),
            ).fetchall()
            counter = connection.execute(
                "SELECT unread_direct_message_count FROM user_inbox_counters WHERE user_id = ?;",
                (alice_id,),
            ).fetchone()
        unread_by_conversation = {row["conversation_id"]: row["unread_count"] for row in rows}
        assert unread_by_conversation[conversation_ab] == 0
        assert unread_by_conversation[conversation_ac] == 3
        assert counter["unread_direct_message_count"] == 3
        unread = await asgi_request(app, "GET", "/api/v1/messages/unread-counts", headers=alice_headers)
        assert unread.json_body["unread_direct_message_count"] == 3, unread

        # Concurrent retries with one client id must produce one message and one unread increment.
        same_id_responses = await asyncio.gather(
            *(
                asgi_request(
                    app,
                    "POST",
                    f"/api/v1/messages/conversations/{conversation_ab}/messages",
                    {
                        "message_type": "text",
                        "text_content": "same-client-id",
                        "client_message_id": "same-client-id",
                    },
                    headers=alice_headers,
                )
                for _ in range(5)
            )
        )
        assert all(response.status == 201 for response in same_id_responses), same_id_responses
        message_ids = {response.json_body["message"]["message_id"] for response in same_id_responses}
        assert len(message_ids) == 1, message_ids
        with get_connection() as connection:
            assert connection.execute(
                "SELECT COUNT(*) FROM chat_messages WHERE sender_user_id = ? AND client_message_id = ?;",
                (alice_id, "same-client-id"),
            ).fetchone()[0] == 1
            bob_member = connection.execute(
                "SELECT unread_count FROM chat_conversation_members WHERE conversation_id = ? AND user_id = ?;",
                (conversation_ab, bob_id),
            ).fetchone()
            bob_counter = connection.execute(
                "SELECT unread_direct_message_count FROM user_inbox_counters WHERE user_id = ?;",
                (bob_id,),
            ).fetchone()
        assert bob_member["unread_count"] == 1
        assert bob_counter["unread_direct_message_count"] == 1

        # Create several unread notifications through the messaging notification helper.
        baseline_notifications = await asgi_request(
            app, "GET", "/api/v1/notifications?unread_only=true", headers=alice_headers
        )
        assert baseline_notifications.status == 200, baseline_notifications
        baseline_unread_count = baseline_notifications.json_body["unread_count"]
        with transaction(immediate=True) as connection:
            for index in range(4):
                service.create_notification_in_transaction(
                    connection,
                    recipient_user_id=alice_id,
                    event_type="custom",
                    category="interaction",
                    actor_user_id=bob_id,
                    object_type="user",
                    object_id=bob_id,
                    title=f"Notification {index}",
                    dedup_key=f"message-regression-{index}",
                )
        notification_list = await asgi_request(app, "GET", "/api/v1/notifications?unread_only=true", headers=alice_headers)
        assert notification_list.status == 200, notification_list
        assert notification_list.json_body["unread_count"] == baseline_unread_count + 4, notification_list
        notification_ids = [
            item["user_notification_id"]
            for item in notification_list.json_body["items"]
            if item["notification_event_id"] not in {
                existing["notification_event_id"] for existing in baseline_notifications.json_body["items"]
            }
        ]
        assert len(notification_ids) == 4, notification_list
        read_responses = await asyncio.gather(
            *(
                asgi_request(app, "POST", f"/api/v1/notifications/{notification_id}/read", headers=alice_headers)
                for notification_id in notification_ids
            )
        )
        assert all(response.status == 200 for response in read_responses), read_responses
        with get_connection() as connection:
            unread_notifications = connection.execute(
                "SELECT COUNT(*) FROM user_notifications WHERE recipient_user_id = ? AND status = 'visible' AND read_at IS NULL AND deleted_at IS NULL;",
                (alice_id,),
            ).fetchone()[0]
            counter = connection.execute(
                "SELECT unread_notification_count FROM user_inbox_counters WHERE user_id = ?;",
                (alice_id,),
            ).fetchone()
        assert unread_notifications == baseline_unread_count
        assert counter["unread_notification_count"] == baseline_unread_count
        unread = await asgi_request(app, "GET", "/api/v1/messages/unread-counts", headers=alice_headers)
        assert unread.json_body["unread_notification_count"] == baseline_unread_count, unread

        with transaction(immediate=True) as connection:
            for index in range(3):
                service.create_notification_in_transaction(
                    connection,
                    recipient_user_id=alice_id,
                    event_type="custom",
                    category="interaction",
                    actor_user_id=carol_id,
                    object_type="user",
                    object_id=carol_id,
                    title=f"Bulk notification {index}",
                    dedup_key=f"message-regression-bulk-{index}",
                )
        marked_all = await asgi_request(app, "POST", "/api/v1/notifications/read-all", headers=alice_headers)
        assert marked_all.status == 200 and marked_all.json_body["marked_count"] == baseline_unread_count + 3, marked_all
        with get_connection() as connection:
            assert connection.execute(
                "SELECT COUNT(*) FROM user_notifications WHERE recipient_user_id = ? AND status = 'visible' AND read_at IS NULL AND deleted_at IS NULL;",
                (alice_id,),
            ).fetchone()[0] == 0
            assert connection.execute(
                "SELECT unread_notification_count FROM user_inbox_counters WHERE user_id = ?;",
                (alice_id,),
            ).fetchone()[0] == 0
        unread = await asgi_request(app, "GET", "/api/v1/messages/unread-counts", headers=alice_headers)
        assert unread.json_body["unread_notification_count"] == 0, unread

        # Concurrent request creation is protected by the pending-pair unique index.
        request_responses = await asyncio.gather(
            *(
                asgi_request(
                    app,
                    "POST",
                    "/api/v1/messages/requests",
                    {"target_user_id": bob_id, "request_message": "concurrent request"},
                    headers=carol_headers,
                )
                for _ in range(5)
            )
        )
        assert all(response.status == 201 for response in request_responses), request_responses
        request_ids = {response.json_body["request"]["message_request_id"] for response in request_responses}
        assert len(request_ids) == 1, request_ids
        with get_connection() as connection:
            assert connection.execute(
                "SELECT COUNT(*) FROM chat_message_requests WHERE requester_user_id = ? AND recipient_user_id = ? AND status = 'pending';",
                (carol_id, bob_id),
            ).fetchone()[0] == 1

        print("Message transaction regression test passed.")


if __name__ == "__main__":
    asyncio.run(main())
