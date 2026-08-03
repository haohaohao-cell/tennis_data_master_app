from __future__ import annotations

import asyncio
import os
from pathlib import Path
import sys
import tempfile
import uuid


ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT_DIR))

from backend.tests.auth_api_smoke import asgi_request
from backend.tests.upload_api_smoke import asgi_bytes_request, multipart_video_body


async def login_phone(app, phone: str) -> tuple[str, str]:
    response = await asgi_request(
        app,
        "POST",
        "/api/v1/auth/phone-login",
        {"phone": phone, "code": "000000"},
    )
    assert response.status == 200, response
    return response.json_body["access_token"], response.json_body["user"]["user_id"]


async def main() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        os.environ["TENNIS_DB_PATH"] = str(Path(temp_dir) / "activity_detail_api_smoke.sqlite3")
        os.environ["TENNIS_VIDEO_STORAGE_DIR"] = str(Path(temp_dir) / "videos")

        from backend.app.core.database import initialize_database, transaction
        from backend.app.main import app

        initialize_database()

        coach_token, coach_id = await login_phone(app, "13500000001")
        student_token, student_id = await login_phone(app, "13500000002")
        peer_token, peer_id = await login_phone(app, "13500000003")
        outsider_token, _ = await login_phone(app, "13500000004")

        lesson_id = str(uuid.uuid4())
        with transaction() as connection:
            connection.execute(
                """
                INSERT INTO lessons (
                    lesson_id,
                    coach_user_id,
                    title,
                    lesson_type,
                    status,
                    started_at,
                    location_name,
                    training_content,
                    homework,
                    next_focus,
                    created_by_user_id
                )
                VALUES (?, ?, 'Serve rhythm lesson', 'private', 'completed',
                    '2026-07-30T10:00:00Z', 'Court 8',
                    'Serve toss and first-step recovery',
                    'Upload two serve clips',
                    'Return stance',
                    ?);
                """,
                (lesson_id, coach_id, coach_id),
            )
            for user_id in (student_id, peer_id):
                connection.execute(
                    """
                    INSERT INTO lesson_students (
                        lesson_student_id,
                        lesson_id,
                        student_user_id,
                        attendance_status,
                        created_by_user_id
                    )
                    VALUES (?, ?, ?, 'attended', ?);
                    """,
                    (str(uuid.uuid4()), lesson_id, user_id, coach_id),
                )

        student_headers = {"authorization": f"Bearer {student_token}"}
        video_bytes = b"lesson practice activity detail video"
        intent = await asgi_request(
            app,
            "POST",
            "/api/v1/tennis-activities/upload-intents",
            {
                "title": "Student Serve Practice",
                "lesson_id": lesson_id,
                "activity_type": "lesson_practice",
                "default_visibility": "lesson_coach",
                "location": {
                    "source": "device_gps",
                    "latitude": 39.9929,
                    "longitude": 116.3109,
                    "accuracy_m": 16,
                    "captured_at": "2026-08-03T09:30:00Z",
                    "country_code": "CN",
                    "region": "北京市",
                    "city": "北京市",
                    "district": "海淀区",
                    "address_label": "北京市海淀区",
                    "coordinate_system": "wgs84",
                },
                "videos": [
                    {
                        "original_filename": "serve-practice.mp4",
                        "mime_type": "video/mp4",
                        "file_size_bytes": len(video_bytes),
                    }
                ],
            },
            headers=student_headers,
        )
        assert intent.status == 201, intent
        activity_id = intent.json_body["activity"]["tennis_activity_id"]
        video_id = intent.json_body["videos"][0]["video_id"]

        boundary = "----activity-detail-smoke-boundary"
        upload = await asgi_bytes_request(
            app,
            "POST",
            f"/api/v1/videos/{video_id}/file",
            multipart_video_body(
                boundary=boundary,
                filename="serve-practice.mp4",
                content_type="video/mp4",
                content=video_bytes,
            ),
            {
                **student_headers,
                "content-type": f"multipart/form-data; boundary={boundary}",
            },
        )
        assert upload.status == 200, upload

        complete = await asgi_request(
            app,
            "POST",
            f"/api/v1/tennis-activities/{activity_id}/complete-upload",
            headers=student_headers,
        )
        assert complete.status == 200, complete

        student_detail = await asgi_request(
            app,
            "GET",
            f"/api/v1/tennis-activities/{activity_id}",
            headers=student_headers,
        )
        assert student_detail.status == 200, student_detail
        assert student_detail.json_body["activity"]["tennis_activity_id"] == activity_id
        assert student_detail.json_body["lesson"]["lesson_id"] == lesson_id
        assert student_detail.json_body["lesson"]["viewer_role"] == "student"
        assert student_detail.json_body["permissions"]["can_manage"] is True
        assert student_detail.json_body["permissions"]["can_play_videos"] is True
        assert student_detail.json_body["summary"]["video_count"] == 1
        assert student_detail.json_body["summary"]["uploaded_video_count"] == 1
        assert student_detail.json_body["activity"]["location"]["latitude"] == 39.9929
        assert student_detail.json_body["activity"]["location"]["district"] == "海淀区"
        assert student_detail.json_body["videos"][0]["video_id"] == video_id

        coach_detail = await asgi_request(
            app,
            "GET",
            f"/api/v1/tennis-activities/{activity_id}",
            headers={"authorization": f"Bearer {coach_token}"},
        )
        assert coach_detail.status == 200, coach_detail
        assert coach_detail.json_body["lesson"]["viewer_role"] == "coach"
        assert coach_detail.json_body["permissions"]["can_manage"] is False
        assert coach_detail.json_body["activity"]["location"]["latitude"] is None
        assert coach_detail.json_body["activity"]["location"]["longitude"] is None
        assert coach_detail.json_body["activity"]["location"]["district"] == "海淀区"
        assert coach_detail.json_body["videos"][0]["video_id"] == video_id

        peer_detail = await asgi_request(
            app,
            "GET",
            f"/api/v1/tennis-activities/{activity_id}",
            headers={"authorization": f"Bearer {peer_token}"},
        )
        assert peer_detail.status == 404, peer_detail

        outsider_detail = await asgi_request(
            app,
            "GET",
            f"/api/v1/tennis-activities/{activity_id}",
            headers={"authorization": f"Bearer {outsider_token}"},
        )
        assert outsider_detail.status == 404, outsider_detail

        print("Activity detail API smoke test passed.")


if __name__ == "__main__":
    asyncio.run(main())
