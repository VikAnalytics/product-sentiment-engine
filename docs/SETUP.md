# Setup & Operations

This guide is for the team running the pipeline. Executives can use the dashboard and reports without reading this.

---

## Prerequisites

- Python 3.9+
- A Supabase project (PostgreSQL + pgvector extension enabled)
- An OpenAI API key

---

## 1. Clone and Install

```bash
git clone https://github.com/VikAnalytics/product-sentiment-engine.git
cd product-sentiment-engine
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python -m spacy download en_core_web_sm
```

---

## 2. Environment Variables

Create a `.env` file in the project root:

```bash
SUPABASE_URL="https://your-project.supabase.co"
SUPABASE_KEY="your-service-role-key"
OPENAI_API_KEY="sk-..."
```

- `SUPABASE_KEY` must be the **service_role** key (Supabase → Project Settings → API).
- `OPENAI_API_KEY` is required for `scout.py`, `tracker.py`, `report.py`, and `weekly_brief.py`. The dashboard only needs Supabase.

Optional overrides:

```bash
LOG_LEVEL=DEBUG               # default: INFO
LOG_FILE=logs/tracker.log     # rotating file handler
TRACKER_DRY_RUN=1             # run tracker without writing to DB
TRACKER_MAX_EVENTS=5          # cap events processed (useful for testing)
REPORTS_DIR=/abs/path/        # default: reports/
```

---

## 3. Apply Supabase Migrations

In the Supabase SQL Editor (or via `supabase db push`), apply all files under `supabase/migrations/` in numeric order — `000` through `018`. See [supabase/README.md](../supabase/README.md) for the full list and what each migration does.

Post-migration one-time step: seed the 8 MACRO (geopolitics/regulatory) themes after `017_macro_targets.sql` is applied:

```bash
PYTHONPATH=src python scripts/seed_macro_targets.py
```

---

## 4. Run the Pipeline

All commands assume you are in the repo root with the venv active.

### 4.1 Discover companies, products, and events

```bash
PYTHONPATH=src python src/scout.py
```

Reads RSS feeds → NLP filter → OpenAI extraction → writes to `targets` and `events`.

### 4.2 Ingest SEC EDGAR filings

```bash
PYTHONPATH=src python src/sec_scout.py
```

Polls EDGAR submissions API for tracked public companies → inserts 8-K, 10-Q, 10-K, DEF 14A filing events. No API key required.

### 4.3 Fetch community sentiment

Dry run (no DB writes), limited to a few events:

```bash
TRACKER_DRY_RUN=1 TRACKER_MAX_EVENTS=5 PYTHONPATH=src python src/tracker.py
```

Production run:

```bash
PYTHONPATH=src python src/tracker.py
```

Environment variables:

| Variable | Effect |
|----------|--------|
| `TRACKER_DRY_RUN=1` | Run everything but skip DB inserts |
| `TRACKER_MAX_EVENTS=N` | Stop after N `(target, event)` pairs |
| `LOG_LEVEL=DEBUG` | Show per-event HN/Reddit hit counts and dedupe decisions |
| `LOG_FILE=logs/tracker.log` | Write logs to a rotating file |

### 4.4 Fetch stock price data

```bash
PYTHONPATH=src python src/price_fetcher.py
```

Downloads 59 days of 5-min OHLCV bars via yfinance for all targets with a ticker set. Upserts into `stock_prices` (safe to re-run).

### 4.5 Compute inter-event price reactions

```bash
PYTHONPATH=src python src/price_correlator.py
```

For each event on a public company, computes the price reaction in the window between that event and the next. Writes to `price_reactions`.

### 4.6 Generate the daily report

```bash
PYTHONPATH=src python src/report.py
```

Aggregates the last 24h of sentiment → deduplicates → OpenAI report → writes to `reports/market_intelligence_YYYY-MM-DD.md`.

To re-parse an existing report and backfill `events.cached_analysis` without calling the AI:

```bash
PYTHONPATH=src python src/report.py reports/market_intelligence_2026-03-20.md
```

### 4.7 Generate the weekly brief

```bash
PYTHONPATH=src python src/weekly_brief.py
```

7-day lookback → strategic synthesis prompt → writes to `reports/weekly_brief_YYYY-WXX.md`. Runs automatically on Mondays via GitHub Actions.

---

### 4.8 AI Stock Simulator

Persistent $1,000 virtual portfolio. Six-factor quant strategy (sentiment momentum, price momentum, inverse volatility, signal consistency, historical accuracy, macro exposure) gated by EV check, signal consensus (3/6), and regime filter, then allocated via Markowitz max-Sharpe with Kelly Criterion caps. No real money involved.

**Execute pending trades** (run after `price_fetcher.py`, before `tracker.py`):

```bash
PYTHONPATH=src python src/sim_trader.py --action execute
```

Processes queued SELLs first (rotation + forced exits), then settles BUYs using today's market open price. Risk rules: stop-loss (−8% from cost), trailing stop (−6% from post-entry peak, armed after +2% gain), take-profit (+25%), sentiment stop (`threat` tag or today's score < −3), max drawdown guard (−15% from peak → full liquidation + queue wipe).

**Analyze and queue tomorrow's trades** (run after `tracker.py` and `price_correlator.py`):

```bash
PYTHONPATH=src python src/sim_trader.py --action analyze
```

Runs the full quant pipeline on today's sentiment data:
1. **Universe**: sentiment from the last 72h (`SIM_SENTIMENT_LOOKBACK_HOURS=72`) with `avg_score ≥ 3`; held positions unioned in so z-scores are comparable
2. **Six-factor scoring**: sentiment momentum (25%), price momentum (20%), inverse volatility (15%), signal consistency (15%), historical accuracy (10%), macro exposure (15%) — Z-scored and composited
3. **Top cohort**: top 1/3 of ranked universe (floor of 4 names)
4. **EV gate**: `p_win ≥ 55%` AND `EV ≥ 1.5%` from `price_reactions` history (min 5 samples). **Strong-signal override**: `avg_score ≥ 7 + tag='opportunity'` bypasses the sample gate with halved position size
5. **Signal consensus**: 3 of 6 factors must be directionally positive
6. **Regime filter**: ≥40% positive sentiment momentum OR absolute count ≥ 3
7. **Markowitz max-Sharpe** (scipy SLSQP, Ledoit-Wolf shrinkage)
8. **Kelly sizing** capped at 25% per position; deploys up to 90% of cash (25% when regime is risk-off → top-1 only)
9. **Rotation**: any held position with composite < 0 gets a SELL queued if a stronger BUY is also queued (max 2/day)
10. AI generates rationale text only — does not pick stocks

Queues BUYs (and any rotation SELLs) in `sim_pending_trades` for tomorrow's execute step.

**Diagnose the funnel** (read-only; shows stage counts so you can see why a day produced no trades):

```bash
PYTHONPATH=src python src/sim_trader.py --action diagnose
```

**Fortnightly performance snapshot** (runs automatically on even-week Mondays):

```bash
PYTHONPATH=src python src/sim_trader.py --action snapshot
```

Computes current portfolio value (cash + market value of holdings), records P&L vs $1,000 starting capital, stores in `sim_snapshots`.

**Timing note:** The cron job fires at 5pm EST (after market close). `execute` runs at 5pm but uses the 9:30am open price already stored in `stock_prices` — correctly simulating "bought at open that morning."

---

## 5. Run the Web Dashboard Locally

```bash
cd web
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000). Requires `web/.env.local` with:

```bash
NEXT_PUBLIC_SUPABASE_URL=https://your-project.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=eyJ...
```

Use the **anon** key (not service_role). For Vercel deployment, see [DEPLOY.md](DEPLOY.md).

---

## 6. Automation

The pipeline runs daily via GitHub Actions (`.github/workflows/run_engine.yml`), triggered externally by cron-job.org at 5pm EST. The full sequence:

```
scout.py → sec_scout.py → price_fetcher.py
  → sim_trader execute   (settle yesterday's trades at today's open)
  → tracker.py → price_correlator.py
  → sim_trader analyze   (queue tomorrow's trades from today's sentiment)
  → report.py
```

On Mondays: `weekly_brief.py` runs after `report.py`.
On even-week Mondays: `sim_trader snapshot` also runs.

The workflow commits generated reports back to the `reports/` directory automatically.

---

## 7. Maintenance Scripts

Located in `scripts/`:

| Script | Purpose |
|--------|---------|
| `dedupe_sentiment_in_db.py` | Backfill `target_sentiment_summary` |
| `deduplicate_sentiment_rows.py` | Remove exact duplicate sentiment rows |
| `find_duplicate_targets.py` | Identify similar target names |
| `merge_duplicate_targets.py` | Merge duplicate targets and their sentiment |
| `link_products_to_companies.py` | Batch link products to parent companies (manual dict) |
| `ai_link_products.py` | AI-driven product→parent linking; creates missing parents if needed |
| `seed_macro_targets.py` | Seed 8 MACRO (geopolitics/regulatory) themes + sector exposures. Run once after migration 017 |
| `update_logo_urls.py` | Fetch logos via Clearbit / Google Favicon API |
| `test_supabase_key.py` | Validate DB connection |

---

## 8. Tests

```bash
pip install -r requirements-dev.txt
pytest                 # all tests
pytest -v              # verbose
pytest tests/test_sim_factors.py -k Kelly   # single test
```

Tests cover pure functions only (no Supabase/OpenAI calls required). `tests/conftest.py` sets placeholder env vars so `config.py` imports succeed without real credentials.

---

## 9. Docker

```bash
docker build -t psengine .

# Dashboard (Streamlit)
docker run --rm -p 8501:8501 --env-file .env psengine

# Pipeline step
docker run --rm --env-file .env psengine python src/scout.py
docker run --rm --env-file .env psengine python src/sim_trader.py --action diagnose
```

The image is Python 3.11-slim, installs `requirements.txt` + the spacy model, and runs as a non-root user.

---

## 10. Observability

### Logs

`src/logging_setup.py` installs a root-level handler at the top of every pipeline entry point. When `GITHUB_ACTIONS=true`, output is one JSON object per line (parseable by Datadog, Loki, etc.). Locally, output is human-readable.

### Pipeline telemetry

`src/pipeline_telemetry.py` wraps every pipeline step (`scout`, `tracker`, `sec_scout`, `price_fetcher`, `price_correlator`, `report`, `weekly_brief`, `sim_execute`, `sim_analyze`, `sim_snapshot`, `sim_diagnose`) with a context manager that writes a row to the `pipeline_runs` table:

| Column | Meaning |
|--------|---------|
| `step_name` | Stage name |
| `started_at`, `ended_at`, `duration_ms` | Timing |
| `status` | `running` / `success` / `failed` |
| `rows_processed` | If the step calls `.rows(n)` on the context handle |
| `error_message` | Exception repr on failure (truncated to 2000 chars) |
| `extra` | Freeform JSONB — anything passed via `.note(**kwargs)` |

Disable telemetry for ad-hoc runs: `PIPELINE_TELEMETRY=0 PYTHONPATH=src python src/scout.py`.

Query recent failures:

```sql
SELECT step_name, started_at, duration_ms, error_message
FROM pipeline_runs
WHERE status = 'failed'
ORDER BY started_at DESC LIMIT 20;
```
