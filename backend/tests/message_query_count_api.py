from __future__ import annotations

import asyncio
from contextlib import contextmanager
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import uuid
from unittest.mock import patch


ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT_DIR))

from backend.tests.activity_detail_api_smoke import login_phone
from backend.tests.auth_api_smoke import asgi_request


@contextmanager
def trace_queries(database_module, statements: list[str]):
    if database_module.settings.uses_postgres:
        from backend.app.core import postgres

        original_execute = postgres.PostgresConnection.execute

        def instrumented_execute(connection, sql, params=()):
            statements.append(sql)
            return original_execute(connection, sql, params)

        postgres.PostgresConnection.execute = instrumented_execute
        try:
            yield
        finally:
            postgres.PostgresConnection.execute = original_execute
        return

    original_connect = database_module._connect

    def instrumented_connect():
        connection = original_connect()
        connection.set_trace_callback(statements.append)
        return connection

    database_module._connect = instrumented_connect
    try:
        yield
    finally:
        database_module._connect = original_connect


async def main() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        os.environ["TENNIS_DB_PATH"] = str(Path(temp_dir) / "message_query_count.sqlite3")
        from backend.app.core import database as database_module
        from backend.app.core.database import get_connection, initialize_database, transaction
        from backend.app.main import app
        from backend.app.messages import service as message_service

        initialize_database()
        alice_token, alice_id = await login_phone(app, "13949000301")
        bob_token, bob_id = await login_phone(app, "13949000302")
        alice = {"authorization": f"Bearer {alice_token}"}
        bob = {"authorization": f"Bearer {bob_token}"}
        for headers, target_id in ((alice, bob_id), (bob, alice_id)):
            response = await asgi_request(app, "POST", f"/api/v1/social/follows/{target_id}", headers=headers)
            assert response.status == 201, response
        direct = await asgi_request(
            app, "POST", "/api/v1/messages/direct-conversations",
            {"target_user_id": bob_id}, headers=alice,
        )
        assert direct.status == 201, direct
        conversation_id = direct.json_body["conversation"]["conversation_id"]

        post_ids: list[str] = []
        with transaction() as connection:
            for index in range(8):
                post_id = str(uuid.uuid4())
                post_ids.append(post_id)
                timestamp = "2026-08-29T00:00:00Z"
                connection.execute(
                    """
                    INSERT INTO social_posts (
                        social_post_id, author_user_id, title, content, visibility,
                        status, review_status, published_at, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, 'public', 'published', 'approved', ?, ?, ?);
                    """,
                    (post_id, alice_id, f"Batch post {index}", f"Batch body {index}", timestamp, timestamp, timestamp),
                )
                connection.execute("INSERT INTO social_post_stats (social_post_id) VALUES (?);", (post_id,))

        for index, post_id in enumerate(post_ids):
            response = await asgi_request(
                app, "POST", f"/api/v1/posts/{post_id}/share",
                {
                    "share_target_type": "conversation",
                    "conversation_id": conversation_id,
                    "message_text": f"Batch post {index}",
                    "client_message_id": f"batch-share-{index}",
                }, headers=alice,
            )
            assert response.status == 201, response

        statements: list[str] = []
        with trace_queries(database_module, statements):
            history = await asgi_request(
                app, "GET", f"/api/v1/messages/conversations/{conversation_id}/messages?page_size=20", headers=bob,
            )
        assert history.status == 200, history
        assert len(history.json_body["items"]) == len(post_ids)
        assert all(item["business_object_card"]["state"] == "available" for item in history.json_body["items"])
        post_query_count = sum("FROM SOCIAL_POSTS" in statement.upper() for statement in statements)
        block_query_count = sum("BLOCKED_USER_ID IN (" in statement.upper() for statement in statements)
        follow_query_count = sum("FOLLOWING_USER_ID IN (" in statement.upper() for statement in statements)
        cover_query_count = sum("FROM POST_MEDIA" in statement.upper() for statement in statements)
        assert post_query_count == 1, statements
        assert block_query_count == 1, statements
        assert follow_query_count == 1, statements
        assert cover_query_count == 1, statements

        with get_connection() as connection:
            row = connection.execute(
                "SELECT * FROM chat_messages WHERE conversation_id = ? ORDER BY message_seq LIMIT 1;",
                (conversation_id,),
            ).fetchone()
            with patch.object(
                message_service, "_batch_social_post_cards", side_effect=sqlite3.OperationalError("injected database failure")
            ):
                try:
                    message_service.hydrate_business_object_card(connection, row, bob_id)
                except sqlite3.OperationalError:
                    pass
                else:
                    raise AssertionError("database hydration failures must not become unavailable cards")

        print({
            "history_items": len(post_ids),
            "total_queries": len(statements),
            "post_hydration_queries": post_query_count,
            "permission_queries": block_query_count + follow_query_count,
            "cover_queries": cover_query_count,
            "database_error_propagates": True,
        })
        print("Message query count API test passed.")


if __name__ == "__main__":
    asyncio.run(main())
