-- 010_source_type.sql
-- Adds source_type to sentiment rows to track which platforms contributed chatter.
-- Values are pipe-separated source names, e.g. "hn", "reddit", "hn|reddit|stackoverflow".

ALTER TABLE sentiment
  ADD COLUMN IF NOT EXISTS source_type VARCHAR(80);

COMMENT ON COLUMN sentiment.source_type IS
  'Pipe-separated list of chatter sources: hn, reddit, stackoverflow, google_news. NULL for rows created before this migration.';
