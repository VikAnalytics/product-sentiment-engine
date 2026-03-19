"""
price_fetcher.py — Stage 4a: Fetch intraday 5-min OHLCV bars via yfinance.

Runs daily after scout.py. For every target with a ticker, downloads the last
60 days of 5-minute bars (yfinance free limit) and upserts into stock_prices.
Deduplicates by (target_id, ts) so re-runs are safe.

Usage:
    PYTHONPATH=src python src/price_fetcher.py
"""

import logging
import os
from datetime import datetime, timezone
from collections import defaultdict

import yfinance as yf

from config import get_supabase

logging.basicConfig(
    level=getattr(logging, os.getenv("LOG_LEVEL", "INFO"), logging.INFO),
    format="%(asctime)s | %(levelname)s | %(message)s",
)
log = logging.getLogger(__name__)

LOOKBACK_DAYS = 60  # yfinance free limit for 5-min bars


def _fetch_bars(ticker: str, days: int) -> list[dict]:
    """Download 5-min OHLCV bars for a ticker. Returns list of bar dicts."""
    try:
        # Use period= instead of start/end to avoid yfinance's exact 60-day boundary errors
        period = f"{min(days, 59)}d"
        df = yf.download(
            ticker,
            period=period,
            interval="5m",
            progress=False,
            auto_adjust=True,
        )
        if df.empty:
            log.warning("No data returned for %s", ticker)
            return []
        # Newer yfinance returns MultiIndex columns like ("Close", "AAPL") — flatten them
        if hasattr(df.columns, "levels"):
            df.columns = df.columns.get_level_values(0)
        # Deduplicate columns after flattening (Open/High/Low/Close/Volume may repeat)
        df = df.loc[:, ~df.columns.duplicated()]
        bars = []
        for ts, row in df.iterrows():
            if ts is None:
                continue
            # Ensure timezone-aware UTC
            if hasattr(ts, "tzinfo") and ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            close = row.get("Close")
            if close is None or close != close:  # NaN check
                continue
            bars.append({
                "ts": ts.isoformat(),
                "open": float(row["Open"]) if "Open" in row and row["Open"] == row["Open"] else None,
                "high": float(row["High"]) if "High" in row and row["High"] == row["High"] else None,
                "low": float(row["Low"]) if "Low" in row and row["Low"] == row["Low"] else None,
                "close": float(close),
                "volume": int(row["Volume"]) if "Volume" in row and row["Volume"] == row["Volume"] else None,
            })
        return bars
    except Exception as exc:
        log.error("Error fetching bars for %s: %s", ticker, exc)
        return []


def run_price_fetcher():
    sb = get_supabase()

    # Load all targets that have a ticker
    targets = (
        sb.table("targets")
        .select("id, name, ticker")
        .eq("status", "tracking")
        .neq("ticker", "null")
        .execute()
        .data
    )
    targets = [t for t in targets if t.get("ticker")]

    # Group target_ids by ticker to avoid fetching the same ticker multiple times
    ticker_to_ids: dict[str, list[int]] = defaultdict(list)
    for t in targets:
        ticker_to_ids[t["ticker"]].append(t["id"])

    log.info("Fetching prices for %d unique tickers across %d targets", len(ticker_to_ids), len(targets))

    total_rows = 0
    for ticker, target_ids in ticker_to_ids.items():
        bars = _fetch_bars(ticker, LOOKBACK_DAYS)
        if not bars:
            continue

        rows_inserted = 0
        for tid in target_ids:
            rows = [{"target_id": tid, **bar} for bar in bars]
            # Upsert in batches of 500 to stay within PostgREST limits
            for i in range(0, len(rows), 500):
                batch = rows[i : i + 500]
                sb.table("stock_prices").upsert(batch, on_conflict="target_id,ts").execute()
                rows_inserted += len(batch)

        log.info("  %s → %d bars × %d target(s) = %d rows upserted", ticker, len(bars), len(target_ids), rows_inserted)
        total_rows += rows_inserted

    log.info("price_fetcher complete. Total rows upserted: %d", total_rows)


if __name__ == "__main__":
    run_price_fetcher()
