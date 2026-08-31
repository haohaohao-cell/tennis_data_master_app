"""PostgreSQL adapter used by the existing hand-written SQL services.

The application deliberately keeps its service SQL and public identifiers
stable during the database migration. This module owns driver-specific
details: qmark-to-pyformat conversion, dict-like rows, pooled connections,
and PostgreSQL error mapping. PostgreSQL is mandatory for runtime requests;
SQLite is used only by explicit offline migration tools.
"""

from __future__ import annotations

import atexit
from contextlib import contextmanager
import re
import sqlite3
from collections.abc import Iterator
from typing import Any
from urllib.parse import parse_qs, urlsplit

from .config import settings

_POOL: Any | None = None
_POOL_KEY: tuple[Any, ...] | None = None


def _connection_options() -> str:
    """Preserve DSN options such as search_path when adding a timeout."""
    if not settings.database_url:
        return f"-c statement_timeout={settings.database_transaction_timeout_seconds}"
    query = parse_qs(urlsplit(settings.database_url).query)
    configured = query.get("options", [""])[0].strip()
    timeout = f"-c statement_timeout={settings.database_transaction_timeout_seconds}"
    return f"{configured} {timeout}".strip()


class CompatRow(dict[str, Any]):
    """Mapping row compatible with both ``sqlite3.Row`` access styles."""

    def __iter__(self):
        # sqlite3.Row iterates over column values, while dict iterates over
        # keys. Existing services use tuple(row) for positional comparisons.
        return iter(self.values())

    def __getitem__(self, key: str | int) -> Any:
        if isinstance(key, int):
            return tuple(self.values())[key]
        if isinstance(key, slice):
            return tuple(self.values())[key]
        return super().__getitem__(key)


def _row_factory(cursor: Any):
    if cursor.description is None:
        # DDL and transaction statements have no result set. psycopg still
        # calls the row factory for them, so provide its explicit no-result
        # maker instead of iterating over None.
        from psycopg.rows import no_result

        return no_result
    columns = [column.name if hasattr(column, "name") else column[0] for column in cursor.description]

    def make_row(values: tuple[Any, ...]) -> CompatRow:
        return CompatRow(zip(columns, values))

    return make_row


def _protected_spans(sql: str) -> list[tuple[int, int]]:
    """Return SQL literal/comment spans that dialect rewrites must not touch."""
    spans: list[tuple[int, int]] = []
    index = 0
    while index < len(sql):
        if sql[index] == "'":
            start = index
            index += 1
            while index < len(sql):
                if sql[index] == "'":
                    if index + 1 < len(sql) and sql[index + 1] == "'":
                        index += 2
                        continue
                    index += 1
                    break
                index += 1
            spans.append((start, index))
            continue
        if sql[index] == '"':
            start = index
            index += 1
            while index < len(sql):
                if sql[index] == '"':
                    if index + 1 < len(sql) and sql[index + 1] == '"':
                        index += 2
                        continue
                    index += 1
                    break
                index += 1
            spans.append((start, index))
            continue
        if sql.startswith("--", index):
            start = index
            index = sql.find("\n", index + 2)
            index = len(sql) if index < 0 else index
            spans.append((start, index))
            continue
        if sql.startswith("/*", index):
            start = index
            end = sql.find("*/", index + 2)
            index = len(sql) if end < 0 else end + 2
            spans.append((start, index))
            continue
        if sql[index] == "$":
            match = re.match(r"\$[A-Za-z_][A-Za-z0-9_]*\$|\$\$", sql[index:])
            if match:
                delimiter = match.group(0)
                start = index
                end = sql.find(delimiter, index + len(delimiter))
                index = len(sql) if end < 0 else end + len(delimiter)
                spans.append((start, index))
                continue
        index += 1
    return spans


def _rewrite_unprotected(sql: str, pattern: str, replacement: str) -> str:
    spans = _protected_spans(sql)
    output: list[str] = []
    cursor = 0
    for start, end in spans:
        output.append(re.sub(pattern, replacement, sql[cursor:start], flags=re.IGNORECASE))
        output.append(sql[start:end])
        cursor = end
    output.append(re.sub(pattern, replacement, sql[cursor:], flags=re.IGNORECASE))
    return "".join(output)


def _masked_unprotected(sql: str) -> str:
    chars = list(sql)
    for start, end in _protected_spans(sql):
        for index in range(start, end):
            chars[index] = " "
    return "".join(chars)


def _escape_psycopg_literal_percents(sql: str) -> str:
    """Escape literal percent signs required by psycopg parameter parsing."""
    output: list[str] = []
    cursor = 0
    for start, end in _protected_spans(sql):
        output.append(sql[cursor:start])
        span = sql[start:end]
        output.append(span.replace("%", "%%") if span.startswith("'") else span)
        cursor = end
    output.append(sql[cursor:])
    return "".join(output)


def translate_sql(sql: str) -> str:
    """Translate the audited SQLite subset without touching literals/comments."""
    translated = _rewrite_unprotected(
        sql,
        r"(\b[A-Za-z_][A-Za-z0-9_.]*)\s+COLLATE\s+NOCASE\b",
        r"LOWER(\1)",
    )
    translated = _rewrite_unprotected(translated, r"\bMAX\(\s*0\s*,", "GREATEST(0,")
    translated = _rewrite_unprotected(
        translated,
        r"\bCURRENT_TIMESTAMP\b",
        "((CURRENT_TIMESTAMP AT TIME ZONE 'UTC')::text)",
    )
    translated = _rewrite_unprotected(
        translated,
        r"\bifnull\s*\(",
        "COALESCE(",
    )
    ignored_insert = bool(re.search(r"\bINSERT\s+OR\s+IGNORE\s+INTO\b", _masked_unprotected(translated), re.IGNORECASE))
    translated = _rewrite_unprotected(translated, r"\bINSERT\s+OR\s+IGNORE\s+INTO\b", "INSERT INTO")
    if ignored_insert and not re.search(r"\bON\s+CONFLICT\b", _masked_unprotected(translated), re.IGNORECASE):
        if len(_masked_unprotected(translated).split(";")) > 2:
            raise ValueError("INSERT OR IGNORE translation requires one SQL statement")
        semicolon = translated.rstrip().endswith(";")
        body = translated.rstrip()[:-1].rstrip() if semicolon else translated.rstrip()
        translated = body + " ON CONFLICT DO NOTHING" + (";" if semicolon else "")

    # Replace qmarks outside quoted SQL literals/comments. A literal question
    # mark, JSON, regex, or dollar-quoted function body remains byte-for-byte.
    output: list[str] = []
    spans = _protected_spans(translated)
    cursor = 0
    for start, end in spans:
        output.append(translated[cursor:start].replace("?", "%s"))
        output.append(translated[start:end])
        cursor = end
    output.append(translated[cursor:].replace("?", "%s"))
    return _escape_psycopg_literal_percents("".join(output))


class PostgresConnection:
    def __init__(self, raw: Any, pool: Any | None = None):
        self.raw = raw
        self.pool = pool

    def execute(self, sql: str, params: tuple[Any, ...] | list[Any] = ()) -> Any:
        try:
            return self.raw.execute(translate_sql(sql), tuple(params))
        except Exception as error:
            raise map_database_error(error) from error

    def executemany(self, sql: str, params: Any) -> Any:
        try:
            with self.raw.cursor() as cursor:
                return cursor.executemany(translate_sql(sql), params)
        except Exception as error:
            raise map_database_error(error) from error

    def commit(self) -> None:
        try:
            self.raw.commit()
        except Exception as error:
            raise map_database_error(error) from error

    def rollback(self) -> None:
        self.raw.rollback()

    def close(self) -> None:
        if self.pool is not None:
            self.pool.putconn(self.raw)
        else:
            self.raw.close()


def map_database_error(error: Exception) -> Exception:
    """Preserve existing service exception handling during the driver swap."""
    try:
        import psycopg.errors as errors

        if isinstance(error, errors.IntegrityError):
            return sqlite3.IntegrityError(str(error))
        if isinstance(error, errors.OperationalError):
            return sqlite3.OperationalError(str(error))
    except ImportError:
        pass
    return error


def _open_raw() -> Any:
    if not settings.database_url:
        raise RuntimeError(
            "TENNIS_DATABASE_URL (or TENNIS_POSTGRES_DSN) must be configured; "
            "SQLite runtime fallback has been removed."
        )
    try:
        import psycopg
    except ImportError as error:
        raise RuntimeError(
            "PostgreSQL is configured but psycopg is not installed; install backend/requirements.txt."
        ) from error
    raw = psycopg.connect(
        settings.database_url,
        connect_timeout=settings.database_connect_timeout_seconds,
        row_factory=_row_factory,
        options=_connection_options(),
    )
    raw.autocommit = False
    return raw


def _pool_key() -> tuple[Any, ...]:
    return (
        settings.database_url,
        settings.database_pool_min_size,
        settings.database_pool_max_size,
        settings.database_connect_timeout_seconds,
        settings.database_transaction_timeout_seconds,
    )


def close_pool() -> None:
    """Close and forget the process pool; useful for tests and DSN rotation."""
    global _POOL, _POOL_KEY
    if _POOL is not None:
        _POOL.close()
        _POOL = None
        _POOL_KEY = None


atexit.register(close_pool)


def _get_pool() -> Any:
    if not settings.database_url:
        raise RuntimeError(
            "TENNIS_DATABASE_URL (or TENNIS_POSTGRES_DSN) must be configured; "
            "SQLite runtime fallback has been removed."
        )
    global _POOL, _POOL_KEY
    key = _pool_key()
    if _POOL is not None and _POOL_KEY != key:
        close_pool()
    if _POOL is None:
        try:
            from psycopg_pool import ConnectionPool
        except ImportError as error:
            raise RuntimeError(
                "PostgreSQL is configured but psycopg_pool is not installed; install backend/requirements.txt."
            ) from error
        _POOL = ConnectionPool(
            conninfo=settings.database_url,
            min_size=settings.database_pool_min_size,
            max_size=settings.database_pool_max_size,
            kwargs={
                "connect_timeout": settings.database_connect_timeout_seconds,
                "row_factory": _row_factory,
                "options": _connection_options(),
            },
            open=True,
        )
        _POOL_KEY = key
    return _POOL


@contextmanager
def connection() -> Iterator[PostgresConnection]:
    """Open one PostgreSQL connection.

    psycopg's server-side connection is intentionally short lived per request;
    the driver handles TCP/session reuse through its prepared connection
    machinery and this boundary can be replaced by a pool without touching
    service code.
    """
    pool = _get_pool()
    with pool.connection() as raw:
        yield PostgresConnection(raw)


@contextmanager
def transaction(*, immediate: bool = False, lock_key: str | None = None) -> Iterator[PostgresConnection]:
    pool = _get_pool()
    with pool.connection() as raw:
        wrapped = PostgresConnection(raw)
        try:
            wrapped.execute("BEGIN;")
            if immediate:
                # SQLite BEGIN IMMEDIATE serialized all writers. PostgreSQL
                # already takes row locks for UPDATE/UPSERT statements, so a
                # caller must opt into an advisory lock for cross-row
                # serialization. Never use a process-wide fallback lock.
                if lock_key:
                    wrapped.execute("SELECT pg_advisory_xact_lock(hashtext(?));", (lock_key,))
            yield wrapped
            wrapped.commit()
        except Exception:
            wrapped.rollback()
            raise


def advisory_lock(connection: PostgresConnection, lock_key: str) -> None:
    """Take a transaction-scoped resource lock for work inside an existing transaction."""
    connection.execute("SELECT pg_advisory_xact_lock(hashtext(?));", (lock_key,))


def check_connection() -> None:
    with connection() as db:
        db.execute("SELECT 1;").fetchone()
