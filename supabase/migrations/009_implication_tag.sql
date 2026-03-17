-- 009_implication_tag.sql
-- Adds a strategic implication tag to each sentiment row.
-- Extracted by Gemini alongside pros/cons to classify strategic urgency.

ALTER TABLE sentiment
  ADD COLUMN IF NOT EXISTS implication_tag VARCHAR(20)
    CHECK (implication_tag IN ('threat', 'opportunity', 'monitor', 'no_action'));

COMMENT ON COLUMN sentiment.implication_tag IS
  'Strategic classification: threat | opportunity | monitor | no_action. NULL for rows created before this migration.';
