from __future__ import annotations

import asyncio
import os
from pathlib import Path
import sys
import tempfile
from urllib.parse import urlencode


ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT_DIR))

from backend.tests.activity_detail_api_smoke import login_phone
from backend.tests.auth_api_smoke import asgi_request


async def send(app, headers: dict[str, str], conversation_id: str, text: str, client_id: str, message_type: str = "text") -> dict:
    response = await asgi_request(
        app,
        "POST",
        f"/api/v1/messages/conversations/{conversation_id}/messages",
        {"message_type": message_type, "text_content": text if message_type == "text" else None, "client_message_id": client_id},
        headers=headers,
    )
    assert response.status == 201, response
    return response.json_body["message"]


async def search(app, headers: dict[str, str], conversation_id: str, query: str, **options):
    params = {"q": query, **options}
    return await asgi_request(
        app,
        "GET",
        f"/api/v1/messages/conversations/{conversation_id}/messages/search?{urlencode(params)}",
        headers=headers,
    )


async def main() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        os.environ["TENNIS_DB_PATH"] = str(Path(temp_dir) / "message_history_search.sqlite3")

        from backend.app.core.database import get_connection, initialize_database
        from backend.app.main import app

        initialize_database()
        (alice_token, alice_id), (bob_token, bob_id), (carol_token, carol_id) = [
            await login_phone(app, phone) for phone in ("13944300001", "13944300002", "13944300003")
        ]
        alice_headers = {"authorization": f"Bearer {alice_token}"}
        bob_headers = {"authorization": f"Bearer {bob_token}"}
        carol_headers = {"authorization": f"Bearer {carol_token}"}
        for headers, target_id in (
            (alice_headers, bob_id), (bob_headers, alice_id), (alice_headers, carol_id), (carol_headers, alice_id),
        ):
            followed = await asgi_request(app, "POST", f"/api/v1/social/follows/{target_id}", headers=headers)
            assert followed.status == 201, followed

        direct_ab = await asgi_request(
            app, "POST", "/api/v1/messages/direct-conversations", {"target_user_id": bob_id}, headers=alice_headers
        )
        direct_ac = await asgi_request(
            app, "POST", "/api/v1/messages/direct-conversations", {"target_user_id": carol_id}, headers=alice_headers
        )
        assert direct_ab.status == direct_ac.status == 201
        conversation_id = direct_ab.json_body["conversation"]["conversation_id"]
        other_conversation_id = direct_ac.json_body["conversation"]["conversation_id"]

        first = await send(app, alice_headers, conversation_id, "serve opener", "search-1")
        chinese = await send(app, bob_headers, conversation_id, "发球训练", "search-2")
        emoji = await send(app, alice_headers, conversation_id, "serve mixed 🎾", "search-3")
        literal = await send(app, bob_headers, conversation_id, r"literal % _ \\ and quote '", "search-4")
        page_one = await send(app, alice_headers, conversation_id, "page needle one", "search-5")
        page_two = await send(app, alice_headers, conversation_id, "page needle two", "search-6")
        page_three = await send(app, alice_headers, conversation_id, "page needle three", "search-7")
        page_four = await send(app, alice_headers, conversation_id, "page needle four", "search-8")
        deleted = await send(app, alice_headers, conversation_id, "deleted serve", "search-deleted")
        await send(app, alice_headers, other_conversation_id, "serve in another conversation", "search-other")
        # Image messages now require a completed message-media attachment;
        # image-specific behavior is covered by message_image_message_api.py.
        await send(app, alice_headers, conversation_id, "payload-only", "search-payload")
        with get_connection() as connection:
            connection.execute("UPDATE chat_messages SET deleted_at = CURRENT_TIMESTAMP WHERE message_id = ?;", (deleted["message_id"],))
            connection.commit()

        basic = await search(app, bob_headers, conversation_id, "serve")
        assert basic.status == 200, basic
        basic_items = basic.json_body["items"]
        assert [item["message_seq"] for item in basic_items] == sorted(
            [item["message_seq"] for item in basic_items], reverse=True
        )
        assert {item["message_id"] for item in basic_items} == {first["message_id"], emoji["message_id"]}
        assert all(item["conversation_id"] == conversation_id for item in basic_items)
        assert other_conversation_id not in {item["conversation_id"] for item in basic_items}

        assert [item["message_id"] for item in (await search(app, bob_headers, conversation_id, "发球")).json_body["items"]] == [chinese["message_id"]]
        assert [item["message_id"] for item in (await search(app, bob_headers, conversation_id, "🎾")).json_body["items"]] == [emoji["message_id"]]
        assert [item["message_id"] for item in (await search(app, bob_headers, conversation_id, "%")).json_body["items"]] == [literal["message_id"]]
        assert [item["message_id"] for item in (await search(app, bob_headers, conversation_id, "_")).json_body["items"]] == [literal["message_id"]]
        assert [item["message_id"] for item in (await search(app, bob_headers, conversation_id, "\\")).json_body["items"]] == [literal["message_id"]]
        assert [item["message_id"] for item in (await search(app, bob_headers, conversation_id, "'")).json_body["items"]] == [literal["message_id"]]

        paged_first = await search(app, bob_headers, conversation_id, "page needle", page_size=2)
        assert paged_first.status == 200
        assert [item["message_id"] for item in paged_first.json_body["items"]] == [page_four["message_id"], page_three["message_id"]]
        cursor = paged_first.json_body["next_before_seq"]
        paged_second = await search(app, bob_headers, conversation_id, "page needle", page_size=2, before_seq=cursor)
        assert [item["message_id"] for item in paged_second.json_body["items"]] == [page_two["message_id"], page_one["message_id"]]
        assert all(item["message_seq"] < cursor for item in paged_second.json_body["items"])

        blank = await search(app, bob_headers, conversation_id, "   ")
        assert blank.status == 400 and blank.json_body["detail"]["code"] == "MESSAGE_SEARCH_QUERY_REQUIRED"
        normalized_maximum = await search(app, bob_headers, conversation_id, f"  {'x' * 100}  ")
        assert normalized_maximum.status == 200, normalized_maximum
        oversized = await search(app, bob_headers, conversation_id, f"  {'x' * 101}  ")
        assert oversized.status == 400
        assert oversized.json_body["detail"]["code"] == "MESSAGE_SEARCH_QUERY_TOO_LONG"
        unauthorized = await search(app, carol_headers, conversation_id, "serve")
        assert unauthorized.status in {403, 404}, unauthorized

        with get_connection() as connection:
            before_member = connection.execute(
                "SELECT last_read_message_seq, unread_count FROM chat_conversation_members WHERE conversation_id = ? AND user_id = ?;",
                (conversation_id, bob_id),
            ).fetchone()
            before_other_member = connection.execute(
                "SELECT last_read_message_seq FROM chat_conversation_members WHERE conversation_id = ? AND user_id = ?;",
                (conversation_id, alice_id),
            ).fetchone()
        before_counts = (await asgi_request(app, "GET", "/api/v1/messages/unread-counts", headers=bob_headers)).json_body
        hidden = await asgi_request(app, "POST", f"/api/v1/messages/conversations/{conversation_id}/hide", headers=bob_headers)
        assert hidden.status == 200
        hidden_search = await search(app, bob_headers, conversation_id, "serve")
        assert hidden_search.status == 200
        blocked = await asgi_request(app, "POST", f"/api/v1/social/blocks/{alice_id}", headers=bob_headers)
        assert blocked.status == 201
        blocked_search = await search(app, bob_headers, conversation_id, "serve")
        assert blocked_search.status == 200
        with get_connection() as connection:
            after_member = connection.execute(
                "SELECT last_read_message_seq, unread_count FROM chat_conversation_members WHERE conversation_id = ? AND user_id = ?;",
                (conversation_id, bob_id),
            ).fetchone()
            after_other_member = connection.execute(
                "SELECT last_read_message_seq FROM chat_conversation_members WHERE conversation_id = ? AND user_id = ?;",
                (conversation_id, alice_id),
            ).fetchone()
        after_counts = (await asgi_request(app, "GET", "/api/v1/messages/unread-counts", headers=bob_headers)).json_body
        assert tuple(after_member) == tuple(before_member)
        assert tuple(after_other_member) == tuple(before_other_member)
        assert after_counts == before_counts

        print("Message history search API test passed.")


if __name__ == "__main__":
    asyncio.run(main())
