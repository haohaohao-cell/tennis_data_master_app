"""Stage 16B isolated tests for export storage and contract-only fan-out."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
import sys
import tempfile

ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT_DIR))


class RecordingDispatcher:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.events = []

    def dispatch(self, envelope) -> None:
        self.events.append(envelope)
        if self.fail:
            raise RuntimeError("contract transport unavailable")


class FakeSocket:
    async def close(self, **_kwargs) -> None:
        return None


async def _registry_checks() -> None:
    from backend.app.messages.realtime import RealtimeRegistry

    dispatcher = RecordingDispatcher()
    registry = RealtimeRegistry(dispatcher=dispatcher, instance_id="stage16b-instance")
    await registry.register("user-a", "device-a", FakeSocket())
    event = registry.fanout_contract("event-a", "user-a", "2026-01-01T00:00:00Z")
    assert event.origin_instance_id == "stage16b-instance"
    assert set(event.__dict__) == {"event_id", "recipient_user_id", "origin_instance_id", "emitted_at"}


def main() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        os.environ["TENNIS_DB_PATH"] = str(Path(temp_dir) / "stage16b.sqlite3")
        os.environ.pop("TENNIS_DATABASE_URL", None)
        os.environ.pop("TENNIS_POSTGRES_DSN", None)
        from backend.app.core import config
        from backend.app.compliance.export_storage import TestFileExportStorage
        from backend.app.core.database import initialize_sqlite_database, transaction
        from backend.app.messages.realtime import RealtimeRegistry

        storage = TestFileExportStorage(Path(temp_dir) / "exports")
        key = storage.put_export("request-a", b'{"safe":true}')
        assert key == "request-a.json" and storage.open_export(key).read_bytes() == b'{"safe":true}'
        assert not list((Path(temp_dir) / "exports").glob("*.tmp"))
        assert not storage.exists_export("../escape.json")
        assert storage.delete_export(key) and not storage.exists_export(key)

        initialize_sqlite_database()
        with transaction() as connection:
            connection.execute("INSERT INTO users (user_id, phone, nickname) VALUES ('stage16b-user', '13916660001', 'Stage 16B');")
            connection.execute("INSERT INTO user_sync_events (user_sync_event_id, event_id, event_type, aggregate_type, aggregate_id, recipient_user_id, occurred_at, persisted_at, payload_json) VALUES ('stage16b-event-row', 'stage16b-event', 'message.created', 'chat_message', 'stage16b-message', 'stage16b-user', '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z', '{}');")
        dispatcher = RecordingDispatcher(fail=True)
        registry = RealtimeRegistry(dispatcher=dispatcher, instance_id="stage16b-instance")
        registry.publish_from_sync_event("stage16b-event")
        assert len(dispatcher.events) == 1
        event = dispatcher.events[0]
        assert event.event_id == "stage16b-event" and event.recipient_user_id == "stage16b-user"
        assert event.origin_instance_id == "stage16b-instance"
        assert not hasattr(event, "message_body") and not hasattr(event, "storage_key")
        asyncio.run(_registry_checks())
        object.__setattr__(config.settings, "export_storage_provider", "external_contract")
        try:
            from backend.app.compliance.export_storage import get_export_storage
            get_export_storage()
        except RuntimeError as error:
            assert "not implemented" in str(error).lower()
        else:
            raise AssertionError("external provider contract must not silently use test storage")
    print("Stage 16B storage and realtime adapter test passed.")


if __name__ == "__main__":
    main()
