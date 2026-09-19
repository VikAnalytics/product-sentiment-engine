-- Migration 020: allow a 'degraded' pipeline step status.
--
-- Until now a step was only ever 'success' or 'failed', which meant it recorded
-- whether Python crashed and nothing else. Every one of 601 recorded runs was a
-- success while StockTwits returned 403 for months and the tracker discarded
-- roughly 29% of events. 'degraded' is for a step that completed but produced
-- suspiciously little: the reason goes in error_message, the counters in extra.
-- Idempotent: safe to re-run.

ALTER TABLE public.pipeline_runs DROP CONSTRAINT IF EXISTS pipeline_runs_status_check;
ALTER TABLE public.pipeline_runs
    ADD CONSTRAINT pipeline_runs_status_check
    CHECK (status IN ('running', 'success', 'degraded', 'failed'));

COMMENT ON COLUMN public.pipeline_runs.status IS
    'running | success | degraded (completed but under its health threshold) | failed';
