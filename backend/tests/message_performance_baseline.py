from __future__ import annotations

import asyncio
import os
from pathlib import Path
import statistics
import sys
import tempfile
import time
from collections.abc import Awaitable, Callable
import json
from urllib.parse import urlencode


ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT_DIR))

from backend.tests.activity_detail_api_smoke import login_phone
from backend.tests.auth_api_smoke import AsgiResponse, asgi_request


SCALES = (("SMALL", 10, 20), ("MEDIUM", 50, 100), ("LARGE", 100, 500))
WARMUP_SAMPLES = 3
MEASUREMENT_SAMPLES = 20
SEARCH_TOKEN = "baseline-search-token"


def percentile_95(samples_ms: list[float]) -> float:
    ordered = sorted(samples_ms)
    return ordered[max(0, int(len(ordered) * 0.95 + 0.999999) - 1)]


def percentile_99(samples_ms: list[float]) -> float:
    ordered = sorted(samples_ms)
    return ordered[max(0, int(len(ordered) * 0.99 + 0.999999) - 1)]


async def measure(operation: Callable[[], Awaitable[AsgiResponse]]) -> dict[str, float | int]:
    for _ in range(WARMUP_SAMPLES):
        response = await operation()
        assert response.status in {200, 201}, response

    samples_ms: list[float] = []
    for _ in range(MEASUREMENT_SAMPLES):
        started_at = time.perf_counter()
        response = await operation()
        samples_ms.append((time.perf_counter() - started_at) * 1000)
        assert response.status in {200, 201}, response

    return {
        "max_ms": max(samples_ms),
        "min_ms": min(samples_ms),
        "p50_ms": statistics.median(samples_ms),
        "p95_ms": percentile_95(samples_ms),
        "p99_ms": percentile_99(samples_ms),
        "samples": len(samples_ms),
    }


def seed_scale(
    get_connection: Callable[[], object],
    conversation_count: int,
    messages_per_conversation: int,
    alice_id: str,
    bob_id: str,
    scale_name: str,
) -> str:
    target_conversation_id = f"benchmark-{scale_name.lower()}-000"
    with get_connection() as connection:
        for conversation_index in range(conversation_count):
            conversation_id = f"benchmark-{scale_name.lower()}-{conversation_index:03d}"
            last_message_id = f"benchmark-message-{scale_name.lower()}-{conversation_index:03d}-{messages_per_conversation:04d}"
            connection.execute(
                """
                INSERT INTO chat_conversations (
                    conversation_id, conversation_type, group_type, title, created_by_user_id,
                    last_message_id, last_message_seq, last_message_preview, last_message_at
                ) VALUES (?, 'group', 'custom', ?, ?, ?, ?, ?, CURRENT_TIMESTAMP);
                """,
                (
                    conversation_id,
                    f"{SEARCH_TOKEN} {scale_name} {conversation_index:03d}",
                    alice_id,
                    last_message_id,
                    messages_per_conversation,
                    SEARCH_TOKEN,
                ),
            )
            connection.executemany(
                """
                INSERT INTO chat_conversation_members (
                    conversation_member_id, conversation_id, user_id, member_role, unread_count
                ) VALUES (?, ?, ?, ?, ?);
                """,
                (
                    (f"benchmark-member-a-{scale_name}-{conversation_index:03d}", conversation_id, alice_id, "owner", 0),
                    (f"benchmark-member-b-{scale_name}-{conversation_index:03d}", conversation_id, bob_id, "member", messages_per_conversation),
                ),
            )
            connection.executemany(
                """
                INSERT INTO chat_messages (
                    message_id, conversation_id, message_seq, sender_user_id, message_type,
                    text_content, client_message_id
                ) VALUES (?, ?, ?, ?, 'text', ?, ?);
                """,
                (
                    (
                        f"benchmark-message-{scale_name.lower()}-{conversation_index:03d}-{message_seq:04d}",
                        conversation_id,
                        message_seq,
                        alice_id if message_seq % 2 else bob_id,
                        f"{SEARCH_TOKEN} message {message_seq:04d}" if message_seq == messages_per_conversation // 2 else f"seed message {message_seq:04d}",
                        f"benchmark-client-{scale_name.lower()}-{conversation_index:03d}-{message_seq:04d}",
                    )
                    for message_seq in range(1, messages_per_conversation + 1)
                ),
            )
        connection.commit()
    return target_conversation_id


async def benchmark_scale(
    app,
    get_connection: Callable[[], object],
    alice_headers: dict[str, str],
    bob_headers: dict[str, str],
    alice_id: str,
    bob_id: str,
    scale_name: str,
    conversation_count: int,
    messages_per_conversation: int,
) -> dict[str, dict[str, float | int]]:
    target_conversation_id = seed_scale(
        get_connection,
        conversation_count,
        messages_per_conversation,
        alice_id,
        bob_id,
        scale_name,
    )
    history_path = f"/api/v1/messages/conversations/{target_conversation_id}/messages?page_size=100"
    history_search_path = (
        f"/api/v1/messages/conversations/{target_conversation_id}/messages/search?"
        f"{urlencode({'q': SEARCH_TOKEN, 'page_size': 30})}"
    )
    conversation_search_path = f"/api/v1/messages/conversations/search?{urlencode({'q': SEARCH_TOKEN, 'page_size': 50})}"
    send_index = 0

    async def send() -> AsgiResponse:
        nonlocal send_index
        send_index += 1
        return await asgi_request(
            app,
            "POST",
            f"/api/v1/messages/conversations/{target_conversation_id}/messages",
            {
                "client_message_id": f"benchmark-send-{scale_name.lower()}-{send_index:04d}",
                "message_type": "text",
                "text_content": f"benchmark send {scale_name} {send_index:04d}",
            },
            headers=alice_headers,
        )

    operations: dict[str, Callable[[], Awaitable[AsgiResponse]]] = {
        "Conversation List": lambda: asgi_request(app, "GET", "/api/v1/messages/conversations?page=1&page_size=50", headers=alice_headers),
        "Message History": lambda: asgi_request(app, "GET", history_path, headers=alice_headers),
        "Conversation Search": lambda: asgi_request(app, "GET", conversation_search_path, headers=alice_headers),
        "Message History Search": lambda: asgi_request(app, "GET", history_search_path, headers=alice_headers),
        "Unread Counts": lambda: asgi_request(app, "GET", "/api/v1/messages/unread-counts", headers=bob_headers),
        "Send": send,
    }
    results = {name: await measure(operation) for name, operation in operations.items()}
    print(f"{scale_name}: conversations={conversation_count}, messages_per_conversation={messages_per_conversation}")
    for name, result in results.items():
        print(
            f"  {name}: samples={result['samples']} min={result['min_ms']:.2f}ms "
            f"p50={result['p50_ms']:.2f}ms p95={result['p95_ms']:.2f}ms "
            f"p99={result['p99_ms']:.2f}ms max={result['max_ms']:.2f}ms"
        )
    return results


async def main() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        # This is a local diagnostic baseline, not a CI latency gate. Isolate
        # it from any configured PostgreSQL runtime before importing the app.
        os.environ.pop("TENNIS_DATABASE_URL", None)
        os.environ.pop("TENNIS_POSTGRES_DSN", None)
        os.environ["TENNIS_DB_PATH"] = str(Path(temp_dir) / "message_performance_baseline.sqlite3")

        from backend.app.core.database import get_connection, initialize_database
        from backend.app.main import app

        initialize_database()
        (alice_token, alice_id), (bob_token, bob_id) = await asyncio.gather(
            login_phone(app, "13947000001"),
            login_phone(app, "13947000002"),
        )
        alice_headers = {"authorization": f"Bearer {alice_token}"}
        bob_headers = {"authorization": f"Bearer {bob_token}"}

        results: dict[str, object] = {}
        for scale_name, conversation_count, messages_per_conversation in SCALES:
            results[scale_name.lower()] = await benchmark_scale(
                app,
                get_connection,
                alice_headers,
                bob_headers,
                alice_id,
                bob_id,
                scale_name,
                conversation_count,
                messages_per_conversation,
            )
        report_path = os.getenv("TENNIS_PERFORMANCE_REPORT")
        if report_path:
            Path(report_path).write_text(
                json.dumps({
                    "report_type": "local_message_performance_baseline",
                    "database_type": "SQLite",
                    "ci_latency_gate": False,
                    "samples_per_operation": MEASUREMENT_SAMPLES,
                    "warmup_samples": WARMUP_SAMPLES,
                    "scales": results,
                    "errors": 0,
                    "timeouts": 0,
                }, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )


if __name__ == "__main__":
    asyncio.run(main())
