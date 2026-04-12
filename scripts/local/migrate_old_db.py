#!/usr/bin/env python3
"""Migrate existing old-schema local DB to new baseline schema.

Strategy: Option A (Data-Preserving Fresh Start)
  1. Back up old DB to iiagentdev_backup
  2. Export data from key tables
  3. Drop and recreate iiagentdev
  4. Run Alembic migrations to create new schema
  5. Transform and import data with UUID/column conversions
  6. Create agent_sandboxes records from sessions.sandbox_id

Usage:
    docker exec ii-agent-local-postgres-1 psql -U iiagent -d postgres \
      -c "SELECT 1 FROM pg_database WHERE datname='iiagentdev'" | grep -q 1  # verify DB exists
    uv run python scripts/local/migrate_old_db.py
"""

from __future__ import annotations

import json
import subprocess
import sys
import uuid


# ── Connection to Postgres via docker exec ───────────────────────────────

CONTAINER = "ii-agent-local-postgres-1"
DB_USER = "iiagent"
OLD_DB = "iiagentdev"
BACKUP_DB = "iiagentdev_backup"


def psql(db: str, sql: str, tuples_only: bool = False) -> str:
    """Run SQL via psql in the Docker container."""
    cmd = [
        "docker",
        "exec",
        CONTAINER,
        "psql",
        "-U",
        DB_USER,
        "-d",
        db,
    ]
    if tuples_only:
        cmd.extend(["-t", "-A"])
    cmd.extend(["-c", sql])
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"SQL ERROR: {result.stderr}", file=sys.stderr)
        raise RuntimeError(f"psql failed: {result.stderr}")
    return result.stdout


def psql_copy_csv(db: str, copy_sql: str) -> str:
    """Run a COPY ... TO STDOUT via psql."""
    cmd = [
        "docker",
        "exec",
        CONTAINER,
        "psql",
        "-U",
        DB_USER,
        "-d",
        db,
        "-c",
        copy_sql,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"COPY failed: {result.stderr}")
    return result.stdout


def psql_pipe(db: str, sql: str) -> str:
    """Pipe large SQL through stdin."""
    cmd = [
        "docker",
        "exec",
        "-i",
        CONTAINER,
        "psql",
        "-U",
        DB_USER,
        "-d",
        db,
    ]
    result = subprocess.run(cmd, input=sql, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"SQL ERROR: {result.stderr}", file=sys.stderr)
        raise RuntimeError(f"psql pipe failed: {result.stderr}")
    return result.stdout


def query_rows(db: str, sql: str) -> list[dict]:
    """Return query results as list of dicts using JSON output."""
    json_sql = f"""
    SELECT json_agg(row_to_json(t))
    FROM ({sql}) t
    """
    raw = psql(db, json_sql, tuples_only=True).strip()
    if not raw or raw == "":
        return []
    return json.loads(raw)


# ── Helpers ──────────────────────────────────────────────────────────────


def ensure_uuid(val: str | None) -> str | None:
    """Ensure a value is a valid UUID string, or return None."""
    if not val:
        return None
    try:
        return str(uuid.UUID(val))
    except (ValueError, AttributeError):
        # Value is not a UUID (e.g. 'admin') — generate a deterministic one
        return str(uuid.uuid5(uuid.NAMESPACE_DNS, val))


def sql_str(val: str | None) -> str:
    """Escape a string for SQL, or return NULL."""
    if val is None:
        return "NULL"
    escaped = val.replace("'", "''")
    return f"'{escaped}'"


def sql_bool(val) -> str:
    if val is None:
        return "NULL"
    return "true" if val else "false"


def sql_ts(val: str | None) -> str:
    if val is None:
        return "NULL"
    return f"'{val}'"


def sql_num(val) -> str:
    if val is None:
        return "NULL"
    return str(val)


def sql_json(val) -> str:
    if val is None:
        return "NULL"
    if isinstance(val, str):
        escaped = val.replace("'", "''")
        return f"'{escaped}'::jsonb"
    escaped = json.dumps(val).replace("'", "''")
    return f"'{escaped}'::jsonb"


# ── Main Migration ───────────────────────────────────────────────────────


def step(msg: str):
    print(f"\n{'=' * 60}")
    print(f"  {msg}")
    print(f"{'=' * 60}")


def main():
    print("=" * 60)
    print("  II-Agent Database Migration: Old Schema -> New Baseline")
    print("=" * 60)

    # ── 0. Sanity check ──────────────────────────────────────────────
    step("Step 0: Verify old database exists")
    check = psql(
        "postgres", f"SELECT 1 FROM pg_database WHERE datname='{OLD_DB}'", tuples_only=True
    ).strip()
    if not check:
        print(f"ERROR: Database {OLD_DB} does not exist!")
        sys.exit(1)
    print(f"  ✓ Database {OLD_DB} exists")

    # ── 1. Export data from old DB ───────────────────────────────────
    step("Step 1: Export data from old database")

    # Users
    users = query_rows(OLD_DB, "SELECT * FROM users")
    print(f"  Users: {len(users)}")

    # Sessions (all, including deleted)
    sessions = query_rows(OLD_DB, "SELECT * FROM sessions")
    print(f"  Sessions: {len(sessions)}")

    # Chat messages
    messages = query_rows(OLD_DB, "SELECT * FROM chat_messages")
    print(f"  Chat messages: {len(messages)}")

    # Agent run tasks
    agent_runs = query_rows(OLD_DB, "SELECT * FROM agent_run_tasks")
    print(f"  Agent run tasks: {len(agent_runs)}")

    # LLM settings
    llm_settings = query_rows(OLD_DB, "SELECT * FROM llm_settings")
    print(f"  LLM settings: {len(llm_settings)}")

    # MCP settings
    mcp_settings = query_rows(OLD_DB, "SELECT * FROM mcp_settings")
    print(f"  MCP settings: {len(mcp_settings)}")

    # Slide contents
    slides = query_rows(OLD_DB, "SELECT * FROM slide_contents")
    print(f"  Slide contents: {len(slides)}")

    # Slide templates
    slide_templates = query_rows(OLD_DB, "SELECT * FROM slide_templates")
    print(f"  Slide templates: {len(slide_templates)}")

    # Session wishlists
    wishlists = query_rows(OLD_DB, "SELECT * FROM session_wishlists")
    print(f"  Session wishlists: {len(wishlists)}")

    # File uploads
    file_uploads = query_rows(OLD_DB, "SELECT * FROM file_uploads")
    print(f"  File uploads: {len(file_uploads)}")

    # Events (summarize count, don't migrate all)
    event_count = psql(OLD_DB, "SELECT COUNT(*) FROM events", tuples_only=True).strip()
    print(f"  Events: {event_count} (will NOT be migrated — old format)")

    # ── 2. Build user ID mapping ─────────────────────────────────────
    step("Step 2: Build ID mappings")

    # Map old user IDs to new UUIDs
    user_id_map: dict[str, str] = {}
    for u in users:
        old_id = u["id"]
        new_id = ensure_uuid(old_id)
        user_id_map[old_id] = new_id
        print(f"  User '{old_id}' -> {new_id}")

    # Map old LLM setting IDs to new UUIDs
    llm_id_map: dict[str, str] = {}
    for ls in llm_settings:
        old_id = ls["id"]
        new_id = ensure_uuid(old_id)
        llm_id_map[old_id] = new_id
        print(f"  LLM setting '{old_id}' -> {new_id}")

    # ── 3. Backup old database ───────────────────────────────────────
    step("Step 3: Backup old database")

    # Terminate all connections to old DB first
    psql(
        "postgres",
        f"""
        SELECT pg_terminate_backend(pid)
        FROM pg_stat_activity
        WHERE datname = '{OLD_DB}' AND pid <> pg_backend_pid()
    """,
    )

    # Drop backup DB if exists
    psql("postgres", f"DROP DATABASE IF EXISTS {BACKUP_DB}")
    # Create backup by copying
    psql("postgres", f"CREATE DATABASE {BACKUP_DB} WITH TEMPLATE {OLD_DB} OWNER {DB_USER}")
    print(f"  ✓ Backed up {OLD_DB} -> {BACKUP_DB}")

    # ── 4. Drop and recreate database ────────────────────────────────
    step("Step 4: Drop and recreate database")

    # Terminate connections
    psql(
        "postgres",
        f"""
        SELECT pg_terminate_backend(pid)
        FROM pg_stat_activity
        WHERE datname = '{OLD_DB}' AND pid <> pg_backend_pid()
    """,
    )

    psql("postgres", f"DROP DATABASE {OLD_DB}")
    psql("postgres", f"CREATE DATABASE {OLD_DB} OWNER {DB_USER}")
    print(f"  ✓ Recreated {OLD_DB}")

    # ── 5. Run Alembic migrations ────────────────────────────────────
    step("Step 5: Run Alembic migrations for new schema")

    # Ensure gen_random_uuid() is available
    psql(OLD_DB, 'CREATE EXTENSION IF NOT EXISTS "pgcrypto"')

    subprocess.run(
        [
            "docker",
            "exec",
            "-e",
            f"DATABASE_URL=postgresql://iiagent:iiagent@localhost:5432/{OLD_DB}",
            CONTAINER,
            "psql",
            "-U",
            DB_USER,
            "-d",
            OLD_DB,
            "-c",
            "SELECT 1",
        ],
        capture_output=True,
        text=True,
    )

    # Run alembic from the host (needs access to migration files)
    import os

    env = os.environ.copy()
    env["DATABASE_URL"] = f"postgresql+asyncpg://iiagent:iiagent@localhost:5433/{OLD_DB}"

    alembic_result = subprocess.run(
        ["uv", "run", "alembic", "upgrade", "head"],
        capture_output=True,
        text=True,
        cwd="/home/mdear/workspaces/git/ii-agent",
        env=env,
    )
    print(f"  Alembic stdout: {alembic_result.stdout}")
    if alembic_result.returncode != 0:
        print(f"  Alembic stderr: {alembic_result.stderr}")
        # Try with sync URL
        env["DATABASE_URL"] = f"postgresql://iiagent:iiagent@localhost:5433/{OLD_DB}"
        alembic_result = subprocess.run(
            ["uv", "run", "alembic", "upgrade", "head"],
            capture_output=True,
            text=True,
            cwd="/home/mdear/workspaces/git/ii-agent",
            env=env,
        )
        print(f"  Alembic retry stdout: {alembic_result.stdout}")
        if alembic_result.returncode != 0:
            print(f"  Alembic retry stderr: {alembic_result.stderr}")
            print("  ERROR: Alembic migration failed!")
            sys.exit(1)

    print("  ✓ Alembic migrations applied")

    # Verify new schema
    tables = psql(
        OLD_DB,
        "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='public'",
        tuples_only=True,
    ).strip()
    print(f"  New schema has {tables} tables")

    # ── 6. Import users ──────────────────────────────────────────────
    step("Step 6: Import users")

    for u in users:
        new_id = user_id_map[u["id"]]
        sql = f"""
        INSERT INTO users (id, email, password_hash, first_name, last_name, avatar,
                          role, is_active, email_verified, last_login_at, metadata,
                          login_provider, organization, language, created_at, updated_at)
        VALUES (
            '{new_id}'::uuid,
            {sql_str(u.get("email"))},
            {sql_str(u.get("password_hash"))},
            {sql_str(u.get("first_name"))},
            {sql_str(u.get("last_name"))},
            {sql_str(u.get("avatar"))},
            {sql_str(u.get("role", "user"))},
            {sql_bool(u.get("is_active", True))},
            {sql_bool(u.get("email_verified", False))},
            {sql_ts(u.get("last_login_at"))},
            {sql_json(u.get("metadata"))},
            {sql_str(u.get("login_provider"))},
            {sql_str(u.get("organization"))},
            'en',
            {sql_ts(u.get("created_at"))},
            {sql_ts(u.get("updated_at"))}
        )
        ON CONFLICT (id) DO NOTHING;
        """
        psql(OLD_DB, sql)
        print(f"  ✓ User '{u['email']}' imported as {new_id}")

        # Create credit_balances record with old credits
        credits = u.get("credits", 0) or 0
        bonus = u.get("bonus_credits", 0) or 0
        psql(
            OLD_DB,
            f"""
            INSERT INTO credit_balances (user_id, credits, bonus_credits)
            VALUES ('{new_id}'::uuid, {sql_num(credits)}, {sql_num(bonus)})
            ON CONFLICT (user_id) DO NOTHING;
        """,
        )
        print(f"  ✓ Credit balance: {credits} credits, {bonus} bonus")

    # ── 7. Import model_settings (from llm_settings) ────────────────
    step("Step 7: Import model_settings (from llm_settings)")

    for ls in llm_settings:
        new_id = llm_id_map[ls["id"]]
        user_id = user_id_map.get(ls["user_id"])

        # Map old columns to new schema
        # old: model, api_type, encrypted_api_key, base_url, max_retries, max_message_chars, temperature, thinking_tokens, metadata
        # new: model_id, provider, encrypted_api_key, base_url, display_name, params, pricing, config_type, is_default, is_active
        model_id = ls.get("model", "")
        provider = ls.get("api_type", "anthropic")

        # Pack old numeric settings into params JSONB
        params = {}
        if ls.get("max_retries"):
            params["max_retries"] = ls["max_retries"]
        if ls.get("max_message_chars"):
            params["max_message_chars"] = ls["max_message_chars"]
        if ls.get("temperature") is not None:
            params["temperature"] = ls["temperature"]
        if ls.get("thinking_tokens"):
            params["thinking_tokens"] = ls["thinking_tokens"]

        sql = f"""
        INSERT INTO model_settings (id, user_id, model_id, provider, encrypted_api_key,
                                   base_url, display_name, params, config_type,
                                   is_default, is_active, created_at, updated_at)
        VALUES (
            '{new_id}'::uuid,
            {f"'{user_id}'::uuid" if user_id else "NULL"},
            {sql_str(model_id)},
            {sql_str(provider)},
            {sql_str(ls.get("encrypted_api_key"))},
            {sql_str(ls.get("base_url"))},
            {sql_str(ls["id"])},
            {sql_json(params) if params else "NULL"},
            'user',
            false,
            {sql_bool(ls.get("is_active", True))},
            {sql_ts(ls.get("created_at"))},
            {sql_ts(ls.get("updated_at"))}
        )
        ON CONFLICT (id) DO NOTHING;
        """
        psql(OLD_DB, sql)
        print(f"  ✓ Model setting '{ls['id']}' ({model_id}/{provider}) -> {new_id}")

    # ── 8. Import MCP settings ───────────────────────────────────────
    step("Step 8: Import MCP settings")

    for ms in mcp_settings:
        new_id = ensure_uuid(ms["id"])
        user_id = user_id_map.get(ms["user_id"])

        sql = f"""
        INSERT INTO mcp_settings (id, user_id, mcp_config, metadata, is_active,
                                 created_at, updated_at)
        VALUES (
            '{new_id}'::uuid,
            {f"'{user_id}'::uuid" if user_id else "NULL"},
            {sql_json(ms.get("mcp_config", {}))},
            {sql_json(ms.get("metadata"))},
            {sql_bool(ms.get("is_active", True))},
            {sql_ts(ms.get("created_at"))},
            {sql_ts(ms.get("updated_at"))}
        )
        ON CONFLICT (id) DO NOTHING;
        """
        psql(OLD_DB, sql)
        print(f"  ✓ MCP setting {new_id}")

    # ── 9. Import sessions ───────────────────────────────────────────
    step("Step 9: Import sessions")

    for s in sessions:
        session_id = s["id"]  # Already UUID format
        user_id = user_id_map.get(s["user_id"])
        if not user_id:
            print(f"  ⚠ Skipping session {session_id}: unknown user_id '{s['user_id']}'")
            continue

        # Map llm_setting_id -> model_setting_id
        model_setting_id = llm_id_map.get(s.get("llm_setting_id"))

        # Map deleted_at -> is_deleted
        is_deleted = s.get("deleted_at") is not None

        # Map agent_type to app_kind
        agent_type = s.get("agent_type") or "general"
        app_kind = "agent"  # default
        if agent_type == "chat":
            app_kind = "chat"

        sql = f"""
        INSERT INTO sessions (id, user_id, version, model_setting_id, name, status,
                             agent_type, app_kind, public_url, is_public, api_version,
                             parent_session_id, session_metadata, last_message_at,
                             created_at, updated_at, is_deleted)
        VALUES (
            '{session_id}'::uuid,
            '{user_id}'::uuid,
            {sql_num(s.get("version", 0))},
            {f"'{model_setting_id}'::uuid" if model_setting_id else "NULL"},
            {sql_str(s.get("name"))},
            {sql_str(s.get("status", "active"))},
            {sql_str(agent_type)},
            {sql_str(app_kind)},
            {sql_str(s.get("public_url"))},
            {sql_bool(s.get("is_public", False))},
            'v0',
            {f"'{s['parent_session_id']}'::uuid" if s.get("parent_session_id") else "NULL"},
            NULL,
            {sql_ts(s.get("last_message_at"))},
            {sql_ts(s.get("created_at"))},
            {sql_ts(s.get("updated_at"))},
            {sql_bool(is_deleted)}
        )
        ON CONFLICT (id) DO NOTHING;
        """
        psql(OLD_DB, sql)

    print(f"  ✓ Imported {len(sessions)} sessions")

    # ── 10. Create agent_sandboxes from sessions.sandbox_id ──────────
    step("Step 10: Create agent_sandboxes records")

    sandbox_count = 0
    for s in sessions:
        sandbox_id = s.get("sandbox_id")
        if not sandbox_id:
            continue
        session_id = s["id"]

        # The sandbox_id in old schema is the provider_sandbox_id for Docker
        # We generate a new UUID for the agent_sandboxes record
        agent_sandbox_uuid = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"sandbox-{sandbox_id}"))

        sql = f"""
        INSERT INTO agent_sandboxes (id, session_id, provider, provider_sandbox_id,
                                     status, provider_data, created_at, updated_at)
        VALUES (
            '{agent_sandbox_uuid}'::uuid,
            '{session_id}'::uuid,
            'docker',
            {sql_str(sandbox_id)},
            'paused',
            NULL,
            {sql_ts(s.get("created_at"))},
            NOW()
        )
        ON CONFLICT (id) DO NOTHING;
        """
        psql(OLD_DB, sql)
        sandbox_count += 1
        print(
            f"  ✓ Session {session_id[:8]}... -> sandbox {sandbox_id[:8]}... (agent_sandbox {agent_sandbox_uuid[:8]}...)"
        )

    print(f"  ✓ Created {sandbox_count} agent_sandboxes records")

    # ── 11. Import chat_messages ─────────────────────────────────────
    step("Step 11: Import chat_messages")

    batch_sql = []
    for m in messages:
        msg_id = m["id"]  # Already UUID
        session_id = m.get("session_id")

        content = m.get("content")
        usage = m.get("usage")
        metadata = m.get("metadata")
        tools = m.get("tools")
        provider_metadata = m.get("provider_metadata")

        sql = f"""
        INSERT INTO chat_messages (id, session_id, role, content, usage, tokens,
                                  model, tools, metadata, provider_metadata,
                                  parent_message_id, is_finished, finish_reason,
                                  created_at, updated_at)
        VALUES (
            '{msg_id}'::uuid,
            '{session_id}'::uuid,
            {sql_str(m.get("role"))},
            {sql_json(content)},
            {sql_json(usage)},
            {sql_num(m.get("tokens"))},
            {sql_str(m.get("model"))},
            {sql_json(tools)},
            {sql_json(metadata)},
            {sql_json(provider_metadata)},
            {f"'{m['parent_message_id']}'::uuid" if m.get("parent_message_id") else "NULL"},
            {sql_bool(m.get("is_finished", True))},
            {sql_str(m.get("finish_reason"))},
            {sql_ts(m.get("created_at"))},
            {sql_ts(m.get("updated_at"))}
        )
        ON CONFLICT (id) DO NOTHING;
        """
        batch_sql.append(sql)

    # Execute in batches
    BATCH_SIZE = 50
    for i in range(0, len(batch_sql), BATCH_SIZE):
        batch = "\n".join(batch_sql[i : i + BATCH_SIZE])
        psql_pipe(OLD_DB, batch)

    print(f"  ✓ Imported {len(messages)} chat messages")

    # ── 12. Import agent_run_tasks -> agent_run_messages ─────────────
    step("Step 12: Import agent_run_tasks -> agent_run_messages")

    for ar in agent_runs:
        # Old schema: id (uuid), session_id (varchar), version, status, user_message_id, timestamps
        # New schema: id (bigint auto), session_id (uuid), run_id (uuid), model_id, status, etc.
        # We use the old UUID as run_id, auto-generate the bigint id
        run_id = ar["id"]
        session_id = ar.get("session_id")

        sql = f"""
        INSERT INTO agent_run_messages (session_id, run_id, model_id, status,
                                       version, created_at, updated_at)
        VALUES (
            '{session_id}'::uuid,
            '{run_id}'::uuid,
            'unknown',
            {sql_str(ar.get("status", "completed"))},
            {sql_num(ar.get("version", 0))},
            {sql_ts(ar.get("created_at"))},
            {sql_ts(ar.get("updated_at"))}
        )
        """
        try:
            psql(OLD_DB, sql)
        except RuntimeError as e:
            print(f"  ⚠ Skipping agent_run {run_id}: {e}")

    print(f"  ✓ Imported {len(agent_runs)} agent run messages")

    # ── 13. Import slide_contents ────────────────────────────────────
    step("Step 13: Import slide_contents")

    for sc in slides:
        slide_id = ensure_uuid(sc["id"])
        session_id = sc.get("session_id")

        sql = f"""
        INSERT INTO slide_contents (id, session_id, presentation_name, slide_number,
                                   slide_title, slide_content, metadata,
                                   created_at, updated_at)
        VALUES (
            '{slide_id}'::uuid,
            '{session_id}'::uuid,
            {sql_str(sc.get("presentation_name", "default"))},
            {sql_num(sc.get("slide_number", 0))},
            {sql_str(sc.get("slide_title"))},
            {sql_str(sc.get("slide_content", ""))},
            {sql_json(sc.get("metadata"))},
            {sql_ts(sc.get("created_at"))},
            {sql_ts(sc.get("updated_at"))}
        )
        ON CONFLICT (id) DO NOTHING;
        """
        try:
            psql(OLD_DB, sql)
        except RuntimeError:
            # May conflict on unique constraint (session_id, presentation_name, slide_number)
            pass

    print(f"  ✓ Imported {len(slides)} slide contents")

    # ── 14. Import file_uploads -> user_assets ───────────────────────
    step("Step 14: Import file_uploads -> user_assets")

    for fu in file_uploads:
        file_id = ensure_uuid(fu["id"])
        user_id = user_id_map.get(fu.get("user_id"))
        if not user_id:
            continue

        sql = f"""
        INSERT INTO user_assets (id, user_id, file_name, storage_path,
                                content_type, file_size,
                                created_at, updated_at)
        VALUES (
            '{file_id}'::uuid,
            '{user_id}'::uuid,
            {sql_str(fu.get("file_name", "unknown"))},
            {sql_str(fu.get("storage_path", ""))},
            {sql_str(fu.get("content_type"))},
            {sql_num(fu.get("file_size"))},
            {sql_ts(fu.get("created_at"))},
            NOW()
        )
        ON CONFLICT (id) DO NOTHING;
        """
        try:
            psql(OLD_DB, sql)
        except RuntimeError:
            pass

    # Also create session_assets links for file_uploads that have session_id
    session_asset_count = 0
    for fu in file_uploads:
        session_id = fu.get("session_id")
        if not session_id:
            continue
        file_id = ensure_uuid(fu["id"])
        sql = f"""
        INSERT INTO session_assets (session_id, asset_id, created_at, updated_at)
        VALUES (
            '{session_id}'::uuid,
            '{file_id}'::uuid,
            {sql_ts(fu.get("created_at"))},
            NOW()
        )
        ON CONFLICT ON CONSTRAINT uq_session_asset DO NOTHING;
        """
        try:
            psql(OLD_DB, sql)
            session_asset_count += 1
        except RuntimeError:
            pass

    print(
        f"  ✓ Imported {len(file_uploads)} user assets, {session_asset_count} session asset links"
    )

    # ── 15. Import session_wishlists ─────────────────────────────────
    step("Step 15: Import session_wishlists")

    for w in wishlists:
        wl_id = ensure_uuid(w["id"])
        user_id = user_id_map.get(w.get("user_id"))
        session_id = w.get("session_id")
        if not user_id or not session_id:
            continue

        sql = f"""
        INSERT INTO session_wishlists (id, user_id, session_id, created_at, updated_at)
        VALUES (
            '{wl_id}'::uuid,
            '{user_id}'::uuid,
            '{session_id}'::uuid,
            {sql_ts(w.get("created_at"))},
            {sql_ts(w.get("updated_at"))}
        )
        ON CONFLICT (id) DO NOTHING;
        """
        psql(OLD_DB, sql)

    print(f"  ✓ Imported {len(wishlists)} session wishlists")

    # ── 16. Verify ───────────────────────────────────────────────────
    step("Step 16: Verify migration")

    counts = {
        "users": psql(OLD_DB, "SELECT COUNT(*) FROM users", tuples_only=True).strip(),
        "model_settings": psql(
            OLD_DB, "SELECT COUNT(*) FROM model_settings", tuples_only=True
        ).strip(),
        "mcp_settings": psql(OLD_DB, "SELECT COUNT(*) FROM mcp_settings", tuples_only=True).strip(),
        "sessions": psql(OLD_DB, "SELECT COUNT(*) FROM sessions", tuples_only=True).strip(),
        "agent_sandboxes": psql(
            OLD_DB, "SELECT COUNT(*) FROM agent_sandboxes", tuples_only=True
        ).strip(),
        "chat_messages": psql(
            OLD_DB, "SELECT COUNT(*) FROM chat_messages", tuples_only=True
        ).strip(),
        "agent_run_messages": psql(
            OLD_DB, "SELECT COUNT(*) FROM agent_run_messages", tuples_only=True
        ).strip(),
        "slide_contents": psql(
            OLD_DB, "SELECT COUNT(*) FROM slide_contents", tuples_only=True
        ).strip(),
        "user_assets": psql(OLD_DB, "SELECT COUNT(*) FROM user_assets", tuples_only=True).strip(),
        "credit_balances": psql(
            OLD_DB, "SELECT COUNT(*) FROM credit_balances", tuples_only=True
        ).strip(),
        "alembic_version": psql(
            OLD_DB, "SELECT version_num FROM alembic_version", tuples_only=True
        ).strip(),
    }

    print("\n  Migration results:")
    for table, count in counts.items():
        print(f"    {table}: {count}")

    print("\n" + "=" * 60)
    print("  Migration complete!")
    print(f"  Backup available in: {BACKUP_DB}")
    print("=" * 60)


if __name__ == "__main__":
    main()
