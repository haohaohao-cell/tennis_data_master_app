"""Render and apply the PostgreSQL form of the repository schema.

The checked-in SQLite schema remains the source of truth for legacy local
databases. Rendering is deterministic and deliberately keeps string IDs and
text JSON fields so existing API contracts and old rows remain compatible.
"""

from __future__ import annotations

from pathlib import Path
import re
from typing import Iterable

from .config import settings
from . import postgres


def _quote_identifier(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value):
        raise ValueError(f"Invalid PostgreSQL schema identifier: {value!r}")
    return f'"{value}"'


def _balanced_block(source: str, start: int) -> int:
    opening = source.find("(", start)
    if opening < 0:
        raise ValueError("CREATE TABLE block has no opening parenthesis")
    depth = 0
    quote: str | None = None
    index = opening
    while index < len(source):
        char = source[index]
        if quote:
            if char == quote:
                if index + 1 < len(source) and source[index + 1] == quote:
                    index += 2
                    continue
                quote = None
        elif char in {"'", '"'}:
            quote = char
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                semicolon = source.find(";", index)
                return semicolon + 1
        index += 1
    raise ValueError("unterminated CREATE TABLE block")


def _table_blocks(source: str) -> tuple[str, list[tuple[str, str]], str]:
    matches = list(re.finditer(r"CREATE TABLE IF NOT EXISTS\s+([A-Za-z_][A-Za-z0-9_]*)", source, re.IGNORECASE))
    if not matches:
        raise ValueError("schema contains no CREATE TABLE statements")
    prefix = source[: matches[0].start()]
    blocks: list[tuple[str, str]] = []
    cursor = matches[0].start()
    for match in matches:
        end = _balanced_block(source, match.start())
        blocks.append((match.group(1), source[match.start():end]))
        cursor = end
    suffix = source[cursor:]
    return prefix, blocks, suffix


def _dependencies(block: str) -> set[str]:
    return {name.lower() for name in re.findall(r"REFERENCES\s+([A-Za-z_][A-Za-z0-9_]*)", block, re.IGNORECASE)}


def _topological_order(blocks: list[tuple[str, str]]) -> list[str]:
    names = {name.lower() for name, _ in blocks}
    pending = {name.lower(): (_dependencies(block) & names) - {name.lower()} for name, block in blocks}
    ordered: list[str] = []
    while pending:
        ready = sorted(name for name, deps in pending.items() if not deps)
        if not ready:
            # The only intentional cycle is points <-> shots. Both tables can
            # be created first; their deferred FK is added below.
            ready = sorted(pending)
        ordered.extend(ready)
        for name in ready:
            pending.pop(name)
        for deps in pending.values():
            deps.difference_update(ready)
    return ordered


def _strip_sqlite_triggers(sql: str) -> tuple[str, list[tuple[str, str]]]:
    trigger_pattern = re.compile(
        r"CREATE TRIGGER IF NOT EXISTS\s+(\w+)\s+.*?\bON\s+(\w+)\b",
        re.IGNORECASE | re.DOTALL,
    )

    def trigger_end(source: str, start: int) -> int:
        """Find the outer trigger END, including nested CASE ... END blocks."""
        begin = re.search(r"\bBEGIN\b", source[start:], re.IGNORECASE)
        if begin is None:
            raise ValueError("SQLite trigger has no BEGIN block")
        index = start + begin.end()
        depth = 1
        quote: str | None = None
        while index < len(source):
            char = source[index]
            if quote:
                if char == quote:
                    if index + 1 < len(source) and source[index + 1] == quote:
                        index += 2
                        continue
                    quote = None
                index += 1
                continue
            if char in {"'", '"'}:
                quote = char
                index += 1
                continue
            token = re.match(r"\b(BEGIN|CASE|END)\b", source[index:], re.IGNORECASE)
            if token:
                if token.group(1).upper() in {"BEGIN", "CASE"}:
                    depth += 1
                else:
                    depth -= 1
                    if depth == 0:
                        semicolon = source.find(";", index + token.end())
                        if semicolon < 0:
                            raise ValueError("SQLite trigger has no terminating semicolon")
                        return semicolon + 1
                index += token.end()
                continue
            index += 1
        raise ValueError("unterminated SQLite trigger block")

    updated: list[tuple[str, str]] = []
    spans: list[tuple[int, int]] = []
    search_at = 0
    while match := trigger_pattern.search(sql, search_at):
        if "set_updated_at" in match.group(1).lower():
            updated.append((match.group(1), match.group(2)))
        end = trigger_end(sql, match.start())
        spans.append((match.start(), end))
        search_at = end
    if not spans:
        return sql, updated
    parts: list[str] = []
    cursor = 0
    for start, end in spans:
        parts.append(sql[cursor:start])
        cursor = end
    parts.append(sql[cursor:])
    return "".join(parts), updated


def render_postgres_schema(source_paths: Iterable[Path] | None = None, schema: str | None = None) -> str:
    paths = tuple(source_paths or (settings.schema_path,))
    source = "\n".join(path.read_text(encoding="utf-8") for path in paths)
    source, updated_triggers = _strip_sqlite_triggers(source)
    source = re.sub(r"^\s*PRAGMA[^;]*;", "", source, flags=re.IGNORECASE | re.MULTILINE)
    source = re.sub(
        r"INSERT\s+OR\s+IGNORE\s+INTO\s+([^;]+);",
        lambda match: f"INSERT INTO {match.group(1)} ON CONFLICT DO NOTHING;",
        source,
        flags=re.IGNORECASE,
    )
    source = re.sub(r"\bCURRENT_TIMESTAMP\b", "(CURRENT_TIMESTAMP AT TIME ZONE 'UTC')::text", source)
    source = re.sub(r"\bIFNULL\s*\(", "COALESCE(", source, flags=re.IGNORECASE)
    source = re.sub(r"\bREAL\b", "double precision", source, flags=re.IGNORECASE)
    # PostgreSQL requires referenced tables to exist at CREATE TABLE time.
    # points/ shots form a deliberate cycle, so defer this one FK.
    source = re.sub(
        r"\s*FOREIGN KEY\s*\(terminal_shot_id\)\s+REFERENCES\s+shots\s*\(shot_id\)\s+DEFERRABLE\s+INITIALLY\s+DEFERRED\s*,?",
        "",
        source,
        flags=re.IGNORECASE,
    )
    # SQLite accepts a trailing comma before a table's closing parenthesis;
    # PostgreSQL does not. Handle both same-line and multi-line definitions.
    source = re.sub(r",\s*\);", "\n);", source)
    _, blocks, suffix = _table_blocks(source)
    by_name = {name.lower(): block for name, block in blocks}
    ordered = _topological_order(blocks)
    table_sql = "\n\n".join(by_name[name] for name in ordered)
    suffix = suffix.replace("INSERT INTO social_post_stats", "INSERT INTO social_post_stats")
    trigger_sql = [
        """
CREATE OR REPLACE FUNCTION {set_updated_at}() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at := (CURRENT_TIMESTAMP AT TIME ZONE 'UTC')::text;
    RETURN NEW;
END;
$$;
""".strip()
    ]
    trigger_sql.append(
        """
CREATE OR REPLACE FUNCTION {validate_terminal_shot}() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.terminal_shot_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM {shots} WHERE shot_id = NEW.terminal_shot_id AND point_id = NEW.point_id
    ) THEN
        RAISE EXCEPTION 'terminal_shot_id must reference a shot in the same point'
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_points_terminal_shot_same_point_update ON {points};
CREATE CONSTRAINT TRIGGER trg_points_terminal_shot_same_point_update
AFTER INSERT OR UPDATE OF terminal_shot_id, point_id ON {points}
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION {validate_terminal_shot}();
""".strip()
    )
    seen: set[str] = set()
    for trigger_name, table_name in updated_triggers:
        if trigger_name in seen:
            continue
        seen.add(trigger_name)
        trigger_sql.append(
            "DROP TRIGGER IF EXISTS " + trigger_name + " ON {table_prefix}" + table_name + ";\n"
            "CREATE TRIGGER " + trigger_name + " BEFORE UPDATE ON {table_prefix}" + table_name + "\n"
            "FOR EACH ROW EXECUTE FUNCTION {set_updated_at}();"
        )
    trigger_sql.append(
        """
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'points_terminal_shot_fk') THEN
        ALTER TABLE {points}
            ADD CONSTRAINT points_terminal_shot_fk
            FOREIGN KEY (terminal_shot_id) REFERENCES {shots}(shot_id)
            DEFERRABLE INITIALLY DEFERRED;
    END IF;
END
$$;
""".strip()
    )
    trigger_sql.append(
        """
ALTER TABLE IF EXISTS {media}
    ADD COLUMN IF NOT EXISTS thumbnail_status TEXT NOT NULL DEFAULT 'pending',
    ADD COLUMN IF NOT EXISTS thumbnail_failure_code TEXT,
    ADD COLUMN IF NOT EXISTS storage_deleted_at TEXT,
    ADD COLUMN IF NOT EXISTS last_cleanup_error TEXT,
    ADD COLUMN IF NOT EXISTS duration_ms INTEGER,
    ADD COLUMN IF NOT EXISTS checksum_sha256 TEXT,
    ADD COLUMN IF NOT EXISTS expected_checksum_sha256 TEXT,
    ADD COLUMN IF NOT EXISTS container TEXT,
    ADD COLUMN IF NOT EXISTS codec TEXT;
""".strip()
    )
    schema_setup = ""
    set_updated_at = "set_updated_at_utc"
    validate_terminal_shot = "validate_terminal_shot_same_point"
    table_prefix = ""
    points = "points"
    shots = "shots"
    media = "chat_message_media"
    if schema:
        quoted_schema = _quote_identifier(schema)
        table_prefix = quoted_schema + "."
        points = f"{quoted_schema}.points"
        shots = f"{quoted_schema}.shots"
        media = f"{quoted_schema}.chat_message_media"
        set_updated_at = f"{quoted_schema}.set_updated_at_utc"
        validate_terminal_shot = f"{quoted_schema}.validate_terminal_shot_same_point"
        schema_setup = f"CREATE SCHEMA IF NOT EXISTS {quoted_schema};\nSET LOCAL search_path TO {quoted_schema}, pg_catalog;\n"
    trigger_sql = [item.format(set_updated_at=set_updated_at, validate_terminal_shot=validate_terminal_shot, table_prefix=table_prefix, points=points, shots=shots, media=media) for item in trigger_sql]
    return "BEGIN;\n" + schema_setup + table_sql + "\n\n" + suffix.strip() + "\n\n" + "\n\n".join(trigger_sql) + "\nCOMMIT;\n"


def initialize_postgres_schema(schema: str | None = None) -> None:
    if not settings.database_url:
        raise RuntimeError(
            "TENNIS_DATABASE_URL (or TENNIS_POSTGRES_DSN) must be configured "
            "before initializing PostgreSQL."
        )
    schema_sql = render_postgres_schema(schema=schema)
    try:
        import psycopg
    except ImportError as error:
        raise RuntimeError(
            "PostgreSQL is configured but psycopg is not installed; install backend/requirements.txt."
        ) from error

    try:
        # Schema setup is a one-shot operation. Use a dedicated raw
        # connection so pool return/reset handling cannot roll back a manual
        # commit after a successful multi-statement execute.
        with psycopg.connect(
            settings.database_url,
            connect_timeout=settings.database_connect_timeout_seconds,
        ) as connection:
            connection.execute(schema_sql)
            connection.commit()
            target_schema = schema or "public"
            table_count = connection.execute(
                "SELECT COUNT(*) FROM pg_tables WHERE schemaname = %s",
                (target_schema,),
            ).fetchone()[0]
            if int(table_count) < 40:
                raise RuntimeError(
                    f"PostgreSQL schema initialization incomplete: {table_count} tables in current schema"
                )
    finally:
        # Initialization may be called before the application pool exists;
        # clear any stale pool so subsequent requests use the configured DSN.
        postgres.close_pool()
