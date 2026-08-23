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


async def main() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        os.environ["TENNIS_DB_PATH"] = str(Path(temp_dir) / "message_core_api.sqlite3")

        from backend.app.core.database import get_connection, initialize_database
        from backend.app.main import app

        initialize_database()
        users = [await login_phone(app, phone) for phone in ("13940000001", "13940000002", "13940000003")]
        (alice_token, alice_id), (bob_token, bob_id), (carol_token, carol_id) = users
        alice_headers = {"authorization": f"Bearer {alice_token}"}
        bob_headers = {"authorization": f"Bearer {bob_token}"}
        carol_headers = {"authorization": f"Bearer {carol_token}"}

        for target_id, headers in ((bob_id, alice_headers), (alice_id, bob_headers)):
            response = await asgi_request(
                app,
                "POST",
                f"/api/v1/social/follows/{target_id}",
                {"source": "message-core-api"},
                headers=headers,
            )
            assert response.status == 201, response

        direct = await asgi_request(
            app,
            "POST",
            "/api/v1/messages/direct-conversations",
            {"target_user_id": bob_id},
            headers=alice_headers,
        )
        assert direct.status == 201, direct
        alice_bob_id = direct.json_body["conversation"]["conversation_id"]

        for method, path, body in (
            ("GET", f"/api/v1/messages/conversations/{alice_bob_id}/messages", None),
            (
                "POST",
                f"/api/v1/messages/conversations/{alice_bob_id}/messages",
                {"message_type": "text", "text_content": "unauthorized"},
            ),
            ("POST", f"/api/v1/messages/conversations/{alice_bob_id}/read", None),
        ):
            response = await asgi_request(app, method, path, body, headers=carol_headers)
            assert response.status in {403, 404}, response

        request = await asgi_request(
            app,
            "POST",
            "/api/v1/messages/requests",
            {"target_user_id": carol_id, "request_message": "Can we chat?"},
            headers=alice_headers,
        )
        assert request.status == 201, request
        request_id = request.json_body["request"]["message_request_id"]
        duplicate_request = await asgi_request(
            app,
            "POST",
            "/api/v1/messages/requests",
            {"target_user_id": carol_id, "request_message": "Can we chat?"},
            headers=alice_headers,
        )
        assert duplicate_request.status == 201, duplicate_request
        assert duplicate_request.json_body["request"]["message_request_id"] == request_id

        unauthorized_accept = await asgi_request(
            app,
            "POST",
            f"/api/v1/messages/requests/{request_id}/accept",
            headers=bob_headers,
        )
        assert unauthorized_accept.status == 404, unauthorized_accept
        accepted = await asgi_request(
            app,
            "POST",
            f"/api/v1/messages/requests/{request_id}/accept",
            headers=carol_headers,
        )
        assert accepted.status == 200, accepted
        assert accepted.json_body["request"]["status"] == "accepted"
        alice_carol_id = accepted.json_body["conversation"]["conversation_id"]

        decline_request = await asgi_request(
            app,
            "POST",
            "/api/v1/messages/requests",
            {"target_user_id": bob_id, "request_message": "Request from Carol"},
            headers=carol_headers,
        )
        assert decline_request.status == 201, decline_request
        decline_request_id = decline_request.json_body["request"]["message_request_id"]
        declined = await asgi_request(
            app,
            "POST",
            f"/api/v1/messages/requests/{decline_request_id}/decline",
            headers=bob_headers,
        )
        assert declined.status == 200 and declined.json_body["request"]["status"] == "declined", declined
        repeated_decline = await asgi_request(
            app,
            "POST",
            f"/api/v1/messages/requests/{decline_request_id}/decline",
            headers=bob_headers,
        )
        assert repeated_decline.status == 404, repeated_decline

        for index in range(2):
            response = await asgi_request(
                app,
                "POST",
                f"/api/v1/messages/conversations/{alice_bob_id}/messages",
                {"message_type": "text", "text_content": f"bob-{index}", "client_message_id": f"bob-{index}"},
                headers=bob_headers,
            )
            assert response.status == 201, response
        for index in range(3):
            response = await asgi_request(
                app,
                "POST",
                f"/api/v1/messages/conversations/{alice_carol_id}/messages",
                {"message_type": "text", "text_content": f"carol-{index}", "client_message_id": f"carol-{index}"},
                headers=carol_headers,
            )
            assert response.status == 201, response

        unread = await asgi_request(app, "GET", "/api/v1/messages/unread-counts", headers=alice_headers)
        assert unread.json_body["unread_direct_message_count"] == 5, unread
        marked = await asgi_request(
            app,
            "POST",
            f"/api/v1/messages/conversations/{alice_bob_id}/read",
            headers=alice_headers,
        )
        assert marked.status == 200 and marked.json_body["unread_count"] == 0, marked
        repeated_mark = await asgi_request(
            app,
            "POST",
            f"/api/v1/messages/conversations/{alice_bob_id}/read",
            headers=alice_headers,
        )
        assert repeated_mark.status == 200, repeated_mark
        unread_after = await asgi_request(app, "GET", "/api/v1/messages/unread-counts", headers=alice_headers)
        assert unread_after.json_body["unread_direct_message_count"] == 3, unread_after

        first_message_id = None
        for index in range(100):
            response = await asgi_request(
                app,
                "POST",
                f"/api/v1/messages/conversations/{alice_bob_id}/messages",
                {
                    "message_type": "text",
                    "text_content": f"history-{index:03d}",
                    "client_message_id": f"history-{index:03d}",
                },
                headers=alice_headers,
            )
            assert response.status == 201, response
            if index == 0:
                first_message_id = response.json_body["message"]["message_id"]

        retry = await asgi_request(
            app,
            "POST",
            f"/api/v1/messages/conversations/{alice_bob_id}/messages",
            {
                "message_type": "text",
                "text_content": "history-000",
                "client_message_id": "history-000",
            },
            headers=alice_headers,
        )
        assert retry.status == 201 and retry.json_body["message"]["message_id"] == first_message_id, retry

        seen_sequences: list[int] = []
        before_seq = None
        while True:
            suffix = "page_size=17" if before_seq is None else f"page_size=17&before_seq={before_seq}"
            page = await asgi_request(
                app,
                "GET",
                f"/api/v1/messages/conversations/{alice_bob_id}/messages?{suffix}",
                headers=alice_headers,
            )
            assert page.status == 200, page
            sequences = [item["message_seq"] for item in page.json_body["items"]]
            assert sequences == sorted(sequences), sequences
            seen_sequences.extend(sequences)
            before_seq = page.json_body["next_before_seq"]
            if before_seq is None:
                break
        assert len(seen_sequences) == len(set(seen_sequences)) == 102, seen_sequences
        assert sorted(seen_sequences) == list(range(1, 103)), seen_sequences

        blocked = await asgi_request(
            app,
            "POST",
            f"/api/v1/social/blocks/{bob_id}",
            {"reason": "message-core-api"},
            headers=alice_headers,
        )
        assert blocked.status == 201, blocked
        for headers in (alice_headers, bob_headers):
            response = await asgi_request(
                app,
                "POST",
                f"/api/v1/messages/conversations/{alice_bob_id}/messages",
                {"message_type": "text", "text_content": "blocked"},
                headers=headers,
            )
            assert response.status == 403, response
            assert response.json_body["detail"]["code"] == "USER_INTERACTION_BLOCKED", response

        with get_connection() as connection:
            assert connection.execute(
                "SELECT COUNT(*) FROM chat_messages WHERE client_message_id = 'history-000';"
            ).fetchone()[0] == 1

        print("Message core API test passed.")


if __name__ == "__main__":
    asyncio.run(main())
