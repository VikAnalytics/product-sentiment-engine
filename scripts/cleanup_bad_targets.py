"""
Clean up targets the scout should never have created.

Before the name guards in scout._is_junk_name, every name the extraction model
produced became a permanently tracked target: a COMPANY literally named "None",
countries and central banks as companies, and a second "Meta Platforms" beside
the existing "Meta". The tracker then searched HN, Reddit and Google News for
each of them daily.

Six passes, each independently selectable:

  sentinels   "None", "NONE" and friends. Target and its events are deleted —
              there is nothing to keep.
  countries   Countries, blocs, central banks and armed groups held as COMPANY.
              Retired (status='archived'), not deleted: their events are real
              news, and archiving keeps them out of the tracker and the report.
  duplicates  Targets whose normalized names now collide — "Chevron Corporation"
              onto "Chevron". Merged with scripts/merge_duplicate_targets.merge_into,
              keeping the row that has a ticker.
  tickers     Tickers known to point at the wrong company. "Motorola" carries
              MSI, which is Motorola Solutions, the public-safety radio company —
              the target tracks Motorola Mobility phones, so the simulator could
              trade MSI on a phone launch.
  products    A reviewed list of product targets that are descriptions rather
              than names ("AI Model", "New Treadmills"). Archived, not deleted,
              so their events survive on the parent company. Real products whose
              names end in a generic word ("Gemini app") were left alone.
  unsourced   Recent events still holding a model paraphrase as their headline.
              Deletes their sentiment readings too, so it is opt-in via --only.

Read-only by default.

Usage:
    PYTHONPATH=src python scripts/cleanup_bad_targets.py
    PYTHONPATH=src python scripts/cleanup_bad_targets.py --apply
    PYTHONPATH=src python scripts/cleanup_bad_targets.py --only duplicates --apply
"""
import argparse
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone

_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_src = os.path.join(_root, "src")
for _p in (_root, _src):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from config import get_supabase, fetch_all_rows  # noqa: E402
from normalize import normalize_target_name  # noqa: E402
from scout import JUNK_NAME_SENTINELS, NON_COMPANY_NAMES, _is_junk_name  # noqa: E402
from scripts.merge_duplicate_targets import merge_into  # noqa: E402

# Tickers that point at a different company than the target tracks.
# name -> (wrong ticker, why)
MISMATCHED_TICKERS = {
    "Motorola": ("MSI", "MSI is Motorola Solutions; this target tracks Motorola Mobility phones (Lenovo)"),
}

# Product targets that are descriptions rather than product names, reviewed one
# by one on 2026-09-23. Id and name must both match before anything is archived,
# so a renamed or re-used id is skipped rather than silently retired. Real
# products whose names merely end in a generic word — "Gemini app", "Fire TV app",
# "Sport Open Earbuds" — were deliberately left tracking.
ARCHIVE_PRODUCTS = {
    198: "new AirTag",
    306: "Starfield Free Lanes update",
    321: "AI-powered social apps",
    339: "Quick Resume feature update",
    341: "‘Tasks’ app",
    399: "Gemini features",
    424: "Hollow Knight (update)",
    453: "The White House App",
    537: "AI dictation app",
    548: "AI Model",
    653: "Gemini AI app",
    671: "Codex Update",
    762: "ComfyUI Tools",
    770: "Thus Chip",
    788: "AI app",
    792: "AI Agent Service",
    796: "Vibe-coding app",
    820: "AI Price History Feature",
    822: "Rocket-Powered Car",
    955: "Various AI Tools",
    969: "AI song cover feature",
    976: "Large Language Model",
    978: "AI-powered tools",
    979: "New all-electric Cadillac Vistiq",
    1100: "Apple Intelligence Features",
    1106: "AI Photo Editing Tools",
    1162: "Smart Circuit Breaker",
    1165: "Texture and Grain Controls",
    1166: "New Fitness Tracker",
    1169: "New Treadmills",
}

PASSES = ("sentinels", "countries", "duplicates", "tickers", "products", "unsourced")

# How far back the "unsourced" pass reaches. The web feed shows 48 hours, and
# older paraphrase events are out of sight in per-target history.
UNSOURCED_DAYS = 2


def _load_targets(sb):
    return fetch_all_rows(
        lambda: sb.table("targets")
        .select("id, name, target_type, status, ticker, parent_target_id")
        .order("id")
    )


def _event_count(sb, target_id: int) -> int:
    rows = sb.table("events").select("id").eq("target_id", target_id).execute().data or []
    return len(rows)


def _sentiment_count(sb, target_id: int) -> int:
    rows = sb.table("sentiment").select("id").eq("target_id", target_id).execute().data or []
    return len(rows)


def clean_sentinels(sb, targets, apply: bool) -> int:
    hits = [t for t in targets if (t["name"] or "").strip().lower() in JUNK_NAME_SENTINELS]
    print(f"\nsentinels: {len(hits)} target(s)")
    for t in hits:
        events, readings = _event_count(sb, t["id"]), _sentiment_count(sb, t["id"])
        print(f"  {'DELETE' if apply else 'would delete'} {t['id']} {t['name']!r} "
              f"[{t['target_type']}], {events} event(s) and {readings} sentiment row(s)")
        if apply:
            # The live FK on sentiment.target_id does not cascade, whatever
            # migration 000 says, so clear the children in dependency order.
            sb.table("sentiment").delete().eq("target_id", t["id"]).execute()
            sb.table("events").delete().eq("target_id", t["id"]).execute()
            sb.table("targets").delete().eq("id", t["id"]).execute()
    return len(hits)


def clean_countries(sb, targets, apply: bool) -> int:
    hits = [
        t for t in targets
        if t["target_type"] == "COMPANY"
        and t["status"] == "tracking"
        and (t["name"] or "").strip().lower() in NON_COMPANY_NAMES
    ]
    print(f"\ncountries: {len(hits)} target(s) held as COMPANY")
    for t in hits:
        print(f"  {'ARCHIVE' if apply else 'would archive'} {t['id']} {t['name']!r} "
              f"({_event_count(sb, t['id'])} event(s) kept)")
        if apply:
            sb.table("targets").update({"status": "archived"}).eq("id", t["id"]).execute()
    return len(hits)


def clean_duplicates(sb, targets, apply: bool) -> int:
    groups = defaultdict(list)
    for t in targets:
        if t["status"] != "tracking":
            continue
        groups[(t["target_type"], normalize_target_name(t["name"]))].append(t)
    collisions = [rows for rows in groups.values() if len(rows) > 1]
    print(f"\nduplicates: {len(collisions)} group(s)")
    merged = 0
    for rows in collisions:
        # Keep the row with a ticker, then the one with the most events, then the oldest.
        rows = sorted(rows, key=lambda r: (r["ticker"] is None, -_event_count(sb, r["id"]), r["id"]))
        keep, extras = rows[0], rows[1:]
        for extra in extras:
            print(f"  {'MERGE' if apply else 'would merge'} {extra['id']} {extra['name']!r} "
                  f"→ {keep['id']} {keep['name']!r} (ticker {keep['ticker']})")
            if apply:
                merge_into(sb, keep["id"], extra["id"], dry_run=False)
            merged += 1
    return merged


def clean_tickers(sb, targets, apply: bool) -> int:
    fixed = 0
    print(f"\ntickers: checking {len(MISMATCHED_TICKERS)} known mismatch(es)")
    for t in targets:
        entry = MISMATCHED_TICKERS.get((t["name"] or "").strip())
        if not entry or t["ticker"] != entry[0]:
            continue
        print(f"  {'CLEAR' if apply else 'would clear'} ticker {t['ticker']} on {t['id']} {t['name']!r}"
              f"\n      {entry[1]}")
        if apply:
            sb.table("targets").update({"ticker": None}).eq("id", t["id"]).execute()
        fixed += 1
    return fixed


def clean_products(sb, targets, apply: bool) -> int:
    """Archive the reviewed list of description-style product targets."""
    by_id = {t["id"]: t for t in targets}
    archived = skipped = 0
    print(f"\nproducts: {len(ARCHIVE_PRODUCTS)} reviewed name(s)")
    for tid, expected in ARCHIVE_PRODUCTS.items():
        target = by_id.get(tid)
        if not target or target["name"] != expected:
            found = repr(target["name"]) if target else "nothing"
            print(f"  skip {tid}: expected {expected!r}, found {found}")
            skipped += 1
            continue
        if target["status"] != "tracking":
            skipped += 1
            continue
        print(f"  {'ARCHIVE' if apply else 'would archive'} {tid} {target['name']!r} "
              f"({_event_count(sb, tid)} event(s) kept)")
        if apply:
            sb.table("targets").update({"status": "archived"}).eq("id", tid).execute()
        archived += 1
    if skipped:
        print(f"  {skipped} already archived, renamed or missing")
    return archived


def clean_unsourced(sb, apply: bool, days: int) -> int:
    """
    Delete recent events that still hold a model paraphrase as their headline.

    Their article was never stored, so there is nothing to restore them from —
    they can only be removed or left to age out of the feed. Their sentiment
    readings go too, which is the real cost: those are genuine scored data.
    SEC filings are exempt; they have their own headline shape and were
    repaired by scripts/backfill_sec_events.py.
    """
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    rows = fetch_all_rows(
        lambda: sb.table("events")
        .select("id, headline, source_url, published_at")
        .gte("published_at", since)
        .order("id")
    )
    doomed = [r for r in rows if not r.get("source_url") and not (r["headline"] or "").startswith("[")]
    readings = 0
    for row in doomed:
        readings += len(sb.table("sentiment").select("id").eq("event_id", row["id"]).execute().data or [])
    print(f"\nunsourced: {len(doomed)} paraphrase event(s) in the last {days} day(s), "
          f"carrying {readings} sentiment reading(s)")
    for row in doomed[:8]:
        print(f"  {'DELETE' if apply else 'would delete'} {row['id']} {row['headline'][:70]}")
    if len(doomed) > 8:
        print(f"  ... and {len(doomed) - 8} more")
    if apply:
        for row in doomed:
            # sentiment.event_id is ON DELETE SET NULL, but a reading with no
            # event is orphaned noise, so remove it with its event.
            sb.table("sentiment").delete().eq("event_id", row["id"]).execute()
            sb.table("events").delete().eq("id", row["id"]).execute()
    return len(doomed)


def report_generic_products(targets) -> None:
    """List only. Many of these are real products, and the guard is for new ones."""
    hits = []
    for t in targets:
        if t["target_type"] != "PRODUCT" or t["status"] != "tracking":
            continue
        reason = _is_junk_name(t["name"], "PRODUCT")
        if reason:
            hits.append((t["id"], t["name"], reason))
    print(f"\nreview (not touched): {len(hits)} product target(s) the new guard would refuse today")
    for tid, name, reason in hits[:20]:
        print(f"  {tid} {name!r} — {reason}")
    if len(hits) > 20:
        print(f"  ... and {len(hits) - 20} more")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="Write the changes (default: print only)")
    ap.add_argument("--only", choices=PASSES, action="append", default=[],
                    help="Run only this pass (repeatable)")
    ap.add_argument("--days", type=int, default=UNSOURCED_DAYS,
                    help=f"How far back the unsourced pass reaches (default: {UNSOURCED_DAYS})")
    args = ap.parse_args()

    passes = args.only or [p for p in PASSES if p != "unsourced"]
    sb = get_supabase()
    targets = _load_targets(sb)
    print(f"{len(targets)} targets loaded. Mode: {'APPLY' if args.apply else 'dry run'}")

    counts = {}
    if "sentinels" in passes:
        counts["sentinels"] = clean_sentinels(sb, targets, args.apply)
    if "countries" in passes:
        counts["countries"] = clean_countries(sb, targets, args.apply)
    if "duplicates" in passes:
        counts["duplicates"] = clean_duplicates(sb, targets, args.apply)
    if "tickers" in passes:
        counts["tickers"] = clean_tickers(sb, targets, args.apply)
    if "products" in passes:
        counts["products"] = clean_products(sb, targets, args.apply)
    if "unsourced" in passes:
        counts["unsourced"] = clean_unsourced(sb, args.apply, args.days)
    report_generic_products(targets)

    print("\nSummary:", ", ".join(f"{k}={v}" for k, v in counts.items()) or "nothing selected")
    if not args.apply:
        print("Dry run — nothing was written. Re-run with --apply.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
