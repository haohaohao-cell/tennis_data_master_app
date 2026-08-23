from pathlib import Path


APP_DIR = Path(__file__).resolve().parents[1]
api = (APP_DIR / "api" / "messages.ts").read_text(encoding="utf-8")
chat = (APP_DIR / "app" / "chat" / "[id].tsx").read_text(encoding="utf-8")

assert api.count("export const MESSAGE_SEND_TIMEOUT_MS") == 1
assert "export const MESSAGE_SEND_TIMEOUT_MS = 15_000" in api
assert "class MessageSendTimeoutError extends Error" in api
assert "setTimeout(() => reject(new MessageSendTimeoutError()), MESSAGE_SEND_TIMEOUT_MS)" in api
assert "Promise.race([request, timeout]).finally" in api
assert "clearTimeout(timeoutId)" in api

for fragment in (
    "isRetryableSendError",
    'error.code === "NETWORK_ERROR"',
    "error.status === 408",
    "error.status === 425",
    "error.status === 429",
    "error.status >= 500",
):
    assert fragment in api, fragment

for status in (400, 401, 403, 404, 409, 422):
    assert f"error.status === {status}" not in api

for fragment in (
    "local_retryable?: boolean",
    "local_status: \"failed\" as const",
    "local_retryable: isRetryableSendError(sendError)",
    "failed && message.local_error",
    "{message.local_error}",
    "styles.messageError",
    "retryMessage?.client_message_id ?? createClientMessageId",
    "retryEnabled={interactionCanSend && item.local_retryable === true}",
    "sendInFlightRef",
    "chatMountedRef",
    "chatConversationIdRef",
    "!chatMountedRef.current || chatConversationIdRef.current !== conversationId",
    "function mergeMessages",
    "CHAT_POLL_INTERVAL_MS = 3000",
):
    assert fragment in chat, fragment

assert chat.count("AppState.addEventListener") == 1
for forbidden in ("NetInfo", "expo-network", "AsyncStorage", "outbox", "automatic retry"):
    assert forbidden not in api + chat, forbidden

print("Message send resilience static test passed.")
