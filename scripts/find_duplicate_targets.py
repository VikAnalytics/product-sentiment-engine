#!/usr/bin/env python3
"""
Find targets that are likely duplicates due to similar naming
(e.g. "M4 iPad Air" vs "iPad Air M4", "Fire TV app" vs "Fire TV app (redesigned)").
Groups by normalized name (lowercase, no parentheticals, sorted words).
Run from project root: PYTHONPATH=src python scripts/find_duplicate_targets.py
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from config import get_supabase
from normalize import normalize_target_name


def main():
    supabase = get_supabase()
    resp = supabase.table("targets").select("id, name, target_type").execute()
    targets = getattr(resp, "data", None) or []

    # Group by (target_type, normalized_name)
    groups = {}
    for t in targets:
        n = t.get("name") or ""
        ttype = (t.get("target_type") or "").upper()
        norm = normalize_target_name(n)
        if not norm:
            continue
        key = (ttype, norm)
        if key not in groups:
            groups[key] = []
        groups[key].append(t)

    # Report groups with more than one target
    dupes = [(k, v) for k, v in groups.items() if len(v) > 1]
    if not dupes:
        print("No duplicate groups found (same normalized name).")
        return

    print("Duplicate groups (same normalized name):\n")
    for (ttype, norm), items in sorted(dupes, key=lambda x: (x[0][0], x[0][1])):
        print(f"  [{ttype}] normalized = {norm!r}")
        for t in sorted(items, key=lambda x: x["name"]):
            print(f"    id={t['id']}  name={t['name']!r}")
        print()

    print("To merge: run scripts/merge_duplicate_targets.py with --merge ID_CANONICAL ID_DUPLICATE (repeat for each pair).")


if __name__ == "__main__":
    main()
