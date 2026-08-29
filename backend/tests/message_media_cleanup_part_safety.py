"""Regression: cleanup must not remove an old partial for a live upload."""

from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile
from datetime import datetime, timedelta, timezone

ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT_DIR))


def main() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        os.environ["TENNIS_DB_PATH"] = str(root / "media-cleanup.sqlite3")
        os.environ["TENNIS_MESSAGE_MEDIA_STORAGE_DIR"] = str(root / "media")
        os.environ.pop("TENNIS_DATABASE_URL", None)
        os.environ.pop("TENNIS_POSTGRES_DSN", None)
        from backend.app.core.database import get_connection, initialize_database
        from backend.app.messages.media_cleanup import cleanup_message_media

        initialize_database()
        media_id = "cleanup-live-upload"
        with get_connection() as connection:
            connection.execute("INSERT INTO users(user_id, phone, nickname) VALUES (?, ?, ?)", ("cleanup-user", "13911110000", "cleanup"))
            connection.execute(
                """INSERT INTO chat_message_media
                   (media_id, owner_user_id, media_type, upload_status, storage_key, mime_type,
                    file_size_bytes, width_px, height_px, client_upload_id, expires_at)
                   VALUES (?, ?, 'image', 'uploading', ?, 'image/jpeg', 1, 1, 1, ?, ?)""",
                (media_id, "cleanup-user", f"images/{media_id}/original.jpg", "cleanup-client", "2099-01-01T00:00:00Z"),
            )
            connection.commit()
        partial = root / "media" / "images" / media_id / "original.jpg.test.part"
        partial.parent.mkdir(parents=True)
        partial.write_bytes(b"partial")
        old = (datetime.now(timezone.utc) - timedelta(days=2)).timestamp()
        os.utime(partial, (old, old))
        report = cleanup_message_media(dry_run=False, grace_hours=1)
        assert partial.is_file(), report
        assert partial.relative_to(root / "media").as_posix() not in report["temporary_files"], report
        print("Message media cleanup partial safety test passed.")


if __name__ == "__main__":
    main()
