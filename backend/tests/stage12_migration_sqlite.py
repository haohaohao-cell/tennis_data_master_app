"""Upgrade a legacy-shaped SQLite message store without losing existing rows."""
from __future__ import annotations
import os
from pathlib import Path
import sys
import tempfile

ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT_DIR))


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="stage12-migrate-") as directory:
        os.environ.pop("TENNIS_DATABASE_URL", None)
        os.environ.pop("TENNIS_POSTGRES_DSN", None)
        os.environ["TENNIS_DB_PATH"] = str(Path(directory) / "legacy.sqlite3")
        from backend.app.core.database import get_connection, initialize_sqlite_database, transaction, _run_stage12_message_migrations
        initialize_sqlite_database()
        with transaction() as connection:
            connection.execute("INSERT INTO users (user_id, phone, nickname) VALUES ('u1','13949000001','Legacy');")
            connection.execute("INSERT INTO chat_conversations (conversation_id, conversation_type, direct_pair_key, created_by_user_id) VALUES ('c1','direct','u1:u1','u1');")
            connection.execute("INSERT INTO chat_conversation_members (conversation_member_id, conversation_id, user_id) VALUES ('m1','c1','u1');")
            connection.execute("INSERT INTO chat_messages (message_id, conversation_id, message_seq, sender_user_id, text_content) VALUES ('msg1','c1',1,'u1','preserve me');")
            connection.execute("INSERT INTO user_sync_events (user_sync_event_id,event_id,event_type,aggregate_type,aggregate_id,recipient_user_id,conversation_id,message_id,message_seq,occurred_at,persisted_at,payload_json) VALUES ('se1','e1','message.created','chat_message','msg1','u1','c1','msg1',1,'x','x','{}');")
            connection.execute("DROP TABLE chat_message_reactions;")
            connection.execute("DROP TABLE chat_message_forwards;")
            connection.execute("ALTER TABLE user_sync_events RENAME TO user_sync_events_legacy;")
            connection.execute("CREATE TABLE user_sync_events AS SELECT * FROM user_sync_events_legacy;")
            connection.execute("DROP TABLE user_sync_events_legacy;")
            # Remove the Stage 12 column to emulate the older message table.
            connection.execute("ALTER TABLE chat_messages RENAME COLUMN edited_at TO legacy_edited_at;")
        with transaction() as connection:
            _run_stage12_message_migrations(connection)
        with get_connection() as connection:
            assert connection.execute("SELECT text_content FROM chat_messages WHERE message_id='msg1';").fetchone()[0] == "preserve me"
            assert connection.execute("SELECT event_id FROM user_sync_events WHERE user_sync_event_id='se1';").fetchone()[0] == "e1"
            assert connection.execute("SELECT 1 FROM pragma_table_info('chat_messages') WHERE name='edited_at';").fetchone()
            assert connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='chat_message_reactions';").fetchone()
            assert connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='chat_message_forwards';").fetchone()
        with transaction() as connection:
            _run_stage12_message_migrations(connection)
    print("Stage 12 SQLite upgrade migration test passed.")


if __name__ == '__main__': main()
