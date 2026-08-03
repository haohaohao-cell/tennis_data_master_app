from __future__ import annotations

from datetime import UTC, datetime, timedelta
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from backend.app.core.database import initialize_database, transaction


DEMO_USERS = (
    ("demo-feed-alice", "演示球员 A"),
    ("demo-feed-bob", "演示球员 B"),
    ("demo-feed-carol", "演示球员 C"),
)


def timestamp(minutes_ago: int) -> str:
    value = datetime.now(UTC) - timedelta(minutes=minutes_ago)
    return value.isoformat(timespec="seconds").replace("+00:00", "Z")


def seed() -> None:
    initialize_database()
    with transaction() as connection:
        for user_id, nickname in DEMO_USERS:
            connection.execute(
                """
                INSERT OR IGNORE INTO users (
                    user_id, nickname, status, playing_hand
                )
                VALUES (?, ?, 'active', 'right');
                """,
                (user_id, nickname),
            )

        connection.execute(
            """
            INSERT OR IGNORE INTO user_follows (
                follow_id, follower_user_id, following_user_id, status, source
            )
            VALUES ('demo-feed-follow', 'demo-feed-alice', 'demo-feed-bob', 'active', 'demo_seed');
            """
        )

        posts = (
            (
                "demo-feed-post-serve",
                "demo-feed-bob",
                "发球节奏记录",
                "今天把抛球高度和击球点重新对齐了。",
                "none",
                None,
                None,
                3,
            ),
            (
                "demo-feed-post-rally",
                "demo-feed-carol",
                "底线相持练习",
                "最后三拍的重心转移比上周稳定。",
                "none",
                None,
                None,
                12,
            ),
            (
                "demo-feed-post-nearby",
                "demo-feed-bob",
                "北京周末约球",
                "周六下午想在朝阳附近找球友练习。",
                "city",
                "北京",
                "北京",
                22,
            ),
            (
                "demo-feed-post-followers",
                "demo-feed-bob",
                "只给关注球友看的训练笔记",
                "把二发落点控制在反手位，下一次继续验证。",
                "region",
                "北京",
                None,
                34,
            ),
        )
        for post_id, author_id, title, content, scope, region, city, minutes_ago in posts:
            created_at = timestamp(minutes_ago)
            connection.execute(
                """
                INSERT OR IGNORE INTO social_posts (
                    social_post_id,
                    author_user_id,
                    title,
                    content,
                    visibility,
                    status,
                    review_status,
                    location_scope,
                    location_region,
                    location_city,
                    published_at,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, 'published', 'approved', ?, ?, ?, ?, ?, ?);
                """,
                (
                    post_id,
                    author_id,
                    title,
                    content,
                    "followers" if post_id.endswith("followers") else "public",
                    scope,
                    region,
                    city,
                    created_at,
                    created_at,
                    created_at,
                ),
            )
            connection.execute(
                """
                INSERT OR IGNORE INTO social_post_stats (
                    social_post_id, like_count, comment_count, favorite_count, share_count
                )
                VALUES (?, 0, 0, 0, 0);
                """,
                (post_id,),
            )

    print("Post feed demo data seeded.")
    print("Recommended: public demo Posts are available without login.")
    print("Nearby: query city=北京 and region=北京.")
    print("Following: login as a user that follows demo-feed-bob.")


if __name__ == "__main__":
    seed()
