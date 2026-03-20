-- Migration 014: Sector classification and Fortune 500 flag on targets
-- sector: industry vertical (e.g. Technology, Healthcare, Defense)
-- is_f500: TRUE if the company is on the Fortune 500 list

ALTER TABLE targets
    ADD COLUMN IF NOT EXISTS sector  VARCHAR(60),
    ADD COLUMN IF NOT EXISTS is_f500 BOOLEAN NOT NULL DEFAULT FALSE;

COMMENT ON COLUMN targets.sector  IS 'Industry vertical: Technology, Healthcare, Defense & Aerospace, Finance, Energy, Consumer, Automotive, Retail, Media & Entertainment, Industrials, Telecom, Other';
COMMENT ON COLUMN targets.is_f500 IS 'TRUE if the company appears on the Fortune 500 list';
