# Supabase schema for Product Sentiment Engine

All tables and the `match_sentiment` RPC are defined in `migrations/`. Run them in order in the Supabase SQL Editor (or via Supabase CLI).

## Tables

| Table       | Purpose |
|------------|---------|
| **targets** | Companies/products to track. Populated by Scout (name, target_type, description, status). |
| **sentiment** | One row per day per target/event: pros, cons, verbatim_quotes, source_url, embedding (for vector dedup). |
| **events** | One row per headline/event per target. Scout inserts here; sentiment rows can link via `event_id`. |

## Migrations (run in order)

1. **000_initial_schema.sql**  
   - Enables `vector` extension (pgvector).  
   - Creates **targets** (id, name, target_type, description, status, created_at).  
   - Creates **sentiment** (id, target_id, pros, cons, verbatim_quotes, source_url, embedding vector(768), created_at).  
   - Creates **match_sentiment** (3 args: query_embedding, match_threshold, p_target_id).  
   Use this on a **fresh** project. Skip if you already have `targets` and `sentiment`.

2. **001_events_and_sentiment_event_id.sql**  
   - Creates **events** (id, target_id, headline, created_at).  
   - Adds **event_id** to **sentiment** (nullable, FK to events).  
   - Replaces **match_sentiment** with 4-arg version (adds optional `p_event_id`).  
   Run after 000 (or on an existing DB that already has targets/sentiment).

## Vector dimension

Migrations use **vector(768)**. If your embedding model uses a different size (e.g. 1536), change the type in both the `sentiment` table and the `match_sentiment` function to match.

## Backfill events (optional)

For existing targets with no rows in **events**, the app uses a virtual event (headline = `targets.description`). To create real event rows:

```sql
INSERT INTO public.events (target_id, headline)
SELECT id, COALESCE(NULLIF(TRIM(description), ''), '(general)')
FROM public.targets
WHERE status = 'tracking'
  AND NOT EXISTS (SELECT 1 FROM public.events e WHERE e.target_id = targets.id);
```

Existing sentiment rows keep `event_id = NULL`; new sentiment can link to these events.
