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


async def send_text(app, headers, conversation_id: str, text: str, client_id: str):
    response = await asgi_request(
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
    assert response.status == 201, response
    return response.json_body["message"]


async def main() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        os.environ["TENNIS_DB_PATH"] = str(Path(temp_dir) / "message_read_receipt.sqlite3")

        from backend.app.core.database import get_connection, initialize_database
        from backend.app.main import app

        initialize_database()
        users = [await login_phone(app, phone) for phone in ("13943100001", "13943100002", "13943100003")]
        (alice_token, alice_id), (bob_token, bob_id), (carol_token, carol_id) = users
        alice_headers = {"authorization": f"Bearer {alice_token}"}
        bob_headers = {"authorization": f"Bearer {bob_token}"}
        carol_headers = {"authorization": f"Bearer {carol_token}"}

        for target_id, headers in ((bob_id, alice_headers), (alice_id, bob_headers)):
            followed = await asgi_request(
                app,
                "POST",
                f"/api/v1/social/follows/{target_id}",
                {"source": "message-read-receipt"},
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

        seq1 = await send_text(app, alice_headers, conversation_id, "seq1", "receipt-seq1")
        alice_view = await asgi_request(
            app, "GET", f"/api/v1/messages/conversations/{conversation_id}/messages", headers=alice_headers
        )
        assert alice_view.status == 200, alice_view
        assert alice_view.json_body["other_member_last_read_message_seq"] == 0

        bob_read = await asgi_request(
            app,
            "POST",
            f"/api/v1/messages/conversations/{conversation_id}/read",
            {"through_message_seq": seq1["message_seq"]},
            headers=bob_headers,
        )
        assert bob_read.status == 200, bob_read
        assert bob_read.json_body["last_read_message_seq"] == seq1["message_seq"]
        assert bob_read.json_body["unread_count"] == 0

        alice_view = await asgi_request(
            app, "GET", f"/api/v1/messages/conversations/{conversation_id}/messages", headers=alice_headers
        )
        assert alice_view.json_body["other_member_last_read_message_seq"] == seq1["message_seq"]

        seq2 = await send_text(app, alice_headers, conversation_id, "seq2", "receipt-seq2")
        stale_mark = await asgi_request(
            app,
            "POST",
            f"/api/v1/messages/conversations/{conversation_id}/read",
            {"through_message_seq": seq1["message_seq"]},
            headers=bob_headers,
        )
        assert stale_mark.status == 200, stale_mark
        assert stale_mark.json_body["last_read_message_seq"] == seq1["message_seq"]
        assert stale_mark.json_body["unread_count"] == 1

        alice_view = await asgi_request(
            app, "GET", f"/api/v1/messages/conversations/{conversation_id}/messages", headers=alice_headers
        )
        assert alice_view.json_body["other_member_last_read_message_seq"] == seq1["message_seq"]

        bob_read = await asgi_request(
            app,
            "POST",
            f"/api/v1/messages/conversations/{conversation_id}/read",
            {"through_message_seq": seq2["message_seq"]},
            headers=bob_headers,
        )
        assert bob_read.json_body["last_read_message_seq"] == seq2["message_seq"]
        assert bob_read.json_body["unread_count"] == 0

        seq3 = await send_text(app, alice_headers, conversation_id, "seq3", "receipt-seq3")
        seq4 = await send_text(app, alice_headers, conversation_id, "seq4", "receipt-seq4")
        through_three = await asgi_request(
            app,
            "POST",
            f"/api/v1/messages/conversations/{conversation_id}/read",
            {"through_message_seq": seq3["message_seq"]},
            headers=bob_headers,
        )
        assert through_three.json_body["unread_count"] == 1

        latest_page = await asgi_request(
            app,
            "GET",
            f"/api/v1/messages/conversations/{conversation_id}/messages?page_size=2",
            headers=alice_headers,
        )
        assert latest_page.status == 200, latest_page
        assert [item["message_seq"] for item in latest_page.json_body["items"]] == [
            seq3["message_seq"],
            seq4["message_seq"],
        ]
        assert latest_page.json_body["other_member_last_read_message_seq"] == seq3["message_seq"]
        older_page = await asgi_request(
            app,
            "GET",
            f"/api/v1/messages/conversations/{conversation_id}/messages?page_size=2&before_seq={seq3['message_seq']}",
            headers=alice_headers,
        )
        assert older_page.status == 200, older_page
        assert older_page.json_body["other_member_last_read_message_seq"] == seq3["message_seq"]

        repeated_mark = await asgi_request(
            app,
            "POST",
            f"/api/v1/messages/conversations/{conversation_id}/read",
            {"through_message_seq": seq3["message_seq"]},
            headers=bob_headers,
        )
        assert repeated_mark.json_body["unread_count"] == 1

        first_retry = await send_text(app, alice_headers, conversation_id, "retry", "receipt-same-client")
        second_retry = await send_text(app, alice_headers, conversation_id, "retry", "receipt-same-client")
        assert second_retry["message_id"] == first_retry["message_id"]
        with get_connection() as connection:
            bob_member = connection.execute(
                """
                SELECT unread_count
                FROM chat_conversation_members
                WHERE conversation_id = ? AND user_id = ?;
                """,
                (conversation_id, bob_id),
            ).fetchone()
        assert bob_member["unread_count"] == 2

        final_read = await asgi_request(
            app,
            "POST",
            f"/api/v1/messages/conversations/{conversation_id}/read",
            {"through_message_seq": first_retry["message_seq"]},
            headers=bob_headers,
        )
        assert final_read.json_body["unread_count"] == 0

        unauthorized = await asgi_request(
            app, "GET", f"/api/v1/messages/conversations/{conversation_id}/messages", headers=carol_headers
        )
        assert unauthorized.status in {403, 404}, unauthorized
        unauthorized_mark = await asgi_request(
            app,
            "POST",
            f"/api/v1/messages/conversations/{conversation_id}/read",
            {"through_message_seq": first_retry["message_seq"]},
            headers=carol_headers,
        )
        assert unauthorized_mark.status in {403, 404}, unauthorized_mark

        group = await asgi_request(
            app,
            "POST",
            "/api/v1/messages/groups",
            {"title": "Receipt scope", "member_user_ids": [bob_id]},
            headers=alice_headers,
        )
        assert group.status == 201, group
        group_id = group.json_body["conversation"]["conversation_id"]
        group_messages = await asgi_request(
            app, "GET", f"/api/v1/messages/conversations/{group_id}/messages", headers=alice_headers
        )
        assert group_messages.status == 200, group_messages
        assert group_messages.json_body["other_member_last_read_message_seq"] is None

        print("Message read receipt API test passed.")


if __name__ == "__main__":
    asyncio.run(main())
