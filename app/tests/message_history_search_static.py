from pathlib import Path


APP_DIR = Path(__file__).resolve().parents[1]
api = (APP_DIR / "api" / "messages.ts").read_text(encoding="utf-8")
screen = (APP_DIR / "app" / "chat" / "[id].tsx").read_text(encoding="utf-8")

for fragment in (
    "export type ConversationMessageSearchResponse",
    "export function searchConversationMessages",
    "new URLSearchParams",
    "/messages/conversations/${encodeURIComponent(conversationId)}/messages/search?${params.toString()}",
):
    assert fragment in api, fragment

for fragment in (
    'accessibilityLabel="搜索聊天记录"',
    "setSearchMode(true)",
    "function HistorySearchPanel",
    'placeholder="搜索聊天记录"',
    "onSubmitEditing={onSubmit}",
    "onSubmit={() => runHistorySearch()}",
    "searchRequestIdRef",
    "searchLoadMoreInFlightRef",
    "const [messages, setMessages]",
    "const [searchResults, setSearchResults]",
    "setSearchResults((current) => (append ? [...current, ...response.items] : response.items))",
    "onLoadMore={() => runHistorySearch(searchNextBeforeSeq, true)}",
    "CHAT_POLL_INTERVAL_MS = 3000",
    "void pollLatestMessages()",
    "void sendTextMessage(",
    "void markConversationRead(",
):
    assert fragment in screen, fragment

assert screen.count("CHAT_POLL_INTERVAL_MS = 3000") == 1
assert screen.count('AppState.addEventListener("change", handleAppStateChange)') == 1
assert "ContactSearch" not in screen
assert "ConversationSearch" not in screen

print("Message history search static test passed.")
