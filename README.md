# Market Intelligence Engine

A dual-signal market intelligence platform for strategy leaders and investment teams.

**Live dashboard:** [market-intelligence-engine-five.vercel.app](https://market-intelligence-engine-five.vercel.app)

---

## Who This Is For

Strategy leaders and investment teams who want to answer questions like:

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
| Geopolitics themes | Reuters World + BBC + AP + Politico EU + Al Jazeera + Foreign Policy | Sentiment on 8 MACRO themes (US-China, Russia-Ukraine, Semi export controls, OPEC, AI regulation, …) |
| Community sentiment | Hacker News + Reddit | Pros, cons, verbatim quotes with source links |
| Stock price reactions | yfinance 5-min OHLCV bars | Inter-event price attribution per event |
| Structured intelligence | OpenAI `gpt-4o-mini` | Daily reports + weekly executive brief |
| AI portfolio simulation | Six-factor quant strategy on sentiment + price + macro data | Virtual $1,000 portfolio with daily trades |

Surfaces through two outputs:

- **Next.js web dashboard** (Vercel) — news feed, sentiment scores, price reaction badges, competitive rankings, AI stock simulator
- **Market Intelligence Report** — board-ready markdown written daily, stored in `reports/`

---

## How to Use the Dashboard

1. Open the [live dashboard](https://market-intelligence-engine-five.vercel.app) (or run locally — see [docs/SETUP.md](docs/SETUP.md)).
2. Use the **sidebar** to navigate:
   - **News Feed** — chronological view of all tracked headlines; filter by date and sector
   - **Analysis** — deep dive into a specific company or product
   - **Simulator** — AI stock simulation portfolio; see open positions, queued trades, and performance
3. In **Analysis** mode, select a company or product to see:
   - Events timeline with sentiment scores and implication tags (threat / opportunity / monitor)
   - Price reaction badges for public companies (inter-event %, 1d/3d/7d)
   - Sentiment trend chart (30 / 90 / all-time)
4. Use **Compare** to put up to 4 targets side by side.
5. Use **Rankings** to see all companies ranked by average sentiment score.

If you only need to consume insights, you can stop here. The rest of this documentation is for the team running the system.

---

## Architecture

```
RSS Feeds + SEC EDGAR
        ↓
   scout.py            NLP filter → OpenAI extracts targets + events → Supabase
   sec_scout.py        EDGAR submissions API → 8-K/10-Q/10-K events → Supabase
        ↓
   price_fetcher.py    yfinance 5-min OHLCV bars → Supabase
   sim_trader.py       execute: settle yesterday's queued trades at today's open price
        ↓
   tracker.py          HN + Reddit → local embeddings → pgvector dedupe → OpenAI sentiment → Supabase
   price_correlator.py Inter-event window attribution → Supabase
   sim_trader.py       analyze: multi-factor quant strategy → queue tomorrow's trades
        ↓
   report.py           Aggregate + dedupe → OpenAI → reports/market_intelligence_YYYY-MM-DD.md
   weekly_brief.py     7-day strategic synthesis → reports/weekly_brief_YYYY-WXX.md (Mondays)
   sim_trader.py       snapshot: fortnightly portfolio performance (even-week Mondays)
        ↓
   web/                Next.js dashboard (deployed on Vercel)
```

---

## How It Works

### 1. Scout — Discover companies, products, and events

Reads RSS from TechCrunch, The Verge, Wired, Reuters, Yahoo Finance, and 17 other feeds. Uses spaCy to keep only articles matching material business concepts (launches, acquisitions, layoffs, earnings, regulatory probes, etc.) — eliminates ~60% of articles before any LLM call. Uses OpenAI to extract the company/product name and write structured rows into `targets` and `events`.

### 2. SEC Scout — EDGAR filing events

Polls EDGAR's submissions API for each tracked public company. Inserts 8-K, 10-Q, 10-K, and DEF 14A filings as events. No API key required. Idempotent: exact headline match check before inserting.

### 3. Tracker — Market sentiment per event

For each event (last 14 days), fetches chatter from Hacker News and Reddit concurrently. Generates 768-dim embeddings locally (no API call) and runs pgvector cosine similarity dedup — skips anything above 0.82 similarity threshold. For net-new chatter, prompts OpenAI (JSON mode) to return: `pros`, `cons`, `verbatim_quotes`, `source_url`, `sentiment_score` (−10 to +10), `implication_tag`.

### 4. Price Intelligence

**price_fetcher.py** downloads 59 days of 5-min OHLCV bars from yfinance for all tracked public companies. **price_correlator.py** computes inter-event attribution: each event "owns" the price move from its timestamp to the next event or market close. Confidence scoring based on event clustering density (±3h window). After-hours events shift attribution to the next regular market open.

### 5. AI Stock Simulator

Persistent $1,000 virtual portfolio. Six-factor quant strategy (sentiment momentum, price momentum, inverse volatility, signal consistency, historical accuracy, macro exposure) → EV gate → 3/6 signal consensus → regime filter → Markowitz max-Sharpe → Kelly sizing. Trades execute at next day's market open. Risk-side: trailing stop (−6% from post-entry peak), fixed stop-loss (−8%), take-profit (+25%), sentiment stop (threat tag or score < −3), max drawdown guard (−15%), rotation SELL (evict held positions with negative composite when stronger BUYs queue). No real money. Run `--action diagnose` anytime to inspect the funnel.

### 6. Reports

**Daily report** aggregates the last 24h of sentiment, deduplicates repeated points, and prompts OpenAI to write a professional Market Intelligence Report. **Weekly brief** (Mondays) is a 7-day strategic synthesis covering opportunities, risks, competitive shifts, and recommended actions.

### 7. MACRO Themes (Geopolitics + Regulation)

Eight seeded themes (US-China Trade Tensions, Russia-Ukraine Conflict, Semiconductor Export Controls, Tariffs, OPEC, AI Regulation, Middle East Tensions, Climate Policy) carry their own event/sentiment timelines. Each theme maps to affected sectors with a 0..1 exposure weight. The simulator's `macro_exposure` factor penalizes candidates whose sector has an active negative-sentiment theme. See `scripts/seed_macro_targets.py`.

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
| Web dashboard | Next.js 16 (App Router) + TypeScript + Tailwind CSS |
| Hosting | Vercel (auto-deploys on push to `main`) |
| Charts | Altair (pipeline reports), SVG (web dashboard) |
| Automation | GitHub Actions + cron-job.org |

---

## Repository Structure

```
├── src/                    Python pipeline (scout, tracker, report, simulator, telemetry, logging)
├── web/                    Next.js web dashboard (deployed on Vercel)
├── supabase/migrations/    Database schema — apply 000 → 018 in numeric order
├── scripts/                One-off maintenance scripts (dedup, merge, seed_macro_targets, ai_link_products)
├── tests/                  Pytest suite covering pure functions (run: `pytest`)
├── reports/                Generated daily reports and weekly briefs
├── docs/                   Setup, deployment, and technical reference
├── Dockerfile              Reproducible Python 3.11-slim image
├── pytest.ini              Test runner config
├── requirements.txt        Runtime deps
├── requirements-dev.txt    Dev/test deps (pytest, pytest-cov)
└── .github/workflows/      GitHub Actions: daily pipeline automation
```

## Running Tests

```bash
pip install -r requirements-dev.txt
pytest             # 59 tests, no network / API calls required
```

## Docker (optional)

```bash
docker build -t psengine .
docker run --rm --env-file .env -p 8501:8501 psengine   # dashboard
docker run --rm --env-file .env psengine python src/scout.py
docker run --rm --env-file .env psengine python src/sim_trader.py --action diagnose
```

---

## Further Reading

| Document | Contents |
|----------|---------|
| [docs/SETUP.md](docs/SETUP.md) | Local setup, environment variables, running the pipeline |
| [docs/DEPLOY.md](docs/DEPLOY.md) | Deploying the web dashboard to Vercel |
| [docs/TECHNICAL_REFERENCE.md](docs/TECHNICAL_REFERENCE.md) | Architecture deep dive, design decisions, engineering problems solved |
| [web/README.md](web/README.md) | Web dashboard local development |
| [supabase/README.md](supabase/README.md) | Database schema and migration guide |
| [scripts/README.md](scripts/README.md) | Maintenance script usage |
