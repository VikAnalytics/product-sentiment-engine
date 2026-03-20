# Product Sentiment Engine

A dual-signal market intelligence platform for strategy leaders and investment teams.

---

## Who This Is For

**Strategy leaders** who want a single place to answer questions like:

- "What are the last 3 meaningful events for Nvidia and Anthropic?"
- "Is sentiment getting better or worse, and why?"
- "Where is the market actually complaining — pricing, performance, trust, UX?"
- "How did the stock price react when that announcement dropped?"

Every insight is traceable to a specific HN thread, Reddit post, or SEC filing.

---

## What the System Does

| Signal | Source | Output |
|--------|--------|--------|
| News events | RSS feeds + SEC EDGAR (8-K, 10-Q, 10-K) | Structured events per company/product |
| Community sentiment | Hacker News + Reddit | Pros, cons, verbatim quotes with source links |
| Stock price reactions | yfinance 5-min OHLCV bars | Inter-event price attribution per event |
| Structured intelligence | OpenAI `gpt-4o-mini` | Daily reports + weekly executive brief |

Surfaces through two outputs:

- **Streamlit dashboard** — events timeline, sentiment scores, price reaction badges, news feed, competitive rankings
- **Market Intelligence Report** — board-ready markdown written daily, stored in `reports/`

---

## How to Use the Dashboard

1. Open the deployed Streamlit app (or run locally — see [SETUP.md](SETUP.md)).
2. Use the **sidebar** to navigate:
   - **News Feed** — chronological view of all tracked headlines; filter by date and sector
   - **Analysis** — deep dive into a specific company or product
3. In Analysis mode, select a company or product to see:
   - Events timeline with sentiment scores and implication tags (threat / opportunity / monitor)
   - Price reaction badges for public companies (inter-event %, 1d/3d/7d)
   - Collapsible price chart with event markers
   - Sentiment trend chart (30 / 90 / all-time)
4. Use **Compare** to put up to 4 targets side by side.
5. Use **Rankings** to see all companies ranked by average sentiment score.

If you only need to consume insights, you can stop here. The rest of this documentation is for the team running the system.

---

## Architecture

```
RSS Feeds + SEC EDGAR
        ↓
   scout.py          NLP filter → OpenAI extracts targets + events → Supabase
   sec_scout.py      EDGAR submissions API → 8-K/10-Q/10-K events → Supabase
        ↓
   tracker.py        HN + Reddit → local embeddings → pgvector dedupe → OpenAI sentiment → Supabase
   price_fetcher.py  yfinance 5-min OHLCV bars → Supabase
   price_correlator.py  Inter-event window attribution → Supabase
        ↓
   report.py         Aggregate + dedupe → OpenAI → reports/market_intelligence_YYYY-MM-DD.md
   weekly_brief.py   7-day strategic synthesis → reports/weekly_brief_YYYY-WXX.md
        ↓
   app.py            Streamlit dashboard
```

---

## How It Works

### 1. Scout — Discover companies, products, and events

- Reads RSS from TechCrunch, The Verge, Wired, Reuters, Yahoo Finance, and others
- Uses spaCy to keep only articles that match material concepts (launches, acquisitions, layoffs, earnings, regulatory probes, etc.) — eliminates ~60% of articles before any LLM call
- Uses OpenAI to extract the company/product name and write structured rows into `targets` and `events`

### 2. SEC Scout — EDGAR filing events

- Polls EDGAR's submissions API for each tracked public company
- Inserts 8-K, 10-Q, 10-K, and DEF 14A filings as events (no API key required)
- Idempotent: exact headline match check before inserting

### 3. Tracker — Market sentiment per event

- For each event (last 14 days), fetches chatter from Hacker News and Reddit concurrently
- Generates 768-dim embeddings locally (no API call) and runs a `pgvector` cosine similarity check — skips anything above 0.82 similarity threshold
- Additional exact-text guard: skips identical (pros, cons, quotes) triples even across days
- For net-new chatter, prompts OpenAI (JSON mode) to return: `pros`, `cons`, `verbatim_quotes`, `source_url`, `sentiment_score` (−10 to +10), `implication_tag`

### 4. Price Intelligence

- **price_fetcher.py** downloads 59 days of 5-min OHLCV bars from yfinance for all public company targets
- **price_correlator.py** computes inter-event attribution: each event "owns" the price move from its timestamp to the next event or market close
- Confidence scoring based on event clustering density (±3h window)
- After-hours events shift attribution to the next regular market open

### 5. Reports

- **Daily report** aggregates the last 24h of sentiment, deduplicates repeated points, and prompts OpenAI to write a professional Market Intelligence Report
- **Weekly brief** (Mondays) is a 7-day strategic synthesis covering opportunities, risks, competitive shifts, and recommended actions

---

## Technology

| Layer | Technology |
|-------|-----------|
| LLM | OpenAI `gpt-4o-mini` |
| Embeddings | `sentence-transformers/all-mpnet-base-v2` (local, 768-dim) |
| Vector search | pgvector `<=>` cosine operator |
| Database | Supabase (PostgreSQL + pgvector) |
| Price data | yfinance (5-min bars, 59-day history, no key needed) |
| SEC filings | EDGAR submissions API (no auth required) |
| NLP filtering | spaCy `en_core_web_sm` |
| Dashboard | Streamlit |
| Charts | Altair (interactive, layered) |
| Automation | GitHub Actions + cron-job.org |

---

## Further Reading

| Document | Contents |
|----------|---------|
| [SETUP.md](SETUP.md) | Local setup, environment variables, running the pipeline |
| [DEPLOY.md](DEPLOY.md) | Deploying the Streamlit dashboard to Streamlit Community Cloud |
| [TECHNICAL_REFERENCE.md](TECHNICAL_REFERENCE.md) | Deep-dive architecture, design decisions, engineering problems solved |
| [supabase/README.md](supabase/README.md) | Database schema and migration guide |
