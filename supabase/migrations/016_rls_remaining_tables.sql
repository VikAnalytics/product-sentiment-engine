-- Enable RLS and add read-only anon policies on tables added after migration 006.
-- stock_prices, price_reactions, target_sentiment_summary: read-only for dashboard.
-- sim_* tables: read-only for dashboard; writes only occur via service_role (pipeline).
-- ALTER TABLE ... ENABLE ROW LEVEL SECURITY is idempotent (safe to re-run).
-- CREATE POLICY IF NOT EXISTS is idempotent (safe to re-run).

ALTER TABLE public.stock_prices              ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.price_reactions           ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.target_sentiment_summary  ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.sim_portfolio             ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.sim_holdings              ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.sim_trades                ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.sim_pending_trades        ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.sim_snapshots             ENABLE ROW LEVEL SECURITY;

-- Read-only policies (anon + authenticated can SELECT, service_role bypasses RLS entirely)
CREATE POLICY IF NOT EXISTS "Allow public read on stock_prices"
  ON public.stock_prices FOR SELECT USING (true);

CREATE POLICY IF NOT EXISTS "Allow public read on price_reactions"
  ON public.price_reactions FOR SELECT USING (true);

CREATE POLICY IF NOT EXISTS "Allow public read on target_sentiment_summary"
  ON public.target_sentiment_summary FOR SELECT USING (true);

CREATE POLICY IF NOT EXISTS "Allow public read on sim_portfolio"
  ON public.sim_portfolio FOR SELECT USING (true);

CREATE POLICY IF NOT EXISTS "Allow public read on sim_holdings"
  ON public.sim_holdings FOR SELECT USING (true);

CREATE POLICY IF NOT EXISTS "Allow public read on sim_trades"
  ON public.sim_trades FOR SELECT USING (true);

CREATE POLICY IF NOT EXISTS "Allow public read on sim_pending_trades"
  ON public.sim_pending_trades FOR SELECT USING (true);

CREATE POLICY IF NOT EXISTS "Allow public read on sim_snapshots"
  ON public.sim_snapshots FOR SELECT USING (true);
