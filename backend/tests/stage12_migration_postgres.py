"""Local isolated-schema proof for a populated PostgreSQL Stage 12 upgrade."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import sys
from urllib.parse import parse_qsl, quote, urlsplit, urlunsplit

ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT_DIR))


def scoped_dsn(source: str, schema: str) -> str:
    parts = urlsplit(source)
    query = [(key, value) for key, value in parse_qsl(parts.query, keep_blank_values=True) if key != "options"]
    query.append(("options", f"-c search_path={schema},pg_catalog"))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "&".join(f"{quote(key)}={quote(value)}" for key, value in query), parts.fragment))


def snapshot(connection, schema: str) -> dict[str, object]:
    tables = ("users", "chat_conversations", "chat_conversation_members", "chat_messages", "chat_message_media", "user_sync_events")
    counts = {table: connection.execute(f'SELECT COUNT(*) FROM "{schema}".{table}').fetchone()[0] for table in tables}
    message = connection.execute(f'SELECT message_id, text_content FROM "{schema}".chat_messages WHERE message_id = %s', ("legacy-msg",)).fetchone()
    return {"counts": counts, "message_id": message[0], "message_hash": hashlib.sha256(message[1].encode()).hexdigest(), "event_id": connection.execute(f'SELECT event_id FROM "{schema}".user_sync_events WHERE user_sync_event_id = %s', ("legacy-event",)).fetchone()[0]}


def main() -> None:
    schema = os.environ["STAGE12_PG_SCHEMA"]
    source = os.environ["TENNIS_DATABASE_URL"]
    import psycopg
    from backend.app.core.postgres_schema import render_postgres_schema
    with psycopg.connect(source, autocommit=True) as connection:
        connection.execute(render_postgres_schema(schema=schema))
        # This is an empty, test-only schema. Removing only newly introduced
        # objects creates a realistic legacy shape without deleting fixture rows.
        connection.execute(f'DROP TABLE "{schema}".chat_message_reactions')
        connection.execute(f'DROP TABLE "{schema}".chat_message_forwards')
        connection.execute(f'ALTER TABLE "{schema}".chat_messages DROP COLUMN edited_at')
        connection.execute(f"DO $$ DECLARE item record; BEGIN FOR item IN SELECT conname FROM pg_constraint WHERE conrelid='\"{schema}\".user_sync_events'::regclass AND contype='c' LOOP EXECUTE format('ALTER TABLE \"{schema}\".user_sync_events DROP CONSTRAINT %I', item.conname); END LOOP; END $$")
        connection.execute(f"ALTER TABLE \"{schema}\".user_sync_events ADD CONSTRAINT legacy_event_type_check CHECK (event_type IN ('message.created','message.recalled','conversation.read'))")
        connection.execute(f"INSERT INTO \"{schema}\".users (user_id, phone, nickname) VALUES ('legacy-u1','13949500001','Legacy One'),('legacy-u2','13949500002','Legacy Two')")
        connection.execute(f"INSERT INTO \"{schema}\".chat_conversations (conversation_id, conversation_type, direct_pair_key, created_by_user_id) VALUES ('legacy-c','direct','legacy-u1:legacy-u2','legacy-u1')")
        connection.execute(f"INSERT INTO \"{schema}\".chat_conversation_members (conversation_member_id,conversation_id,user_id,muted_until,pinned_at) VALUES ('legacy-m1','legacy-c','legacy-u1',NULL,NULL),('legacy-m2','legacy-c','legacy-u2',NULL,NULL)")
        connection.execute(f"INSERT INTO \"{schema}\".chat_messages (message_id,conversation_id,message_seq,sender_user_id,text_content) VALUES ('legacy-msg','legacy-c',1,'legacy-u1','legacy migration payload')")
        connection.execute(f"INSERT INTO \"{schema}\".chat_message_media (media_id,owner_user_id,media_type,storage_key,mime_type,file_size_bytes,width_px,height_px,client_upload_id,expires_at) VALUES ('legacy-media','legacy-u1','image','legacy/opaque','image/jpeg',1,1,1,'legacy-upload','2099-01-01T00:00:00Z')")
        connection.execute(f"INSERT INTO \"{schema}\".user_sync_events (user_sync_event_id,event_id,event_type,aggregate_type,aggregate_id,recipient_user_id,conversation_id,message_id,message_seq,occurred_at,persisted_at,payload_json) VALUES ('legacy-event','legacy-sync','message.created','chat_message','legacy-msg','legacy-u2','legacy-c','legacy-msg',1,'2026-01-01T00:00:00Z','2026-01-01T00:00:00Z','{{}}')")
        before = snapshot(connection, schema)
        connection.execute(render_postgres_schema(schema=schema))
        after_first = snapshot(connection, schema)
        connection.execute(render_postgres_schema(schema=schema))
        after_second = snapshot(connection, schema)
        assert before == after_first == after_second
        assert connection.execute(f"SELECT 1 FROM information_schema.columns WHERE table_schema=%s AND table_name='chat_messages' AND column_name='edited_at'", (schema,)).fetchone()
        assert connection.execute(f"SELECT 1 FROM pg_indexes WHERE schemaname=%s AND indexname='idx_chat_message_reactions_message'", (schema,)).fetchone()
        assert connection.execute(f"SELECT 1 FROM pg_constraint WHERE connamespace=%s::regnamespace AND conname='user_sync_events_stage12_event_type_check'", (schema,)).fetchone()
    print("Stage 12 PostgreSQL legacy upgrade migration test passed.")


if __name__ == "__main__": main()
