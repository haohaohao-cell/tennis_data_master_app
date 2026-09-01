"""Isolated Stage 14A authorized message/object/media search coverage."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
import sys
import tempfile
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit

ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT_DIR))

from backend.tests.activity_detail_api_smoke import login_phone
from backend.tests.auth_api_smoke import asgi_request


async def request(app, method: str, path: str, headers: dict[str, str], body: dict | None = None):
    return await asgi_request(app, method, path, body, headers=headers)


async def search(app, headers: dict[str, str], conversation_id: str, **params):
    return await request(app, "GET", f"/api/v1/messages/conversations/{conversation_id}/messages/search?{urlencode(params)}", headers)


async def send(app, headers: dict[str, str], conversation_id: str, text: str, client_id: str, **extra) -> dict:
    response = await request(app, "POST", f"/api/v1/messages/conversations/{conversation_id}/messages", headers, {
        "message_type": "text", "text_content": text, "client_message_id": client_id, **extra,
    })
    assert response.status == 201, response
    return response.json_body["message"]


async def main() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        postgres_schema = os.environ.get("STAGE14A_POSTGRES_SCHEMA")
        if postgres_schema:
            source_dsn = os.environ["TENNIS_DATABASE_URL"]
            parts = urlsplit(source_dsn)
            query = [(key, value) for key, value in parse_qsl(parts.query, keep_blank_values=True) if key != "options"]
            query.append(("options", f"-c search_path={postgres_schema},pg_catalog"))
            scoped_dsn = urlunsplit((parts.scheme, parts.netloc, parts.path, "&".join(f"{quote(key)}={quote(value)}" for key, value in query), parts.fragment))
            os.environ["TENNIS_DATABASE_URL"] = scoped_dsn
            os.environ["TENNIS_POSTGRES_DSN"] = scoped_dsn
        else:
            os.environ["TENNIS_DB_PATH"] = str(Path(temp_dir) / "stage14a.sqlite3")
            os.environ.pop("TENNIS_DATABASE_URL", None)
            os.environ.pop("TENNIS_POSTGRES_DSN", None)
        from backend.app.core.database import get_connection, initialize_database, initialize_sqlite_database, transaction
        from backend.app.core import config
        from backend.app.main import app

        if postgres_schema:
            object.__setattr__(config.settings, "database_url", os.environ["TENNIS_DATABASE_URL"])
        (initialize_database if postgres_schema else initialize_sqlite_database)()
        (alice_token, alice_id), (bob_token, bob_id), (carol_token, carol_id) = [
            await login_phone(app, phone) for phone in ("13955000001", "13955000002", "13955000003")
        ]
        alice, bob, carol = ({"authorization": f"Bearer {token}"} for token in (alice_token, bob_token, carol_token))
        created = await request(app, "POST", "/api/v1/messages/groups", alice, {"title": "Stage 14A", "member_user_ids": [bob_id]})
        assert created.status == 201
        conversation_id = created.json_body["conversation"]["conversation_id"]

        with transaction() as connection:
            connection.execute("INSERT INTO tennis_activities (tennis_activity_id, owner_user_id, title, activity_type, default_visibility) VALUES ('stage14a-activity', ?, 'Search activity', 'serve_training', 'public');", (alice_id,))

        alpha = await send(app, alice, conversation_id, "Serve plan alpha", "stage14a-alpha")
        beta = await send(app, bob, conversation_id, "Serve plan beta", "stage14a-beta")
        activity = await send(app, alice, conversation_id, "Activity reference", "stage14a-activity", target_object_type="tennis_activity", target_object_id="stage14a-activity")
        media = await send(app, alice, conversation_id, "media placeholder", "stage14a-media")
        revoked = await send(app, alice, conversation_id, "revoked private search text", "stage14a-revoked")
        with transaction() as connection:
            connection.execute("UPDATE chat_messages SET status = 'revoked' WHERE message_id = ?;", (revoked["message_id"],))
            connection.execute("UPDATE chat_messages SET message_type = 'image' WHERE message_id = ?;", (media["message_id"],))
            connection.execute("INSERT INTO chat_message_media (media_id, owner_user_id, message_id, media_type, upload_status, storage_key, mime_type, file_size_bytes, width_px, height_px, client_upload_id, expires_at) VALUES ('stage14a-media', ?, ?, 'image', 'attached', 'private/search-key.jpg', 'image/jpeg', 12, 2, 2, 'stage14a-media-upload', '2099-01-01T00:00:00Z');", (alice_id, media["message_id"]))
            connection.execute("INSERT INTO chat_message_attachments (attachment_id, message_id, attachment_type, media_id, mime_type, file_size_bytes, width_px, height_px) VALUES ('stage14a-media-attachment', ?, 'image', 'stage14a-media', 'image/jpeg', 12, 2, 2);", (media["message_id"],))

        text = await search(app, bob, conversation_id, q="serve plan", page_size=1)
        assert text.status == 200 and text.json_body["items"][0]["message_id"] == beta["message_id"], text
        assert text.json_body["items"][0]["match_kind"] == "text" and text.json_body["next_cursor"]
        next_page = await search(app, bob, conversation_id, q="serve plan", page_size=1, cursor=text.json_body["next_cursor"])
        assert next_page.status == 200 and next_page.json_body["items"][0]["message_id"] == alpha["message_id"]
        tampered = await search(app, bob, conversation_id, q="different", cursor=text.json_body["next_cursor"])
        assert tampered.status == 400 and tampered.json_body["detail"]["code"] == "MESSAGE_SEARCH_CURSOR_INVALID"
        assert (await search(app, bob, conversation_id, q="", sender_user_id=alice_id)).status == 200
        assert (await search(app, bob, conversation_id, q="", object_type="tennis_activity", object_id="stage14a-activity")).json_body["items"][0]["business_object_card"]["title"] == "Search activity"
        media_result = await search(app, bob, conversation_id, q="", has_media="true")
        assert media_result.status == 200 and media_result.json_body["items"][0]["message_id"] == media["message_id"]
        assert media_result.json_body["items"][0]["media_summary"]["media_types"] == ["image"]
        assert "private/search-key.jpg" not in str(media_result.json_body)
        assert (await search(app, bob, conversation_id, q="", message_type="image")).json_body["items"][0]["message_id"] == media["message_id"]
        assert (await search(app, bob, conversation_id, q="revoked private search text")).json_body["items"] == []
        assert (await search(app, carol, conversation_id, q="serve")).status in {403, 404}
        assert (await search(app, bob, conversation_id, q="", object_id="missing")).status == 400
        assert (await search(app, bob, conversation_id, q="", sent_after="2099-01-01", sent_before="2000-01-01")).status == 400
        with get_connection() as connection:
            sync_count = connection.execute("SELECT COUNT(*) AS count FROM user_sync_events;").fetchone()["count"]
            assert sync_count > 0
        assert postgres_schema or Path(os.environ["TENNIS_DB_PATH"]).exists()
        print("Stage 14A search API test passed.")


if __name__ == "__main__":
    asyncio.run(main())
