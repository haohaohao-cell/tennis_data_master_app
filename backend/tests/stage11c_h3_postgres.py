"""Isolated PostgreSQL concurrency and recovery regression for Fake Push.

This is a local thread-based database-lock test, not a distributed-worker or
production throughput claim.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import sys
import uuid
from urllib.parse import parse_qsl, quote, urlsplit, urlunsplit

from fastapi import HTTPException

ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT_DIR))


def _scoped_dsn(source: str, schema: str) -> str:
    parts = urlsplit(source)
    query = [(key, value) for key, value in parse_qsl(parts.query, keep_blank_values=True) if key != "options"]
    query.append(("options", f"-c search_path={schema},pg_catalog"))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "&".join(f"{quote(key)}={quote(value)}" for key, value in query), parts.fragment))


def main() -> None:
    schema, source = os.environ.get("STAGE11H3_SCHEMA"), os.environ.get("TENNIS_DATABASE_URL")
    if not schema or not source:
        raise SystemExit("STAGE11H3_SCHEMA and TENNIS_DATABASE_URL are required")
    from backend.app.core import config

    object.__setattr__(config.settings, "database_url", _scoped_dsn(source, schema))
    object.__setattr__(config.settings, "message_push_enabled", True)
    object.__setattr__(config.settings, "message_push_fake_provider_enabled", True)
    object.__setattr__(config.settings, "message_push_token_registration_enabled", True)
    object.__setattr__(config.settings, "message_push_max_attempts", 2)
    from backend.app.core.database import get_connection, transaction
    from backend.app.messages import push, sync
    from backend.app.messages.schemas import DirectMessagePushDeliveryRequest, MessageDeviceRegisterRequest, PushTokenRegisterRequest

    suffix = uuid.uuid4().hex[:10]
    user_id = f"h3-user-{suffix}"
    with transaction() as connection:
        connection.execute("INSERT INTO users (user_id, phone, nickname) VALUES (?, ?, ?);", (user_id, f"136{suffix[:8]}", "H3"))
    first_device = sync.register_device(user_id, MessageDeviceRegisterRequest(device_id=f"h3-device-{suffix}-1")).device
    push.register_token(user_id, first_device.device_id, PushTokenRegisterRequest(token=f"fake_success_h3_{suffix}_1"))
    event_id = f"direct_message:h3-event-{suffix}"
    request = DirectMessagePushDeliveryRequest.model_validate({
        "push_kind": "direct_message", "recipient_user_id": user_id, "delivery_id": event_id,
        "preference_kind": "direct_message", "notification_type": None,
        "target": {"type": "chat", "conversation_id": f"h3-conversation-{suffix}"},
        "display": {"title": "redacted", "body": None},
        "data": {"type": "direct_message", "message_id": event_id.partition(":")[2], "sender_user_id": "other"},
    })
    with ThreadPoolExecutor(max_workers=4) as workers:
        responses = list(workers.map(lambda _: push.create_deliveries(request), range(4)))
    assert all(len(response) == 1 for response in responses)
    with get_connection() as connection:
        assert connection.execute("SELECT COUNT(*) FROM push_deliveries WHERE event_id = ?;", (event_id,)).fetchone()[0] == 1

    # Two local worker threads compete for one eligible delivery. Only one wins.
    with ThreadPoolExecutor(max_workers=2) as workers:
        claimed = list(workers.map(push.claim_delivery, ("h3-worker-a", "h3-worker-b")))
    winners = [row for row in claimed if row is not None]
    assert len(winners) == 1
    first = winners[0]
    assert push.claim_delivery("h3-worker-c") is None
    with get_connection() as connection:
        held = connection.execute("SELECT status, lease_owner FROM push_deliveries WHERE delivery_id = ?;", (first["delivery_id"],)).fetchone()
        assert held["status"] == "leased" and held["lease_owner"] in {"h3-worker-a", "h3-worker-b"}
        connection.execute("UPDATE push_deliveries SET leased_at = '2000-01-01T00:00:00Z' WHERE delivery_id = ?;", (first["delivery_id"],))
        connection.commit()
    reclaimed = push.claim_delivery("h3-worker-recovery")
    assert reclaimed is not None and reclaimed["delivery_id"] == first["delivery_id"]
    with get_connection() as connection:
        reclaim_count = connection.execute("SELECT lease_reclaim_count FROM push_deliveries WHERE delivery_id = ?;", (first["delivery_id"],)).fetchone()[0]
    assert reclaim_count == 1

    # A revoked device cancels its leased delivery without a provider call.
    sync.revoke_device(user_id, first_device.device_id)
    with transaction() as connection:
        connection.execute("UPDATE push_deliveries SET leased_at = '2000-01-01T00:00:00Z' WHERE delivery_id = ?;", (reclaimed["delivery_id"],))
    provider = push.FakePushProvider()
    cancelled = push.process_delivery("h3-worker-after-crash", provider)
    assert cancelled is not None and cancelled.status == "cancelled" and provider.results == []

    # A second device receives an independent delivery for the same event.
    second_device = sync.register_device(user_id, MessageDeviceRegisterRequest(device_id=f"h3-device-{suffix}-2")).device
    push.register_token(user_id, second_device.device_id, PushTokenRegisterRequest(token=f"fake_success_h3_{suffix}_2"))
    deliveries = push.create_deliveries(request)
    assert len(deliveries) == 1 and deliveries[0].device_id == second_device.device_id
    # A send-time preference decision suppresses delivery before provider I/O.
    second_delivery = deliveries[0]
    with transaction() as connection:
        connection.execute("UPDATE push_deliveries SET status = 'pending', available_at = CURRENT_TIMESTAMP WHERE delivery_id = ?;", (second_delivery.delivery_id,))
    original_allowed = push._refresh_allowed
    push._refresh_allowed = lambda row: False
    try:
        suppressed = push.process_delivery("h3-worker-preference", provider)
    finally:
        push._refresh_allowed = original_allowed
    assert suppressed is not None and suppressed.status == "suppressed" and provider.results == []

    metrics = push.delivery_metrics()
    assert metrics["cancelled"] == 1 and metrics["suppressed"] == 1 and metrics["lease_reclaims"] == 2
    metrics_text = str(metrics).lower()
    assert f"fake_success_h3_{suffix}" not in metrics_text
    assert "redacted" not in metrics_text and "postgresql://" not in metrics_text and "\\" not in metrics_text
    print("Stage 11C-H3 PostgreSQL concurrency and recovery test passed.")


if __name__ == "__main__":
    main()
