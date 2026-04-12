"""
ai_link_products.py — Use OpenAI to identify parent companies for unlinked product targets.
If the parent company doesn't exist in the DB, it is created (with domain + logo resolved).

Usage:
    PYTHONPATH=src python scripts/ai_link_products.py           # preview only (dry run)
    PYTHONPATH=src python scripts/ai_link_products.py --apply   # write to DB
"""

import argparse
import json
import logging
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from config import get_supabase, get_json_model
from normalize import normalize_target_name
from domain_resolver import resolve_domain

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger(__name__)

BATCH_SIZE = 50


def fetch_unlinked_products(sb):
    rows = []
    offset = 0
    while True:
        resp = (sb.table("targets").select("id, name")
                .eq("target_type", "PRODUCT").is_("parent_target_id", "null")
                .range(offset, offset + 999).execute())
        batch = resp.data or []
        rows.extend(batch)
        if len(batch) < 1000:
            break
        offset += 1000
    return rows


def fetch_companies(sb):
    rows = []
    offset = 0
    while True:
        resp = (sb.table("targets").select("id, name")
                .eq("target_type", "COMPANY")
                .range(offset, offset + 999).execute())
        batch = resp.data or []
        rows.extend(batch)
        if len(batch) < 1000:
            break
        offset += 1000
    return rows


def resolve_parent_id(company_name: str, companies: list):
    """Match AI-returned company name to DB company (exact → normalized). Returns id or None."""
    if not company_name or company_name.upper() in ("NONE", "UNKNOWN", ""):
        return None
    for c in companies:
        if c["name"].strip().lower() == company_name.strip().lower():
            return c["id"]
    norm = normalize_target_name(company_name)
    for c in companies:
        if normalize_target_name(c["name"]) == norm:
            return c["id"]
    return None


def insert_company(sb, company_name: str, companies: list):
    """
    Insert a new COMPANY target. Resolves domain + logo via AI.
    Appends to companies list so subsequent products in the same run can match it.
    Returns the new company id.
    """
    log.info("    🌐 Resolving domain for '%s'...", company_name)
    domain = resolve_domain(company_name, target_type="company", use_ai=True)
    row = {
        "name": company_name,
        "target_type": "COMPANY",
        "status": "tracking",
    }
    if domain:
        row["domain"] = domain
        row["logo_url"] = f"https://logo.clearbit.com/{domain}"
        log.info("    🔗 Domain: %s", domain)

    result = sb.table("targets").insert(row).execute()
    inserted = (result.data or [{}])[0]
    new_id = inserted.get("id")
    if new_id:
        companies.append({"id": new_id, "name": company_name})
        log.info("    💾 Created company: %s (id=%d)", company_name, new_id)
    return new_id


def ai_identify_parents(products: list, company_names: list) -> dict:
    """
    Ask OpenAI to identify parent company for each product.
    Returns {product_id: {"company": name, "known": bool}}
    - known=True  → company name is in our DB list
    - known=False → company exists but not in our DB yet (should be created)
    - company="NONE" → truly unknown or standalone product
    """
    model = get_json_model()
    product_list = "\n".join(f'- {p["id"]}: {p["name"]}' for p in products)
    company_list = ", ".join(company_names[:300])

    prompt = f"""You are a tech industry analyst. For each product below, identify its parent company.

Known companies (already in our database):
{company_list}

Products (format: id: name):
{product_list}

For each product return:
- "company": the parent company name (use exact name from known list if it matches, otherwise the real company name)
- "known": true if the company is in the known list, false if it exists but is missing from the list, null if truly unknown

Return JSON only — object mapping product id (string) to {{"company": "...", "known": true/false/null}}.
Use "NONE" for company if the product has no clear parent (e.g. it IS a company, or parent is unknown).
Example: {{"123": {{"company": "Apple", "known": true}}, "456": {{"company": "Klei Entertainment", "known": false}}, "789": {{"company": "NONE", "known": null}}}}"""

    response = model.generate_content(prompt)
    try:
        return json.loads(response.text or "{}")
    except json.JSONDecodeError:
        log.warning("AI returned invalid JSON: %s", response.text[:200])
        return {}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Write to DB (default: dry run)")
    args = parser.parse_args()

    sb = get_supabase()
    products = fetch_unlinked_products(sb)
    companies = fetch_companies(sb)  # mutable — new companies appended during run
    company_names = [c["name"] for c in companies]

    log.info("Unlinked products: %d | Known companies: %d\n", len(products), len(companies))
    if not products:
        log.info("No unlinked products found.")
        return

    to_link = []      # (product, company_name, parent_id)
    to_create = []    # (product, company_name) — company needs inserting first
    standalone = []   # products with no known parent

    for i in range(0, len(products), BATCH_SIZE):
        batch = products[i:i + BATCH_SIZE]
        log.info("Batch %d/%d...", i // BATCH_SIZE + 1, (len(products) + BATCH_SIZE - 1) // BATCH_SIZE)

        result = ai_identify_parents(batch, company_names)

        for product in batch:
            pid = str(product["id"])
            entry = result.get(pid, {})
            if isinstance(entry, str):
                # Fallback: old format
                entry = {"company": entry, "known": entry.upper() not in ("NONE", "UNKNOWN")}

            company_name = entry.get("company", "NONE") if isinstance(entry, dict) else "NONE"
            known = entry.get("known") if isinstance(entry, dict) else None

            if not company_name or company_name.upper() in ("NONE", "UNKNOWN"):
                standalone.append(product)
                continue

            parent_id = resolve_parent_id(company_name, companies)
            if parent_id:
                to_link.append((product, company_name, parent_id))
                log.info("  ✓ %s → %s (id=%d)", product["name"], company_name, parent_id)
            elif known is False:
                to_create.append((product, company_name))
                log.info("  + %s → '%s' (will create)", product["name"], company_name)
            else:
                standalone.append(product)
                log.info("  - %s → '%s' (no match, skipping)", product["name"], company_name)

    log.info("\nSummary: %d link, %d create+link, %d standalone/unknown",
             len(to_link), len(to_create), len(standalone))

    if not args.apply:
        log.info("\nDry run — pass --apply to write to DB.")
        return

    # Create missing companies + link
    for product, company_name in to_create:
        existing_id = resolve_parent_id(company_name, companies)
        if not existing_id:
            existing_id = insert_company(sb, company_name, companies)
        if existing_id:
            sb.table("targets").update({"parent_target_id": existing_id}).eq("id", product["id"]).execute()
            log.info("  💾 Linked %s → %s (new)", product["name"], company_name)

    # Link existing matches
    for product, company_name, parent_id in to_link:
        sb.table("targets").update({"parent_target_id": parent_id}).eq("id", product["id"]).execute()
        log.info("  💾 Linked %s → %s", product["name"], company_name)

    log.info("\nDone. %d linked, %d new companies created.", len(to_link) + len(to_create), len(to_create))


if __name__ == "__main__":
    main()
