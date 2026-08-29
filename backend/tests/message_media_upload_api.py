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


def image_bytes(size: tuple[int, int] = (32, 20), color: tuple[int, int, int] = (40, 120, 210)) -> bytes:
    image = Image.new("RGB", size, color)
    buffer = BytesIO()
    image.save(buffer, format="JPEG", quality=90)
    return buffer.getvalue()


async def main() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        os.environ["TENNIS_DB_PATH"] = str(Path(temp_dir) / "message_media_upload.sqlite3")
        os.environ["TENNIS_MESSAGE_MEDIA_STORAGE_DIR"] = str(Path(temp_dir) / "message-media")
        from backend.app.core.database import get_connection, initialize_database
        from backend.app.main import app

        initialize_database()
        token, user_id = await login_phone(app, "13700000001")
        other_token, _ = await login_phone(app, "13700000002")
        headers = {"authorization": f"Bearer {token}"}
        other_headers = {"authorization": f"Bearer {other_token}"}
        raw = image_bytes()

        intent_body = {
            "media_type": "image",
            "mime_type": "image/jpeg",
            "file_size_bytes": len(raw),
            "width_px": 32,
            "height_px": 20,
            "client_upload_id": "upload-1",
        }
        intent = await asgi_request(app, "POST", "/api/v1/messages/media/upload-intents", intent_body, headers=headers)
        assert intent.status == 201, intent
        media_id = intent.json_body["media"]["media_id"]
        assert intent.json_body["media"]["upload_status"] == "created"
        assert "storage_key" not in str(intent.json_body)

        retry = await asgi_request(app, "POST", "/api/v1/messages/media/upload-intents", intent_body, headers=headers)
        assert retry.status == 201 and retry.json_body["media"]["media_id"] == media_id
        conflict = await asgi_request(app, "POST", "/api/v1/messages/media/upload-intents", {**intent_body, "width_px": 31}, headers=headers)
        assert conflict.status == 409 and conflict.json_body["detail"]["code"] == "CLIENT_UPLOAD_ID_CONFLICT"

        for invalid in (
            {**intent_body, "client_upload_id": "bad-mime", "mime_type": "video/mp4"},
            {**intent_body, "client_upload_id": "bad-size", "file_size_bytes": -1},
            {**intent_body, "client_upload_id": "bad-width", "width_px": 0},
            {**intent_body, "client_upload_id": "bad-key", "client_upload_id": "../path"},
        ):
            response = await asgi_request(app, "POST", "/api/v1/messages/media/upload-intents", invalid, headers=headers)
            assert response.status == 422, response

        boundary = f"message-image-{uuid.uuid4().hex}"
        upload = await asgi_bytes_request(
            app,
            "POST",
            f"/api/v1/messages/media/{media_id}/file",
            multipart_video_body(boundary=boundary, filename="photo.jpg", content_type="image/jpeg", content=raw),
            {**headers, "content-type": f"multipart/form-data; boundary={boundary}"},
        )
        assert upload.status == 200 and upload.json_body["media"]["upload_status"] == "uploading", upload
        complete = await asgi_request(app, "POST", f"/api/v1/messages/media/{media_id}/complete", headers=headers)
        assert complete.status == 200 and complete.json_body["media"]["upload_status"] == "uploaded", complete
        assert complete.json_body["media"]["thumbnail_status"] == "generated"
        assert complete.json_body["media"]["thumbnail_url"]
        complete_retry = await asgi_request(app, "POST", f"/api/v1/messages/media/{media_id}/complete", headers=headers)
        assert complete_retry.status == 200 and complete_retry.json_body["media"]["media_id"] == media_id
        assert "storage_key" not in str(complete_retry.json_body)

        denied = await asgi_request(app, "GET", f"/api/v1/messages/media/{media_id}", headers=other_headers)
        assert denied.status == 404, denied
        with get_connection() as connection:
            assert connection.execute("SELECT COUNT(*) FROM chat_messages;").fetchone()[0] == 0
            assert connection.execute("SELECT upload_status FROM chat_message_media WHERE media_id = ?;", (media_id,)).fetchone()[0] == "uploaded"

        missing = await asgi_request(app, "POST", "/api/v1/messages/media/upload-intents", {**intent_body, "client_upload_id": "missing"}, headers=headers)
        missing_id = missing.json_body["media"]["media_id"]
        missing_complete = await asgi_request(app, "POST", f"/api/v1/messages/media/{missing_id}/complete", headers=headers)
        assert missing_complete.status == 409, missing_complete
        with get_connection() as connection:
            assert connection.execute("SELECT upload_status FROM chat_message_media WHERE media_id = ?;", (missing_id,)).fetchone()[0] == "created"

        canceled = await asgi_request(app, "POST", f"/api/v1/messages/media/{missing_id}/cancel", headers=headers)
        assert canceled.status == 200 and canceled.json_body["media"]["upload_status"] == "deleted"
        canceled_retry = await asgi_request(app, "POST", f"/api/v1/messages/media/{missing_id}/cancel", headers=headers)
        assert canceled_retry.status == 200 and canceled_retry.json_body["media"]["upload_status"] == "deleted"

        expired_intent = await asgi_request(app, "POST", "/api/v1/messages/media/upload-intents", {**intent_body, "client_upload_id": "expired"}, headers=headers)
        expired_id = expired_intent.json_body["media"]["media_id"]
        with get_connection() as connection:
            connection.execute("UPDATE chat_message_media SET expires_at = '2000-01-01T00:00:00Z' WHERE media_id = ?;", (expired_id,))
            connection.commit()
        expired_read = await asgi_request(app, "GET", f"/api/v1/messages/media/{expired_id}", headers=headers)
        assert expired_read.status == 404
        with get_connection() as connection:
            assert connection.execute("SELECT upload_status FROM chat_message_media WHERE media_id = ?;", (expired_id,)).fetchone()[0] == "expired"

        print("Message media upload API test passed.")


if __name__ == "__main__":
    asyncio.run(main())
