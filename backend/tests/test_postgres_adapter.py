import unittest
from contextlib import nullcontext
from unittest.mock import patch

from backend.app.core.postgres import CompatRow, transaction, translate_sql
from backend.app.core.postgres_schema import render_postgres_schema


class PostgresAdapterTest(unittest.TestCase):
    def test_sql_translation_preserves_service_contract(self) -> None:
        translated = translate_sql(
            "SELECT * FROM users WHERE nickname COLLATE NOCASE LIKE ? "
            "AND note = 'CURRENT_TIMESTAMP ?' LIMIT ? OFFSET ?"
        )
        self.assertIn("LOWER(nickname) LIKE %s", translated)
        self.assertIn("LIMIT %s OFFSET %s", translated)
        self.assertIn("'CURRENT_TIMESTAMP ?'", translated)

    def test_sqlite_insert_ignore_becomes_postgres_upsert(self) -> None:
        translated = translate_sql("INSERT OR IGNORE INTO users (user_id) VALUES (?);")
        self.assertEqual(
            translated,
            "INSERT INTO users (user_id) VALUES (%s) ON CONFLICT DO NOTHING;",
        )

    def test_compat_row_supports_mapping_and_positional_access(self) -> None:
        row = CompatRow({"user_id": "u1", "status": "active"})
        self.assertEqual(row["user_id"], "u1")
        self.assertEqual(row[0], "u1")
        self.assertEqual(tuple(row), ("u1", "active"))

    def test_rendered_schema_has_all_backend_tables(self) -> None:
        schema = render_postgres_schema(schema="public")
        self.assertGreaterEqual(schema.count("CREATE TABLE IF NOT EXISTS"), 40)
        for table_name in (
            "users",
            "chat_messages",
            "user_sync_events",
            "message_moderation_reports",
            "export_requests",
            "deletion_requests",
            "compliance_audit_logs",
        ):
            self.assertIn(f"CREATE TABLE IF NOT EXISTS {table_name}", schema)
        self.assertNotIn("PRAGMA ", schema.upper())
        self.assertNotIn("\nEND;\n\nCREATE OR REPLACE FUNCTION", schema)
        self.assertIn('CREATE SCHEMA IF NOT EXISTS "public"', schema)

    def test_immediate_without_resource_key_does_not_take_global_lock(self) -> None:
        class FakeRaw:
            def __init__(self) -> None:
                self.statements: list[str] = []

            def execute(self, sql: str, params: tuple[object, ...]) -> "FakeRaw":
                self.statements.append(sql)
                return self

            def commit(self) -> None:
                pass

            def rollback(self) -> None:
                pass

        class FakePool:
            def __init__(self, raw: FakeRaw) -> None:
                self.raw = raw

            def connection(self):
                return nullcontext(self.raw)

        raw = FakeRaw()
        with patch("backend.app.core.postgres._get_pool", return_value=FakePool(raw)):
            with transaction(immediate=True):
                pass

        self.assertEqual(raw.statements, ["BEGIN;"])


if __name__ == "__main__":
    unittest.main()
