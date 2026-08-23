from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT_DIR))

from backend.tests.auth_api_smoke import asgi_request


async def main() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        os.environ["TENNIS_DB_PATH"] = os.path.join(temp_dir, "admin_api_smoke.sqlite3")

        from backend.app.admin.service import ensure_test_admin_account
        from backend.app.core.database import initialize_database
        from backend.app.main import app

        initialize_database()

        normal_login = await asgi_request(
            app,
            "POST",
            "/api/v1/auth/phone-login",
            {"phone": "13900000001", "code": "000000"},
        )
        assert normal_login.status == 200, normal_login
        normal_token = normal_login.json_body["access_token"]

        forbidden = await asgi_request(
            app,
            "GET",
            "/api/v1/admin/users",
            headers={"authorization": f"Bearer {normal_token}"},
        )
        assert forbidden.status == 403, forbidden
        assert forbidden.json_body["detail"]["code"] == "ADMIN_PERMISSION_REQUIRED"

        admin_user_id = ensure_test_admin_account("smoke-admin", "0000")

        invalid_admin_login = await asgi_request(
            app,
            "POST",
            "/api/v1/admin/auth/login",
            {"username": "smoke-admin", "password": "wrong"},
        )
        assert invalid_admin_login.status == 401, invalid_admin_login
        assert invalid_admin_login.json_body["detail"]["code"] == "INVALID_ADMIN_CREDENTIALS"

        admin_login = await asgi_request(
            app,
            "POST",
            "/api/v1/admin/auth/login",
            {
                "username": "smoke-admin",
                "password": "0000",
                "device": {"device_name": "Admin smoke", "platform": "test"},
            },
        )
        assert admin_login.status == 200, admin_login
        assert admin_login.json_body["user"]["user_id"] == admin_user_id
        assert admin_login.json_body["admin_role"] == "owner"
        admin_token = admin_login.json_body["access_token"]

        admin_headers = {"authorization": f"Bearer {admin_token}"}
        created_user = await asgi_request(
            app,
            "POST",
            "/api/v1/admin/users",
            {
                "nickname": "Managed Player",
                "phone": "13900000002",
                "playing_hand": "left",
            },
            headers=admin_headers,
        )
        assert created_user.status == 201, created_user
        managed_user_id = created_user.json_body["user_id"]

        users = await asgi_request(app, "GET", "/api/v1/admin/users", headers=admin_headers)
        assert users.status == 200, users
        assert users.json_body["total"] >= 2

        updated_user = await asgi_request(
            app,
            "PATCH",
            f"/api/v1/admin/users/{managed_user_id}",
            {"status": "disabled"},
            headers=admin_headers,
        )
        assert updated_user.status == 200, updated_user
        assert updated_user.json_body["status"] == "disabled"

        activity = await asgi_request(
            app,
            "POST",
            "/api/v1/admin/tennis-activities",
            {
                "owner_user_id": managed_user_id,
                "title": "Admin Created Activity",
                "activity_type": "serve_training",
                "default_visibility": "private",
            },
            headers=admin_headers,
        )
        assert activity.status == 201, activity
        activity_id = activity.json_body["tennis_activity_id"]

        updated_activity = await asgi_request(
            app,
            "PATCH",
            f"/api/v1/admin/tennis-activities/{activity_id}",
            {"default_visibility": "public"},
            headers=admin_headers,
        )
        assert updated_activity.status == 200, updated_activity
        assert updated_activity.json_body["default_visibility"] == "public"

        video = await asgi_request(
            app,
            "POST",
            "/api/v1/admin/videos",
            {
                "tennis_activity_id": activity_id,
                "owner_user_id": managed_user_id,
                "uploader_user_id": admin_user_id,
                "filename": "admin-created-video.mp4",
                "video_path": "/storage/videos/admin-created-video.mp4",
                "visibility": "inherit",
            },
            headers=admin_headers,
        )
        assert video.status == 201, video
        video_id = video.json_body["video_id"]

        updated_video = await asgi_request(
            app,
            "PATCH",
            f"/api/v1/admin/videos/{video_id}",
            {"analysis_status": "queued"},
            headers=admin_headers,
        )
        assert updated_video.status == 200, updated_video
        assert updated_video.json_body["analysis_status"] == "queued"

        post = await asgi_request(
            app,
            "POST",
            "/api/v1/admin/posts",
            {
                "author_user_id": managed_user_id,
                "source_tennis_activity_id": activity_id,
                "title": "Admin Created Post",
                "content": "Created from admin smoke test.",
                "visibility": "public",
            },
            headers=admin_headers,
        )
        assert post.status == 201, post
        post_id = post.json_body["social_post_id"]

        updated_post = await asgi_request(
            app,
            "PATCH",
            f"/api/v1/admin/posts/{post_id}",
            {"status": "published"},
            headers=admin_headers,
        )
        assert updated_post.status == 200, updated_post
        assert updated_post.json_body["status"] == "published"
        assert updated_post.json_body["published_at"] is not None

        deleted_post = await asgi_request(
            app,
            "DELETE",
            f"/api/v1/admin/posts/{post_id}",
            headers=admin_headers,
        )
        assert deleted_post.status == 200, deleted_post
        assert deleted_post.json_body["success"] is True

        deleted_video = await asgi_request(
            app,
            "DELETE",
            f"/api/v1/admin/videos/{video_id}",
            headers=admin_headers,
        )
        assert deleted_video.status == 200, deleted_video

        deleted_activity = await asgi_request(
            app,
            "DELETE",
            f"/api/v1/admin/tennis-activities/{activity_id}",
            headers=admin_headers,
        )
        assert deleted_activity.status == 200, deleted_activity

        deleted_user = await asgi_request(
            app,
            "DELETE",
            f"/api/v1/admin/users/{managed_user_id}",
            headers=admin_headers,
        )
        assert deleted_user.status == 200, deleted_user

        print("Admin API smoke test passed.")


if __name__ == "__main__":
    asyncio.run(main())
