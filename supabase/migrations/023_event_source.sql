-- Migration 023: keep the article an event came from.
--
-- events.headline held the model's one-sentence paraphrase, not the publication's
-- headline: scout read each entry's title, link and publish time and then threw
-- all three away. That produced editorialised "headlines" ("signifies major
-- shifts in energy policies"), no way to click through, and a dedupe guard that
-- could never work — a paraphrase differs every run, so the same story re-entered
-- daily (39 near-duplicate pairs in 14 days).
--
-- headline now holds the real title, summary holds the model's read, and
-- published_at is when the news happened rather than when the pipeline ran.
-- Backfilled from created_at and NOT NULL, so consumers can read one column
-- instead of COALESCE-ing at every call site; created_at stays as the ingest
-- time. Idempotent: safe to re-run.

ALTER TABLE public.events
    ADD COLUMN IF NOT EXISTS source_title text,
    ADD COLUMN IF NOT EXISTS source_url   text,
    ADD COLUMN IF NOT EXISTS summary      text,
    ADD COLUMN IF NOT EXISTS published_at timestamptz;

UPDATE public.events SET published_at = created_at WHERE published_at IS NULL;

ALTER TABLE public.events ALTER COLUMN published_at SET DEFAULT now();
ALTER TABLE public.events ALTER COLUMN published_at SET NOT NULL;

CREATE INDEX IF NOT EXISTS idx_events_published_at ON public.events(published_at DESC);

-- One story per target. Partial so the pre-023 rows, which have no URL, are exempt.
CREATE UNIQUE INDEX IF NOT EXISTS uq_events_target_source
    ON public.events(target_id, source_url) WHERE source_url IS NOT NULL;

COMMENT ON COLUMN public.events.headline IS
    'The publication''s own headline. Rows created before migration 023 hold the model paraphrase instead.';
COMMENT ON COLUMN public.events.summary IS
    'One-sentence read of what the article means for this target, written by the extraction model.';
COMMENT ON COLUMN public.events.source_url IS
    'Link to the article or filing. Doubles as the idempotency key for re-runs.';
COMMENT ON COLUMN public.events.published_at IS
    'When the article or filing was published. created_at is when this row was written.';
