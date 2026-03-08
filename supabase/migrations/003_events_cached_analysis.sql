-- Store strategic analysis per event so the dashboard can show report-generated analysis
-- without calling Gemini again. Populated when report.py runs and parses the report output.

ALTER TABLE public.events
  ADD COLUMN IF NOT EXISTS cached_analysis text,
  ADD COLUMN IF NOT EXISTS cached_analysis_at timestamptz;

COMMENT ON COLUMN public.events.cached_analysis IS 'Strategic analysis text from the last report run for this event; dashboard displays this instead of calling Gemini.';
COMMENT ON COLUMN public.events.cached_analysis_at IS 'When cached_analysis was written.';
