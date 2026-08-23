from pathlib import Path


APP_DIR = Path(__file__).resolve().parents[1]
api = (APP_DIR / "api" / "messages.ts").read_text(encoding="utf-8")
screen = (APP_DIR / "app" / "(tabs)" / "messages.tsx").read_text(encoding="utf-8")

for fragment in (
    "export function muteConversation",
    "export function unmuteConversation",
    '/messages/conversations/${encodeURIComponent(conversationId)}/mute',
    "is_muted: boolean",
):
    assert fragment in api, fragment

for fragment in (
    'text: muted ? "取消静音" : "静音 24 小时"',
    '"聊天管理"',
    'name="notifications-off-outline"',
    "item.member.is_muted",
    "conversationMutationInFlightRef.current.has(conversationId)",
    "loadRequestIdRef.current += 1",
    "onTogglePin={handleConversationPin}",
    "onToggleMute={handleConversationMute}",
    "MESSAGES_POLL_INTERVAL_MS = 8000",
):
    assert fragment in screen, fragment

assert screen.count("MESSAGES_POLL_INTERVAL_MS = 8000") == 1
assert 'text: "删除"' not in screen

print("Message conversation mute static test passed.")
