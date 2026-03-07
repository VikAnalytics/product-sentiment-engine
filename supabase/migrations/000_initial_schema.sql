-- Product Sentiment Engine: initial schema (targets, sentiment, match_sentiment).
-- Run this first on a fresh Supabase project, or skip if you already have these tables.
-- Requires: pgvector extension (enable in Dashboard → Database → Extensions, or run "CREATE EXTENSION IF NOT EXISTS vector;").

-- Enable pgvector (skip if already enabled via Dashboard)
CREATE EXTENSION IF NOT EXISTS vector;

-- 1. Targets: companies/products we track (discovered by Scout)
CREATE TABLE IF NOT EXISTS public.targets (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  name text NOT NULL,
  target_type text NOT NULL,
  description text,
  status text NOT NULL DEFAULT 'tracking',
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_targets_status ON public.targets(status);
CREATE UNIQUE INDEX IF NOT EXISTS idx_targets_name ON public.targets(name);

-- 2. Sentiment: one row per day per target/event (pros, cons, quotes, embedding for dedup)
CREATE TABLE IF NOT EXISTS public.sentiment (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  target_id bigint NOT NULL REFERENCES public.targets(id) ON DELETE CASCADE,
  pros text,
  cons text,
  verbatim_quotes text,
  source_url text,
  embedding vector(768),
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_sentiment_target_id ON public.sentiment(target_id);
CREATE INDEX IF NOT EXISTS idx_sentiment_created_at ON public.sentiment(created_at);

-- 3. match_sentiment: find existing sentiment row with similar embedding (for vector dedup)
CREATE OR REPLACE FUNCTION public.match_sentiment(
  query_embedding vector(768),
  match_threshold float,
  p_target_id bigint
)
RETURNS TABLE (
  id bigint,
  target_id bigint,
  similarity float
)
LANGUAGE plpgsql
AS $$
BEGIN
  RETURN QUERY
  SELECT
    s.id,
    s.target_id,
    1 - (s.embedding <=> query_embedding) AS similarity
  FROM public.sentiment s
  WHERE
    s.target_id = p_target_id
    AND s.embedding IS NOT NULL
    AND 1 - (s.embedding <=> query_embedding) > match_threshold
  ORDER BY s.embedding <=> query_embedding
  LIMIT 1;
END;
$$;

COMMENT ON TABLE public.targets IS 'Companies/products to track; populated by Scout from RSS + AI.';
COMMENT ON TABLE public.sentiment IS 'Daily sentiment snapshots per target/event; pros, cons, quotes, and embedding for dedup.';
