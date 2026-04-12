# Product Sentiment Engine — Claude Context

## What This Project Does

Dual-signal market intelligence platform that:
1. **Scouts** tech news from RSS feeds + SEC EDGAR filings (8-K, 10-Q, 10-K)
2. **Tracks** community sentiment from Hacker News + Reddit discussions
3. **Prices** stock reactions to each event via inter-event window attribution
4. **Simulates** AI-driven stock trading using a five-layer quant strategy on sentiment + price data
5. **Reports** executive-ready market intelligence reports
6. **Displays** a Streamlit dashboard with sentiment scores + price reaction badges + simulator

Target audience: strategy leaders and investment teams who want to know what news moved markets and why.

---

## Architecture: Three-Stage Pipeline

```
RSS Feeds + SEC EDGAR
   ↓
[scout.py]            → NLP filter → OpenAI extracts targets + events → Supabase (targets, events)
[sec_scout.py]        → EDGAR submissions API → 8-K/10-Q/10-K filing events → Supabase (events)
   ↓
[price_fetcher.py]    → yfinance 5-min OHLCV bars → Supabase (stock_prices)
[sim_trader.py execute] → settle yesterday's queued trades at today's open price
   ↓
[tracker.py]          → HN + Reddit fetch → local embeddings → pgvector dedupe → OpenAI sentiment → Supabase (sentiment)
[price_correlator.py] → inter-event window attribution → Supabase (price_reactions)
[sim_trader.py analyze] → 5-layer quant strategy → queue tomorrow's trades → Supabase (sim_pending_trades)
   ↓
[report.py]           → Aggregate + dedupe → OpenAI report → reports/market_intelligence_YYYY-MM-DD.md
[weekly_brief.py]     → 7-day synthesis → reports/weekly_brief_YYYY-WXX.md (Mondays)
[sim_trader.py snapshot] → fortnightly P&L snapshot → Supabase (sim_snapshots) (even-week Mondays)
   ↓
[app.py]              → Streamlit dashboard: sentiment + price badges + price chart + simulator
```

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| LLM | OpenAI `gpt-4o-mini` |
| Embeddings | Local sentence-transformers (`all-mpnet-base-v2`, 768-dim) |
| Database | Supabase (PostgreSQL) + pgvector extension |
| UI | Streamlit |
| NLP filtering | spaCy (`en_core_web_sm`) |
| Data sources | RSS, HN Algolia API, Reddit RSS, Google News RSS, SEC EDGAR |
| Price data | yfinance (5-min OHLCV, 59-day history, free) |
| Quant optimization | numpy + scipy (`SLSQP` solver for Markowitz max-Sharpe) |
| Automation | GitHub Actions + external cron (cron-job.org, 5pm EST daily) |

---

## Key Files

| File | Role |
|------|------|
| `src/config.py` | **Single source of truth** for all constants and client init |
| `src/scout.py` | Stage 1: RSS → targets + events |
| `src/tracker.py` | Stage 2: sentiment fetch + vector dedupe (largest logic) |
| `src/report.py` | Stage 3: aggregate + generate reports |
| `src/app.py` | Streamlit dashboard (~700 lines) |
| `src/sentiment_dedupe.py` | Text normalization + word-overlap dedupe utilities |
| `src/consolidate_pros_cons.py` | AI-powered merging of similar pros/cons |
| `src/normalize.py` | Target name normalization (word-order invariant) |
| `src/domain_resolver.py` | Company name → official domain via OpenAI |
| `src/sec_scout.py` | SEC EDGAR filing scout → events (8-K, 10-Q, 10-K, DEF 14A) |
| `src/price_fetcher.py` | Fetch 5-min OHLCV bars via yfinance → stock_prices table |
| `src/price_correlator.py` | Inter-event price attribution → price_reactions table |
| `src/sim_trader.py` | AI stock simulator: execute/analyze/snapshot (five-layer quant strategy) |
| `supabase/migrations/` | Schema evolution (run 000 → 015 in order) |
| `.github/workflows/run_engine.yml` | Daily automation |

---

## Database Schema (Supabase)

- **targets**: Companies/products (`id`, `name`, `target_type`, `description`, `status`, `logo_url`, `domain`, `parent_target_id`, `ticker`, `sector`, `is_f500`)
- **events**: News events per target (`id`, `target_id`, `headline`, `created_at`, `cached_analysis`)
- **sentiment**: Sentiment rows with embeddings (`id`, `target_id`, `event_id`, `pros`, `cons`, `verbatim_quotes`, `source_url`, `embedding vector(768)`, `sentiment_score SMALLINT`, `created_at`)
  - `sentiment_score`: AI-assigned score from -10 (very negative) to +10 (very positive); NULL for rows before migration 008
- **target_sentiment_summary**: AI-consolidated per-target summary (one row per target)
- **match_sentiment**: PostgreSQL function for pgvector cosine similarity search
- **sim_portfolio**: Singleton row tracking cash balance + peak value (for drawdown)
- **sim_holdings**: One row per open position (`ticker UNIQUE`, `shares`, `avg_buy_price`, `total_cost`)
- **sim_trades**: Full trade log — every executed or skipped BUY/SELL with rationale
- **sim_pending_trades**: Trades queued by analyze step, consumed by next day's execute
- **sim_snapshots**: Fortnightly portfolio value snapshots (P&L vs $1,000 starting capital)
- **stock_prices**: 5-min OHLCV bars per target (`target_id`, `ts`, `open`, `high`, `low`, `close`, `volume`)
- **price_reactions**: Inter-event attribution per event (`event_id`, `ticker`, `price_at_event`, `window_return_pct`, `reaction_1d/3d/7d`, `market_session`, `confidence`, `confidence_reason`)

---

## Environment Variables

Required in `.env` (never committed):
```
OPENAI_API_KEY=...
SUPABASE_URL=...
SUPABASE_KEY=...     # service_role key
```

Optional overrides:
```
LOG_LEVEL=DEBUG               # default: INFO
LOG_FILE=logs/tracker.log     # rotating file handler
TRACKER_DRY_RUN=1             # test without writing to DB
TRACKER_MAX_EVENTS=5          # cap events processed (for testing)
REPORTS_DIR=/abs/path/        # default: reports/
EMBED_MODEL_NAME=all-mpnet-base-v2
```

---

## Running the Pipeline Locally

```bash
# Install
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python -m spacy download en_core_web_sm

# Run pipeline stages (always set PYTHONPATH=src)
PYTHONPATH=src python src/scout.py
PYTHONPATH=src python src/tracker.py
PYTHONPATH=src python src/report.py

# Dashboard
PYTHONPATH=src streamlit run src/app.py
```

For safe testing of tracker: `TRACKER_DRY_RUN=1 TRACKER_MAX_EVENTS=5 PYTHONPATH=src python src/tracker.py`

---

## Key Constants (`src/config.py`)

```python
OPENAI_MODEL_NAME = "gpt-4o-mini"
EMBEDDING_MODEL = "all-mpnet-base-v2"
MATCH_THRESHOLD = 0.82          # Vector similarity threshold for dedup
ARTICLES_PER_FEED = 10
HN_SEARCH_LIMIT = 3
REDDIT_SEARCH_LIMIT = 3
GOOGLE_NEWS_LIMIT = 3
LOOKBACK_DAYS = 1               # Report window
MAX_PAYLOAD_CHARS_PER_FIELD = 2000
MAX_CHATTER_CHARS = 3000        # Truncate combined chatter before AI call (token savings)
EVENT_MAX_AGE_DAYS = 14         # Skip events older than this in tracker
REPORT_EVENT_MAX_AGE_DAYS = 3  # Only include events created within last 3 days in daily report
```

---

## Deduplication Strategy (Multi-Layered)

1. **Vector similarity** via `match_sentiment()` pgvector function (threshold: 0.82)
2. **Exact-text guard**: identical (pros, cons, quotes) triple for same event = skip
3. **Daily idempotency**: one sentiment row per (target, event) per calendar day
4. **Text normalization**: lowercase + strip punctuation + collapse spaces
5. **Word overlap**: 55%+ overlap = near-duplicate
6. **AI consolidation**: OpenAI merges similar bullet points

---

## Naming Conventions

- `target_type`: `"COMPANY"` or `"PRODUCT"` (uppercase)
- `target.status`: `"tracking"` (lowercase) — only tracked targets are processed
- Sentiment fields: `pros`, `cons`, `verbatim_quotes`, `source_url`
- File dates: `YYYY-MM-DD`
- DB timestamps: `YYYY-MM-DDTHH:MM:SSZ`

---

## Error Handling Patterns

- API failures are logged but pipeline continues (silent fallbacks)
- If embedding fails → skip vector dedupe, still write row
- If OpenAI rate-limits in report.py → generate mock/partial report
- Scripts use `try/except` blocks with verbose logging at each stage

---

## Maintenance Scripts (`scripts/`)

| Script | Purpose |
|--------|---------|
| `dedupe_sentiment_in_db.py` | Backfill existing rows into `target_sentiment_summary` |
| `deduplicate_sentiment_rows.py` | Remove exact duplicate sentiment rows |
| `find_duplicate_targets.py` | Identify similar target names |
| `merge_duplicate_targets.py` | Merge duplicate targets + sentiment |
| `link_products_to_companies.py` | Batch link products to parent companies |
| `update_logo_urls.py` | Fetch logos via Clearbit / Google Favicon API |
| `test_supabase_key.py` | Validate DB connection |

---

## Tracker Performance Optimizations (implemented)

- **Parallel HTTP fetches**: HN, Reddit, and Google News are fetched concurrently per event via `ThreadPoolExecutor(max_workers=3)` — ~3x faster than sequential
- **Chatter truncation**: `combined_chatter` capped at `MAX_CHATTER_CHARS=3000` before the AI call (token savings)
- **HN comment cap**: `comment_text` truncated to 300 chars, consistent with Reddit (150) and Google News (200)
- **Old event skip**: Events older than `EVENT_MAX_AGE_DAYS=14` are skipped before any HTTP calls (avoids dead network calls on stale news)
- **Sleep on skip paths removed**: `time.sleep()` only fires after a real API round-trip, not on already-scanned/no-chatter/vector-match skips
- **Reddit source**: Switched from `api.reddit.com` JSON (blocked 403 since 2023) to `www.reddit.com/search.rss` via feedparser — no auth required
- **Stack Overflow removed**: Was returning 429 consistently; removed entirely

## Expanded News Coverage (implemented)

**`scout.py` RSS feeds** (21 total): TechCrunch, The Verge, Wired, Engadget, ZDNet, Reuters Business, Reuters Financial, Yahoo Finance, MarketWatch (x2), CNBC (x2), Benzinga, NYT Business, AP Business, Fortune, SEC EDGAR 8-K atom feed, FTC press releases, FDA news releases.

**`scout.py` CORE_LEMMAS** expanded with M&A (`takeover`, `buyout`, `ipo`, `divest`), regulatory (`approve`, `antitrust`, `sanction`, `recall`), macro (`tariff`, `inflation`, `rate`, `recession`), management (`ceo`, `appoint`, `succession`).

**`tracker.py` sources** (6 per event, concurrent):
1. Hacker News — Algolia API
2. Reddit — `reddit.com/search.rss`
3. Google News Financial — earnings/revenue query
4. Google News General — broad stock-moving query (M&A, regulatory, analyst, lawsuit, tariff)
5. StockTwits — public stream per ticker (public companies only)
6. Yahoo Finance — per-ticker RSS (public companies only)

`MAX_CHATTER_CHARS` = 5000 (was 3000).

---

## Sentiment Scoring & Momentum (P1 — implemented)

- **Score field**: `sentiment_score SMALLINT` added to `sentiment` table (migration `008_sentiment_score.sql`)
- **Tracker prompt**: OpenAI now outputs JSON with keys `pros, cons, verbatim_quotes, source_url, sentiment_score, implication_tag`
- **Parser**: `_parse_ai_sentiment_line()` handles 4-part (old) and 5-part (new) format; clamps score to [-10, +10]
- **Dashboard badges**: Each event card shows a color-coded score pill; target hero shows current avg score + momentum vs. last 7 days
- **Score color bands**: ≥7 green, 3–6 lime, -2–+2 gray, -6–-3 orange, ≤-7 red
- **Momentum**: computed as avg(last 7 days) − avg(prior 7 days); shown as ↑/↓ arrow on target hero
- **Report**: score included in payload as `SENTIMENT SCORE: N/10`; AI prompted to interpret it

## Weekly Executive Brief (P3 — implemented)

- **Script**: `src/weekly_brief.py` — 7-day lookback, strategic synthesis prompt
- **Output**: `reports/weekly_brief_YYYY-WXX.md` (e.g. `weekly_brief_2026-W12.md`)
- **Prompt focus**: Week in Review, Top 3 Opportunities, Top 3 Risks, Competitive Shifts, Recommended Actions, Score Breakdown
- **Dashboard**: 4th tab `📋 Weekly Brief` reads the latest file; dropdown to browse past weeks
- **GitHub Actions**: `run_engine.yml` — Monday 07:00 UTC schedule added; `weekly_brief.py` runs only on scheduled (Monday) triggers, not manual dispatches
- **Run manually**: `PYTHONPATH=src python src/weekly_brief.py`

## Structured Gemini Output — JSON Mode (P8 — implemented)

- **`config.py`**: `get_json_model()` returns a `GenerativeModel` with `generation_config=GenerationConfig(response_mime_type="application/json")`; `get_model()` unchanged for report/brief free-form text
- **`tracker.py`**: `_parse_json_sentiment(text)` replaces pipe parser as primary; validates required keys, clamps score, rejects invalid tags; returns `None` on bad JSON
- **Fallback chain**: if JSON parse fails → `_parse_ai_sentiment_line()` (pipe format) tries next; ensures zero regression against any model responses that don't respect JSON mode
- **Prompt**: rewritten as plain JSON schema description (no `PROS: | CONS: |` pipe instruction); uses double-braced `{{...}}` for f-string safety
- **Cleanup**: removed unused `model = get_model()` and `get_model` import from `run_tracker()`; `get_json_model()` called inline per extraction

## Source Diversity (P7 — implemented)

- **Migration**: `010_source_type.sql` — `source_type VARCHAR(80)` on `sentiment` table (pipe-separated source names)
- **New tracker sources**:
  - `search_stackoverflow(query)` — Stack Overflow API (free, no key, 300 req/day); returns question titles + body snippets
  - `search_google_news_financial(name)` — Google News RSS filtered for `{name} earnings OR revenue OR quarterly results`; uses `feedparser`
- **Source tagging**: `_build_source_type(hn, reddit, so, news)` → e.g. `"hn|stackoverflow|google_news"` stored in `source_type`
- **Scout feeds**: Added `feeds.reuters.com/reuters/businessNews` and `finance.yahoo.com/news/rssindex`; expanded `CORE_LEMMAS` with earnings terms: `beat, miss, guidance, forecast, outlook, quarter, quarterly, downgrade, upgrade`
- **Config**: `STACKOVERFLOW_SEARCH_LIMIT = 3`, `GOOGLE_NEWS_LIMIT = 3`
- **Dashboard**: Event card shows `Sources: HN, Reddit, Stack Overflow, Financial News` caption alongside score/tag badges
- **Lint**: Removed unused `get_embedding_model_name` import from tracker

## Strategic Implication Tagging (P6 — implemented)

- **Migration**: `009_implication_tag.sql` — `implication_tag VARCHAR(20)` on `sentiment` table; CHECK constraint: `threat | opportunity | monitor | no_action`
- **Tracker prompt**: now 6 fields: `PROS | CONS | QUOTES | URL | SCORE | TAG`; TAG guidelines explain each label
- **Parser**: `_parse_ai_sentiment_line()` handles 4/5/6-part format; invalid tags are silently dropped (None)
- **Tag priority** (for resolving dominant tag across multiple rows): `threat > opportunity > monitor > no_action`
- **Event card expander label**: prefixed with tag emoji (🔴/🟢/🟡/⚪) so executives scan urgency without opening
- **Event card body**: score badge + tag badge shown side by side in columns
- **Lint fixes**: `import pandas as pd` moved to top-level; all `fetch_*` functions typed `Optional[int]` to clear Pylance unreachable hints

## Trend Charts (P5 — implemented)

- **Deep Dive tab**: `📈 Sentiment trend` expander (collapsed by default) — Altair chart with 30/90/All-time toggle
- **Chart layers**: neutral band (−2 to +2 gray), zero rule, daily avg bars, 7-day rolling avg line + dots; fully interactive (zoom/pan)
- **Compare tab**: mini 30-day sparkline (`st.line_chart`, height=80) in each comparison card
- **Core helper**: `_build_score_timeseries(score_rows, lookback_days)` → pandas DataFrame with `date`, `score`, `rolling_avg`; `render_trend_chart(score_rows, name)` renders the full Altair chart

## Competitive Comparison View (P2 — implemented)

- **Tab layout**: Main area now has 3 tabs — `🔍 Deep Dive` (existing), `⚡ Compare`, `🏆 Rankings`
- **Compare tab**: Multi-select up to 4 targets; side-by-side columns show logo, score badge, momentum, top 3 pros/cons
- **Rankings tab**: All tracked targets ranked by avg sentiment score (desc); unscored targets sorted last; shows score (color-coded), momentum trend arrow, event count, reading count
- **New fetch helpers**: `fetch_all_scores_batch()` (one DB call for all scores), `fetch_event_count_by_target()`, `fetch_recent_sentiment_for_target(target_id, limit)`

## Dashboard Notes (`src/app.py`)

- Sidebar: select company → filter products by parent company
- Main view: target hero card (logo + description) → events timeline → aggregated company sentiment
- Filters out placeholder strings: "None identified", "No pros mentioned", etc.
- Uses `st.cache_data` for DB queries
- Optional: `streamlit-searchbox` for faster target navigation
- Deployed to Streamlit Cloud using `src/requirements.txt` (lighter dependency set; Streamlit Cloud auto-detects this when entrypoint is `src/app.py`)

## Price Intelligence Layer (implemented)

- **Migrations**: `011_ticker.sql` (ticker on targets), `012_stock_prices.sql`, `013_price_reactions.sql`
- **Tickers**: 52 targets have tickers set (public companies + subsidiaries sharing parent ticker); private companies have NULL ticker
- **`price_fetcher.py`**: Downloads 59 days of 5-min OHLCV bars via yfinance for all targets with a ticker; upserts into `stock_prices`; deduplicates by ticker to avoid fetching the same company twice for subsidiaries
- **`price_correlator.py`**: For each event on a public company, computes: `price_at_event` (close at nearest 5-min bar), `window_return_pct` (inter-event: price at this event → next event or market close), `reaction_1d/3d/7d` (broader context), `confidence` (high/medium/low based on event isolation within ±3h), `market_session` (regular/premarket/afterhours — afterhours events shift attribution to next market open)
- **`sec_scout.py`**: Polls EDGAR submissions API (`data.sec.gov/submissions/CIK{}.json`) for 8-K, 10-Q, 10-K, DEF 14A filings filed in last 7 days; uses `company_tickers.json` for ticker→CIK mapping; inserts filing events with `[FORM_TYPE] Company — date SEC filing` headline; idempotent via exact headline match
- **Dashboard**: Event cards show price reaction badges (inter-event %, 1d/3d/7d %, confidence label) for public company events; Deep Dive tab has a collapsible "Price Chart — TICKER" expander with Altair line chart + orange event markers; private companies show no price section
- **GitHub Actions**: `sec_scout.py`, `price_fetcher.py`, `price_correlator.py` added to daily pipeline after `scout.py` and before `report.py`
- **Attribution model**: Probabilistic correlation (not causation) — each event "owns" the price move until the next event or market close; confidence degrades when multiple events cluster within 3 hours or when the move is during premarket/afterhours
- **Price chart pagination**: `fetch_price_series()` paginates in 1000-row pages via `.range()` to bypass Supabase's default PostgREST row cap — critical for 59d window (~4600 bars)
- **Event markers**: positioned at actual close price on the event date (`y=alt.Y("close:Q")`) — not a fixed pixel offset
- **yfinance pinned**: `yfinance==1.2.0` in requirements.txt for GitHub Actions consistency

## Sector Classification + Fortune 500 (implemented)

- **Migration**: `014_sector.sql` — `sector VARCHAR(60)` and `is_f500 BOOLEAN DEFAULT FALSE` on targets
- **Sectors**: Technology, Gaming, Consumer Electronics, Automotive & EV, Media & Entertainment, Finance & Fintech, Retail, Defense & Aerospace, Mobility, Sports & Events, Education, Social Media, Luxury, Transport, Industrials
- **Fortune 500**: US companies only; 151 tracked companies all classified as of 2026-03-20
- **Dashboard sidebar**: sector multiselect + F500 checkbox filter above the Companies expander; Rankings tab filters to companies only

## News Feed View (implemented)

- **Sidebar nav**: "News Feed / Analysis / Simulator" radio toggle at the top of the sidebar (above sector filters)
- **News Feed mode**: full-screen chronological feed of all tracked headlines across all companies
  - Date picker (calendar) — browse any past day, not just today
  - Sector multiselect filter
  - Each card: company name + sector pill + relative time + headline + score badge + implication tag + one-line description from top pro
  - `fetch_todays_headlines(lookback_hours)` in `app.py`, TTL=120s
- **Analysis mode**: existing Deep Dive / Compare / Rankings / Weekly Brief tabs
- **Simulator mode**: full-page portfolio view (see below)

## AI Stock Simulator (implemented)

- **Migration**: `015_simulator.sql` — 5 tables: `sim_portfolio`, `sim_holdings`, `sim_trades`, `sim_pending_trades`, `sim_snapshots`
- **Script**: `src/sim_trader.py` — three actions: `--action execute | analyze | snapshot`
- **Capital**: $1,000 starting cash, persistent (compounds over time, not reset per round)
- **Trade execution**: BUY/SELL only at market open price (first 5-min bar from `stock_prices`); trades queued by `analyze`, consumed by next day's `execute`
- **Timing**: cron fires 5pm EST → `execute` uses today's 9:30am open (already in DB) → correctly simulates "bought at open"

**Five-layer quant strategy (analyze step):**
1. **Multi-Factor Ranking**: 5 Z-scored factors (sentiment momentum 30%, price momentum 25%, inverse volatility 15%, signal consistency 15%, historical accuracy 15%) → top 20% of universe
2. **EV Gate**: p_win > 55% AND expected return > 3% from `price_reactions` history (min 5 samples)
3. **Signal Consensus**: 4/5 factors must be directionally positive
4. **Regime Filter**: ≥50% of universe must have positive sentiment momentum (risk-off = hold cash)
5. **Markowitz + Kelly**: `scipy` max-Sharpe optimization with Ledoit-Wolf covariance shrinkage; Kelly Criterion caps each position at 25%; max 80% of cash deployed

**Risk management (execute step):**
- Stop-loss: −8% from avg cost → forced SELL
- Take-profit: +25% → forced SELL
- Sentiment stop: `implication_tag='threat'` or today's avg score < −3 → forced SELL
- Max drawdown: −15% from `peak_value` → liquidate all + clear pending queue

**Dashboard**: Sidebar "Simulator" view shows portfolio summary (cash / holdings value / total P&L), open positions with unrealized P&L, queued trades for tomorrow, recent trade log, and Altair portfolio growth chart from fortnightly snapshots.

**GitHub Actions**: `execute` added to daily pipeline after `price_fetcher`; `analyze` added after `price_correlator`; `snapshot` runs on even-week Mondays alongside `weekly_brief`

**Dependencies**: `numpy` and `scipy` added to `requirements.txt`

## Key Implementation Notes

- **Supabase 1000-row cap**: PostgREST silently truncates at 1000 rows even with `.limit(10000)`. Any query returning >1000 rows must loop with `.range(offset, offset+999)`.
- **Python 3.9 datetime**: `_parse_iso_dt(ts)` helper normalises fractional seconds to exactly 6 digits before `fromisoformat()`. Supabase timestamps can have 5 decimal places which crash Python 3.9.
- **Report event age**: `REPORT_EVENT_MAX_AGE_DAYS=3` in config.py — report only includes events created in last 3 days to prevent stale headlines resurfacing.
- **Product logos**: `_target_logo_url()` falls back to parent company logo when product has no logo set.
- **Streamlit theme**: `.streamlit/config.toml` must use `base=dark` to match custom CSS — light base causes white-on-white dropdowns.
