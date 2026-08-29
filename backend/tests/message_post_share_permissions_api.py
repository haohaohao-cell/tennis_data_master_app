from __future__ import annotations

import asyncio
from datetime import UTC, datetime
import os
from pathlib import Path
import sys
import tempfile
import uuid


ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT_DIR))

from backend.tests.activity_detail_api_smoke import login_phone
from backend.tests.auth_api_smoke import asgi_request


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


async def main() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        os.environ["TENNIS_DB_PATH"] = str(Path(temp_dir) / "message_post_share_permissions.sqlite3")
        from backend.app.core.database import initialize_database, transaction
        from backend.app.main import app

        initialize_database()
        users = [await login_phone(app, phone) for phone in ("13962000001", "13962000002", "13962000003")]
        (alice_token, alice_id), (bob_token, bob_id), (carol_token, carol_id) = users
        alice_headers = {"authorization": f"Bearer {alice_token}"}
        bob_headers = {"authorization": f"Bearer {bob_token}"}
        carol_headers = {"authorization": f"Bearer {carol_token}"}
        for headers, target_id in ((bob_headers, carol_id), (carol_headers, bob_id), (bob_headers, alice_id), (alice_headers, bob_id)):
            response = await asgi_request(app, "POST", f"/api/v1/social/follows/{target_id}", headers=headers)
            assert response.status == 201, response
        direct = await asgi_request(app, "POST", "/api/v1/messages/direct-conversations", {"target_user_id": carol_id}, headers=bob_headers)
        assert direct.status == 201
        conversation_id = direct.json_body["conversation"]["conversation_id"]

        def add_post(visibility: str) -> str:
            post_id = str(uuid.uuid4())
            with transaction() as connection:
                connection.execute(
                    """INSERT INTO social_posts (social_post_id, author_user_id, title, content, visibility, status, review_status, published_at, created_at, updated_at)
                    VALUES (?, ?, ?, 'private card content', ?, 'published', 'approved', ?, ?, ?);""",
                    (post_id, alice_id, f"{visibility} title", visibility, now_iso(), now_iso(), now_iso()),
                )
                connection.execute("INSERT INTO social_post_stats (social_post_id) VALUES (?);", (post_id,))
            return post_id

        friends_post = add_post("friends")
        shared = await asgi_request(
            app, "POST", f"/api/v1/posts/{friends_post}/share",
            {"share_target_type": "conversation", "conversation_id": conversation_id, "message_text": "friends", "client_message_id": "post-share-permissions-1"},
            headers=bob_headers,
        )
        assert shared.status == 201, shared
        bob_history = await asgi_request(app, "GET", f"/api/v1/messages/conversations/{conversation_id}/messages", headers=bob_headers)
        carol_history = await asgi_request(app, "GET", f"/api/v1/messages/conversations/{conversation_id}/messages", headers=carol_headers)
        assert bob_history.json_body["items"][0]["share_card"]["state"] == "available"
        unavailable = carol_history.json_body["items"][0]["share_card"]
        assert unavailable == {"state": "unavailable", "post_id": friends_post, "reason": "not_found_or_no_access", "title": None, "summary": None, "cover_url": None, "author": None, "visibility": None}

        with transaction() as connection:
            connection.execute("UPDATE social_posts SET visibility = 'private' WHERE social_post_id = ?;", (friends_post,))
        after_private = await asgi_request(app, "GET", f"/api/v1/messages/conversations/{conversation_id}/messages", headers=bob_headers)
        assert after_private.json_body["items"][0]["share_card"]["state"] == "unavailable"
        with transaction() as connection:
            connection.execute("UPDATE social_posts SET status = 'deleted', deleted_at = ? WHERE social_post_id = ?;", (now_iso(), friends_post))
        after_delete = await asgi_request(app, "GET", f"/api/v1/messages/conversations/{conversation_id}/messages", headers=carol_headers)
        assert after_delete.json_body["items"][0]["share_card"]["state"] == "unavailable"

        private_post = add_post("private")
        forbidden = await asgi_request(
            app, "POST", f"/api/v1/posts/{private_post}/share",
            {"share_target_type": "conversation", "conversation_id": conversation_id, "message_text": "private", "client_message_id": "post-share-private"},
            headers=bob_headers,
        )
        assert forbidden.status == 404 and forbidden.json_body["detail"]["code"] == "POST_NOT_FOUND"
        print("Message post share permissions API test passed.")


if __name__ == "__main__":
    asyncio.run(main())
