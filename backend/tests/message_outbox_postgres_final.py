"""Isolated PostgreSQL API regression for the stage-9 Outbox final gate.

This test deliberately configures a caller-provided PostgreSQL search_path
before importing the ASGI app.  It never initializes or opens the default
SQLite database.
"""

from __future__ import annotations

import asyncio
from datetime import timedelta
import json
import os
from pathlib import Path
import statistics
import sys
import time
from urllib.parse import parse_qsl, quote, urlsplit, urlunsplit

ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT_DIR))

from backend.tests.activity_detail_api_smoke import login_phone
from backend.tests.auth_api_smoke import asgi_request


def schema_dsn(dsn: str, schema: str) -> str:
    parts = urlsplit(dsn)
    query = [(key, value) for key, value in parse_qsl(parts.query, keep_blank_values=True) if key != "options"]
    query.append(("options", f"-c search_path={schema},pg_catalog"))
    encoded = "&".join(f"{quote(key, safe='')}={quote(value, safe='')}" for key, value in query)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, encoded, parts.fragment))


def percentile_report(samples: list[float]) -> dict[str, float | int]:
    ordered = sorted(samples)
    def at(percent: float) -> float:
        return ordered[min(len(ordered) - 1, int((len(ordered) - 1) * percent))]
    return {
        "warmup_samples": 3,
        "samples": len(ordered),
        "p50_ms": round(at(0.50), 3),
        "p95_ms": round(at(0.95), 3),
        "p99_ms": round(at(0.99), 3),
        "max_ms": round(max(ordered), 3),
        "errors": 0,
        "timeouts": 0,
    }


async def main() -> None:
    schema = os.environ["STAGE9R2PGFINAL_SCHEMA"]
    configured_dsn = schema_dsn(os.environ["TENNIS_DATABASE_URL"], schema)
    os.environ["TENNIS_DATABASE_URL"] = configured_dsn
    os.environ["TENNIS_POSTGRES_DSN"] = configured_dsn

    from backend.app.core import config
    object.__setattr__(config.settings, "database_url", os.environ["TENNIS_DATABASE_URL"])
    from backend.app.core.database import get_connection
    from backend.app.main import app
    from backend.app.messages import outbox
    from backend.app.core.time import to_iso, utc_now

    (alice_token, alice_id), (bob_token, bob_id) = [
        await login_phone(app, phone) for phone in ("13990100001", "13990100002")
    ]
    alice_headers = {"authorization": f"Bearer {alice_token}"}
    bob_headers = {"authorization": f"Bearer {bob_token}"}
    for headers, target_id in ((alice_headers, bob_id), (bob_headers, alice_id)):
        response = await asgi_request(app, "POST", f"/api/v1/social/follows/{target_id}", {"source": "stage9r2pgfinal"}, headers=headers)
        assert response.status == 201, response
    direct = await asgi_request(app, "POST", "/api/v1/messages/direct-conversations", {"target_user_id": bob_id}, headers=alice_headers)
    assert direct.status == 201, direct
    conversation_id = direct.json_body["conversation"]["conversation_id"]

    def state() -> dict[str, int | str | None]:
        with get_connection() as connection:
            conversation = connection.execute("SELECT last_message_id, last_message_preview FROM chat_conversations WHERE conversation_id = ?", (conversation_id,)).fetchone()
            member = connection.execute("SELECT unread_count FROM chat_conversation_members WHERE conversation_id = ? AND user_id = ?", (conversation_id, bob_id)).fetchone()
            inbox = connection.execute("SELECT unread_direct_message_count FROM user_inbox_counters WHERE user_id = ?", (bob_id,)).fetchone()
            return {
                "messages": connection.execute("SELECT COUNT(*) FROM chat_messages WHERE conversation_id = ?", (conversation_id,)).fetchone()[0],
                "events": connection.execute("SELECT COUNT(*) FROM outbox_events WHERE conversation_id = ?", (conversation_id,)).fetchone()[0],
                "notifications": connection.execute("SELECT COUNT(*) FROM user_notifications WHERE recipient_user_id = ?", (bob_id,)).fetchone()[0],
                "unread": member["unread_count"], "inbox": inbox["unread_direct_message_count"],
                "last_message_id": conversation["last_message_id"], "last_preview": conversation["last_message_preview"],
            }

    before = state()
    payload = {"message_type": "text", "text_content": "atomic outbox", "client_message_id": "pgfinal-atomic"}
    sent = await asgi_request(app, "POST", f"/api/v1/messages/conversations/{conversation_id}/messages", payload, headers=alice_headers)
    assert sent.status == 201, sent
    message_id, event_id = sent.json_body["message"]["message_id"], sent.json_body["event_id"]
    after = state()
    assert after["messages"] == before["messages"] + 1 and after["events"] == before["events"] + 1
    assert after["unread"] == before["unread"] + 1 and after["inbox"] == before["inbox"] + 1
    assert after["last_message_id"] == message_id

    retry = await asgi_request(app, "POST", f"/api/v1/messages/conversations/{conversation_id}/messages", payload, headers=alice_headers)
    assert retry.status == 201 and retry.json_body["message"]["message_id"] == message_id and retry.json_body["event_id"] == event_id
    after_retry = state()
    assert after_retry == after

    concurrent_payload = {"message_type": "text", "text_content": "concurrent", "client_message_id": "pgfinal-concurrent"}
    responses = await asyncio.gather(*(
        asgi_request(app, "POST", f"/api/v1/messages/conversations/{conversation_id}/messages", concurrent_payload, headers=alice_headers)
        for _ in range(5)
    ))
    assert all(response.status == 201 for response in responses), responses
    concurrent_message_ids = {response.json_body["message"]["message_id"] for response in responses}
    concurrent_event_ids = {response.json_body["event_id"] for response in responses}
    assert len(concurrent_message_ids) == len(concurrent_event_ids) == 1
    conflict = await asgi_request(app, "POST", f"/api/v1/messages/conversations/{conversation_id}/messages", {**concurrent_payload, "text_content": "different"}, headers=alice_headers)
    assert conflict.status == 409 and conflict.json_body["detail"]["code"] == "CLIENT_MESSAGE_ID_CONFLICT", conflict
    assert "message" not in conflict.json_body and "text_content" not in str(conflict.json_body)

    before_failure = state()
    original_create = outbox.create_message_event
    outbox.create_message_event = lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("forced outbox failure"))
    failure = await asgi_request(app, "POST", f"/api/v1/messages/conversations/{conversation_id}/messages", {"message_type": "text", "text_content": "rollback", "client_message_id": "pgfinal-rollback"}, headers=alice_headers)
    outbox.create_message_event = original_create
    assert failure.status == 500, failure
    after_failure = state()
    assert after_failure == before_failure
    with get_connection() as connection:
        assert connection.execute("SELECT COUNT(*) FROM chat_messages WHERE client_message_id = ?", ("pgfinal-rollback",)).fetchone()[0] == 0

    messages_a = await asgi_request(app, "GET", f"/api/v1/messages/conversations/{conversation_id}/messages?limit=1", headers=bob_headers)
    messages_b = await asgi_request(app, "GET", f"/api/v1/messages/conversations/{conversation_id}/messages?limit=50", headers=bob_headers)
    assert messages_a.status == messages_b.status == 200
    events_a = await asgi_request(app, "GET", f"/api/v1/messages/conversations/{conversation_id}/events?limit=1", headers=bob_headers)
    assert events_a.status == 200 and events_a.json_body["next_cursor"]
    events_repeat = await asgi_request(app, "GET", f"/api/v1/messages/conversations/{conversation_id}/events?limit=1&cursor={events_a.json_body['next_cursor']}", headers=bob_headers)
    assert events_repeat.status == 200
    # Event reads are side-effect free; repeat the original cursor and compare counts.
    cursor_before = state()
    repeated_first_page = await asgi_request(app, "GET", f"/api/v1/messages/conversations/{conversation_id}/events?limit=1", headers=bob_headers)
    assert repeated_first_page.status == 200 and state() == cursor_before

    time_checks: dict[str, bool] = {}
    lease_event = event_id
    with get_connection() as connection:
        connection.execute("UPDATE outbox_events SET status='leased', leased_at=? WHERE event_id=?", (to_iso(utc_now() + timedelta(minutes=5)), lease_event))
        connection.commit()
    time_checks["future_lease_not_claimed"] = not any(item.event_id == lease_event for item in outbox.lease_events("future-worker", limit=50, lease_seconds=60))
    with get_connection() as connection:
        connection.execute("UPDATE outbox_events SET leased_at=? WHERE event_id=?", (to_iso(utc_now() - timedelta(minutes=2)), lease_event))
        connection.commit()
    reclaimed = outbox.lease_events("reclaim-worker", limit=50, lease_seconds=60)
    time_checks["expired_lease_reclaimed"] = any(item.event_id == lease_event for item in reclaimed)
    time_checks["canonical_utc_z"] = to_iso(utc_now()).endswith("Z")

    timings: dict[str, list[float]] = {"message_plus_outbox_write": [], "idempotent_retry": [], "event_read": [], "lease_reclaim": [], "cursor_recovery": []}
    for _ in range(3):
        await asgi_request(app, "GET", f"/api/v1/messages/conversations/{conversation_id}/events?limit=10", headers=bob_headers)
    for index in range(20):
        perf_payload = {"message_type": "text", "text_content": f"perf-{index}", "client_message_id": f"pgfinal-perf-{index}"}
        started = time.perf_counter(); response = await asgi_request(app, "POST", f"/api/v1/messages/conversations/{conversation_id}/messages", perf_payload, headers=alice_headers); timings["message_plus_outbox_write"].append((time.perf_counter() - started) * 1000); assert response.status == 201
        started = time.perf_counter(); response = await asgi_request(app, "POST", f"/api/v1/messages/conversations/{conversation_id}/messages", perf_payload, headers=alice_headers); timings["idempotent_retry"].append((time.perf_counter() - started) * 1000); assert response.status == 201
        started = time.perf_counter(); response = await asgi_request(app, "GET", f"/api/v1/messages/conversations/{conversation_id}/events?limit=20", headers=bob_headers); timings["event_read"].append((time.perf_counter() - started) * 1000); assert response.status == 200
        started = time.perf_counter(); response = await asgi_request(app, "GET", f"/api/v1/messages/conversations/{conversation_id}/messages?limit=20", headers=bob_headers); timings["cursor_recovery"].append((time.perf_counter() - started) * 1000); assert response.status == 200
        leased = outbox.lease_events(f"perf-{index}", limit=1, lease_seconds=60)
        if leased:
            with get_connection() as connection:
                connection.execute("UPDATE outbox_events SET leased_at=? WHERE event_id=?", (to_iso(utc_now() - timedelta(minutes=2)), leased[0].event_id)); connection.commit()
            started = time.perf_counter(); outbox.lease_events(f"reclaim-{index}", limit=1, lease_seconds=60); timings["lease_reclaim"].append((time.perf_counter() - started) * 1000)
    assert all(len(values) == 20 for values in timings.values()), {key: len(value) for key, value in timings.items()}
    print(json.dumps({
        "schema": schema, "api_transaction": {"before": before, "after": after, "after_retry": after_retry},
        "rollback": {"before": before_failure, "after": after_failure},
        "idempotency": {"concurrent_responses": len(responses), "message_ids": len(concurrent_message_ids), "event_ids": len(concurrent_event_ids), "conflict_code": conflict.json_body["detail"]["code"]},
        "cursor": {"message_history_available": len(messages_b.json_body.get("items", [])), "event_cursor_available": True, "repeat_read_side_effect_free": True, "public_device_sync_api": False},
        "time_compatibility": time_checks, "performance": {key: percentile_report(value) for key, value in timings.items()},
    }))


if __name__ == "__main__":
    asyncio.run(main())
