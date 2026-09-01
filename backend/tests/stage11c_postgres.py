"""Isolated PostgreSQL regression for Stage 11C token and delivery primitives."""

from __future__ import annotations

import os
from pathlib import Path
import sys
import uuid
from urllib.parse import parse_qsl, quote, urlsplit, urlunsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


def main() -> None:
    schema = os.environ.get("STAGE11C_SCHEMA")
    source = os.environ.get("TENNIS_DATABASE_URL")
    if not schema or not source:
        raise SystemExit("STAGE11C_SCHEMA and TENNIS_DATABASE_URL are required")
    parts = urlsplit(source)
    query = [(key, value) for key, value in parse_qsl(parts.query, keep_blank_values=True) if key != "options"]
    query.append(("options", f"-c search_path={schema},pg_catalog"))
    scoped = urlunsplit((parts.scheme, parts.netloc, parts.path, "&".join(f"{quote(key)}={quote(value)}" for key, value in query), parts.fragment))
    os.environ["TENNIS_DATABASE_URL"] = scoped
    os.environ["TENNIS_POSTGRES_DSN"] = scoped
    from backend.app.core import config

    object.__setattr__(config.settings, "database_url", scoped)
    object.__setattr__(config.settings, "message_push_enabled", True)
    object.__setattr__(config.settings, "message_push_fake_provider_enabled", True)
    object.__setattr__(config.settings, "message_push_token_registration_enabled", True)
    from backend.app.core.database import get_connection, transaction
    from backend.app.messages import push, sync
    from backend.app.messages.schemas import DirectMessagePushDeliveryRequest, MessageDeviceRegisterRequest, PushTokenRegisterRequest

    suffix = uuid.uuid4().hex[:10]
    user_id = f"pg11c-{suffix}"
    device_id = f"pg11c-device-{suffix}"
    event_id = f"direct_message:pg11c-event-{suffix}"
    with transaction() as connection:
        connection.execute("INSERT INTO users (user_id, phone, nickname) VALUES (?, ?, ?);", (user_id, f"139{suffix[:8]}", "PG Stage 11C"))
    device = sync.register_device(user_id, MessageDeviceRegisterRequest(device_id=device_id))
    token = push.register_token(user_id, device.device.device_id, PushTokenRegisterRequest(token=f"fake_success_{suffix}"))
    request = DirectMessagePushDeliveryRequest.model_validate({
        "push_kind": "direct_message", "recipient_user_id": user_id, "delivery_id": event_id,
        "preference_kind": "direct_message", "notification_type": None,
        "target": {"type": "chat", "conversation_id": "pg-stage11c-conversation"},
        "display": {"title": "safe", "body": "never sent to provider"},
        "data": {"type": "direct_message", "message_id": event_id.split(":", 1)[1], "sender_user_id": "pg-other"},
    })
    first = push.create_deliveries(request)
    second = push.create_deliveries(request)
    original = push._refresh_allowed
    push._refresh_allowed = lambda row: True
    try:
        sent = push.process_delivery("pg-stage11c-worker")
    finally:
        push._refresh_allowed = original
    with get_connection() as connection:
        count = connection.execute("SELECT COUNT(*) FROM push_deliveries WHERE event_id = ?;", (request.delivery_id,)).fetchone()[0]
        status = connection.execute("SELECT status FROM push_deliveries WHERE delivery_id = ?;", (first[0].delivery_id,)).fetchone()[0]
        raw = connection.execute("SELECT token_ciphertext FROM push_device_tokens WHERE token_id = ?;", (token.token_id,)).fetchone()[0]
    assert len(first) == 1 and len(second) == 1 and count == 1
    assert sent is not None and sent.status == "sent" and status == "sent" and raw != f"fake_success_{suffix}"
    provider = push.FakePushProvider()
    assert provider.send(f"fake_success_{suffix}", {}).outcome == "success"
    assert provider.send("fake_retry_pg", {}).outcome == "retryable"
    assert provider.send("fake_permanent_pg", {}).outcome == "permanent"
    assert provider.send("fake_invalid_pg", {}).outcome == "invalid_token"
    assert provider.send("fake_timeout_pg", {}).error_code == "PROVIDER_TIMEOUT"
    print("Stage 11C PostgreSQL isolated fake push test passed.")


if __name__ == "__main__":
    main()
