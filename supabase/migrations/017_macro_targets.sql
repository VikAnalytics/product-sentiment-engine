-- Migration 017: Macro (geopolitics) targets + sector exposure mapping
-- MACRO target_type captures standalone geopolitical themes (US-China Tensions,
-- Russia-Ukraine, Semi Export Controls, OPEC, AI Regulation, etc.)
-- that drive company sentiment but aren't mappable to a single ticker.

-- Extend target_type CHECK to include MACRO.
ALTER TABLE targets DROP CONSTRAINT IF EXISTS targets_target_type_check;
ALTER TABLE targets
    ADD CONSTRAINT targets_target_type_check
    CHECK (target_type IN ('COMPANY', 'PRODUCT', 'MACRO'));

-- Many-to-many: which sectors does a macro theme touch, and at what weight.
CREATE TABLE IF NOT EXISTS macro_sector_exposure (
    id SERIAL PRIMARY KEY,
    macro_target_id INTEGER NOT NULL REFERENCES targets(id) ON DELETE CASCADE,
    sector VARCHAR(60) NOT NULL,
    exposure_weight NUMERIC(3, 2) NOT NULL DEFAULT 1.00 CHECK (exposure_weight BETWEEN 0 AND 1),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (macro_target_id, sector)
);

CREATE INDEX IF NOT EXISTS idx_macro_sector_macro  ON macro_sector_exposure(macro_target_id);
CREATE INDEX IF NOT EXISTS idx_macro_sector_sector ON macro_sector_exposure(sector);

COMMENT ON TABLE  macro_sector_exposure     IS 'Maps MACRO themes (geopolitics, regulatory) to the equity sectors they influence, with a 0..1 weight used by the simulator macro_exposure factor.';
COMMENT ON COLUMN macro_sector_exposure.exposure_weight IS '0 = no exposure; 1 = full exposure. Used to scale macro sentiment into the candidate ticker composite score.';
