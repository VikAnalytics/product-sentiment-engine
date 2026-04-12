"""
ai_link_products.py — Use OpenAI to identify parent companies for unlinked product targets.

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

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger(__name__)

BATCH_SIZE = 50  # products per AI call


def fetch_unlinked_products(sb):
    rows = []
    offset = 0
    while True:
        resp = sb.table("targets").select("id, name").eq("target_type", "PRODUCT").is_("parent_target_id", "null").range(offset, offset + 999).execute()
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
        resp = sb.table("targets").select("id, name").eq("target_type", "COMPANY").range(offset, offset + 999).execute()
        batch = resp.data or []
        rows.extend(batch)
        if len(batch) < 1000:
            break
        offset += 1000
    return rows


def resolve_parent_id(company_name: str, companies: list) -> int | None:
    """Match AI-returned company name to a DB company (exact → normalized)."""
    if not company_name or company_name.upper() in ("NONE", "UNKNOWN", ""):
        return None
    # Exact match first
    for c in companies:
        if c["name"].strip().lower() == company_name.strip().lower():
            return c["id"]
    # Normalized match
    norm = normalize_target_name(company_name)
    for c in companies:
        if normalize_target_name(c["name"]) == norm:
            return c["id"]
    return None


def ai_identify_parents(products: list, company_names: list) -> dict:
    """
    Send a batch of product names to OpenAI.
    Returns {product_id: parent_company_name_or_NONE}.
    """
    model = get_json_model()
    product_list = "\n".join(f'- {p["id"]}: {p["name"]}' for p in products)
    company_list = ", ".join(company_names[:200])  # cap to avoid huge prompts

    prompt = f"""You are a tech industry analyst. For each product below, identify its parent company.
Only use company names from the provided list. If the parent company is not in the list or unknown, return "NONE".

Known companies:
{company_list}

Products (format: id: name):
{product_list}

Return JSON only — an object mapping each product id (as string) to the parent company name or "NONE".
Example: {{"123": "Apple", "456": "NONE", "789": "Google"}}"""

    response = model.generate_content(prompt)
    try:
        return json.loads(response.text or "{}")
    except json.JSONDecodeError:
        log.warning("AI returned invalid JSON: %s", response.text[:200])
        return {}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Write parent_target_id to DB (default: dry run)")
    args = parser.parse_args()

    sb = get_supabase()

    products = fetch_unlinked_products(sb)
    companies = fetch_companies(sb)
    company_names = [c["name"] for c in companies]

    log.info("Unlinked products: %d | Known companies: %d", len(products), len(companies))
    if not products:
        log.info("No unlinked products found.")
        return

    # Process in batches
    linked = []
    skipped = []

    for i in range(0, len(products), BATCH_SIZE):
        batch = products[i:i + BATCH_SIZE]
        log.info("Processing batch %d/%d...", i // BATCH_SIZE + 1, (len(products) + BATCH_SIZE - 1) // BATCH_SIZE)

        result = ai_identify_parents(batch, company_names)

        for product in batch:
            pid = str(product["id"])
            company_name = result.get(pid, "NONE")
            parent_id = resolve_parent_id(company_name, companies)

            if parent_id:
                linked.append((product, company_name, parent_id))
                log.info("  ✓ %s → %s (id=%d)", product["name"], company_name, parent_id)
            else:
                skipped.append(product)
                if company_name.upper() not in ("NONE", "UNKNOWN", ""):
                    log.info("  ~ %s → '%s' (not found in DB)", product["name"], company_name)

    log.info("\nSummary: %d to link, %d no match found", len(linked), len(skipped))

    if not args.apply:
        log.info("\nDry run — pass --apply to write to DB.")
        return

    for product, company_name, parent_id in linked:
        sb.table("targets").update({"parent_target_id": parent_id}).eq("id", product["id"]).execute()
        log.info("  💾 Linked %s → %s", product["name"], company_name)

    log.info("\nDone. %d products linked.", len(linked))


if __name__ == "__main__":
    main()
