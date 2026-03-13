## Setup & Operations

This guide is for the team operating the engine (data/engineering). Executives can use the dashboard and reports without reading this.

### 1. Prerequisites

- Python 3.9+ and `virtualenv`
- A Supabase project (Postgres + pgvector enabled)
- A Gemini API key

Clone the repo and create a virtual environment:

```bash
git clone https://github.com/VikAnalytics/product-sentiment-engine.git
cd product-sentiment-engine
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Environment variables

Create a `.env` file in the project root:

```bash
SUPABASE_URL="https://your-project.supabase.co"
SUPABASE_KEY="your-service-role-key"
GEMINI_API_KEY="your-gemini-api-key"
```

- `SUPABASE_KEY` should be the **service_role** key (Project Settings → API).
- `GEMINI_API_KEY` is required for `scout.py`, `tracker.py`, and `report.py`.  
  The dashboard itself only needs Supabase.

### 3. Apply Supabase migrations

From the Supabase SQL editor (or `supabase db push`), apply all SQL files under `supabase/migrations/` in numeric order:

- `000_initial_schema.sql` (targets, sentiment, match_sentiment)
- `001_events_and_sentiment_event_id.sql` and subsequent files
- `006_rls_read_policies.sql` (RLS read access for the dashboard)

### 4. Running the pipeline locally

All commands below assume you are in the repo root and the venv is active.

#### 4.1. Discover companies/products and events (Scout)

```bash
PYTHONPATH=src python src/scout.py
```

This:

- Reads RSS feeds
- Filters articles with spaCy
- Writes to `targets` and `events` in Supabase

#### 4.2. Fetch sentiment for each event (Tracker)

Dry-run (no DB writes), limited to a few events for testing:

```bash
LOG_LEVEL=INFO \
TRACKER_DRY_RUN=1 \
TRACKER_MAX_EVENTS=5 \
PYTHONPATH=src python src/tracker.py
```

Production-style run (writes sentiment rows):

```bash
LOG_LEVEL=INFO \
PYTHONPATH=src python src/tracker.py
```

Environment variables:

- `TRACKER_DRY_RUN=1` — run everything but **do not insert** into `sentiment`.
- `TRACKER_MAX_EVENTS=N` — stop after N `(target,event)` pairs (helpful for tests).
- `LOG_LEVEL=DEBUG` — more detailed logs (HN/Reddit hit counts, etc.).
- `LOG_FILE=logs/tracker.log` — optional rotating log file for cron / CI.

#### 4.3. Generate the Market Intelligence report (Reporter)

```bash
PYTHONPATH=src python src/report.py
```

By default this:

- Looks back 1 day (configurable in `src/config.py` via `LOOKBACK_DAYS`)
- Writes `reports/market_intelligence_YYYY-MM-DD.md`

Set `REPORTS_DIR` in `.env` to change the output directory.

### 5. Running the dashboard locally

From the project root:

```bash
PYTHONPATH=src streamlit run src/app.py
```

Requirements:

- `.env` must contain `SUPABASE_URL` and `SUPABASE_KEY`.
- The Supabase project must have migrations applied and some data in `targets`, `events`, and `sentiment`.

For deployment instructions (Streamlit Community Cloud), see **`DEPLOY.md`**.

