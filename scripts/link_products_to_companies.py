#!/usr/bin/env python3
"""
One-off: link PRODUCT targets to COMPANY targets by setting parent_target_id.
Edit the PRODUCT_TO_COMPANY mapping below, then run from project root:
  PYTHONPATH=src python scripts/link_products_to_companies.py
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from config import get_supabase


# Edit this mapping: product name (exact match) -> company name (exact match).
# Pre-filled from your DB; add/remove as needed. Run without --list to apply.
# Note: DB may use curly apostrophe (\u2019); if a product is skipped, try adding it with that character.
CURLY_APOS = "\u2019"  # ' (right single quotation mark)
PRODUCT_TO_COMPANY = {
    # Google (curly apostrophe in DB for Gemini's)
    "Gemini's Canvas in AI Mode": "Google",
    "Gemini" + CURLY_APOS + "s Canvas in AI Mode": "Google",
    # OpenAI
    "ChatGPT's 'adult mode'": "OpenAI",
    "ChatGPT" + CURLY_APOS + "s 'adult mode'": "OpenAI",
    # Apple
    "MacBook Neo and iPhone 17e": "Apple",
    "MacBook Neo": "Apple",
    "iPhone 17e": "Apple",
    "M4 iPad Air": "Apple",
    "iPad Air M4": "Apple",
    "MacBook Air M5": "Apple",
    "MacBook Pro M5 Pro/Max": "Apple",
    "M5 Pro": "Apple",
    # Amazon
    "Amazon Connect Health": "Amazon",
    "Fire TV app (redesigned)": "Amazon",
    "Fire TV app": "Amazon",
    # Google
    "Google Pixel 10a": "Google",
    "Pixel Buds 2a": "Google",
    # Samsung
    "Samsung Galaxy Book 6 Pro": "Samsung",
    "Samsung Galaxy Buds 4": "Samsung",
    "Samsung Galaxy Buds 4 Pro": "Samsung",
    "Samsung Galaxy S26 Ultra": "Samsung",
    "Galaxy Buds 4": "Samsung",
    "Galaxy Buds 4 Pro": "Samsung",
    "Galaxy S26 Ultra": "Samsung",
    # OpenAI
    "GPT-5.4": "OpenAI",
    # Xbox / Valve / Netflix / Dell / etc.
    "Project Helix": "Xbox",
    "Roklue": "Roku",
    "Steam Machine": "Valve",
    "Steam Frame": "Valve",
    "Steam Controller": "Valve",
    "Overcooked! All You Can Eat (Netflix version)": "Netflix",
    "Overcooked! All You Can Eat (Netflix's custom version)": "Netflix",
    "Exclusive Threads": "Meta",
    "Dell XPS 14 (2026)": "Dell",
    "XPS 14 (2026)": "Dell",
    "Spectre I": "Dell",
    "ASUS ProArt GoPro Edition PX13": "ASUS",
    "Ambient Dreamie": "Ambient",
    "Seattle Ultrasonics C-200": "Seattle Ultrasonics",
    "Deveillance Spectre I": "Deveillance",
    "Falcon Northwest FragBox": "Falcon Northwest",
    "DART spacecraft": "NASA",
    "AI-powered chat rephraser (Roblox)": "Roblox",
    # Capcom / Nintendo / Bandai Namco / game studios
    "Pragmata": "Capcom",
    "Sketchbook demo (for Pragmata)": "Capcom",
    "Pragmata Sketchbook Demo": "Capcom",
    "Pokémon Pokopia": "Nintendo",
    "Peakychu": "Nintendo",
    "Mosslax": "Nintendo",
    "Blue Prince": "Bandai Namco",
    "Slay the Spire 2": "Mega Crit",
    "Minishoot' Adventures": "Tribute Games",
    "InKonbini: One Store. Many Stories": "Tribute Games",
    "Mixtape": "Tribute Games",
    "Denshattack!": "Bandai Namco",
    "Ratatan": "Bandai Namco",
    "Toem 2": "Wishfully",
    "Grave Seasons": "Tribute Games",
    "Scott Pilgrim EX": "Tribute Games",
    "Planet of Lana II: Children of the Leaf": "Thunderful Publishing",
    "The Legend of Khiimori": "Lunacy Studios",
    "Lost and Found Co.": "Studio Ortica",
    "Ratcheteer DX": "Tribute Games",
    "Birds Watching": "Human Computer",
    "My Little Puppy": "Dreamotion",
    "The House of Hikmah": "Aesir Interactive",
    "Ballgame": "Weekend Games",
    "Echobreaker": "Upstream Arcade",
    "Öoo": "Panic",
}


def main():
    import argparse
    p = argparse.ArgumentParser(description="Link products to companies in targets table")
    p.add_argument("--list", action="store_true", help="List all targets (id, name, type) and exit")
    p.add_argument("--dry-run", action="store_true", help="Show what would be updated, don't write")
    args = p.parse_args()

    supabase = get_supabase()
    resp = supabase.table("targets").select("id, name, target_type, parent_target_id").execute()
    targets = getattr(resp, "data", None) or []

    companies = {t["name"]: t["id"] for t in targets if (t.get("target_type") or "").upper() == "COMPANY"}
    products = [t for t in targets if (t.get("target_type") or "").upper() == "PRODUCT"]

    if args.list:
        print("Companies:")
        for t in targets:
            if (t.get("target_type") or "").upper() == "COMPANY":
                print(f"  id={t['id']}  name={t['name']!r}")
        print("\nProducts:")
        for t in products:
            parent = t.get("parent_target_id")
            print(f"  id={t['id']}  name={t['name']!r}  parent_target_id={parent}")
        print("\nEdit PRODUCT_TO_COMPANY in this script and run without --list to link.")
        return

    if not PRODUCT_TO_COMPANY:
        print("PRODUCT_TO_COMPANY is empty. Add product_name -> company_name and run again.")
        print("Run with --list to see exact names in your DB.")
        return

    name_to_id = {t["name"]: t["id"] for t in targets}
    updates = []
    for product_name, company_name in PRODUCT_TO_COMPANY.items():
        if product_name not in name_to_id:
            print(f"  Skip (product not found): {product_name!r}")
            continue
        if company_name not in companies:
            print(f"  Skip (company not found): {company_name!r}")
            continue
        product_id = name_to_id[product_name]
        company_id = companies[company_name]
        updates.append((product_id, product_name, company_name, company_id))

    if not updates:
        print("No valid product->company pairs. Check names (use --list).")
        return

    for product_id, product_name, company_name, company_id in updates:
        print(f"  {product_name!r} -> {company_name!r} (product_id={product_id}, company_id={company_id})")

    if args.dry_run:
        print("\nDry run. Run without --dry-run to apply.")
        return

    for product_id, product_name, company_name, company_id in updates:
        supabase.table("targets").update({"parent_target_id": company_id}).eq("id", product_id).execute()
        print(f"  Updated id={product_id} ({product_name!r}) -> parent_target_id={company_id}")
    print("Done.")


if __name__ == "__main__":
    main()
