from __future__ import annotations

import asyncio
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
from collections.abc import Awaitable, Callable
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT_DIR))

from backend.tests.auth_api_smoke import AsgiResponse, asgi_request


async def asgi_bytes_request(
    app: Callable[..., Awaitable[None]],
    method: str,
    path: str,
    body_bytes: bytes,
    headers: dict[str, str],
) -> AsgiResponse:
    raw_headers = [
        (key.lower().encode("latin-1"), value.encode("latin-1"))
        for key, value in headers.items()
    ]
    raw_headers.append((b"content-length", str(len(body_bytes)).encode("latin-1")))

    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode("ascii"),
        "query_string": b"",
        "headers": raw_headers,
        "client": ("127.0.0.1", 50000),
        "server": ("testserver", 80),
    }
    received = False
    response_status = 500
    response_headers: dict[str, str] = {}
    response_body = bytearray()

    async def receive() -> dict[str, Any]:
        nonlocal received
        if not received:
            received = True
            return {"type": "http.request", "body": body_bytes, "more_body": False}
        return {"type": "http.disconnect"}

    async def send(message: dict[str, Any]) -> None:
        nonlocal response_status, response_headers
        if message["type"] == "http.response.start":
            response_status = message["status"]
            response_headers = {
                key.decode("latin-1"): value.decode("latin-1")
                for key, value in message.get("headers", [])
            }
        if message["type"] == "http.response.body":
            response_body.extend(message.get("body", b""))

    await app(scope, receive, send)
    payload = json.loads(response_body.decode("utf-8")) if response_body else {}
    return AsgiResponse(status=response_status, headers=response_headers, json_body=payload)


def multipart_video_body(
    *,
    boundary: str,
    filename: str,
    content_type: str,
    content: bytes,
) -> bytes:
    return b"".join(
        [
            f"--{boundary}\r\n".encode("utf-8"),
            f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'.encode(
                "utf-8"
            ),
            f"Content-Type: {content_type}\r\n\r\n".encode("utf-8"),
            content,
            f"\r\n--{boundary}--\r\n".encode("utf-8"),
        ]
    )


async def main() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        storage_dir = Path(temp_dir) / "videos"
        os.environ["TENNIS_DB_PATH"] = str(Path(temp_dir) / "upload_api_smoke.sqlite3")
        os.environ["TENNIS_VIDEO_STORAGE_DIR"] = str(storage_dir)

        from backend.app.core.database import initialize_database
        from backend.app.main import app

        initialize_database()

        login = await asgi_request(
            app,
            "POST",
            "/api/v1/auth/phone-login",
            {"phone": "13700000001", "code": "000000"},
        )
        assert login.status == 200, login
        access_token = login.json_body["access_token"]
        headers = {"authorization": f"Bearer {access_token}"}

        video_bytes = b"fake mp4 bytes for smoke test"
        intent = await asgi_request(
            app,
            "POST",
            "/api/v1/tennis-activities/upload-intents",
            {
                "title": "Upload Smoke Activity",
                "activity_type": "other",
                "default_visibility": "private",
                "location": {
                    "source": "device_gps",
                    "latitude": 39.9042,
                    "longitude": 116.4074,
                    "accuracy_m": 18.5,
                    "captured_at": "2026-08-03T10:00:00Z",
                    "country_code": "CN",
                    "region": "北京市",
                    "city": "北京市",
                    "district": "东城区",
                    "address_label": "北京市东城区",
                    "coordinate_system": "wgs84",
                },
                "videos": [
                    {
                        "original_filename": "smoke.mp4",
                        "mime_type": "video/mp4",
                        "file_size_bytes": len(video_bytes),
                    }
                ],
            },
            headers=headers,
        )
        assert intent.status == 201, intent
        activity_id = intent.json_body["activity"]["tennis_activity_id"]
        assert intent.json_body["activity"]["location"]["latitude"] == 39.9042
        assert intent.json_body["activity"]["location_name"] == "北京市 东城区"
        video = intent.json_body["videos"][0]
        assert video["upload_status"] == "pending"

        boundary = "----tennis-upload-smoke-boundary"
        upload = await asgi_bytes_request(
            app,
            "POST",
            f"/api/v1/videos/{video['video_id']}/file",
            multipart_video_body(
                boundary=boundary,
                filename="smoke.mp4",
                content_type="video/mp4",
                content=video_bytes,
            ),
            {
                **headers,
                "content-type": f"multipart/form-data; boundary={boundary}",
            },
        )
        assert upload.status == 200, upload
        assert upload.json_body["video"]["upload_status"] == "uploaded"
        assert upload.json_body["video"]["file_hash"] == hashlib.sha256(video_bytes).hexdigest()
        assert upload.json_body["video"]["thumbnail_path"], upload

        public_path = upload.json_body["video"]["video_path"]
        stored_file = storage_dir / public_path.removeprefix("/storage/videos/").replace("/", os.sep)
        assert stored_file.read_bytes() == video_bytes
        thumbnail_path = upload.json_body["video"]["thumbnail_path"]
        thumbnail_file = storage_dir / thumbnail_path.removeprefix("/storage/videos/").replace("/", os.sep)
        assert thumbnail_file.is_file(), thumbnail_file

        complete = await asgi_request(
            app,
            "POST",
            f"/api/v1/tennis-activities/{activity_id}/complete-upload",
            headers=headers,
        )
        assert complete.status == 200, complete
        assert complete.json_body["queued_count"] == 1
        assert complete.json_body["videos"][0]["analysis_status"] == "queued"

        detail = await asgi_request(
            app,
            "GET",
            f"/api/v1/tennis-activities/{activity_id}",
            headers=headers,
        )
        assert detail.status == 200, detail
        assert detail.json_body["videos"][0]["upload_status"] == "uploaded"

        other_login = await asgi_request(
            app,
            "POST",
            "/api/v1/auth/phone-login",
            {"phone": "13700000002", "code": "000000"},
        )
        assert other_login.status == 200, other_login
        other_delete = await asgi_request(
            app,
            "DELETE",
            f"/api/v1/tennis-activities/{activity_id}",
            headers={"authorization": f"Bearer {other_login.json_body['access_token']}"},
        )
        assert other_delete.status == 404, other_delete

        deleted = await asgi_request(
            app,
            "DELETE",
            f"/api/v1/tennis-activities/{activity_id}",
            headers=headers,
        )
        assert deleted.status == 200, deleted
        assert deleted.json_body == {"success": True, "id": activity_id}
        assert not stored_file.exists()
        assert not thumbnail_file.exists()

        deleted_detail = await asgi_request(
            app,
            "GET",
            f"/api/v1/tennis-activities/{activity_id}",
            headers=headers,
        )
        assert deleted_detail.status == 404, deleted_detail

        repeated_delete = await asgi_request(
            app,
            "DELETE",
            f"/api/v1/tennis-activities/{activity_id}",
            headers=headers,
        )
        assert repeated_delete.status == 404, repeated_delete

        record = await asgi_request(
            app,
            "POST",
            "/api/v1/tennis-activities",
            {
                "title": "Singles Match Record",
                "activity_type": "match",
                "default_visibility": "private",
                "location": {
                    "source": "device_gps",
                    "latitude": 31.2304,
                    "longitude": 121.4737,
                    "accuracy_m": 12,
                    "captured_at": "2026-08-03T10:05:00Z",
                    "country_code": "CN",
                    "region": "上海市",
                    "city": "上海市",
                    "district": "黄浦区",
                    "address_label": "上海市黄浦区",
                    "coordinate_system": "wgs84",
                },
                "opponent_name": "Alex",
                "note": "6-4 practice match",
            },
            headers=headers,
        )
        assert record.status == 201, record
        record_activity_id = record.json_body["tennis_activity_id"]
        assert record.json_body["activity_type"] == "match"
        assert record.json_body["opponent_name"] == "Alex"
        assert record.json_body["location"]["district"] == "黄浦区"
        record_detail = await asgi_request(
            app,
            "GET",
            f"/api/v1/tennis-activities/{record_activity_id}",
            headers=headers,
        )
        assert record_detail.status == 200, record_detail
        assert record_detail.json_body["activity"]["location"]["latitude"] == 31.2304
        assert record_detail.json_body["summary"]["video_count"] == 0
        assert record_detail.json_body["summary"]["analysis_status"] == "none"
        assert record_detail.json_body["videos"] == []

        record_deleted = await asgi_request(
            app,
            "DELETE",
            f"/api/v1/tennis-activities/{record_activity_id}",
            headers=headers,
        )
        assert record_deleted.status == 200, record_deleted

        match_upload_intent = await asgi_request(
            app,
            "POST",
            "/api/v1/tennis-activities/upload-intents",
            {
                "title": "Match Video Activity",
                "activity_type": "match",
                "default_visibility": "private",
                "opponent_name": "Taylor",
                "videos": [
                    {
                        "original_filename": "match.mp4",
                        "mime_type": "video/mp4",
                        "file_size_bytes": len(video_bytes),
                    }
                ],
            },
            headers=headers,
        )
        assert match_upload_intent.status == 201, match_upload_intent
        assert match_upload_intent.json_body["activity"]["activity_type"] == "match"
        assert match_upload_intent.json_body["activity"]["opponent_name"] == "Taylor"

        mov_bytes = b"fake mov bytes for smoke test"
        mov_intent = await asgi_request(
            app,
            "POST",
            "/api/v1/tennis-activities/upload-intents",
            {
                "title": "Upload MOV Smoke Activity",
                "activity_type": "other",
                "default_visibility": "private",
                "videos": [
                    {
                        "original_filename": "smoke-recording.MOV",
                        "mime_type": "application/quicktime",
                        "file_size_bytes": len(mov_bytes),
                    }
                ],
            },
            headers=headers,
        )
        assert mov_intent.status == 201, mov_intent
        mov_video = mov_intent.json_body["videos"][0]
        assert mov_video["filename"].endswith(".mov"), mov_intent

        mov_boundary = "----tennis-mov-upload-boundary"
        mov_upload = await asgi_bytes_request(
            app,
            "POST",
            f"/api/v1/videos/{mov_video['video_id']}/file",
            multipart_video_body(
                boundary=mov_boundary,
                filename="smoke-recording.MOV",
                content_type="application/quicktime",
                content=mov_bytes,
            ),
            {
                **headers,
                "content-type": f"multipart/form-data; boundary={mov_boundary}",
            },
        )
        assert mov_upload.status == 200, mov_upload
        assert mov_upload.json_body["video"]["thumbnail_path"], mov_upload

        mismatch_bytes = b"camera roll exported bytes"
        mismatch_intent = await asgi_request(
            app,
            "POST",
            "/api/v1/tennis-activities/upload-intents",
            {
                "title": "Upload Size Advisory Activity",
                "activity_type": "other",
                "default_visibility": "private",
                "videos": [
                    {
                        "original_filename": "phone-camera.mp4",
                        "mime_type": "video/mp4",
                        "file_size_bytes": len(mismatch_bytes) + 99,
                    }
                ],
            },
            headers=headers,
        )
        assert mismatch_intent.status == 201, mismatch_intent
        mismatch_video = mismatch_intent.json_body["videos"][0]
        mismatch_boundary = "----tennis-upload-size-advisory-boundary"
        mismatch_upload = await asgi_bytes_request(
            app,
            "POST",
            f"/api/v1/videos/{mismatch_video['video_id']}/file",
            multipart_video_body(
                boundary=mismatch_boundary,
                filename="phone-camera.mp4",
                content_type="video/mp4",
                content=mismatch_bytes,
            ),
            {
                **headers,
                "content-type": f"multipart/form-data; boundary={mismatch_boundary}",
            },
        )
        assert mismatch_upload.status == 200, mismatch_upload
        assert mismatch_upload.json_body["video"]["upload_status"] == "uploaded"
        assert mismatch_upload.json_body["video"]["thumbnail_path"], mismatch_upload
        assert mismatch_upload.json_body["video"]["file_size_bytes"] == len(mismatch_bytes)
        assert (
            mismatch_upload.json_body["video"]["file_hash"]
            == hashlib.sha256(mismatch_bytes).hexdigest()
        )

        print("Upload API smoke test passed.")


if __name__ == "__main__":
    asyncio.run(main())
