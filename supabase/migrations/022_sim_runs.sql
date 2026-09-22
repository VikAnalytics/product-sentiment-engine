-- Migration 022: keep a summary of each completed simulator run.
--
-- The simulator can be restarted (sim_trader.py --action reset) so its record is
-- not shaped by bugs since fixed. Resetting deletes nothing, but the moment of
-- retirement went unrecorded: a run's last fortnightly snapshot can be two weeks
-- before it actually ended, so "where did the previous run finish, and what did
-- the market do meanwhile" had no answer. One row per retired run, carrying the
-- benchmarks over that run's own window so the comparison stays honest later.
-- Idempotent: safe to re-run.

CREATE TABLE IF NOT EXISTS sim_runs (
    id              SERIAL PRIMARY KEY,
    started_at      TIMESTAMPTZ NOT NULL,
    ended_at        TIMESTAMPTZ NOT NULL,
    starting_value  NUMERIC(12,2) NOT NULL,
    final_value     NUMERIC(12,2) NOT NULL,
    return_pct      NUMERIC(8,4)  NOT NULL,
    spy_value       NUMERIC(12,2),
    qqq_value       NUMERIC(12,2),
    trades          INTEGER,
    note            TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_sim_runs_ended ON sim_runs(ended_at DESC);

ALTER TABLE public.sim_runs ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Allow public read on sim_runs" ON public.sim_runs;
CREATE POLICY "Allow public read on sim_runs"
  ON public.sim_runs FOR SELECT USING (true);

COMMENT ON TABLE  sim_runs IS 'One row per retired simulator run: where it finished and what the benchmarks did over the same window.';
COMMENT ON COLUMN sim_runs.spy_value IS 'Value of starting_value invested in SPY across this run''s window.';
COMMENT ON COLUMN sim_runs.qqq_value IS 'Value of starting_value invested in QQQ across this run''s window.';
