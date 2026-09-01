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
        os.environ.pop("TENNIS_DATABASE_URL", None)
        os.environ.pop("TENNIS_POSTGRES_DSN", None)
        os.environ["TENNIS_DB_PATH"] = str(Path(temp_dir) / "message_sync_api.sqlite3")

        from backend.app.core.database import get_connection, initialize_sqlite_database
        from backend.app.main import app
        from backend.app.messages import sync as sync_service

        initialize_sqlite_database()
        initialize_sqlite_database()

        (alice_token, alice_id), (bob_token, bob_id), (carol_token, carol_id) = await asyncio.gather(
            login_phone(app, "13970000001"),
            login_phone(app, "13970000002"),
            login_phone(app, "13970000003"),
        )
        alice_headers = {"authorization": f"Bearer {alice_token}"}
        bob_headers = {"authorization": f"Bearer {bob_token}"}
        carol_headers = {"authorization": f"Bearer {carol_token}"}

        alice_device_id = "device-alice-primary"
        bob_device_id = "device-bob-primary"
        carol_device_id = "device-carol-primary"
        alice_device_responses = await asyncio.gather(
            *(
                asgi_request(
                    app,
                    "POST",
                    "/api/v1/messages/devices",
                    {"device_id": alice_device_id, "platform": "unknown", "app_version": "11b-test"},
                    headers=alice_headers,
                )
                for _ in range(5)
            )
        )
        assert all(response.status == 200 for response in alice_device_responses), alice_device_responses
        assert {response.json_body["device"]["device_id"] for response in alice_device_responses} == {alice_device_id}
        bob_device = await asgi_request(
            app,
            "POST",
            "/api/v1/messages/devices",
            {"device_id": bob_device_id, "platform": "unknown"},
            headers=bob_headers,
        )
        assert bob_device.status == 200, bob_device
        carol_device = await asgi_request(
            app,
            "POST",
            "/api/v1/messages/devices",
            {"device_id": carol_device_id, "platform": "unknown"},
            headers=carol_headers,
        )
        assert carol_device.status == 200, carol_device

        ownership_conflict = await asgi_request(
            app,
            "POST",
            "/api/v1/messages/devices",
            {"device_id": alice_device_id, "platform": "unknown"},
            headers=bob_headers,
        )
        assert ownership_conflict.status == 409
        assert ownership_conflict.json_body["detail"]["code"] == "MESSAGING_DEVICE_OWNERSHIP_CONFLICT"
        device_update = await asgi_request(
            app,
            "PATCH",
            f"/api/v1/messages/devices/{alice_device_id}",
            {"platform": "web", "app_version": "11b-updated"},
            headers=alice_headers,
        )
        assert device_update.status == 200, device_update
        assert device_update.json_body["device"]["platform"] == "web"
        foreign_device_update = await asgi_request(
            app,
            "PATCH",
            f"/api/v1/messages/devices/{alice_device_id}",
            {"platform": "web"},
            headers=bob_headers,
        )
        assert foreign_device_update.status == 404
        foreign_device_sync = await asgi_request(
            app,
            "GET",
            f"/api/v1/messages/sync?device_id={alice_device_id}&limit=10",
            headers=bob_headers,
        )
        assert foreign_device_sync.status == 404

        initial_sync = await asgi_request(
            app,
            "GET",
            f"/api/v1/messages/sync?device_id={alice_device_id}&limit=10",
            headers=alice_headers,
        )
        assert initial_sync.status == 200, initial_sync
        assert initial_sync.json_body["items"] == []
        assert initial_sync.json_body["cursor_status"] == "initial"

        group = await asgi_request(
            app,
            "POST",
            "/api/v1/messages/groups",
            {"member_user_ids": [bob_id, carol_id], "title": "Sync test group", "group_type": "custom"},
            headers=alice_headers,
        )
        assert group.status == 201, group
        conversation_id = group.json_body["conversation"]["conversation_id"]

        first_message = await asgi_request(
            app,
            "POST",
            f"/api/v1/messages/conversations/{conversation_id}/messages",
            {"message_type": "text", "text_content": "sync body must stay private", "client_message_id": "sync-1"},
            headers=alice_headers,
        )
        assert first_message.status == 201, first_message
        first_event_id = first_message.json_body["event_id"]

        alice_sync = await asgi_request(
            app,
            "GET",
            f"/api/v1/messages/sync?device_id={alice_device_id}&limit=1",
            headers=alice_headers,
        )
        assert alice_sync.status == 200, alice_sync
        assert len(alice_sync.json_body["items"]) == 1
        assert alice_sync.json_body["items"][0]["event_id"] == first_event_id
        assert alice_sync.json_body["items"][0]["recipient_user_id"] == alice_id
        assert "sync body must stay private" not in str(alice_sync.json_body)
        assert alice_sync.json_body["next_cursor"]

        checkpoint = await asgi_request(
            app,
            "POST",
            "/api/v1/messages/sync/checkpoints",
            {"device_id": alice_device_id, "cursor": alice_sync.json_body["next_cursor"]},
            headers=alice_headers,
        )
        assert checkpoint.status == 200, checkpoint

        bob_sync = await asgi_request(
            app,
            "GET",
            f"/api/v1/messages/sync?device_id={bob_device_id}&limit=10",
            headers=bob_headers,
        )
        assert bob_sync.status == 200, bob_sync
        assert [item["event_id"] for item in bob_sync.json_body["items"]] == [first_event_id]
        assert all(item["recipient_user_id"] == bob_id for item in bob_sync.json_body["items"])

        second_alice_device = await asgi_request(
            app,
            "POST",
            "/api/v1/messages/devices",
            {"device_id": "device-alice-secondary", "platform": "unknown"},
            headers=alice_headers,
        )
        assert second_alice_device.status == 200, second_alice_device
        second_device_sync = await asgi_request(
            app,
            "GET",
            "/api/v1/messages/sync?device_id=device-alice-secondary&limit=10",
            headers=alice_headers,
        )
        assert second_device_sync.status == 200, second_device_sync
        assert [item["event_id"] for item in second_device_sync.json_body["items"]] == [first_event_id]

        for index in range(3):
            response = await asgi_request(
                app,
                "POST",
                f"/api/v1/messages/conversations/{conversation_id}/messages",
                {
                    "message_type": "text",
                    "text_content": f"page-{index}",
                    "client_message_id": f"sync-page-{index}",
                },
                headers=bob_headers,
            )
            assert response.status == 201, response

        page_one = await asgi_request(
            app,
            "GET",
            f"/api/v1/messages/sync?device_id=device-alice-secondary&limit=1",
            headers=alice_headers,
        )
        assert page_one.status == 200, page_one
        assert page_one.json_body["has_more"] is True
        page_two = await asgi_request(
            app,
            "GET",
            f"/api/v1/messages/sync?device_id=device-alice-secondary&limit=10&cursor={page_one.json_body['next_cursor']}",
            headers=alice_headers,
        )
        assert page_two.status == 200, page_two
        assert page_two.json_body["items"]
        assert page_two.json_body["items"][0]["event_id"] != page_one.json_body["items"][0]["event_id"]
        latest_checkpoint = await asgi_request(
            app,
            "POST",
            "/api/v1/messages/sync/checkpoints",
            {"device_id": "device-alice-secondary", "cursor": page_two.json_body["next_cursor"]},
            headers=alice_headers,
        )
        assert latest_checkpoint.status == 200, latest_checkpoint
        backward_checkpoint = await asgi_request(
            app,
            "POST",
            "/api/v1/messages/sync/checkpoints",
            {"device_id": "device-alice-secondary", "cursor": page_one.json_body["next_cursor"]},
            headers=alice_headers,
        )
        assert backward_checkpoint.status == 200, backward_checkpoint
        assert backward_checkpoint.json_body["cursor"] == latest_checkpoint.json_body["cursor"]
        foreign_device_cursor = await asgi_request(
            app,
            "GET",
            f"/api/v1/messages/sync?device_id=device-alice-secondary&cursor={alice_sync.json_body['next_cursor']}&limit=10",
            headers=alice_headers,
        )
        assert foreign_device_cursor.status == 400
        assert foreign_device_cursor.json_body["detail"]["code"] == "SYNC_CURSOR_INVALID"

        invalid_cursor = await asgi_request(
            app,
            "GET",
            f"/api/v1/messages/sync?device_id={alice_device_id}&cursor=not-a-cursor&limit=10",
            headers=alice_headers,
        )
        assert invalid_cursor.status == 400
        assert invalid_cursor.json_body["detail"]["code"] == "SYNC_CURSOR_INVALID"
        foreign_cursor = await asgi_request(
            app,
            "GET",
            f"/api/v1/messages/sync?device_id={bob_device_id}&cursor={alice_sync.json_body['next_cursor']}&limit=10",
            headers=bob_headers,
        )
        assert foreign_cursor.status == 400
        assert foreign_cursor.json_body["detail"]["code"] == "SYNC_CURSOR_INVALID"

        with get_connection() as connection:
            carol_member = connection.execute(
                "SELECT conversation_member_id FROM chat_conversation_members WHERE conversation_id = ? AND user_id = ?;",
                (conversation_id, carol_id),
            ).fetchone()
            connection.execute(
                "UPDATE chat_conversation_members SET status = 'left', left_at = CURRENT_TIMESTAMP WHERE conversation_member_id = ?;",
                (carol_member["conversation_member_id"],),
            )
            connection.commit()
        carol_after_leave = await asgi_request(
            app,
            "GET",
            f"/api/v1/messages/sync?device_id={carol_device_id}&limit=10",
            headers=carol_headers,
        )
        assert carol_after_leave.status == 200, carol_after_leave
        assert carol_after_leave.json_body["items"] == []

        read = await asgi_request(
            app,
            "POST",
            f"/api/v1/messages/conversations/{conversation_id}/read",
            {"through_message_seq": 4},
            headers=alice_headers,
        )
        assert read.status == 200, read
        for headers, target_id in ((alice_headers, bob_id), (bob_headers, alice_id)):
            followed = await asgi_request(
                app,
                "POST",
                f"/api/v1/social/follows/{target_id}",
                {"source": "sync-hardening"},
                headers=headers,
            )
            assert followed.status in (200, 201), followed
        direct = await asgi_request(
            app,
            "POST",
            "/api/v1/messages/direct-conversations",
            {"target_user_id": bob_id},
            headers=alice_headers,
        )
        assert direct.status == 201, direct
        direct_message = await asgi_request(
            app,
            "POST",
            f"/api/v1/messages/conversations/{direct.json_body['conversation']['conversation_id']}/messages",
            {"message_type": "text", "text_content": "direct event stays private", "client_message_id": "sync-direct"},
            headers=alice_headers,
        )
        assert direct_message.status == 201, direct_message
        direct_event_id = direct_message.json_body["event_id"]
        recalled = await asgi_request(
            app,
            "POST",
            f"/api/v1/messages/conversations/{direct.json_body['conversation']['conversation_id']}/messages/{direct_message.json_body['message']['message_id']}/recall",
            headers=alice_headers,
        )
        assert recalled.status == 200, recalled
        event_types = {
            item["event_type"]
            for item in (
                await asgi_request(
                    app,
                    "GET",
                    "/api/v1/messages/sync?device_id=device-alice-secondary&limit=100",
                    headers=alice_headers,
                )
            ).json_body["items"]
        }
        assert {"message.created", "message.recalled", "conversation.read"}.issubset(event_types)
        for blocker_headers, target_id in ((alice_headers, bob_id), (bob_headers, alice_id)):
            blocked = await asgi_request(app, "POST", f"/api/v1/social/blocks/{target_id}", headers=blocker_headers)
            assert blocked.status == 201, blocked
            blocked_sync = await asgi_request(
                app,
                "GET",
                "/api/v1/messages/sync?device_id=device-alice-secondary&limit=100",
                headers=alice_headers,
            )
            assert direct_event_id not in {item["event_id"] for item in blocked_sync.json_body["items"]}
            unblocked = await asgi_request(app, "DELETE", f"/api/v1/social/blocks/{target_id}", headers=blocker_headers)
            assert unblocked.status == 200, unblocked

        revoked = await asgi_request(
            app,
            "DELETE",
            f"/api/v1/messages/devices/{alice_device_id}",
            headers=alice_headers,
        )
        assert revoked.status == 200, revoked
        assert revoked.json_body["device"]["revoked_at"] is not None
        revoked_sync = await asgi_request(
            app,
            "GET",
            f"/api/v1/messages/sync?device_id={alice_device_id}&limit=10",
            headers=alice_headers,
        )
        assert revoked_sync.status == 403
        assert revoked_sync.json_body["detail"]["code"] == "MESSAGING_DEVICE_REVOKED"
        revoked_checkpoint = await asgi_request(
            app,
            "POST",
            "/api/v1/messages/sync/checkpoints",
            {"device_id": alice_device_id, "cursor": alice_sync.json_body["next_cursor"]},
            headers=alice_headers,
        )
        assert revoked_checkpoint.status == 403

        with get_connection() as connection:
            known_event = connection.execute(
                "SELECT event_id FROM user_sync_events WHERE recipient_user_id = ? LIMIT 1;",
                (alice_id,),
            ).fetchone()["event_id"]
        expired_cursor = sync_service._encode_cursor(
            alice_id,
            "device-alice-secondary",
            "2000-01-01T00:00:00Z",
            known_event,
        )
        expired = await asgi_request(
            app,
            "GET",
            f"/api/v1/messages/sync?device_id=device-alice-secondary&cursor={expired_cursor}&limit=10",
            headers=alice_headers,
        )
        assert expired.status == 409, expired
        assert expired.json_body["detail"]["code"] == "SYNC_CURSOR_EXPIRED"
        assert expired.json_body["detail"]["requires_full_reconciliation"] is True

        before_rollback = None
        with get_connection() as connection:
            before_rollback = connection.execute(
                "SELECT COUNT(*) FROM chat_messages WHERE conversation_id = ?;", (conversation_id,)
            ).fetchone()[0]
        original_append = sync_service.append_conversation_event

        def fail_sync_event(*_: object, **__: object) -> None:
            raise RuntimeError("sync event failure injection")

        sync_service.append_conversation_event = fail_sync_event
        try:
            rollback_response = await asgi_request(
                app,
                "POST",
                f"/api/v1/messages/conversations/{conversation_id}/messages",
                {"message_type": "text", "text_content": "must rollback", "client_message_id": "sync-rollback"},
                headers=alice_headers,
            )
            assert rollback_response.status == 500, rollback_response
        finally:
            sync_service.append_conversation_event = original_append
        with get_connection() as connection:
            assert connection.execute(
                "SELECT COUNT(*) FROM chat_messages WHERE conversation_id = ?;", (conversation_id,)
            ).fetchone()[0] == before_rollback
            assert connection.execute(
                "SELECT COUNT(*) FROM outbox_events WHERE message_id IN (SELECT message_id FROM chat_messages WHERE client_message_id = ?);",
                ("sync-rollback",),
            ).fetchone()[0] == 0

        print("Message sync API test passed.")


if __name__ == "__main__":
    asyncio.run(main())
