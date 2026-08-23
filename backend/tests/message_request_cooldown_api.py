from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
import os
from pathlib import Path
import sys
import tempfile


ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT_DIR))

from backend.tests.activity_detail_api_smoke import login_phone
from backend.tests.auth_api_smoke import asgi_request


REQUEST_PATH = "/api/v1/messages/requests"


async def create_request(app, headers: dict[str, str], target_user_id: str, message: str) -> object:
    return await asgi_request(
        app,
        "POST",
        REQUEST_PATH,
        {"target_user_id": target_user_id, "request_message": message, "source": "cooldown-test"},
        headers=headers,
    )


async def main() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        os.environ["TENNIS_DB_PATH"] = str(Path(temp_dir) / "message_request_cooldown.sqlite3")

        from backend.app.core.database import get_connection, initialize_database, transaction
        from backend.app.main import app

        initialize_database()
        users = [await login_phone(app, f"1394510000{index}") for index in range(1, 8)]
        (alice_token, alice_id), (bob_token, bob_id), (carol_token, carol_id), (dave_token, dave_id), (erin_token, erin_id), (frank_token, frank_id), (gina_token, gina_id) = users
        alice_headers = {"authorization": f"Bearer {alice_token}"}
        bob_headers = {"authorization": f"Bearer {bob_token}"}
        carol_headers = {"authorization": f"Bearer {carol_token}"}
        dave_headers = {"authorization": f"Bearer {dave_token}"}
        frank_headers = {"authorization": f"Bearer {frank_token}"}
        gina_headers = {"authorization": f"Bearer {gina_token}"}

        # A -> B is initially eligible for a request and B can decline it.
        first = await create_request(app, alice_headers, bob_id, "first request")
        assert first.status == 201, first
        first_id = first.json_body["request"]["message_request_id"]
        declined = await asgi_request(app, "POST", f"{REQUEST_PATH}/{first_id}/decline", headers=bob_headers)
        assert declined.status == 200, declined
        assert declined.json_body["request"]["status"] == "declined"
        assert declined.json_body["request"]["responded_at"]

        with get_connection() as connection:
            before_pair_rows = connection.execute(
                "SELECT COUNT(*) FROM chat_message_requests WHERE requester_user_id = ? AND recipient_user_id = ?;",
                (alice_id, bob_id),
            ).fetchone()[0]
            before_pair_notifications = connection.execute(
                """
                SELECT COUNT(*)
                FROM user_notifications AS notifications
                JOIN notification_events AS events
                  ON events.notification_event_id = notifications.notification_event_id
                WHERE notifications.recipient_user_id = ?
                  AND events.dedup_key LIKE 'message_request:%';
                """,
                (bob_id,),
            ).fetchone()[0]
            before_privacy = connection.execute(
                "SELECT * FROM user_privacy_settings WHERE user_id IN (?, ?) ORDER BY user_id;",
                (alice_id, bob_id),
            ).fetchall()
            before_blocks = connection.execute(
                "SELECT COUNT(*) FROM user_blocks WHERE (blocker_user_id = ? AND blocked_user_id = ?) OR (blocker_user_id = ? AND blocked_user_id = ?);",
                (alice_id, bob_id, bob_id, alice_id),
            ).fetchone()[0]
        before_counts = (await asgi_request(app, "GET", "/api/v1/messages/unread-counts", headers=bob_headers)).json_body

        retry = await create_request(app, alice_headers, bob_id, "must not persist this text")
        assert retry.status == 429, retry
        assert retry.json_body["detail"]["code"] == "MESSAGE_REQUEST_COOLDOWN_ACTIVE"
        after_counts = (await asgi_request(app, "GET", "/api/v1/messages/unread-counts", headers=bob_headers)).json_body
        assert after_counts == before_counts
        with get_connection() as connection:
            assert connection.execute(
                "SELECT COUNT(*) FROM chat_message_requests WHERE requester_user_id = ? AND recipient_user_id = ?;",
                (alice_id, bob_id),
            ).fetchone()[0] == before_pair_rows
            assert connection.execute(
                """
                SELECT COUNT(*)
                FROM user_notifications AS notifications
                JOIN notification_events AS events
                  ON events.notification_event_id = notifications.notification_event_id
                WHERE notifications.recipient_user_id = ?
                  AND events.dedup_key LIKE 'message_request:%';
                """,
                (bob_id,),
            ).fetchone()[0] == before_pair_notifications
            assert connection.execute(
                "SELECT COUNT(*) FROM chat_message_requests WHERE request_message = ?;",
                ("must not persist this text",),
            ).fetchone()[0] == 0
            after_privacy = connection.execute(
                "SELECT * FROM user_privacy_settings WHERE user_id IN (?, ?) ORDER BY user_id;",
                (alice_id, bob_id),
            ).fetchall()
            after_blocks = connection.execute(
                "SELECT COUNT(*) FROM user_blocks WHERE (blocker_user_id = ? AND blocked_user_id = ?) OR (blocker_user_id = ? AND blocked_user_id = ?);",
                (alice_id, bob_id, bob_id, alice_id),
            ).fetchone()[0]
        assert [tuple(row) for row in after_privacy] == [tuple(row) for row in before_privacy]
        assert after_blocks == before_blocks

        # Pending retries remain idempotent and do not become cooldown errors.
        pending = await create_request(app, alice_headers, carol_id, "pending request")
        assert pending.status == 201, pending
        pending_retry = await create_request(app, alice_headers, carol_id, "different text")
        assert pending_retry.status == 201
        assert pending_retry.json_body["request"]["message_request_id"] == pending.json_body["request"]["message_request_id"]
        with get_connection() as connection:
            assert connection.execute(
                "SELECT COUNT(*) FROM chat_message_requests WHERE requester_user_id = ? AND recipient_user_id = ?;",
                (alice_id, carol_id),
            ).fetchone()[0] == 1

        # The reverse direction is independent and remains eligible.
        reverse = await create_request(app, bob_headers, alice_id, "reverse direction")
        assert reverse.status == 201, reverse
        other_requester = await create_request(app, carol_headers, bob_id, "other requester")
        assert other_requester.status == 201, other_requester
        # A -> C and C -> B are independent from A -> B's cooldown.

        # Make the first decline old enough, then a new request gets a new ID and normal notification.
        old_decline = (datetime.now(UTC) - timedelta(hours=24, seconds=1)).isoformat().replace("+00:00", "Z")
        with transaction() as connection:
            connection.execute("UPDATE chat_message_requests SET responded_at = ? WHERE message_request_id = ?;", (old_decline, first_id))
        expired = await create_request(app, alice_headers, bob_id, "after expiry")
        assert expired.status == 201, expired
        second_id = expired.json_body["request"]["message_request_id"]
        assert second_id != first_id and expired.json_body["request"]["status"] == "pending"
        second_declined = await asgi_request(app, "POST", f"{REQUEST_PATH}/{second_id}/decline", headers=bob_headers)
        assert second_declined.status == 200
        just_before_expiry = (datetime.now(UTC) - timedelta(hours=23, minutes=59)).isoformat().replace("+00:00", "Z")
        with transaction() as connection:
            connection.execute("UPDATE chat_message_requests SET responded_at = ? WHERE message_request_id = ?;", (just_before_expiry, second_id))
        still_blocked = await create_request(app, alice_headers, bob_id, "still cooling down")
        assert still_blocked.status == 429
        safely_expired = (datetime.now(UTC) - timedelta(hours=24, seconds=1)).isoformat().replace("+00:00", "Z")
        with transaction() as connection:
            connection.execute("UPDATE chat_message_requests SET responded_at = ? WHERE message_request_id = ?;", (safely_expired, second_id))
        after_second_expiry = await create_request(app, alice_headers, bob_id, "second fresh request")
        assert after_second_expiry.status == 201
        third_id = after_second_expiry.json_body["request"]["message_request_id"]
        assert third_id not in {first_id, second_id}

        # A legacy malformed declined row with no authoritative timestamp is not an indefinite block.
        legacy = await create_request(app, dave_headers, alice_id, "legacy source")
        assert legacy.status == 201
        legacy_id = legacy.json_body["request"]["message_request_id"]
        legacy_declined = await asgi_request(app, "POST", f"{REQUEST_PATH}/{legacy_id}/decline", headers=alice_headers)
        assert legacy_declined.status == 200
        with transaction() as connection:
            connection.execute("PRAGMA ignore_check_constraints = ON;")
            connection.execute("UPDATE chat_message_requests SET responded_at = NULL WHERE message_request_id = ?;", (legacy_id,))
            connection.execute("PRAGMA ignore_check_constraints = OFF;")
        legacy_retry = await create_request(app, dave_headers, alice_id, "legacy retry allowed")
        assert legacy_retry.status == 201

        # Block remains authoritative during any request state.
        blocked_request = await create_request(app, alice_headers, frank_id, "blocked request")
        assert blocked_request.status == 201
        blocked = await asgi_request(app, "POST", f"/api/v1/social/blocks/{frank_id}", headers=alice_headers)
        assert blocked.status == 201
        blocked_retry = await create_request(app, alice_headers, frank_id, "blocked retry")
        assert blocked_retry.status == 403

        # An accepted request and an existing Direct conversation retain their existing errors.
        accepted_request = await create_request(app, alice_headers, gina_id, "accepted request")
        assert accepted_request.status == 201
        accepted_id = accepted_request.json_body["request"]["message_request_id"]
        accepted = await asgi_request(app, "POST", f"{REQUEST_PATH}/{accepted_id}/accept", headers=gina_headers)
        assert accepted.status == 200
        direct_existing = await create_request(app, alice_headers, gina_id, "direct already exists")
        assert direct_existing.status == 409
        assert direct_existing.json_body["detail"]["code"] == "DIRECT_CONVERSATION_EXISTS"

        print("Message request cooldown API test passed.")


if __name__ == "__main__":
    asyncio.run(main())
