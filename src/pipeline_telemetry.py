"""
Pipeline step telemetry.

Provides a context manager that records start/end, duration, status, row counts,
and error information to the `pipeline_runs` Supabase table.

Graceful no-op: if the table is missing (migration 018 not yet applied), or any
DB error occurs, telemetry logs locally and the wrapped work still runs. The
pipeline never fails because telemetry failed.

Usage:
    from pipeline_telemetry import step

    with step("scout") as s:
        count = run_scout()
        s.rows(count)
        s.note(events_created=count)
"""
import logging
import os
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Dict, Iterator, Optional

log = logging.getLogger(__name__)


class _StepHandle:
    """Exposed inside the context manager body so callers can attach metrics."""

    def __init__(self) -> None:
        self._rows: Optional[int] = None
        self._extra: Dict[str, Any] = {}
        self._degraded: list = []

    def rows(self, count: Optional[int]) -> None:
        """Record how many rows the step processed (optional)."""
        if count is None:
            return
        try:
            self._rows = int(count)
        except (TypeError, ValueError):
            pass

    def note(self, **kwargs: Any) -> None:
        """Attach arbitrary JSON-serializable metadata to the run record."""
        self._extra.update(kwargs)

    def degrade(self, reason: str) -> None:
        """
        Record that the step finished but did not do its job properly.

        A step that completes is not the same as a step that worked. StockTwits
        answered 403 for months and the tracker dropped roughly a third of its
        events, all while every run recorded 'success', because the only thing
        being measured was whether Python raised. Call this when a step's own
        numbers say something is wrong; several reasons may be recorded.
        """
        if reason:
            self._degraded.append(reason)

    def check(self, condition: bool, reason: str) -> None:
        """Convenience: degrade when `condition` is true."""
        if condition:
            self.degrade(reason)


def _insert_start(sb, step_name: str) -> Optional[int]:
    """Insert the starting row; return its id, or None on any failure."""
    try:
        resp = (
            sb.table("pipeline_runs")
            .insert({
                "step_name": step_name,
                "started_at": datetime.now(timezone.utc).isoformat(),
                "status": "running",
            })
            .execute()
        )
        data = getattr(resp, "data", None) or []
        return data[0].get("id") if data else None
    except Exception as exc:
        log.debug("telemetry: could not insert start row for %s (%s). Continuing.", step_name, exc)
        return None


def _finalize(sb, run_id: Optional[int], status: str, duration_ms: int,
              rows: Optional[int], extra: Optional[dict], error: Optional[str]) -> None:
    if run_id is None:
        return
    try:
        update = {
            "ended_at": datetime.now(timezone.utc).isoformat(),
            "duration_ms": duration_ms,
            "status": status,
        }
        if rows is not None:
            update["rows_processed"] = rows
        if extra:
            update["extra"] = extra
        if error:
            update["error_message"] = error[:2000]
        sb.table("pipeline_runs").update(update).eq("id", run_id).execute()
    except Exception as exc:
        # 'degraded' needs migration 020. Without it the CHECK constraint rejects
        # the write, which would strand the row at 'running'. Record the run as a
        # success carrying the reason rather than losing it entirely.
        if status == "degraded":
            try:
                update["status"] = "success"
                sb.table("pipeline_runs").update(update).eq("id", run_id).execute()
                log.debug("telemetry: 'degraded' rejected (apply migration 020); recorded as success.")
                return
            except Exception:
                pass
        log.debug("telemetry: could not finalize run %s (%s).", run_id, exc)


@contextmanager
def step(step_name: str) -> Iterator[_StepHandle]:
    """
    Context manager: records the start, duration, status, and any extras.
    Re-raises any exception raised inside the body after recording 'failed'.

    The manager is best-effort: if Supabase is unreachable or the migration
    has not been applied, the wrapped work still runs normally.
    """
    handle = _StepHandle()
    run_id: Optional[int] = None
    sb = None
    start = time.monotonic()

    # Telemetry can be disabled via env for tests / ad-hoc runs.
    enabled = os.getenv("PIPELINE_TELEMETRY", "1") != "0"

    if enabled:
        try:
            from config import get_supabase  # local import to avoid circulars
            sb = get_supabase()
            run_id = _insert_start(sb, step_name)
        except Exception as exc:
            log.debug("telemetry: disabled for this run (%s)", exc)
            sb = None

    try:
        yield handle
    except Exception as exc:
        elapsed_ms = int((time.monotonic() - start) * 1000)
        log.error("pipeline step '%s' FAILED after %dms: %s", step_name, elapsed_ms, exc)
        if sb is not None:
            _finalize(sb, run_id, "failed", elapsed_ms, handle._rows, handle._extra, str(exc))
        raise
    else:
        elapsed_ms = int((time.monotonic() - start) * 1000)
        rows_label = handle._rows if handle._rows is not None else "—"
        if handle._degraded:
            reason = "; ".join(handle._degraded)
            log.warning("pipeline step '%s' DEGRADED in %dms (rows=%s): %s",
                        step_name, elapsed_ms, rows_label, reason)
            if sb is not None:
                _finalize(sb, run_id, "degraded", elapsed_ms, handle._rows, handle._extra, reason)
        else:
            log.info("pipeline step '%s' ok in %dms (rows=%s)", step_name, elapsed_ms, rows_label)
            if sb is not None:
                _finalize(sb, run_id, "success", elapsed_ms, handle._rows, handle._extra, None)
