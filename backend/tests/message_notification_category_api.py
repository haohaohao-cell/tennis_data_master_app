from __future__ import annotations

import asyncio
import os
from pathlib import Path
import sys
import tempfile
import uuid


ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT_DIR))

from backend.tests.activity_detail_api_smoke import login_phone
from backend.tests.auth_api_smoke import asgi_request


async def main() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        os.environ["TENNIS_DB_PATH"] = str(Path(temp_dir) / "message_notification_category.sqlite3")
        os.environ["TENNIS_VIDEO_STORAGE_DIR"] = str(Path(temp_dir) / "videos")

        from backend.app.core.database import initialize_database, transaction
        from backend.app.main import app
        from backend.app.messages import service

        initialize_database()
        recipient_token, recipient_id = await login_phone(app, "13930000001")
        requester_token, requester_id = await login_phone(app, "13930000002")
        legacy_token, legacy_requester_id = await login_phone(app, "13930000003")
        recipient_headers = {"authorization": f"Bearer {recipient_token}"}
        requester_headers = {"authorization": f"Bearer {requester_token}"}

        interaction_events = (
            ("follow", "follow"),
            ("post_like", "post_like"),
            ("post_comment", "post_comment"),
            ("comment_reply", "comment_reply"),
            ("custom", "future_interaction"),
        )
        course_events = (
            ("system_announcement", "system"),
            ("ai_analysis_completed", "ai"),
            ("coach_application_reviewed", "coach"),
            ("lesson_updated", "lesson"),
        )
        with transaction() as connection:
            for event_type, key in interaction_events:
                service.create_notification_in_transaction(
                    connection,
                    recipient_user_id=recipient_id,
                    event_type=event_type,
                    category="interaction",
                    actor_user_id=requester_id,
                    object_type="user",
                    object_id=requester_id,
                    title=key,
                    dedup_key=f"category-test:{key}",
                )
            for event_type, category in course_events:
                service.create_notification_in_transaction(
                    connection,
                    recipient_user_id=recipient_id,
                    event_type=event_type,
                    category=category,
                    actor_user_id=requester_id,
                    title=f"course-{category}",
                    dedup_key=f"category-test:course:{category}",
                )

        # A new request carries explicit payload typing while preserving the stored event_type.
        request_response = await asgi_request(
            app,
            "POST",
            "/api/v1/messages/requests",
            {"target_user_id": recipient_id},
            headers=requester_headers,
        )
        assert request_response.status == 201, request_response
        new_request_id = request_response.json_body["request"]["message_request_id"]

        # Simulate an already-persisted request notification without the new payload marker.
        legacy_request_id = str(uuid.uuid4())
        with transaction() as connection:
            connection.execute(
                """
                INSERT INTO chat_message_requests (
                    message_request_id, requester_user_id, recipient_user_id, request_message, source
                ) VALUES (?, ?, ?, ?, ?);
                """,
                (legacy_request_id, legacy_requester_id, recipient_id, "legacy", "test"),
            )
            service.create_notification_in_transaction(
                connection,
                recipient_user_id=recipient_id,
                event_type="custom",
                category="interaction",
                actor_user_id=legacy_requester_id,
                object_type="user",
                object_id=legacy_requester_id,
                title="legacy-request",
                dedup_key=f"message_request:{legacy_request_id}",
                payload={"message_request_id": legacy_request_id},
            )

        all_response = await asgi_request(app, "GET", "/api/v1/notifications?page_size=50", headers=recipient_headers)
        assert all_response.status == 200, all_response
        events_by_title = {item["event"]["title"]: item["event"] for item in all_response.json_body["items"]}
        for event_type, key in interaction_events:
            event = events_by_title[key]
            assert event["event_type"] == event_type
            assert event["notification_type"] == event_type
            assert event["product_category"] == "interaction_follow"
        for event_type, category in course_events:
            event = events_by_title[f"course-{category}"]
            assert event["event_type"] == event_type
            assert event["notification_type"] == event_type
            assert event["product_category"] == "course_system"

        request_events = [
            item["event"] for item in all_response.json_body["items"]
            if item["event"]["product_category"] == "request"
        ]
        assert len(request_events) == 2, request_events
        assert all(event["event_type"] == "custom" for event in request_events)
        assert all(event["notification_type"] == "message_request" for event in request_events)
        with transaction() as connection:
            new_payload = connection.execute(
                "SELECT payload_json FROM notification_events WHERE dedup_key = ?;",
                (f"message_request:{new_request_id}",),
            ).fetchone()[0]
            legacy_payload = connection.execute(
                "SELECT payload_json FROM notification_events WHERE dedup_key = ?;",
                (f"message_request:{legacy_request_id}",),
            ).fetchone()[0]
        assert '"notification_type":"message_request"' in new_payload
        assert '"notification_type":"message_request"' not in legacy_payload

        # Product filtering happens before LIMIT/OFFSET and excludes requests from normal categories.
        interaction_page_1 = await asgi_request(
            app, "GET", "/api/v1/notifications?product_category=interaction_follow&page=1&page_size=3", headers=recipient_headers
        )
        interaction_page_2 = await asgi_request(
            app, "GET", "/api/v1/notifications?product_category=interaction_follow&page=2&page_size=3", headers=recipient_headers
        )
        assert interaction_page_1.status == interaction_page_2.status == 200
        interaction_items = interaction_page_1.json_body["items"] + interaction_page_2.json_body["items"]
        assert len(interaction_page_1.json_body["items"]) == 3
        assert len(interaction_items) == 5
        assert all(item["event"]["product_category"] == "interaction_follow" for item in interaction_items)

        course_page_1 = await asgi_request(
            app, "GET", "/api/v1/notifications?product_category=course_system&page=1&page_size=3", headers=recipient_headers
        )
        course_page_2 = await asgi_request(
            app, "GET", "/api/v1/notifications?product_category=course_system&page=2&page_size=3", headers=recipient_headers
        )
        assert course_page_1.status == course_page_2.status == 200
        course_items = course_page_1.json_body["items"] + course_page_2.json_body["items"]
        assert len(course_page_1.json_body["items"]) == 3
        assert len(course_items) == 4
        assert all(item["event"]["product_category"] == "course_system" for item in course_items)

        request_filter = await asgi_request(
            app, "GET", "/api/v1/notifications?product_category=request&page_size=10", headers=recipient_headers
        )
        assert request_filter.status == 200, request_filter
        assert len(request_filter.json_body["items"]) == 2
        assert all(item["event"]["product_category"] == "request" for item in request_filter.json_body["items"])

        # P2-01: two unread request notifications and two pending requests contribute two, not four.
        counts = await asgi_request(app, "GET", "/api/v1/messages/unread-counts", headers=recipient_headers)
        assert counts.status == 200, counts
        assert counts.json_body["unread_notification_count"] == 11
        assert counts.json_body["pending_message_request_count"] == 2
        assert counts.json_body["messages_tab_badge_count"] == 11

        invalid_filter = await asgi_request(
            app, "GET", "/api/v1/notifications?product_category=unknown", headers=recipient_headers
        )
        assert invalid_filter.status == 422, invalid_filter

        print("Message notification category API test passed.")


if __name__ == "__main__":
    asyncio.run(main())
