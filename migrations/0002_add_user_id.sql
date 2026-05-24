-- 0002_add_user_id.sql
--
-- Add user_id column to trace_log and session_artifacts for multi-tenancy.
-- ORDER BY is left untouched (online ALTER of the sorting key would require
-- a backfill + table swap which is not safe in production).
--
-- Idempotent: IF NOT EXISTS guards both columns so re-running on a partially
-- migrated cluster is a no-op.
--
-- Existing rows backfill to '' (DEFAULT ''). They will not match any real
-- user filter in fetch_artifacts / fetch_traces and thus become invisible
-- to user-scoped reads, which is the intended privacy behavior.
--
-- Rollback: ALTER TABLE trace_log DROP COLUMN IF EXISTS user_id;
--           ALTER TABLE session_artifacts DROP COLUMN IF EXISTS user_id;
--           (only run if you also revert the application code that writes
--           the column, otherwise inserts will start failing.)

ALTER TABLE trace_log
    ADD COLUMN IF NOT EXISTS user_id String DEFAULT '';

ALTER TABLE session_artifacts
    ADD COLUMN IF NOT EXISTS user_id String DEFAULT '';
