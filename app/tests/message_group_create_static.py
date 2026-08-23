from pathlib import Path


APP_DIR = Path(__file__).resolve().parents[1]
api = (APP_DIR / "api" / "messages.ts").read_text(encoding="utf-8")
messages = (APP_DIR / "app" / "(tabs)" / "messages.tsx").read_text(encoding="utf-8")
create = (APP_DIR / "app" / "messages" / "create-group.tsx").read_text(encoding="utf-8")
chat = (APP_DIR / "app" / "chat" / "[id].tsx").read_text(encoding="utf-8")

for fragment in (
    "export function createGroupConversation(",
    "/api/v1/messages/groups",
    'method: "POST"',
    "group_type: \"custom\"",
    "member_user_ids: memberUserIds",
    "title: title.trim()",
):
    assert fragment in api, fragment

for fragment in (
    'accessibilityLabel="创建群聊"',
    'router.push("/messages/create-group")',
):
    assert fragment in messages, fragment

for fragment in (
    'searchUsers(accessToken',
    "const [selected, setSelected]",
    "selected.map((item) => item.user.user_id)",
    "selectedIds",
    "setSelected((current) => current.some",
    "const createInFlightRef = useRef(false)",
    "const createRequestIdRef = useRef(0)",
    "const createMutexRequestIdRef = useRef<number | null>(null)",
    "const mountedRef = useRef(true)",
    "mountedRef.current = false",
    "createRequestIdRef.current += 1",
    "createMutexRequestIdRef.current = null",
    "const requestId = ++createRequestIdRef.current",
    "createMutexRequestIdRef.current = requestId",
    "createRequestIdRef.current !== requestId",
    "createMutexRequestIdRef.current === requestId",
    "setLoading(false)",
    "setTitle(\"\")",
    "setQuery(\"\")",
    "const requestUserId = userId",
    "const authSessionRef = useRef({ status, userId })",
    "authSessionRef.current = { status, userId }",
    "authSessionRef.current.userId !== requestUserId",
    "!mountedRef.current",
    "setSelected([])",
    "if (createInFlightRef.current)",
    "createInFlightRef.current = true",
    "createInFlightRef.current = false",
    "const searchRequestIdRef = useRef(0)",
    "const handleQueryChange = useCallback",
    "onChangeText={handleQueryChange}",
    "const requestId = ++searchRequestIdRef.current",
    "searchRequestIdRef.current !== requestId",
    "searchRequestIdRef.current += 1",
    "createGroupConversation(",
    'pathname: "/chat/[id]"',
    'error.code === "USER_INTERACTION_BLOCKED"',
    "error.status === 403",
    "当前成员组合无法创建群聊",
    'maxLength={120}',
    "disabled={loading}",
):
    assert fragment in create, fragment

assert "app/api/users.ts" not in create
handler_start = create.index("const handleQueryChange")
handler_end = create.index("const runSearch", handler_start)
assert "searchRequestIdRef.current += 1" in create[handler_start:handler_end]
submit_start = create.index("const submit = useCallback")
submit_end = create.index("return (", submit_start)
submit_block = create[submit_start:submit_end]
assert submit_block.index("const requestId = ++createRequestIdRef.current") < submit_block.index("createGroupConversation(")
assert submit_block.index("createMutexRequestIdRef.current === requestId") < submit_block.index("createInFlightRef.current = false")
auth_start = create.index("useEffect(() => {\n    searchRequestIdRef.current += 1")
auth_end = create.index("}, [status, userId]);", auth_start)
auth_block = create[auth_start:auth_end]
assert "createRequestIdRef.current += 1" in auth_block
assert "setLoading(false)" in auth_block
assert "expo-image-picker" not in api + messages + create
assert "WebSocket" not in api + messages + create
assert "EventSource" not in api + messages + create
assert "Socket.IO" not in api + messages + create
assert 'message.message_type !== "text"' in chat
assert 'conversation?.conversation.conversation_type !== "direct"' in chat

print("Message group create static test passed.")
