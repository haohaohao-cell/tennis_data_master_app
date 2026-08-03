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


def iso_at(hour: int, minute: int) -> str:
    return datetime(2026, 8, 1, hour, minute, tzinfo=UTC).isoformat(
        timespec="seconds"
    ).replace("+00:00", "Z")


def insert_post(
    connection,
    *,
    author_user_id: str,
    content: str,
    published_at: str,
    social_post_id: str,
    visibility: str = "public",
) -> None:
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
        VALUES (?, ?, ?, ?, 'published', 'approved', ?, ?, ?);
        """,
        (social_post_id, author_user_id, content, visibility, published_at, published_at, published_at),
    )
    connection.execute(
        "INSERT INTO social_post_stats (social_post_id) VALUES (?);",
        (social_post_id,),
    )


async def main() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        os.environ["TENNIS_DB_PATH"] = str(Path(temp_dir) / "profile_post_collections.sqlite3")
        os.environ["TENNIS_VIDEO_STORAGE_DIR"] = str(Path(temp_dir) / "videos")

        from backend.app.core.database import initialize_database, transaction
        from backend.app.main import app

        initialize_database()

        author_token, author_id = await login_phone(app, "13000000001")
        viewer_token, viewer_id = await login_phone(app, "13000000002")
        author_headers = {"authorization": f"Bearer {author_token}"}
        viewer_headers = {"authorization": f"Bearer {viewer_token}"}

        newest_favorite_post_id = str(uuid.uuid4())
        oldest_favorite_post_id = str(uuid.uuid4())
        hidden_favorite_post_id = str(uuid.uuid4())
        private_favorite_post_id = str(uuid.uuid4())
        liked_post_id = str(uuid.uuid4())
        private_liked_post_id = str(uuid.uuid4())

        with transaction() as connection:
            insert_post(
                connection,
                author_user_id=author_id,
                content="Newest favorite post",
                published_at=iso_at(9, 0),
                social_post_id=newest_favorite_post_id,
            )
            insert_post(
                connection,
                author_user_id=author_id,
                content="Oldest favorite post",
                published_at=iso_at(8, 0),
                social_post_id=oldest_favorite_post_id,
            )
            insert_post(
                connection,
                author_user_id=author_id,
                content="Hidden favorite post",
                published_at=iso_at(7, 0),
                social_post_id=hidden_favorite_post_id,
            )
            insert_post(
                connection,
                author_user_id=author_id,
                content="Private favorite post",
                published_at=iso_at(6, 0),
                social_post_id=private_favorite_post_id,
                visibility="private",
            )
            insert_post(
                connection,
                author_user_id=author_id,
                content="Visible liked post",
                published_at=iso_at(5, 0),
                social_post_id=liked_post_id,
            )
            insert_post(
                connection,
                author_user_id=author_id,
                content="Private liked post",
                published_at=iso_at(4, 0),
                social_post_id=private_liked_post_id,
                visibility="private",
            )

            for social_post_id, favorited_at in [
                (newest_favorite_post_id, iso_at(12, 30)),
                (oldest_favorite_post_id, iso_at(11, 30)),
                (hidden_favorite_post_id, iso_at(10, 30)),
                (private_favorite_post_id, iso_at(9, 30)),
            ]:
                connection.execute(
                    """
                    INSERT INTO post_favorites (
                        favorite_id,
                        social_post_id,
                        user_id,
                        status,
                        source,
                        favorited_at
                    )
                    VALUES (?, ?, ?, 'active', ?, ?);
                    """,
                    (str(uuid.uuid4()), social_post_id, viewer_id, "profile", favorited_at),
                )

            for social_post_id, reacted_at in [
                (liked_post_id, iso_at(12, 45)),
                (private_liked_post_id, iso_at(10, 45)),
            ]:
                connection.execute(
                    """
                    INSERT INTO post_reactions (
                        reaction_id,
                        social_post_id,
                        user_id,
                        reaction_type,
                        status,
                        source,
                        reacted_at
                    )
                    VALUES (?, ?, ?, 'like', 'active', 'profile', ?);
                    """,
                    (str(uuid.uuid4()), social_post_id, viewer_id, reacted_at),
                )

            connection.execute(
                """
                INSERT INTO user_post_hides (
                    user_post_hide_id,
                    user_id,
                    social_post_id,
                    status,
                    source,
                    hidden_at
                )
                VALUES (?, ?, ?, 'active', 'profile', ?);
                """,
                (str(uuid.uuid4()), viewer_id, hidden_favorite_post_id, iso_at(12, 0)),
            )

        first_favorites = await asgi_request(
            app,
            "GET",
            "/api/v1/me/favorite-posts?limit=1",
            headers=viewer_headers,
        )
        assert first_favorites.status == 200, first_favorites
        assert first_favorites.json_body["collection"] == "favorites"
        assert first_favorites.json_body["items"][0]["post"]["social_post_id"] == newest_favorite_post_id
        assert first_favorites.json_body["items"][0]["viewer_state"]["is_favorited"] is True
        assert first_favorites.json_body["has_more"] is True
        next_cursor = first_favorites.json_body["next_cursor"]
        assert next_cursor

        second_favorites = await asgi_request(
            app,
            "GET",
            f"/api/v1/me/favorite-posts?limit=1&cursor={next_cursor}",
            headers=viewer_headers,
        )
        assert second_favorites.status == 200, second_favorites
        assert second_favorites.json_body["items"][0]["post"]["social_post_id"] == oldest_favorite_post_id
        assert second_favorites.json_body["has_more"] is False

        liked_posts = await asgi_request(
            app,
            "GET",
            "/api/v1/me/liked-posts",
            headers=viewer_headers,
        )
        assert liked_posts.status == 200, liked_posts
        assert liked_posts.json_body["collection"] == "likes"
        assert [item["post"]["social_post_id"] for item in liked_posts.json_body["items"]] == [
            liked_post_id
        ]
        assert liked_posts.json_body["items"][0]["viewer_state"]["is_liked"] is True

        unfavorite = await asgi_request(
            app,
            "DELETE",
            f"/api/v1/posts/{newest_favorite_post_id}/favorite",
            headers=viewer_headers,
        )
        assert unfavorite.status == 200, unfavorite

        favorites_after_unfavorite = await asgi_request(
            app,
            "GET",
            "/api/v1/me/favorite-posts",
            headers=viewer_headers,
        )
        assert favorites_after_unfavorite.status == 200, favorites_after_unfavorite
        assert [item["post"]["social_post_id"] for item in favorites_after_unfavorite.json_body["items"]] == [
            oldest_favorite_post_id
        ]

        author_view = await asgi_request(
            app,
            "GET",
            "/api/v1/me/favorite-posts",
            headers=author_headers,
        )
        assert author_view.status == 200, author_view
        assert author_view.json_body["items"] == []

        print("Profile Post Collections API smoke test passed.")


if __name__ == "__main__":
    asyncio.run(main())
