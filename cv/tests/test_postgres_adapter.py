import unittest
from unittest.mock import patch

from cv.persistence.postgres import PostgresConnection, _prepare_connection, _split_script, get_connection


class PostgresScriptParserTest(unittest.TestCase):
    def test_split_script_ignores_comments_and_dollar_quoted_semicolons(self) -> None:
        script = """
        -- migration note;
        CREATE TABLE users (user_id text);
        /* function body; stays together */
        CREATE FUNCTION marker() RETURNS void AS $$
        BEGIN
            PERFORM 1;
        END;
        $$ LANGUAGE plpgsql;
        """
        statements = _split_script(script)
        self.assertEqual(len(statements), 2)
        self.assertIn("CREATE TABLE users", statements[0])
        self.assertIn("PERFORM 1;", statements[1])

    def test_connection_returns_checked_out_connection_to_pool(self) -> None:
        class FakeRaw:
            def commit(self) -> None:
                pass

            def rollback(self) -> None:
                pass

        class FakePool:
            def __init__(self) -> None:
                self.raw = FakeRaw()
                self.returned = []

            def getconn(self) -> FakeRaw:
                return self.raw

            def putconn(self, raw: FakeRaw) -> None:
                self.returned.append(raw)

        pool = FakePool()
        with patch("cv.persistence.postgres._get_pool", return_value=pool):
            connection = get_connection(dsn="postgresql://test")
            self.assertIsInstance(connection, PostgresConnection)
            connection.close()

        self.assertEqual(pool.returned, [pool.raw])

    def test_pool_session_setup_does_not_run_schema_ddl(self) -> None:
        class FakeRaw:
            def __init__(self) -> None:
                self.statements = []

            def execute(self, sql: str) -> None:
                self.statements.append(sql)

            def commit(self) -> None:
                pass

        raw = FakeRaw()
        _prepare_connection(raw, "cv_analysis")
        self.assertEqual(raw.statements, ['SET SESSION search_path TO "cv_analysis", pg_catalog'])


if __name__ == "__main__":
    unittest.main()
