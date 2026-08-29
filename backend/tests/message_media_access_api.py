from __future__ import annotations

import asyncio
import os
from pathlib import Path
import sys
import tempfile
import sys

ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT_DIR))

from backend.tests.auth_api_smoke import asgi_request
from backend.tests.message_image_message_api import create_media, image_bytes
from backend.tests.activity_detail_api_smoke import login_phone

async def main() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        os.environ["TENNIS_DB_PATH"] = str(Path(temp_dir) / "message_media_access.sqlite3")
        os.environ["TENNIS_MESSAGE_MEDIA_STORAGE_DIR"] = str(Path(temp_dir) / "message-media")
        from backend.app.core.database import initialize_database, transaction
        from backend.app.main import app

        initialize_database()
        sender_token, sender_id = await login_phone(app, "13900000001")
        receiver_token, receiver_id = await login_phone(app, "13900000002")
        outsider_token, _ = await login_phone(app, "13900000003")
        sender_headers = {"authorization": f"Bearer {sender_token}"}
        receiver_headers = {"authorization": f"Bearer {receiver_token}"}
        outsider_headers = {"authorization": f"Bearer {outsider_token}"}
        follow = await asgi_request(app, "POST", f"/api/v1/social/follows/{receiver_id}", headers=sender_headers)
        assert follow.status == 201, follow
        follow_back = await asgi_request(app, "POST", f"/api/v1/social/follows/{sender_id}", headers=receiver_headers)
        assert follow_back.status == 201, follow_back
        conversation = await asgi_request(app, "POST", "/api/v1/messages/direct-conversations", {"target_user_id": receiver_id}, headers=sender_headers)
        conversation_id = conversation.json_body["conversation"]["conversation_id"]
        media_id = await create_media(app, sender_headers, image_bytes(), "access-image")
        unbound = await asgi_request(app, "GET", f"/api/v1/messages/media/{media_id}", headers=outsider_headers)
        assert unbound.status == 404
        sent = await asgi_request(app, "POST", f"/api/v1/messages/conversations/{conversation_id}/messages", {
            "message_type": "image", "client_message_id": "access-message", "attachments": [{"attachment_type": "image", "media_id": media_id}],
        }, headers=sender_headers)
        assert sent.status == 201
        assert (await asgi_request(app, "GET", f"/api/v1/messages/media/{media_id}", headers=sender_headers)).status == 200
        assert (await asgi_request(app, "GET", f"/api/v1/messages/media/{media_id}", headers=receiver_headers)).status == 200
        assert (await asgi_request(app, "GET", f"/api/v1/messages/media/{media_id}", headers=outsider_headers)).status == 404
        with transaction() as connection:
            connection.execute("UPDATE chat_conversation_members SET status = 'removed', left_at = CURRENT_TIMESTAMP WHERE conversation_id = ? AND user_id = ?;", (conversation_id, receiver_id))
        removed = await asgi_request(app, "GET", f"/api/v1/messages/media/{media_id}", headers=receiver_headers)
        assert removed.status == 404
        with transaction() as connection:
            connection.execute("UPDATE chat_messages SET status = 'revoked', deleted_at = CURRENT_TIMESTAMP WHERE conversation_id = ?;", (conversation_id,))
        revoked = await asgi_request(app, "GET", f"/api/v1/messages/media/{media_id}", headers=sender_headers)
        assert revoked.status == 404
        guessed = await asgi_request(app, "GET", "/api/v1/messages/media/not-a-real-media", headers=sender_headers)
        assert guessed.status == 404
        print("Message media access API test passed.")


if __name__ == "__main__":
    asyncio.run(main())
