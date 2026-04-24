# Supabase Schema

All tables, indexes, and the `match_sentiment` RPC are defined in `migrations/`. Apply them in numeric order using the Supabase SQL Editor or `supabase db push`.

---

## Migrations

Filenames below are exact — apply in numeric order.

| File | What It Does |
|------|-------------|
| `000_initial_schema.sql` | Enables pgvector. Creates `targets`, `sentiment`, and `match_sentiment` (3-arg). |
| `001_events_and_sentiment_event_id.sql` | Creates `events`. Adds `event_id` FK to `sentiment`. Upgrades `match_sentiment` to 4-arg (adds optional `p_event_id`). |
| `002_targets_parent_for_products.sql` | Adds `parent_target_id` (self-referencing FK) to link products to parent companies. |
| `003_events_cached_analysis.sql` | Adds `cached_analysis` and `cached_analysis_at` to `events` for storing AI-generated strategic analysis. |
| `004_targets_logo_url.sql` | Adds `logo_url` to `targets`. |
| `005_targets_domain.sql` | Adds `domain` to `targets` for favicon / Clearbit lookup. |
| `006_rls_read_policies.sql` | RLS read policies on `targets`, `events`, `sentiment` for anon key access. Required if dashboard uses the anon key. |
| `007_target_sentiment_summary.sql` | Creates `target_sentiment_summary` for AI-consolidated per-target pros/cons. |
| `008_sentiment_score.sql` | Adds `sentiment_score SMALLINT` to `sentiment` (−10 to +10). |
| `009_implication_tag.sql` | Adds `implication_tag VARCHAR(20)` to `sentiment` with CHECK constraint (`threat`, `opportunity`, `monitor`, `no_action`). |
| `010_source_type.sql` | Adds `source_type VARCHAR(80)` to `sentiment` (pipe-separated source names, e.g. `hn\|reddit`). |
| `011_ticker.sql` | Adds `ticker VARCHAR(10)` to `targets` for price data. |
| `012_stock_prices.sql` | Creates `stock_prices` table (`target_id`, `ts TIMESTAMPTZ`, `open`, `high`, `low`, `close`, `volume`). Unique constraint on `(target_id, ts)`. |
| `013_price_reactions.sql` | Creates `price_reactions` table with inter-event attribution fields (`price_at_event`, `window_return_pct`, `reaction_1d/3d/7d`, `confidence`, etc.). |
| `014_sector.sql` | Adds `sector VARCHAR(60)` and `is_f500 BOOLEAN DEFAULT FALSE` to `targets`. |
| `015_simulator.sql` | Creates AI stock simulator tables: `sim_portfolio`, `sim_holdings`, `sim_trades`, `sim_pending_trades`, `sim_snapshots`. Seeds the starting $1,000 portfolio row. **Note:** if applied before `peak_value` was added, run: `ALTER TABLE public.sim_portfolio ADD COLUMN IF NOT EXISTS peak_value NUMERIC(12,2) NOT NULL DEFAULT 1000.00;` |
| `016_rls_remaining_tables.sql` | Enables RLS + read-only anon policies on `stock_prices`, `price_reactions`, `target_sentiment_summary`, and all `sim_*` tables (missed by migration 006). |
| `017_macro_targets.sql` | Extends `targets.target_type` CHECK to include `MACRO`. Creates `macro_sector_exposure(macro_target_id, sector, exposure_weight 0..1)`. Run `scripts/seed_macro_targets.py` after applying to populate 8 themes + sector exposures. |
| `018_pipeline_runs.sql` | Creates `pipeline_runs` telemetry table (`step_name`, `started_at`, `ended_at`, `duration_ms`, `status`, `rows_processed`, `error_message`, `extra JSONB`). Written to by `src/pipeline_telemetry.py` — graceful no-op if missing. |

---

## Tables

### targets

Companies and products being tracked.

```
id                BIGINT PK
name              TEXT
target_type       TEXT        -- "COMPANY" | "PRODUCT" | "MACRO" (migration 017)
description       TEXT
status            TEXT        -- "tracking" (pipeline only processes these)
logo_url          TEXT
domain            TEXT
parent_target_id  BIGINT FK   -- links products to their parent company
ticker            VARCHAR(10) -- NULL for private companies
sector            VARCHAR(60)
is_f500           BOOLEAN
created_at        TIMESTAMPTZ
```

### events

One row per news headline per target.

```
id                BIGINT PK
target_id         BIGINT FK → targets
headline          TEXT
cached_analysis   TEXT        -- AI-written strategic analysis (cached from report.py)
cached_analysis_at TIMESTAMPTZ
created_at        TIMESTAMPTZ
```

### sentiment

One row per (target, event) per calendar day.

```
id                BIGINT PK
target_id         BIGINT FK → targets
event_id          BIGINT FK → events (nullable)
pros              TEXT
cons              TEXT
verbatim_quotes   TEXT
source_url        TEXT
embedding         vector(768) -- sentence-transformer embedding for dedup
sentiment_score   SMALLINT    -- −10 to +10; NULL on rows before migration 008
implication_tag   VARCHAR(20) -- threat | opportunity | monitor | no_action
source_type       VARCHAR(80) -- e.g. "hn|reddit"
created_at        TIMESTAMPTZ
```

### stock_prices

5-minute OHLCV bars from yfinance.

```
id          BIGINT PK
target_id   BIGINT FK → targets
ts          TIMESTAMPTZ
open        FLOAT
high        FLOAT
low         FLOAT
close       FLOAT
volume      BIGINT
UNIQUE(target_id, ts)
```

### price_reactions

Inter-event price attribution per event.

```
event_id           BIGINT PK FK → events
target_id          BIGINT FK → targets
ticker             VARCHAR(10)
price_at_event     FLOAT
window_return_pct  FLOAT       -- inter-event window return
next_event_id      BIGINT FK
window_end_reason  TEXT        -- "next_event" | "market_close"
reaction_1d        FLOAT
reaction_3d        FLOAT
reaction_7d        FLOAT
market_session     TEXT        -- regular | premarket | afterhours
confidence         TEXT        -- high | medium | low
confidence_reason  TEXT
computed_at        TIMESTAMPTZ
```

### target_sentiment_summary

AI-consolidated pros/cons per target (one row per target).

```
target_id       BIGINT PK FK → targets
pros_summary    TEXT
cons_summary    TEXT
quotes_summary  TEXT
updated_at      TIMESTAMPTZ
```

### sim_portfolio

Singleton row tracking current cash balance and peak value.

```
id              SERIAL PK
cash_usd        NUMERIC(12,2)   -- current available cash
peak_value      NUMERIC(12,2)   -- highest total portfolio value (for drawdown tracking)
initialized_at  TIMESTAMPTZ
updated_at      TIMESTAMPTZ
```

### sim_holdings

One row per open position (ticker currently held).

```
id              SERIAL PK
target_id       INTEGER FK → targets
ticker          VARCHAR(10) UNIQUE
shares          NUMERIC(14,6)
avg_buy_price   NUMERIC(12,4)
total_cost      NUMERIC(12,2)   -- cost basis
created_at      TIMESTAMPTZ
updated_at      TIMESTAMPTZ
```

### sim_trades

Full trade log — every executed or skipped trade.

```
id              BIGSERIAL PK
trade_date      DATE
target_id       INTEGER FK → targets
ticker          VARCHAR(10)
action          VARCHAR(4)      -- BUY | SELL
shares          NUMERIC(14,6)
price           NUMERIC(12,4)
usd_value       NUMERIC(12,2)   -- shares × price
pnl_usd         NUMERIC(12,2)   -- SELL only: proceeds − cost_basis
status          VARCHAR(12)     -- executed | skipped
skip_reason     TEXT
ai_rationale    TEXT            -- quant decision explanation
created_at      TIMESTAMPTZ
```

### sim_pending_trades

Trades queued by the analyze step, executed next morning.

```
id              BIGSERIAL PK
queued_at       TIMESTAMPTZ
target_id       INTEGER FK → targets
ticker          VARCHAR(10)
action          VARCHAR(4)      -- BUY | SELL
usd_amount      NUMERIC(12,2)   -- BUY: dollar amount to spend
sell_all        BOOLEAN         -- SELL: liquidate full position
ai_rationale    TEXT
```

### sim_snapshots

Fortnightly portfolio performance snapshots (one row per snapshot date).

```
id              SERIAL PK
snapshot_date   DATE UNIQUE
cash_usd        NUMERIC(12,2)
holdings_value  NUMERIC(12,2)   -- market value of all open positions
total_value     NUMERIC(12,2)
pnl_usd         NUMERIC(12,2)   -- vs $1,000 starting capital
pnl_pct         NUMERIC(8,4)
summary_text    TEXT
created_at      TIMESTAMPTZ
```

### macro_sector_exposure

Maps MACRO (geopolitics/regulatory) themes to the sectors they influence.
Used by the simulator's `macro_exposure` factor.

```
id              SERIAL PK
macro_target_id INTEGER FK → targets (must be target_type='MACRO')
sector          VARCHAR(60)     -- one of the sector names used in targets.sector
exposure_weight NUMERIC(3,2)    -- 0..1, enforced by CHECK
created_at      TIMESTAMPTZ
UNIQUE(macro_target_id, sector)
```

Seeded by `scripts/seed_macro_targets.py` with 8 themes (US-China, Russia-Ukraine,
Semi Export Controls, Middle East, OPEC, Tariffs, AI Regulation, Climate).

### pipeline_runs

Per-step telemetry for the daily pipeline. Written by `src/pipeline_telemetry.py`.

```
id              BIGSERIAL PK
step_name       VARCHAR(60)     -- scout | tracker | sec_scout | price_fetcher |
                                -- price_correlator | report | weekly_brief |
                                -- sim_execute | sim_analyze | sim_snapshot | sim_diagnose
started_at      TIMESTAMPTZ     -- inserted when the step begins
ended_at        TIMESTAMPTZ     -- updated on success or failure
duration_ms     INTEGER
status          VARCHAR(20)     -- running | success | failed (CHECK constraint)
rows_processed  INTEGER         -- optional, set via step.rows(n)
error_message   TEXT            -- on failure, truncated to 2000 chars
extra           JSONB           -- freeform metadata via step.note(**kwargs)
```

Indexed on `(step_name, started_at DESC)` and `(status, started_at DESC)` for
fast "recent failures" / "trend per step" queries.

---

## match_sentiment (RPC)

PostgreSQL function used by `tracker.py` to find semantically similar sentiment rows before inserting a new one.

```sql
match_sentiment(
    query_embedding  vector(768),
    match_threshold  float,
    p_target_id      bigint,
    p_event_id       bigint  -- optional; NULL = match across all events for target
) RETURNS TABLE (id bigint, similarity float)
```

Uses pgvector's `<=>` cosine distance operator. Returns rows where `1 - (embedding <=> query_embedding) > match_threshold`.

---

## Notes

- **1000-row cap**: Supabase PostgREST silently truncates results at 1000 rows regardless of `.limit()`. Any query that might return more than 1000 rows (e.g. `stock_prices`) must paginate using `.range(offset, offset+999)`.
- **Vector dimension**: All migrations use `vector(768)` to match `all-mpnet-base-v2`. If you switch embedding models, update both the `sentiment` column type and the `match_sentiment` function signature.
- **Backfilling events**: For targets that have `event_id = NULL` sentiment (created before migration 001), the dashboard and report fall back to using `targets.description` as a virtual event headline. To create real event rows, run the backfill query from the old `supabase/README.md` or use `scripts/`.
