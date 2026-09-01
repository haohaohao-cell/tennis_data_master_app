"""Live notification-preference and conversation-mute delivery regression.

The test uses the production message intent builders rather than replacing the
send-time decision hook.  It can run against a temporary SQLite database or a
fresh PostgreSQL schema supplied through ``STAGE11H4_SCHEMA``.
"""

from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile
import uuid
from urllib.parse import parse_qsl, quote, urlsplit, urlunsplit


ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT_DIR))


def _scoped_dsn(source: str, schema: str) -> str:
    parts = urlsplit(source)
    query = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if key != "options"
    ]
    query.append(("options", f"-c search_path={schema},pg_catalog"))
    return urlunsplit(
        (
            parts.scheme,
            parts.netloc,
            parts.path,
            "&".join(f"{quote(key)}={quote(value)}" for key, value in query),
            parts.fragment,
        )
    )


def _configure() -> tempfile.TemporaryDirectory[str] | None:
    from backend.app.core import config

    schema = os.environ.get("STAGE11H4_SCHEMA")
    source = os.environ.get("TENNIS_DATABASE_URL")
    if schema:
        if not source:
            raise SystemExit("TENNIS_DATABASE_URL is required with STAGE11H4_SCHEMA")
        object.__setattr__(config.settings, "database_url", _scoped_dsn(source, schema))
        return None

    directory = tempfile.TemporaryDirectory(prefix="stage11c-h4-")
    object.__setattr__(config.settings, "database_url", None)
    object.__setattr__(config.settings, "database_path", Path(directory.name) / "fixture.sqlite3")
    from backend.app.core import database

    database.initialize_database()
    return directory


def _message_and_delivery(sender_id: str, recipient_id: str, conversation_id: str, ordinal: int):
    from backend.app.messages import push, service
    from backend.app.messages.schemas import MessageCreate

    sent = service.send_message(
        sender_id,
        conversation_id,
        MessageCreate(text_content=f"fixture-{ordinal}", client_message_id=f"h4-message-{ordinal}"),
    )
    intent = service.build_direct_message_push_intent(recipient_id, sent.message.message_id)
    assert intent.decision == "eligible" and intent.request is not None
    deliveries = push.create_deliveries(intent.request)
    assert len(deliveries) == 1
    return deliveries[0]


def main() -> None:
    temporary_directory = _configure()
    try:
        from backend.app.core import config
        from backend.app.core.database import get_connection, transaction
        from backend.app.messages import push, service, sync
        from backend.app.messages.schemas import (
            MessageDeviceRegisterRequest,
            NotificationPreferencePatch,
            PushTokenRegisterRequest,
        )

        object.__setattr__(config.settings, "message_push_enabled", True)
        object.__setattr__(config.settings, "message_push_fake_provider_enabled", True)
        object.__setattr__(config.settings, "message_push_token_registration_enabled", True)
        suffix = uuid.uuid4().hex[:8]
        sender_id, recipient_id = f"h4-sender-{suffix}", f"h4-recipient-{suffix}"
        with transaction() as connection:
            connection.execute(
                "INSERT INTO users (user_id, phone, nickname) VALUES (?, ?, ?);",
                (sender_id, f"137{suffix}", "H4 sender"),
            )
            connection.execute(
                "INSERT INTO users (user_id, phone, nickname) VALUES (?, ?, ?);",
                (recipient_id, f"138{suffix}", "H4 recipient"),
            )
            conversation_id = service.ensure_direct_conversation_in_transaction(
                connection,
                sender_id,
                recipient_id,
                require_direct_permission=False,
            )
        device = sync.register_device(
            recipient_id,
            MessageDeviceRegisterRequest(device_id=f"h4-device-{suffix}"),
        ).device
        push.register_token(
            recipient_id,
            device.device_id,
            PushTokenRegisterRequest(token=f"fake_success_h4_{suffix}"),
        )

        # Preference changes after delivery creation must suppress provider I/O.
        preference_delivery = _message_and_delivery(sender_id, recipient_id, conversation_id, 1)
        service.update_notification_preferences(
            recipient_id,
            NotificationPreferencePatch(direct_message_notifications=False),
        )
        preference_provider = push.FakePushProvider()
        preference_result = push.process_delivery("h4-preference-worker", preference_provider)
        assert preference_result is not None
        assert preference_result.delivery_id == preference_delivery.delivery_id
        assert preference_result.status == "suppressed"
        assert preference_provider.results == []

        # A fresh event is eligible when created, then muted before its worker runs.
        service.update_notification_preferences(
            recipient_id,
            NotificationPreferencePatch(direct_message_notifications=True),
        )
        mute_delivery = _message_and_delivery(sender_id, recipient_id, conversation_id, 2)
        muted = service.set_conversation_mute(recipient_id, conversation_id, True)
        assert muted.is_muted
        mute_provider = push.FakePushProvider()
        mute_result = push.process_delivery("h4-mute-worker", mute_provider)
        assert mute_result is not None
        assert mute_result.delivery_id == mute_delivery.delivery_id
        assert mute_result.status == "suppressed"
        assert mute_provider.results == []

        # Terminal sent state is never revisited by preference or mute rechecks.
        service.set_conversation_mute(recipient_id, conversation_id, False)
        sent_delivery = _message_and_delivery(sender_id, recipient_id, conversation_id, 3)
        sent_provider = push.FakePushProvider()
        sent_result = push.process_delivery("h4-sent-worker", sent_provider)
        assert sent_result is not None and sent_result.status == "sent"
        assert len(sent_provider.results) == 1
        service.update_notification_preferences(
            recipient_id,
            NotificationPreferencePatch(direct_message_notifications=False),
        )
        service.set_conversation_mute(recipient_id, conversation_id, True)
        assert push.process_delivery("h4-terminal-worker", push.FakePushProvider()) is None
        with get_connection() as connection:
            persisted = connection.execute(
                "SELECT status FROM push_deliveries WHERE delivery_id = ?;",
                (sent_delivery.delivery_id,),
            ).fetchone()
        assert persisted is not None and persisted["status"] == "sent"
    finally:
        if temporary_directory is not None:
            temporary_directory.cleanup()
    print("Stage 11C-H4 live preference and mute delivery test passed.")


if __name__ == "__main__":
    main()
