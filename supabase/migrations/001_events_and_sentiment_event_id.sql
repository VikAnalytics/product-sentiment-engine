-- Multiple events per target: track which event caused which sentiment.
-- Run this in Supabase SQL Editor if you use the dashboard, or via Supabase CLI.

-- 1. Events table: one row per headline/event per target
CREATE TABLE IF NOT EXISTS public.events (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  target_id uuid NOT NULL REFERENCES public.targets(id) ON DELETE CASCADE,
  headline text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_events_target_id ON public.events(target_id);

-- 2. Link sentiment to an event (nullable for existing rows)
ALTER TABLE public.sentiment
  ADD COLUMN IF NOT EXISTS event_id uuid REFERENCES public.events(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_sentiment_event_id ON public.sentiment(event_id);

-- 3. Update match_sentiment RPC to optionally scope by event_id.
-- If your existing RPC has a different name or signature, adjust accordingly.
-- This version expects: query_embedding, match_threshold, p_target_id, p_event_id (optional).
CREATE OR REPLACE FUNCTION public.match_sentiment(
  query_embedding vector(768),
  match_threshold float,
  p_target_id uuid,
  p_event_id uuid DEFAULT NULL
)
RETURNS TABLE (
  id uuid,
  target_id uuid,
  event_id uuid,
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
    AND ((p_event_id IS NULL AND s.event_id IS NULL) OR (p_event_id IS NOT NULL AND s.event_id = p_event_id))
    AND 1 - (s.embedding <=> query_embedding) > match_threshold
  ORDER BY s.embedding <=> query_embedding
  LIMIT 1;
END;
$$;

COMMENT ON TABLE public.events IS 'One row per headline/event discovered by Scout for a target; sentiment rows link here to track which event caused which sentiment.';
