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
        os.environ["TENNIS_DB_PATH"] = str(Path(temp_dir) / "message_post_share.sqlite3")
        from backend.app.core.database import get_connection, initialize_database, transaction
        from backend.app.main import app

        initialize_database()
        alice_token, alice_id = await login_phone(app, "13961000001")
        bob_token, bob_id = await login_phone(app, "13961000002")
        carol_token, carol_id = await login_phone(app, "13961000003")
        alice_headers = {"authorization": f"Bearer {alice_token}"}
        bob_headers = {"authorization": f"Bearer {bob_token}"}
        carol_headers = {"authorization": f"Bearer {carol_token}"}

        post_id = str(uuid.uuid4())
        with transaction() as connection:
            connection.execute(
                """
                INSERT INTO social_posts (
                    social_post_id, author_user_id, title, content, visibility, status,
                    review_status, published_at, created_at, updated_at
                ) VALUES (?, ?, 'Card title', 'Card summary must stay bounded.', 'public', 'published', 'approved', ?, ?, ?);
                """,
                (post_id, alice_id, now_iso(), now_iso(), now_iso()),
            )
            connection.execute("INSERT INTO social_post_stats (social_post_id) VALUES (?);", (post_id,))

        for headers, target_id in ((bob_headers, carol_id), (carol_headers, bob_id)):
            followed = await asgi_request(app, "POST", f"/api/v1/social/follows/{target_id}", headers=headers)
            assert followed.status == 201, followed
        direct = await asgi_request(app, "POST", "/api/v1/messages/direct-conversations", {"target_user_id": carol_id}, headers=bob_headers)
        assert direct.status == 201, direct
        conversation_id = direct.json_body["conversation"]["conversation_id"]

        body = {
            "share_target_type": "conversation",
            "conversation_id": conversation_id,
            "message_text": "Card title",
            "client_message_id": "post-share-api-1",
            "payload": {"internal_only": "must_not_reach_chat"},
        }
        first = await asgi_request(app, "POST", f"/api/v1/posts/{post_id}/share", body, headers=bob_headers)
        retry = await asgi_request(app, "POST", f"/api/v1/posts/{post_id}/share", body, headers=bob_headers)
        assert first.status == retry.status == 201
        assert first.json_body["share"]["post_share_id"] == retry.json_body["share"]["post_share_id"]
        assert first.json_body["share"]["message_id"] == retry.json_body["share"]["message_id"]
        assert retry.json_body["stats"]["share_count"] == 1
        other_post_id = str(uuid.uuid4())
        with transaction() as connection:
            connection.execute(
                """INSERT INTO social_posts (social_post_id, author_user_id, title, visibility, status, review_status, published_at, created_at, updated_at)
                VALUES (?, ?, 'Other card', 'public', 'published', 'approved', ?, ?, ?);""",
                (other_post_id, alice_id, now_iso(), now_iso(), now_iso()),
            )
            connection.execute("INSERT INTO social_post_stats (social_post_id) VALUES (?);", (other_post_id,))
        conflicting_share = await asgi_request(app, "POST", f"/api/v1/posts/{other_post_id}/share", body, headers=bob_headers)
        assert conflicting_share.status == 409
        assert conflicting_share.json_body["detail"]["code"] == "CLIENT_MESSAGE_ID_CONFLICT"

        history = await asgi_request(app, "GET", f"/api/v1/messages/conversations/{conversation_id}/messages", headers=carol_headers)
        assert history.status == 200, history
        message = history.json_body["items"][0]
        card = message["share_card"]
        assert message["message_type"] == "post_share"
        assert message["payload_json"] is None
        assert message["business_object_card"]["kind"] == "business_object"
        assert message["business_object_card"]["state"] == "available"
        assert card["state"] == "available"
        assert card["post_id"] == post_id
        assert card["title"] == "Card title" and card["summary"] == "Card summary must stay bounded."
        assert card["author"]["user_id"] == alice_id
        assert set(card["author"]) == {"user_id", "nickname", "avatar_path"}
        assert set(card) == {"state", "post_id", "reason", "title", "summary", "cover_url", "author", "visibility"}

        reconciled = await asgi_request(
            app, "POST", f"/api/v1/messages/conversations/{conversation_id}/messages/reconcile",
            {"message_ids": [message["message_id"]]}, headers=carol_headers,
        )
        searched = await asgi_request(
            app, "GET", f"/api/v1/messages/conversations/{conversation_id}/messages/search?q=Card%20title", headers=carol_headers,
        )
        assert reconciled.status == searched.status == 200
        assert reconciled.json_body["items"][0]["share_card"] == card
        assert searched.json_body["items"][0]["share_card"] == card
        with get_connection() as connection:
            assert connection.execute("SELECT COUNT(*) FROM post_shares WHERE client_message_id = ?;", ("post-share-api-1",)).fetchone()[0] == 1
            assert connection.execute("SELECT COUNT(*) FROM chat_messages WHERE client_message_id = ?;", ("post-share-api-1",)).fetchone()[0] == 1
            assert connection.execute(
                "SELECT unread_count FROM chat_conversation_members WHERE conversation_id = ? AND user_id = ?;", (conversation_id, carol_id)
            ).fetchone()[0] == 1

        unauthorized = await asgi_request(app, "GET", f"/api/v1/messages/conversations/{conversation_id}/messages", headers=alice_headers)
        assert unauthorized.status == 403
        print("Message post share API test passed.")


if __name__ == "__main__":
    asyncio.run(main())
