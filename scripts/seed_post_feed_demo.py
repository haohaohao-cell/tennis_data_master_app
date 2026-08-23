from __future__ import annotations

from datetime import UTC, datetime, timedelta
import hashlib
from pathlib import Path
import shutil
import sys


ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from backend.app.core.database import initialize_database, transaction


DEMO_VIDEO_SOURCE = ROOT_DIR / "cv" / "data" / "samples" / "input" / "long5.mp4"
DEMO_VIDEO_STORAGE = ROOT_DIR / "backend" / "storage" / "videos"
DEMO_VIDEOS = {
    "demo-feed-post-serve": (
        "demo-feed-serve.mp4",
        "/storage/videos/demo-feed-serve.mp4",
    ),
    "demo-feed-post-rally": (
        "demo-feed-rally.mp4",
        "/storage/videos/demo-feed-rally.mp4",
    ),
    "demo-feed-post-nearby": (
        "demo-feed-nearby.mp4",
        "/storage/videos/demo-feed-nearby.mp4",
    ),
}
DEMO_THUMBNAILS = {
    "demo-feed-post-serve": (
        ROOT_DIR / "app" / "assets" / "images" / "content" / "serve-session.png",
        "/storage/videos/demo-feed-serve.png",
    ),
    "demo-feed-post-rally": (
        ROOT_DIR / "app" / "assets" / "images" / "content" / "court-practice.png",
        "/storage/videos/demo-feed-rally.png",
    ),
    "demo-feed-post-nearby": (
        ROOT_DIR / "app" / "assets" / "images" / "content" / "match-evening.png",
        "/storage/videos/demo-feed-nearby.png",
    ),
}

DEMO_USERS = (
    ("demo-feed-alice", "演示球员 A"),
    ("demo-feed-bob", "演示球员 B"),
    ("demo-feed-carol", "演示球员 C"),
)


def timestamp(minutes_ago: int) -> str:
    value = datetime.now(UTC) - timedelta(minutes=minutes_ago)
    return value.isoformat(timespec="seconds").replace("+00:00", "Z")


def prepare_demo_media() -> tuple[int, str]:
    if not DEMO_VIDEO_SOURCE.is_file():
        raise FileNotFoundError(f"Demo video not found: {DEMO_VIDEO_SOURCE}")

    DEMO_VIDEO_STORAGE.mkdir(parents=True, exist_ok=True)
    for filename, _ in DEMO_VIDEOS.values():
        video_target = DEMO_VIDEO_STORAGE / filename
        if not video_target.exists() or video_target.stat().st_size != DEMO_VIDEO_SOURCE.stat().st_size:
            shutil.copy2(DEMO_VIDEO_SOURCE, video_target)

    for source, public_path in DEMO_THUMBNAILS.values():
        if not source.is_file():
            raise FileNotFoundError(f"Demo thumbnail not found: {source}")
        target = DEMO_VIDEO_STORAGE / Path(public_path).name
        if not target.exists() or target.stat().st_size != source.stat().st_size:
            shutil.copy2(source, target)

    file_hash = hashlib.sha256(DEMO_VIDEO_SOURCE.read_bytes()).hexdigest()
    return DEMO_VIDEO_SOURCE.stat().st_size, file_hash


def seed() -> None:
    initialize_database()
    video_size_bytes, video_hash = prepare_demo_media()
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
            thumbnail_source = DEMO_THUMBNAILS.get(post_id)
            video_source = DEMO_VIDEOS.get(post_id)
            if thumbnail_source is None or video_source is None:
                continue
            thumbnail_path = thumbnail_source[1]
            video_filename, video_path = video_source
            connection.execute(
                """
                INSERT OR IGNORE INTO videos (
                    video_id,
                    owner_user_id,
                    uploader_user_id,
                    filename,
                    original_filename,
                    video_path,
                    thumbnail_path,
                    mime_type,
                    file_size_bytes,
                    file_hash,
                    video_duration_ms,
                    video_width_px,
                    video_height_px,
                    visibility,
                    upload_status,
                    uploaded_at,
                    analysis_status
                )
                VALUES (
                    ?, ?, ?, ?, ?, ?, ?, 'video/mp4', ?, ?, 60000, 1280, 720,
                    'public', 'uploaded', ?, 'uploaded'
                );
                """,
                (
                    f"{post_id}-video",
                    author_id,
                    author_id,
                    video_filename,
                    video_filename,
                    video_path,
                    thumbnail_path,
                    video_size_bytes,
                    video_hash,
                    timestamp(minutes_ago),
                ),
            )
            connection.execute(
                """
                INSERT OR IGNORE INTO post_media (
                    post_media_id,
                    social_post_id,
                    media_type,
                    video_id,
                    sort_order,
                    caption
                )
                VALUES (?, ?, 'video', ?, 0, ?);
                """,
                (
                    f"{post_id}-media",
                    post_id,
                    f"{post_id}-video",
                    title,
                ),
            )

    print("Post feed demo data seeded.")
    print("Recommended: public demo Posts are available without login.")
    print("Nearby: query city=北京 and region=北京.")
    print("Following: login as a user that follows demo-feed-bob.")
    print(f"Demo videos copied to: {DEMO_VIDEO_STORAGE}")


if __name__ == "__main__":
    seed()
