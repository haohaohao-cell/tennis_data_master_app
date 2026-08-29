from __future__ import annotations

import asyncio
from io import BytesIO
import os
from pathlib import Path
import sys
import tempfile
import uuid

from PIL import Image

ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT_DIR))

from backend.tests.activity_detail_api_smoke import login_phone
from backend.tests.auth_api_smoke import asgi_request
from backend.tests.upload_api_smoke import asgi_bytes_request, multipart_video_body


def image_bytes() -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (40, 24), (220, 80, 80)).save(buffer, format="PNG")
    return buffer.getvalue()


async def create_media(app, headers, raw: bytes, client_id: str) -> str:
    intent = await asgi_request(app, "POST", "/api/v1/messages/media/upload-intents", {
        "media_type": "image", "mime_type": "image/png", "file_size_bytes": len(raw),
        "width_px": 40, "height_px": 24, "client_upload_id": client_id,
    }, headers=headers)
    assert intent.status == 201, intent
    media_id = intent.json_body["media"]["media_id"]
    boundary = f"image-{uuid.uuid4().hex}"
    upload = await asgi_bytes_request(app, "POST", f"/api/v1/messages/media/{media_id}/file",
        multipart_video_body(boundary=boundary, filename="image.png", content_type="image/png", content=raw),
        {**headers, "content-type": f"multipart/form-data; boundary={boundary}"})
    assert upload.status == 200, upload
    complete = await asgi_request(app, "POST", f"/api/v1/messages/media/{media_id}/complete", headers=headers)
    assert complete.status == 200, complete
    return media_id


async def main() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        os.environ["TENNIS_DB_PATH"] = str(Path(temp_dir) / "message_image.sqlite3")
        os.environ["TENNIS_MESSAGE_MEDIA_STORAGE_DIR"] = str(Path(temp_dir) / "message-media")
        from backend.app.core.database import get_connection, initialize_database
        from backend.app.main import app

        initialize_database()
        sender_token, sender_id = await login_phone(app, "13800000001")
        receiver_token, receiver_id = await login_phone(app, "13800000002")
        sender_headers = {"authorization": f"Bearer {sender_token}"}
        receiver_headers = {"authorization": f"Bearer {receiver_token}"}
        follow = await asgi_request(app, "POST", f"/api/v1/social/follows/{receiver_id}", headers=sender_headers)
        assert follow.status == 201, follow
        follow_back = await asgi_request(app, "POST", f"/api/v1/social/follows/{sender_id}", headers=receiver_headers)
        assert follow_back.status == 201, follow_back
        conversation = await asgi_request(app, "POST", "/api/v1/messages/direct-conversations", {"target_user_id": receiver_id}, headers=sender_headers)
        assert conversation.status == 201, conversation
        conversation_id = conversation.json_body["conversation"]["conversation_id"]
        raw = image_bytes()
        media_id = await create_media(app, sender_headers, raw, "message-image-1")
        not_ready_intent = await asgi_request(app, "POST", "/api/v1/messages/media/upload-intents", {
            "media_type": "image", "mime_type": "image/png", "file_size_bytes": len(raw), "width_px": 40, "height_px": 24, "client_upload_id": "not-ready",
        }, headers=sender_headers)
        not_ready_id = not_ready_intent.json_body["media"]["media_id"]
        not_ready = await asgi_request(app, "POST", f"/api/v1/messages/conversations/{conversation_id}/messages", {
            "message_type": "image", "client_message_id": "not-ready-message", "attachments": [{"attachment_type": "image", "media_id": not_ready_id}],
        }, headers=sender_headers)
        assert not_ready.status == 409 and not_ready.json_body["detail"]["code"] == "MESSAGE_MEDIA_NOT_READY"

        body = {
            "message_type": "image", "client_message_id": "image-message-1", "text_content": "Look at this rally.",
            "attachments": [{"attachment_type": "image", "media_id": media_id}],
        }
        sent = await asgi_request(app, "POST", f"/api/v1/messages/conversations/{conversation_id}/messages", body, headers=sender_headers)
        assert sent.status == 201, sent
        message_id = sent.json_body["message"]["message_id"]
        attachment = sent.json_body["message"]["attachments"][0]
        assert attachment["media_id"] == media_id and attachment["media_url"] and attachment["thumbnail_url"]
        assert "storage_key" not in str(sent.json_body)
        retry = await asgi_request(app, "POST", f"/api/v1/messages/conversations/{conversation_id}/messages", body, headers=sender_headers)
        assert retry.status == 201 and retry.json_body["message"]["message_id"] == message_id
        conflict = await asgi_request(app, "POST", f"/api/v1/messages/conversations/{conversation_id}/messages", {**body, "text_content": "changed"}, headers=sender_headers)
        assert conflict.status == 409 and conflict.json_body["detail"]["code"] == "CLIENT_MESSAGE_ID_CONFLICT"
        second_bind = await asgi_request(app, "POST", f"/api/v1/messages/conversations/{conversation_id}/messages", {
            "message_type": "image", "client_message_id": "image-message-2", "attachments": [{"attachment_type": "image", "media_id": media_id}],
        }, headers=sender_headers)
        assert second_bind.status == 409 and second_bind.json_body["detail"]["code"] == "MESSAGE_MEDIA_ALREADY_ATTACHED", second_bind
        history = await asgi_request(app, "GET", f"/api/v1/messages/conversations/{conversation_id}/messages", headers=receiver_headers)
        assert history.status == 200 and history.json_body["items"][0]["attachments"][0]["media_id"] == media_id
        with get_connection() as connection:
            assert connection.execute("SELECT COUNT(*) FROM chat_messages WHERE message_id = ?;", (message_id,)).fetchone()[0] == 1
            assert connection.execute("SELECT upload_status FROM chat_message_media WHERE media_id = ?;", (media_id,)).fetchone()[0] == "attached"
            unread = connection.execute("SELECT unread_count FROM chat_conversation_members WHERE conversation_id = ? AND user_id = ?;", (conversation_id, receiver_id)).fetchone()[0]
            assert unread == 1
        print("Message image message API test passed.")


if __name__ == "__main__":
    asyncio.run(main())
