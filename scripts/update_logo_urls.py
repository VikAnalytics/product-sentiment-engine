#!/usr/bin/env python3
"""
Update targets.domain and targets.logo_url for companies only. Products do not get domain/logo.
Uses one batched Gemini call for all companies that need a domain, then updates DB.

Run from project root:
  PYTHONPATH=src python scripts/update_logo_urls.py

Options:
  --dry-run   Only print what would be updated, do not write to DB.
  --list      List all targets with current logo_url and domain.
  --no-ai     Use name-based guess only (no Gemini calls).
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from config import get_supabase
from domain_resolver import resolve_domains_batch

CLEARBIT_BASE = "https://logo.clearbit.com"


def main():
    dry_run = "--dry-run" in sys.argv
    list_only = "--list" in sys.argv
    use_ai = "--no-ai" not in sys.argv

    supabase = get_supabase()
    resp = supabase.table("targets").select("*").execute()
    targets = getattr(resp, "data", None) or []

    if list_only:
        print("Targets (id | name | type | domain | logo_url)")
        print("-" * 80)
        for t in targets:
            print(f"  {t.get('id')} | {t.get('name')} | {t.get('target_type')} | {t.get('domain') or '-'} | {t.get('logo_url') or '-'}")
        return

    # Only companies get domain/logo; skip products
    companies = [t for t in targets if (t.get("target_type") or "").strip().upper() == "COMPANY"]
    need_domain = [t for t in companies if not (t.get("domain") or "").strip()]
    names_to_resolve = list({(t.get("name") or "").strip() for t in need_domain if (t.get("name") or "").strip()})

    if not names_to_resolve:
        print("No companies missing domain. Nothing to update.")
        return

    # One (or few) batched API call(s) for all companies
    name_to_domain = resolve_domains_batch(names_to_resolve, use_ai=use_ai)

    updated = 0
    for t in companies:
        tid = t.get("id")
        name = (t.get("name") or "").strip()
        current_domain = (t.get("domain") or "").strip()
        domain = current_domain or name_to_domain.get(name) or ""
        current_logo = (t.get("logo_url") or "").strip()

        if not domain:
            continue
        logo_url = f"{CLEARBIT_BASE}/{domain}"
        needs_domain = not current_domain
        needs_logo = current_logo != logo_url
        if not needs_domain and not needs_logo:
            continue

        payload = {}
        if needs_domain:
            payload["domain"] = domain
        if needs_logo:
            payload["logo_url"] = logo_url

        if dry_run:
            print(f"Would set for {name!r} (id={tid}): {payload}")
        else:
            try:
                supabase.table("targets").update(payload).eq("id", tid).execute()
                print(f"Updated {name!r} (id={tid}): {payload}")
            except Exception as e:
                print(f"Failed {name!r} (id={tid}): {e}", file=sys.stderr)
        updated += 1

    print(f"Done. {'Would update' if dry_run else 'Updated'} {updated} company/companies.")


if __name__ == "__main__":
    main()
