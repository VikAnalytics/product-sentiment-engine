-- Migration 018: Pipeline step telemetry
-- Records start/end, duration, status, row counts, and error for every
-- pipeline stage (scout, tracker, sec_scout, price_fetcher, price_correlator,
-- report, weekly_brief, sim_trader). Queryable from the dashboard to surface
-- failing steps or slowdowns, and persists across runs so regressions are
-- visible over time.

CREATE TABLE IF NOT EXISTS pipeline_runs (
    id              BIGSERIAL PRIMARY KEY,
    step_name       VARCHAR(60) NOT NULL,
    started_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    ended_at        TIMESTAMPTZ,
    duration_ms     INTEGER,
    status          VARCHAR(20) NOT NULL DEFAULT 'running'
                    CHECK (status IN ('running', 'success', 'failed')),
    rows_processed  INTEGER,
    error_message   TEXT,
    extra           JSONB
);

CREATE INDEX IF NOT EXISTS idx_pipeline_runs_step_started
    ON pipeline_runs(step_name, started_at DESC);

CREATE INDEX IF NOT EXISTS idx_pipeline_runs_status_started
    ON pipeline_runs(status, started_at DESC);

COMMENT ON TABLE  pipeline_runs IS 'Per-step telemetry for the daily sentiment/trading pipeline.';
COMMENT ON COLUMN pipeline_runs.step_name IS 'Logical stage name: scout, tracker, sec_scout, price_fetcher, price_correlator, report, weekly_brief, sim_execute, sim_analyze, sim_snapshot.';
COMMENT ON COLUMN pipeline_runs.extra     IS 'Freeform JSON — e.g. {"events_created": 12, "api_calls": 47}.';
