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

# An 8-K's item numbers are what make it worth reading. Without them every
# filing reads "NEWS CORP filed something", and News Corp files a routine
# Item 8.01 nearly every business day.
SEC_ITEM_LABELS = {
    "1.01": "Material agreement",
    "1.02": "Agreement terminated",
    "1.03": "Bankruptcy",
    "2.01": "Acquisition or disposal",
    "2.02": "Results of operations",
    "2.03": "New financial obligation",
    "2.04": "Obligation accelerated",
    "2.05": "Exit or disposal costs",
    "2.06": "Material impairment",
    "3.01": "Listing or compliance notice",
    "3.02": "Unregistered equity sale",
    "3.03": "Security holder rights changed",
    "4.01": "Auditor changed",
    "4.02": "Prior financials unreliable",
    "5.01": "Change in control",
    "5.02": "Officer or director change",
    "5.03": "Bylaws amended",
    "5.07": "Shareholder vote",
    "7.01": "Regulation FD disclosure",
    "8.01": "Other events",
    "9.01": "Exhibits",
}

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
    Returns list of {form_type, filing_date, accepted_at, items, accession_no,
    primary_document}.
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
        # Both sit in the same payload and were being dropped: acceptance is the
        # only real timestamp EDGAR gives, and the items say what was filed.
        accepted = recent.get("acceptanceDateTime", [])
        items = recent.get("items", [])
        name = data.get("name", "")

        filings = []
        for i, (form, date, accession, doc) in enumerate(zip(forms, dates, accessions, docs)):
            if form not in TRACKED_FORMS:
                continue
            if date < cutoff_date:
                continue
            filings.append({
                "form_type": form,
                "filing_date": date,
                "accepted_at": accepted[i] if i < len(accepted) else "",
                "items": items[i] if i < len(items) else "",
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


def _filing_published_at(filing: dict) -> str:
    """
    When the filing actually went live, as an ISO-8601 UTC string.

    EDGAR's acceptanceDateTime is already UTC. The fallback is the filing date at
    21:00 UTC (17:00 ET, just after the close), which is where most filings land;
    the previous hardcoded 16:30Z was meant to mean "after the close" but is
    12:30 ET, so every filing was attributed to a mid-session price move.
    """
    accepted = (filing.get("accepted_at") or "").strip()
    if accepted:
        try:
            parsed = datetime.fromisoformat(accepted.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc).isoformat()
        except ValueError:
            log.debug("Unparseable acceptanceDateTime %r, falling back to filing date", accepted)
    return f"{filing['filing_date']}T21:00:00+00:00"


def _filing_headline(filing: dict, company: str) -> str:
    """
    '[8-K · Results of operations] ADOBE INC.' — the item is what separates an
    earnings release from a routine buyback notice, and it was being discarded.
    """
    form_type = filing["form_type"]
    codes = [c.strip() for c in (filing.get("items") or "").split(",") if c.strip()]
    # 9.01 is only ever "exhibits attached" and never the point of the filing.
    labels = [SEC_ITEM_LABELS[c] for c in codes if c in SEC_ITEM_LABELS and c != "9.01"]
    if labels:
        return f"[{form_type} · {', '.join(labels[:2])}] {company}"
    return f"[{form_type}] {company}"


# Flipped the first time the DB rejects the post-023 columns, so a database
# without the migration keeps collecting filings instead of losing the run.
_EVENT_COLUMNS_OK = True


def _filing_already_stored(sb, target_id: int, url: str, headline: str) -> bool:
    """True if this filing is already an event for this target."""
    if _EVENT_COLUMNS_OK:
        try:
            found = (
                sb.table("events").select("id")
                .eq("target_id", target_id).eq("source_url", url)
                .limit(1).execute().data or []
            )
            if found:
                return True
        except Exception:
            pass  # pre-023 database: fall through to the headline check
    found = (
        sb.table("events").select("id")
        .eq("target_id", target_id).eq("headline", headline)
        .limit(1).execute().data or []
    )
    return bool(found)


def _insert_filing_event(sb, row: dict) -> None:
    """Insert a filing event, degrading to the pre-023 column set if needed."""
    global _EVENT_COLUMNS_OK
    if _EVENT_COLUMNS_OK:
        try:
            sb.table("events").insert(row).execute()
            return
        except Exception as exc:
            message = str(exc)
            if "column" not in message.lower() and "PGRST204" not in message:
                raise
            _EVENT_COLUMNS_OK = False
            log.warning("events is missing the migration 023 columns (%s). Writing the legacy shape.",
                        message[:120])
    # Without published_at, created_at has to carry the filing time, as it did before.
    sb.table("events").insert({
        "target_id": row["target_id"],
        "headline": row["headline"],
        "created_at": row["published_at"],
        "cached_analysis": row["cached_analysis"],
    }).execute()


def run_sec_scout():
    sb = get_supabase()

    targets = (
        sb.table("targets")
        .select("id, name, ticker, target_type")
        .eq("status", "tracking")
        .in_("target_type", ["COMPANY", "PRODUCT"])
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
            headline = _filing_headline(filing, company)

            # Idempotency: one event per filing. Keyed on the accession URL, since
            # the headline no longer carries the date that used to make it unique.
            if _filing_already_stored(sb, target["id"], url, headline):
                continue

            row = {
                "target_id": target["id"],
                "headline": headline,
                "summary": f"{form_type} filed with the SEC on {filing_date}.",
                "source_title": headline,
                "source_url": url,
                "published_at": _filing_published_at(filing),
                "cached_analysis": f"Source: {url}",
            }
            _insert_filing_event(sb, row)
            log.info("  New filing event: %s | %s | %s", ticker, form_type, filing_date)
            total_new += 1

    log.info("sec_scout complete. New filing events: %d", total_new)
    return {"tickers_checked": len(ticker_to_target), "filing_events_created": total_new}


if __name__ == "__main__":
    from logging_setup import setup_logging
    from pipeline_telemetry import step

    setup_logging()
    with step("sec_scout") as s:
        m = run_sec_scout()
        s.rows(m["filing_events_created"])
        s.note(**m)
