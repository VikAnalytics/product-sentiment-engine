#!/usr/bin/env python3
"""
Backfill: grouped by target_id. For each target, combine all pros/cons from all its
sentiment rows, deduplicate with rule-based logic (word overlap + substring), and write
one row to target_sentiment_summary. Raw sentiment rows are not modified.

No API calls—uses only sentiment_dedupe (no Gemini). Run migration 007 first.

Run from project root:
  PYTHONPATH=src python scripts/dedupe_sentiment_in_db.py

Optional: --dry-run to print what would be written without updating.
"""
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone

_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
os.chdir(_root)
sys.path.insert(0, os.path.join(_root, "src"))

from config import get_supabase
from sentiment_dedupe import to_bullet_lines, dedupe_lines


def main():
    dry_run = "--dry-run" in sys.argv
    if dry_run:
        print("DRY RUN — no updates will be written.")
    supabase = get_supabase()
    resp = supabase.table("sentiment").select("id, target_id, pros, cons").execute()
    rows = getattr(resp, "data", None) or []
    by_target = defaultdict(list)
    for row in rows:
        by_target[row["target_id"]].append(row)
    written = 0
    for target_id, group in by_target.items():
        all_pros = []
        all_cons = []
        for row in group:
            for line in to_bullet_lines(row.get("pros") or ""):
                all_pros.append(line)
            for line in to_bullet_lines(row.get("cons") or ""):
                all_cons.append(line)
        if not all_pros and not all_cons:
            continue
        # Rule-based dedupe only (no API calls)
        new_pros = "\n".join(dedupe_lines(all_pros)).strip() if all_pros else ""
        new_cons = "\n".join(dedupe_lines(all_cons)).strip() if all_cons else ""
        if dry_run:
            total_pros_chars = sum(len(r.get("pros") or "") for r in group)
            total_cons_chars = sum(len(r.get("cons") or "") for r in group)
            print(f"target_id={target_id}: {len(group)} sentiment row(s) -> 1 summary row, pros {total_pros_chars} -> {len(new_pros)} chars, cons {total_cons_chars} -> {len(new_cons)} chars")
            written += 1
            continue
        supabase.table("target_sentiment_summary").upsert(
            {
                "target_id": target_id,
                "pros": new_pros or None,
                "cons": new_cons or None,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
            on_conflict="target_id",
        ).execute()
        written += 1
    print(f"Done. Wrote {written} target_sentiment_summary row(s)." if not dry_run else f"Would write {written} summary row(s). Run without --dry-run to apply.")


if __name__ == "__main__":
    main()
