from __future__ import annotations

import asyncio
from contextlib import contextmanager
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import time
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from urllib.parse import urlencode


ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT_DIR))

from backend.tests.activity_detail_api_smoke import login_phone
from backend.tests.auth_api_smoke import asgi_request


@dataclass
class QueryStats:
    statements: list[str]

    @property
    def total(self) -> int:
        return len(self.statements)

    @property
    def hydration(self) -> int:
        markers = ("chat_message_attachments", "FROM users", "FROM chat_messages")
        return sum(1 for statement in self.statements if any(marker in statement for marker in markers))


@contextmanager
def trace_queries(database_module, stats: QueryStats) -> Iterator[None]:
    """Attach a test-only trace callback to every connection opened by the app."""
    original_connect = database_module._connect

    def instrumented_connect() -> sqlite3.Connection:
        connection = original_connect()
        connection.set_trace_callback(stats.statements.append)
        return connection

    database_module._connect = instrumented_connect
    try:
        yield
    finally:
        database_module._connect = original_connect


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4()}"


def seed_history(connection: sqlite3.Connection, conversation_id: str, alice_id: str, bob_id: str, count: int) -> None:
    connection.execute(
        """
        INSERT INTO chat_conversations (
            conversation_id, conversation_type, direct_pair_key, created_by_user_id,
            last_message_id, last_message_seq, last_message_preview, last_message_at
        ) VALUES (?, 'direct', ?, ?, ?, ?, ?, CURRENT_TIMESTAMP);
        """,
        (conversation_id, f"benchmark-pair-{conversation_id}", alice_id, f"{conversation_id}-message-{count}", count, "benchmark",),
    )
    connection.executemany(
        """
        INSERT INTO chat_conversation_members (
            conversation_member_id, conversation_id, user_id, member_role, unread_count
        ) VALUES (?, ?, ?, ?, 0);
        """,
        (
            (new_id("member"), conversation_id, alice_id, "member"),
            (new_id("member"), conversation_id, bob_id, "member"),
        ),
    )
    for sequence in range(1, count + 1):
        message_id = f"{conversation_id}-message-{sequence}"
        status = "revoked" if sequence == 4 else "sent"
        reply_to = f"{conversation_id}-message-1" if sequence == 2 else None
        connection.execute(
            """
            INSERT INTO chat_messages (
                message_id, conversation_id, message_seq, sender_user_id, message_type,
                text_content, reply_to_message_id, client_message_id, status
            ) VALUES (?, ?, ?, ?, 'text', ?, ?, ?, ?);
            """,
            (message_id, conversation_id, sequence, alice_id if sequence % 2 else bob_id,
             f"benchmark history {sequence}", reply_to, f"{message_id}-client", status),
        )
        if sequence == 3:
            connection.execute(
                """
                INSERT INTO chat_message_attachments (
                    attachment_id, message_id, attachment_type, media_path, sort_order
                ) VALUES (?, ?, 'file', ?, 0);
                """,
                (new_id("attachment"), message_id, "/benchmark/file.txt"),
            )


def seed_conversations(
    connection: sqlite3.Connection,
    prefix: str,
    count: int,
    alice_id: str,
    bob_id: str,
) -> None:
    for index in range(count):
        conversation_id = f"{prefix}-{index:04d}"
        connection.execute(
            """
            INSERT INTO chat_conversations (
                conversation_id, conversation_type, group_type, title, created_by_user_id
            ) VALUES (?, 'group', 'custom', ?, ?);
            """,
            (conversation_id, f"benchmark conversation {index}", alice_id),
        )
        connection.executemany(
            """
            INSERT INTO chat_conversation_members (
                conversation_member_id, conversation_id, user_id, member_role
            ) VALUES (?, ?, ?, ?);
            """,
            (
                (new_id("member"), conversation_id, alice_id, "owner"),
                (new_id("member"), conversation_id, bob_id, "member"),
            ),
        )


async def measure(app, database_module, method: str, path: str, headers: dict[str, str]) -> dict[str, int | float]:
    stats = QueryStats([])
    started = time.perf_counter()
    with trace_queries(database_module, stats):
        response = await asgi_request(app, method, path, headers=headers)
    elapsed_ms = (time.perf_counter() - started) * 1000
    assert response.status == 200, response
    assert response.json_body.get("items") is not None, response
    return {
        "total_queries": stats.total,
        "hydration_queries": stats.hydration,
        "items": len(response.json_body["items"]),
        "elapsed_ms": round(elapsed_ms, 2),
    }


async def main() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        os.environ["TENNIS_DB_PATH"] = str(Path(temp_dir) / "message_query_benchmark.sqlite3")
        from backend.app.core.database import get_connection, initialize_database
        from backend.app.core import database as database_module
        from backend.app.main import app

        initialize_database()
        alice_token, alice_id = await login_phone(app, "13949000101")
        bob_token, bob_id = await login_phone(app, "13949000102")
        alice_headers = {"authorization": f"Bearer {alice_token}"}

        history_results: dict[int, dict[str, int | float]] = {}
        history_ids: dict[int, str] = {}
        with get_connection() as connection:
            for count in (20, 50, 200):
                conversation_id = f"benchmark-history-{count}"
                seed_history(connection, conversation_id, alice_id, bob_id, count)
                history_ids[count] = conversation_id
            connection.commit()
        for count in (20, 50, 200):
            history_results[count] = await measure(
                app,
                database_module,
                "GET",
                f"/api/v1/messages/conversations/{history_ids[count]}/messages?page_size=50",
                alice_headers,
            )

        list_results: dict[int, dict[str, int | float]] = {}
        for count in (10, 50, 200):
            with get_connection() as connection:
                connection.execute(
                    "DELETE FROM chat_conversation_members WHERE conversation_id LIKE 'benchmark-list-%';"
                )
                connection.execute("DELETE FROM chat_conversations WHERE conversation_id LIKE 'benchmark-list-%';")
                seed_conversations(connection, "benchmark-list", count, alice_id, bob_id)
                connection.commit()
            list_results[count] = await measure(
                app,
                database_module,
                "GET",
                "/api/v1/messages/conversations?page=1&page_size=50",
                alice_headers,
            )

        search_results = await measure(
            app,
            database_module,
            "GET",
            f"/api/v1/messages/conversations/search?{urlencode({'q': 'benchmark conversation', 'page_size': 50})}",
            alice_headers,
        )
        history_search_results = await measure(
            app,
            database_module,
            "GET",
            f"/api/v1/messages/conversations/{history_ids[200]}/messages/search?{urlencode({'q': 'benchmark history', 'page_size': 50})}",
            alice_headers,
        )

        print("Message History")
        for count, result in history_results.items():
            print(f"  {count}: {result}")
        print("Conversation List")
        for count, result in list_results.items():
            print(f"  {count}: {result}")
        print(f"Conversation Search: {search_results}")
        print(f"History Search: {history_search_results}")

        # Guard the batching properties without imposing machine-specific latency limits.
        assert history_results[200]["hydration_queries"] <= 8
        assert list_results[200]["hydration_queries"] <= 4
        assert history_results[200]["items"] == 50
        assert list_results[200]["items"] == 50
        assert search_results["hydration_queries"] <= 4
        assert history_search_results["hydration_queries"] <= 8
        print("Message query benchmark regression assertions passed.")


if __name__ == "__main__":
    asyncio.run(main())
