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


async def list_messages(app, headers, conversation_id: str):
    return await asgi_request(
        app,
        "GET",
        f"/api/v1/messages/conversations/{conversation_id}/messages",
        headers=headers,
    )


async def send_text(app, headers, conversation_id: str, text: str, client_id: str):
    return await asgi_request(
        app,
        "POST",
        f"/api/v1/messages/conversations/{conversation_id}/messages",
        {
            "message_type": "text",
            "text_content": text,
            "client_message_id": client_id,
        },
        headers=headers,
    )


async def main() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        os.environ["TENNIS_DB_PATH"] = str(Path(temp_dir) / "message_block_state.sqlite3")

        from backend.app.core.database import initialize_database
        from backend.app.main import app

        initialize_database()
        users = [await login_phone(app, phone) for phone in ("13943200001", "13943200002", "13943200003")]
        (alice_token, alice_id), (bob_token, bob_id), (carol_token, carol_id) = users
        alice_headers = {"authorization": f"Bearer {alice_token}"}
        bob_headers = {"authorization": f"Bearer {bob_token}"}
        carol_headers = {"authorization": f"Bearer {carol_token}"}

        for target_id, headers in ((bob_id, alice_headers), (alice_id, bob_headers)):
            followed = await asgi_request(
                app,
                "POST",
                f"/api/v1/social/follows/{target_id}",
                {"source": "message-block-state"},
                headers=headers,
            )
            assert followed.status == 201, followed

        direct = await asgi_request(
            app,
            "POST",
            "/api/v1/messages/direct-conversations",
            {"target_user_id": bob_id},
            headers=alice_headers,
        )
        assert direct.status == 201, direct
        conversation_id = direct.json_body["conversation"]["conversation_id"]

        group = await asgi_request(
            app,
            "POST",
            "/api/v1/messages/groups",
            {"title": "Block state scope", "member_user_ids": [bob_id]},
            headers=alice_headers,
        )
        assert group.status == 201, group
        group_id = group.json_body["conversation"]["conversation_id"]

        initial_message = await send_text(
            app,
            alice_headers,
            conversation_id,
            "History remains visible",
            "block-state-history",
        )
        assert initial_message.status == 201, initial_message
        message = initial_message.json_body["message"]

        for headers in (alice_headers, bob_headers):
            response = await list_messages(app, headers, conversation_id)
            assert response.status == 200, response
            assert response.json_body["direct_interaction_state"] == {
                "can_send": True,
                "blocked_by_current_user": False,
            }

        blocked = await asgi_request(
            app,
            "POST",
            f"/api/v1/social/blocks/{bob_id}",
            {"reason": "message-block-state"},
            headers=alice_headers,
        )
        assert blocked.status == 201, blocked

        alice_history = await list_messages(app, alice_headers, conversation_id)
        bob_history = await list_messages(app, bob_headers, conversation_id)
        assert alice_history.status == bob_history.status == 200
        assert alice_history.json_body["items"][0]["message_id"] == message["message_id"]
        assert bob_history.json_body["items"][0]["message_id"] == message["message_id"]
        assert alice_history.json_body["direct_interaction_state"] == {
            "can_send": False,
            "blocked_by_current_user": True,
        }
        assert bob_history.json_body["direct_interaction_state"] == {
            "can_send": False,
            "blocked_by_current_user": False,
        }

        for headers, client_id in ((alice_headers, "blocked-alice"), (bob_headers, "blocked-bob")):
            response = await send_text(app, headers, conversation_id, "blocked", client_id)
            assert response.status == 403, response
            assert response.json_body["detail"]["code"] == "USER_INTERACTION_BLOCKED"

        marked = await asgi_request(
            app,
            "POST",
            f"/api/v1/messages/conversations/{conversation_id}/read",
            {"through_message_seq": message["message_seq"]},
            headers=bob_headers,
        )
        assert marked.status == 200, marked
        assert marked.json_body["last_read_message_seq"] == message["message_seq"]
        receipt = await list_messages(app, alice_headers, conversation_id)
        assert receipt.json_body["other_member_last_read_message_seq"] == message["message_seq"]
        assert receipt.json_body["items"][0]["message_id"] == message["message_id"]

        blocked_request = await asgi_request(
            app,
            "POST",
            "/api/v1/messages/requests",
            {"target_user_id": bob_id, "request_message": "must not bypass block"},
            headers=alice_headers,
        )
        assert blocked_request.status == 403, blocked_request
        assert blocked_request.json_body["detail"]["code"] == "USER_INTERACTION_BLOCKED"

        unauthorized = await list_messages(app, carol_headers, conversation_id)
        assert unauthorized.status in {403, 404}, unauthorized

        group_messages = await list_messages(app, alice_headers, group_id)
        assert group_messages.status == 200, group_messages
        assert group_messages.json_body["direct_interaction_state"] is None

        unblocked = await asgi_request(
            app,
            "DELETE",
            f"/api/v1/social/blocks/{bob_id}",
            headers=alice_headers,
        )
        assert unblocked.status == 200, unblocked
        for headers in (alice_headers, bob_headers):
            response = await list_messages(app, headers, conversation_id)
            assert response.status == 200, response
            assert response.json_body["direct_interaction_state"] == {
                "can_send": True,
                "blocked_by_current_user": False,
            }

        restored_send = await send_text(
            app,
            bob_headers,
            conversation_id,
            "Sending restored",
            "block-state-restored",
        )
        assert restored_send.status == 201, restored_send

        print("Message block state API test passed.")


if __name__ == "__main__":
    asyncio.run(main())
