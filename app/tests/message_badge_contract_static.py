from pathlib import Path


APP_DIR = Path(__file__).resolve().parents[1]
api = (APP_DIR / "api" / "messages.ts").read_text(encoding="utf-8")
tab_layout = (APP_DIR / "app" / "(tabs)" / "_layout.tsx").read_text(encoding="utf-8")


assert "messages_tab_badge_count: number;" in api
assert "total_unread_count: number;" in api
assert "setUnreadCount(response.messages_tab_badge_count);" in tab_layout
assert "setUnreadCount(response.total_unread_count);" not in tab_layout

print("Message badge contract static test passed.")
