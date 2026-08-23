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


async def create_group(app, headers, title: str, member_ids: list[str]):
    return await asgi_request(
        app,
        "POST",
        "/api/v1/messages/groups",
        {"title": title, "group_type": "custom", "member_user_ids": member_ids},
        headers=headers,
    )


async def send(app, headers, conversation_id: str, text: str, client_id: str):
    return await asgi_request(
        app,
        "POST",
        f"/api/v1/messages/conversations/{conversation_id}/messages",
        {"message_type": "text", "text_content": text, "client_message_id": client_id},
        headers=headers,
    )


async def history(app, headers, conversation_id: str, page_size: int = 50, before_seq: int | None = None):
    query = f"page_size={page_size}"
    if before_seq is not None:
        query += f"&before_seq={before_seq}"
    return await asgi_request(
        app,
        "GET",
        f"/api/v1/messages/conversations/{conversation_id}/messages?{query}",
        headers=headers,
    )


async def main() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        os.environ["TENNIS_DB_PATH"] = str(Path(temp_dir) / "message_group_core.sqlite3")

        from backend.app.core.database import get_connection, initialize_database
        from backend.app.main import app

        initialize_database()
        users = [await login_phone(app, phone) for phone in (
            "13947000001", "13947000002", "13947000003", "13947000004", "13947000005"
        )]
        (alice_token, alice_id), (bob_token, bob_id), (carol_token, carol_id), (dave_token, dave_id), (erin_token, erin_id) = users
        alice = {"authorization": f"Bearer {alice_token}"}
        bob = {"authorization": f"Bearer {bob_token}"}
        carol = {"authorization": f"Bearer {carol_token}"}
        dave = {"authorization": f"Bearer {dave_token}"}

        invalid_empty = await create_group(app, alice, "", [bob_id])
        invalid_long = await create_group(app, alice, "x" * 121, [bob_id])
        assert invalid_empty.status == 422
        assert invalid_long.status == 422

        group_response = await create_group(app, alice, "Core Group", [alice_id, bob_id, bob_id, carol_id])
        assert group_response.status == 201, group_response
        group = group_response.json_body["conversation"]
        group_id = group["conversation_id"]
        assert group["conversation_type"] == "group"
        assert group["title"] == "Core Group"
        assert group_response.json_body["member"]["user_id"] == alice_id
        assert group_response.json_body["member"]["member_role"] == "owner"
        assert {item["user_id"] for item in group_response.json_body["other_members"]} == {bob_id, carol_id}

        with get_connection() as connection:
            members = connection.execute(
                "SELECT user_id, member_role, status FROM chat_conversation_members WHERE conversation_id = ? ORDER BY user_id;",
                (group_id,),
            ).fetchall()
        assert len(members) == 3
        assert {row["user_id"] for row in members} == {alice_id, bob_id, carol_id}
        assert {row["member_role"] for row in members if row["user_id"] != alice_id} == {"member"}
        assert all(row["status"] == "active" for row in members)

        listed = await asgi_request(app, "GET", "/api/v1/messages/conversations?page_size=50", headers=alice)
        assert listed.status == 200
        listed_item = next(item for item in listed.json_body["items"] if item["conversation"]["conversation_id"] == group_id)
        assert listed_item["conversation"]["title"] == "Core Group"
        assert listed_item["member"]["member_role"] == "owner"

        # Each direction of an active Block fails closed without exposing ownership.
        blocked_by_creator = await asgi_request(app, "POST", f"/api/v1/social/blocks/{dave_id}", headers=alice)
        assert blocked_by_creator.status == 201
        blocked_create_one = await create_group(app, alice, "Blocked One", [dave_id])
        assert blocked_create_one.status == 403
        assert blocked_create_one.json_body["detail"]["code"] == "USER_INTERACTION_BLOCKED"
        assert "blocker_user_id" not in str(blocked_create_one.json_body)
        await asgi_request(app, "DELETE", f"/api/v1/social/blocks/{dave_id}", headers=alice)

        blocked_by_candidate = await asgi_request(app, "POST", f"/api/v1/social/blocks/{alice_id}", headers=dave)
        assert blocked_by_candidate.status == 201
        blocked_create_two = await create_group(app, alice, "Blocked Two", [dave_id])
        assert blocked_create_two.status == 403
        assert blocked_create_two.json_body["detail"]["code"] == "USER_INTERACTION_BLOCKED"
        assert "blocker_user_id" not in str(blocked_create_two.json_body)
        await asgi_request(app, "DELETE", f"/api/v1/social/blocks/{alice_id}", headers=dave)

        # Creator and another member both send; retries remain one persisted row.
        first = await send(app, alice, group_id, "group first", "group-first")
        assert first.status == 201
        first_message = first.json_body["message"]
        retry = await send(app, alice, group_id, "different retry body", "group-first")
        assert retry.status == 201
        assert retry.json_body["message"]["message_id"] == first_message["message_id"]
        assert retry.json_body["message"]["message_seq"] == first_message["message_seq"]

        with get_connection() as connection:
            same_client_rows = connection.execute(
                "SELECT message_id, message_seq FROM chat_messages WHERE conversation_id = ? AND sender_user_id = ? AND client_message_id = ?;",
                (group_id, alice_id, "group-first"),
            ).fetchall()
        assert len(same_client_rows) == 1

        second = await send(app, bob, group_id, "group second", "group-second")
        assert second.status == 201
        assert second.json_body["message"]["sender_user_id"] == bob_id
        assert second.json_body["message"]["status"] == "sent"
        assert second.json_body["message"]["conversation_id"] == group_id

        for index in range(4):
            filler = await send(app, carol, group_id, f"pagination-{index}", f"group-page-{index}")
            assert filler.status == 201

        with get_connection() as connection:
            persisted = connection.execute(
                "SELECT message_id, message_seq FROM chat_messages WHERE conversation_id = ? ORDER BY message_seq;",
                (group_id,),
            ).fetchall()
        assert [row["message_seq"] for row in persisted] == list(range(1, len(persisted) + 1))

        page_one = await history(app, bob, group_id, page_size=2)
        assert page_one.status == 200
        page_one_items = page_one.json_body["items"]
        assert len(page_one_items) == 2
        assert page_one.json_body["next_before_seq"] == persisted[-2]["message_seq"]
        page_two = await history(app, bob, group_id, page_size=2, before_seq=page_one.json_body["next_before_seq"])
        assert page_two.status == 200
        page_two_items = page_two.json_body["items"]
        assert len(page_two_items) == 2
        page_ids = [item["message_id"] for item in page_one_items + page_two_items]
        assert len(page_ids) == len(set(page_ids))
        assert [item["message_seq"] for item in page_one_items] == [row["message_seq"] for row in persisted[-2:]]
        assert [item["message_seq"] for item in page_two_items] == [row["message_seq"] for row in persisted[-4:-2]]
        assert all(item["conversation_id"] == group_id and item["sender"] for item in page_one_items + page_two_items)
        assert page_one.json_body["direct_interaction_state"] is None

        counts_before = (await asgi_request(app, "GET", "/api/v1/messages/unread-counts", headers=bob)).json_body
        with get_connection() as connection:
            bob_before_read = connection.execute(
                "SELECT unread_count, last_read_message_seq, last_read_message_id, last_read_at FROM chat_conversation_members WHERE conversation_id = ? AND user_id = ?;",
                (group_id, bob_id),
            ).fetchone()
            alice_before_read = connection.execute(
                "SELECT unread_count, last_read_message_seq FROM chat_conversation_members WHERE conversation_id = ? AND user_id = ?;",
                (group_id, alice_id),
            ).fetchone()
        assert bob_before_read["unread_count"] > 0
        assert counts_before["unread_group_message_count"] >= bob_before_read["unread_count"]
        assert counts_before["messages_tab_badge_count"] == counts_before["unread_direct_message_count"] + counts_before["unread_notification_count"] + counts_before["pending_message_request_count"]

        mark_read = await asgi_request(
            app,
            "POST",
            f"/api/v1/messages/conversations/{group_id}/read",
            {"through_message_seq": persisted[-1]["message_seq"]},
            headers=bob,
        )
        assert mark_read.status == 200
        assert mark_read.json_body["last_read_message_seq"] == persisted[-1]["message_seq"]
        with get_connection() as connection:
            bob_after_read = connection.execute(
                "SELECT unread_count, last_read_message_seq, last_read_message_id, last_read_at FROM chat_conversation_members WHERE conversation_id = ? AND user_id = ?;",
                (group_id, bob_id),
            ).fetchone()
            alice_after_read = connection.execute(
                "SELECT unread_count, last_read_message_seq FROM chat_conversation_members WHERE conversation_id = ? AND user_id = ?;",
                (group_id, alice_id),
            ).fetchone()
        assert bob_after_read["unread_count"] == 0
        assert bob_after_read["last_read_message_seq"] == persisted[-1]["message_seq"]
        assert bob_after_read["last_read_message_id"] == persisted[-1]["message_id"]
        assert bob_after_read["last_read_at"] is not None
        assert tuple(alice_after_read) == tuple(alice_before_read)
        group_history_after_read = await history(app, bob, group_id)
        assert group_history_after_read.json_body["other_member_last_read_message_seq"] is None

        # Existing Group Block semantics: membership and Group send remain unchanged.
        blocked_existing = await asgi_request(app, "POST", f"/api/v1/social/blocks/{bob_id}", headers=alice)
        assert blocked_existing.status == 201
        alice_group_send = await send(app, alice, group_id, "group after block", "group-after-block-a")
        bob_group_send = await send(app, bob, group_id, "group after block b", "group-after-block-b")
        assert alice_group_send.status == bob_group_send.status == 201
        with get_connection() as connection:
            active_pair = connection.execute(
                "SELECT user_id, status FROM chat_conversation_members WHERE conversation_id = ? AND user_id IN (?, ?) ORDER BY user_id;",
                (group_id, alice_id, bob_id),
            ).fetchall()
        assert all(row["status"] == "active" for row in active_pair)
        await asgi_request(app, "DELETE", f"/api/v1/social/blocks/{bob_id}", headers=alice)

        # Membership preferences remain per-user and independent.
        with get_connection() as connection:
            before_pin = connection.execute(
                "SELECT unread_count, last_read_message_seq, muted_until, archived_at FROM chat_conversation_members WHERE conversation_id = ? AND user_id = ?;",
                (group_id, bob_id),
            ).fetchone()
            message_count_before_preferences = connection.execute(
                "SELECT COUNT(*) FROM chat_messages WHERE conversation_id = ?;", (group_id,)
            ).fetchone()[0]
        pin = await asgi_request(app, "POST", f"/api/v1/messages/conversations/{group_id}/pin", headers=bob)
        pin_retry = await asgi_request(app, "POST", f"/api/v1/messages/conversations/{group_id}/pin", headers=bob)
        assert pin.status == pin_retry.status == 200
        assert pin.json_body["pinned_at"] == pin_retry.json_body["pinned_at"]
        bob_list = await asgi_request(app, "GET", "/api/v1/messages/conversations", headers=bob)
        alice_list = await asgi_request(app, "GET", "/api/v1/messages/conversations", headers=alice)
        assert next(item for item in bob_list.json_body["items"] if item["conversation"]["conversation_id"] == group_id)["member"]["pinned_at"]
        assert next(item for item in alice_list.json_body["items"] if item["conversation"]["conversation_id"] == group_id)["member"]["pinned_at"] is None

        with get_connection() as connection:
            after_pin = connection.execute(
                "SELECT unread_count, last_read_message_seq, muted_until, archived_at FROM chat_conversation_members WHERE conversation_id = ? AND user_id = ?;",
                (group_id, bob_id),
            ).fetchone()
        assert tuple(after_pin) == tuple(before_pin)

        mute = await asgi_request(app, "POST", f"/api/v1/messages/conversations/{group_id}/mute", headers=bob)
        assert mute.status == 200 and mute.json_body["is_muted"] is True
        with get_connection() as connection:
            bob_pref = connection.execute(
                "SELECT unread_count, last_read_message_seq, pinned_at, muted_until, archived_at FROM chat_conversation_members WHERE conversation_id = ? AND user_id = ?;",
                (group_id, bob_id),
            ).fetchone()
            alice_pref = connection.execute(
                "SELECT pinned_at, muted_until, archived_at FROM chat_conversation_members WHERE conversation_id = ? AND user_id = ?;",
                (group_id, alice_id),
            ).fetchone()
        assert bob_pref["pinned_at"] is not None and bob_pref["muted_until"] is not None and bob_pref["archived_at"] is None
        assert bob_pref["unread_count"] == after_pin["unread_count"]
        assert bob_pref["last_read_message_seq"] == after_pin["last_read_message_seq"]
        assert alice_pref["pinned_at"] is None and alice_pref["muted_until"] is None and alice_pref["archived_at"] is None
        unmute = await asgi_request(app, "DELETE", f"/api/v1/messages/conversations/{group_id}/mute", headers=bob)
        assert unmute.status == 200 and unmute.json_body["is_muted"] is False

        with get_connection() as connection:
            before_hide = connection.execute(
                "SELECT unread_count, last_read_message_seq, pinned_at, muted_until FROM chat_conversation_members WHERE conversation_id = ? AND user_id = ?;",
                (group_id, bob_id),
            ).fetchone()
        hide = await asgi_request(app, "POST", f"/api/v1/messages/conversations/{group_id}/hide", headers=bob)
        assert hide.status == 200
        hidden_list = await asgi_request(app, "GET", "/api/v1/messages/conversations", headers=bob)
        assert group_id not in {item["conversation"]["conversation_id"] for item in hidden_list.json_body["items"]}
        unhide = await asgi_request(app, "DELETE", f"/api/v1/messages/conversations/{group_id}/hide", headers=bob)
        assert unhide.status == 200
        visible_again = await asgi_request(app, "GET", "/api/v1/messages/conversations", headers=bob)
        assert group_id in {item["conversation"]["conversation_id"] for item in visible_again.json_body["items"]}
        with get_connection() as connection:
            after_hide = connection.execute(
                "SELECT unread_count, last_read_message_seq, pinned_at, muted_until FROM chat_conversation_members WHERE conversation_id = ? AND user_id = ?;",
                (group_id, bob_id),
            ).fetchone()
            message_count_after_preferences = connection.execute(
                "SELECT COUNT(*) FROM chat_messages WHERE conversation_id = ?;", (group_id,)
            ).fetchone()[0]
        assert tuple(after_hide) == tuple(before_hide)
        assert message_count_after_preferences == message_count_before_preferences
        unpin = await asgi_request(app, "DELETE", f"/api/v1/messages/conversations/{group_id}/pin", headers=bob)
        assert unpin.status == 200 and unpin.json_body["pinned_at"] is None

        conversation_search = await asgi_request(
            app, "GET", "/api/v1/messages/conversations/search?q=Core%20Group", headers=alice
        )
        outsider_conversation_search = await asgi_request(
            app, "GET", "/api/v1/messages/conversations/search?q=Core%20Group", headers=dave
        )
        assert conversation_search.status == 200
        assert group_id in {item["conversation"]["conversation_id"] for item in conversation_search.json_body["items"]}
        assert outsider_conversation_search.status == 200 and outsider_conversation_search.json_body["items"] == []

        history_search = await asgi_request(
            app,
            "GET",
            f"/api/v1/messages/conversations/{group_id}/messages/search?q=group%20first",
            headers=alice,
        )
        outsider_history_search = await asgi_request(
            app,
            "GET",
            f"/api/v1/messages/conversations/{group_id}/messages/search?q=group%20first",
            headers=dave,
        )
        assert history_search.status == 200
        assert all(item["conversation_id"] == group_id for item in history_search.json_body["items"])
        assert outsider_history_search.status == 403

        # Non-members cannot read, send, or mark the Group read.
        outsider_history = await history(app, dave, group_id)
        outsider_send = await send(app, dave, group_id, "must fail", "group-outsider")
        outsider_read = await asgi_request(
            app, "POST", f"/api/v1/messages/conversations/{group_id}/read", {"through_message_seq": 1}, headers=dave
        )
        assert outsider_history.status == outsider_send.status == outsider_read.status == 403
        assert "group after block" not in str(outsider_history.json_body)

        print("Message group core API test passed.")


if __name__ == "__main__":
    asyncio.run(main())
