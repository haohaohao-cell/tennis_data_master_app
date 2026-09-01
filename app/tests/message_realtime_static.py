"""Static guard for the Stage 11D App coordination boundary."""

from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
realtime = (ROOT_DIR / "app" / "api" / "messageRealtime.ts").read_text(encoding="utf-8")
bridge = (ROOT_DIR / "app" / "messages" / "MessageRealtimeBridge.tsx").read_text(encoding="utf-8")

assert "access_token" in realtime
assert "sync.wake" in realtime
assert "seenEventIds" in realtime
assert "scheduleReconnect" in realtime
assert "syncMessagesWithRecovery" in bridge
assert "AppState.addEventListener" in bridge
assert "registerMessageDevice" in bridge
print("Stage 11D App realtime static test passed.")
