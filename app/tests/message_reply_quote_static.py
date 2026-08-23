from pathlib import Path


APP_DIR = Path(__file__).resolve().parents[1]
api = (APP_DIR / "api" / "messages.ts").read_text(encoding="utf-8")
chat = (APP_DIR / "app" / "chat" / "[id].tsx").read_text(encoding="utf-8")

for fragment in (
    'reply_to_message_id: string | null',
    'reply_preview: MessageReplyPreview | null',
    'replyToMessageId?: string | null',
    'reply_to_message_id: replyToMessageId ?? null',
):
    assert fragment in api, fragment

for fragment in (
    'const [replyTarget, setReplyTarget]',
    'setReplyTarget(null)',
    'replyPreviewForMessage',
    'onReply={() =>',
    'replyEnabled={conversation?.conversation.conversation_type === "direct"}',
    'conversation?.conversation.conversation_type === "direct" && !item.local_status',
    'accessibilityLabel="回复消息"',
    'accessibilityLabel="取消回复"',
    'sendTextMessage(accessToken, conversationId, content, clientMessageId, replyPreview?.message_id)',
    'reply_preview: replyPreview',
    'local_retryable: isRetryableSendError(sendError)',
    'function QuotePreview',
    '引用消息不可用',
    'scrollToQuotedMessage',
    'onScrollToIndexFailed',
    'requestAnimationFrame(() =>',
    'CHAT_POLL_INTERVAL_MS = 3000',
):
    assert fragment in chat, fragment

assert 'WebSocket' not in api + chat
assert 'expo-image-picker' not in api + chat
assert chat.count('AppState.addEventListener') == 1

print("Message reply quote static test passed.")
