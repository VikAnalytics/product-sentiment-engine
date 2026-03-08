#!/usr/bin/env python3
"""
One-time cleanup: keep only one sentiment row per (target_id, pros, cons).
When multiple rows for the same target have identical pros and cons, delete the
duplicates and keep the one with the smallest id.

Going forward: sentiment table keeps saving pros/cons as usual (tracker/report).
Dashboard shows summarized/distinct data via target_sentiment_summary.

Run from project root:
  PYTHONPATH=src python scripts/deduplicate_sentiment_rows.py

Optional: --dry-run to print what would be deleted without deleting.
"""
import os
import sys
from collections import defaultdict

_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
os.chdir(_root)
sys.path.insert(0, os.path.join(_root, "src"))

from config import get_supabase


def main():
    dry_run = "--dry-run" in sys.argv
    if dry_run:
        print("DRY RUN — no rows will be deleted.")
    supabase = get_supabase()
    resp = supabase.table("sentiment").select("id, target_id, pros, cons").execute()
    rows = getattr(resp, "data", None) or []
    # Group by (target_id, pros, cons); normalize None to ""
    key_to_rows = defaultdict(list)
    for r in rows:
        pros = r.get("pros")
        cons = r.get("cons")
        key = (r["target_id"], pros if pros is not None else "", cons if cons is not None else "")
        key_to_rows[key].append(r["id"])
    # For each group, keep min(id), delete the rest
    to_delete = []
    for key, ids in key_to_rows.items():
        if len(ids) <= 1:
            continue
        ids_sorted = sorted(ids)
        to_delete.extend(ids_sorted[1:])  # keep ids_sorted[0]
    if not to_delete:
        print("No duplicate rows (same target_id + pros + cons) found.")
        return
    if dry_run:
        print(f"Would delete {len(to_delete)} duplicate sentiment row(s) (keep 1 per identical pros/cons per target).")
        return
    for sid in to_delete:
        supabase.table("sentiment").delete().eq("id", sid).execute()
    print(f"Done. Deleted {len(to_delete)} duplicate row(s).")


if __name__ == "__main__":
    main()
