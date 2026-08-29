from __future__ import annotations

import asyncio
from hashlib import sha256
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import uuid

ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT_DIR))

from backend.tests.activity_detail_api_smoke import login_phone
from backend.tests.auth_api_smoke import asgi_request
from backend.tests.upload_api_smoke import asgi_bytes_request, multipart_video_body


def video_bytes(directory: Path) -> bytes:
    output = directory / "fixture.mp4"
    ffmpeg = os.getenv("TENNIS_FFMPEG_PATH") or "ffmpeg"
    subprocess.run([ffmpeg, "-y", "-v", "error", "-f", "lavfi", "-i", "color=c=red:s=64x48:d=1", "-pix_fmt", "yuv420p", str(output)], check=True, capture_output=True)
    return output.read_bytes()


async def main() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        os.environ["TENNIS_DB_PATH"] = str(root / "message_video.sqlite3")
        os.environ["TENNIS_MESSAGE_MEDIA_STORAGE_DIR"] = str(root / "message-media")
        from backend.app.core.database import get_connection, initialize_database
        from backend.app.main import app

        initialize_database()
        token, user_id = await login_phone(app, "13600000001")
        other_token, other_id = await login_phone(app, "13600000002")
        headers = {"authorization": f"Bearer {token}"}
        other_headers = {"authorization": f"Bearer {other_token}"}
        await asgi_request(app, "POST", f"/api/v1/social/follows/{other_id}", headers=headers)
        await asgi_request(app, "POST", f"/api/v1/social/follows/{user_id}", headers=other_headers)
        conversation = await asgi_request(app, "POST", "/api/v1/messages/direct-conversations", {"target_user_id": other_id}, headers=headers)
        conversation_id = conversation.json_body["conversation"]["conversation_id"]
        raw = video_bytes(root)
        checksum = sha256(raw).hexdigest()
        intent = await asgi_request(app, "POST", "/api/v1/messages/media/upload-intents", {"media_type": "video", "mime_type": "video/mp4", "file_size_bytes": len(raw), "width_px": 64, "height_px": 48, "duration_ms": 1000, "expected_checksum_sha256": checksum, "client_upload_id": "video-upload-1"}, headers=headers)
        assert intent.status == 201, intent
        media_id = intent.json_body["media"]["media_id"]
        boundary = f"video-{uuid.uuid4().hex}"
        upload = await asgi_bytes_request(app, "POST", f"/api/v1/messages/media/{media_id}/file", multipart_video_body(boundary=boundary, filename="clip.mp4", content_type="video/mp4", content=raw), {**headers, "content-type": f"multipart/form-data; boundary={boundary}"})
        assert upload.status == 200, upload
        complete = await asgi_request(app, "POST", f"/api/v1/messages/media/{media_id}/complete", headers=headers)
        assert complete.status == 200 and complete.json_body["media"]["upload_status"] == "uploaded", complete
        assert complete.json_body["media"]["checksum_sha256"] == checksum
        assert complete.json_body["media"]["thumbnail_url"]
        sent = await asgi_request(app, "POST", f"/api/v1/messages/conversations/{conversation_id}/messages", {"message_type": "video", "client_message_id": "video-message-1", "attachments": [{"attachment_type": "video", "media_id": media_id}]}, headers=headers)
        assert sent.status == 201, sent
        assert sent.json_body["message"]["attachments"][0]["attachment_type"] == "video"
        assert "storage_key" not in str(sent.json_body)
        history = await asgi_request(app, "GET", f"/api/v1/messages/conversations/{conversation_id}/messages", headers=other_headers)
        assert history.status == 200 and history.json_body["items"][0]["message_type"] == "video"
        assert history.json_body["items"][0]["attachments"][0]["thumbnail_url"]
        print("Message video upload API test passed.")


if __name__ == "__main__":
    asyncio.run(main())
