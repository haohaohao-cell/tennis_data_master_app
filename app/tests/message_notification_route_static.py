from pathlib import Path


APP_DIR = Path(__file__).resolve().parents[1]
resolver = (APP_DIR / "api" / "messageNotificationRoute.ts").read_text(encoding="utf-8")
screen = (APP_DIR / "app" / "(tabs)" / "messages.tsx").read_text(encoding="utf-8")

expected_fragments = (
    'case "user_profile":',
    'pathname: "/user/[id]"',
    'case "post_detail":',
    'case "post_comments":',
    'focus: "comments"',
    'case "message_request":',
    'kind: "request_view"',
    'case "activity_detail":',
    'pathname: "/activity/[id]"',
    'case "lesson_detail":',
    'case "none":',
)
for fragment in expected_fragments:
    assert fragment in resolver, fragment

assert "deep_link" not in resolver
assert "object_type" not in resolver
assert "resolveNotificationRoute(item.event.target, item.actor)" in screen
assert 'deep_link?.includes("messages/requests")' not in screen
assert 'item.event.object_type === "social_post"' not in screen
assert 'item.event.object_type === "user"' not in screen

print("Message notification route static test passed.")
