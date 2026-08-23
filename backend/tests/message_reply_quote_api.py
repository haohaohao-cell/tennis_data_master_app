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


async def send(
    app,
    headers: dict[str, str],
    conversation_id: str,
    text: str,
    client_id: str,
    reply_to_message_id: str | None = None,
):
    return await asgi_request(
        app,
        "POST",
        f"/api/v1/messages/conversations/{conversation_id}/messages",
        {
            "message_type": "text",
            "text_content": text,
            "client_message_id": client_id,
            "reply_to_message_id": reply_to_message_id,
        },
        headers=headers,
    )


async def main() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        os.environ["TENNIS_DB_PATH"] = str(Path(temp_dir) / "message_reply_quote.sqlite3")

        from backend.app.core.database import get_connection, initialize_database
        from backend.app.main import app

        initialize_database()
        (alice_token, alice_id), (bob_token, bob_id), (carol_token, carol_id) = [
            await login_phone(app, phone) for phone in ("13945000001", "13945000002", "13945000003")
        ]
        alice_headers = {"authorization": f"Bearer {alice_token}"}
        bob_headers = {"authorization": f"Bearer {bob_token}"}
        carol_headers = {"authorization": f"Bearer {carol_token}"}
        for headers, target_id in (
            (alice_headers, bob_id),
            (bob_headers, alice_id),
            (alice_headers, carol_id),
            (carol_headers, alice_id),
        ):
            response = await asgi_request(app, "POST", f"/api/v1/social/follows/{target_id}", headers=headers)
            assert response.status == 201, response

        ab = await asgi_request(
            app, "POST", "/api/v1/messages/direct-conversations", {"target_user_id": bob_id}, headers=alice_headers
        )
        ac = await asgi_request(
            app, "POST", "/api/v1/messages/direct-conversations", {"target_user_id": carol_id}, headers=alice_headers
        )
        assert ab.status == ac.status == 201
        ab_id = ab.json_body["conversation"]["conversation_id"]
        ac_id = ac.json_body["conversation"]["conversation_id"]

        ac_secret_response = await send(app, alice_headers, ac_id, "AC private secret 9f31", "reply-ac-secret")
        assert ac_secret_response.status == 201, ac_secret_response
        ac_secret = ac_secret_response.json_body["message"]
        original_response = await send(app, alice_headers, ab_id, "Original serve plan", "reply-original")
        assert original_response.status == 201, original_response
        original = original_response.json_body["message"]
        basic_response = await send(app, bob_headers, ab_id, "Agreed", "reply-basic", original["message_id"])
        assert basic_response.status == 201, basic_response
        basic = basic_response.json_body["message"]
        assert basic["reply_to_message_id"] == original["message_id"]
        assert basic["reply_preview"] == {
            "state": "available",
            "message_id": original["message_id"],
            "message_seq": original["message_seq"],
            "sender_user_id": alice_id,
            "sender_nickname": basic["reply_preview"]["sender_nickname"],
            "text_content": "Original serve plan",
        }

        own_response = await send(app, bob_headers, ab_id, "Replying to myself", "reply-own", basic["message_id"])
        assert own_response.status == 201
        assert own_response.json_body["message"]["reply_to_message_id"] == basic["message_id"]

        missing = await send(app, bob_headers, ab_id, "Missing", "reply-missing", "not-a-message")
        assert missing.status == 404 and missing.json_body["detail"]["code"] == "MESSAGE_NOT_FOUND", missing
        cross_conversation = await send(app, alice_headers, ac_id, "Leaked?", "reply-cross", original["message_id"])
        assert cross_conversation.status == 400, cross_conversation
        assert cross_conversation.json_body["detail"]["code"] == "REPLY_MESSAGE_WRONG_CONVERSATION"
        assert "Original serve plan" not in str(cross_conversation.json_body)
        non_member = await send(app, carol_headers, ab_id, "No access", "reply-member", original["message_id"])
        assert non_member.status in {403, 404}, non_member

        before_retry = (await asgi_request(app, "GET", "/api/v1/messages/unread-counts", headers=alice_headers)).json_body
        retry_first = await send(app, bob_headers, ab_id, "One logical reply", "reply-idempotent", original["message_id"])
        retry_second = await send(app, bob_headers, ab_id, "Mutated reply", "reply-idempotent", basic["message_id"])
        assert retry_first.status == retry_second.status == 201
        assert retry_first.json_body["message"]["message_id"] == retry_second.json_body["message"]["message_id"]
        assert retry_second.json_body["message"]["reply_to_message_id"] == original["message_id"]
        after_retry = (await asgi_request(app, "GET", "/api/v1/messages/unread-counts", headers=alice_headers)).json_body
        assert after_retry["unread_direct_message_count"] == before_retry["unread_direct_message_count"] + 1

        for index in range(4):
            response = await send(app, alice_headers, ab_id, f"filler {index}", f"reply-filler-{index}")
            assert response.status == 201
        paginated_reply_response = await send(
            app, bob_headers, ab_id, "Latest paginated reply", "reply-paginated", original["message_id"]
        )
        assert paginated_reply_response.status == 201
        paginated_reply = paginated_reply_response.json_body["message"]
        paged = await asgi_request(
            app, "GET", f"/api/v1/messages/conversations/{ab_id}/messages?page_size=2", headers=alice_headers
        )
        assert paged.status == 200
        paged_items = paged.json_body["items"]
        assert paginated_reply["message_id"] in {item["message_id"] for item in paged_items}
        assert original["message_id"] not in {item["message_id"] for item in paged_items}
        paged_quote = next(item for item in paged_items if item["message_id"] == paginated_reply["message_id"])
        assert paged_quote["reply_preview"]["message_id"] == original["message_id"]
        assert paged_quote["reply_preview"]["text_content"] == "Original serve plan"
        searched = await asgi_request(
            app, "GET", f"/api/v1/messages/conversations/{ab_id}/messages/search?q=Agreed", headers=alice_headers
        )
        assert searched.status == 200 and searched.json_body["items"][0]["reply_preview"]["message_id"] == original["message_id"]

        with get_connection() as connection:
            connection.execute(
                "UPDATE chat_messages SET reply_to_message_id = ? WHERE message_id = ?;",
                (ac_secret["message_id"], paginated_reply["message_id"]),
            )
            connection.commit()
        corrupted_history = await asgi_request(
            app, "GET", f"/api/v1/messages/conversations/{ab_id}/messages?page_size=20", headers=alice_headers
        )
        assert corrupted_history.status == 200
        corrupted = next(item for item in corrupted_history.json_body["items"] if item["message_id"] == paginated_reply["message_id"])
        assert corrupted["reply_preview"] == {
            "state": "unavailable",
            "message_id": ac_secret["message_id"],
            "message_seq": None,
            "sender_user_id": None,
            "sender_nickname": None,
            "text_content": None,
        }
        assert "AC private secret 9f31" not in str(corrupted_history.json_body)
        corrupted_search = await asgi_request(
            app, "GET", f"/api/v1/messages/conversations/{ab_id}/messages/search?q=Latest%20paginated", headers=alice_headers
        )
        assert corrupted_search.status == 200
        assert corrupted_search.json_body["items"][0]["reply_preview"]["state"] == "unavailable"
        assert "AC private secret 9f31" not in str(corrupted_search.json_body)

        blocked = await asgi_request(app, "POST", f"/api/v1/social/blocks/{alice_id}", headers=bob_headers)
        assert blocked.status == 201
        blocked_reply = await send(app, bob_headers, ab_id, "blocked", "reply-blocked", original["message_id"])
        assert blocked_reply.status == 403 and blocked_reply.json_body["detail"]["code"] == "USER_INTERACTION_BLOCKED"
        await asgi_request(app, "DELETE", f"/api/v1/social/blocks/{alice_id}", headers=bob_headers)

        with get_connection() as connection:
            connection.execute("UPDATE chat_messages SET deleted_at = CURRENT_TIMESTAMP WHERE message_id = ?;", (original["message_id"],))
            connection.commit()
        unavailable_history = await asgi_request(
            app, "GET", f"/api/v1/messages/conversations/{ab_id}/messages?page_size=20", headers=bob_headers
        )
        assert unavailable_history.status == 200
        quoted = next(item for item in unavailable_history.json_body["items"] if item["message_id"] == basic["message_id"])
        assert quoted["reply_preview"] == {
            "state": "unavailable",
            "message_id": original["message_id"],
            "message_seq": None,
            "sender_user_id": None,
            "sender_nickname": None,
            "text_content": None,
        }

        print("Message reply quote API test passed.")


if __name__ == "__main__":
    asyncio.run(main())
