-- Enable RLS and add read-only anon policies on tables added after migration 006.
-- stock_prices, price_reactions, target_sentiment_summary: read-only for dashboard.
-- sim_* tables: read-only for dashboard; writes only occur via service_role (pipeline).
-- DROP POLICY IF EXISTS + CREATE makes this idempotent (safe to re-run).

ALTER TABLE public.stock_prices              ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.price_reactions           ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.target_sentiment_summary  ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.sim_portfolio             ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.sim_holdings              ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.sim_trades                ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.sim_pending_trades        ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.sim_snapshots             ENABLE ROW LEVEL SECURITY;

-- stock_prices
DROP POLICY IF EXISTS "Allow public read on stock_prices" ON public.stock_prices;
CREATE POLICY "Allow public read on stock_prices"
  ON public.stock_prices FOR SELECT USING (true);

-- price_reactions
DROP POLICY IF EXISTS "Allow public read on price_reactions" ON public.price_reactions;
CREATE POLICY "Allow public read on price_reactions"
  ON public.price_reactions FOR SELECT USING (true);

-- target_sentiment_summary
DROP POLICY IF EXISTS "Allow public read on target_sentiment_summary" ON public.target_sentiment_summary;
CREATE POLICY "Allow public read on target_sentiment_summary"
  ON public.target_sentiment_summary FOR SELECT USING (true);

-- sim_portfolio
DROP POLICY IF EXISTS "Allow public read on sim_portfolio" ON public.sim_portfolio;
CREATE POLICY "Allow public read on sim_portfolio"
  ON public.sim_portfolio FOR SELECT USING (true);

-- sim_holdings
DROP POLICY IF EXISTS "Allow public read on sim_holdings" ON public.sim_holdings;
CREATE POLICY "Allow public read on sim_holdings"
  ON public.sim_holdings FOR SELECT USING (true);

-- sim_trades
DROP POLICY IF EXISTS "Allow public read on sim_trades" ON public.sim_trades;
CREATE POLICY "Allow public read on sim_trades"
  ON public.sim_trades FOR SELECT USING (true);

-- sim_pending_trades
DROP POLICY IF EXISTS "Allow public read on sim_pending_trades" ON public.sim_pending_trades;
CREATE POLICY "Allow public read on sim_pending_trades"
  ON public.sim_pending_trades FOR SELECT USING (true);

-- sim_snapshots
DROP POLICY IF EXISTS "Allow public read on sim_snapshots" ON public.sim_snapshots;
CREATE POLICY "Allow public read on sim_snapshots"
  ON public.sim_snapshots FOR SELECT USING (true);
