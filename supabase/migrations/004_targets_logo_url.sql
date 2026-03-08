-- Optional high-quality logo URL for companies and products (displayed in dashboard when set).
ALTER TABLE public.targets
ADD COLUMN IF NOT EXISTS logo_url text;

COMMENT ON COLUMN public.targets.logo_url IS 'Optional URL to a high-quality logo image for dashboard display.';
