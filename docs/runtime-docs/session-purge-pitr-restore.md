# Session-purge: point-in-time recovery (PITR) restore runbook

> **Pre-flip checklist gate #8** in
> [`docs/design-docs/session-lifecycle-and-data-custody.md`](../design-docs/session-lifecycle-and-data-custody.md).
>
> This runbook is the executable equivalent of design-doc §14.1
> *"Disaster-recovery posture"*. It describes the procedure an on-call
> operator follows to restore a single soft-or-hard-deleted session from
> PostgreSQL PITR into a non-prod (staging) environment so the user can
> have their data examined or recovered.
>
> **Scope:** one session at a time. Recovering an entire user account
> from PITR is out of scope for this runbook (and explicitly an Art. 17
> red flag — see §15 of the design doc).

## 0. When to run this runbook

| Situation | Run this runbook? |
|---|---|
| User soft-deleted a session and wants it back **within the grace window** | **No** — use `POST /v1/sessions/{id}/restore` (§4.3); PITR is only for hard-deleted rows. |
| User soft-deleted a session and the grace window has expired (purge committed) | **Yes** — only PITR can recover. |
| User invoked `purge_now` (Art. 17) | **Yes**, *but* — see §15 of the design doc. The user must withdraw the Art. 17 request **and** legal must approve before this runbook runs. |
| Session was lost due to operator error (bad migration, wrong DELETE) | **Yes**. |
| Session was caught by `purge_dead_letter` (provider DELETEs failed) but the row still exists | **No** — the `sessions` row is intact; investigate `purge_dead_letter`, do **not** PITR. |

## 1. Pre-flight (≤ 5 min)

### 1.1 Identify the target session and timestamp

The operator MUST know:

* `session_id` (UUID).
* The wall-clock instant *just before* the deletion (the PITR target). The
  best evidence is the corresponding row in `application_events`. The
  audit row survives because `application_events.session_id` is
  `ON DELETE SET NULL` (§3.1), so the row is still there but with a
  `NULL` `session_id`. Locate it by content:

  ```sql
  SELECT created_at, event_type, content
    FROM application_events
   WHERE event_type IN (
            'session.purge_committed',
            'session.purged_by_user',
            'session.purged_by_grace'
         )
     AND content ->> 'session_id' = :sid
   ORDER BY created_at DESC
   LIMIT 5;
  ```

  Use the `created_at` of the most recent matching row. The PITR target
  is **5 seconds before** that timestamp (gives a wide enough margin to
  capture the row's last-good state without re-introducing the delete).

### 1.2 Verify backup retention covers the target

The design-doc retention requirement is **≥ 37 days** (gate #10). If the
target instant is older than that, abort — the backup may not cover it.

```bash
# Cloud SQL example — list available recovery times
gcloud sql instances describe ${PROD_INSTANCE} \
  --format='value(serverCaCert.expirationTime, settings.backupConfiguration)'
gcloud sql backups list --instance=${PROD_INSTANCE} --limit=10
```

### 1.3 Verify staging is empty (or scoped)

The restored database lands in **staging**, never in prod. If staging is
in use for unrelated work, coordinate with the team in `#staging` before
proceeding — restoring will overwrite the staging DB.

## 2. Restore procedure

### 2.1 Initiate the PITR clone

> Replace `${PROD_INSTANCE}`, `${STAGING_INSTANCE}`, and `${TARGET_TS}`
> with the values from §1. The clone is non-destructive on prod.

```bash
# Cloud SQL — clones prod to a NEW instance at a point in time
gcloud sql instances clone ${PROD_INSTANCE} ${STAGING_INSTANCE}-pitr-$(date +%Y%m%d) \
  --point-in-time="${TARGET_TS}"
```

```sql
-- AWS RDS equivalent: aws rds restore-db-instance-to-point-in-time
-- self-hosted equivalent: pg_basebackup + recovery.conf (recovery_target_time)
```

Wait for the clone instance to become `RUNNABLE`. Typical SLO: 10–30 min.

### 2.2 Verify the row exists in the clone

```sql
\c clone_db
SELECT id, user_id, is_deleted, purge_after, purge_started_at, custody, legal_hold
  FROM sessions
 WHERE id = :sid;
-- Expected: 1 row, is_deleted=true (if grace-purged) or false (if hard-deleted
-- mid-flight). The row MUST exist; if missing, the PITR target is too late.
```

If the row is missing, increase the rewind: subtract another 30 seconds
from `${TARGET_TS}` and re-clone.

### 2.3 Extract the row + dependents into a SQL dump

```bash
# Operate on the CLONE, never on prod.
pg_dump --host="${CLONE_HOST}" --username=postgres --dbname=ii_agent \
  --table=sessions --table=chat_messages --table=chat_summaries \
  --table=agent_run_messages --table=run_tasks --table=task_logs \
  --table=agent_sandboxes --table=session_assets \
  --table=chat_provider_containers --table=chat_provider_files \
  --where="session_id = '${SID}'::uuid" \
  --data-only --column-inserts \
  > /tmp/session-${SID}-pitr.sql
```

Hand-filter the dump if other sessions leaked in (the `--where` clause
applies per-table; `sessions` itself is filtered by `id`, so add a
secondary filter on the `sessions.sql` line):

```bash
sed -i '/INSERT INTO public\.sessions/!b; /'${SID}'/!d' /tmp/session-${SID}-pitr.sql
```

### 2.4 Apply to staging (idempotent)

```bash
# Wipe any pre-existing residue of this session_id in staging FIRST so
# the restore is idempotent on retry.
psql --host=staging-db --username=ii_agent --dbname=ii_agent <<'SQL'
BEGIN;
DELETE FROM session_assets WHERE session_id = :'sid';
DELETE FROM chat_provider_files WHERE session_id = :'sid';
DELETE FROM chat_provider_containers WHERE session_id = :'sid';
DELETE FROM agent_sandboxes WHERE session_id = :'sid';
DELETE FROM task_logs WHERE task_id IN (SELECT id FROM run_tasks WHERE session_id = :'sid');
DELETE FROM run_tasks WHERE session_id = :'sid';
DELETE FROM agent_run_messages WHERE session_id = :'sid';
DELETE FROM chat_summaries WHERE session_id = :'sid';
DELETE FROM chat_messages WHERE session_id = :'sid';
DELETE FROM sessions WHERE id = :'sid';
COMMIT;
SQL

# Now apply the dump.
psql --host=staging-db --username=ii_agent --dbname=ii_agent \
     -f /tmp/session-${SID}-pitr.sql
```

### 2.5 Reset purge state on the restored row

The restored row may carry stale `purge_after` / `purge_started_at` /
`purge_attempts` from prod. Clear them so the staging cleanup loop does
not immediately re-purge the row:

```sql
UPDATE sessions
   SET is_deleted = false,
       purge_after = NULL,
       purge_started_at = NULL,
       purge_attempts = 0
 WHERE id = :sid;
```

### 2.6 Audit trail

Record the restore in `application_events` so the action is queryable:

```sql
INSERT INTO application_events (event_type, session_id, user_id, content)
VALUES (
  'session.restored_from_pitr',
  :sid,
  (SELECT user_id FROM sessions WHERE id = :sid),
  jsonb_build_object(
    'pitr_target_ts', :target_ts,
    'restored_by',    :operator_email,
    'reason',         :ticket_url,
    'runbook',        'docs/runtime-docs/session-purge-pitr-restore.md'
  )
);
```

### 2.7 Hand-off to the user

1. Confirm the user can list the session in staging via the normal UI.
2. If the user wants the data **back in prod**, escalate — putting
   PITR-restored rows back into prod is an explicit cross-environment
   data move and is out of scope for this runbook (talk to the data team
   and legal first).

## 3. Post-checks

After the restore, confirm:

- [ ] `sessions` row exists in staging with `is_deleted=false`.
- [ ] `chat_messages.session_id = :sid` count > 0 (the user actually has
      messages — sanity check the dump landed).
- [ ] `application_events` contains a `session.restored_from_pitr` row
      from §2.6.
- [ ] No new rows in `purge_dead_letter` for the session (these would
      indicate a partial restore + re-purge).

## 4. Tear-down

* Drop the PITR clone instance once §2.4 is committed AND the user has
  confirmed access to the restored session — clones cost money:

  ```bash
  gcloud sql instances delete ${STAGING_INSTANCE}-pitr-$(date +%Y%m%d)
  ```

* Remove `/tmp/session-${SID}-pitr.sql` from any operator hosts.

* Update the operator-action ticket with:
  - clone instance name + creation time,
  - PITR target timestamp,
  - row count restored per table,
  - drop time.

## 5. Rehearsal expectations (for gate #8 sign-off)

To flip pre-flip checklist gate #8 from ❌ to ✅, an operator must have
**rehearsed this runbook end-to-end** against staging at least once,
covering:

1. Soft-delete a non-billable test session in a stage cluster.
2. Allow grace-purge to commit (or run `purge_now`).
3. Verify the `sessions` row is gone.
4. Run §2.1–§2.7 of this runbook to bring it back from PITR.
5. Sign off in `#staging-changes` with the rehearsal evidence (timing,
   row counts, any deviations from this runbook).
6. Capture deltas to this runbook in a follow-up edit so the runbook
   stays self-correcting.

Once that rehearsal is complete, update the gate row in the design-doc
status table from ❌ to ✅ with a link to the rehearsal record.

## 6. Known limitations

* **Provider artefacts are NOT restored.** OpenAI containers / files,
  GCS slide assets, sandbox VMs that were torn down by phase (b) cannot
  be brought back from PITR — they live outside the database. The
  restored session may show stale `chat_provider_*` rows whose upstream
  IDs are 404; the application is expected to re-create those on next
  use (§14.2 idempotency contract).
* **`run_tasks` already-completed status is preserved**, but any sandbox
  state (`agent_sandboxes.status`) is restored AS-OF the PITR target —
  the sandbox itself is gone. The application must re-provision a
  sandbox if the user resumes the session.
* **Cross-session FKs that were SET NULL during purge cannot be
  rehydrated.** Audit rows with `session_id = NULL` stay NULL — there
  is no record of which session they belonged to once the original
  purge committed (this is intentional; see §3.1 v3.7).
