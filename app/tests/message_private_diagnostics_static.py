from pathlib import Path


APP_DIR = Path(__file__).resolve().parents[1]
api = (APP_DIR / "api" / "messages.ts").read_text(encoding="utf-8")


def function_block(name: str) -> str:
    start = api.index(f"export function {name}(")
    end = api.find("\nexport function ", start + 1)
    return api[start:] if end == -1 else api[start:end]


private_calls = {
    "sendTextMessage": "text_content: textContent",
    "createMessageRequest": "request_message: requestMessage",
    "searchConversationMessages": "q: query.trim()",
    "searchConversations": "q: query.trim()",
    "createGroupConversation": "title: title.trim()",
}

for name, private_input in private_calls.items():
    block = function_block(name)
    assert private_input in block, (name, private_input)
    assert "captureDiagnostics: false" in block, name

for name in ("listMessages", "markConversationRead", "getUnreadCounts"):
    assert "captureDiagnostics: false" not in function_block(name), name

print("Message private diagnostics static test passed.")
