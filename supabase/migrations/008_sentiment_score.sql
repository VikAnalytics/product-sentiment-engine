-- 008_sentiment_score.sql
-- Adds a numeric sentiment score (-10 to +10) to each sentiment row.
-- Extracted by Gemini alongside pros/cons so we can track momentum over time.

ALTER TABLE sentiment
  ADD COLUMN IF NOT EXISTS sentiment_score SMALLINT
    CHECK (sentiment_score >= -10 AND sentiment_score <= 10);

COMMENT ON COLUMN sentiment.sentiment_score IS
  'AI-assigned sentiment score: -10 (very negative) to +10 (very positive). NULL for rows created before this migration.';
