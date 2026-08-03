from __future__ import annotations

from datetime import UTC, datetime, timedelta


def utc_now() -> datetime:
    return datetime.now(UTC)


def utc_now_iso() -> str:
    return to_iso(utc_now())


def to_iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def minutes_from_now(minutes: int) -> str:
    return to_iso(utc_now() + timedelta(minutes=minutes))


def days_from_now(days: int) -> str:
    return to_iso(utc_now() + timedelta(days=days))
