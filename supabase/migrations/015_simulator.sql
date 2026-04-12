-- Migration 015: AI Stock Simulator
-- Persistent simulation portfolio: $1000 starting capital, daily AI trades, fortnightly snapshots.
-- Apply manually via Supabase SQL editor.

-- Current cash balance (singleton row)
CREATE TABLE IF NOT EXISTS sim_portfolio (
    id             SERIAL PRIMARY KEY,
    cash_usd       NUMERIC(12,2) NOT NULL DEFAULT 1000.00,
    peak_value     NUMERIC(12,2) NOT NULL DEFAULT 1000.00,  -- for max drawdown tracking
    initialized_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
-- Seed the starting portfolio (only if table is empty)
INSERT INTO sim_portfolio (cash_usd)
SELECT 1000.00
WHERE NOT EXISTS (SELECT 1 FROM sim_portfolio);

-- Open positions (one row per ticker held)
CREATE TABLE IF NOT EXISTS sim_holdings (
    id            SERIAL PRIMARY KEY,
    target_id     INTEGER NOT NULL REFERENCES targets(id) ON DELETE CASCADE,
    ticker        VARCHAR(10) NOT NULL UNIQUE,
    shares        NUMERIC(14,6) NOT NULL,
    avg_buy_price NUMERIC(12,4) NOT NULL,
    total_cost    NUMERIC(12,2) NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS sim_holdings_target ON sim_holdings (target_id);

-- Full trade log (executed and skipped)
CREATE TABLE IF NOT EXISTS sim_trades (
    id           BIGSERIAL PRIMARY KEY,
    trade_date   DATE NOT NULL,
    target_id    INTEGER REFERENCES targets(id),
    ticker       VARCHAR(10) NOT NULL,
    action       VARCHAR(4) NOT NULL CHECK (action IN ('BUY', 'SELL')),
    shares       NUMERIC(14,6),
    price        NUMERIC(12,4),
    usd_value    NUMERIC(12,2),       -- shares * price
    pnl_usd      NUMERIC(12,2),       -- SELL only: proceeds - cost_basis
    status       VARCHAR(12) NOT NULL DEFAULT 'executed'
                     CHECK (status IN ('executed', 'skipped')),
    skip_reason  TEXT,
    ai_rationale TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS sim_trades_date   ON sim_trades (trade_date);
CREATE INDEX IF NOT EXISTS sim_trades_ticker ON sim_trades (ticker);

-- Pending decisions queued by AI (executed next day at market open)
CREATE TABLE IF NOT EXISTS sim_pending_trades (
    id           BIGSERIAL PRIMARY KEY,
    queued_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    target_id    INTEGER REFERENCES targets(id),
    ticker       VARCHAR(10) NOT NULL,
    action       VARCHAR(4) NOT NULL CHECK (action IN ('BUY', 'SELL')),
    usd_amount   NUMERIC(12,2),        -- BUY: dollar amount to spend
    sell_all     BOOLEAN NOT NULL DEFAULT TRUE,   -- SELL: liquidate entire position
    ai_rationale TEXT
);

-- Fortnightly performance snapshots
CREATE TABLE IF NOT EXISTS sim_snapshots (
    id             SERIAL PRIMARY KEY,
    snapshot_date  DATE NOT NULL UNIQUE,
    cash_usd       NUMERIC(12,2) NOT NULL,
    holdings_value NUMERIC(12,2) NOT NULL,
    total_value    NUMERIC(12,2) NOT NULL,
    pnl_usd        NUMERIC(12,2) NOT NULL,
    pnl_pct        NUMERIC(8,4) NOT NULL,
    summary_text   TEXT,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
