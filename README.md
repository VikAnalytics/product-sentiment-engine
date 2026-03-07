# 📈 Product Sentiment Engine

An automated, cloud-native market intelligence pipeline that aggregates tech news, extracts market-moving events (product launches, M&A, leadership changes), and analyzes public sentiment using Natural Language Processing (NLP) and Large Language Models (LLMs).

## 🏗️ Architecture & Pipeline

This engine is designed to run entirely on autopilot via a decoupled CI/CD scheduler, utilizing batch processing to minimize API compute costs. 

The pipeline runs daily in three distinct phases:

1. **The Scout (Ingestion & NLP Filtering)**
   * Ingests RSS feeds from top tech publications (TechCrunch, The Verge, Wired, etc.).
   * Uses local NLP (`spaCy` lemmatization) to instantly filter noise and identify high-value articles based on root concepts (e.g., *acquire, launch, sue, layoff*).
   * Batches the filtered articles into a single, cost-optimized payload.
   * Prompts Google Gemini (2.5 Flash) to perform Multi-Entity Extraction, parsing out the exact Companies and Products mentioned.
   * Upserts the entities to a relational cloud database (**Supabase**).

2. **The Tracker (Sentiment Aggregation)**
   * Pulls the active tracking list from the cloud database.
   * Scrapes Hacker News APIs for public chatter and community sentiment surrounding each target.
   * Batches the raw internet noise and uses Gemini to synthesize actionable `Pros` and `Cons` for each entity.
   * Stores the structured sentiment data back in the cloud.

3. **The Reporter (Executive Synthesis)**
   * Aggregates the daily database records.
   * Uses generative AI to draft a formatted "Daily Executive Market Report" summarizing company movements, product intelligence, and strategic takeaways.
   * Automatically commits the Markdown report back to the repository for historical archiving.

## 🚀 Key Engineering Wins

* **Compute Cost Optimization:** Transitioned from a "Streaming" architecture (1 API call per article) to a "Batch Processing" architecture. By combining Python-based NLP pre-filtering with batch LLM payloads, daily API consumption was reduced by over 95%.
* **Idempotent Data Flow:** Built database-level checks to prevent duplicate entity logging across multiple daily runs.
* **Decoupled Automation:** Removed dependency on "always-on" web servers. The pipeline runs ephemerally via **GitHub Actions**, triggered securely by an external webhook cron job (`cron-job.org`).

## 🛠️ Tech Stack

* **Language:** Python 3.11
* **AI / LLM:** Google Gemini 2.5 Flash API
* **NLP:** `spaCy` (en_core_web_sm)
* **Database:** Supabase (PostgreSQL)
* **Automation:** GitHub Actions, cron-job.org
* **Data Sources:** RSS (feedparser), Hacker News Algolia API

