"""
Say out loud when a pipeline run went wrong, or never happened.

Every step already records its own health: pipeline_telemetry writes a row to
pipeline_runs with status success/degraded/failed and, for a degraded step, the
reason it gave itself. Nothing read those rows, which is how the engine spent
three months reporting success while writing nothing — OpenAI started answering
429 around 2026-06-10, every run still exited 0, and the silence was only found
in September.

Two modes, because they catch different failures:

  (default)     Look at the run that just finished. Exit 1 if any step failed or
                degraded, so the workflow goes red and GitHub sends its own mail.
  --heartbeat   Look for any successful run at all in the last N hours. A
                pipeline that never starts writes no row, so nothing inside a run
                can notice this one; it has to be asked from outside.

Both write a summary to $GITHUB_STEP_SUMMARY when that exists, so the reason is
visible in the run page rather than buried in the log.

Usage:
    PYTHONPATH=src python scripts/check_pipeline_health.py
    PYTHONPATH=src python scripts/check_pipeline_health.py --heartbeat --max-age-hours 26
"""
import argparse
import os
import sys
from datetime import datetime, timedelta, timezone

_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_src = os.path.join(_root, "src")
for _p in (_root, _src):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from config import get_supabase  # noqa: E402

# Steps a healthy weekday run always records. A step that never started writes
# no row at all, which reads as "fine" unless someone looks for the absence.
CORE_STEPS = [
    "scout", "sec_scout", "price_fetcher", "sim_execute",
    "tracker", "price_correlator", "sim_analyze", "report",
]

OK, DEGRADED, FAILED = "success", "degraded", "failed"


def _emit(lines: list) -> None:
    """Print, and repeat into the workflow's summary panel when there is one."""
    text = "\n".join(lines)
    print(text)
    summary = os.getenv("GITHUB_STEP_SUMMARY")
    if summary:
        try:
            with open(summary, "a", encoding="utf-8") as fh:
                fh.write(text + "\n")
        except OSError:
            pass


def _recent_runs(sb, hours: int) -> list:
    since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    return (
        sb.table("pipeline_runs")
        .select("step_name, status, started_at, duration_ms, rows_processed, error_message")
        .gte("started_at", since)
        .order("started_at")
        .execute()
        .data
    ) or []


def assess(runs: list, core_steps: list = None, hours: int = 6) -> tuple:
    """
    Decide whether a set of pipeline_runs rows is healthy.

    Pure, so the interesting cases — a degraded step, a step that never ran, one
    left marked running — are testable without a database. Returns
    (exit_code, lines).
    """
    core_steps = CORE_STEPS if core_steps is None else core_steps
    if not runs:
        return 1, [f"## Pipeline: no steps recorded in the last {hours}h",
                   "",
                   "Nothing ran, or telemetry could not be written. Check the workflow log."]

    # One row per step: the newest attempt is the one that counts, so a retry
    # that succeeds clears an earlier degraded attempt.
    latest = {}
    for row in sorted(runs, key=lambda r: r.get("started_at") or ""):
        latest[row["step_name"]] = row

    bad = [r for r in latest.values() if r["status"] in (DEGRADED, FAILED)]
    missing = [s for s in core_steps if s not in latest]
    # A step still marked running was killed mid-flight — treat it as unfinished.
    stuck = [r for r in latest.values() if r["status"] == "running"]

    lines = ["## Pipeline health", ""]
    for step in core_steps + [s for s in latest if s not in core_steps]:
        row = latest.get(step)
        if not row:
            lines.append(f"- `{step}` — **did not run**")
            continue
        mark = {OK: "ok", DEGRADED: "**degraded**", FAILED: "**failed**", "running": "**never finished**"}
        detail = f" — {row['error_message']}" if row.get("error_message") else ""
        rows = f" ({row['rows_processed']} rows)" if row.get("rows_processed") is not None else ""
        lines.append(f"- `{step}` — {mark.get(row['status'], row['status'])}{rows}{detail}")

    if not bad and not missing and not stuck:
        return 0, lines + ["", "Every step reported success."]

    headline = []
    if bad:
        headline.append(f"{len(bad)} step(s) {'/'.join(sorted({r['status'] for r in bad}))}")
    if missing:
        headline.append(f"{len(missing)} step(s) did not run: {', '.join(missing)}")
    if stuck:
        headline.append(f"{len(stuck)} step(s) never finished")
    return 1, lines + ["", "### Needs attention", ""] + [f"- {h}" for h in headline]


def check_last_run(sb, hours: int) -> int:
    code, lines = assess(_recent_runs(sb, hours), hours=hours)
    _emit(lines)
    return code


def check_heartbeat(sb, hours: int) -> int:
    runs = _recent_runs(sb, hours)
    good = [r for r in runs if r["step_name"] in CORE_STEPS and r["status"] == OK]
    if good:
        newest = max(r["started_at"] for r in good)
        _emit([f"Pipeline alive: {len(good)} successful step(s), newest at {newest[:16]}Z."])
        return 0

    last = (
        sb.table("pipeline_runs").select("step_name, started_at, status")
        .eq("status", OK).order("started_at", desc=True).limit(1).execute().data
    ) or []
    when = last[0]["started_at"][:16] + "Z" if last else "never"
    _emit([f"## Pipeline silent for over {hours}h",
           "",
           f"Last successful step: {when}.",
           "",
           "Nothing has run. The external trigger (cron-job.org) or the workflow "
           "itself has stopped — no in-run check can report this, because no run "
           "happened. The engine sat like this from 2026-07-04 to 2026-09-19."])
    return 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--heartbeat", action="store_true", help="Check that the pipeline ran at all")
    ap.add_argument("--max-age-hours", type=int, default=None,
                    help="Window to look back (default: 6 for a run check, 26 for a heartbeat)")
    args = ap.parse_args()
    hours = args.max_age_hours or (26 if args.heartbeat else 6)

    try:
        sb = get_supabase()
    except Exception as exc:
        # Can't read the telemetry: say so rather than pass silently, which is
        # the failure mode this script exists to end.
        _emit([f"## Pipeline health unknown", "", f"Could not reach Supabase: {exc}"])
        return 1

    return check_heartbeat(sb, hours) if args.heartbeat else check_last_run(sb, hours)


if __name__ == "__main__":
    raise SystemExit(main())
