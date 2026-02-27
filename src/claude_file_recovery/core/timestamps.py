"""Timestamp normalization for --before CLI option."""

from __future__ import annotations

import re
from datetime import datetime, timezone


def normalize_timestamp(user_input: str) -> str:
    """Convert flexible user input into UTC ISO 8601 for lexicographic comparison.

    Accepted formats:
        "YYYY-MM-DD"              → end of day in local time, converted to UTC
        "YYYY-MM-DD HH:MM"       → end of minute in local time, converted to UTC
        "YYYY-MM-DD HH:MM:SS"    → end of second in local time, converted to UTC
        "YYYY-MM-DDTHH:MM:SSZ"   → UTC, honored as-is
        "YYYY-MM-DD HH:MM+02:00" → offset honored, converted to UTC

    Returns:
        UTC timestamp string in the format "YYYY-MM-DDTHH:MM:SS.mmmZ"
        suitable for lexicographic comparison with stored timestamps.

    Raises:
        ValueError: If input cannot be parsed.
    """
    s = user_input.strip()
    if not s:
        raise ValueError("Empty timestamp")

    # Try full ISO 8601 with timezone info (Z or +HH:MM)
    if "Z" in s or re.search(r"[+-]\d{2}:\d{2}$", s):
        return _parse_aware(s)

    # Bare timestamps — interpret as local time
    # YYYY-MM-DD
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
        dt = datetime.strptime(s, "%Y-%m-%d")
        dt = dt.replace(hour=23, minute=59, second=59, microsecond=999000)
        return _local_to_utc(dt)

    # YYYY-MM-DD HH:MM
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}", s):
        dt = datetime.strptime(s.replace("T", " "), "%Y-%m-%d %H:%M")
        dt = dt.replace(second=59, microsecond=999000)
        return _local_to_utc(dt)

    # YYYY-MM-DD HH:MM:SS
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}", s):
        dt = datetime.strptime(s.replace("T", " "), "%Y-%m-%d %H:%M:%S")
        dt = dt.replace(microsecond=999000)
        return _local_to_utc(dt)

    raise ValueError(
        f"Cannot parse timestamp: {s!r}. "
        "Expected format: YYYY-MM-DD, YYYY-MM-DD HH:MM, YYYY-MM-DD HH:MM:SS, "
        "or full ISO 8601 with timezone (e.g. 2026-01-30T15:00:00Z)"
    )


def utc_to_local(utc_ts: str, fmt: str = "%Y-%m-%d %H:%M") -> str:
    """Convert a UTC ISO 8601 timestamp to a local-time string.

    Returns the formatted local time, or the raw input on parse failure.
    """
    try:
        dt_utc = datetime.fromisoformat(utc_ts.replace("Z", "+00:00"))
        return dt_utc.astimezone().strftime(fmt)
    except Exception:
        return utc_ts


def format_local_confirmation(utc_ts: str) -> str:
    """Format a UTC timestamp as a local-time confirmation string.

    Example: "2026-01-30T14:00:00.000Z (2026-01-30 15:00 local)"
    """
    local_str = utc_to_local(utc_ts)
    if local_str == utc_ts:
        return utc_ts
    return f"{utc_ts} ({local_str} local)"


def _parse_aware(s: str) -> str:
    """Parse a timestamp with explicit timezone and convert to UTC."""
    try:
        # Replace Z with +00:00 for fromisoformat compatibility
        normalized = s.replace("Z", "+00:00").replace(" ", "T")
        dt = datetime.fromisoformat(normalized)
        dt_utc = dt.astimezone(timezone.utc)
        return _format_utc(dt_utc)
    except (ValueError, OverflowError) as e:
        raise ValueError(f"Cannot parse timestamp with timezone: {s!r} — {e}") from e


def _local_to_utc(dt_naive: datetime) -> str:
    """Interpret a naive datetime as local time and convert to UTC."""
    dt_local = dt_naive.astimezone()  # attaches system local timezone
    dt_utc = dt_local.astimezone(timezone.utc)
    return _format_utc(dt_utc)


def _format_utc(dt: datetime) -> str:
    """Format a datetime as a UTC ISO 8601 string matching stored format."""
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"
