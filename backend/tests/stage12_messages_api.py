"""Isolated Stage 12 SQLite regression for mutations, reactions, forward, and groups."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
import sys
import tempfile
from urllib.parse import parse_qsl, quote, urlsplit, urlunsplit

ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT_DIR))

from backend.tests.activity_detail_api_smoke import login_phone
from backend.tests.auth_api_smoke import asgi_request


async def request(app, method: str, path: str, headers: dict[str, str], body: dict | None = None):
    return await asgi_request(app, method, path, body, headers=headers)


async def main() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        postgres_schema = os.environ.get("STAGE12_POSTGRES_SCHEMA")
        database_path = Path(temp_dir) / "stage12_messages.sqlite3"
        if postgres_schema:
            source_dsn = os.environ["TENNIS_DATABASE_URL"]
            parts = urlsplit(source_dsn)
            query = [(key, value) for key, value in parse_qsl(parts.query, keep_blank_values=True) if key != "options"]
            query.append(("options", f"-c search_path={postgres_schema},pg_catalog"))
            scoped_dsn = urlunsplit((parts.scheme, parts.netloc, parts.path, "&".join(f"{quote(key)}={quote(value)}" for key, value in query), parts.fragment))
            os.environ["TENNIS_DATABASE_URL"] = scoped_dsn
            os.environ["TENNIS_POSTGRES_DSN"] = scoped_dsn
        else:
            os.environ["TENNIS_DB_PATH"] = str(database_path)
            os.environ.pop("TENNIS_DATABASE_URL", None)
            os.environ.pop("TENNIS_POSTGRES_DSN", None)
        if postgres_schema:
            from backend.app.core import config
            object.__setattr__(config.settings, "database_url", os.environ["TENNIS_DATABASE_URL"])
        from backend.app.core.database import get_connection, initialize_database
        from backend.app.main import app

        initialize_database()
        accounts = [await login_phone(app, phone) for phone in ("13948000001", "13948000002", "13948000003", "13948000004")]
        (alice_token, alice_id), (bob_token, bob_id), (carol_token, carol_id), (dave_token, dave_id) = accounts
        alice, bob, carol, dave = ({"authorization": f"Bearer {token}"} for token, _ in accounts)

        source_group = await request(app, "POST", "/api/v1/messages/groups", alice, {"title": "Stage 12 source", "member_user_ids": [bob_id]})
        assert source_group.status == 201, source_group
        source_group_id = source_group.json_body["conversation"]["conversation_id"]
        group = await request(app, "POST", "/api/v1/messages/groups", alice, {"title": "Stage 12", "member_user_ids": [bob_id]})
        assert group.status == 201, group
        group_id = group.json_body["conversation"]["conversation_id"]

        created = await request(app, "POST", f"/api/v1/messages/conversations/{source_group_id}/messages", alice, {"message_type": "text", "text_content": "original plan", "client_message_id": "stage12-original"})
        assert created.status == 201, created
        message_id = created.json_body["message"]["message_id"]

        edited = await request(app, "PATCH", f"/api/v1/messages/conversations/{source_group_id}/messages/{message_id}", alice, {"text_content": "edited plan"})
        assert edited.status == 200 and edited.json_body["message"]["text_content"] == "edited plan" and edited.json_body["event_id"]
        assert (await request(app, "PATCH", f"/api/v1/messages/conversations/{source_group_id}/messages/{message_id}", bob, {"text_content": "nope"})).status == 403
        unchanged = await request(app, "PATCH", f"/api/v1/messages/conversations/{source_group_id}/messages/{message_id}", alice, {"text_content": "edited plan"})
        assert unchanged.status == 200 and unchanged.json_body["event_id"] is None

        first_reaction = await request(app, "PATCH", f"/api/v1/messages/conversations/{source_group_id}/messages/{message_id}/reaction", bob, {"reaction_type": "like"})
        repeated_reaction = await request(app, "PATCH", f"/api/v1/messages/conversations/{source_group_id}/messages/{message_id}/reaction", bob, {"reaction_type": "like"})
        changed_reaction = await request(app, "PATCH", f"/api/v1/messages/conversations/{source_group_id}/messages/{message_id}/reaction", alice, {"reaction_type": "heart"})
        assert first_reaction.status == repeated_reaction.status == changed_reaction.status == 200
        assert first_reaction.json_body["event_id"] and repeated_reaction.json_body["event_id"] is None
        summaries = {item["reaction_type"]: item for item in changed_reaction.json_body["message"]["reactions"]}
        assert summaries["like"]["count"] == summaries["heart"]["count"] == 1
        removed = await request(app, "DELETE", f"/api/v1/messages/conversations/{source_group_id}/messages/{message_id}/reaction", bob)
        removed_twice = await request(app, "DELETE", f"/api/v1/messages/conversations/{source_group_id}/messages/{message_id}/reaction", bob)
        assert removed.status == removed_twice.status == 200 and removed.json_body["event_id"] and removed_twice.json_body["event_id"] is None
        assert (await request(app, "PATCH", f"/api/v1/messages/conversations/{source_group_id}/messages/{message_id}/reaction", carol, {"reaction_type": "x"})).status == 403

        forwarded = await request(app, "POST", f"/api/v1/messages/conversations/{source_group_id}/messages/{message_id}/forward", alice, {"target_conversation_ids": [group_id], "client_forward_id": "stage12-forward"})
        assert forwarded.status == 200 and len(forwarded.json_body["items"]) == 1 and len(forwarded.json_body["event_ids"]) == 2
        forward_retry = await request(app, "POST", f"/api/v1/messages/conversations/{source_group_id}/messages/{message_id}/forward", alice, {"target_conversation_ids": [group_id], "client_forward_id": "stage12-forward"})
        assert forward_retry.status == 200 and forward_retry.json_body["items"][0]["message"]["message_id"] == forwarded.json_body["items"][0]["message"]["message_id"]
        before_invalid = (await request(app, "GET", f"/api/v1/messages/conversations/{group_id}/messages", alice)).json_body["items"]
        invalid_forward = await request(app, "POST", f"/api/v1/messages/conversations/{source_group_id}/messages/{message_id}/forward", alice, {"target_conversation_ids": [group_id, "missing"], "client_forward_id": "stage12-forward-invalid"})
        after_invalid = (await request(app, "GET", f"/api/v1/messages/conversations/{group_id}/messages", alice)).json_body["items"]
        assert invalid_forward.status == 404 and len(after_invalid) == len(before_invalid)
        assert (await request(app, "POST", f"/api/v1/messages/conversations/{source_group_id}/messages/{message_id}/forward", bob, {"target_conversation_ids": [group_id], "client_forward_id": "stage12-denied"})).status == 403

        added = await request(app, "POST", f"/api/v1/messages/conversations/{group_id}/members", alice, {"user_id": carol_id})
        assert added.status == 200 and added.json_body["member"]["status"] == "active" and added.json_body["event_id"]
        assert (await request(app, "POST", f"/api/v1/messages/conversations/{group_id}/members", bob, {"user_id": dave_id})).status == 403
        promoted = await request(app, "PATCH", f"/api/v1/messages/conversations/{group_id}/members/{bob_id}/role", alice, {"member_role": "admin"})
        assert promoted.status == 200 and promoted.json_body["member"]["member_role"] == "admin"
        added_by_admin = await request(app, "POST", f"/api/v1/messages/conversations/{group_id}/members", bob, {"user_id": dave_id})
        assert added_by_admin.status == 200
        removed_member = await request(app, "DELETE", f"/api/v1/messages/conversations/{group_id}/members/{carol_id}", bob)
        assert removed_member.status == 200 and removed_member.json_body["member"]["status"] == "removed"
        assert (await request(app, "GET", f"/api/v1/messages/conversations/{group_id}/messages", carol)).status == 403
        left = await request(app, "POST", f"/api/v1/messages/conversations/{group_id}/leave", dave)
        owner_leave = await request(app, "POST", f"/api/v1/messages/conversations/{group_id}/leave", alice)
        assert left.status == 200 and left.json_body["member"]["status"] == "left"
        assert owner_leave.status == 409 and owner_leave.json_body["detail"]["code"] == "GROUP_OWNER_TRANSFER_REQUIRED"

        with get_connection() as connection:
            event_types = {row[0] for row in connection.execute("SELECT event_type FROM user_sync_events WHERE conversation_id = ?;", (group_id,)).fetchall()}
            assert {"message.created", "message.forwarded", "conversation.members_changed"}.issubset(event_types)
            assert postgres_schema or database_path.exists()
        print("Stage 12 message API test passed.")


if __name__ == "__main__":
    asyncio.run(main())
