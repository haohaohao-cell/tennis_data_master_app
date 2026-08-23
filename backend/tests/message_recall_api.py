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


async def send(app, headers, conversation_id: str, text: str, client_id: str, reply_to: str | None = None):
    return await asgi_request(
        app,
        "POST",
        f"/api/v1/messages/conversations/{conversation_id}/messages",
        {
            "message_type": "text",
            "text_content": text,
            "client_message_id": client_id,
            "reply_to_message_id": reply_to,
        },
        headers=headers,
    )


async def history(app, headers, conversation_id: str, page_size: int = 50):
    return await asgi_request(
        app,
        "GET",
        f"/api/v1/messages/conversations/{conversation_id}/messages?page_size={page_size}",
        headers=headers,
    )


async def recall(app, headers, conversation_id: str, message_id: str):
    return await asgi_request(
        app,
        "POST",
        f"/api/v1/messages/conversations/{conversation_id}/messages/{message_id}/recall",
        headers=headers,
    )


async def reconcile(app, headers, conversation_id: str, message_ids: list[str]):
    return await asgi_request(
        app,
        "POST",
        f"/api/v1/messages/conversations/{conversation_id}/messages/reconcile",
        {"message_ids": message_ids},
        headers=headers,
    )


async def main() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        os.environ["TENNIS_DB_PATH"] = str(Path(temp_dir) / "message_recall.sqlite3")

        from backend.app.core.database import get_connection, initialize_database
        from backend.app.main import app

        initialize_database()
        (alice_token, alice_id), (bob_token, bob_id), (carol_token, carol_id) = [
            await login_phone(app, phone) for phone in ("13946000001", "13946000002", "13946000003")
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
            followed = await asgi_request(app, "POST", f"/api/v1/social/follows/{target_id}", headers=headers)
            assert followed.status == 201, followed

        direct_response = await asgi_request(
            app, "POST", "/api/v1/messages/direct-conversations", {"target_user_id": bob_id}, headers=alice_headers
        )
        other_direct_response = await asgi_request(
            app, "POST", "/api/v1/messages/direct-conversations", {"target_user_id": carol_id}, headers=alice_headers
        )
        assert direct_response.status == other_direct_response.status == 201
        direct_id = direct_response.json_body["conversation"]["conversation_id"]
        other_direct_id = other_direct_response.json_body["conversation"]["conversation_id"]

        # Historical mutation regression: both rows are loaded, then fall outside the latest-50 page.
        old_target_response = await send(app, alice_headers, direct_id, "historical target secret", "recall-old-target")
        assert old_target_response.status == 201
        old_target = old_target_response.json_body["message"]
        old_reply_response = await send(
            app, bob_headers, direct_id, "historical reply", "recall-old-reply", old_target["message_id"]
        )
        assert old_reply_response.status == 201
        old_reply = old_reply_response.json_body["message"]
        initially_loaded = await history(app, bob_headers, direct_id, page_size=50)
        initially_loaded_ids = {item["message_id"] for item in initially_loaded.json_body["items"]}
        assert old_target["message_id"] in initially_loaded_ids and old_reply["message_id"] in initially_loaded_ids
        for index in range(51):
            filler = await send(app, alice_headers, direct_id, f"filler-{index}", f"recall-filler-{index}")
            assert filler.status == 201
        latest_page = await history(app, bob_headers, direct_id)
        assert len(latest_page.json_body["items"]) == 50
        assert old_target["message_id"] not in {item["message_id"] for item in latest_page.json_body["items"]}
        assert old_reply["message_id"] not in {item["message_id"] for item in latest_page.json_body["items"]}
        recalled_old = await recall(app, alice_headers, direct_id, old_target["message_id"])
        assert recalled_old.status == 200
        with get_connection() as connection:
            before_reconcile_member = connection.execute(
                "SELECT unread_count, last_read_message_id, last_read_message_seq, last_read_at, archived_at, pinned_at, muted_until FROM chat_conversation_members WHERE conversation_id = ? AND user_id = ?;",
                (direct_id, bob_id),
            ).fetchone()
            before_reconcile_conversation = connection.execute(
                "SELECT last_message_id, last_message_seq, last_message_at, last_message_preview FROM chat_conversations WHERE conversation_id = ?;",
                (direct_id,),
            ).fetchone()
            before_reconcile_notifications = connection.execute(
                "SELECT COUNT(*) FROM user_notifications WHERE recipient_user_id = ?;", (bob_id,)
            ).fetchone()[0]
        old_reconcile = await reconcile(
            app, bob_headers, direct_id, [old_target["message_id"], old_reply["message_id"]]
        )
        assert old_reconcile.status == 200
        old_rows = {item["message_id"]: item for item in old_reconcile.json_body["items"]}
        assert old_rows[old_target["message_id"]]["status"] == "revoked"
        assert old_rows[old_target["message_id"]]["text_content"] is None
        assert old_rows[old_reply["message_id"]]["reply_preview"]["state"] == "unavailable"
        with get_connection() as connection:
            after_reconcile_member = connection.execute(
                "SELECT unread_count, last_read_message_id, last_read_message_seq, last_read_at, archived_at, pinned_at, muted_until FROM chat_conversation_members WHERE conversation_id = ? AND user_id = ?;",
                (direct_id, bob_id),
            ).fetchone()
            after_reconcile_conversation = connection.execute(
                "SELECT last_message_id, last_message_seq, last_message_at, last_message_preview FROM chat_conversations WHERE conversation_id = ?;",
                (direct_id,),
            ).fetchone()
            after_reconcile_notifications = connection.execute(
                "SELECT COUNT(*) FROM user_notifications WHERE recipient_user_id = ?;", (bob_id,)
            ).fetchone()[0]
        assert tuple(after_reconcile_member) == tuple(before_reconcile_member)
        assert tuple(after_reconcile_conversation) == tuple(before_reconcile_conversation)
        assert after_reconcile_notifications == before_reconcile_notifications
        non_member_reconcile = await reconcile(app, carol_headers, direct_id, [old_target["message_id"]])
        assert non_member_reconcile.status == 403
        other_message = await send(app, alice_headers, other_direct_id, "other conversation secret", "recall-other-conv")
        assert other_message.status == 201
        cross_conversation = await reconcile(app, alice_headers, direct_id, [other_message.json_body["message"]["message_id"]])
        assert cross_conversation.status == 200 and cross_conversation.json_body["items"] == []

        group_response = await asgi_request(
            app,
            "POST",
            "/api/v1/messages/groups",
            {"title": "Recall group", "member_user_ids": [bob_id]},
            headers=alice_headers,
        )
        assert group_response.status == 201
        group_id = group_response.json_body["conversation"]["conversation_id"]

        nonlatest_response = await send(app, alice_headers, direct_id, "nonlatest private text", "recall-nonlatest")
        latest_response = await send(app, alice_headers, direct_id, "latest private secret", "recall-latest")
        assert nonlatest_response.status == latest_response.status == 201
        nonlatest = nonlatest_response.json_body["message"]
        latest = latest_response.json_body["message"]

        before_unread = (await asgi_request(app, "GET", "/api/v1/messages/unread-counts", headers=bob_headers)).json_body
        with get_connection() as connection:
            before_member = connection.execute(
                "SELECT unread_count, last_read_message_id, last_read_message_seq, last_read_at, archived_at FROM chat_conversation_members WHERE conversation_id = ? AND user_id = ?;",
                (direct_id, bob_id),
            ).fetchone()
            before_conversation = connection.execute(
                "SELECT last_message_id, last_message_seq, last_message_at, last_message_preview FROM chat_conversations WHERE conversation_id = ?;",
                (direct_id,),
            ).fetchone()
        assert before_conversation["last_message_id"] == latest["message_id"]

        non_sender = await recall(app, bob_headers, direct_id, latest["message_id"])
        assert non_sender.status == 403 and non_sender.json_body["detail"]["code"] == "MESSAGE_RECALL_NOT_ALLOWED"
        non_member = await recall(app, carol_headers, direct_id, latest["message_id"])
        assert non_member.status == 403
        wrong_conversation = await recall(app, alice_headers, other_direct_id, latest["message_id"])
        assert wrong_conversation.status == 404 and wrong_conversation.json_body["detail"]["code"] == "MESSAGE_NOT_FOUND"

        hidden = await asgi_request(app, "POST", f"/api/v1/messages/conversations/{direct_id}/hide", headers=bob_headers)
        assert hidden.status == 200
        blocked = await asgi_request(app, "POST", f"/api/v1/social/blocks/{alice_id}", headers=bob_headers)
        assert blocked.status == 201

        recalled = await recall(app, alice_headers, direct_id, latest["message_id"])
        assert recalled.status == 200
        recalled_message = recalled.json_body["message"]
        assert recalled_message["status"] == "revoked"
        assert recalled_message["message_id"] == latest["message_id"]
        assert recalled_message["message_seq"] == latest["message_seq"]
        assert recalled_message["text_content"] is None
        assert recalled_message["payload_json"] is None
        assert recalled_message["attachments"] == []
        assert recalled_message["reply_preview"] is None

        repeated = await recall(app, alice_headers, direct_id, latest["message_id"])
        assert repeated.status == 200 and repeated.json_body["message"]["status"] == "revoked"
        after_unread = (await asgi_request(app, "GET", "/api/v1/messages/unread-counts", headers=bob_headers)).json_body
        assert after_unread == before_unread
        with get_connection() as connection:
            after_member = connection.execute(
                "SELECT unread_count, last_read_message_id, last_read_message_seq, last_read_at, archived_at FROM chat_conversation_members WHERE conversation_id = ? AND user_id = ?;",
                (direct_id, bob_id),
            ).fetchone()
            after_conversation = connection.execute(
                "SELECT last_message_id, last_message_seq, last_message_at, last_message_preview FROM chat_conversations WHERE conversation_id = ?;",
                (direct_id,),
            ).fetchone()
        assert tuple(after_member[:4]) == tuple(before_member[:4])
        assert after_member["archived_at"] is not None
        assert after_conversation["last_message_id"] == before_conversation["last_message_id"]
        assert after_conversation["last_message_seq"] == before_conversation["last_message_seq"]
        assert after_conversation["last_message_at"] == before_conversation["last_message_at"]
        assert after_conversation["last_message_preview"] == "[消息已撤回]"

        bob_history = await history(app, bob_headers, direct_id)
        assert bob_history.status == 200
        latest_row = next(item for item in bob_history.json_body["items"] if item["message_id"] == latest["message_id"])
        assert latest_row["status"] == "revoked" and latest_row["text_content"] is None
        search_old = await asgi_request(
            app, "GET", f"/api/v1/messages/conversations/{direct_id}/messages/search?q=latest%20private%20secret", headers=bob_headers
        )
        assert search_old.status == 200, search_old
        assert search_old.json_body["items"] == [], search_old.json_body

        # Recall remains allowed for the sender even while the receiver's block exists.
        await asgi_request(app, "DELETE", f"/api/v1/social/blocks/{alice_id}", headers=bob_headers)
        reply_target_response = await send(app, alice_headers, direct_id, "reply target", "recall-reply-target")
        assert reply_target_response.status == 201
        reply_target = reply_target_response.json_body["message"]
        reply_response = await send(app, bob_headers, direct_id, "reply before recall", "recall-reply", reply_target["message_id"])
        assert reply_response.status == 201
        reply = reply_response.json_body["message"]
        recalled_target = await recall(app, alice_headers, direct_id, reply_target["message_id"])
        assert recalled_target.status == 200
        reply_history = await history(app, bob_headers, direct_id)
        reply_row = next(item for item in reply_history.json_body["items"] if item["message_id"] == reply["message_id"])
        assert reply_row["reply_preview"]["state"] == "unavailable"
        assert "reply target" not in str(reply_row["reply_preview"])
        new_reply = await send(app, bob_headers, direct_id, "new reply rejected", "recall-new-reply", reply_target["message_id"])
        assert new_reply.status == 400 and new_reply.json_body["detail"]["code"] == "REPLY_MESSAGE_UNAVAILABLE"
        recalled_reply = await recall(app, bob_headers, direct_id, reply["message_id"])
        assert recalled_reply.status == 200 and recalled_reply.json_body["message"]["status"] == "revoked"
        assert recalled_reply.json_body["message"]["text_content"] is None

        # A non-latest recall must not rewrite the current conversation preview.
        current_preview = (await asgi_request(app, "GET", f"/api/v1/messages/conversations?{''}", headers=alice_headers)).status
        assert current_preview == 200
        nonlatest_before = after_conversation["last_message_preview"]
        recalled_nonlatest = await recall(app, alice_headers, direct_id, nonlatest["message_id"])
        assert recalled_nonlatest.status == 200
        with get_connection() as connection:
            preview_after_nonlatest = connection.execute(
                "SELECT last_message_id, last_message_preview FROM chat_conversations WHERE conversation_id = ?;", (direct_id,)
            ).fetchone()
        assert preview_after_nonlatest["last_message_preview"] == nonlatest_before

        group_message_response = await send(app, alice_headers, group_id, "group recall", "recall-group")
        assert group_message_response.status == 201
        group_recall = await recall(app, alice_headers, group_id, group_message_response.json_body["message"]["message_id"])
        assert group_recall.status == 400 and group_recall.json_body["detail"]["code"] == "RECALL_DIRECT_ONLY"

        print("Message recall API test passed.")


if __name__ == "__main__":
    asyncio.run(main())
