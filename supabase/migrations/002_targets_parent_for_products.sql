-- Products can belong to a company: filter dashboard Products by selected Company.
-- Run after 001. Safe on existing DBs.

ALTER TABLE public.targets
  ADD COLUMN IF NOT EXISTS parent_target_id bigint REFERENCES public.targets(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_targets_parent_target_id ON public.targets(parent_target_id);

COMMENT ON COLUMN public.targets.parent_target_id IS 'For PRODUCT targets: the COMPANY target this product belongs to. Null for companies or ungrouped products.';
