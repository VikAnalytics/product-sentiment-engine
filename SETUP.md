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

In the Supabase SQL Editor (or via `supabase db push`), apply all files under `supabase/migrations/` in numeric order — `000` through `014`. See [supabase/README.md](supabase/README.md) for the full list and what each migration does.

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

## 5. Run the Dashboard Locally

```bash
PYTHONPATH=src streamlit run src/app.py
```

Requires `SUPABASE_URL` and `SUPABASE_KEY` in `.env`. For deployment to Streamlit Community Cloud, see [DEPLOY.md](DEPLOY.md).

---

## 6. Automation

The pipeline runs daily via GitHub Actions (`.github/workflows/run_engine.yml`), triggered externally by cron-job.org at 5pm EST. The full sequence:

```
scout.py → sec_scout.py → tracker.py → price_fetcher.py → price_correlator.py → report.py
```

On Mondays, `weekly_brief.py` runs after `report.py`.

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
| `link_products_to_companies.py` | Batch link products to parent companies |
| `update_logo_urls.py` | Fetch logos via Clearbit / Google Favicon API |
| `test_supabase_key.py` | Validate DB connection |
