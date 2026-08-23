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


async def follow(app, headers, target_id: str) -> None:
    response = await asgi_request(
        app,
        "POST",
        f"/api/v1/social/follows/{target_id}",
        {"source": "conversation-pin"},
        headers=headers,
    )
    assert response.status == 201, response


async def create_direct(app, headers, target_id: str) -> str:
    response = await asgi_request(
        app,
        "POST",
        "/api/v1/messages/direct-conversations",
        {"target_user_id": target_id},
        headers=headers,
    )
    assert response.status == 201, response
    return response.json_body["conversation"]["conversation_id"]


async def send_message(app, headers, conversation_id: str, text: str, client_id: str) -> dict:
    response = await asgi_request(
        app,
        "POST",
        f"/api/v1/messages/conversations/{conversation_id}/messages",
        {"message_type": "text", "text_content": text, "client_message_id": client_id},
        headers=headers,
    )
    assert response.status == 201, response
    return response.json_body["message"]


async def list_conversations(app, headers, page_size: int = 30, page: int = 1):
    return await asgi_request(
        app,
        "GET",
        f"/api/v1/messages/conversations?page={page}&page_size={page_size}",
        headers=headers,
    )


async def main() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        os.environ["TENNIS_DB_PATH"] = str(Path(temp_dir) / "message_conversation_pin.sqlite3")

        from backend.app.core.database import get_connection, initialize_database
        from backend.app.main import app

        initialize_database()
        users = [
            await login_phone(app, phone)
            for phone in ("13943300001", "13943300002", "13943300003", "13943300004", "13943300005")
        ]
        (alice_token, alice_id), (bob_token, bob_id), (carol_token, carol_id), (dave_token, dave_id), (erin_token, erin_id) = users
        alice_headers = {"authorization": f"Bearer {alice_token}"}
        bob_headers = {"authorization": f"Bearer {bob_token}"}
        carol_headers = {"authorization": f"Bearer {carol_token}"}
        dave_headers = {"authorization": f"Bearer {dave_token}"}
        erin_headers = {"authorization": f"Bearer {erin_token}"}

        for target_id, headers in (
            (bob_id, alice_headers),
            (alice_id, bob_headers),
            (carol_id, alice_headers),
            (alice_id, carol_headers),
            (dave_id, alice_headers),
            (alice_id, dave_headers),
            (erin_id, alice_headers),
            (alice_id, erin_headers),
        ):
            await follow(app, headers, target_id)

        conversation_x = await create_direct(app, alice_headers, bob_id)
        conversation_y = await create_direct(app, alice_headers, carol_id)
        conversation_z = await create_direct(app, alice_headers, dave_id)
        conversation_w = await create_direct(app, alice_headers, erin_id)

        # Make X old, Y newer, and Z newest. W stays empty to preserve null recency behavior.
        await send_message(app, alice_headers, conversation_x, "old X", "pin-x")
        await send_message(app, bob_headers, conversation_x, "unread reply", "pin-x-unread")
        await asyncio.sleep(1.05)
        await send_message(app, alice_headers, conversation_y, "new Y", "pin-y")
        await asyncio.sleep(1.05)
        await send_message(app, alice_headers, conversation_z, "newest Z", "pin-z")

        initial = await list_conversations(app, alice_headers, page_size=4)
        assert initial.status == 200, initial
        initial_ids = [item["conversation"]["conversation_id"] for item in initial.json_body["items"]]
        assert initial_ids[:3] == [conversation_z, conversation_y, conversation_x], initial_ids
        assert all(item["member"]["pinned_at"] is None for item in initial.json_body["items"])

        pin_x = await asgi_request(
            app, "POST", f"/api/v1/messages/conversations/{conversation_x}/pin", headers=alice_headers
        )
        assert pin_x.status == 200 and pin_x.json_body["pinned_at"], pin_x
        first_pinned_at = pin_x.json_body["pinned_at"]
        repeated_pin = await asgi_request(
            app, "POST", f"/api/v1/messages/conversations/{conversation_x}/pin", headers=alice_headers
        )
        assert repeated_pin.status == 200, repeated_pin
        assert repeated_pin.json_body["pinned_at"] == first_pinned_at, repeated_pin

        # A pinned conversation from the old page must move before the unpinned bucket.
        first_page = await list_conversations(app, alice_headers, page_size=2)
        assert first_page.status == 200, first_page
        assert [item["conversation"]["conversation_id"] for item in first_page.json_body["items"]] == [
            conversation_x,
            conversation_z,
        ], first_page

        # Pin ordering inside the pinned bucket keeps activity recency ordering.
        pin_y = await asgi_request(
            app, "POST", f"/api/v1/messages/conversations/{conversation_y}/pin", headers=alice_headers
        )
        assert pin_y.status == 200, pin_y
        pinned_page = await list_conversations(app, alice_headers, page_size=2)
        assert [item["conversation"]["conversation_id"] for item in pinned_page.json_body["items"]] == [
            conversation_y,
            conversation_x,
        ], pinned_page

        # Pin is isolated to the authenticated member's row.
        bob_view = await list_conversations(app, bob_headers)
        assert bob_view.status == 200, bob_view
        bob_item = next(item for item in bob_view.json_body["items"] if item["conversation"]["conversation_id"] == conversation_x)
        assert bob_item["member"]["pinned_at"] is None, bob_item

        with get_connection() as connection:
            alice_member_before = connection.execute(
                "SELECT unread_count, last_read_message_seq FROM chat_conversation_members WHERE conversation_id = ? AND user_id = ?;",
                (conversation_x, alice_id),
            ).fetchone()

        # Existing block state is independent from pin state.
        blocked = await asgi_request(
            app,
            "POST",
            f"/api/v1/social/blocks/{bob_id}",
            {"reason": "pin-independence"},
            headers=alice_headers,
        )
        assert blocked.status == 201, blocked
        pin_blocked = await asgi_request(
            app, "POST", f"/api/v1/messages/conversations/{conversation_x}/pin", headers=alice_headers
        )
        assert pin_blocked.status == 200, pin_blocked
        unpin_blocked = await asgi_request(
            app, "DELETE", f"/api/v1/messages/conversations/{conversation_x}/pin", headers=alice_headers
        )
        assert unpin_blocked.status == 200 and unpin_blocked.json_body["pinned_at"] is None, unpin_blocked
        with get_connection() as connection:
            alice_member_after = connection.execute(
                "SELECT unread_count, last_read_message_seq FROM chat_conversation_members WHERE conversation_id = ? AND user_id = ?;",
                (conversation_x, alice_id),
            ).fetchone()
        assert tuple(alice_member_after) == tuple(alice_member_before)

        repeated_unpin = await asgi_request(
            app, "DELETE", f"/api/v1/messages/conversations/{conversation_x}/pin", headers=alice_headers
        )
        assert repeated_unpin.status == 200 and repeated_unpin.json_body["pinned_at"] is None, repeated_unpin

        unauthorized = await asgi_request(
            app, "POST", f"/api/v1/messages/conversations/{conversation_x}/pin", headers=carol_headers
        )
        assert unauthorized.status in {403, 404}, unauthorized

        restored = await asgi_request(
            app, "DELETE", f"/api/v1/social/blocks/{bob_id}", headers=alice_headers
        )
        assert restored.status == 200, restored

        # W is still empty and remains in the unpinned bucket according to existing null ordering.
        final_page = await list_conversations(app, alice_headers, page_size=10)
        assert final_page.status == 200, final_page
        final_items = final_page.json_body["items"]
        x_item = next(item for item in final_items if item["conversation"]["conversation_id"] == conversation_x)
        w_item = next(item for item in final_items if item["conversation"]["conversation_id"] == conversation_w)
        assert x_item["member"]["pinned_at"] is None
        assert w_item["member"]["pinned_at"] is None

        print("Message conversation pin API test passed.")


if __name__ == "__main__":
    asyncio.run(main())
