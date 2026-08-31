"""PostgreSQL persistence adapter for CV analysis rows.

The CV pipeline has a deliberately separate schema because its historical
``users``/``uploads``/``points``/``shots`` contract differs from the backend
social schema. Both schemas may live in the same PostgreSQL database without
renaming or changing any CV columns.
"""

from __future__ import annotations

import atexit
import os
import re
from typing import Any

from cv.config import DEFAULT_DB_PATH


CV_DATABASE_SCHEMA = os.getenv("TENNIS_CV_DATABASE_SCHEMA", "cv_analysis")
CV_DATABASE_URL = os.getenv("TENNIS_CV_DATABASE_URL") or os.getenv("TENNIS_DATABASE_URL") or os.getenv("TENNIS_POSTGRES_DSN")
_POOL: Any | None = None
_POOL_KEY: tuple[Any, ...] | None = None


def _pool_size(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        parsed = int(value)
    except ValueError as error:
        raise ValueError(f"{name} must be an integer") from error
    if parsed < 1:
        raise ValueError(f"{name} must be at least 1")
    return parsed


def _configured_schema() -> str:
    return _validate_schema(os.getenv("TENNIS_CV_DATABASE_SCHEMA", CV_DATABASE_SCHEMA))


def _configured_dsn() -> str | None:
    return os.getenv("TENNIS_CV_DATABASE_URL") or os.getenv("TENNIS_DATABASE_URL") or os.getenv("TENNIS_POSTGRES_DSN") or CV_DATABASE_URL


def _validate_schema(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value):
        raise ValueError(f"Invalid CV PostgreSQL schema identifier: {value!r}")
    return value


def _split_script(script: str) -> list[str]:
    statements: list[str] = []
    start = 0
    quote: str | None = None
    dollar_quote: str | None = None
    line_comment = False
    block_comment = False
    index = 0
    while index < len(script):
        char = script[index]
        if line_comment:
            if char == "\n":
                line_comment = False
            index += 1
            continue
        if block_comment:
            if script.startswith("*/", index):
                block_comment = False
                index += 2
            else:
                index += 1
            continue
        if dollar_quote:
            if script.startswith(dollar_quote, index):
                index += len(dollar_quote)
                dollar_quote = None
            else:
                index += 1
            continue
        if quote:
            if char == quote:
                if index + 1 < len(script) and script[index + 1] == quote:
                    index += 2
                    continue
                quote = None
        elif script.startswith("--", index):
            line_comment = True
            index += 2
            continue
        elif script.startswith("/*", index):
            block_comment = True
            index += 2
            continue
        elif char == "$":
            match = re.match(r"\$[A-Za-z_][A-Za-z0-9_]*\$|\$\$", script[index:])
            if match:
                dollar_quote = match.group(0)
                index += len(dollar_quote)
                continue
        elif char in {"'", '"'}:
            quote = char
        elif char == ";":
            statement = script[start:index].strip()
            if statement:
                statements.append(statement)
            start = index + 1
        index += 1
    tail = script[start:].strip()
    if tail:
        statements.append(tail)
    return statements


def _translate_sql(sql: str, params: Any) -> tuple[str, tuple[Any, ...] | Any]:
    """Translate SQLite-style placeholders used by the CV repository."""
    if isinstance(params, dict):
        names: list[str] = []

        def replace(match: re.Match[str]) -> str:
            names.append(match.group(1))
            return "%s"

        translated = re.sub(r"(?<!:):([A-Za-z_][A-Za-z0-9_]*)", replace, sql)
        return translated, tuple(params[name] for name in names)
    return sql.replace("?", "%s"), params


class PostgresConnection:
    """Small DB-API facade matching the methods used by CV persistence."""

    def __init__(self, raw: Any, schema: str, pool: Any | None = None):
        self.raw = raw
        self.schema = schema
        self.pool = pool
        self._closed = False

    def execute(self, sql: str, params: Any = ()) -> Any:
        translated, bound = _translate_sql(sql, params)
        return self.raw.execute(translated, bound)

    def executemany(self, sql: str, params: Any) -> Any:
        rows = list(params)
        names = re.findall(r"(?<!:):([A-Za-z_][A-Za-z0-9_]*)", sql)
        translated = re.sub(r"(?<!:):([A-Za-z_][A-Za-z0-9_]*)", "%s", sql)
        if rows and isinstance(rows[0], dict):
            rows = [tuple(row[name] for name in names) for row in rows]
        else:
            rows = [tuple(row) for row in rows]
        with self.raw.cursor() as cursor:
            return cursor.executemany(translated, rows)

    def executescript(self, script: str) -> None:
        for statement in _split_script(script):
            self.raw.execute(statement)

    def commit(self) -> None:
        self.raw.commit()

    def rollback(self) -> None:
        self.raw.rollback()

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self.pool is not None:
            # A caller may close without an explicit commit. Reset the
            # transaction before returning the session to the pool.
            try:
                self.raw.rollback()
            except Exception:
                pass
            finally:
                self.pool.putconn(self.raw)
        else:
            self.raw.close()

    def __enter__(self) -> "PostgresConnection":
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        if exc_type is None:
            self.commit()
        else:
            self.rollback()
        self.close()


def _require_dsn(dsn: str | None = None) -> str:
    value = dsn or _configured_dsn()
    if not value:
        raise RuntimeError(
            "TENNIS_DATABASE_URL (or TENNIS_CV_DATABASE_URL) must be configured; "
            "CV SQLite persistence has been removed."
        )
    return value


def _connect_raw(dsn: str | None = None, schema: str | None = None) -> Any:
    connection_dsn = _require_dsn(dsn)
    try:
        import psycopg
        from psycopg.rows import dict_row
    except ImportError as error:
        raise RuntimeError("Install backend/requirements.txt (psycopg[binary,pool]) before using CV persistence.") from error
    target_schema = _validate_schema(schema or _configured_schema())
    _ensure_schema(connection_dsn, target_schema)
    raw = psycopg.connect(connection_dsn, row_factory=dict_row)
    _prepare_connection(raw, target_schema)
    return raw


def _prepare_connection(raw: Any, schema: str) -> None:
    """Pin a pooled session to the CV schema without running DDL."""
    raw.execute(f'SET SESSION search_path TO "{schema}", pg_catalog')
    raw.commit()


def _ensure_schema(dsn: str, schema: str) -> None:
    """Create the CV namespace once, serialized across concurrent processes."""
    try:
        import psycopg
    except ImportError as error:
        raise RuntimeError("Install backend/requirements.txt (psycopg[binary,pool]) before using CV persistence.") from error

    with psycopg.connect(dsn) as raw:
        # CREATE SCHEMA IF NOT EXISTS can still race at pg_namespace under
        # concurrent pool startup. A transaction-scoped advisory lock makes
        # initialization deterministic across workers and processes.
        raw.execute("SELECT pg_advisory_xact_lock(hashtext(%s));", (f"cv-schema:{schema}",))
        raw.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema}"')
        raw.commit()


def _pool_key(dsn: str, schema: str) -> tuple[Any, ...]:
    return (
        dsn,
        schema,
        _pool_size("TENNIS_CV_DATABASE_POOL_MIN_SIZE", 1),
        _pool_size("TENNIS_CV_DATABASE_POOL_MAX_SIZE", 4),
    )


def close_pool() -> None:
    """Close the process pool, including after DSN/schema rotation in tests."""
    global _POOL, _POOL_KEY
    if _POOL is not None:
        _POOL.close()
        _POOL = None
        _POOL_KEY = None


atexit.register(close_pool)


def _get_pool(dsn: str, schema: str) -> Any:
    global _POOL, _POOL_KEY
    key = _pool_key(dsn, schema)
    if _POOL is not None and _POOL_KEY != key:
        close_pool()
    if _POOL is None:
        try:
            from psycopg.rows import dict_row
            from psycopg_pool import ConnectionPool
        except ImportError as error:
            raise RuntimeError(
                "Install backend/requirements.txt (psycopg[binary,pool]) before using CV persistence."
            ) from error

        min_size = key[2]
        max_size = key[3]
        if max_size < min_size:
            raise ValueError("TENNIS_CV_DATABASE_POOL_MAX_SIZE must be >= TENNIS_CV_DATABASE_POOL_MIN_SIZE")

        _ensure_schema(dsn, schema)

        def configure(raw: Any) -> None:
            _prepare_connection(raw, schema)

        _POOL = ConnectionPool(
            conninfo=dsn,
            min_size=min_size,
            max_size=max_size,
            kwargs={"row_factory": dict_row},
            configure=configure,
            open=True,
        )
        _POOL_KEY = key
    return _POOL


def get_connection(db_path: str | os.PathLike[str] = DEFAULT_DB_PATH, *, dsn: str | None = None) -> PostgresConnection:
    del db_path  # Kept for source compatibility; PostgreSQL is the only store.
    target_schema = _configured_schema()
    pool = _get_pool(_require_dsn(dsn), target_schema)
    return PostgresConnection(pool.getconn(), target_schema, pool)


def initialize_schema(*, dsn: str | None = None, schema: str | None = None) -> None:
    """Create CV tables in the configured PostgreSQL schema idempotently."""
    from .core_tables import CREATE_CORE_TABLES_SQL
    from .points_schema import CREATE_POINTS_TABLE_SQL
    from .shots_schema import CREATE_SHOTS_TABLE_SQL

    target_schema = _validate_schema(schema or _configured_schema())
    pool = _get_pool(_require_dsn(dsn), target_schema)
    connection = PostgresConnection(pool.getconn(), target_schema, pool)
    try:
        for script in (CREATE_CORE_TABLES_SQL, CREATE_POINTS_TABLE_SQL, CREATE_SHOTS_TABLE_SQL):
            converted = re.sub(r"\bREAL\b", "double precision", script, flags=re.IGNORECASE)
            for statement in _split_script(converted):
                connection.execute(statement.replace("CURRENT_TIMESTAMP", "(CURRENT_TIMESTAMP AT TIME ZONE 'UTC')::text"))
        connection.commit()
        table_count = connection.execute(
            """
            SELECT COUNT(*) AS table_count
            FROM information_schema.tables
            WHERE table_schema = %s AND table_type = 'BASE TABLE'
            """,
            (target_schema,),
        ).fetchone()["table_count"]
        if int(table_count) < 4:
            raise RuntimeError(
                f"CV PostgreSQL schema initialization incomplete: {table_count} tables in {target_schema}"
            )
    finally:
        connection.close()


__all__ = ["CV_DATABASE_SCHEMA", "CV_DATABASE_URL", "get_connection", "initialize_schema"]
