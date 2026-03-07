-- Multiple events per target: track which event caused which sentiment.
-- Run after 000_initial_schema.sql. Safe to run on DBs that already have targets/sentiment.

-- 1. Events table: one row per headline/event per target
CREATE TABLE IF NOT EXISTS public.events (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  target_id bigint NOT NULL REFERENCES public.targets(id) ON DELETE CASCADE,
  headline text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_events_target_id ON public.events(target_id);

-- 2. Link sentiment to an event (nullable for existing rows)
ALTER TABLE public.sentiment
  ADD COLUMN IF NOT EXISTS event_id bigint REFERENCES public.events(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_sentiment_event_id ON public.sentiment(event_id);

-- 3. Update match_sentiment to optionally scope by event_id
CREATE OR REPLACE FUNCTION public.match_sentiment(
  query_embedding vector(768),
  match_threshold float,
  p_target_id bigint,
  p_event_id bigint DEFAULT NULL
)
RETURNS TABLE (
  id bigint,
  target_id bigint,
  event_id bigint,
  similarity float
)
LANGUAGE plpgsql
AS $$
BEGIN
  RETURN QUERY
  SELECT
    s.id,
    s.target_id,
    s.event_id,
    1 - (s.embedding <=> query_embedding) AS similarity
  FROM public.sentiment s
  WHERE
    s.target_id = p_target_id
    AND s.embedding IS NOT NULL
    AND ((p_event_id IS NULL AND s.event_id IS NULL) OR (p_event_id IS NOT NULL AND s.event_id = p_event_id))
    AND 1 - (s.embedding <=> query_embedding) > match_threshold
  ORDER BY s.embedding <=> query_embedding
  LIMIT 1;
END;
$$;

COMMENT ON TABLE public.events IS 'One row per headline/event discovered by Scout for a target; sentiment rows link here to track which event caused which sentiment.';
