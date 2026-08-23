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


async def list_conversations(app, headers: dict[str, str]) -> list[dict]:
    response = await asgi_request(app, "GET", "/api/v1/messages/conversations?page_size=30", headers=headers)
    assert response.status == 200, response
    return response.json_body["items"]


async def send(app, headers: dict[str, str], conversation_id: str, client_message_id: str) -> dict:
    response = await asgi_request(
        app,
        "POST",
        f"/api/v1/messages/conversations/{conversation_id}/messages",
        {"message_type": "text", "text_content": client_message_id, "client_message_id": client_message_id},
        headers=headers,
    )
    assert response.status == 201, response
    return response.json_body["message"]


async def main() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        os.environ["TENNIS_DB_PATH"] = str(Path(temp_dir) / "message_conversation_hide.sqlite3")

        from backend.app.core.database import get_connection, initialize_database
        from backend.app.main import app
        from backend.app.messages import service

        initialize_database()

        def archived_at(conversation_id: str, user_id: str) -> str | None:
            with get_connection() as connection:
                row = connection.execute(
                    "SELECT archived_at FROM chat_conversation_members WHERE conversation_id = ? AND user_id = ?;",
                    (conversation_id, user_id),
                ).fetchone()
            return row["archived_at"]

        (alice_token, alice_id), (bob_token, bob_id), (carol_token, _) = [
            await login_phone(app, phone) for phone in ("13943500001", "13943500002", "13943500003")
        ]
        alice_headers = {"authorization": f"Bearer {alice_token}"}
        bob_headers = {"authorization": f"Bearer {bob_token}"}
        carol_headers = {"authorization": f"Bearer {carol_token}"}
        for headers, target_id in ((alice_headers, bob_id), (bob_headers, alice_id)):
            followed = await asgi_request(app, "POST", f"/api/v1/social/follows/{target_id}", headers=headers)
            assert followed.status == 201, followed

        created = await asgi_request(
            app,
            "POST",
            "/api/v1/messages/direct-conversations",
            {"target_user_id": bob_id},
            headers=alice_headers,
        )
        assert created.status == 201, created
        conversation_id = created.json_body["conversation"]["conversation_id"]
        assert archived_at(conversation_id, bob_id) is None

        first_message = await send(app, alice_headers, conversation_id, "hide-initial")
        pinned = await asgi_request(app, "POST", f"/api/v1/messages/conversations/{conversation_id}/pin", headers=bob_headers)
        muted = await asgi_request(app, "POST", f"/api/v1/messages/conversations/{conversation_id}/mute", headers=bob_headers)
        assert pinned.status == muted.status == 200
        before_hide = next(item for item in await list_conversations(app, bob_headers) if item["conversation"]["conversation_id"] == conversation_id)["member"]
        badge_before_hide = (await asgi_request(app, "GET", "/api/v1/messages/unread-counts", headers=bob_headers)).json_body

        hidden = await asgi_request(app, "POST", f"/api/v1/messages/conversations/{conversation_id}/hide", headers=bob_headers)
        assert hidden.status == 200 and hidden.json_body["is_hidden"] is True and hidden.json_body["archived_at"]
        first_archived_at = hidden.json_body["archived_at"]
        assert conversation_id not in {item["conversation"]["conversation_id"] for item in await list_conversations(app, bob_headers)}
        assert conversation_id in {item["conversation"]["conversation_id"] for item in await list_conversations(app, alice_headers)}
        with get_connection() as connection:
            hidden_member = connection.execute(
                """
                SELECT unread_count, last_read_message_seq, pinned_at, muted_until
                FROM chat_conversation_members
                WHERE conversation_id = ? AND user_id = ?;
                """,
                (conversation_id, bob_id),
            ).fetchone()
        assert hidden_member["unread_count"] == before_hide["unread_count"]
        assert hidden_member["last_read_message_seq"] == before_hide["last_read_message_seq"]
        assert hidden_member["pinned_at"] == pinned.json_body["pinned_at"]
        assert hidden_member["muted_until"] == muted.json_body["muted_until"]
        assert (await asgi_request(app, "GET", "/api/v1/messages/unread-counts", headers=bob_headers)).json_body == badge_before_hide

        repeated_hide = await asgi_request(app, "POST", f"/api/v1/messages/conversations/{conversation_id}/hide", headers=bob_headers)
        assert repeated_hide.status == 200 and repeated_hide.json_body["archived_at"] == first_archived_at
        history = await asgi_request(app, "GET", f"/api/v1/messages/conversations/{conversation_id}/messages", headers=bob_headers)
        assert history.status == 200 and history.json_body["items"][0]["message_id"] == first_message["message_id"]
        assert archived_at(conversation_id, bob_id) == first_archived_at
        marked = await asgi_request(
            app,
            "POST",
            f"/api/v1/messages/conversations/{conversation_id}/read",
            {"through_message_seq": first_message["message_seq"]},
            headers=bob_headers,
        )
        assert marked.status == 200 and archived_at(conversation_id, bob_id) == first_archived_at

        restored = await asgi_request(app, "DELETE", f"/api/v1/messages/conversations/{conversation_id}/hide", headers=bob_headers)
        assert restored.status == 200 and restored.json_body == {
            "success": True,
            "conversation_id": conversation_id,
            "archived_at": None,
            "is_hidden": False,
        }
        repeated_unhide = await asgi_request(app, "DELETE", f"/api/v1/messages/conversations/{conversation_id}/hide", headers=bob_headers)
        assert repeated_unhide.status == 200 and repeated_unhide.json_body["archived_at"] is None
        restored_member = next(item for item in await list_conversations(app, bob_headers) if item["conversation"]["conversation_id"] == conversation_id)["member"]
        assert restored_member["pinned_at"] == pinned.json_body["pinned_at"]
        assert restored_member["muted_until"] == muted.json_body["muted_until"] and restored_member["is_muted"] is True
        assert restored_member["last_read_message_seq"] == before_hide["last_read_message_seq"] + 1

        # Block and Hide are independent; blocked sends do not restore visibility.
        blocked = await asgi_request(app, "POST", f"/api/v1/social/blocks/{alice_id}", headers=bob_headers)
        assert blocked.status == 201
        blocked_hide = await asgi_request(app, "POST", f"/api/v1/messages/conversations/{conversation_id}/hide", headers=bob_headers)
        assert blocked_hide.status == 200 and blocked_hide.json_body["is_hidden"] is True
        blocked_send = await asgi_request(
            app,
            "POST",
            f"/api/v1/messages/conversations/{conversation_id}/messages",
            {"message_type": "text", "text_content": "blocked", "client_message_id": "hide-blocked"},
            headers=alice_headers,
        )
        assert blocked_send.status == 403 and archived_at(conversation_id, bob_id) is not None
        assert (await asgi_request(app, "DELETE", f"/api/v1/social/blocks/{alice_id}", headers=bob_headers)).status == 200

        # A real incoming message restores B while retaining Pin, Mute, unread, and Push semantics.
        badge_before_incoming = (await asgi_request(app, "GET", "/api/v1/messages/unread-counts", headers=bob_headers)).json_body
        incoming = await send(app, alice_headers, conversation_id, "hide-incoming-new")
        assert archived_at(conversation_id, bob_id) is None
        bob_visible = next(item for item in await list_conversations(app, bob_headers) if item["conversation"]["conversation_id"] == conversation_id)["member"]
        assert bob_visible["pinned_at"] == pinned.json_body["pinned_at"] and bob_visible["is_muted"] is True
        assert bob_visible["unread_count"] == 1
        badge_after_incoming = (await asgi_request(app, "GET", "/api/v1/messages/unread-counts", headers=bob_headers)).json_body
        assert badge_after_incoming["messages_tab_badge_count"] == badge_before_incoming["messages_tab_badge_count"] + 1
        assert service.build_direct_message_push_intent(bob_id, incoming["message_id"]).decision == "suppressed_by_conversation_mute"

        # A genuinely new outgoing message restores the sender too.
        assert (await asgi_request(app, "POST", f"/api/v1/messages/conversations/{conversation_id}/hide", headers=bob_headers)).status == 200
        await send(app, bob_headers, conversation_id, "hide-outgoing-new")
        assert archived_at(conversation_id, bob_id) is None

        # Retrying an existing logical send must not restore a hidden membership.
        retry_source = await send(app, bob_headers, conversation_id, "hide-idempotent")
        assert (await asgi_request(app, "POST", f"/api/v1/messages/conversations/{conversation_id}/hide", headers=bob_headers)).status == 200
        retry = await send(app, bob_headers, conversation_id, "hide-idempotent")
        assert retry["message_id"] == retry_source["message_id"] and archived_at(conversation_id, bob_id) is not None

        unauthorized = await asgi_request(app, "POST", f"/api/v1/messages/conversations/{conversation_id}/hide", headers=carol_headers)
        assert unauthorized.status in {403, 404}, unauthorized
        print("Message conversation hide API test passed.")


if __name__ == "__main__":
    asyncio.run(main())
