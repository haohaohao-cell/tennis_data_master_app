from pathlib import Path


APP_DIR = Path(__file__).resolve().parents[1]
api = (APP_DIR / "api" / "messages.ts").read_text(encoding="utf-8")
chat = (APP_DIR / "app" / "chat" / "[id].tsx").read_text(encoding="utf-8")

for fragment in (
    "export function recallMessage(",
    "/messages/conversations/${encodeURIComponent(conversationId)}/messages/${encodeURIComponent(messageId)}/recall",
    'method: "POST"',
):
    assert fragment in api, fragment

for fragment in (
    "function hasMessageMutation",
    "function mergePollMessages",
    "const snapshotMessages = messagesRef.current",
    "const currentMessages = messagesRef.current",
    "const pollMutationGeneration = messageMutationGenerationRef.current",
    "const latestPageIds = new Set(response.items.map((item) => item.message_id))",
    ".filter((item) => !latestPageIds.has(item.message_id))",
    "const stalePollResponse = messageMutationGenerationRef.current !== pollMutationGeneration",
    "mergePollMessages(",
    "protectedIds",
    "item.local_status",
    "current.status !== incoming.status",
    "JSON.stringify(currentReply) !== JSON.stringify(incomingReply)",
    "const hasServerMutation = authoritativeItems.some",
    "const persistedMessageIds = snapshotMessages",
    "reconcileMessages(",
    "persistedMessageIds.slice(page * 500, (page + 1) * 500)",
    "const authoritativeItems = [...response.items, ...reconciliation.items]",
    "mergePollMessages(",
    "!hasServerMutation",
    "const handleRecall = useCallback",
    "mergeMessages(current, [response.message])",
    'conversation?.conversation.conversation_type !== "direct"',
    'message.message_type !== "text"',
    'message.status !== "sent"',
    'Alert.alert(\"撤回消息\"',
    'accessibilityLabel="撤回消息"',
    'const revoked = message.status === "revoked"',
    '该消息已撤回',
    "!revoked && message.reply_preview",
    "recallEnabled && !revoked",
    'CHAT_POLL_INTERVAL_MS = 3000',
):
    assert fragment in chat, fragment

assert chat.count("AppState.addEventListener") == 1
assert "WebSocket" not in api + chat
assert "app/api/uploads.ts" not in api + chat
assert "setInterval" in chat
assert chat.count("setInterval(() =>") == 1

generation_index = chat.index("const pollMutationGeneration = messageMutationGenerationRef.current")
list_index = chat.index("await listMessages(")
assert generation_index < list_index
assert "current?.status === \"revoked\" && item.status === \"sent\"" in chat

print("Message recall static test passed.")
