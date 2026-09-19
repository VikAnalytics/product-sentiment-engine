-- Migration 021: benchmark the simulator against the market it trades in.
--
-- sim_snapshots recorded the portfolio in isolation, so the dashboard could show
-- "+9.9% since inception" in green while SPY returned +11.6% and QQQ +17.0% over
-- the same window. In isolation that reads as a win; it is underperformance.
-- Each column holds what SIM_STARTING_CAPITAL invested in that index at the
-- simulator's inception would be worth on the snapshot date, so the values plot
-- directly against total_value.
-- Idempotent: safe to re-run.

ALTER TABLE public.sim_snapshots ADD COLUMN IF NOT EXISTS spy_value NUMERIC(12,2);
ALTER TABLE public.sim_snapshots ADD COLUMN IF NOT EXISTS qqq_value NUMERIC(12,2);

COMMENT ON COLUMN public.sim_snapshots.spy_value IS
    'Value of the starting capital had it been invested in SPY at inception.';
COMMENT ON COLUMN public.sim_snapshots.qqq_value IS
    'Value of the starting capital had it been invested in QQQ at inception. QQQ is the fairer comparison: the tracked universe is tech-heavy.';
