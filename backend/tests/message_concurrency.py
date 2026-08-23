from __future__ import annotations

import asyncio
import os
from pathlib import Path
import tempfile
import sys

ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT_DIR))

from backend.tests.activity_detail_api_smoke import login_phone
from backend.tests.auth_api_smoke import asgi_request


async def main() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        os.environ["TENNIS_DB_PATH"] = str(Path(temp_dir) / "message_concurrency.sqlite3")

        from backend.app.core.database import get_connection, initialize_database
        from backend.app.main import app

        initialize_database()
        alice_token, alice_id = await login_phone(app, "13930000001")
        bob_token, bob_id = await login_phone(app, "13930000002")
        alice_headers = {"authorization": f"Bearer {alice_token}"}
        bob_headers = {"authorization": f"Bearer {bob_token}"}

        for target_id, headers in ((bob_id, alice_headers), (alice_id, bob_headers)):
            response = await asgi_request(
                app,
                "POST",
                f"/api/v1/social/follows/{target_id}",
                {"source": "message-concurrency"},
                headers=headers,
            )
            assert response.status in {201, 409}, response

        create_responses = await asyncio.gather(
            *(
                asgi_request(
                    app,
                    "POST",
                    "/api/v1/messages/direct-conversations",
                    {"target_user_id": bob_id},
                    headers=alice_headers,
                )
                for _ in range(5)
            )
        )
        assert all(response.status == 201 for response in create_responses), create_responses
        conversation_ids = {
            response.json_body["conversation"]["conversation_id"]
            for response in create_responses
        }
        assert len(conversation_ids) == 1, conversation_ids
        conversation_id = next(iter(conversation_ids))

        send_responses = await asyncio.gather(
            *(
                asgi_request(
                    app,
                    "POST",
                    f"/api/v1/messages/conversations/{conversation_id}/messages",
                    {
                        "message_type": "text",
                        "text_content": f"parallel-{index}",
                        "client_message_id": f"parallel-{index}",
                    },
                    headers=alice_headers,
                )
                for index in range(20)
            )
        )
        assert all(response.status == 201 for response in send_responses), send_responses

        with get_connection() as connection:
            conversation_count = connection.execute(
                """
                SELECT COUNT(*)
                FROM chat_conversations
                WHERE direct_pair_key = (
                    SELECT CASE WHEN ? < ? THEN ? || ':' || ? ELSE ? || ':' || ? END
                )
                  AND deleted_at IS NULL;
                """,
                (alice_id, bob_id, alice_id, bob_id, bob_id, alice_id),
            ).fetchone()[0]
            message_count = connection.execute(
                "SELECT COUNT(*) FROM chat_messages WHERE conversation_id = ?;",
                (conversation_id,),
            ).fetchone()[0]
            messages = connection.execute(
                """
                SELECT message_id, message_seq, text_content
                FROM chat_messages
                WHERE conversation_id = ?
                ORDER BY message_seq ASC;
                """,
                (conversation_id,),
            ).fetchall()
            conversation = connection.execute(
                "SELECT last_message_id, last_message_seq, last_message_preview FROM chat_conversations WHERE conversation_id = ?;",
                (conversation_id,),
            ).fetchone()
            members = connection.execute(
                """
                SELECT user_id, unread_count
                FROM chat_conversation_members
                WHERE conversation_id = ? AND deleted_at IS NULL
                ORDER BY user_id;
                """,
                (conversation_id,),
            ).fetchall()
            counters = connection.execute(
                "SELECT unread_direct_message_count FROM user_inbox_counters WHERE user_id = ?;",
                (bob_id,),
            ).fetchone()

        assert conversation_count == 1, conversation_count
        assert message_count == 20, message_count
        assert [row["message_seq"] for row in messages] == list(range(1, 21)), messages
        assert conversation["last_message_seq"] == 20
        last_message = next(row for row in messages if row["message_id"] == conversation["last_message_id"])
        assert last_message["message_seq"] == 20
        assert conversation["last_message_preview"] == last_message["text_content"]
        assert len(members) == 2
        member_by_user = {row["user_id"]: row["unread_count"] for row in members}
        assert member_by_user[alice_id] == 0
        assert member_by_user[bob_id] == 20
        assert counters["unread_direct_message_count"] == 20

        retry = await asgi_request(
            app,
            "POST",
            f"/api/v1/messages/conversations/{conversation_id}/messages",
            {
                "message_type": "text",
                "text_content": "parallel-retry",
                "client_message_id": "parallel-0",
            },
            headers=alice_headers,
        )
        assert retry.status == 201
        with get_connection() as connection:
            assert connection.execute(
                "SELECT COUNT(*) FROM chat_messages WHERE conversation_id = ?;",
                (conversation_id,),
            ).fetchone()[0] == 20
            assert connection.execute(
                "SELECT unread_count FROM chat_conversation_members WHERE conversation_id = ? AND user_id = ?;",
                (conversation_id, bob_id),
            ).fetchone()[0] == 20
            assert connection.execute(
                "SELECT unread_direct_message_count FROM user_inbox_counters WHERE user_id = ?;",
                (bob_id,),
            ).fetchone()[0] == 20
        print("Message concurrency test passed.")


if __name__ == "__main__":
    asyncio.run(main())
