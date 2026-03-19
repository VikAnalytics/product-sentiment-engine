"""
price_correlator.py — Stage 4b: Inter-event price attribution.

For each event on a public company (ticker present), computes:
  - price_at_event: close price at the 5-min bar nearest to the event timestamp
  - window_return_pct: % change from event → next event for the same target
    (or market close if no next event that day)
  - reaction_1d/3d/7d: % change over broader windows (context)
  - confidence: high/medium/low based on event isolation and session

Runs daily after price_fetcher.py.

Usage:
    PYTHONPATH=src python src/price_correlator.py
"""

import logging
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple
from zoneinfo import ZoneInfo

from config import get_supabase

logging.basicConfig(
    level=getattr(logging, os.getenv("LOG_LEVEL", "INFO"), logging.INFO),
    format="%(asctime)s | %(levelname)s | %(message)s",
)
log = logging.getLogger(__name__)

ET = ZoneInfo("America/New_York")


def _parse_ts(s: str) -> datetime:
    """Parse ISO timestamp robustly — handles variable-length fractional seconds."""
    # Normalize fractional seconds to exactly 6 digits so fromisoformat works on Python 3.9
    s = re.sub(r'(\.\d+)', lambda m: m.group(1).ljust(7, '0')[:7], s)
    return datetime.fromisoformat(s)
MARKET_OPEN_H, MARKET_OPEN_M = 9, 30
MARKET_CLOSE_H, MARKET_CLOSE_M = 16, 0

# How close (in minutes) to the event timestamp a price bar must be
MAX_BAR_LAG_MINUTES = 10

# Window sizes for broader context
WINDOW_DAYS = {"reaction_1d": 1, "reaction_3d": 3, "reaction_7d": 7}


def _market_session(ts: datetime) -> str:
    """Classify a UTC timestamp as regular/premarket/afterhours."""
    local = ts.astimezone(ET)
    minutes_from_midnight = local.hour * 60 + local.minute
    open_min = MARKET_OPEN_H * 60 + MARKET_OPEN_M
    close_min = MARKET_CLOSE_H * 60 + MARKET_CLOSE_M
    if open_min <= minutes_from_midnight < close_min:
        return "regular"
    if 4 * 60 <= minutes_from_midnight < open_min:
        return "premarket"
    return "afterhours"


def _bar_ts(bar: dict) -> datetime:
    """Parse a bar's timestamp to a timezone-aware datetime.
    yfinance returns ET-aware timestamps; naive ones are assumed UTC."""
    ts = _parse_ts(bar["ts"])
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts


def _nearest_close(bars: list[dict], ts: datetime) -> Tuple[Optional[float], Optional[datetime]]:
    """Find the close price in the bar nearest to ts (within MAX_BAR_LAG_MINUTES)."""
    best_delta = None
    best_close = None
    best_ts = None
    for bar in bars:
        bar_ts = _bar_ts(bar)
        delta = abs((bar_ts - ts).total_seconds()) / 60
        if delta <= MAX_BAR_LAG_MINUTES:
            if best_delta is None or delta < best_delta:
                best_delta = delta
                best_close = float(bar["close"])
                best_ts = bar_ts
    return best_close, best_ts


def _pct_change(p_start: float, p_end: float) -> Optional[float]:
    if p_start and p_end and p_start != 0:
        return round((p_end - p_start) / p_start * 100, 4)
    return None


def _day_close(bars: list[dict], ref_ts: datetime, offset_days: int) -> Optional[float]:
    """Get the last close price on the trading day that is offset_days after ref_ts."""
    target_date = (ref_ts + timedelta(days=offset_days)).date()
    day_bars = [
        b for b in bars
        if _bar_ts(b).astimezone(ET).date() == target_date
    ]
    if not day_bars:
        return None
    return float(max(day_bars, key=lambda b: b["ts"])["close"])


def _fetch_bars_paginated(sb, target_id: int) -> list[dict]:
    """Fetch all 5-min bars for a target, paginating past Supabase's 1000-row limit."""
    all_bars = []
    PAGE = 900
    offset = 0
    while True:
        batch = (
            sb.table("stock_prices")
            .select("ts, close")
            .eq("target_id", target_id)
            .order("ts", desc=False)
            .range(offset, offset + PAGE - 1)
            .execute()
            .data
        )
        all_bars.extend(batch)
        if len(batch) < PAGE:
            break
        offset += PAGE
    return all_bars


def run_correlator():
    sb = get_supabase()

    # Load targets with tickers
    targets = (
        sb.table("targets")
        .select("id, name, ticker")
        .eq("status", "tracking")
        .neq("ticker", "null")
        .execute()
        .data
    )
    targets = [t for t in targets if t.get("ticker")]

    log.info("Computing price reactions for %d public targets", len(targets))
    total_written = 0

    for target in targets:
        tid = target["id"]
        name = target["name"]
        ticker = target["ticker"]

        # Load events for this target (last 60 days), sorted ascending
        cutoff = (datetime.now(timezone.utc) - timedelta(days=60)).isoformat()
        events = (
            sb.table("events")
            .select("id, headline, created_at")
            .eq("target_id", tid)
            .gte("created_at", cutoff)
            .order("created_at", desc=False)
            .execute()
            .data
        )
        if not events:
            continue

        # Load all 5-min bars for this target (paginated past Supabase 1000-row limit)
        bars = _fetch_bars_paginated(sb, tid)
        if not bars:
            log.warning("No price bars for %s (%s)", name, ticker)
            continue

        written = 0
        for i, event in enumerate(events):
            try:
                event_ts = (_parse_ts(event["created_at"].replace("Z", "+00:00")))
                session = _market_session(event_ts)

                # For after-hours/premarket: shift attribution to next market open
                if session != "regular":
                    # Find next market open bar
                    next_open_bars = [
                        b for b in bars
                        if _bar_ts(b) > event_ts
                        and _market_session(_bar_ts(b)) == "regular"
                    ]
                    ref_ts = _bar_ts(next_open_bars[0]) if next_open_bars else event_ts
                else:
                    ref_ts = event_ts

                price_at_event, _ = _nearest_close(bars, ref_ts)
                if price_at_event is None:
                    continue

                # Inter-event window: price at next event for this target
                next_event = events[i + 1] if i + 1 < len(events) else None
                window_end_price = None
                window_end_reason = "market_close"
                next_event_id = None

                if next_event:
                    next_ts = (_parse_ts(next_event["created_at"].replace("Z", "+00:00")))
                    # Only use inter-event window if same trading day
                    if next_ts.astimezone(ET).date() == event_ts.astimezone(ET).date():
                        window_end_price, _ = _nearest_close(bars, next_ts)
                        if window_end_price:
                            window_end_reason = "next_event"
                            next_event_id = next_event["id"]

                if window_end_price is None:
                    # Fall back to end-of-day close
                    eod_bars = [
                        b for b in bars
                        if _bar_ts(b).astimezone(ET).date() == ref_ts.astimezone(ET).date()
                        and _market_session(_bar_ts(b)) == "regular"
                    ]
                    if eod_bars:
                        window_end_price = float(max(eod_bars, key=lambda b: b["ts"])["close"])
                        window_end_reason = "market_close"

                window_return_pct = _pct_change(price_at_event, window_end_price)

                # Broader context windows
                reaction_1d = _pct_change(price_at_event, _day_close(bars, ref_ts, 1))
                reaction_3d = _pct_change(price_at_event, _day_close(bars, ref_ts, 3))
                reaction_7d = _pct_change(price_at_event, _day_close(bars, ref_ts, 7))

                # Confidence: how many other events happened within ±3 hours?
                nearby = [
                    e for e in events
                    if e["id"] != event["id"]
                    and abs(((_parse_ts(e["created_at"].replace("Z", "+00:00"))) - event_ts).total_seconds()) < 10800
                ]
                if len(nearby) == 0:
                    confidence = "high"
                    confidence_reason = "isolated — no other events within 3h"
                elif len(nearby) <= 2:
                    confidence = "medium"
                    confidence_reason = f"{len(nearby)} other event(s) within 3h"
                else:
                    confidence = "low"
                    confidence_reason = f"{len(nearby)} other events within 3h — attribution unclear"

                row = {
                    "event_id": event["id"],
                    "target_id": tid,
                    "ticker": ticker,
                    "price_at_event": price_at_event,
                    "window_return_pct": window_return_pct,
                    "next_event_id": next_event_id,
                    "window_end_reason": window_end_reason,
                    "reaction_1d": reaction_1d,
                    "reaction_3d": reaction_3d,
                    "reaction_7d": reaction_7d,
                    "market_session": session,
                    "confidence": confidence,
                    "confidence_reason": confidence_reason,
                }
                sb.table("price_reactions").upsert(row, on_conflict="event_id").execute()
                written += 1

            except Exception as exc:
                log.error("Error processing event %s for %s: %s", event["id"], name, exc)

        if written:
            log.info("  %s (%s) → %d price reactions computed", name, ticker, written)
        total_written += written

    log.info("price_correlator complete. Total reactions written: %d", total_written)


if __name__ == "__main__":
    run_correlator()
