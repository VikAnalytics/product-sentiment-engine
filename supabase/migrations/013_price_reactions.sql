-- Migration 013: Price reaction windows per event (inter-event attribution)
-- For each event, stores the % return in the window between this event and the next,
-- plus broader 1d/3d/7d windows for context.

CREATE TABLE IF NOT EXISTS price_reactions (
    event_id            INTEGER PRIMARY KEY REFERENCES events(id) ON DELETE CASCADE,
    target_id           INTEGER NOT NULL REFERENCES targets(id) ON DELETE CASCADE,
    ticker              VARCHAR(10),
    price_at_event      NUMERIC(12, 4),          -- close price at event timestamp
    window_return_pct   NUMERIC(8, 4),           -- % change: event → next event (inter-event)
    next_event_id       INTEGER REFERENCES events(id) ON DELETE SET NULL,
    window_end_reason   VARCHAR(20),             -- 'next_event' | 'market_close' | 'next_open'
    reaction_1d         NUMERIC(8, 4),           -- % change over full next trading day
    reaction_3d         NUMERIC(8, 4),
    reaction_7d         NUMERIC(8, 4),
    market_session      VARCHAR(12),             -- 'regular' | 'premarket' | 'afterhours'
    confidence          VARCHAR(8),              -- 'high' | 'medium' | 'low'
    confidence_reason   TEXT,
    computed_at         TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS price_reactions_target ON price_reactions (target_id);

COMMENT ON TABLE price_reactions IS 'Inter-event price attribution windows. Each event owns the price move until the next event or market close.';
