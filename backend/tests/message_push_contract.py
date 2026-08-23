from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import sys
import tempfile


ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT_DIR))

from backend.tests.activity_detail_api_smoke import login_phone
from backend.tests.auth_api_smoke import asgi_request


async def _follow(app, source_id: str, target_id: str, headers: dict[str, str]) -> None:
    response = await asgi_request(
        app,
        "POST",
        f"/api/v1/social/follows/{target_id}",
        {"source": "message-push-contract"},
        headers=headers,
    )
    assert response.status == 201, (source_id, target_id, response)


async def main() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        os.environ["TENNIS_DB_PATH"] = str(Path(temp_dir) / "message_push_contract.sqlite3")
        os.environ["TENNIS_VIDEO_STORAGE_DIR"] = str(Path(temp_dir) / "videos")

        from backend.app.core.database import initialize_database, transaction
        from backend.app.main import app
        from backend.app.messages import service

        initialize_database()
        alice_token, alice_id = await login_phone(app, "13933000001")
        bob_token, bob_id = await login_phone(app, "13933000002")
        carol_token, carol_id = await login_phone(app, "13933000003")
        alice_headers = {"authorization": f"Bearer {alice_token}"}
        bob_headers = {"authorization": f"Bearer {bob_token}"}
        carol_headers = {"authorization": f"Bearer {carol_token}"}

        await _follow(app, alice_id, bob_id, alice_headers)
        await _follow(app, bob_id, alice_id, bob_headers)
        conversation = await asgi_request(
            app,
            "POST",
            "/api/v1/messages/direct-conversations",
            {"target_user_id": bob_id},
            headers=alice_headers,
        )
        assert conversation.status == 201, conversation
        conversation_id = conversation.json_body["conversation"]["conversation_id"]

        baseline_counts = await asgi_request(
            app, "GET", "/api/v1/messages/unread-counts", headers=bob_headers
        )
        first_send = await asgi_request(
            app,
            "POST",
            f"/api/v1/messages/conversations/{conversation_id}/messages",
            {
                "message_type": "text",
                "text_content": "private direct message text",
                "client_message_id": "push-contract-dm-1",
            },
            headers=alice_headers,
        )
        assert first_send.status == 201, first_send
        first_message_id = first_send.json_body["message"]["message_id"]
        direct_intent = service.build_direct_message_push_intent(bob_id, first_message_id)
        assert direct_intent.decision == "eligible"
        assert direct_intent.request is not None
        assert direct_intent.request.push_kind == "direct_message"
        assert direct_intent.request.recipient_user_id == bob_id
        assert direct_intent.request.preference_kind == "direct_message"
        assert direct_intent.request.target.type == "chat"
        assert direct_intent.request.target.conversation_id == conversation_id
        assert direct_intent.request.data.message_id == first_message_id
        assert direct_intent.request.data.sender_user_id == alice_id
        assert direct_intent.request.delivery_id == f"direct_message:{first_message_id}"
        assert direct_intent.request.display.body is None

        retry = await asgi_request(
            app,
            "POST",
            f"/api/v1/messages/conversations/{conversation_id}/messages",
            {
                "message_type": "text",
                "text_content": "private direct message text",
                "client_message_id": "push-contract-dm-1",
            },
            headers=alice_headers,
        )
        assert retry.status == 201
        assert retry.json_body["message"]["message_id"] == first_message_id
        retry_intent = service.build_direct_message_push_intent(bob_id, first_message_id)
        assert retry_intent.request is not None
        assert retry_intent.request.delivery_id == direct_intent.request.delivery_id
        counts_after_retry = await asgi_request(
            app, "GET", "/api/v1/messages/unread-counts", headers=bob_headers
        )
        assert counts_after_retry.json_body["unread_direct_message_count"] == (
            baseline_counts.json_body["unread_direct_message_count"] + 1
        )

        dm_off = await asgi_request(
            app,
            "PATCH",
            "/api/v1/notifications/preferences",
            {"direct_message_notifications": False},
            headers=bob_headers,
        )
        assert dm_off.status == 200, dm_off
        second_send = await asgi_request(
            app,
            "POST",
            f"/api/v1/messages/conversations/{conversation_id}/messages",
            {
                "message_type": "text",
                "text_content": "still persists while push is off",
                "client_message_id": "push-contract-dm-2",
            },
            headers=alice_headers,
        )
        assert second_send.status == 201, second_send
        suppressed_direct = service.build_direct_message_push_intent(
            bob_id, second_send.json_body["message"]["message_id"]
        )
        assert suppressed_direct.decision == "suppressed_by_preference"
        counts_after_second = await asgi_request(
            app, "GET", "/api/v1/messages/unread-counts", headers=bob_headers
        )
        assert counts_after_second.json_body["unread_direct_message_count"] == (
            baseline_counts.json_body["unread_direct_message_count"] + 2
        )

        before_request_counts = counts_after_second.json_body
        message_request = await asgi_request(
            app,
            "POST",
            "/api/v1/messages/requests",
            {"target_user_id": bob_id, "request_message": "private request text"},
            headers=carol_headers,
        )
        assert message_request.status == 201, message_request
        request_id = message_request.json_body["request"]["message_request_id"]
        request_intent = service.build_message_request_push_intent(bob_id, request_id)
        assert request_intent.decision == "eligible"
        assert request_intent.request is not None
        assert request_intent.request.push_kind == "message_request"
        assert request_intent.request.notification_type == "message_request"
        assert request_intent.request.preference_kind == "message_request"
        assert request_intent.request.target.type == "message_request"
        assert request_intent.request.target.request_id == request_id
        assert request_intent.request.delivery_id == f"message_request:{request_id}"
        assert request_intent.request.display.body is None

        request_notification_id = next(
            item["notification_event_id"]
            for item in (
                await asgi_request(app, "GET", "/api/v1/notifications", headers=bob_headers)
            ).json_body["items"]
            if item["event"]["notification_type"] == "message_request"
        )
        delegated_request_intent = service.build_notification_event_push_intent(
            bob_id, request_notification_id
        )
        assert delegated_request_intent.request is not None
        assert delegated_request_intent.request.delivery_id == request_intent.request.delivery_id

        request_off = await asgi_request(
            app,
            "PATCH",
            "/api/v1/notifications/preferences",
            {"message_request_notifications": False},
            headers=bob_headers,
        )
        assert request_off.status == 200, request_off
        assert service.build_message_request_push_intent(
            bob_id, request_id
        ).decision == "suppressed_by_preference"
        requests = await asgi_request(
            app,
            "GET",
            "/api/v1/messages/requests?box=inbox&status=pending",
            headers=bob_headers,
        )
        assert any(item["message_request_id"] == request_id for item in requests.json_body["items"])
        counts_after_request = (
            await asgi_request(app, "GET", "/api/v1/messages/unread-counts", headers=bob_headers)
        ).json_body
        assert counts_after_request["pending_message_request_count"] == (
            before_request_counts["pending_message_request_count"] + 1
        )
        assert counts_after_request["unread_notification_count"] == (
            before_request_counts["unread_notification_count"] + 1
        )
        assert counts_after_request["messages_tab_badge_count"] == (
            before_request_counts["messages_tab_badge_count"] + 1
        )

        mapped_specs = {
            "follow": ("interaction", "user", alice_id, None, None, "user_profile", "follow"),
            "post_like": (
                "interaction", "social_post", "post-1", None, None, "post_detail", "like_comment"
            ),
            "post_comment": (
                "interaction", "comment", "comment-1", "social_post", "post-1", "post_comments", "like_comment"
            ),
            "comment_reply": (
                "interaction", "comment", "comment-2", "social_post", "post-1", "post_comments", "like_comment"
            ),
            "lesson_updated": ("lesson", "lesson", "lesson-1", None, None, "none", "course"),
            "ai_analysis_completed": (
                "ai", "analysis", "analysis-1", "tennis_activity", "activity-1", "activity_detail", "ai_analysis"
            ),
        }
        unmapped_specs = {
            "mention": "interaction",
            "video_shared": "interaction",
            "coach_application_reviewed": "coach",
            "system_announcement": "system",
            "custom": "system",
        }
        event_ids: dict[str, str] = {}
        with transaction() as connection:
            for event_type, spec in mapped_specs.items():
                category, object_type, object_id, context_type, context_id, _, _ = spec
                event_ids[event_type] = service.create_notification_in_transaction(
                    connection,
                    recipient_user_id=bob_id,
                    event_type=event_type,
                    category=category,
                    actor_user_id=alice_id,
                    object_type=object_type,
                    object_id=object_id,
                    context_type=context_type,
                    context_id=context_id,
                    title=f"push-{event_type}",
                    body=f"body-{event_type}",
                    dedup_key=f"push-contract:{event_type}",
                )
            for event_type, category in unmapped_specs.items():
                event_ids[event_type] = service.create_notification_in_transaction(
                    connection,
                    recipient_user_id=bob_id,
                    event_type=event_type,
                    category=category,
                    actor_user_id=alice_id,
                    title=f"push-{event_type}",
                    dedup_key=f"push-contract:{event_type}",
                )
            malformed_event_id = service.create_notification_in_transaction(
                connection,
                recipient_user_id=bob_id,
                event_type="follow",
                category="interaction",
                actor_user_id=alice_id,
                object_type="user",
                object_id="   ",
                title="malformed-follow",
                dedup_key="push-contract:malformed-follow",
            )

        serializable_intents = [direct_intent, suppressed_direct, request_intent]
        for event_type, spec in mapped_specs.items():
            _, _, _, _, _, target_type, preference_kind = spec
            intent = service.build_notification_event_push_intent(bob_id, event_ids[event_type])
            expected_decision = "unsupported" if event_type == "lesson_updated" else "eligible"
            assert intent.decision == expected_decision, (event_type, intent)
            assert intent.request is not None
            assert intent.request.push_kind == "notification_event"
            assert intent.request.notification_type == event_type
            assert intent.request.preference_kind == preference_kind
            assert intent.request.target.type == target_type
            assert intent.request.delivery_id == f"notification_event:{event_ids[event_type]}"
            serializable_intents.append(intent)

        malformed = service.build_notification_event_push_intent(bob_id, malformed_event_id)
        assert malformed.decision == "invalid_target"
        assert malformed.request is not None and malformed.request.target.type == "none"
        serializable_intents.append(malformed)

        for event_type in unmapped_specs:
            intent = service.build_notification_event_push_intent(bob_id, event_ids[event_type])
            assert intent.decision == "eligible_without_preference_mapping", (event_type, intent)
            assert intent.request is not None
            assert intent.request.preference_kind is None
            serializable_intents.append(intent)

        all_mapped_off = await asgi_request(
            app,
            "PATCH",
            "/api/v1/notifications/preferences",
            {
                "follow_notifications": False,
                "like_comment_notifications": False,
                "course_notifications": False,
                "ai_analysis_notifications": False,
            },
            headers=bob_headers,
        )
        assert all_mapped_off.status == 200, all_mapped_off
        for event_type in mapped_specs:
            intent = service.build_notification_event_push_intent(bob_id, event_ids[event_type])
            assert intent.decision == "suppressed_by_preference", (event_type, intent)

        notifications_after_suppression = await asgi_request(
            app, "GET", "/api/v1/notifications?page_size=50", headers=bob_headers
        )
        returned_event_ids = {
            item["notification_event_id"] for item in notifications_after_suppression.json_body["items"]
        }
        assert set(event_ids.values()).issubset(returned_event_ids)
        assert malformed_event_id in returned_event_ids

        unsupported = service.build_direct_message_push_intent(alice_id, first_message_id)
        assert unsupported.decision == "unsupported" and unsupported.request is None

        encoded = json.dumps(
            [intent.model_dump(mode="json") for intent in serializable_intents],
            ensure_ascii=False,
        )
        assert "private direct message text" not in encoded
        assert "private request text" not in encoded
        assert "phone" not in encoded and "email" not in encoded

        print("Message Push contract test passed.")


if __name__ == "__main__":
    asyncio.run(main())
