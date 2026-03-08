-- Optional domain (e.g. apple.com) for logo lookup via Clearbit and future use.
ALTER TABLE public.targets
ADD COLUMN IF NOT EXISTS domain text;

COMMENT ON COLUMN public.targets.domain IS 'Optional domain for logo lookup (e.g. apple.com). Used by scripts/update_logo_urls.py.';
