from __future__ import annotations

import os
from pathlib import Path
import sqlite3
import sys
import tempfile


ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT_DIR))


OLD_SOURCE_ENUM = "'device_gps', 'network_estimate', 'manual_legacy', 'unavailable'"
NEW_SOURCE_ENUM = "'device_gps', 'video_metadata', 'manual_legacy', 'unavailable'"
STALE_BACKUP_TABLE = "tennis_activities_old_location_source"


def _inject_stale_tennis_activity_fk_references(connection: sqlite3.Connection) -> None:
    schema_version = connection.execute("PRAGMA schema_version;").fetchone()[0]
    connection.execute("PRAGMA writable_schema = ON;")
    try:
        connection.execute(
            """
            UPDATE sqlite_schema
            SET sql = replace(
                sql,
                'REFERENCES tennis_activities',
                'REFERENCES "tennis_activities_old_location_source"'
            )
            WHERE type = 'table'
              AND name IN ('videos', 'social_posts');
            """
        )
        connection.execute(f"PRAGMA schema_version = {int(schema_version) + 1};")
    finally:
        connection.execute("PRAGMA writable_schema = OFF;")


def main() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        db_path = Path(temp_dir) / "old_location_source.sqlite3"
        schema_sql = (ROOT_DIR / "backend" / "db" / "schema.sql").read_text(encoding="utf-8")
        old_schema_sql = schema_sql.replace(NEW_SOURCE_ENUM, OLD_SOURCE_ENUM)

        connection = sqlite3.connect(db_path)
        connection.executescript(old_schema_sql)
        connection.execute("INSERT INTO users (user_id, nickname) VALUES (?, ?)", ("u1", "Test"))
        connection.execute(
            """
            INSERT INTO tennis_activities (
                tennis_activity_id,
                owner_user_id,
                activity_type,
                default_visibility,
                location_source
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            ("old1", "u1", "other", "private", "unavailable"),
        )
        connection.execute(
            """
            INSERT INTO tennis_activities (
                tennis_activity_id,
                owner_user_id,
                activity_type,
                default_visibility,
                location_source,
                location_latitude,
                location_longitude,
                location_accuracy_m,
                location_city,
                location_district,
                location_coordinate_system
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("old_network", "u1", "other", "private", "network_estimate", 16.8, 112.3, 20000, "三沙市", "西沙区", "wgs84"),
        )
        connection.execute(
            """
            INSERT INTO videos (
                video_id,
                tennis_activity_id,
                owner_user_id,
                uploader_user_id,
                filename,
                video_path
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("activity_video", "old1", "u1", "u1", "activity_video.mp4", "/storage/videos/activity_video.mp4"),
        )
        connection.execute(
            """
            INSERT INTO social_posts (
                social_post_id,
                author_user_id,
                source_tennis_activity_id
            )
            VALUES (?, ?, ?)
            """,
            ("source_post", "u1", "old1"),
        )
        _inject_stale_tennis_activity_fk_references(connection)
        connection.commit()
        connection.close()

        os.environ["TENNIS_DB_PATH"] = str(db_path)

        from backend.app.core.database import initialize_database

        initialize_database()

        connection = sqlite3.connect(db_path)
        connection.execute("PRAGMA foreign_keys = ON;")
        connection.execute(
            """
            INSERT INTO tennis_activities (
                tennis_activity_id,
                owner_user_id,
                activity_type,
                default_visibility,
                location_source,
                location_latitude,
                location_longitude,
                location_accuracy_m,
                location_coordinate_system
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("new1", "u1", "other", "private", "video_metadata", 31.2, 121.4, 20000, "wgs84"),
        )
        try:
            connection.execute(
                """
                INSERT INTO tennis_activities (
                    tennis_activity_id,
                    owner_user_id,
                    activity_type,
                    default_visibility,
                    location_source
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                ("new_network", "u1", "other", "private", "network_estimate"),
            )
        except sqlite3.IntegrityError:
            pass
        else:
            raise AssertionError("network_estimate should be rejected after migration.")
        stale_ref_count = connection.execute(
            """
            SELECT count(*)
            FROM sqlite_schema
            WHERE sql LIKE ?;
            """,
            (f"%{STALE_BACKUP_TABLE}%",),
        ).fetchone()[0]
        video_activity_fk = [
            row
            for row in connection.execute("PRAGMA foreign_key_list(videos)").fetchall()
            if row[3] == "tennis_activity_id"
        ]
        post_activity_fk = [
            row
            for row in connection.execute("PRAGMA foreign_key_list(social_posts)").fetchall()
            if row[3] == "source_tennis_activity_id"
        ]
        connection.execute(
            """
            INSERT INTO social_posts (
                social_post_id,
                author_user_id,
                visibility,
                status
            )
            VALUES (?, ?, ?, ?)
            """,
            ("post_upload_intent", "u1", "public", "draft"),
        )
        connection.execute(
            """
            INSERT INTO videos (
                video_id,
                tennis_activity_id,
                owner_user_id,
                uploader_user_id,
                filename,
                video_path,
                visibility,
                upload_status,
                analysis_status
            )
            VALUES (?, NULL, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "post_upload_video",
                "u1",
                "u1",
                "post_upload_video.mp4",
                "/storage/videos/posts/post_upload_video.mp4",
                "private",
                "pending",
                "uploaded",
            ),
        )
        connection.execute(
            """
            INSERT INTO post_media (
                post_media_id,
                social_post_id,
                media_type,
                video_id,
                sort_order
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            ("post_upload_media", "post_upload_intent", "video", "post_upload_video", 0),
        )
        connection.commit()
        count = connection.execute("SELECT count(*) FROM tennis_activities").fetchone()[0]
        migrated_network = connection.execute(
            """
            SELECT location_source, location_latitude, location_longitude, location_city, location_district
            FROM tennis_activities
            WHERE tennis_activity_id = ?
            """,
            ("old_network",),
        ).fetchone()
        foreign_key_issues = connection.execute("PRAGMA foreign_key_check;").fetchall()
        connection.close()

        assert count == 3
        assert migrated_network == ("unavailable", None, None, None, None)
        assert stale_ref_count == 0
        assert video_activity_fk and video_activity_fk[0][2] == "tennis_activities"
        assert post_activity_fk and post_activity_fk[0][2] == "tennis_activities"
        assert not foreign_key_issues
        print("Activity location source migration smoke test passed.")


if __name__ == "__main__":
    main()
