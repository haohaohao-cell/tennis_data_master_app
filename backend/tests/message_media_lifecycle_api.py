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


def image_bytes(size: tuple[int, int] = (1200, 800)) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", size, (30, 110, 190)).save(buffer, format="JPEG")
    return buffer.getvalue()


async def main() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        storage = Path(temp_dir) / "message-media"
        os.environ["TENNIS_DB_PATH"] = str(Path(temp_dir) / "lifecycle.sqlite3")
        os.environ["TENNIS_MESSAGE_MEDIA_STORAGE_DIR"] = str(storage)
        from backend.app.core.database import get_connection, initialize_database
        from backend.app.main import app
        from backend.app.messages.media_cleanup import cleanup_message_media

        initialize_database()
        token, user_id = await login_phone(app, "13800000001")
        headers = {"authorization": f"Bearer {token}"}
        raw = image_bytes()
        payload = {
            "media_type": "image", "mime_type": "image/jpeg",
            "file_size_bytes": len(raw), "width_px": 1200, "height_px": 800,
            "client_upload_id": "stage7-lifecycle",
        }
        intent = await asgi_request(app, "POST", "/api/v1/messages/media/upload-intents", payload, headers=headers)
        media_id = intent.json_body["media"]["media_id"]
        boundary = f"stage7-{uuid.uuid4().hex}"
        upload = await asgi_bytes_request(
            app, "POST", f"/api/v1/messages/media/{media_id}/file",
            multipart_video_body(boundary=boundary, filename="image.jpg", content_type="image/jpeg", content=raw),
            {**headers, "content-type": f"multipart/form-data; boundary={boundary}"},
        )
        assert upload.status == 200
        complete = await asgi_request(app, "POST", f"/api/v1/messages/media/{media_id}/complete", headers=headers)
        assert complete.status == 200
        assert complete.json_body["media"]["thumbnail_status"] == "generated"
        original = storage / f"images/{media_id}/original.jpg"
        thumbnail = storage / f"images/{media_id}/thumbnail.jpg"
        assert original.is_file() and thumbnail.is_file()
        with Image.open(thumbnail) as image:
            assert image.width <= 640 and image.height <= 640

        thumbnail.unlink()
        read = await asgi_request(app, "GET", f"/api/v1/messages/media/{media_id}", headers=headers)
        assert read.status == 200 and read.json_body["media"]["thumbnail_url"] is None

        failed_payload = {**payload, "client_upload_id": "stage7-thumbnail-failure"}
        failed_intent = await asgi_request(app, "POST", "/api/v1/messages/media/upload-intents", failed_payload, headers=headers)
        failed_id = failed_intent.json_body["media"]["media_id"]
        failed_boundary = f"stage7-failed-{uuid.uuid4().hex}"
        await asgi_bytes_request(
            app, "POST", f"/api/v1/messages/media/{failed_id}/file",
            multipart_video_body(boundary=failed_boundary, filename="image.jpg", content_type="image/jpeg", content=raw),
            {**headers, "content-type": f"multipart/form-data; boundary={failed_boundary}"},
        )
        from unittest.mock import patch
        with patch("backend.app.messages.media_service.create_thumbnail", side_effect=RuntimeError("test")):
            failed_complete = await asgi_request(app, "POST", f"/api/v1/messages/media/{failed_id}/complete", headers=headers)
        assert failed_complete.status == 200
        assert failed_complete.json_body["media"]["upload_status"] == "uploaded"
        assert failed_complete.json_body["media"]["thumbnail_status"] == "failed"
        assert (storage / f"images/{failed_id}/original.jpg").is_file()

        orphan = storage / "images/orphan/original.jpg"
        orphan.parent.mkdir(parents=True)
        orphan.write_bytes(b"orphan")
        dry_run = cleanup_message_media(dry_run=True)
        assert dry_run["dry_run"] is True and "images/orphan/original.jpg" in dry_run["orphan_files"]
        assert orphan.is_file()

        with get_connection() as connection:
            connection.execute("UPDATE chat_message_media SET expires_at = '2000-01-01T00:00:00Z' WHERE media_id = ?;", (media_id,))
            connection.commit()
        execute = cleanup_message_media(dry_run=False)
        assert any(item.get("media_id") == media_id for item in execute["deleted_files"])
        assert not original.exists() and not thumbnail.exists() and not orphan.exists()
        repeat = cleanup_message_media(dry_run=False)
        assert not repeat["errors"]

        malformed_payload = {**payload, "client_upload_id": "stage8-malformed-expiry"}
        malformed_intent = await asgi_request(app, "POST", "/api/v1/messages/media/upload-intents", malformed_payload, headers=headers)
        malformed_id = malformed_intent.json_body["media"]["media_id"]
        malformed_original = storage / f"images/{malformed_id}/original.jpg"
        malformed_original.parent.mkdir(parents=True, exist_ok=True)
        malformed_original.write_bytes(raw)
        with get_connection() as connection:
            connection.execute("UPDATE chat_message_media SET expires_at = 'not-a-timestamp' WHERE media_id = ?;", (malformed_id,))
            connection.commit()
        malformed = cleanup_message_media(dry_run=False)
        assert {item["media_id"] for item in malformed["errors"] if item.get("error") == "INVALID_EXPIRES_AT"} == {malformed_id}
        assert malformed_original.is_file()
        print("Message media lifecycle API test passed.")


if __name__ == "__main__":
    asyncio.run(main())
