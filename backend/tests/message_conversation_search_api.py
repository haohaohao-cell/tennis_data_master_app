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


async def search(app, headers: dict[str, str], query: str, **options):
    return await asgi_request(
        app,
        "GET",
        f"/api/v1/messages/conversations/search?{urlencode({'q': query, **options})}",
        headers=headers,
    )


async def create_group(app, headers: dict[str, str], title: str, member_user_ids: list[str]) -> str:
    response = await asgi_request(
        app,
        "POST",
        "/api/v1/messages/groups",
        {"title": title, "group_type": "custom", "member_user_ids": member_user_ids},
        headers=headers,
    )
    assert response.status == 201, response
    return response.json_body["conversation"]["conversation_id"]


async def send(app, headers: dict[str, str], conversation_id: str, text: str, client_id: str) -> dict:
    response = await asgi_request(
        app,
        "POST",
        f"/api/v1/messages/conversations/{conversation_id}/messages",
        {"message_type": "text", "text_content": text, "client_message_id": client_id},
        headers=headers,
    )
    assert response.status == 201, response
    return response.json_body["message"]


async def main() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        os.environ["TENNIS_DB_PATH"] = str(Path(temp_dir) / "message_conversation_search.sqlite3")

        from backend.app.core.database import get_connection, initialize_database
        from backend.app.main import app

        initialize_database()
        (alice_token, alice_id), (bob_token, bob_id), (carol_token, carol_id), (dave_token, dave_id) = [
            await login_phone(app, phone)
            for phone in ("13944400001", "13944400002", "13944400003", "13944400004")
        ]
        alice_headers = {"authorization": f"Bearer {alice_token}"}
        bob_headers = {"authorization": f"Bearer {bob_token}"}
        carol_headers = {"authorization": f"Bearer {carol_token}"}

        with get_connection() as connection:
            connection.execute("UPDATE users SET nickname = ? WHERE user_id = ?;", ("Self Only", alice_id))
            connection.execute("UPDATE users SET nickname = ? WHERE user_id = ?;", (r"Target Bob % _ \ ' 张", bob_id))
            connection.execute("UPDATE users SET nickname = ? WHERE user_id = ?;", ("Carol", carol_id))
            connection.execute("UPDATE users SET nickname = ? WHERE user_id = ?;", ("Dave", dave_id))
            connection.commit()

        for headers, target_id in ((alice_headers, bob_id), (bob_headers, alice_id)):
            response = await asgi_request(app, "POST", f"/api/v1/social/follows/{target_id}", headers=headers)
            assert response.status == 201, response
        direct = await asgi_request(
            app,
            "POST",
            "/api/v1/messages/direct-conversations",
            {"target_user_id": bob_id},
            headers=alice_headers,
        )
        assert direct.status == 201, direct
        direct_id = direct.json_body["conversation"]["conversation_id"]
        duplicate_direct = await asgi_request(
            app,
            "POST",
            "/api/v1/messages/direct-conversations",
            {"target_user_id": bob_id},
            headers=alice_headers,
        )
        assert duplicate_direct.json_body["conversation"]["conversation_id"] == direct_id

        target_group_id = await create_group(app, alice_headers, r"Target Group % _ \ ' 张", [carol_id])
        isolated_group_id = await create_group(app, carol_headers, "Target isolated", [dave_id])
        assert isolated_group_id != target_group_id
        for index in range(31):
            await create_group(app, alice_headers, f"Noise {index:02d}", [carol_id])
        filtered_target_id = await create_group(app, alice_headers, "Filtered Target", [carol_id])

        await send(app, bob_headers, direct_id, "incoming unread", "search-direct-unread")
        await asyncio.sleep(1.05)
        await send(app, alice_headers, target_group_id, "newer group activity", "search-group-recency")
        pinned = await asgi_request(app, "POST", f"/api/v1/messages/conversations/{direct_id}/pin", headers=alice_headers)
        muted = await asgi_request(app, "POST", f"/api/v1/messages/conversations/{direct_id}/mute", headers=alice_headers)
        assert pinned.status == muted.status == 200

        target = await search(app, alice_headers, "Target", page_size=30)
        assert target.status == 200, target
        target_items = target.json_body["items"]
        target_ids = [item["conversation"]["conversation_id"] for item in target_items]
        assert target_ids[0] == direct_id, target_ids
        assert target_group_id in target_ids and filtered_target_id in target_ids
        assert isolated_group_id not in target_ids
        direct_item = next(item for item in target_items if item["conversation"]["conversation_id"] == direct_id)
        assert direct_item["member"]["pinned_at"]
        assert direct_item["member"]["is_muted"] is True
        assert direct_item["member"]["unread_count"] == 1
        assert direct_item["member"]["archived_at"] is None
        assert len(target_ids) == len(set(target_ids))

        assert (await search(app, alice_headers, "Self Only")).json_body["items"] == []
        assert (await search(app, alice_headers, "does not exist")).json_body["items"] == []
        assert direct_id in [item["conversation"]["conversation_id"] for item in (await search(app, alice_headers, "%")).json_body["items"]]
        assert direct_id in [item["conversation"]["conversation_id"] for item in (await search(app, alice_headers, "_")).json_body["items"]]
        assert direct_id in [item["conversation"]["conversation_id"] for item in (await search(app, alice_headers, "\\")).json_body["items"]]
        assert direct_id in [item["conversation"]["conversation_id"] for item in (await search(app, alice_headers, "'")).json_body["items"]]
        assert direct_id in [item["conversation"]["conversation_id"] for item in (await search(app, alice_headers, "张")).json_body["items"]]

        filtered_page = await search(app, alice_headers, "Filtered Target", page_size=1)
        assert filtered_page.status == 200
        assert [item["conversation"]["conversation_id"] for item in filtered_page.json_body["items"]] == [filtered_target_id]

        with get_connection() as connection:
            before_member = connection.execute(
                "SELECT unread_count, last_read_message_seq, pinned_at, muted_until, archived_at FROM chat_conversation_members WHERE conversation_id = ? AND user_id = ?;",
                (direct_id, alice_id),
            ).fetchone()
        before_badge = (await asgi_request(app, "GET", "/api/v1/messages/unread-counts", headers=alice_headers)).json_body
        hidden = await asgi_request(app, "POST", f"/api/v1/messages/conversations/{direct_id}/hide", headers=alice_headers)
        assert hidden.status == 200
        assert direct_id not in [item["conversation"]["conversation_id"] for item in (await search(app, alice_headers, "Target")).json_body["items"]]
        unhidden = await asgi_request(app, "DELETE", f"/api/v1/messages/conversations/{direct_id}/hide", headers=alice_headers)
        assert unhidden.status == 200
        blocked = await asgi_request(app, "POST", f"/api/v1/social/blocks/{bob_id}", headers=alice_headers)
        assert blocked.status == 201
        assert direct_id in [item["conversation"]["conversation_id"] for item in (await search(app, alice_headers, "Target")).json_body["items"]]
        with get_connection() as connection:
            after_member = connection.execute(
                "SELECT unread_count, last_read_message_seq, pinned_at, muted_until, archived_at FROM chat_conversation_members WHERE conversation_id = ? AND user_id = ?;",
                (direct_id, alice_id),
            ).fetchone()
        after_badge = (await asgi_request(app, "GET", "/api/v1/messages/unread-counts", headers=alice_headers)).json_body
        assert tuple(after_member) == tuple(before_member)
        assert after_badge == before_badge

        blank = await search(app, alice_headers, "   ")
        assert blank.status == 400 and blank.json_body["detail"]["code"] == "CONVERSATION_SEARCH_QUERY_REQUIRED"
        normalized_maximum = await search(app, alice_headers, f"  {'x' * 100}  ")
        assert normalized_maximum.status == 200
        oversized = await search(app, alice_headers, f"  {'x' * 101}  ")
        assert oversized.status == 400
        assert oversized.json_body["detail"]["code"] == "CONVERSATION_SEARCH_QUERY_TOO_LONG"

        print("Message conversation search API test passed.")


if __name__ == "__main__":
    asyncio.run(main())
