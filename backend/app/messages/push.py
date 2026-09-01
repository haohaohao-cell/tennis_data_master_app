"""Provider-independent push token and fake delivery infrastructure.

This module deliberately stops at a local fake provider. Delivery rows are
created after the domain transaction has committed and are never the source
of truth for message state.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import timedelta
import hashlib
import hmac
import os
import uuid

from fastapi import status

from backend.app.auth.service import raise_api_error
from backend.app.core.config import settings
from backend.app.core.database import get_connection, transaction
from backend.app.core.time import to_iso, utc_now, utc_now_iso
from backend.app.messages.schemas import (
    MessagingPushDeliveryRequest,
    PushDeliveryResponse,
    PushTokenRegisterRequest,
    PushTokenResponse,
)


MAX_TOKEN_BYTES = 512
LEASE_SECONDS = 60
RETRY_DELAYS_SECONDS = (5, 30, 300)


@dataclass(frozen=True)
class FakeProviderResult:
    outcome: str
    provider_message_id: str | None = None
    error_code: str | None = None
    error_message: str | None = None


def _key() -> bytes:
    return settings.message_push_token_key.encode("utf-8")


def token_fingerprint(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _crypt(token: str) -> str:
    nonce = os.urandom(16)
    raw = token.encode("utf-8")
    stream = b"".join(hmac.new(_key(), nonce + index.to_bytes(4, "big"), hashlib.sha256).digest() for index in range((len(raw) + 31) // 32))
    ciphertext = bytes(value ^ stream[index] for index, value in enumerate(raw))
    mac = hmac.new(_key(), nonce + ciphertext, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(nonce + mac + ciphertext).decode("ascii")


def _decrypt(value: str) -> str:
    encoded = base64.urlsafe_b64decode(value.encode("ascii"))
    nonce, mac, ciphertext = encoded[:16], encoded[16:48], encoded[48:]
    expected = hmac.new(_key(), nonce + ciphertext, hashlib.sha256).digest()
    if not hmac.compare_digest(mac, expected):
        raise RuntimeError("push token ciphertext integrity failure")
    stream = b"".join(hmac.new(_key(), nonce + index.to_bytes(4, "big"), hashlib.sha256).digest() for index in range((len(ciphertext) + 31) // 32))
    return bytes(value ^ stream[index] for index, value in enumerate(ciphertext)).decode("utf-8")


def _token_response(row: object) -> PushTokenResponse:
    return PushTokenResponse(
        token_id=row["token_id"], device_id=row["device_id"], provider=row["provider"],
        environment=row["environment"], status=row["status"], token_fingerprint=row["token_fingerprint"],
        created_at=row["created_at"], rotated_at=row["rotated_at"], revoked_at=row["revoked_at"],
    )


def _select_device(connection: object, user_id: str, device_id: str, active_only: bool = True) -> object:
    query = "SELECT * FROM messaging_devices WHERE device_id = ? AND user_id = ?"
    if active_only:
        query += " AND revoked_at IS NULL"
    row = connection.execute(query + " LIMIT 1;", (device_id, user_id)).fetchone()
    if row is None:
        raise_api_error(status.HTTP_403_FORBIDDEN, "PUSH_DEVICE_NOT_AVAILABLE", "The messaging device is not available.")
    return row


def register_token(user_id: str, device_id: str, payload: PushTokenRegisterRequest) -> PushTokenResponse:
    if not settings.message_push_token_registration_enabled:
        raise_api_error(status.HTTP_503_SERVICE_UNAVAILABLE, "PUSH_TOKEN_REGISTRATION_DISABLED", "Push token registration is disabled.")
    if not payload.token.startswith("fake_"):
        raise_api_error(status.HTTP_422_UNPROCESSABLE_ENTITY, "FAKE_PUSH_TOKEN_REQUIRED", "Only fake test tokens are accepted.")
    if len(payload.token.encode("utf-8")) > MAX_TOKEN_BYTES:
        raise_api_error(status.HTTP_422_UNPROCESSABLE_ENTITY, "PUSH_TOKEN_TOO_LARGE", "The push token is too large.")
    fingerprint = token_fingerprint(payload.token)
    now = utc_now_iso()
    with transaction(immediate=True, lock_key=f"push-token:{fingerprint}") as connection:
        _select_device(connection, user_id, device_id)
        existing = connection.execute(
            "SELECT * FROM push_device_tokens WHERE provider = ? AND environment = ? AND token_fingerprint = ? LIMIT 1;",
            (payload.provider, payload.environment, fingerprint),
        ).fetchone()
        if existing is not None and existing["user_id"] != user_id:
            raise_api_error(status.HTTP_409_CONFLICT, "PUSH_TOKEN_OWNERSHIP_CONFLICT", "The push token belongs to another user.")
        if existing is not None and existing["device_id"] != device_id:
            raise_api_error(status.HTTP_409_CONFLICT, "PUSH_TOKEN_DEVICE_CONFLICT", "The push token is registered to another device.")
        if existing is not None and existing["device_id"] == device_id and existing["status"] == "active":
            row = existing
        else:
            connection.execute(
                "UPDATE push_device_tokens SET status = 'revoked', revoked_at = ?, updated_at = ? WHERE user_id = ? AND device_id = ? AND status = 'active';",
                (now, now, user_id, device_id),
            )
            if existing is not None:
                connection.execute(
                    "UPDATE push_device_tokens SET status = 'active', revoked_at = NULL, invalid_reason = NULL, rotated_at = ?, updated_at = ? WHERE token_id = ?;",
                    (now, now, existing["token_id"]),
                )
                row = connection.execute("SELECT * FROM push_device_tokens WHERE token_id = ?;", (existing["token_id"],)).fetchone()
            else:
                token_id = str(uuid.uuid4())
                connection.execute(
                    "INSERT INTO push_device_tokens (token_id, user_id, device_id, provider, environment, token_ciphertext, token_fingerprint, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);",
                    (token_id, user_id, device_id, payload.provider, payload.environment, _crypt(payload.token), fingerprint, now, now),
                )
                row = connection.execute("SELECT * FROM push_device_tokens WHERE token_id = ?;", (token_id,)).fetchone()
    if row is None:
        raise RuntimeError("push token registration did not produce a row")
    return _token_response(row)


def revoke_token(user_id: str, device_id: str, token_id: str) -> PushTokenResponse:
    now = utc_now_iso()
    with transaction(immediate=True, lock_key=f"push-device:{device_id}") as connection:
        _select_device(connection, user_id, device_id, active_only=False)
        connection.execute(
            "UPDATE push_device_tokens SET status = 'revoked', revoked_at = COALESCE(revoked_at, ?), updated_at = ? WHERE token_id = ? AND user_id = ? AND device_id = ?;",
            (now, now, token_id, user_id, device_id),
        )
        row = connection.execute("SELECT * FROM push_device_tokens WHERE token_id = ? AND user_id = ? AND device_id = ?;", (token_id, user_id, device_id)).fetchone()
    if row is None:
        raise_api_error(status.HTTP_404_NOT_FOUND, "PUSH_TOKEN_NOT_FOUND", "The push token was not found.")
    return _token_response(row)


def revoke_device_tokens(user_id: str, device_id: str) -> int:
    now = utc_now_iso()
    with transaction(immediate=True, lock_key=f"push-device:{device_id}") as connection:
        result = connection.execute(
            "UPDATE push_device_tokens SET status = 'revoked', revoked_at = COALESCE(revoked_at, ?), updated_at = ? WHERE user_id = ? AND device_id = ? AND status = 'active';",
            (now, now, user_id, device_id),
        )
    return int(result.rowcount or 0)


def _safe_payload(request: MessagingPushDeliveryRequest) -> dict[str, object]:
    return {
        "type": request.push_kind,
        "target": request.target.model_dump(exclude_none=True),
        "data": request.data.model_dump(exclude_none=True),
    }


class FakePushProvider:
    """Deterministic local provider; token prefixes inject failure modes."""

    def __init__(self) -> None:
        self.results: list[dict[str, str]] = []

    def send(self, token: str, payload: dict[str, object]) -> FakeProviderResult:
        del payload
        if not settings.message_push_fake_provider_enabled:
            result = FakeProviderResult("permanent", error_code="PROVIDER_DISABLED", error_message="fake provider disabled")
            self.results.append({"outcome": result.outcome, "error_code": result.error_code or ""})
            return result
        if not token.startswith("fake_"):
            result = FakeProviderResult("invalid_token", error_code="INVALID_TOKEN", error_message="test token rejected")
            self.results.append({"outcome": result.outcome, "error_code": result.error_code or ""})
            return result
        if "invalid" in token:
            result = FakeProviderResult("invalid_token", error_code="INVALID_TOKEN", error_message="test token rejected")
            self.results.append({"outcome": result.outcome, "error_code": result.error_code or ""})
            return result
        if "timeout" in token:
            result = FakeProviderResult("retryable", error_code="PROVIDER_TIMEOUT", error_message="fake timeout")
            self.results.append({"outcome": result.outcome, "error_code": result.error_code or ""})
            return result
        if "retry" in token:
            result = FakeProviderResult("retryable", error_code="PROVIDER_RETRYABLE", error_message="fake retry")
            self.results.append({"outcome": result.outcome, "error_code": result.error_code or ""})
            return result
        if "permanent" in token:
            result = FakeProviderResult("permanent", error_code="PROVIDER_REJECTED", error_message="fake permanent failure")
            self.results.append({"outcome": result.outcome, "error_code": result.error_code or ""})
            return result
        result = FakeProviderResult("success", provider_message_id=f"fake:{uuid.uuid4()}")
        self.results.append({"outcome": result.outcome})
        return result


def create_deliveries(request: MessagingPushDeliveryRequest) -> list[PushDeliveryResponse]:
    if request.push_kind not in {"direct_message", "message_request", "notification_event"}:
        return []
    now = utc_now_iso()
    created: list[PushDeliveryResponse] = []
    with transaction(immediate=True, lock_key=f"push-event:{request.delivery_id}") as connection:
        if not settings.message_push_enabled:
            return []
        devices = connection.execute(
            "SELECT token_id, device_id FROM push_device_tokens WHERE user_id = ? AND status = 'active' ORDER BY device_id, token_id;",
            (request.recipient_user_id,),
        ).fetchall()
        for device in devices:
            delivery_id = f"{request.delivery_id}:{device['device_id']}"
            connection.execute(
                "INSERT INTO push_deliveries (delivery_id, event_id, user_id, device_id, token_id, channel, push_kind, created_at, updated_at) VALUES (?, ?, ?, ?, ?, 'push', ?, ?, ?) ON CONFLICT (event_id, device_id, channel) DO NOTHING;",
                (delivery_id, request.delivery_id, request.recipient_user_id, device["device_id"], device["token_id"], request.push_kind, now, now),
            )
            row = connection.execute("SELECT * FROM push_deliveries WHERE event_id = ? AND device_id = ? AND channel = 'push';", (request.delivery_id, device["device_id"])).fetchone()
            if row is not None:
                created.append(_delivery_response(row))
    return created


def consume_outbox_event(event: object) -> int:
    """Create post-commit deliveries for a leased message event.

    This consumer only creates durable delivery work. Provider calls remain in
    ``process_delivery`` and therefore cannot roll back the message commit.
    """
    if event["event_type"] != "message.created":
        return 0
    with get_connection() as connection:
        recipients = connection.execute(
            "SELECT user_id FROM chat_conversation_members WHERE conversation_id = ? AND user_id <> ? AND status = 'active' AND deleted_at IS NULL;",
            (event["conversation_id"], event["actor_user_id"]),
        ).fetchall()
    created = 0
    for recipient in recipients:
        from backend.app.messages import service

        intent = service.build_direct_message_push_intent(recipient["user_id"], event["message_id"])
        if intent.request is not None and intent.decision in {"eligible", "eligible_without_preference_mapping"}:
            created += len(create_deliveries(intent.request))
    return created


def _delivery_response(row: object) -> PushDeliveryResponse:
    return PushDeliveryResponse(
        delivery_id=row["delivery_id"], event_id=row["event_id"], device_id=row["device_id"], token_id=row["token_id"],
        channel=row["channel"], status=row["status"], attempt_count=row["attempt_count"], error_code=row["error_code"],
    )


def claim_delivery(worker_id: str) -> object | None:
    now = utc_now()
    lease_until = to_iso(now + timedelta(seconds=LEASE_SECONDS))
    with transaction(immediate=True, lock_key="push-claim") as connection:
        connection.execute(
            "UPDATE push_deliveries SET status = 'pending', leased_at = NULL, lease_owner = NULL, "
            "lease_reclaim_count = lease_reclaim_count + 1, updated_at = ? "
            "WHERE status = 'leased' AND leased_at < ?;",
            (utc_now_iso(), to_iso(now - timedelta(seconds=LEASE_SECONDS))),
        )
        row = connection.execute("SELECT * FROM push_deliveries WHERE status IN ('pending', 'retryable') AND available_at <= ? ORDER BY created_at, delivery_id LIMIT 1;", (utc_now_iso(),)).fetchone()
        if row is None:
            return None
        connection.execute("UPDATE push_deliveries SET status = 'leased', leased_at = ?, lease_owner = ?, attempt_count = attempt_count + 1, updated_at = ? WHERE delivery_id = ? AND status IN ('pending', 'retryable');", (lease_until, worker_id, utc_now_iso(), row["delivery_id"]))
        return connection.execute("SELECT * FROM push_deliveries WHERE delivery_id = ?;", (row["delivery_id"],)).fetchone()


def _refresh_allowed(row: object) -> bool:
    from backend.app.messages import service
    prefix, _, identifier = row["event_id"].partition(":")
    if prefix == "direct_message":
        intent = service.build_direct_message_push_intent(row["user_id"], identifier)
    elif prefix == "message_request":
        intent = service.build_message_request_push_intent(row["user_id"], identifier)
    elif prefix == "notification_event":
        intent = service.build_notification_event_push_intent(row["user_id"], identifier)
    else:
        return False
    return intent.decision in {"eligible", "eligible_without_preference_mapping"}


def process_delivery(worker_id: str, provider: FakePushProvider | None = None) -> PushDeliveryResponse | None:
    row = claim_delivery(worker_id)
    if row is None:
        return None
    provider_instance = provider or FakePushProvider()
    with get_connection() as connection:
        current = connection.execute(
            "SELECT deliveries.*, tokens.token_ciphertext, tokens.status AS token_status, devices.revoked_at AS device_revoked_at "
            "FROM push_deliveries AS deliveries "
            "JOIN push_device_tokens AS tokens ON tokens.token_id = deliveries.token_id "
            "JOIN messaging_devices AS devices ON devices.device_id = deliveries.device_id AND devices.user_id = deliveries.user_id "
            "WHERE deliveries.delivery_id = ? AND deliveries.status = 'leased' AND deliveries.lease_owner = ?;",
            (row["delivery_id"], worker_id),
        ).fetchone()
    if current is None:
        return None
    if current["token_status"] != "active" or current["device_revoked_at"] is not None:
        with transaction(immediate=True, lock_key=f"push-delivery:{current['delivery_id']}") as connection:
            connection.execute(
                "UPDATE push_deliveries SET status = 'cancelled', processed_at = ?, error_code = 'TOKEN_OR_DEVICE_REVOKED', "
                "updated_at = ? WHERE delivery_id = ? AND status = 'leased' AND lease_owner = ?;",
                (utc_now_iso(), utc_now_iso(), current["delivery_id"], worker_id),
            )
        return _delivery_after(current["delivery_id"])
    if not _refresh_allowed(current):
        with transaction(immediate=True, lock_key=f"push-delivery:{current['delivery_id']}") as connection:
            connection.execute("UPDATE push_deliveries SET status = 'suppressed', processed_at = ?, updated_at = ?, error_code = 'SUPPRESSED' WHERE delivery_id = ? AND lease_owner = ?;", (utc_now_iso(), utc_now_iso(), current["delivery_id"], worker_id))
        return _delivery_after(current["delivery_id"])
    result = provider_instance.send(_decrypt(current["token_ciphertext"]), {"event_id": current["event_id"]})
    now = utc_now_iso()
    with transaction(immediate=True, lock_key=f"push-delivery:{current['delivery_id']}") as connection:
        if result.outcome == "success":
            connection.execute("UPDATE push_deliveries SET status = 'sent', processed_at = ?, provider_message_id = ?, updated_at = ? WHERE delivery_id = ? AND lease_owner = ?;", (now, result.provider_message_id, now, current["delivery_id"], worker_id))
        elif result.outcome == "invalid_token":
            connection.execute("UPDATE push_deliveries SET status = 'invalid_token', processed_at = ?, error_code = ?, last_error = ?, updated_at = ? WHERE delivery_id = ? AND lease_owner = ?;", (now, result.error_code, result.error_message, now, current["delivery_id"], worker_id))
            connection.execute("UPDATE push_device_tokens SET status = 'invalid', invalid_reason = ?, updated_at = ? WHERE token_id = ?;", (result.error_code, now, current["token_id"]))
        elif result.outcome == "retryable":
            if int(current["attempt_count"]) >= settings.message_push_max_attempts:
                connection.execute("UPDATE push_deliveries SET status = 'dead_letter', processed_at = ?, error_code = ?, last_error = ?, updated_at = ? WHERE delivery_id = ? AND lease_owner = ?;", (now, result.error_code, result.error_message, now, current["delivery_id"], worker_id))
            else:
                delay = RETRY_DELAYS_SECONDS[min(int(current["attempt_count"]) - 1, len(RETRY_DELAYS_SECONDS) - 1)]
                connection.execute("UPDATE push_deliveries SET status = 'retryable', available_at = ?, error_code = ?, last_error = ?, updated_at = ?, leased_at = NULL, lease_owner = NULL WHERE delivery_id = ? AND lease_owner = ?;", (to_iso(utc_now() + timedelta(seconds=delay)), result.error_code, result.error_message, now, current["delivery_id"], worker_id))
        else:
            connection.execute("UPDATE push_deliveries SET status = 'failed_permanent', processed_at = ?, error_code = ?, last_error = ?, updated_at = ? WHERE delivery_id = ? AND lease_owner = ?;", (now, result.error_code, result.error_message, now, current["delivery_id"], worker_id))
    return _delivery_after(current["delivery_id"])


def _delivery_after(delivery_id: str) -> PushDeliveryResponse:
    with get_connection() as connection:
        row = connection.execute("SELECT * FROM push_deliveries WHERE delivery_id = ?;", (delivery_id,)).fetchone()
    if row is None:
        raise RuntimeError("push delivery disappeared")
    return _delivery_response(row)


def delivery_metrics() -> dict[str, int]:
    """Return development-only aggregate diagnostics without user or token data."""
    statuses = (
        "pending", "leased", "sent", "retryable", "failed_permanent",
        "invalid_token", "suppressed", "dead_letter", "cancelled",
    )
    metrics = {name: 0 for name in statuses}
    metrics.update({"attempt_count": 0, "lease_reclaims": 0, "failed_reasons": 0})
    with get_connection() as connection:
        rows = connection.execute("SELECT status, COUNT(*) AS count FROM push_deliveries GROUP BY status;").fetchall()
        for row in rows:
            if row["status"] in metrics:
                metrics[row["status"]] = int(row["count"])
        totals = connection.execute(
            "SELECT COALESCE(SUM(attempt_count), 0) AS total_attempt_count, "
            "COALESCE(SUM(lease_reclaim_count), 0) AS total_lease_reclaims, "
            "COALESCE(SUM(CASE WHEN error_code IS NULL THEN 0 ELSE 1 END), 0) AS total_failed_reasons "
            "FROM push_deliveries;"
        ).fetchone()
    metrics["attempt_count"] = int(totals["total_attempt_count"])
    metrics["lease_reclaims"] = int(totals["total_lease_reclaims"])
    metrics["failed_reasons"] = int(totals["total_failed_reasons"])
    return metrics
