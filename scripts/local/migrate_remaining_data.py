#!/usr/bin/env python3
"""Migrate remaining unmigrated data from iiagentdev_backup to iiagentdev.

Handles four gaps identified in the comprehensive DB audit:
  1. agent_run_tasks (270 rows) → run_tasks (task_type='agent_run')
  2. provider_files (2 rows)    → chat_provider_files
  3. provider_vector_stores (1)  → chat_provider_vector_stores
  4. session_metrics (28 rows)  → (no direct equivalent; stored as JSON in session metadata)

Usage:
  docker exec ii-agent-local-postgres-1 psql -U iiagent -d iiagentdev -f /dev/stdin < scripts/local/migrate_remaining_data.sql
  -- OR run this script which generates & executes the SQL:
  python scripts/local/migrate_remaining_data.py
"""

import subprocess
import sys

# =============================================================================
# The dev@localhost user_id that owns all migrated data
# =============================================================================
DEV_USER_ID = "eac4f4fd-0aa6-4f98-b6fb-91156deb670b"

# Status mapping: old agent_run_tasks status → new RunStatus enum values
# Old: completed, failed, aborted, system_interrupted
# New: pending, running, completed, failed, cancelled, paused, aborting
STATUS_MAP = {
    "completed": "completed",
    "failed": "failed",
    "aborted": "cancelled",  # "aborted" maps to "cancelled" in new system
    "system_interrupted": "cancelled",  # "system_interrupted" maps to "cancelled"
}

SQL = f"""
-- =============================================================================
-- 1. Migrate agent_run_tasks → run_tasks
--    Maps old agent_run_tasks to new run_tasks with task_type='agent_run'
-- =============================================================================
BEGIN;

-- Use a temporary table to avoid conflicts
INSERT INTO run_tasks (id, session_id, task_type, status, version, created_at, updated_at)
SELECT
    art.id,
    art.session_id::uuid,
    'agent_run' AS task_type,
    CASE art.status
        WHEN 'completed' THEN 'completed'
        WHEN 'failed' THEN 'failed'
        WHEN 'aborted' THEN 'cancelled'
        WHEN 'system_interrupted' THEN 'cancelled'
        ELSE 'failed'
    END AS status,
    art.version,
    COALESCE(art.created_at, now()),
    COALESCE(art.updated_at, now())
FROM dblink(
    'dbname=iiagentdev_backup user=iiagent',
    'SELECT id, session_id, version, status, created_at, updated_at FROM agent_run_tasks'
) AS art(id uuid, session_id varchar, version bigint, status varchar, created_at timestamptz, updated_at timestamptz)
ON CONFLICT (id) DO NOTHING;

-- Report
DO $$
DECLARE cnt INTEGER;
BEGIN
    SELECT count(*) INTO cnt FROM run_tasks;
    RAISE NOTICE 'run_tasks now has % rows', cnt;
END $$;

COMMIT;

-- =============================================================================
-- 2. Migrate provider_files → chat_provider_files
-- =============================================================================
BEGIN;

INSERT INTO chat_provider_files (id, file_id, session_id, provider, provider_file_id, raw_file_object, created_at, updated_at, expires_at)
SELECT
    pf.id,
    pf.file_id,
    pf.session_id,
    pf.provider,
    pf.provider_file_id,
    pf.raw_file_object,
    COALESCE(pf.created_at, now()),
    COALESCE(pf.updated_at, now()),
    pf.expires_at
FROM dblink(
    'dbname=iiagentdev_backup user=iiagent',
    'SELECT id, file_id, session_id, provider, provider_file_id, raw_file_object::text, created_at, updated_at, expires_at FROM provider_files'
) AS pf(id uuid, file_id uuid, session_id uuid, provider varchar, provider_file_id varchar, raw_file_object jsonb, created_at timestamptz, updated_at timestamptz, expires_at timestamptz)
ON CONFLICT (id) DO NOTHING;

DO $$
DECLARE cnt INTEGER;
BEGIN
    SELECT count(*) INTO cnt FROM chat_provider_files;
    RAISE NOTICE 'chat_provider_files now has % rows', cnt;
END $$;

COMMIT;

-- =============================================================================
-- 3. Migrate provider_vector_stores → chat_provider_vector_stores
--    Note: user_id was 'admin' (string) in old system → map to dev user UUID
-- =============================================================================
BEGIN;

INSERT INTO chat_provider_vector_stores (id, user_id, provider, vector_store_id, version, raw_vector_object, created_at, updated_at, expires_at)
SELECT
    pvs.id,
    '{DEV_USER_ID}'::uuid AS user_id,
    pvs.provider,
    pvs.vector_store_id,
    pvs.version,
    pvs.raw_vector_object,
    COALESCE(pvs.created_at, now()),
    COALESCE(pvs.updated_at, now()),
    pvs.expires_at
FROM dblink(
    'dbname=iiagentdev_backup user=iiagent',
    'SELECT id, provider, vector_store_id, version, raw_vector_object::text, created_at, updated_at, expires_at FROM provider_vector_stores'
) AS pvs(id uuid, provider varchar, vector_store_id varchar, version bigint, raw_vector_object jsonb, created_at timestamptz, updated_at timestamptz, expires_at timestamptz)
ON CONFLICT (id) DO NOTHING;

DO $$
DECLARE cnt INTEGER;
BEGIN
    SELECT count(*) INTO cnt FROM chat_provider_vector_stores;
    RAISE NOTICE 'chat_provider_vector_stores now has % rows', cnt;
END $$;

COMMIT;

-- =============================================================================
-- 4. Session metrics → update sessions.data JSONB (archive credit usage)
--    No direct table mapping; store as metadata on the session record.
--    Skip if sessions table doesn't have a data/metadata column.
-- =============================================================================
-- session_metrics contains per-session credit totals (28 rows).
-- The new billing system uses credit_transactions. These are historical
-- summaries only. We'll log them but not migrate to a table.

DO $$
DECLARE
    r RECORD;
BEGIN
    RAISE NOTICE '--- Session Metrics (historical, for reference) ---';
    FOR r IN
        SELECT *
        FROM dblink(
            'dbname=iiagentdev_backup user=iiagent',
            'SELECT session_id, credits, created_at, updated_at FROM session_metrics ORDER BY updated_at'
        ) AS sm(session_id uuid, credits float, created_at timestamptz, updated_at timestamptz)
    LOOP
        RAISE NOTICE 'Session % : credits = % (% to %)', r.session_id, r.credits, r.created_at, r.updated_at;
    END LOOP;
    RAISE NOTICE '--- End session metrics ---';
END $$;
"""


def main() -> None:
    # First ensure dblink extension is available
    setup_sql = "CREATE EXTENSION IF NOT EXISTS dblink;"
    result = subprocess.run(
        [
            "docker",
            "exec",
            "-i",
            "ii-agent-local-postgres-1",
            "psql",
            "-U",
            "iiagent",
            "-d",
            "iiagentdev",
            "-c",
            setup_sql,
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"Failed to create dblink extension: {result.stderr}", file=sys.stderr)
        sys.exit(1)

    # Execute the migration
    result = subprocess.run(
        [
            "docker",
            "exec",
            "-i",
            "ii-agent-local-postgres-1",
            "psql",
            "-U",
            "iiagent",
            "-d",
            "iiagentdev",
        ],
        input=SQL,
        capture_output=True,
        text=True,
    )

    print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
