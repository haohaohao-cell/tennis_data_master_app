from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SYNC_API = (ROOT / "app" / "api" / "messageSync.ts").read_text(encoding="utf-8")
OUTBOX_API = (ROOT / "app" / "api" / "messageOutbox.ts").read_text(encoding="utf-8")


def main() -> None:
    for endpoint in (
        '"/api/v1/messages/devices"',
        '"/api/v1/messages/sync/checkpoints"',
    ):
        assert endpoint in SYNC_API, endpoint
    assert "/api/v1/messages/sync?${params.toString()}" in SYNC_API
    for marker in (
        "getMessageDeviceId",
        "readMessageSyncState",
        "writeMessageSyncState",
        "event_ids",
        "SYNC_CURSOR_EXPIRED",
        "listConversations",
        "getUnreadCounts",
        "listNotifications",
    ):
        assert marker in SYNC_API or marker in OUTBOX_API, marker
    assert 'const SYNC_STATE_STORAGE_KEY = "tennis.message-sync.v1"' in OUTBOX_API
    assert 'const seen = new Set(state.event_ids)' in SYNC_API
    assert "websocket" not in SYNC_API.lower()
    assert "sse" not in SYNC_API.lower()
    print("Message sync static contract test passed.")


if __name__ == "__main__":
    main()
