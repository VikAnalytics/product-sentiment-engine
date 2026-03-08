#!/usr/bin/env python3
"""
Merge duplicate targets: reassign all events and sentiment from duplicate -> canonical,
update parent_target_id on targets that pointed to duplicate, then delete the duplicate.
Run from project root: PYTHONPATH=src python scripts/merge_duplicate_targets.py --merge CANONICAL_ID DUPLICATE_ID
Repeat --merge for each pair, or use --dry-run to preview.
"""
import sys
import os
import argparse
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from config import get_supabase


def merge_into(supabase, keep_id: int, merge_id: int, dry_run: bool) -> None:
    """Reassign merge_id's data to keep_id, then delete merge_id target."""
    if keep_id == merge_id:
        print(f"  Skip: same id {keep_id}")
        return
    # Resolve names for logging
    keep_r = supabase.table("targets").select("name").eq("id", keep_id).execute()
    merge_r = supabase.table("targets").select("name").eq("id", merge_id).execute()
    keep_name = (getattr(keep_r, "data", None) or [{}])[0].get("name", keep_id)
    merge_name = (getattr(merge_r, "data", None) or [{}])[0].get("name", merge_id)

    if dry_run:
        print(f"  Would merge {merge_id!r} ({merge_name}) into {keep_id!r} ({keep_name})")
        return

    # 1) events: target_id merge_id -> keep_id
    supabase.table("events").update({"target_id": keep_id}).eq("target_id", merge_id).execute()
    # 2) sentiment: target_id merge_id -> keep_id
    supabase.table("sentiment").update({"target_id": keep_id}).eq("target_id", merge_id).execute()
    # 3) targets that had parent_target_id = merge_id -> keep_id
    supabase.table("targets").update({"parent_target_id": keep_id}).eq("parent_target_id", merge_id).execute()
    # 4) delete the duplicate target
    supabase.table("targets").delete().eq("id", merge_id).execute()
    print(f"  Merged {merge_id} ({merge_name!r}) into {keep_id} ({keep_name!r})")


def main():
    p = argparse.ArgumentParser(description="Merge duplicate targets into a canonical one")
    p.add_argument("--merge", nargs=2, type=int, metavar=("CANONICAL_ID", "DUPLICATE_ID"), action="append", default=[], help="Merge DUPLICATE_ID into CANONICAL_ID (can repeat)")
    p.add_argument("--dry-run", action="store_true", help="Only print what would be done")
    args = p.parse_args()

    if not args.merge:
        print("Usage: --merge CANONICAL_ID DUPLICATE_ID [--merge CANONICAL_ID DUPLICATE_ID ...] [--dry-run]")
        print("Example: --merge 41 92   (merge target 92 into 41, then delete 92)")
        return

    supabase = get_supabase()
    for keep_id, merge_id in args.merge:
        merge_into(supabase, keep_id, merge_id, args.dry_run)

    if not args.dry_run and args.merge:
        print("Done.")


if __name__ == "__main__":
    main()
