-- Migration 011: Add ticker symbol to targets
-- Public companies get a ticker (e.g. AAPL, NVDA); private companies stay NULL

ALTER TABLE targets ADD COLUMN IF NOT EXISTS ticker VARCHAR(10);

COMMENT ON COLUMN targets.ticker IS 'Stock ticker symbol (e.g. AAPL). NULL for private companies.';
