# 📈 Product Sentiment Engine

An autonomous, serverless market intelligence platform that aggregates tech news, extracts market-moving events, and synthesizes multi-channel public sentiment.

Designed to separate "signal" from "noise," this engine uses Natural Language Processing (NLP), Large Language Models (LLMs), and Vector Embeddings to mathematically deduplicate market chatter and generate executive-grade intelligence reports with absolute data provenance.

## 🏗️ Architecture & Pipeline

The pipeline runs in three phases (manually or via CI/CD), with shared configuration and an **event-centric** data model so you can see which headline led to which sentiment.

### 1. The Scout (Ingestion & NLP Filtering)

* Ingests RSS feeds from top tech publications (TechCrunch, The Verge, Wired, Engadget, ZDNet).
* Uses local NLP (`spaCy` lemmatization) to filter noise and keep articles that match root concepts (e.g. *acquire, launch, sue, layoff*).
* Sends the filtered batch to Google Gemini (2.5 Flash) for multi-entity extraction: **Companies** and **Products** plus a one-sentence headline per entity.
* Writes to **Supabase**: new entities go into `targets` and one row per headline into `events`. Existing targets get **new event rows** for new headlines (multiple events per company/product).

### 2. The Vector Intelligence Engine (Semantic Deduplication)

* For each **target** and each of its **events**, fetches recent chatter from Hacker News and Reddit (24-hour window).
* Builds a **headline-focused** search query (target name + event headline) so results are about that specific story, not generic brand chatter.
* Converts chatter into a 768-dimensional vector using Gemini’s embedding API and runs a **cosine-similarity** check in `pgvector` (`match_sentiment`). Near-duplicate chatter for that event is discarded.
* For net-new chatter, the LLM extracts Pros, Cons, and verbatim “Voice of the Customer” quotes, then saves one **sentiment** row linked to that **event** (`event_id`), so you know which event drove which sentiment.

### 3. The Reporter (Executive Synthesis)

* Loads targets, their **events**, and sentiment from the last 24 hours (or configurable lookback).
* Aggregates pros/cons/quotes **per event**, deduplicates repeated sentences, and truncates long fields to stay within model limits.
* Asks Gemini to write a single **Market Intelligence Report** (Executive Summary, Target Deep Dives **per event**, Forward Outlook) with strict instructions to avoid repetition and to keep “Event: [headline]” visible so readers see which event caused which analysis.
* Writes the report to `reports/market_intelligence_YYYY-MM-DD.md`. Override output directory with the `REPORTS_DIR` env var.

## 🚀 Key Engineering Wins

* **Semantic Deduplication (The Moat):** Transitioned from standard LLM summarization to Vector Math. By using `pgvector` to calculate the mathematical distance between today's market noise and yesterday's baseline, the engine guarantees that only true, net-new market signals reach the final report.
* **Absolute Data Provenance:** Eliminated LLM hallucination risk by forcing strict URL attribution. Every extracted quote is hard-linked to its exact Reddit or Hacker News origin, ensuring 100% auditability for executive decision-making.
* **Compute Cost Optimization:** Transitioned from a "Streaming" architecture to a "Batch Processing" architecture. By combining Python-based NLP pre-filtering, Vector deduplication, and batch LLM payloads, daily API token consumption was reduced by over 95%.
* **Decoupled Automation:** The pipeline runs ephemerally via **GitHub Actions**, triggered securely by an external webhook cron job (`cron-job.org`), requiring zero "always-on" server infrastructure.

## 📊 Running the dashboard

From the **project root** (where this README is), start the Streamlit app:

```bash
streamlit run src/app.py
```

Use `src/app.py`, not `app.py` — the app lives in the `src/` folder. Ensure `.env` is in the project root with `SUPABASE_URL`, `SUPABASE_KEY`, and `GEMINI_API_KEY`.

## 🛠️ Tech Stack

| Layer | Technology |
|-------|------------|
| **Language** | Python 3.9+ (3.11 in CI) |
| **AI / Generative** | Google Gemini 2.5 Flash |
| **AI / Embeddings** | Google embedding API (model configurable in `config.py`; e.g. `text-embedding-004` or current equivalent) |
| **NLP** | spaCy (`en_core_web_sm`) |
| **Database** | Supabase (PostgreSQL + `pgvector`) |
| **Automation** | GitHub Actions, cron-job.org (or any scheduler) |
| **Data sources** | RSS (feedparser), Hacker News Algolia API, Reddit API |
