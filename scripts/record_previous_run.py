"""
Record a summary row for a simulator run that was retired before migration 022.

Resets from now on write their own sim_runs row. This exists for the run retired
on 2026-09-19, where the reset happened before the table did, and for any case
where a summary needs reconstructing after the fact.

Defaults describe that run: it began on 2026-04-12 and finished at $1,099.12 with
57 trades on the log. Benchmarks are computed over the same window, so the
comparison matches what the run actually lived through.

Usage:
    PYTHONPATH=src python scripts/record_previous_run.py --dry-run
    PYTHONPATH=src python scripts/record_previous_run.py
"""
import argparse
import logging
import os
import sys
from datetime import date, datetime, timezone

_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_src = os.path.join(_root, "src")
if _src not in sys.path:
    sys.path.insert(0, _src)

from config import SIM_STARTING_CAPITAL, get_supabase  # noqa: E402
from sim_trader import _benchmark_values  # noqa: E402

log = logging.getLogger("record_previous_run")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--started", default="2026-04-12")
    ap.add_argument("--ended", default="2026-09-19")
    ap.add_argument("--final", type=float, default=1099.12)
    ap.add_argument("--trades", type=int, default=57)
    ap.add_argument("--note", default="closed 1 open position (HD) at reset")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    started, ended = date.fromisoformat(args.started), date.fromisoformat(args.ended)
    sb = get_supabase()

    benchmarks = _benchmark_values(started, ended, SIM_STARTING_CAPITAL)
    row = {
        "started_at": datetime.combine(started, datetime.min.time(), timezone.utc).isoformat(),
        "ended_at": datetime.combine(ended, datetime.min.time(), timezone.utc).isoformat(),
        "starting_value": SIM_STARTING_CAPITAL,
        "final_value": args.final,
        "return_pct": round((args.final - SIM_STARTING_CAPITAL) / SIM_STARTING_CAPITAL * 100, 4),
        "trades": args.trades,
        "note": args.note,
        **benchmarks,
    }

    log.info("%s to %s", started, ended)
    log.info("  strategy   $%8.2f  %+.2f%%", row["final_value"], row["return_pct"])
    for key in ("spy_value", "qqq_value"):
        val = row.get(key)
        label = key.replace("_value", "").upper()
        if val is None:
            log.info("  %-10s n/a", label)
        else:
            log.info("  %-10s $%8.2f  %+.2f%%   run %+.2f vs it",
                     label, val, (val - SIM_STARTING_CAPITAL) / SIM_STARTING_CAPITAL * 100,
                     row["final_value"] - val)

    if args.dry_run:
        log.info("dry run — nothing written")
        return 0

    try:
        existing = sb.table("sim_runs").select("id, ended_at").execute().data or []
    except Exception as exc:
        log.error("\nsim_runs is not available (%s).\nApply migration 022 first, then run this again.", exc)
        return 1

    if any((r.get("ended_at") or "").startswith(args.ended) for r in existing):
        log.info("a run ending %s is already recorded — nothing to do", args.ended)
        return 0

    sb.table("sim_runs").insert(row).execute()
    log.info("recorded")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
