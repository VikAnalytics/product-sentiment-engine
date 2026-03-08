#!/usr/bin/env python3
"""
Dry-run: test that SUPABASE_URL and SUPABASE_KEY in .env work.
Run from project root: python scripts/test_supabase_key.py
"""
import os
import sys

# Load .env from project root (parent of scripts/)
_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
os.chdir(_root)
sys.path.insert(0, os.path.join(_root, "src"))

# Now config will load .env from project root
from config import get_supabase

def main():
    print("Testing Supabase connection (using SUPABASE_URL + SUPABASE_KEY from .env)...")
    try:
        supabase = get_supabase()
        resp = supabase.table("targets").select("id").limit(1).execute()
        data = getattr(resp, "data", None) or []
        print("OK — connection works.")
        print(f"  targets table: read succeeded (sample rows: {len(data)}).")
    except Exception as e:
        print("FAILED — key or URL is wrong, or RLS/migrations issue.")
        if hasattr(e, "code"):
            print(f"  Code: {e.code}")
        if hasattr(e, "message"):
            print(f"  Message: {e.message}")
        if hasattr(e, "details"):
            print(f"  Details: {e.details}")
        print(f"  Full: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
