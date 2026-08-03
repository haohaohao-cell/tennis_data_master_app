from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
import os
from pathlib import Path
import sys
import tempfile
import uuid


ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT_DIR))

from backend.tests.activity_detail_api_smoke import login_phone
from backend.tests.auth_api_smoke import asgi_request


def iso(minutes: int) -> str:
    return (datetime(2026, 7, 31, 12, 0, tzinfo=UTC) + timedelta(minutes=minutes)).isoformat(
        timespec="seconds"
    ).replace("+00:00", "Z")


def add_post(
    connection,
    *,
    author_id: str,
    minutes: int,
    visibility: str = "public",
    review_status: str = "approved",
    status: str = "published",
    location_scope: str = "none",
    location_region: str | None = None,
    location_city: str | None = None,
) -> str:
    post_id = str(uuid.uuid4())
    published_at = iso(minutes)
    connection.execute(
        """
        INSERT INTO social_posts (
            social_post_id, author_user_id, content, visibility, status, review_status,
            location_scope, location_region, location_city, published_at, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """,
        (
            post_id,
            author_id,
            f"Feed post {minutes}",
            visibility,
            status,
            review_status,
            location_scope,
            location_region,
            location_city,
            published_at,
            published_at,
            published_at,
        ),
    )
    connection.execute(
        "INSERT INTO social_post_stats (social_post_id, like_count) VALUES (?, ?);",
        (post_id, max(minutes, 0)),
    )
    return post_id


async def main() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        os.environ["TENNIS_DB_PATH"] = str(Path(temp_dir) / "post_feed.sqlite3")

        from backend.app.core.database import initialize_database, transaction
        from backend.app.main import app

        initialize_database()
        alice_token, alice_id = await login_phone(app, "13700000001")
        _, bob_id = await login_phone(app, "13700000002")
        _, blocked_id = await login_phone(app, "13700000003")

        with transaction() as connection:
            connection.execute(
                """
                INSERT INTO user_follows (follow_id, follower_user_id, following_user_id, status)
                VALUES (?, ?, ?, 'active');
                """,
                (str(uuid.uuid4()), alice_id, bob_id),
            )
            connection.execute(
                """
                INSERT INTO user_blocks (user_block_id, blocker_user_id, blocked_user_id)
                VALUES (?, ?, ?);
                """,
                (str(uuid.uuid4()), alice_id, blocked_id),
            )
            public_new = add_post(connection, author_id=bob_id, minutes=9)
            following_only = add_post(connection, author_id=bob_id, minutes=8, visibility="followers")
            private_post = add_post(connection, author_id=bob_id, minutes=7, visibility="private")
            rejected_post = add_post(connection, author_id=bob_id, minutes=6, review_status="rejected")
            hidden_post = add_post(connection, author_id=bob_id, minutes=5, status="hidden")
            blocked_post = add_post(connection, author_id=blocked_id, minutes=10)
            following_newest = add_post(connection, author_id=bob_id, minutes=11, visibility="followers")
            nearby_city = add_post(
                connection,
                author_id=bob_id,
                minutes=4,
                location_scope="city",
                location_region="北京",
                location_city="北京",
            )
            nearby_region = add_post(
                connection,
                author_id=bob_id,
                minutes=3,
                location_scope="region",
                location_region="北京",
            )

        anonymous = await asgi_request(app, "GET", "/api/v1/posts/feed?feed_type=recommended&limit=20")
        assert anonymous.status == 200, anonymous
        anonymous_ids = {item["post"]["social_post_id"] for item in anonymous.json_body["items"]}
        assert public_new in anonymous_ids
        assert private_post not in anonymous_ids
        assert rejected_post not in anonymous_ids
        assert hidden_post not in anonymous_ids
        assert blocked_post in anonymous_ids

        headers = {"authorization": f"Bearer {alice_token}"}
        first_page = await asgi_request(
            app,
            "GET",
            "/api/v1/posts/feed?feed_type=recommended&limit=2",
            headers=headers,
        )
        assert first_page.status == 200, first_page
        first_ids = [item["post"]["social_post_id"] for item in first_page.json_body["items"]]
        assert blocked_post not in first_ids
        assert first_page.json_body["has_more"] is True

        second_page = await asgi_request(
            app,
            "GET",
            f"/api/v1/posts/feed?feed_type=recommended&limit=20&cursor={first_page.json_body['next_cursor']}",
            headers=headers,
        )
        assert second_page.status == 200, second_page
        second_ids = [item["post"]["social_post_id"] for item in second_page.json_body["items"]]
        assert not set(first_ids).intersection(second_ids)

        following = await asgi_request(
            app,
            "GET",
            "/api/v1/posts/feed?feed_type=following&limit=20",
            headers=headers,
        )
        assert following.status == 200, following
        following_ids = [item["post"]["social_post_id"] for item in following.json_body["items"]]
        assert following_ids[:3] == [following_newest, public_new, following_only]
        assert private_post not in following_ids

        views = await asgi_request(
            app,
            "POST",
            "/api/v1/posts/views/bulk",
            {
                "items": [
                    {"social_post_id": public_new, "source": "home_feed", "dwell_time_ms": 1200},
                    {"social_post_id": public_new, "source": "home_feed", "dwell_time_ms": 900},
                ]
            },
            headers=headers,
        )
        assert views.status == 200, views
        assert views.json_body["accepted_post_ids"] == [public_new]

        after_view = await asgi_request(
            app,
            "GET",
            "/api/v1/posts/feed?feed_type=following&limit=2",
            headers=headers,
        )
        assert after_view.status == 200, after_view
        after_view_ids = [item["post"]["social_post_id"] for item in after_view.json_body["items"]]
        assert after_view_ids == [following_newest, following_only]
        assert after_view.json_body["has_more"] is True

        after_view_next = await asgi_request(
            app,
            "GET",
            f"/api/v1/posts/feed?feed_type=following&limit=20&cursor={after_view.json_body['next_cursor']}",
            headers=headers,
        )
        assert after_view_next.status == 200, after_view_next
        assert [item["post"]["social_post_id"] for item in after_view_next.json_body["items"]] == [
            nearby_city,
            nearby_region,
            public_new,
        ]

        hidden = await asgi_request(
            app,
            "POST",
            f"/api/v1/posts/{following_only}/hide",
            {"reason": "not_interested"},
            headers=headers,
        )
        assert hidden.status == 200, hidden
        after_hide = await asgi_request(
            app,
            "GET",
            "/api/v1/posts/feed?feed_type=following&limit=20",
            headers=headers,
        )
        after_hide_ids = [item["post"]["social_post_id"] for item in after_hide.json_body["items"]]
        assert following_only not in after_hide_ids
        assert after_hide_ids[:4] == [following_newest, nearby_city, nearby_region, public_new]

        nearby = await asgi_request(
            app,
            "GET",
            "/api/v1/posts/feed?feed_type=nearby&city=%E5%8C%97%E4%BA%AC&region=%E5%8C%97%E4%BA%AC&limit=20",
            headers=headers,
        )
        assert nearby.status == 200, nearby
        nearby_ids = {item["post"]["social_post_id"] for item in nearby.json_body["items"]}
        assert nearby_city in nearby_ids
        assert nearby_region in nearby_ids
        assert nearby.json_body["fallback_mode"] == "region"

        invalid_cursor = await asgi_request(
            app,
            "GET",
            "/api/v1/posts/feed?feed_type=recommended&cursor=bad-cursor",
            headers=headers,
        )
        assert invalid_cursor.status == 400, invalid_cursor
        assert invalid_cursor.json_body["detail"]["code"] == "INVALID_FEED_CURSOR"

        print("Post Feed API smoke test passed.")


if __name__ == "__main__":
    asyncio.run(main())
