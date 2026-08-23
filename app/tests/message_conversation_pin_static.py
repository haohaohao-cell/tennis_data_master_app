from pathlib import Path


APP_DIR = Path(__file__).resolve().parents[1]
api = (APP_DIR / "api" / "messages.ts").read_text(encoding="utf-8")
screen = (APP_DIR / "app" / "(tabs)" / "messages.tsx").read_text(encoding="utf-8")

for fragment in (
    "export function pinConversation",
    "export function unpinConversation",
    '/messages/conversations/${encodeURIComponent(conversationId)}/pin',
    'method: "POST"',
    'method: "DELETE"',
):
    assert fragment in api, fragment

for fragment in (
    "MESSAGES_POLL_INTERVAL_MS = 8000",
    "conversationMutationInFlightRef.current.has(conversationId)",
    "loadRequestIdRef.current += 1",
    "setConversations((current) =>",
    "onLongPress={() =>",
    '"聊天管理"',
    'text: pinned ? "取消置顶" : "置顶"',
    'name="pin"',
    "mutationIds.has(conversationId)",
):
    assert fragment in screen, fragment

assert screen.count("MESSAGES_POLL_INTERVAL_MS = 8000") == 1
assert 'text: "删除"' not in screen

print("Message conversation pin static test passed.")
