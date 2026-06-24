"""Shared UTC datetime helpers.

Centralizes what were three identical ``_now`` definitions (sessions, users,
db.models) plus the wire/compare conversions that lived inline. Storage is
always timezone-aware UTC; the conversions bridge SQLite (naive) vs Postgres
(aware) and the epoch-seconds wire format the frontend expects.
"""

from __future__ import annotations

from datetime import datetime, timezone


def utcnow() -> datetime:
    """Timezone-aware current UTC time — what we store."""
    return datetime.now(timezone.utc)


def as_naive_utc(dt: datetime) -> datetime:
    """Coerce an aware/naive datetime to naive UTC so comparisons never raise on a
    mixed offset (SQLite returns naive datetimes; Postgres returns aware)."""
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def to_epoch(dt: datetime | None) -> float:
    """Stored datetime -> epoch seconds (the frontend ``Session`` uses numbers).
    Naive values are treated as UTC (that's how we store them)."""
    if dt is None:
        return 0.0
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp()
