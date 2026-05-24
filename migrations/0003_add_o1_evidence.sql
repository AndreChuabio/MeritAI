-- 0003_add_o1_evidence.sql
--
-- Add o1_evidence table backing the USCIS O-1A evidence ledger on the
-- Track page. Each row is one piece of evidence the user has declared
-- for a specific criterion. ReplacingMergeTree on updated_at lets us
-- "update" via insert (latest version wins) and "delete" via tombstone
-- (deleted = 1). The audit explicitly flagged ALTER UPDATE / DELETE as
-- a smell on ClickHouse Cloud, so we never use them here.
--
-- Idempotent: IF NOT EXISTS guards the table so re-running is a no-op.
--
-- Reads must use FINAL or argMax(updated_at) to dedupe across versions,
-- and must filter deleted = 0 to ignore tombstoned rows.
--
-- ORDER BY (user_id, criterion, id) co-locates one user's evidence on
-- disk and keeps list_evidence + count_satisfied_criteria cheap.
--
-- Rollback: DROP TABLE IF EXISTS o1_evidence;
--           (only run after reverting application code that writes /
--           reads this table, otherwise the Track page will 500.)

CREATE TABLE IF NOT EXISTS o1_evidence (
    id String,
    user_id String,
    criterion String,
    title String,
    description String,
    evidence_url String DEFAULT '',
    evidence_date Date DEFAULT toDate('1970-01-01'),
    declared_at DateTime DEFAULT now(),
    status String DEFAULT 'draft',
    metadata String DEFAULT '{}',
    deleted UInt8 DEFAULT 0,
    updated_at DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(updated_at)
ORDER BY (user_id, criterion, id);
