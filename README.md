# 📈 Product Sentiment Engine

An autonomous, serverless market intelligence platform that aggregates tech news, extracts market-moving events, and synthesizes multi-channel public sentiment. 

Designed to separate "signal" from "noise," this engine utilizes Natural Language Processing (NLP), Large Language Models (LLMs), and Vector Embeddings to mathematically deduplicate market chatter and generate executive-grade intelligence reports with absolute data provenance.

## 🏗️ Architecture & Pipeline

The pipeline runs entirely on autopilot via a decoupled CI/CD scheduler, executing daily in three distinct phases:

### 1. The Scout (Ingestion & NLP Filtering)
* Ingests RSS feeds from top tech publications (TechCrunch, The Verge, Wired, etc.).
* Uses local NLP (`spaCy` lemmatization) to instantly filter noise and identify high-value articles based on root concepts (e.g., *acquire, launch, sue, layoff*).
* Prompts Google Gemini (2.5 Flash) to perform Multi-Entity Extraction, parsing out the exact Companies and Products mentioned.
* Upserts the structured entities to a relational cloud database (**Supabase**).

### 2. The Vector Intelligence Engine (Semantic Deduplication)
* Scrapes multi-channel data streams (Hacker News APIs, Reddit APIs) using strict 24-hour temporal filters to capture fresh public chatter.
* Converts unstructured internet noise into 768-dimensional mathematical coordinates using Gemini's Embedding Model (`text-embedding-004`).
* Executes a **Cosine Similarity** search against historical data in a `pgvector` database. If the new chatter is mathematically identical to yesterday's complaints, it is silently discarded.
* For statistically net-new signals, the LLM extracts strategic Pros, Cons, and verbatim "Voice of the Customer" quotes.

### 3. The Reporter (Executive Synthesis)
* Aggregates the verified, net-new daily intelligence.
* Drafts a formatted "Market Intelligence Report" summarizing company movements and product outlooks.
* Injects hyperlinked, verbatim user quotes directly into the report, ensuring executives can trace every insight back to its exact origin URL.
* Automatically commits the Markdown report back to the repository for historical archiving.

## 🚀 Key Engineering Wins

* **Semantic Deduplication (The Moat):** Transitioned from standard LLM summarization to Vector Math. By using `pgvector` to calculate the mathematical distance between today's market noise and yesterday's baseline, the engine guarantees that only true, net-new market signals reach the final report.
* **Absolute Data Provenance:** Eliminated LLM hallucination risk by forcing strict URL attribution. Every extracted quote is hard-linked to its exact Reddit or Hacker News origin, ensuring 100% auditability for executive decision-making.
* **Compute Cost Optimization:** Transitioned from a "Streaming" architecture to a "Batch Processing" architecture. By combining Python-based NLP pre-filtering, Vector deduplication, and batch LLM payloads, daily API token consumption was reduced by over 95%.
* **Decoupled Automation:** The pipeline runs ephemerally via **GitHub Actions**, triggered securely by an external webhook cron job (`cron-job.org`), requiring zero "always-on" server infrastructure.

## 🛠️ Tech Stack

* **Language:** Python 3.11
* **AI / Generative:** Google Gemini 2.5 Flash API
* **AI / Embeddings:** Google Gemini `text-embedding-004`
* **NLP:** `spaCy` (en_core_web_sm)
* **Database:** Supabase (PostgreSQL + `pgvector` extension)
* **Automation:** GitHub Actions, cron-job.org
* **Data Sources:** RSS (feedparser), Hacker News Algolia API, Reddit API
