"""Temporary-database authorization and association regression for user Activity deletion."""

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


async def main() -> None:
    with tempfile.TemporaryDirectory(prefix="activity-delete-") as directory:
        os.environ.pop("TENNIS_DATABASE_URL", None)
        os.environ.pop("TENNIS_POSTGRES_DSN", None)
        os.environ["TENNIS_DB_PATH"] = str(Path(directory) / "activity_delete.sqlite3")
        from backend.app.core.database import get_connection, initialize_sqlite_database, transaction
        from backend.app.main import app

        initialize_sqlite_database()
        owner = await asgi_request(app, "POST", "/api/v1/auth/phone-login", {"phone": "13960000001", "code": "000000"})
        other = await asgi_request(app, "POST", "/api/v1/auth/phone-login", {"phone": "13960000002", "code": "000000"})
        assert owner.status == 200 and other.status == 200
        owner_headers = {"authorization": f"Bearer {owner.json_body['access_token']}"}
        other_headers = {"authorization": f"Bearer {other.json_body['access_token']}"}
        created = await asgi_request(
            app,
            "POST",
            "/api/v1/tennis-activities",
            {"activity_type": "casual_hit", "default_visibility": "private", "title": "Delete contract"},
            headers=owner_headers,
        )
        assert created.status == 201, created
        activity_id = created.json_body["tennis_activity_id"]
        post_id = str(uuid.uuid4())
        with transaction() as connection:
            connection.execute(
                "INSERT INTO social_posts (social_post_id, author_user_id, source_tennis_activity_id, status, visibility) VALUES (?, ?, ?, 'draft', 'private');",
                (post_id, owner.json_body["user"]["user_id"], activity_id),
            )

        forbidden = await asgi_request(app, "DELETE", f"/api/v1/tennis-activities/{activity_id}", headers=other_headers)
        assert forbidden.status == 404 and forbidden.json_body["detail"]["code"] == "TENNIS_ACTIVITY_NOT_FOUND"
        removed = await asgi_request(app, "DELETE", f"/api/v1/tennis-activities/{activity_id}", headers=owner_headers)
        assert removed.status == 200 and removed.json_body["success"] is True
        assert removed.json_body["tennis_activity_id"] == activity_id and removed.json_body["deleted_at"]
        repeated = await asgi_request(app, "DELETE", f"/api/v1/tennis-activities/{activity_id}", headers=owner_headers)
        absent = await asgi_request(app, "DELETE", "/api/v1/tennis-activities/missing-activity", headers=owner_headers)
        assert repeated.status == 404 and absent.status == 404
        with get_connection() as connection:
            activity = connection.execute("SELECT deleted_at FROM tennis_activities WHERE tennis_activity_id = ?;", (activity_id,)).fetchone()
            post = connection.execute("SELECT source_tennis_activity_id FROM social_posts WHERE social_post_id = ?;", (post_id,)).fetchone()
        assert activity["deleted_at"] is not None and post["source_tennis_activity_id"] is None
    print("User Activity deletion API test passed.")


if __name__ == "__main__":
    asyncio.run(main())
