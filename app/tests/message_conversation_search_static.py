from pathlib import Path


APP_DIR = Path(__file__).resolve().parents[1]
api = (APP_DIR / "api" / "messages.ts").read_text(encoding="utf-8")
screen = (APP_DIR / "app" / "(tabs)" / "messages.tsx").read_text(encoding="utf-8")

for fragment in (
    "export function searchConversations",
    "/api/v1/messages/conversations/search?${params.toString()}",
):
    assert fragment in api, fragment

for fragment in (
    'router.push("/friends/search")',
    'accessibilityLabel="搜索聊天"',
    'activeView === "chat"',
    "function ConversationSearchPanel",
    'placeholder="搜索聊天"',
    "onSubmit={() => runConversationSearch()}",
    "const [conversations, setConversations]",
    "const [conversationSearchResults, setConversationSearchResults]",
    "conversationSearchRequestIdRef",
    "conversationSearchPaginationInFlightRef",
    "function ConversationSearchRow",
    'pathname: "/chat/[id]"',
    'name="pin"',
    'name="notifications-off-outline"',
    "unreadBadge",
    "MESSAGES_POLL_INTERVAL_MS = 8000",
    'AppState.addEventListener("change", handleAppStateChange)',
):
    assert fragment in screen, fragment

assert screen.count("MESSAGES_POLL_INTERVAL_MS = 8000") == 1
assert screen.count('AppState.addEventListener("change", handleAppStateChange)') == 1
assert "ContactSearch" not in screen
assert "HiddenConversationManagement" not in screen
assert "GlobalMessageSearch" not in screen

print("Message conversation search static test passed.")
