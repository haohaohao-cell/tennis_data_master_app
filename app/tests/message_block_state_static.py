from pathlib import Path


APP_DIR = Path(__file__).resolve().parents[1]
api = (APP_DIR / "api" / "messages.ts").read_text(encoding="utf-8")
chat = (APP_DIR / "app" / "chat" / "[id].tsx").read_text(encoding="utf-8")

for fragment in (
    "direct_interaction_state: DirectConversationInteractionState | null",
    "blocked_by_current_user: boolean",
    "can_send: boolean",
):
    assert fragment in api, fragment

for fragment in (
    "setDirectInteractionState(messageResponse.direct_interaction_state)",
    "setDirectInteractionState(response.direct_interaction_state)",
    "if (!interactionCanSend)",
    'sendError.code === "USER_INTERACTION_BLOCKED"',
    'setDirectInteractionState({ blocked_by_current_user: false, can_send: false })',
    '"你已拉黑该用户，当前无法发送消息"',
    '"当前无法向该用户发送消息"',
    "retryEnabled={interactionCanSend && item.local_retryable === true}",
    'failed && !retryEnabled ? <Text style={styles.messageTime}>暂不可重试</Text>',
    'conversation?.conversation.conversation_type === "group" || directInteractionState?.can_send === true',
):
    assert fragment in chat, fragment

state_update = chat.index("setDirectInteractionState(response.direct_interaction_state)")
no_message_return = chat.index(
    "if (newServerMessages.length === 0 && !hasLocalReplacement && !hasServerMutation)"
)
assert state_update < no_message_return

assert "CHAT_POLL_INTERVAL_MS = 3000" in chat
assert "对方已拉黑你" not in chat

print("Message block state static test passed.")
