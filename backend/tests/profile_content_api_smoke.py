from __future__ import annotations

import asyncio
import os
from pathlib import Path
import sys
import tempfile


ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT_DIR))

from backend.tests.auth_api_smoke import asgi_request
from backend.tests.upload_api_smoke import asgi_bytes_request, multipart_video_body


async def main() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        storage_dir = Path(temp_dir) / "videos"
        os.environ["TENNIS_DB_PATH"] = str(Path(temp_dir) / "profile_content_api_smoke.sqlite3")
        os.environ["TENNIS_VIDEO_STORAGE_DIR"] = str(storage_dir)

        from backend.app.core.database import initialize_database
        from backend.app.main import app

        initialize_database()

        login = await asgi_request(
            app,
            "POST",
            "/api/v1/auth/phone-login",
            {"phone": "13600000001", "code": "000000"},
        )
        assert login.status == 200, login
        headers = {"authorization": f"Bearer {login.json_body['access_token']}"}

        empty_content = await asgi_request(
            app,
            "GET",
            "/api/v1/me/profile-content",
            headers=headers,
        )
        assert empty_content.status == 200, empty_content
        assert empty_content.json_body["stats"]["training"] == 0

        video_bytes = b"profile content smoke video"
        intent = await asgi_request(
            app,
            "POST",
            "/api/v1/tennis-activities/upload-intents",
            {
                "title": "Profile Visible Training",
                "activity_type": "other",
                "default_visibility": "private",
                "videos": [
                    {
                        "original_filename": "profile-training.mp4",
                        "mime_type": "video/mp4",
                        "file_size_bytes": len(video_bytes),
                    }
                ],
            },
            headers=headers,
        )
        assert intent.status == 201, intent
        activity_id = intent.json_body["activity"]["tennis_activity_id"]
        video_id = intent.json_body["videos"][0]["video_id"]

        boundary = "----profile-content-smoke-boundary"
        upload = await asgi_bytes_request(
            app,
            "POST",
            f"/api/v1/videos/{video_id}/file",
            multipart_video_body(
                boundary=boundary,
                filename="profile-training.mp4",
                content_type="video/mp4",
                content=video_bytes,
            ),
            {
                **headers,
                "content-type": f"multipart/form-data; boundary={boundary}",
            },
        )
        assert upload.status == 200, upload

        complete = await asgi_request(
            app,
            "POST",
            f"/api/v1/tennis-activities/{activity_id}/complete-upload",
            headers=headers,
        )
        assert complete.status == 200, complete

        content = await asgi_request(
            app,
            "GET",
            "/api/v1/me/profile-content",
            headers=headers,
        )
        assert content.status == 200, content
        assert content.json_body["stats"]["training"] == 1
        training = content.json_body["training"][0]
        assert training["tennis_activity_id"] == activity_id
        assert training["title"] == "Profile Visible Training"
        assert training["video_count"] == 1
        assert training["uploaded_video_count"] == 1
        assert training["upload_status"] == "uploaded"
        assert training["analysis_status"] == "queued"
        assert training["first_video"]["video_id"] == video_id
        assert training["first_video"]["thumbnail_path"], training
        activity_thumbnail_file = storage_dir / training["first_video"]["thumbnail_path"].removeprefix(
            "/storage/videos/"
        ).replace("/", os.sep)
        assert activity_thumbnail_file.is_file(), activity_thumbnail_file

        post_video_bytes = b"profile content post video"
        post_intent = await asgi_request(
            app,
            "POST",
            "/api/v1/posts/upload-intents",
            {
                "title": "Profile Visible Post",
                "content": "A post that should be tappable and have a thumbnail.",
                "visibility": "public",
                "videos": [
                    {
                        "original_filename": "profile-post.mp4",
                        "mime_type": "video/mp4",
                        "file_size_bytes": len(post_video_bytes),
                        "video_duration_ms": 12_000,
                    }
                ],
            },
            headers=headers,
        )
        assert post_intent.status == 201, post_intent
        post_id = post_intent.json_body["post"]["social_post_id"]
        post_video_id = post_intent.json_body["videos"][0]["video_id"]
        post_boundary = "----profile-content-post-smoke-boundary"
        post_upload = await asgi_bytes_request(
            app,
            "POST",
            f"/api/v1/videos/{post_video_id}/file",
            multipart_video_body(
                boundary=post_boundary,
                filename="profile-post.mp4",
                content_type="video/mp4",
                content=post_video_bytes,
            ),
            {
                **headers,
                "content-type": f"multipart/form-data; boundary={post_boundary}",
            },
        )
        assert post_upload.status == 200, post_upload
        assert post_upload.json_body["video"]["thumbnail_path"], post_upload
        publish = await asgi_request(
            app,
            "POST",
            f"/api/v1/posts/{post_id}/publish",
            headers=headers,
        )
        assert publish.status == 200, publish

        content_after_post = await asgi_request(
            app,
            "GET",
            "/api/v1/me/profile-content",
            headers=headers,
        )
        assert content_after_post.status == 200, content_after_post
        assert content_after_post.json_body["stats"]["posts"] == 1
        profile_post = content_after_post.json_body["posts"][0]
        assert profile_post["social_post_id"] == post_id
        assert profile_post["first_video_thumbnail_path"], profile_post
        post_thumbnail_file = storage_dir / profile_post["first_video_thumbnail_path"].removeprefix(
            "/storage/videos/"
        ).replace("/", os.sep)
        assert post_thumbnail_file.is_file(), post_thumbnail_file

        print("Profile content API smoke test passed.")


if __name__ == "__main__":
    asyncio.run(main())
