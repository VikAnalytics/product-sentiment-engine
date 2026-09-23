"""
Rewrite SEC filing events that were stored before migration 023.

Every one of them reads "[8-K] NEWS CORP — 2026-09-22 SEC filing" and is
timestamped filing_date + 16:30Z. That was meant to say "after the close" but is
12:30 ET, mid-session, so price_correlator credited each filing with the
midday-to-close move at confidence='high'. Neither the acceptance time nor the
item codes were ever stored, though EDGAR returns both.

The accession URL survives in cached_analysis ("Source: https://www.sec.gov/
Archives/edgar/data/<cik>/<accession>"), which is enough to ask EDGAR again.
Each event gets its real headline, acceptance time, and source_url:

    [8-K] NEWS CORP — 2026-09-22 SEC filing      published_at 2026-09-22T16:30:00Z
    [8-K · Other events] NEWS CORP               published_at 2026-09-21T20:23:10Z

Events whose accession is no longer in EDGAR's recent window are left alone and
counted. Re-run price_correlator afterwards: it upserts on event_id, so the
corrected timestamps re-attribute themselves.

Read-only by default.

Usage:
    PYTHONPATH=src python scripts/backfill_sec_events.py
    PYTHONPATH=src python scripts/backfill_sec_events.py --apply
    PYTHONPATH=src python scripts/backfill_sec_events.py --limit 20 --apply
"""
import argparse
import os
import re
import sys
import time
from collections import defaultdict

_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_src = os.path.join(_root, "src")
for _p in (_root, _src):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import requests  # noqa: E402

from config import get_supabase, fetch_all_rows  # noqa: E402
from sec_scout import (  # noqa: E402
    EDGAR_HEADERS,
    SUBMISSIONS_URL,
    _filing_headline,
    _filing_published_at,
)

SOURCE_RE = re.compile(r"Source:\s*(https://www\.sec\.gov/Archives/edgar/data/(\d+)/([0-9]+))")
# "[8-K] NEWS CORP — 2026-09-22 SEC filing" -> company name
COMPANY_RE = re.compile(r"^\[[^\]]+\]\s*(.+?)\s+—\s+\d{4}-\d{2}-\d{2}\s+SEC filing$")


def _load_filing_events(sb):
    rows = fetch_all_rows(
        lambda: sb.table("events")
        .select("id, target_id, headline, cached_analysis, published_at, source_url")
        .like("headline", "[%")
        .order("id")
    )
    events = []
    for row in rows:
        match = SOURCE_RE.search(row.get("cached_analysis") or "")
        if not match:
            continue
        row["url"], row["cik"], row["accession"] = match.group(1), match.group(2), match.group(3)
        events.append(row)
    return events


def _fetch_filing_index(cik: str) -> dict:
    """accession (no dashes) -> {form_type, filing_date, accepted_at, items, company}."""
    url = SUBMISSIONS_URL.format(cik=cik.zfill(10))
    resp = requests.get(url, headers=EDGAR_HEADERS, timeout=20)
    resp.raise_for_status()
    data = resp.json()
    recent = data.get("filings", {}).get("recent", {})
    name = data.get("name", "")
    index = {}
    forms = recent.get("form", [])
    for i, form in enumerate(forms):
        accession = (recent.get("accessionNumber", [])[i] if i < len(recent.get("accessionNumber", [])) else "")
        index[accession.replace("-", "")] = {
            "form_type": form,
            "filing_date": recent.get("filingDate", [])[i] if i < len(recent.get("filingDate", [])) else "",
            "accepted_at": recent.get("acceptanceDateTime", [])[i] if i < len(recent.get("acceptanceDateTime", [])) else "",
            "items": recent.get("items", [])[i] if i < len(recent.get("items", [])) else "",
            "company": name,
        }
    return index


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="Write the changes (default: print only)")
    ap.add_argument("--limit", type=int, default=0, help="Only process this many events")
    args = ap.parse_args()

    sb = get_supabase()
    events = _load_filing_events(sb)
    if args.limit:
        events = events[: args.limit]
    print(f"{len(events)} filing event(s) carry a recoverable accession. "
          f"Mode: {'APPLY' if args.apply else 'dry run'}")

    by_cik = defaultdict(list)
    for event in events:
        by_cik[event["cik"]].append(event)
    print(f"{len(by_cik)} CIK(s) to fetch from EDGAR\n")

    updated = missing = failed = 0
    for cik, rows in by_cik.items():
        try:
            index = _fetch_filing_index(cik)
        except Exception as exc:
            print(f"  EDGAR error for CIK {cik}: {exc}")
            failed += len(rows)
            continue
        time.sleep(0.12)  # EDGAR asks for <= 10 req/sec

        for row in rows:
            filing = index.get(row["accession"])
            if not filing:
                missing += 1
                continue
            old_company = COMPANY_RE.match(row["headline"])
            company = filing["company"] or (old_company.group(1) if old_company else "")
            headline = _filing_headline(filing, company)
            published_at = _filing_published_at(filing)
            patch = {
                "headline": headline,
                "summary": f"{filing['form_type']} filed with the SEC on {filing['filing_date']}.",
                "source_title": headline,
                "source_url": row["url"],
                "published_at": published_at,
            }
            if updated < 8 or args.apply is False and updated < 12:
                print(f"  {row['id']}: {row['headline'][:54]}")
                print(f"        -> {headline[:54]}")
                print(f"        {row['published_at'][:19]} -> {published_at[:19]}")
            if args.apply:
                sb.table("events").update(patch).eq("id", row["id"]).execute()
            updated += 1

    print(f"\n{updated} event(s) {'updated' if args.apply else 'would be updated'}, "
          f"{missing} no longer in EDGAR's recent window, {failed} skipped on fetch errors")
    if args.apply:
        print("Run price_correlator next: it upserts on event_id and will re-attribute these.")
    else:
        print("Dry run — nothing was written. Re-run with --apply.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
