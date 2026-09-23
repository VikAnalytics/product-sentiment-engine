"""
Reading event rows.

An event has two timestamps and they mean different things. published_at is when
the article or filing went out; created_at is when the pipeline wrote the row.
Every stage that asks "when did this news happen" — price attribution, the
tracker's age cutoff, the report window — wants published_at. Before migration
023 the column does not exist, so the helpers here fall back to created_at,
which is what the whole pipeline used to read.

Keep the coarse date filter in the database on created_at (it is always there)
and do the exact filtering here, so a pre-023 database still runs.
"""
import re
from datetime import datetime, timezone
from typing import Optional


def _parse_iso(ts: str) -> Optional[datetime]:
    """Parse a Supabase timestamp. Returns None rather than raising on junk."""
    if not ts:
        return None
    s = ts.strip().replace("Z", "+00:00")
    # Supabase emits 1-6 fractional digits; Python 3.9's fromisoformat wants exactly 6.
    s = re.sub(r"\.(\d+)", lambda m: "." + (m.group(1) + "000000")[:6], s)
    try:
        parsed = datetime.fromisoformat(s)
    except ValueError:
        return None
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed


def event_time_iso(row: dict) -> str:
    """When the event happened, as stored. published_at if present, else created_at."""
    return (row.get("published_at") or row.get("created_at") or "").strip()


def event_time(row: dict) -> Optional[datetime]:
    """When the event happened, as an aware datetime, or None if unparseable."""
    return _parse_iso(event_time_iso(row))


def sort_by_event_time(rows: list, reverse: bool = False) -> list:
    """Order events by when the news happened. Undated rows sort oldest."""
    epoch = datetime.min.replace(tzinfo=timezone.utc)
    return sorted(rows, key=lambda r: event_time(r) or epoch, reverse=reverse)


def within_age(row: dict, cutoff: datetime) -> bool:
    """True if the event happened at or after cutoff. Undated rows are kept."""
    happened = event_time(row)
    return True if happened is None else happened >= cutoff
