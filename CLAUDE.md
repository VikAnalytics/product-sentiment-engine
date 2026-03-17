# Product Sentiment Engine — Claude Context

## What This Project Does

Automated market intelligence pipeline that:
1. **Scouts** tech news from RSS feeds (TechCrunch, The Verge, Wired, Engadget, ZDNet)
2. **Tracks** real customer sentiment from Hacker News + Reddit discussions
3. **Reports** executive-ready market intelligence reports
4. **Displays** a Streamlit dashboard for real-time monitoring

Target audience: strategy leaders who want to know how the market reacts to tech product/company news.

---

## Architecture: Three-Stage Pipeline

```
RSS Feeds
   ↓
[scout.py]   → NLP filter → Gemini extracts targets + events → Supabase (targets, events)
   ↓
[tracker.py] → HN + Reddit fetch → local embeddings → pgvector dedupe → Gemini sentiment → Supabase (sentiment)
   ↓
[report.py]  → Aggregate + dedupe → Gemini report → reports/market_intelligence_YYYY-MM-DD.md
   ↓
[app.py]     → Streamlit dashboard reading from Supabase
```

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| LLM | Google Gemini 2.5 Flash (`gemini-2.5-flash`) |
| Embeddings | Local sentence-transformers (`all-mpnet-base-v2`, 768-dim) |
| Database | Supabase (PostgreSQL) + pgvector extension |
| UI | Streamlit |
| NLP filtering | spaCy (`en_core_web_sm`) |
| Data sources | RSS, HN Algolia API, Reddit API |
| Automation | GitHub Actions + external cron |

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
| `src/domain_resolver.py` | Company name → official domain via Gemini |
| `supabase/migrations/` | Schema evolution (run 000 → 007 in order) |
| `.github/workflows/run_engine.yml` | Daily automation |

---

## Database Schema (Supabase)

- **targets**: Companies/products (`id`, `name`, `target_type`, `description`, `status`, `logo_url`, `domain`, `parent_target_id`)
- **events**: News events per target (`id`, `target_id`, `headline`, `created_at`, `cached_analysis`)
- **sentiment**: Sentiment rows with embeddings (`id`, `target_id`, `event_id`, `pros`, `cons`, `verbatim_quotes`, `source_url`, `embedding vector(768)`, `sentiment_score SMALLINT`, `created_at`)
  - `sentiment_score`: AI-assigned score from -10 (very negative) to +10 (very positive); NULL for rows before migration 008
- **target_sentiment_summary**: AI-consolidated per-target summary (one row per target)
- **match_sentiment**: PostgreSQL function for pgvector cosine similarity search

---

## Environment Variables

Required in `.env` (never committed):
```
GEMINI_API_KEY=...
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
GEMINI_MODEL_NAME = "gemini-2.5-flash"
EMBEDDING_MODEL = "all-mpnet-base-v2"
MATCH_THRESHOLD = 0.82          # Vector similarity threshold for dedup
ARTICLES_PER_FEED = 10
HN_SEARCH_LIMIT = 3
REDDIT_SEARCH_LIMIT = 3
LOOKBACK_DAYS = 1               # Report window
MAX_PAYLOAD_CHARS_PER_FIELD = 2000
```

---

## Deduplication Strategy (Multi-Layered)

1. **Vector similarity** via `match_sentiment()` pgvector function (threshold: 0.82)
2. **Exact-text guard**: identical (pros, cons, quotes) triple for same event = skip
3. **Daily idempotency**: one sentiment row per (target, event) per calendar day
4. **Text normalization**: lowercase + strip punctuation + collapse spaces
5. **Word overlap**: 55%+ overlap = near-duplicate
6. **AI consolidation**: Gemini merges similar bullet points

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
- If Gemini rate-limits in report.py → generate mock/partial report
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

## Sentiment Scoring & Momentum (P1 — implemented)

- **Score field**: `sentiment_score SMALLINT` added to `sentiment` table (migration `008_sentiment_score.sql`)
- **Tracker prompt**: Gemini now outputs `PROS: ... | CONS: ... | QUOTES: ... | URL: ... | SCORE: N` (N = -10 to +10)
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
- Deployed to Streamlit Cloud using `requirements-app.txt` (lighter dependency set)
