from pathlib import Path


APP_DIR = Path(__file__).resolve().parents[1]
api = (APP_DIR / "api" / "messages.ts").read_text(encoding="utf-8")
chat = (APP_DIR / "app" / "chat" / "[id].tsx").read_text(encoding="utf-8")


for fragment in (
    "export type PostShareCard",
    'state: "available" | "unavailable"',
    "share_card: PostShareCard | null",
):
    assert fragment in api, fragment

for fragment in (
    "function BusinessObjectMessageCard",
    "messageBusinessObjectCardModel(card)",
    '"@/messages/businessObjectCard"',
    "disabled={!model.destination}",
    "分享了{model.label}",
    "onError={() => setCoverFailed(true)}",
    "numberOfLines={2}",
):
    assert fragment in chat, fragment

assert "business_object_card: BusinessObjectCard | null" in api

assert "app/api/uploads.ts" not in chat
assert "WebSocket" not in chat

print("Message post share static test passed.")
