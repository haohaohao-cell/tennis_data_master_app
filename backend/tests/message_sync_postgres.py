"""Isolated PostgreSQL regression for the Stage 11B public sync contract."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
import sys
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


async def main() -> None:
    schema = os.environ.get("STAGE11B_SCHEMA")
    source_dsn = os.environ.get("TENNIS_DATABASE_URL")
    if not schema or not source_dsn:
        raise SystemExit("STAGE11B_SCHEMA and TENNIS_DATABASE_URL are required")

    configured_dsn = schema_dsn(source_dsn, schema)
    os.environ["TENNIS_DATABASE_URL"] = configured_dsn
    os.environ["TENNIS_POSTGRES_DSN"] = configured_dsn

    from backend.app.core import config
    object.__setattr__(config.settings, "database_url", configured_dsn)
    from backend.app.core.database import get_connection
    from backend.app.main import app
    from backend.app.messages import sync as sync_service

    with get_connection() as connection:
        identity = connection.execute(
            "SELECT current_database(), current_user, current_schema();"
        ).fetchone()
        assert identity[2] == schema, identity
        table_count = connection.execute(
            "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = current_schema() AND table_type = 'BASE TABLE';"
        ).fetchone()[0]
        assert int(table_count) >= 39, table_count
        constraint_count = connection.execute(
            """
            SELECT COUNT(*)
            FROM pg_constraint
            WHERE connamespace = current_schema()::regnamespace
              AND conrelid::regclass::text IN ('messaging_devices', 'user_sync_events', 'device_sync_checkpoints')
              AND contype IN ('p', 'u', 'f', 'c');
            """
        ).fetchone()[0]
        assert int(constraint_count) >= 12, constraint_count
        index_count = connection.execute(
            """
            SELECT COUNT(*)
            FROM pg_indexes
            WHERE schemaname = current_schema()
              AND indexname IN (
                'idx_messaging_devices_user_device',
                'idx_messaging_devices_user_active',
                'idx_user_sync_events_recipient_cursor',
                'idx_user_sync_events_conversation',
                'idx_device_sync_checkpoints_user'
              );
            """
        ).fetchone()[0]
        assert int(index_count) == 5, index_count

    (alice_token, alice_id), (bob_token, bob_id) = await asyncio.gather(
        login_phone(app, "13981100001"),
        login_phone(app, "13981100002"),
    )
    alice_headers = {"authorization": f"Bearer {alice_token}"}
    bob_headers = {"authorization": f"Bearer {bob_token}"}

    device_id = "pg11b-alice-primary"
    registrations = await asyncio.gather(*(
        asgi_request(
            app,
            "POST",
            "/api/v1/messages/devices",
            {"device_id": device_id, "platform": "unknown", "app_version": "11b-pg"},
            headers=alice_headers,
        )
        for _ in range(5)
    ))
    assert all(response.status == 200 for response in registrations), registrations
    assert len({response.json_body["device"]["device_id"] for response in registrations}) == 1
    conflict = await asgi_request(
        app,
        "POST",
        "/api/v1/messages/devices",
        {"device_id": device_id, "platform": "unknown"},
        headers=bob_headers,
    )
    assert conflict.status == 409
    assert conflict.json_body["detail"]["code"] == "MESSAGING_DEVICE_OWNERSHIP_CONFLICT"

    second_device = await asgi_request(
        app,
        "POST",
        "/api/v1/messages/devices",
        {"device_id": "pg11b-alice-second", "platform": "unknown"},
        headers=alice_headers,
    )
    assert second_device.status == 200, second_device
    initial = await asgi_request(
        app,
        "GET",
        f"/api/v1/messages/sync?device_id={device_id}&limit=10",
        headers=alice_headers,
    )
    assert initial.status == 200 and initial.json_body["items"] == [], initial

    for headers, target_id in ((alice_headers, bob_id), (bob_headers, alice_id)):
        followed = await asgi_request(
            app,
            "POST",
            f"/api/v1/social/follows/{target_id}",
            {"source": "stage11b-pg"},
            headers=headers,
        )
        assert followed.status in (200, 201), followed
    direct = await asgi_request(
        app,
        "POST",
        "/api/v1/messages/direct-conversations",
        {"target_user_id": bob_id},
        headers=alice_headers,
    )
    assert direct.status == 201, direct
    conversation_id = direct.json_body["conversation"]["conversation_id"]

    sent = await asgi_request(
        app,
        "POST",
        f"/api/v1/messages/conversations/{conversation_id}/messages",
        {"message_type": "text", "text_content": "pg sync private", "client_message_id": "pg11b-first"},
        headers=alice_headers,
    )
    assert sent.status == 201, sent
    event_id = sent.json_body["event_id"]

    alice_sync = await asgi_request(
        app,
        "GET",
        f"/api/v1/messages/sync?device_id={device_id}&limit=1",
        headers=alice_headers,
    )
    assert alice_sync.status == 200 and alice_sync.json_body["items"], alice_sync
    assert alice_sync.json_body["items"][0]["event_id"] == event_id
    assert "pg sync private" not in str(alice_sync.json_body)
    cursor = alice_sync.json_body["next_cursor"]
    assert cursor

    bob_sync = await asgi_request(
        app,
        "GET",
        "/api/v1/messages/sync?device_id=pg11b-bob-primary&limit=10",
        headers=bob_headers,
    )
    assert bob_sync.status == 404 or bob_sync.json_body.get("detail", {}).get("code") == "MESSAGING_DEVICE_NOT_FOUND"
    bob_device = await asgi_request(
        app,
        "POST",
        "/api/v1/messages/devices",
        {"device_id": "pg11b-bob-primary", "platform": "unknown"},
        headers=bob_headers,
    )
    assert bob_device.status == 200, bob_device
    bob_sync = await asgi_request(
        app,
        "GET",
        "/api/v1/messages/sync?device_id=pg11b-bob-primary&limit=10",
        headers=bob_headers,
    )
    assert bob_sync.status == 200
    assert [item["event_id"] for item in bob_sync.json_body["items"]] == [event_id]

    checkpoint_responses = await asyncio.gather(*(
        asgi_request(
            app,
            "POST",
            "/api/v1/messages/sync/checkpoints",
            {"device_id": device_id, "cursor": cursor},
            headers=alice_headers,
        )
        for _ in range(5)
    ))
    assert all(response.status == 200 for response in checkpoint_responses), checkpoint_responses
    with get_connection() as connection:
        checkpoint = connection.execute(
            "SELECT user_id, device_id, cursor FROM device_sync_checkpoints WHERE device_id = ?;",
            (device_id,),
        ).fetchone()
        assert checkpoint["user_id"] == alice_id and checkpoint["cursor"] == cursor
        event_count = connection.execute(
            "SELECT COUNT(*) FROM user_sync_events WHERE recipient_user_id = ? AND event_id = ?;",
            (bob_id, event_id),
        ).fetchone()[0]
        assert event_count == 1
    backward_checkpoint = await asgi_request(
        app,
        "POST",
        "/api/v1/messages/sync/checkpoints",
        {"device_id": device_id, "cursor": cursor},
        headers=alice_headers,
    )
    assert backward_checkpoint.status == 200
    assert backward_checkpoint.json_body["cursor"] == cursor

    foreign_cursor = await asgi_request(
        app,
        "GET",
        f"/api/v1/messages/sync?device_id=pg11b-bob-primary&cursor={cursor}&limit=10",
        headers=bob_headers,
    )
    assert foreign_cursor.status == 400
    assert foreign_cursor.json_body["detail"]["code"] == "SYNC_CURSOR_INVALID"

    expired_cursor = sync_service._encode_cursor(alice_id, device_id, "2000-01-01T00:00:00Z", event_id)
    expired = await asgi_request(
        app,
        "GET",
        f"/api/v1/messages/sync?device_id={device_id}&cursor={expired_cursor}&limit=10",
        headers=alice_headers,
    )
    assert expired.status == 409
    assert expired.json_body["detail"]["code"] == "SYNC_CURSOR_EXPIRED"
    assert expired.json_body["detail"]["requires_full_reconciliation"] is True

    original_append = sync_service.append_conversation_event

    def fail_sync_event(*_: object, **__: object) -> None:
        raise RuntimeError("stage11b postgres rollback injection")

    sync_service.append_conversation_event = fail_sync_event
    try:
        rollback = await asgi_request(
            app,
            "POST",
            f"/api/v1/messages/conversations/{conversation_id}/messages",
            {"message_type": "text", "text_content": "rollback only", "client_message_id": "pg11b-rollback"},
            headers=alice_headers,
        )
    finally:
        sync_service.append_conversation_event = original_append
    assert rollback.status == 500, rollback
    with get_connection() as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM chat_messages WHERE client_message_id = ?;", ("pg11b-rollback",)
        ).fetchone()[0] == 0

    revoked = await asgi_request(
        app,
        "DELETE",
        f"/api/v1/messages/devices/{device_id}",
        headers=alice_headers,
    )
    assert revoked.status == 200 and revoked.json_body["device"]["revoked_at"], revoked
    revoked_sync = await asgi_request(
        app,
        "GET",
        f"/api/v1/messages/sync?device_id={device_id}&limit=10",
        headers=alice_headers,
    )
    assert revoked_sync.status == 403
    assert revoked_sync.json_body["detail"]["code"] == "MESSAGING_DEVICE_REVOKED"
    revoked_checkpoint = await asgi_request(
        app,
        "POST",
        "/api/v1/messages/sync/checkpoints",
        {"device_id": device_id, "cursor": cursor},
        headers=alice_headers,
    )
    assert revoked_checkpoint.status == 403

    print("Message sync PostgreSQL isolated-schema test passed.")


if __name__ == "__main__":
    asyncio.run(main())
