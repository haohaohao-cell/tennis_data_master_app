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
        avatar_storage_dir = Path(temp_dir) / "avatars"
        os.environ["TENNIS_AVATAR_STORAGE_DIR"] = str(avatar_storage_dir)
        os.environ["TENNIS_DB_PATH"] = str(Path(temp_dir) / "avatar_api_smoke.sqlite3")
        os.environ["TENNIS_VIDEO_STORAGE_DIR"] = str(Path(temp_dir) / "videos")

        from backend.app.core.database import initialize_database
        from backend.app.main import app

        initialize_database()

        login = await asgi_request(
            app,
            "POST",
            "/api/v1/auth/phone-login",
            {"phone": "13500000001", "code": "000000"},
        )
        assert login.status == 200, login
        headers = {"authorization": f"Bearer {login.json_body['access_token']}"}

        avatar_bytes = b"fake png avatar bytes"
        boundary = "----tennis-avatar-smoke-boundary"
        upload = await asgi_bytes_request(
            app,
            "POST",
            "/api/v1/users/me/avatar",
            multipart_video_body(
                boundary=boundary,
                filename="avatar.png",
                content_type="image/png",
                content=avatar_bytes,
            ),
            {
                **headers,
                "content-type": f"multipart/form-data; boundary={boundary}",
            },
        )
        assert upload.status == 200, upload
        first_avatar_path = upload.json_body["user"]["avatar_path"]
        assert first_avatar_path.startswith("/storage/avatars/"), upload
        first_avatar_file = avatar_storage_dir / first_avatar_path.removeprefix(
            "/storage/avatars/"
        ).replace("/", os.sep)
        assert first_avatar_file.read_bytes() == avatar_bytes

        replacement_bytes = b"fake jpg avatar bytes"
        replacement_boundary = "----tennis-avatar-replacement-boundary"
        replacement = await asgi_bytes_request(
            app,
            "POST",
            "/api/v1/users/me/avatar",
            multipart_video_body(
                boundary=replacement_boundary,
                filename="avatar.jpg",
                content_type="image/jpeg",
                content=replacement_bytes,
            ),
            {
                **headers,
                "content-type": f"multipart/form-data; boundary={replacement_boundary}",
            },
        )
        assert replacement.status == 200, replacement
        replacement_path = replacement.json_body["user"]["avatar_path"]
        assert replacement_path != first_avatar_path
        replacement_file = avatar_storage_dir / replacement_path.removeprefix(
            "/storage/avatars/"
        ).replace("/", os.sep)
        assert replacement_file.read_bytes() == replacement_bytes
        assert not first_avatar_file.exists(), first_avatar_file

        invalid_boundary = "----tennis-avatar-invalid-boundary"
        invalid = await asgi_bytes_request(
            app,
            "POST",
            "/api/v1/users/me/avatar",
            multipart_video_body(
                boundary=invalid_boundary,
                filename="avatar.txt",
                content_type="text/plain",
                content=b"not an image",
            ),
            {
                **headers,
                "content-type": f"multipart/form-data; boundary={invalid_boundary}",
            },
        )
        assert invalid.status == 415, invalid
        assert invalid.json_body["detail"]["code"] == "UNSUPPORTED_AVATAR_TYPE"

        print("Avatar API smoke test passed.")


if __name__ == "__main__":
    asyncio.run(main())
