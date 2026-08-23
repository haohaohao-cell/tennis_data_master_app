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


async def main() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        os.environ["TENNIS_DB_PATH"] = str(Path(temp_dir) / "message_hydration_batch.sqlite3")

        from backend.app.core.database import get_connection, initialize_database
        from backend.app.main import app

        initialize_database()
        alice_token, alice_id = await login_phone(app, "13949000001")
        bob_token, bob_id = await login_phone(app, "13949000002")
        alice = {"authorization": f"Bearer {alice_token}"}
        bob = {"authorization": f"Bearer {bob_token}"}
        for headers, target_id in ((alice, bob_id), (bob, alice_id)):
            followed = await asgi_request(app, "POST", f"/api/v1/social/follows/{target_id}", headers=headers)
            assert followed.status == 201, followed

        conversation_response = await asgi_request(
            app,
            "POST",
            "/api/v1/messages/direct-conversations",
            {"target_user_id": bob_id},
            headers=alice,
        )
        assert conversation_response.status == 201, conversation_response
        conversation_id = conversation_response.json_body["conversation"]["conversation_id"]

        original = await asgi_request(
            app,
            "POST",
            f"/api/v1/messages/conversations/{conversation_id}/messages",
            {"message_type": "text", "text_content": "hydration source", "client_message_id": "hydration-source"},
            headers=alice,
        )
        assert original.status == 201, original
        original_message = original.json_body["message"]

        reply = await asgi_request(
            app,
            "POST",
            f"/api/v1/messages/conversations/{conversation_id}/messages",
            {
                "message_type": "text",
                "text_content": "hydration reply",
                "reply_to_message_id": original_message["message_id"],
                "client_message_id": "hydration-reply",
            },
            headers=bob,
        )
        assert reply.status == 201, reply

        with get_connection() as connection:
            attachment_message_id = "hydration-attachment-message"
            connection.execute(
                """
                INSERT INTO chat_messages (
                    message_id, conversation_id, message_seq, sender_user_id, message_type,
                    text_content, client_message_id
                ) VALUES (?, ?, ?, ?, 'text', ?, ?);
                """,
                (attachment_message_id, conversation_id, 3, alice_id, "with attachment", "hydration-attachment"),
            )
            connection.execute(
                """
                INSERT INTO chat_message_attachments (
                    attachment_id, message_id, attachment_type, media_path, sort_order
                ) VALUES (?, ?, 'file', ?, 0);
                """,
                ("hydration-attachment", attachment_message_id, "/tmp/hydration.txt"),
            )
            connection.execute(
                "UPDATE chat_conversations SET last_message_id = ?, last_message_seq = 3 WHERE conversation_id = ?;",
                (attachment_message_id, conversation_id),
            )
            connection.commit()

        recalled = await asgi_request(
            app,
            "POST",
            f"/api/v1/messages/conversations/{conversation_id}/messages/{original_message['message_id']}/recall",
            headers=alice,
        )
        assert recalled.status == 200, recalled

        history = await asgi_request(
            app,
            "GET",
            f"/api/v1/messages/conversations/{conversation_id}/messages?page_size=10",
            headers=bob,
        )
        assert history.status == 200, history
        items = {item["message_id"]: item for item in history.json_body["items"]}
        assert items[original_message["message_id"]]["status"] == "revoked"
        assert items[original_message["message_id"]]["text_content"] is None
        assert items[original_message["message_id"]]["attachments"] == []
        assert items[reply.json_body["message"]["message_id"]]["reply_preview"]["state"] == "unavailable"
        assert items[attachment_message_id]["attachments"][0]["media_path"] == "/tmp/hydration.txt"

        print("Message hydration batch API test passed.")


if __name__ == "__main__":
    asyncio.run(main())
