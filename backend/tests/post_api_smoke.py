from __future__ import annotations

import asyncio
import os
from pathlib import Path
import sys
import tempfile


ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT_DIR))

from backend.tests.activity_detail_api_smoke import login_phone
from backend.tests.auth_api_smoke import asgi_request
from backend.tests.upload_api_smoke import asgi_bytes_request, multipart_video_body


async def main() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        storage_dir = Path(temp_dir) / "videos"
        os.environ["TENNIS_DB_PATH"] = str(Path(temp_dir) / "post_api_smoke.sqlite3")
        os.environ["TENNIS_VIDEO_STORAGE_DIR"] = str(storage_dir)

        from backend.app.core.database import initialize_database
        from backend.app.main import app

        initialize_database()

        access_token, user_id = await login_phone(app, "13600000001")
        other_token, _ = await login_phone(app, "13600000002")
        headers = {"authorization": f"Bearer {access_token}"}

        post_video_bytes = b"short social post video"
        intent = await asgi_request(
            app,
            "POST",
            "/api/v1/posts/upload-intents",
            {
                "content": "Serve rhythm finally felt cleaner.",
                "visibility": "public",
                "videos": [
                    {
                        "original_filename": "serve-post.MOV",
                        "mime_type": "application/quicktime",
                        "file_size_bytes": len(post_video_bytes),
                        "video_duration_ms": 42_000,
                    }
                ],
            },
            headers=headers,
        )
        assert intent.status == 201, intent
        post_id = intent.json_body["post"]["social_post_id"]
        post_video_id = intent.json_body["videos"][0]["video_id"]
        assert intent.json_body["post"]["status"] == "draft"
        assert intent.json_body["videos"][0]["tennis_activity_id"] is None
        assert intent.json_body["videos"][0]["filename"].endswith(".mov")

        draft_detail = await asgi_request(
            app,
            "GET",
            f"/api/v1/posts/{post_id}",
            headers=headers,
        )
        assert draft_detail.status == 200, draft_detail
        assert draft_detail.json_body["post"]["status"] == "draft"

        other_draft_detail = await asgi_request(
            app,
            "GET",
            f"/api/v1/posts/{post_id}",
            headers={"authorization": f"Bearer {other_token}"},
        )
        assert other_draft_detail.status == 404, other_draft_detail

        anonymous_draft_detail = await asgi_request(
            app,
            "GET",
            f"/api/v1/posts/{post_id}",
        )
        assert anonymous_draft_detail.status == 404, anonymous_draft_detail

        premature_publish = await asgi_request(
            app,
            "POST",
            f"/api/v1/posts/{post_id}/publish",
            headers=headers,
        )
        assert premature_publish.status == 409, premature_publish
        assert premature_publish.json_body["detail"]["code"] == "POST_MEDIA_UPLOAD_INCOMPLETE"

        boundary = "----tennis-post-upload-boundary"
        upload = await asgi_bytes_request(
            app,
            "POST",
            f"/api/v1/videos/{post_video_id}/file",
            multipart_video_body(
                boundary=boundary,
                filename="serve-post.MOV",
                content_type="application/quicktime",
                content=post_video_bytes,
            ),
            {
                **headers,
                "content-type": f"multipart/form-data; boundary={boundary}",
            },
        )
        assert upload.status == 200, upload
        assert upload.json_body["video"]["upload_status"] == "uploaded"
        assert upload.json_body["video"]["thumbnail_path"], upload
        post_thumbnail_file = storage_dir / upload.json_body["video"]["thumbnail_path"].removeprefix(
            "/storage/videos/"
        ).replace("/", os.sep)
        assert post_thumbnail_file.is_file(), post_thumbnail_file

        other_upload = await asgi_bytes_request(
            app,
            "POST",
            f"/api/v1/videos/{post_video_id}/file",
            multipart_video_body(
                boundary=boundary,
                filename="serve-post.MOV",
                content_type="application/quicktime",
                content=post_video_bytes,
            ),
            {
                "authorization": f"Bearer {other_token}",
                "content-type": f"multipart/form-data; boundary={boundary}",
            },
        )
        assert other_upload.status == 404, other_upload

        publish = await asgi_request(
            app,
            "POST",
            f"/api/v1/posts/{post_id}/publish",
            headers=headers,
        )
        assert publish.status == 200, publish
        assert publish.json_body["post"]["status"] == "published"
        assert publish.json_body["post"]["published_at"] is not None
        assert publish.json_body["videos"][0]["thumbnail_path"], publish

        detail = await asgi_request(
            app,
            "GET",
            f"/api/v1/posts/{post_id}",
            headers=headers,
        )
        assert detail.status == 200, detail
        assert detail.json_body["post"]["social_post_id"] == post_id
        assert detail.json_body["videos"][0]["thumbnail_path"], detail

        other_detail = await asgi_request(
            app,
            "GET",
            f"/api/v1/posts/{post_id}",
            headers={"authorization": f"Bearer {other_token}"},
        )
        assert other_detail.status == 200, other_detail
        assert other_detail.json_body["post"]["social_post_id"] == post_id

        anonymous_detail = await asgi_request(
            app,
            "GET",
            f"/api/v1/posts/{post_id}",
        )
        assert anonymous_detail.status == 200, anonymous_detail
        assert anonymous_detail.json_body["viewer_state"] is None

        feed = await asgi_request(app, "GET", "/api/v1/posts/feed")
        assert feed.status == 200, feed
        assert feed.json_body["items"][0]["post"]["social_post_id"] == post_id
        assert feed.json_body["items"][0]["videos"][0]["thumbnail_path"], feed

        too_long = await asgi_request(
            app,
            "POST",
            "/api/v1/posts/upload-intents",
            {
                "content": "This should be rejected.",
                "videos": [
                    {
                        "original_filename": "too-long.mp4",
                        "mime_type": "video/mp4",
                        "file_size_bytes": 10,
                        "video_duration_ms": 600_001,
                    }
                ],
            },
            headers=headers,
        )
        assert too_long.status == 400, too_long
        assert too_long.json_body["detail"]["code"] == "POST_VIDEO_TOO_LONG"

        activity_video_bytes = b"activity source video for clip"
        activity_intent = await asgi_request(
            app,
            "POST",
            "/api/v1/tennis-activities/upload-intents",
            {
                "title": "Clip Source Activity",
                "activity_type": "other",
                "default_visibility": "private",
                "videos": [
                    {
                        "original_filename": "source.mp4",
                        "mime_type": "video/mp4",
                        "file_size_bytes": len(activity_video_bytes),
                    }
                ],
            },
            headers=headers,
        )
        assert activity_intent.status == 201, activity_intent
        activity_id = activity_intent.json_body["activity"]["tennis_activity_id"]
        activity_video_id = activity_intent.json_body["videos"][0]["video_id"]
        activity_boundary = "----tennis-post-clip-source-boundary"
        activity_upload = await asgi_bytes_request(
            app,
            "POST",
            f"/api/v1/videos/{activity_video_id}/file",
            multipart_video_body(
                boundary=activity_boundary,
                filename="source.mp4",
                content_type="video/mp4",
                content=activity_video_bytes,
            ),
            {
                **headers,
                "content-type": f"multipart/form-data; boundary={activity_boundary}",
            },
        )
        assert activity_upload.status == 200, activity_upload
        assert activity_upload.json_body["video"]["thumbnail_path"], activity_upload
        complete = await asgi_request(
            app,
            "POST",
            f"/api/v1/tennis-activities/{activity_id}/complete-upload",
            headers=headers,
        )
        assert complete.status == 200, complete

        clip_post = await asgi_request(
            app,
            "POST",
            "/api/v1/posts",
            {
                "content": "Clip from today's activity.",
                "status": "published",
                "visibility": "public",
                "media": [
                    {
                        "video_id": activity_video_id,
                        "clip_start_ms": 1_000,
                        "clip_end_ms": 8_000,
                    }
                ],
            },
            headers=headers,
        )
        assert clip_post.status == 201, clip_post
        assert clip_post.json_body["post"]["source_tennis_activity_id"] == activity_id
        assert clip_post.json_body["media"][0]["media_type"] == "video_clip"
        assert clip_post.json_body["videos"][0]["thumbnail_path"], clip_post

        print("Post API smoke test passed.")


if __name__ == "__main__":
    asyncio.run(main())
