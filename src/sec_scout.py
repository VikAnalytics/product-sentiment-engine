"""
sec_scout.py — SEC EDGAR filing scout.

Uses EDGAR's company submissions API to find recent 8-K, 10-Q, 10-K, and
DEF 14A filings for each tracked public target and inserts them as events.

No API key required. EDGAR rate limit: ≤10 req/sec (we stay well under).

Usage:
    PYTHONPATH=src python src/sec_scout.py
"""

import logging
import os
import time
from datetime import datetime, timezone, timedelta
from collections import defaultdict
from typing import Optional

import requests

from config import get_supabase

logging.basicConfig(
    level=getattr(logging, os.getenv("LOG_LEVEL", "INFO"), logging.INFO),
    format="%(asctime)s | %(levelname)s | %(message)s",
)
log = logging.getLogger(__name__)

TRACKED_FORMS = {"8-K", "10-Q", "10-K", "DEF 14A"}
LOOKBACK_DAYS = int(os.getenv("SEC_LOOKBACK_DAYS", "7"))

EDGAR_HEADERS = {
    "User-Agent": "ProductSentimentEngine research@example.com",
    "Accept-Encoding": "gzip, deflate",
}
TICKER_CIK_URL = "https://www.sec.gov/files/company_tickers.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
FILING_INDEX_URL = "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik}&type={form}&dateb=&owner=include&count=5"


def _load_ticker_cik_map() -> dict[str, str]:
    """Download EDGAR's full ticker→CIK mapping (cached for this run)."""
    try:
        resp = requests.get(TICKER_CIK_URL, headers=EDGAR_HEADERS, timeout=15)
        resp.raise_for_status()
        raw = resp.json()  # {idx: {cik_str, ticker, title}}
        mapping = {}
        for entry in raw.values():
            ticker = (entry.get("ticker") or "").upper()
            cik = str(entry.get("cik_str", "")).zfill(10)
            if ticker and cik:
                mapping[ticker] = cik
        log.info("Loaded EDGAR ticker→CIK map: %d entries", len(mapping))
        return mapping
    except Exception as exc:
        log.error("Failed to load ticker→CIK map: %s", exc)
        return {}


def _fetch_recent_filings(cik: str, cutoff_date: str) -> list[dict]:
    """
    Fetch recent filings from EDGAR submissions API for a CIK.
    Returns list of {form_type, filing_date, accession_no, primary_document}.
    """
    try:
        url = SUBMISSIONS_URL.format(cik=cik)
        resp = requests.get(url, headers=EDGAR_HEADERS, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        recent = data.get("filings", {}).get("recent", {})
        forms = recent.get("form", [])
        dates = recent.get("filingDate", [])
        accessions = recent.get("accessionNumber", [])
        docs = recent.get("primaryDocument", [])
        name = data.get("name", "")

        filings = []
        for form, date, accession, doc in zip(forms, dates, accessions, docs):
            if form not in TRACKED_FORMS:
                continue
            if date < cutoff_date:
                continue
            filings.append({
                "form_type": form,
                "filing_date": date,
                "accession_no": accession,
                "primary_document": doc,
                "company_name": name,
                "cik": cik,
            })
        return filings
    except Exception as exc:
        log.error("EDGAR submissions error for CIK %s: %s", cik, exc)
        return []


def _filing_url(cik: str, accession_no: str) -> str:
    clean = accession_no.replace("-", "")
    return f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{clean}"


def run_sec_scout():
    sb = get_supabase()

    targets = (
        sb.table("targets")
        .select("id, name, ticker")
        .eq("status", "tracking")
        .neq("ticker", "null")
        .execute()
        .data
    )
    targets = [t for t in targets if t.get("ticker")]

    # Deduplicate by ticker so each company is only fetched once
    ticker_to_target: dict[str, dict] = {}
    for t in targets:
        ticker = t["ticker"].upper()
        if ticker not in ticker_to_target:
            ticker_to_target[ticker] = t

    log.info("SEC scout: %d unique tickers to check", len(ticker_to_target))

    ticker_cik = _load_ticker_cik_map()
    cutoff_date = (datetime.now(timezone.utc) - timedelta(days=LOOKBACK_DAYS)).strftime("%Y-%m-%d")
    total_new = 0

    for ticker, target in ticker_to_target.items():
        cik = ticker_cik.get(ticker)
        if not cik:
            log.debug("No CIK found for ticker %s", ticker)
            continue

        filings = _fetch_recent_filings(cik, cutoff_date)
        time.sleep(0.12)  # stay under 10 req/sec

        if not filings:
            continue

        for filing in filings:
            form_type = filing["form_type"]
            filing_date = filing["filing_date"]
            company = filing.get("company_name") or target["name"]
            url = _filing_url(cik, filing["accession_no"])
            headline = f"[{form_type}] {company} — {filing_date} SEC filing"

            # Idempotency: skip if event with same headline already exists for this target
            existing = (
                sb.table("events")
                .select("id")
                .eq("target_id", target["id"])
                .eq("headline", headline)
                .limit(1)
                .execute()
                .data
            )
            if existing:
                continue

            sb.table("events").insert({
                "target_id": target["id"],
                "headline": headline,
                "created_at": f"{filing_date}T16:30:00Z",  # filings typically go live after market close
                "cached_analysis": f"Source: {url}",
            }).execute()
            log.info("  New filing event: %s | %s | %s", ticker, form_type, filing_date)
            total_new += 1

    log.info("sec_scout complete. New filing events: %d", total_new)


if __name__ == "__main__":
    run_sec_scout()
