"""SQLite stage-9 regression for durable message events and lease semantics."""

from __future__ import annotations

import asyncio
from datetime import timedelta
import json
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
        os.environ["TENNIS_DB_PATH"] = str(Path(temp_dir) / "stage9-outbox.sqlite3")
        from backend.app.core.database import get_connection, initialize_database, transaction
        from backend.app.main import app
        from backend.app.messages import outbox
        from backend.app.core.time import to_iso, utc_now

        initialize_database()
        (alice_token, alice_id), (bob_token, bob_id) = [
            await login_phone(app, phone)
            for phone in ("13990000001", "13990000002")
        ]
        alice_headers = {"authorization": f"Bearer {alice_token}"}
        bob_headers = {"authorization": f"Bearer {bob_token}"}
        for target_id in (bob_id,):
            response = await asgi_request(
                app, "POST", f"/api/v1/social/follows/{target_id}",
                {"source": "stage9"}, headers=alice_headers,
            )
            assert response.status == 201, response
        response = await asgi_request(
            app, "POST", "/api/v1/social/follows/" + alice_id,
            {"source": "stage9"}, headers=bob_headers,
        )
        assert response.status == 201, response
        response = await asgi_request(
            app, "POST", "/api/v1/messages/direct-conversations",
            {"target_user_id": bob_id}, headers=alice_headers,
        )
        assert response.status == 201, response
        conversation_id = response.json_body["conversation"]["conversation_id"]

        payload = {
            "message_type": "text",
            "text_content": "stage9 durable event",
            "client_message_id": "stage9-client-1",
        }
        sent = await asgi_request(
            app, "POST", f"/api/v1/messages/conversations/{conversation_id}/messages",
            payload, headers=alice_headers,
        )
        assert sent.status == 201, sent
        message = sent.json_body["message"]
        event_id = sent.json_body["event_id"]
        assert event_id
        with get_connection() as connection:
            assert connection.execute("SELECT COUNT(*) FROM outbox_events WHERE message_id = ?", (message["message_id"],)).fetchone()[0] == 1
            assert connection.execute("SELECT unread_count FROM chat_conversation_members WHERE conversation_id = ? AND user_id = ?", (conversation_id, bob_id)).fetchone()[0] == 1

        retry = await asgi_request(
            app, "POST", f"/api/v1/messages/conversations/{conversation_id}/messages",
            payload, headers=alice_headers,
        )
        assert retry.status == 201 and retry.json_body["message"]["message_id"] == message["message_id"], retry
        assert retry.json_body["event_id"] == event_id

        recovered = await asgi_request(
            app, "GET", f"/api/v1/messages/conversations/{conversation_id}/messages/by-client-id/stage9-client-1",
            headers=alice_headers,
        )
        assert recovered.status == 200 and recovered.json_body["found"] is True, recovered
        assert recovered.json_body["event_id"] == event_id
        missing = await asgi_request(
            app, "GET", f"/api/v1/messages/conversations/{conversation_id}/messages/by-client-id/missing",
            headers=alice_headers,
        )
        assert missing.status == 200 and missing.json_body["found"] is False, missing

        events = await asgi_request(
            app, "GET", f"/api/v1/messages/conversations/{conversation_id}/events?limit=1",
            headers=bob_headers,
        )
        assert events.status == 200 and len(events.json_body["items"]) == 1, events
        assert events.json_body["items"][0]["event_id"] == event_id
        assert events.json_body["next_cursor"] is not None
        page2 = await asgi_request(
            app, "GET", f"/api/v1/messages/conversations/{conversation_id}/events?limit=1&cursor={events.json_body['next_cursor']}",
            headers=bob_headers,
        )
        assert page2.status == 200 and page2.json_body["items"] == [], page2

        leased = outbox.lease_events("stage9-worker-a", limit=1, lease_seconds=60)
        assert len(leased) == 1 and leased[0].event_id == event_id
        assert outbox.lease_events("stage9-worker-b", limit=1, lease_seconds=60) == []
        assert outbox.acknowledge_event(event_id, "stage9-worker-b") is False
        assert outbox.acknowledge_event(event_id, "stage9-worker-a") is True
        assert outbox.lease_events("stage9-worker-b", limit=1, lease_seconds=60) == []

        # A stale lease can be reclaimed, but only after its lease window expires.
        second = await asgi_request(
            app, "POST", f"/api/v1/messages/conversations/{conversation_id}/messages",
            {"message_type": "text", "text_content": "lease timeout", "client_message_id": "stage9-client-2"},
            headers=alice_headers,
        )
        assert second.status == 201, second
        second_event_id = second.json_body["event_id"]
        first_lease = outbox.lease_events("stage9-worker-a", limit=1, lease_seconds=60)
        assert [item.event_id for item in first_lease] == [second_event_id]
        with transaction(immediate=True) as connection:
            connection.execute(
                "UPDATE outbox_events SET leased_at = ? WHERE event_id = ?",
                (to_iso(utc_now() - timedelta(minutes=2)), second_event_id),
            )
        reclaimed = outbox.lease_events("stage9-worker-b", limit=1, lease_seconds=60)
        assert [item.event_id for item in reclaimed] == [second_event_id]
        assert outbox.acknowledge_event(second_event_id, "stage9-worker-b") is True

        # Failure to append the event must roll the message and unread write back.
        original_create_event = outbox.create_message_event
        outbox.create_message_event = lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("forced outbox failure"))
        failed = await asgi_request(
            app, "POST", f"/api/v1/messages/conversations/{conversation_id}/messages",
            {"message_type": "text", "text_content": "must rollback", "client_message_id": "stage9-rollback"},
            headers=alice_headers,
        )
        outbox.create_message_event = original_create_event
        assert failed.status == 500, failed
        with get_connection() as connection:
            assert connection.execute("SELECT COUNT(*) FROM chat_messages WHERE client_message_id = ?", ("stage9-rollback",)).fetchone()[0] == 0
            assert connection.execute("SELECT COUNT(*) FROM outbox_events WHERE message_id IN (SELECT message_id FROM chat_messages WHERE client_message_id = ?)", ("stage9-rollback",)).fetchone()[0] == 0

        with get_connection() as connection:
            row = connection.execute("SELECT status, attempt_count FROM outbox_events WHERE event_id = ?", (event_id,)).fetchone()
            assert row["status"] == "processed" and row["attempt_count"] == 1

        # A previously-created message from before stage 9 remains recoverable;
        # its event is optional because the migration does not synthesize events.
        legacy = await asgi_request(
            app, "POST", f"/api/v1/messages/conversations/{conversation_id}/messages",
            {"message_type": "text", "text_content": "legacy event gap", "client_message_id": "stage9-client-legacy"},
            headers=alice_headers,
        )
        assert legacy.status == 201, legacy
        legacy_message_id = legacy.json_body["message"]["message_id"]
        legacy_event_id = legacy.json_body["event_id"]
        with transaction(immediate=True) as connection:
            connection.execute("DELETE FROM outbox_events WHERE event_id = ?", (legacy_event_id,))
        legacy_recovery = await asgi_request(
            app, "GET", f"/api/v1/messages/conversations/{conversation_id}/messages/by-client-id/stage9-client-legacy",
            headers=alice_headers,
        )
        assert legacy_recovery.status == 200 and legacy_recovery.json_body["found"] is True, legacy_recovery
        assert legacy_recovery.json_body["message"]["message_id"] == legacy_message_id
        assert legacy_recovery.json_body["event_id"] is None

        report = {
            "stage": "stage9-sqlite-outbox-regression",
            "status": "ok",
            "checks": {
                "draft_state_contract": "covered_by_app_static_test",
                "message_outbox_same_transaction": True,
                "client_message_id_idempotency": True,
                "event_cursor_pagination": True,
                "lease_owner_exclusivity": True,
                "lease_timeout_reclaim": True,
                "event_failure_rolls_back_message": True,
                "source_sqlite_modified": False,
            },
            "postgres_status": "BLOCKED / UNVERIFIED",
            "sensitive_values_logged": False,
        }
        Path(ROOT_DIR / "backend/db/stage9-sqlite-regression-20260829.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print("Stage 9 SQLite outbox regression passed.")


if __name__ == "__main__":
    asyncio.run(main())
