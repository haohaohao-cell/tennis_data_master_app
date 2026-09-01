"""Temporary-database core regression for Stage 11C fake push state."""

from __future__ import annotations

from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.app.core import config
from backend.app.core import database
from backend.app.messages import push
from backend.app.messages import sync
from backend.app.messages.schemas import DirectMessagePushDeliveryRequest, MessageDeviceRegisterRequest, PushTokenRegisterRequest


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="stage11c-") as directory:
        object.__setattr__(config.settings, "database_url", None)
        object.__setattr__(config.settings, "database_path", Path(directory) / "fixture.sqlite3")
        object.__setattr__(config.settings, "message_push_enabled", True)
        object.__setattr__(config.settings, "message_push_fake_provider_enabled", True)
        object.__setattr__(config.settings, "message_push_token_registration_enabled", True)
        database.initialize_sqlite_database()
        with database.transaction() as connection:
            connection.execute("INSERT INTO users (user_id, phone, nickname) VALUES (?, ?, ?);", ("u-stage11c", "13900000001", "Stage 11C"))

        device = sync.register_device("u-stage11c", MessageDeviceRegisterRequest(device_id="stage11c-device-1"))
        first = push.register_token("u-stage11c", device.device.device_id, PushTokenRegisterRequest(token="fake_success_token"))
        same = push.register_token("u-stage11c", device.device.device_id, PushTokenRegisterRequest(token="fake_success_token"))
        assert first.token_id == same.token_id
        rotated = push.register_token("u-stage11c", device.device.device_id, PushTokenRegisterRequest(token="fake_retry_token"))
        assert rotated.token_id != first.token_id
        with database.get_connection() as connection:
            assert connection.execute("SELECT status FROM push_device_tokens WHERE token_id = ?;", (first.token_id,)).fetchone()[0] == "revoked"
            assert connection.execute("SELECT token_ciphertext FROM push_device_tokens WHERE token_id = ?;", (rotated.token_id,)).fetchone()[0] != "fake_retry_token"

        request = DirectMessagePushDeliveryRequest.model_validate({
            "push_kind": "direct_message", "recipient_user_id": "u-stage11c", "delivery_id": "direct_message:stage11c-event",
            "preference_kind": "direct_message", "notification_type": None,
            "target": {"type": "chat", "conversation_id": "stage11c-conversation"},
            "display": {"title": "redacted", "body": "must not be stored"},
            "data": {"type": "direct_message", "message_id": "stage11c-event", "sender_user_id": "u-other"},
        })
        created = push.create_deliveries(request)
        duplicate = push.create_deliveries(request)
        assert len(created) == 1 and len(duplicate) == 1
        original_allowed = push._refresh_allowed
        push._refresh_allowed = lambda row: True
        try:
            retry = push.process_delivery("worker-1")
            assert retry is not None and retry.status == "retryable"
            object.__setattr__(config.settings, "message_push_max_attempts", 1)
            with database.transaction() as connection:
                connection.execute("UPDATE push_deliveries SET available_at = CURRENT_TIMESTAMP WHERE delivery_id = ?;", (retry.delivery_id,))
            dead = push.process_delivery("worker-1")
            assert dead is not None and dead.status == "dead_letter"
        finally:
            push._refresh_allowed = original_allowed
        push.revoke_device_tokens("u-stage11c", device.device.device_id)
        with database.get_connection() as connection:
            assert connection.execute("SELECT COUNT(*) FROM push_device_tokens WHERE status = 'active';").fetchone()[0] == 0
    print("Stage 11C SQLite fake push core test passed.")


if __name__ == "__main__":
    main()
