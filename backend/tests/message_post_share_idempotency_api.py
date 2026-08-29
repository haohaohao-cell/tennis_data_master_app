from __future__ import annotations

import asyncio
from datetime import UTC, datetime
import os
from pathlib import Path
import sys
import tempfile
import uuid
from unittest.mock import patch


ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT_DIR))

from backend.tests.activity_detail_api_smoke import login_phone
from backend.tests.auth_api_smoke import asgi_request


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


async def follow(app, headers: dict[str, str], target_id: str) -> None:
    response = await asgi_request(app, "POST", f"/api/v1/social/follows/{target_id}", headers=headers)
    assert response.status == 201, response


async def create_direct(app, headers: dict[str, str], target_id: str) -> str:
    response = await asgi_request(
        app,
        "POST",
        "/api/v1/messages/direct-conversations",
        {"target_user_id": target_id},
        headers=headers,
    )
    assert response.status == 201, response
    return response.json_body["conversation"]["conversation_id"]


def post_row(post_id: str, author_id: str, title: str) -> tuple[object, ...]:
    timestamp = now_iso()
    return (post_id, author_id, title, timestamp, timestamp, timestamp)


async def main() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        os.environ["TENNIS_DB_PATH"] = str(Path(temp_dir) / "message_post_share_idempotency.sqlite3")
        from backend.app.core.database import get_connection, initialize_database, transaction
        from backend.app.main import app
        from backend.app.messages import service as message_service
        from backend.app.posts import interaction_service
        from backend.app.posts.schemas import PostShareCreate

        initialize_database()
        users = [await login_phone(app, phone) for phone in ("13971000001", "13971000002", "13971000003", "13971000004")]
        (alice_token, alice_id), (bob_token, bob_id), (carol_token, carol_id), (dave_token, dave_id) = users
        alice_headers = {"authorization": f"Bearer {alice_token}"}
        bob_headers = {"authorization": f"Bearer {bob_token}"}
        carol_headers = {"authorization": f"Bearer {carol_token}"}
        dave_headers = {"authorization": f"Bearer {dave_token}"}

        for headers, target_id in (
            (bob_headers, carol_id), (carol_headers, bob_id),
            (bob_headers, dave_id), (dave_headers, bob_id),
            (alice_headers, dave_id), (dave_headers, alice_id),
        ):
            await follow(app, headers, target_id)

        post_one = str(uuid.uuid4())
        post_two = str(uuid.uuid4())
        with transaction() as connection:
            connection.executemany(
                """
                INSERT INTO social_posts (
                    social_post_id, author_user_id, title, visibility, status,
                    review_status, published_at, created_at, updated_at
                ) VALUES (?, ?, ?, 'public', 'published', 'approved', ?, ?, ?);
                """,
                [post_row(post_one, alice_id, "One"), post_row(post_two, alice_id, "Two")],
            )
            connection.executemany(
                "INSERT INTO social_post_stats (social_post_id) VALUES (?);",
                [(post_one,), (post_two,)],
            )

        conversation_one = await create_direct(app, bob_headers, carol_id)
        conversation_two = await create_direct(app, bob_headers, dave_id)

        def share_body(*, key: str | None, post_id: str = post_one, conversation_id: str | None = conversation_one,
                       target_type: str = "conversation", channel: str | None = "chat",
                       text: str | None = "hello", payload: dict | None = None) -> dict:
            body = {
                "share_target_type": target_type,
                "message_text": text,
                "channel": channel,
                "payload": payload,
            }
            if key is not None:
                body["client_message_id"] = key
            if conversation_id is not None:
                body["conversation_id"] = conversation_id
            return body

        async def share(headers: dict[str, str], post_id: str = post_one, **kwargs):
            return await asgi_request(app, "POST", f"/api/v1/posts/{post_id}/share", share_body(**kwargs), headers=headers)

        exact_body = share_body(key="exact-1", payload={"a": 1, "b": {"x": True}})
        first = await asgi_request(app, "POST", f"/api/v1/posts/{post_one}/share", exact_body, headers=bob_headers)
        retry = await asgi_request(app, "POST", f"/api/v1/posts/{post_one}/share", exact_body, headers=bob_headers)
        assert first.status == retry.status == 201
        assert first.json_body["share"]["post_share_id"] == retry.json_body["share"]["post_share_id"]
        assert first.json_body["share"]["message_id"] == retry.json_body["share"]["message_id"]
        with get_connection() as connection:
            assert connection.execute("SELECT COUNT(*) FROM post_shares WHERE client_message_id = 'exact-1';").fetchone()[0] == 1
            assert connection.execute("SELECT COUNT(*) FROM chat_messages WHERE client_message_id = 'exact-1';").fetchone()[0] == 1
            assert connection.execute("SELECT share_count FROM social_post_stats WHERE social_post_id = ?;", (post_one,)).fetchone()[0] == 1
            recipient_unread = connection.execute(
                "SELECT unread_count FROM chat_conversation_members WHERE conversation_id = ? AND user_id = ?;",
                (conversation_one, carol_id),
            ).fetchone()[0]
            assert recipient_unread == 1

        before_counts = None
        with get_connection() as connection:
            before_counts = (
                connection.execute("SELECT COUNT(*) FROM post_shares;").fetchone()[0],
                connection.execute("SELECT COUNT(*) FROM chat_messages;").fetchone()[0],
                connection.execute("SELECT share_count FROM social_post_stats WHERE social_post_id = ?;", (post_one,)).fetchone()[0],
                connection.execute("SELECT share_count FROM social_post_stats WHERE social_post_id = ?;", (post_two,)).fetchone()[0],
                connection.execute("SELECT unread_count FROM chat_conversation_members WHERE conversation_id = ? AND user_id = ?;", (conversation_one, carol_id)).fetchone()[0],
                connection.execute("SELECT unread_count FROM chat_conversation_members WHERE conversation_id = ? AND user_id = ?;", (conversation_two, dave_id)).fetchone()[0],
            )

        conflict_requests = (
            ("different_post", dict(post_id=post_two)),
            ("different_conversation", dict(conversation_id=conversation_two)),
            ("different_target", dict(target_type="copy_link", conversation_id=None)),
            ("different_channel", dict(channel="share_sheet")),
            ("different_text", dict(text="different")),
            ("different_payload", dict(payload={"a": 2})),
        )
        for label, kwargs in conflict_requests:
            response = await share(bob_headers, key="exact-1", **kwargs)
            assert response.status == 409, (label, response)
            assert response.json_body["detail"]["code"] == "CLIENT_MESSAGE_ID_CONFLICT", (label, response)
            serialized = str(response.json_body)
            assert post_one not in serialized and conversation_one not in serialized and "hello" not in serialized
            with get_connection() as connection:
                after = (
                    connection.execute("SELECT COUNT(*) FROM post_shares;").fetchone()[0],
                    connection.execute("SELECT COUNT(*) FROM chat_messages;").fetchone()[0],
                    connection.execute("SELECT share_count FROM social_post_stats WHERE social_post_id = ?;", (post_one,)).fetchone()[0],
                    connection.execute("SELECT share_count FROM social_post_stats WHERE social_post_id = ?;", (post_two,)).fetchone()[0],
                    connection.execute("SELECT unread_count FROM chat_conversation_members WHERE conversation_id = ? AND user_id = ?;", (conversation_one, carol_id)).fetchone()[0],
                    connection.execute("SELECT unread_count FROM chat_conversation_members WHERE conversation_id = ? AND user_id = ?;", (conversation_two, dave_id)).fetchone()[0],
                )
            assert after == before_counts, (label, before_counts, after)

        # A normal text message owns its key and cannot be shadowed by a Post share.
        text_key = "ordinary-message-key"
        normal = await asgi_request(
            app, "POST", f"/api/v1/messages/conversations/{conversation_two}/messages",
            {"message_type": "text", "text_content": "ordinary", "client_message_id": text_key}, headers=bob_headers,
        )
        assert normal.status == 201, normal
        text_conflict = await share(bob_headers, key=text_key, conversation_id=conversation_two)
        assert text_conflict.status == 409 and text_conflict.json_body["detail"]["code"] == "CLIENT_MESSAGE_ID_CONFLICT"

        # Different users have independent idempotency scopes.
        alice_conversation = await create_direct(app, alice_headers, dave_id)
        other_user = await share(alice_headers, key="exact-1", conversation_id=alice_conversation)
        assert other_user.status == 201, other_user
        different_key = await share(bob_headers, key="exact-2")
        assert different_key.status == 201, different_key

        missing_key = await share(bob_headers, key=None)
        assert missing_key.status == 422, missing_key
        empty_key = await share(bob_headers, key="")
        assert empty_key.status == 422, empty_key
        copy_link = await share(bob_headers, key=None, target_type="copy_link", conversation_id=None)
        assert copy_link.status == 201 and copy_link.json_body["share"]["message_id"] is None
        copy_key = "copy-link-key"
        copy_first = await share(
            bob_headers,
            key=copy_key,
            target_type="copy_link",
            conversation_id=None,
            text="copy this",
        )
        copy_retry = await share(
            bob_headers,
            key=copy_key,
            target_type="copy_link",
            conversation_id=None,
            text="copy this",
        )
        assert copy_first.status == copy_retry.status == 201
        assert copy_first.json_body["share"]["post_share_id"] == copy_retry.json_body["share"]["post_share_id"]
        copy_conflict = await share(
            bob_headers,
            key=copy_key,
            target_type="copy_link",
            conversation_id=None,
            text="changed copy text",
        )
        assert copy_conflict.status == 409
        assert copy_conflict.json_body["detail"]["code"] == "CLIENT_MESSAGE_ID_CONFLICT"

        # Concurrent identical requests serialize on the database transaction and commit once.
        concurrent_key = "concurrent-1"
        responses = await asyncio.gather(*(share(bob_headers, key=concurrent_key) for _ in range(6)))
        assert all(response.status == 201 for response in responses), responses
        assert len({response.json_body["share"]["post_share_id"] for response in responses}) == 1
        assert len({response.json_body["share"]["message_id"] for response in responses}) == 1
        with get_connection() as connection:
            assert connection.execute("SELECT COUNT(*) FROM post_shares WHERE client_message_id = ?;", (concurrent_key,)).fetchone()[0] == 1
            assert connection.execute("SELECT COUNT(*) FROM chat_messages WHERE client_message_id = ?;", (concurrent_key,)).fetchone()[0] == 1

        # Failures inside either side of the transaction leave no orphan rows.
        rollback_key = "rollback-message"
        with patch.object(message_service, "send_message_in_transaction", side_effect=RuntimeError("test message failure")):
            try:
                interaction_service.share_post(
                    bob_id,
                    post_one,
                    PostShareCreate(**share_body(key=rollback_key)),
                )
            except RuntimeError:
                pass
            else:
                raise AssertionError("message failure should propagate to the caller")
        with get_connection() as connection:
            assert connection.execute("SELECT COUNT(*) FROM post_shares WHERE client_message_id = ?;", (rollback_key,)).fetchone()[0] == 0
            assert connection.execute("SELECT COUNT(*) FROM chat_messages WHERE client_message_id = ?;", (rollback_key,)).fetchone()[0] == 0

        count_failure_key = "rollback-count"
        with patch.object(interaction_service, "_update_stat_count", side_effect=RuntimeError("test count failure")):
            try:
                interaction_service.share_post(
                    bob_id,
                    post_one,
                    PostShareCreate(**share_body(key=count_failure_key)),
                )
            except RuntimeError:
                pass
            else:
                raise AssertionError("share count failure should propagate to the caller")
        with get_connection() as connection:
            assert connection.execute("SELECT COUNT(*) FROM post_shares WHERE client_message_id = ?;", (count_failure_key,)).fetchone()[0] == 0
            assert connection.execute("SELECT COUNT(*) FROM chat_messages WHERE client_message_id = ?;", (count_failure_key,)).fetchone()[0] == 0

        print("Message Post share idempotency API test passed.")


if __name__ == "__main__":
    asyncio.run(main())
