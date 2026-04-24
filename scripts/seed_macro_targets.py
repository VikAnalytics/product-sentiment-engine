#!/usr/bin/env python3
"""
Seed MACRO (geopolitics / regulatory) targets and their sector exposures.
Idempotent: skips rows that already exist by name.

Run from project root:
    PYTHONPATH=src python scripts/seed_macro_targets.py

Requires migration 017_macro_targets.sql to be applied first.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from config import get_supabase


# Theme name  →  (description, {sector: exposure_weight})
MACRO_THEMES = {
    "US-China Trade Tensions": (
        "Escalating trade, tech, and diplomatic friction between the US and China. "
        "Tariffs, export controls, retaliatory policy.",
        {
            "Technology":           1.00,
            "Consumer Electronics": 0.90,
            "Automotive & EV":      0.70,
            "Gaming":               0.50,
            "Social Media":         0.60,
        },
    ),
    "Russia-Ukraine Conflict": (
        "Ongoing war in Ukraine and Russia sanctions regime. Affects energy, "
        "defense spending, European financials, commodity flows.",
        {
            "Defense & Aerospace": 1.00,
            "Industrials":         0.70,
            "Transport":           0.60,
            "Finance & Fintech":   0.50,
        },
    ),
    "Middle East Tensions": (
        "Israel-Gaza conflict, Iran proxy escalation, Red Sea shipping disruption, "
        "Gulf state alignment shifts.",
        {
            "Defense & Aerospace": 0.80,
            "Transport":           0.90,
            "Industrials":         0.60,
        },
    ),
    "Semiconductor Export Controls": (
        "US/EU/Japan restrictions on advanced chip exports to China, Huawei, "
        "sanctioned entities. Impacts fab equipment, AI accelerators, memory.",
        {
            "Technology":           1.00,
            "Consumer Electronics": 0.90,
        },
    ),
    "Global Tariffs & Trade Policy": (
        "Blanket and sectoral tariffs, retaliatory duties, reshoring incentives, "
        "WTO disputes.",
        {
            "Retail":               0.90,
            "Consumer Electronics": 0.80,
            "Automotive & EV":      0.80,
            "Technology":           0.60,
            "Industrials":          0.60,
        },
    ),
    "OPEC & Energy Policy": (
        "OPEC+ production decisions, oil price swings, strategic reserve releases, "
        "LNG policy, renewables subsidies.",
        {
            "Transport":       0.90,
            "Industrials":     0.70,
            "Automotive & EV": 0.60,
        },
    ),
    "AI Regulation": (
        "EU AI Act, US executive orders, China AI governance, antitrust scrutiny "
        "of frontier labs.",
        {
            "Technology":   1.00,
            "Social Media": 0.70,
            "Media & Entertainment": 0.40,
        },
    ),
    "Climate & Clean Energy Policy": (
        "IRA incentives, EU Green Deal, carbon pricing, EV mandates, "
        "fossil fuel policy shifts.",
        {
            "Automotive & EV": 0.90,
            "Industrials":     0.80,
            "Transport":       0.60,
        },
    ),
}


def main():
    sb = get_supabase()

    for name, (description, sector_map) in MACRO_THEMES.items():
        # Find or create MACRO target
        existing = (
            sb.table("targets")
            .select("id, target_type")
            .eq("name", name)
            .limit(1)
            .execute()
            .data
            or []
        )

        if existing:
            tgt_id = existing[0]["id"]
            if existing[0]["target_type"] != "MACRO":
                sb.table("targets").update({"target_type": "MACRO"}).eq("id", tgt_id).execute()
                print(f"  upgraded existing target to MACRO: {name} (id={tgt_id})")
            else:
                print(f"  exists: {name} (id={tgt_id})")
        else:
            ins = (
                sb.table("targets")
                .insert({
                    "name": name,
                    "target_type": "MACRO",
                    "status": "tracking",
                    "description": description,
                    "sector": "Macro",
                })
                .execute()
            )
            tgt_id = ins.data[0]["id"]
            print(f"  created: {name} (id={tgt_id})")

        # Upsert sector exposures
        for sector, weight in sector_map.items():
            existing_exp = (
                sb.table("macro_sector_exposure")
                .select("id")
                .eq("macro_target_id", tgt_id)
                .eq("sector", sector)
                .limit(1)
                .execute()
                .data
                or []
            )
            if existing_exp:
                sb.table("macro_sector_exposure").update({
                    "exposure_weight": weight,
                }).eq("id", existing_exp[0]["id"]).execute()
            else:
                sb.table("macro_sector_exposure").insert({
                    "macro_target_id": tgt_id,
                    "sector": sector,
                    "exposure_weight": weight,
                }).execute()
        print(f"    → {len(sector_map)} sector exposures set")

    print(f"\nDone. Seeded {len(MACRO_THEMES)} MACRO themes.")


if __name__ == "__main__":
    main()
