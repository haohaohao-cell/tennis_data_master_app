"""Static contract guard for Stage 13B card normalization and safe routing."""

from pathlib import Path


APP_DIR = Path(__file__).resolve().parents[1]
model = (APP_DIR / "messages" / "businessObjectCard.ts").read_text(encoding="utf-8")
chat = (APP_DIR / "app" / "chat" / "[id].tsx").read_text(encoding="utf-8")

for state in ("active", "archived", "deleted", "unavailable", "denied", "not_found", "unsupported"):
    assert f'"{state}"' in model, state
for marker in (
    "card.can_preview",
    "card.can_open",
    "card.safe_summary",
    "card.access === \"denied\"",
    "card.access === \"not_found\"",
    "card.object_state === \"deleted\"",
    "card.state === \"unsupported\"",
    'pathname: "/activity/[id]"',
    'pathname: "/post/[id]"',
    "if (!card.can_open) return null",
):
    assert marker in model, marker

assert "video_path" not in model
assert "storage_key" not in model
assert "router.push(model.destination)" in chat
assert "disabled={!model.destination}" in chat
assert "messageBusinessObjectCardStateLabel" in chat
assert "WebSocket" not in model
print("Stage 13B business-object card static test passed.")
