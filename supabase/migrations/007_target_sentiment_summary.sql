-- One row per target: AI-consolidated pros/cons (distinct differentiators). Raw sentiment rows stay unchanged.
CREATE TABLE IF NOT EXISTS public.target_sentiment_summary (
  target_id bigint NOT NULL PRIMARY KEY REFERENCES public.targets(id) ON DELETE CASCADE,
  pros text,
  cons text,
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_target_sentiment_summary_updated_at ON public.target_sentiment_summary(updated_at);

ALTER TABLE public.target_sentiment_summary ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Allow public read on target_sentiment_summary"
  ON public.target_sentiment_summary FOR SELECT USING (true);

COMMENT ON TABLE public.target_sentiment_summary IS 'One row per target: consolidated pros/cons (differentiators). Filled by scripts/dedupe_sentiment_in_db.py.';
