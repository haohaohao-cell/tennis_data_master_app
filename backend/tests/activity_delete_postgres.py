"""Isolated PostgreSQL regression for the owned Activity soft-delete contract."""

from __future__ import annotations

import os
from pathlib import Path
import sys
import uuid
from urllib.parse import parse_qsl, quote, urlsplit, urlunsplit

ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT_DIR))


def main() -> None:
    schema = os.environ.get("STAGE11H2_SCHEMA")
    source = os.environ.get("TENNIS_DATABASE_URL")
    if not schema or not source:
        raise SystemExit("STAGE11H2_SCHEMA and TENNIS_DATABASE_URL are required")
    parts = urlsplit(source)
    query = [(key, value) for key, value in parse_qsl(parts.query, keep_blank_values=True) if key != "options"]
    query.append(("options", f"-c search_path={schema},pg_catalog"))
    scoped = urlunsplit((parts.scheme, parts.netloc, parts.path, "&".join(f"{quote(key)}={quote(value)}" for key, value in query), parts.fragment))
    from backend.app.core import config

    object.__setattr__(config.settings, "database_url", scoped)
    from fastapi import HTTPException
    from backend.app.core.database import get_connection, transaction
    from backend.app.uploads import service

    suffix = uuid.uuid4().hex[:10]
    owner_id, other_id = f"activity-owner-{suffix}", f"activity-other-{suffix}"
    activity_id, post_id = str(uuid.uuid4()), str(uuid.uuid4())
    with transaction() as connection:
        for user_id, phone in ((owner_id, f"138{suffix[:8]}"), (other_id, f"137{suffix[:8]}")):
            connection.execute("INSERT INTO users (user_id, phone, nickname) VALUES (?, ?, ?);", (user_id, phone, user_id))
        connection.execute(
            "INSERT INTO tennis_activities (tennis_activity_id, owner_user_id, activity_type, default_visibility) VALUES (?, ?, 'casual_hit', 'private');",
            (activity_id, owner_id),
        )
        connection.execute(
            "INSERT INTO social_posts (social_post_id, author_user_id, source_tennis_activity_id, status, visibility) VALUES (?, ?, ?, 'draft', 'private');",
            (post_id, owner_id, activity_id),
        )
    try:
        service.delete_activity(other_id, activity_id)
    except HTTPException as error:
        assert error.status_code == 404 and error.detail["code"] == "TENNIS_ACTIVITY_NOT_FOUND"
    else:
        raise AssertionError("cross-user deletion unexpectedly succeeded")
    deleted = service.delete_activity(owner_id, activity_id)
    assert deleted.success and deleted.deleted_at
    try:
        service.delete_activity(owner_id, activity_id)
    except HTTPException as error:
        assert error.status_code == 404 and error.detail["code"] == "TENNIS_ACTIVITY_NOT_FOUND"
    else:
        raise AssertionError("repeat deletion unexpectedly succeeded")
    with get_connection() as connection:
        activity = connection.execute("SELECT deleted_at FROM tennis_activities WHERE tennis_activity_id = ?;", (activity_id,)).fetchone()
        post = connection.execute("SELECT source_tennis_activity_id FROM social_posts WHERE social_post_id = ?;", (post_id,)).fetchone()
    assert activity["deleted_at"] is not None and post["source_tennis_activity_id"] is None
    print("User Activity deletion PostgreSQL isolated-schema test passed.")


if __name__ == "__main__":
    main()
