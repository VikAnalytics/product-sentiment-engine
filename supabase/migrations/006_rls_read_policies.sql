-- Allow the dashboard (and any client using anon or service_role key) to read targets, events, sentiment.
-- If RLS is enabled and no policies exist, Supabase returns 403/empty. This fixes that.

ALTER TABLE public.targets ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.events ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.sentiment ENABLE ROW LEVEL SECURITY;

-- Policies: allow SELECT for all roles (anon key used by Streamlit Cloud, or service_role which bypasses RLS anyway).
CREATE POLICY "Allow public read on targets"
  ON public.targets FOR SELECT USING (true);

CREATE POLICY "Allow public read on events"
  ON public.events FOR SELECT USING (true);

CREATE POLICY "Allow public read on sentiment"
  ON public.sentiment FOR SELECT USING (true);
