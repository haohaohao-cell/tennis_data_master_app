from pathlib import Path


APP_DIR = Path(__file__).resolve().parents[1]
api = (APP_DIR / "api" / "messages.ts").read_text(encoding="utf-8")
screen = (APP_DIR / "app" / "(tabs)" / "messages.tsx").read_text(encoding="utf-8")

for fragment in (
    "export function hideConversation",
    "export function unhideConversation",
    '/messages/conversations/${encodeURIComponent(conversationId)}/hide',
    "is_hidden: boolean",
):
    assert fragment in api, fragment

for fragment in (
    '"聊天管理"',
    'text: pinned ? "取消置顶" : "置顶"',
    'text: muted ? "取消静音" : "静音 24 小时"',
    'text: "隐藏聊天"',
    'Alert.alert("隐藏聊天？", "聊天记录不会删除。有新消息时会重新显示。"',
    "current.filter((item) =>",
    "conversationMutationInFlightRef.current.has(conversationId)",
    "loadRequestIdRef.current += 1",
    "MESSAGES_POLL_INTERVAL_MS = 8000",
):
    assert fragment in screen, fragment

assert screen.count("MESSAGES_POLL_INTERVAL_MS = 8000") == 1
assert 'text: "删除"' not in screen

print("Message conversation hide static test passed.")
