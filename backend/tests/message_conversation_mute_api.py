from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
import os
from pathlib import Path
import sys
import tempfile


ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT_DIR))

from backend.app.core.time import to_iso, utc_now
from backend.tests.activity_detail_api_smoke import login_phone
from backend.tests.auth_api_smoke import asgi_request


async def follow(app, headers: dict[str, str], target_id: str) -> None:
    response = await asgi_request(app, "POST", f"/api/v1/social/follows/{target_id}", headers=headers)
    assert response.status == 201, response


async def conversations(app, headers: dict[str, str]) -> list[dict]:
    response = await asgi_request(app, "GET", "/api/v1/messages/conversations", headers=headers)
    assert response.status == 200, response
    return response.json_body["items"]


async def main() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        os.environ["TENNIS_DB_PATH"] = str(Path(temp_dir) / "message_conversation_mute.sqlite3")

        from backend.app.core.database import get_connection, initialize_database
        from backend.app.main import app
        from backend.app.messages import service

        initialize_database()
        (alice_token, alice_id), (bob_token, bob_id), (carol_token, _) = [
            await login_phone(app, phone) for phone in ("13943400001", "13943400002", "13943400003")
        ]
        alice_headers = {"authorization": f"Bearer {alice_token}"}
        bob_headers = {"authorization": f"Bearer {bob_token}"}
        carol_headers = {"authorization": f"Bearer {carol_token}"}
        await follow(app, alice_headers, bob_id)
        await follow(app, bob_headers, alice_id)

        created = await asgi_request(
            app,
            "POST",
            "/api/v1/messages/direct-conversations",
            {"target_user_id": bob_id},
            headers=alice_headers,
        )
        assert created.status == 201, created
        conversation_id = created.json_body["conversation"]["conversation_id"]
        initial_bob = next(
            item for item in await conversations(app, bob_headers)
            if item["conversation"]["conversation_id"] == conversation_id
        )
        assert initial_bob["member"]["muted_until"] is None
        assert initial_bob["member"]["is_muted"] is False

        # A's preference is isolated from B and is an exact 24-hour server-created period.
        before_mute = datetime.now(UTC)
        alice_mute = await asgi_request(
            app, "POST", f"/api/v1/messages/conversations/{conversation_id}/mute", headers=alice_headers
        )
        assert alice_mute.status == 200, alice_mute
        alice_expiry = datetime.fromisoformat(alice_mute.json_body["muted_until"].replace("Z", "+00:00"))
        assert timedelta(hours=23, minutes=59, seconds=57) <= alice_expiry - before_mute <= timedelta(hours=24, seconds=3)
        assert alice_mute.json_body["is_muted"] is True
        assert next(
            item for item in await conversations(app, bob_headers)
            if item["conversation"]["conversation_id"] == conversation_id
        )["member"]["is_muted"] is False

        repeated_alice_mute = await asgi_request(
            app, "POST", f"/api/v1/messages/conversations/{conversation_id}/mute", headers=alice_headers
        )
        assert repeated_alice_mute.status == 200
        assert repeated_alice_mute.json_body["muted_until"] == alice_mute.json_body["muted_until"]

        # B's mute controls only B's future Direct Message Push eligibility.
        bob_mute = await asgi_request(
            app, "POST", f"/api/v1/messages/conversations/{conversation_id}/mute", headers=bob_headers
        )
        assert bob_mute.status == 200 and bob_mute.json_body["is_muted"] is True
        unread_before = (
            await asgi_request(app, "GET", "/api/v1/messages/unread-counts", headers=bob_headers)
        ).json_body
        sent_while_muted = await asgi_request(
            app,
            "POST",
            f"/api/v1/messages/conversations/{conversation_id}/messages",
            {"message_type": "text", "text_content": "still delivered", "client_message_id": "mute-delivered"},
            headers=alice_headers,
        )
        assert sent_while_muted.status == 201, sent_while_muted
        message_id = sent_while_muted.json_body["message"]["message_id"]
        unread_after = (
            await asgi_request(app, "GET", "/api/v1/messages/unread-counts", headers=bob_headers)
        ).json_body
        assert unread_after["unread_direct_message_count"] == unread_before["unread_direct_message_count"] + 1
        assert unread_after["messages_tab_badge_count"] == unread_before["messages_tab_badge_count"] + 1
        assert service.build_direct_message_push_intent(bob_id, message_id).decision == "suppressed_by_conversation_mute"

        marked = await asgi_request(
            app,
            "POST",
            f"/api/v1/messages/conversations/{conversation_id}/read",
            {"through_message_seq": sent_while_muted.json_body["message"]["message_seq"]},
            headers=bob_headers,
        )
        assert marked.status == 200 and marked.json_body["unread_count"] == 0

        pinned = await asgi_request(
            app, "POST", f"/api/v1/messages/conversations/{conversation_id}/pin", headers=bob_headers
        )
        assert pinned.status == 200 and pinned.json_body["pinned_at"]
        unmuted = await asgi_request(
            app, "DELETE", f"/api/v1/messages/conversations/{conversation_id}/mute", headers=bob_headers
        )
        assert unmuted.status == 200 and unmuted.json_body["muted_until"] is None and not unmuted.json_body["is_muted"]
        repeated_unmute = await asgi_request(
            app, "DELETE", f"/api/v1/messages/conversations/{conversation_id}/mute", headers=bob_headers
        )
        assert repeated_unmute.status == 200 and repeated_unmute.json_body["muted_until"] is None
        bob_member_after_unmute = next(
            item for item in await conversations(app, bob_headers)
            if item["conversation"]["conversation_id"] == conversation_id
        )["member"]
        assert bob_member_after_unmute["pinned_at"] == pinned.json_body["pinned_at"]

        # Block state and mute state remain independent for an active member.
        blocked = await asgi_request(app, "POST", f"/api/v1/social/blocks/{alice_id}", headers=bob_headers)
        assert blocked.status == 201, blocked
        muted_while_blocked = await asgi_request(
            app, "POST", f"/api/v1/messages/conversations/{conversation_id}/mute", headers=bob_headers
        )
        assert muted_while_blocked.status == 200 and muted_while_blocked.json_body["is_muted"] is True

        global_off = await asgi_request(
            app,
            "PATCH",
            "/api/v1/notifications/preferences",
            {"direct_message_notifications": False},
            headers=bob_headers,
        )
        assert global_off.status == 200
        assert service.build_direct_message_push_intent(bob_id, message_id).decision == "suppressed_by_preference"
        global_on = await asgi_request(
            app,
            "PATCH",
            "/api/v1/notifications/preferences",
            {"direct_message_notifications": True},
            headers=bob_headers,
        )
        assert global_on.status == 200
        assert service.build_direct_message_push_intent(bob_id, message_id).decision == "suppressed_by_conversation_mute"

        # Expiry is evaluated lazily by the server. A subsequent mute starts a new period.
        with get_connection() as connection:
            connection.execute(
                """
                UPDATE chat_conversation_members
                SET muted_until = ?
                WHERE conversation_id = ? AND user_id = ?;
                """,
                (to_iso(utc_now() - timedelta(seconds=1)), conversation_id, bob_id),
            )
            connection.commit()
        expired_member = next(
            item for item in await conversations(app, bob_headers)
            if item["conversation"]["conversation_id"] == conversation_id
        )["member"]
        assert expired_member["muted_until"] is not None and expired_member["is_muted"] is False
        assert service.build_direct_message_push_intent(bob_id, message_id).decision == "eligible"
        remuted = await asgi_request(
            app, "POST", f"/api/v1/messages/conversations/{conversation_id}/mute", headers=bob_headers
        )
        assert remuted.status == 200 and remuted.json_body["is_muted"] is True
        assert remuted.json_body["muted_until"] != expired_member["muted_until"]

        # Conversation mute is deliberately narrower than Message Request Push.
        message_request = await asgi_request(
            app,
            "POST",
            "/api/v1/messages/requests",
            {"target_user_id": bob_id, "request_message": "request remains independent"},
            headers=carol_headers,
        )
        assert message_request.status == 201, message_request
        request_id = message_request.json_body["request"]["message_request_id"]
        assert service.build_message_request_push_intent(bob_id, request_id).decision == "eligible"

        unauthorized = await asgi_request(
            app, "POST", f"/api/v1/messages/conversations/{conversation_id}/mute", headers=carol_headers
        )
        assert unauthorized.status in {403, 404}, unauthorized

        print("Message conversation mute API test passed.")


if __name__ == "__main__":
    asyncio.run(main())
