"""Static contract checks for the local draft and message outbox state machine."""

from pathlib import Path


APP_DIR = Path(__file__).resolve().parents[1]
outbox = (APP_DIR / "api" / "messageOutbox.ts").read_text(encoding="utf-8")
chat = (APP_DIR / "app" / "chat" / "[id].tsx").read_text(encoding="utf-8")

for state in ("queued", "sending", "sent", "failed_retryable", "failed_permanent", "cancelled"):
    assert f'"{state}"' in outbox

for fragment in (
    "saveLocalDraft",
    "clearLocalDraft",
    "enqueueLocalMessage",
    "recoverLocalMessageOutbox",
    "client_message_id",
    "server_message_id",
    "server_event_id",
    "TERMINAL_RETENTION_MS",
    'item.local_state === "sent"',
    'item.local_state === "sending"',
    "next_retry_at",
    "withStorageLock",
    "storageQueue",
):
    assert fragment in outbox + chat, fragment

assert "removeLocalMessageOutbox(item.local_id)" not in chat
assert "recoverMessageByClientId" in chat
assert 'local_state: effectiveRetryable ? "failed_retryable" : "failed_permanent"' in chat

print("Message outbox local-state static test passed.")
