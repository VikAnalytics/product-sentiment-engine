## Product Sentiment Engine

### Who this is for

This repo is designed for **Strategy Leaders** who want a *single place* to see:

- **What changed** for your companies and products (news events).
- **How the market reacted** (pros, cons, and real customer quotes).
- **What to do about it** (executive-ready written reports).

You should be able to open the dashboard and answer, in minutes, questions like:

- “What are the last 3 meaningful events for Nvidia and Anthropic?”  
- “Is sentiment getting better or worse, and why?”  
- “Where is the market actually complaining (pricing, performance, trust, UX)?”

The underlying system is fully transparent and auditable; every insight can be traced back to specific HN/Reddit threads or articles.

### What the system does

- **Ingests tech news** from top RSS feeds and turns each headline into a structured **event** for a company or product.
- **Scans public chatter** (Hacker News + Reddit) around each event and keeps only *non-duplicative* signals.
- **Extracts sentiment** as:
  - **Pros**: what the market likes.
  - **Cons**: what the market criticizes.
  - **Voice of the customer**: verbatim quotes with source links.
- **Surfaces intelligence** in two ways:
  - A **Streamlit dashboard** for day-to-day monitoring (events timeline + company sentiment).
  - A written **Market Intelligence Report** for board decks and IC memos.

### How to use the dashboard (executive view)

1. Open the deployed Streamlit app (or run it locally with `streamlit run src/app.py`).
2. Use the **sidebar** to select a company or product.
3. For the selected target you will see:
   - **Events & sentiment**: a timeline of recent events; expand each to see pros, cons, and customer quotes.
   - **Company sentiment**: consolidated, deduplicated pros/cons and source links not tied to a specific event.
4. When there is no real signal for an event, the dashboard explicitly shows **“No new chatter for this event.”**

If you only care about consuming insights, you can stop here. The rest of the documentation is for the team operating the system.

### How it works (one-page architecture)

The engine runs in three stages, all driven by configuration in `src/config.py` and a Supabase/Postgres schema under `supabase/migrations/`:

- **1. Scout – Discover companies, products, and events**
  - Reads RSS from TechCrunch, The Verge, Wired, Engadget, ZDNet.
  - Uses spaCy to keep only articles that match “material” concepts (launches, acquisitions, layoffs, probes, etc.).
  - Uses Gemini to extract **targets** (companies/products) and write:
    - `targets` table: one row per company or product.
    - `events` table: one row per headline per target, with a short description.

- **2. Tracker – Market sentiment per event**
  - For each `target` + `event`, builds a focused search query and fetches recent chatter from **Hacker News** and **Reddit**.
  - Embeds the combined chatter with `gemini-embedding-001` and uses `pgvector` to run a **similarity check** (`match_sentiment`) so we only keep net-new information.
  - For non-duplicate chatter, prompts Gemini to output **“PROS | CONS | QUOTES | URL”** and writes one `sentiment` row linked to that `event`.

- **3. Reporter – Executive report**
  - Aggregates events and sentiment for a lookback window.
  - Deduplicates repeated pros/cons and quotes.
  - Asks Gemini to draft a report with:
    - **Executive summary**,
    - **Per-target / per-event analysis**, and
    - **Forward-looking implications**.
  - Saves to `reports/market_intelligence_YYYY-MM-DD.md`.

### Operations, setup, and deployment

- **Setup & local runs** (cloning the repo, `.env`, Supabase, Gemini key, running `scout`, `tracker`, and `report`):
  - See **`SETUP.md`**.
- **Deploying the Streamlit dashboard** (Streamlit Community Cloud):
  - See **`DEPLOY.md`**.
- **Supabase schema** (tables, RLS, and functions):
  - See SQL migrations under **`supabase/migrations/`**.

### Technology overview

- **Language**: Python 3.9+  
- **LLM**: Google Gemini 2.5 Flash  
- **Embeddings**: `gemini-embedding-001` via the Gemini API  
- **Database**: Supabase (PostgreSQL + `pgvector`)  
- **UI**: Streamlit dashboard (`src/app.py`)  
- **Automation**: GitHub Actions + external cron (or any scheduler)  
- **Data sources**: RSS feeds, Hacker News Algolia API, Reddit API
