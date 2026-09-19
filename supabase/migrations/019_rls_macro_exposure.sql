-- Migration 019: RLS + anon read policy for macro_sector_exposure.
-- The web dashboard (anon key) reads sector exposure weights for the Macro view.
-- Writes still happen only through the pipeline's service_role key.
-- Idempotent: safe to re-run.

ALTER TABLE public.macro_sector_exposure ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Allow public read on macro_sector_exposure" ON public.macro_sector_exposure;
CREATE POLICY "Allow public read on macro_sector_exposure"
  ON public.macro_sector_exposure FOR SELECT USING (true);
