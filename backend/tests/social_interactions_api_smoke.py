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
    return datetime(2026, 8, 1, 12, 0, tzinfo=UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


async def main() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        os.environ["TENNIS_DB_PATH"] = str(Path(temp_dir) / "social_interactions.sqlite3")
        os.environ["TENNIS_VIDEO_STORAGE_DIR"] = str(Path(temp_dir) / "videos")

        from backend.app.core.database import initialize_database, transaction
        from backend.app.main import app

        initialize_database()

        alice_token, alice_id = await login_phone(app, "13810000001")
        bob_token, bob_id = await login_phone(app, "13810000002")
        carol_token, carol_id = await login_phone(app, "13810000003")
        dave_token, dave_id = await login_phone(app, "13810000004")
        alice_headers = {"authorization": f"Bearer {alice_token}"}
        bob_headers = {"authorization": f"Bearer {bob_token}"}
        carol_headers = {"authorization": f"Bearer {carol_token}"}
        dave_headers = {"authorization": f"Bearer {dave_token}"}

        post_id = str(uuid.uuid4())
        with transaction() as connection:
            connection.execute(
                """
                INSERT INTO social_posts (
                    social_post_id,
                    author_user_id,
                    content,
                    visibility,
                    status,
                    review_status,
                    published_at,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, 'Serve rhythm notes', 'public', 'published', 'approved', ?, ?, ?);
                """,
                (post_id, alice_id, now_iso(), now_iso(), now_iso()),
            )
            connection.execute(
                "INSERT INTO social_post_stats (social_post_id) VALUES (?);",
                (post_id,),
            )

        first_like = await asgi_request(
            app,
            "POST",
            f"/api/v1/posts/{post_id}/like",
            {"source": "home_feed"},
            headers=bob_headers,
        )
        assert first_like.status == 200, first_like
        assert first_like.json_body["stats"]["like_count"] == 1

        duplicate_like = await asgi_request(
            app,
            "POST",
            f"/api/v1/posts/{post_id}/like",
            {"source": "home_feed"},
            headers=bob_headers,
        )
        assert duplicate_like.status == 200, duplicate_like
        assert duplicate_like.json_body["stats"]["like_count"] == 1

        favorite = await asgi_request(
            app,
            "POST",
            f"/api/v1/posts/{post_id}/favorite",
            {"source": "post_detail"},
            headers=bob_headers,
        )
        assert favorite.status == 200, favorite
        assert favorite.json_body["stats"]["favorite_count"] == 1

        duplicate_favorite = await asgi_request(
            app,
            "POST",
            f"/api/v1/posts/{post_id}/favorite",
            {"source": "post_detail"},
            headers=bob_headers,
        )
        assert duplicate_favorite.status == 200, duplicate_favorite
        assert duplicate_favorite.json_body["stats"]["favorite_count"] == 1

        public_detail = await asgi_request(
            app,
            "GET",
            f"/api/v1/posts/public/{post_id}",
            headers=bob_headers,
        )
        assert public_detail.status == 200, public_detail
        assert public_detail.json_body["viewer_state"] == {
            "is_liked": True,
            "is_favorited": True,
        }

        unified_detail = await asgi_request(
            app,
            "GET",
            f"/api/v1/posts/{post_id}",
            headers=bob_headers,
        )
        assert unified_detail.status == 200, unified_detail
        assert unified_detail.json_body["viewer_state"] == {
            "is_liked": True,
            "is_favorited": True,
        }

        unfavorite = await asgi_request(
            app,
            "DELETE",
            f"/api/v1/posts/{post_id}/favorite",
            headers=bob_headers,
        )
        assert unfavorite.status == 200, unfavorite
        assert unfavorite.json_body["stats"]["favorite_count"] == 0

        comment = await asgi_request(
            app,
            "POST",
            f"/api/v1/posts/{post_id}/comments",
            {"content": "This serve shape looks cleaner.", "source": "post_detail"},
            headers=bob_headers,
        )
        assert comment.status == 201, comment
        comment_id = comment.json_body["comment"]["comment_id"]
        assert comment.json_body["stats"]["comment_count"] == 1

        reply = await asgi_request(
            app,
            "POST",
            f"/api/v1/posts/{post_id}/comments",
            {"content": "The toss finally stayed quiet.", "parent_comment_id": comment_id},
            headers=alice_headers,
        )
        assert reply.status == 201, reply
        reply_id = reply.json_body["comment"]["comment_id"]
        assert reply.json_body["stats"]["comment_count"] == 2

        comments = await asgi_request(app, "GET", f"/api/v1/posts/{post_id}/comments")
        assert comments.status == 200, comments
        assert comments.json_body["items"][0]["comment_id"] == comment_id
        assert comments.json_body["items"][0]["reply_count"] == 1

        replies = await asgi_request(
            app,
            "GET",
            f"/api/v1/posts/{post_id}/comments?parent_comment_id={comment_id}",
        )
        assert replies.status == 200, replies
        assert replies.json_body["items"][0]["comment_id"] == reply_id

        alice_notifications = await asgi_request(app, "GET", "/api/v1/notifications", headers=alice_headers)
        assert alice_notifications.status == 200, alice_notifications
        alice_event_types = {item["event"]["event_type"] for item in alice_notifications.json_body["items"]}
        assert {"post_like", "post_comment"}.issubset(alice_event_types)

        bob_notifications = await asgi_request(app, "GET", "/api/v1/notifications", headers=bob_headers)
        assert bob_notifications.status == 200, bob_notifications
        bob_event_types = {item["event"]["event_type"] for item in bob_notifications.json_body["items"]}
        assert "comment_reply" in bob_event_types

        delete_reply = await asgi_request(
            app,
            "DELETE",
            f"/api/v1/posts/{post_id}/comments/{reply_id}",
            headers=alice_headers,
        )
        assert delete_reply.status == 200, delete_reply
        assert delete_reply.json_body["stats"]["comment_count"] == 1

        report = await asgi_request(
            app,
            "POST",
            "/api/v1/reports",
            {
                "target_type": "social_post",
                "target_id": post_id,
                "reason_type": "spam",
                "reason_text": "Smoke test report.",
                "source": "post_detail",
            },
            headers=bob_headers,
        )
        assert report.status == 201, report
        duplicate_report = await asgi_request(
            app,
            "POST",
            "/api/v1/reports",
            {
                "target_type": "social_post",
                "target_id": post_id,
                "reason_type": "spam",
                "reason_text": "Duplicate smoke test report.",
            },
            headers=bob_headers,
        )
        assert duplicate_report.status == 201, duplicate_report
        assert duplicate_report.json_body["report"]["content_report_id"] == report.json_body["report"]["content_report_id"]

        follow_bob = await asgi_request(
            app,
            "POST",
            f"/api/v1/social/follows/{bob_id}",
            headers=alice_headers,
        )
        assert follow_bob.status == 201, follow_bob
        follow_alice = await asgi_request(
            app,
            "POST",
            f"/api/v1/social/follows/{alice_id}",
            headers=bob_headers,
        )
        assert follow_alice.status == 201, follow_alice
        assert follow_alice.json_body["relationship"]["is_friend"] is True

        direct = await asgi_request(
            app,
            "POST",
            "/api/v1/messages/direct-conversations",
            {"target_user_id": alice_id},
            headers=bob_headers,
        )
        assert direct.status == 201, direct
        conversation_id = direct.json_body["conversation"]["conversation_id"]

        share = await asgi_request(
            app,
            "POST",
            f"/api/v1/posts/{post_id}/share",
            {
                "share_target_type": "conversation",
                "conversation_id": conversation_id,
                "message_text": "Look at this serve note.",
                "channel": "chat",
            },
            headers=bob_headers,
        )
        assert share.status == 201, share
        assert share.json_body["stats"]["share_count"] == 1
        assert share.json_body["share"]["message_id"] is not None

        shared_messages = await asgi_request(
            app,
            "GET",
            f"/api/v1/messages/conversations/{conversation_id}/messages",
            headers=alice_headers,
        )
        assert shared_messages.status == 200, shared_messages
        assert shared_messages.json_body["items"][0]["message_type"] == "post_share"
        assert shared_messages.json_body["items"][0]["target_object_id"] == post_id

        direct_denied = await asgi_request(
            app,
            "POST",
            "/api/v1/messages/direct-conversations",
            {"target_user_id": carol_id},
            headers=dave_headers,
        )
        assert direct_denied.status == 403, direct_denied
        assert direct_denied.json_body["detail"]["code"] == "MESSAGE_REQUEST_REQUIRED"

        request = await asgi_request(
            app,
            "POST",
            "/api/v1/messages/requests",
            {
                "target_user_id": carol_id,
                "request_message": "Want to review a serve drill?",
                "source": "profile",
            },
            headers=dave_headers,
        )
        assert request.status == 201, request
        message_request_id = request.json_body["request"]["message_request_id"]

        inbox = await asgi_request(
            app,
            "GET",
            "/api/v1/messages/requests?box=inbox&status=pending",
            headers=carol_headers,
        )
        assert inbox.status == 200, inbox
        assert inbox.json_body["items"][0]["message_request_id"] == message_request_id

        accepted = await asgi_request(
            app,
            "POST",
            f"/api/v1/messages/requests/{message_request_id}/accept",
            headers=carol_headers,
        )
        assert accepted.status == 200, accepted
        assert accepted.json_body["request"]["status"] == "accepted"
        assert accepted.json_body["conversation"]["conversation_id"] is not None

        privacy = await asgi_request(app, "GET", "/api/v1/privacy/settings", headers=dave_headers)
        assert privacy.status == 200, privacy
        assert privacy.json_body["direct_message_policy"] == "friends"
        privacy_update = await asgi_request(
            app,
            "PATCH",
            "/api/v1/privacy/settings",
            {
                "direct_message_policy": "everyone",
                "allow_message_requests": False,
                "default_post_visibility": "private",
            },
            headers=dave_headers,
        )
        assert privacy_update.status == 200, privacy_update
        assert privacy_update.json_body["direct_message_policy"] == "everyone"
        assert privacy_update.json_body["allow_message_requests"] is False
        assert privacy_update.json_body["default_post_visibility"] == "private"

        block = await asgi_request(
            app,
            "POST",
            f"/api/v1/social/blocks/{bob_id}",
            {"reason": "smoke test block"},
            headers=alice_headers,
        )
        assert block.status == 201, block

        block_list = await asgi_request(app, "GET", "/api/v1/social/blocks", headers=alice_headers)
        assert block_list.status == 200, block_list
        assert block_list.json_body["items"][0]["user"]["user_id"] == bob_id

        blocked_follow = await asgi_request(
            app,
            "POST",
            f"/api/v1/social/follows/{alice_id}",
            headers=bob_headers,
        )
        assert blocked_follow.status == 403, blocked_follow
        assert blocked_follow.json_body["detail"]["code"] == "USER_INTERACTION_BLOCKED"

        blocked_message = await asgi_request(
            app,
            "POST",
            f"/api/v1/messages/conversations/{conversation_id}/messages",
            {"message_type": "text", "text_content": "Can you still see this?"},
            headers=bob_headers,
        )
        assert blocked_message.status == 403, blocked_message
        assert blocked_message.json_body["detail"]["code"] == "USER_INTERACTION_BLOCKED"

        unblock = await asgi_request(
            app,
            "DELETE",
            f"/api/v1/social/blocks/{bob_id}",
            headers=alice_headers,
        )
        assert unblock.status == 200, unblock

        print("Social interactions API smoke test passed.")


if __name__ == "__main__":
    asyncio.run(main())
