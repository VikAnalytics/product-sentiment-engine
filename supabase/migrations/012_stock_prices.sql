-- Migration 012: Intraday stock price bars (5-minute OHLCV)
-- One row per (target, timestamp). Used for inter-event price attribution.

CREATE TABLE IF NOT EXISTS stock_prices (
    id            BIGSERIAL PRIMARY KEY,
    target_id     INTEGER NOT NULL REFERENCES targets(id) ON DELETE CASCADE,
    ts            TIMESTAMPTZ NOT NULL,          -- bar open timestamp (UTC)
    open          NUMERIC(12, 4),
    high          NUMERIC(12, 4),
    low           NUMERIC(12, 4),
    close         NUMERIC(12, 4) NOT NULL,
    volume        BIGINT,
    UNIQUE (target_id, ts)
);

CREATE INDEX IF NOT EXISTS stock_prices_target_ts ON stock_prices (target_id, ts DESC);

COMMENT ON TABLE stock_prices IS '5-minute OHLCV bars fetched via yfinance. One row per (target, bar timestamp).';
