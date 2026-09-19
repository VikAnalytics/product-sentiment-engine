"""
Backfill SPY and QQQ values onto existing simulator snapshots.

Snapshots taken before migration 021 have no benchmark, so the growth chart shows
the portfolio with nothing to judge it against. This fills them in so the whole
history is comparable, not just snapshots taken from now on.

Each value is what the starting capital would be worth had it been invested in
that index on the simulator's inception date, which is exactly how run_snapshot
records it going forward.

Usage:
    PYTHONPATH=src python scripts/backfill_sim_benchmarks.py --dry-run
    PYTHONPATH=src python scripts/backfill_sim_benchmarks.py
"""
import argparse
import logging
import os
import sys
from datetime import date

_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_src = os.path.join(_root, "src")
if _src not in sys.path:
    sys.path.insert(0, _src)

from config import SIM_STARTING_CAPITAL, get_supabase  # noqa: E402
from sim_trader import _benchmark_values, _inception_date  # noqa: E402

log = logging.getLogger("backfill_sim_benchmarks")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true", help="compute but write nothing")
    ap.add_argument("--force", action="store_true", help="recompute rows that already have values")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    sb = get_supabase()
    snaps = (
        sb.table("sim_snapshots").select("*").order("snapshot_date").execute().data or []
    )
    if not snaps:
        log.info("no snapshots to backfill")
        return 0

    portfolio = (sb.table("sim_portfolio").select("*").limit(1).execute().data or [{}])
    inception = _inception_date(sb, portfolio[0] if portfolio else {})
    log.info("inception: %s, %d snapshot(s)\n", inception, len(snaps))

    written = 0
    for snap in snaps:
        on = date.fromisoformat(snap["snapshot_date"])
        already = snap.get("spy_value") is not None and snap.get("qqq_value") is not None
        if already and not args.force:
            log.info("%s  already has benchmarks, skipping", on)
            continue

        vals = _benchmark_values(inception, on, SIM_STARTING_CAPITAL)
        total = float(snap["total_value"])
        parts = []
        for key, val in vals.items():
            label = key.replace("_value", "").upper()
            parts.append(f"{label} ${val:.2f} ({total - val:+.2f})" if val is not None
                         else f"{label} n/a")
        log.info("%s  portfolio $%8.2f   %s", on, total, "   ".join(parts))

        if all(v is None for v in vals.values()):
            continue
        if args.dry_run:
            written += 1
            continue
        try:
            sb.table("sim_snapshots").update(vals).eq("id", snap["id"]).execute()
            written += 1
        except Exception as exc:
            log.warning("  write failed for %s: %s", on, exc)

    log.info("\n%s %d snapshot(s)", "would update" if args.dry_run else "updated", written)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
