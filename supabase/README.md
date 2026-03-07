# Supabase schema for events

## Migration: multiple events per target

Run `migrations/001_events_and_sentiment_event_id.sql` in the Supabase SQL Editor (or via CLI). It:

1. Creates an **events** table: one row per headline/event per target.
2. Adds **event_id** to **sentiment** (nullable for existing rows).
3. Updates **match_sentiment** to accept optional `p_event_id` so vector dedup can be scoped per event.

## Vector dimension

The migration uses `vector(768)`. If your embedding model uses a different size (e.g. 1536), change the function parameter type in the migration to match your `sentiment.embedding` column.

## Backfill (optional)

For existing targets that have no rows in **events**, the app treats them as having one “virtual” event with headline = `targets.description`. To create real event rows for old targets (so the report shows “Event: …” explicitly), you can run:

```sql
INSERT INTO public.events (target_id, headline)
SELECT id, COALESCE(NULLIF(TRIM(description), ''), '(general)')
FROM public.targets
WHERE status = 'tracking'
  AND NOT EXISTS (SELECT 1 FROM public.events e WHERE e.target_id = targets.id);
```

Existing sentiment rows stay with `event_id = NULL`; new sentiment will link to events.
