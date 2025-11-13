"""Date and time helpers."""
from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo


COL_TZ = ZoneInfo("America/Bogota")


def utc_now_naive() -> datetime:
    """Return current UTC time without tzinfo for SQLite compatibility."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def to_colombia(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(COL_TZ)


def to_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)
