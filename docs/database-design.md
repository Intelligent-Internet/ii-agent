# Database Design — II-Agent

> 30 models, 38 tables, PostgreSQL 15+

## Entity-Relationship Overview

```
┌─────────┐
│  users   │──1:N──┬── sessions ──1:N── chat_messages
│          │       │       │                  └── self-ref (parent_message_id)
│          │       │       ├──1:N── run_tasks ──1:N── task_logs
│          │       │       │            └──1:N── agent_run_messages
│          │       │       ├──1:N── agent_sandboxes
│          │       │       ├──1:N── application_events
│          │       │       ├──1:N── slide_contents
│          │       │       ├──1:N── slide_versions (self-ref root/parent)
│          │       │       ├──1:N── storybooks (self-ref root/parent)
│          │       │       │            └──M:N── storybook_pages (via storybook_page_links)
│          │       │       ├──1:N── session_assets ──N:1── user_assets
│          │       │       ├──1:N── chat_summaries (self-ref parent_summary)
│          │       │       ├──1:N── chat_provider_containers
│          │       │       ├──1:N── chat_provider_files
│          │       │       ├──1:N── project_databases
│          │       │       ├──1:N── credit_transactions
│          │       │       ├──0..1── projects ──1:N── project_deployments
│          │       │       │             └──0..1── project_custom_domains
│          │       │       ├──M:N── session_pins (user + session)
│          │       │       └──M:N── session_wishlists (user + session)
│          │       │
│          │       ├── api_keys
│          │       ├── llm_settings ──1:N── sessions
│          │       ├── mcp_settings
│          │       ├── skills
│          │       ├── user_assets
│          │       ├── billing_transactions
│          │       ├── credit_balances (1:1)
│          │       ├── connectors
│          │       ├── composio_profiles
│          │       ├── apple_credentials
│          │       └── projects
│          │
└─────────┘       chat_provider_vector_stores (user-scoped)

Standalone:  waitlist, media_templates, slide_templates
```

---

## Tables by Domain

### 1. Users & Auth

| Table | PK | Key Columns | Notes |
|-------|-----|-------------|-------|
| **users** | UUID | email (unique), role, is_active, stripe_customer_id, subscription_*, language | Central entity. Credits managed via `credit_balances` only |
| **api_keys** | UUID | user_id FK, api_key (unique), is_active | Per-user API keys |
| **waitlist** | email (String) | — | Standalone, no FK |

### 2. Sessions

| Table | PK | Key Columns | Notes |
|-------|-----|-------------|-------|
| **sessions** | UUID | user_id FK, llm_setting_id FK (indexed), status, app_kind, version (optimistic lock), parent_session_id (self-ref), is_deleted (Boolean soft delete) | Core workspace. Sandbox resolved via `agent_sandboxes.session_id`. `updated_at` serves as deletion timestamp. |
| **session_pins** | UUID | user_id FK, session_id FK | Unique(user_id, session_id) |
| **session_wishlists** | UUID | user_id FK, session_id FK | Unique(user_id, session_id) |

### 3. Tasks & Agent Runs

| Table | PK | Key Columns | Notes |
|-------|-----|-------------|-------|
| **run_tasks** | UUID | session_id FK, task_type, entity_id, status, version (optimistic lock) | Canonical run lifecycle |
| **task_logs** | BigInteger (auto) | task_id FK, status, data (JSONB) | Append-only log |
| **agent_run_messages** | BigInteger (auto) | session_id FK, run_id FK, parent_run_id FK(run_tasks, SET NULL), model_id, status, messages (JSONB), version (optimistic lock) | LLM interaction records |
| **agent_sandboxes** | UUID | session_id FK, provider, provider_sandbox_id, status, expired_at | Sandbox lifecycle |

### 4. Chat

| Table | PK | Key Columns | Notes |
|-------|-----|-------------|-------|
| **chat_messages** | UUID | session_id FK, role, content (JSONB), parent_message_id (self-ref), is_finished, finish_reason | Message tree |
| **chat_summaries** | UUID | session_id FK, summary_text, end_message_id, compression_ratio, parent_summary_id (self-ref) | Context compression |
| **chat_provider_containers** | UUID | session_id FK, provider, container_id | Unique(container_id, provider) |
| **chat_provider_files** | UUID | file_id FK(user_assets), session_id FK, provider, provider_file_id | Unique(provider_file_id, provider) |
| **chat_provider_vector_stores** | UUID | user_id FK, provider, vector_store_id, version (optimistic lock) | Unique(user_id, provider, vector_store_id) |

### 5. Files

| Table | PK | Key Columns | Notes |
|-------|-----|-------------|-------|
| **user_assets** | UUID | user_id FK, file_name, storage_path (unique), content_type, file_size, asset_type, upload_status, is_public | File storage records |
| **session_assets** | UUID | session_id FK, asset_id FK(user_assets) | Unique(session_id, asset_id) — M:N link |

### 6. Billing & Credits

| Table | PK | Key Columns | Notes |
|-------|-----|-------------|-------|
| **billing_transactions** | UUID | user_id FK, stripe_event_id (unique), amount (Numeric 18,6), credits, status, raw_payload | Stripe event log |
| **credit_balances** | UUID | user_id FK (unique — 1:1), credits (Numeric 18,6), bonus_credits, version (optimistic lock), billing_status | Current balance |
| **credit_transactions** | UUID | user_id FK, transaction_type, credit_type, amount, balance_after, session_id FK, run_id, model_id, billing_transaction_id FK | Ledger |

### 7. Projects & Deployments

| Table | PK | Key Columns | Notes |
|-------|-----|-------------|-------|
| **projects** | UUID | user_id FK, session_id FK (unique), status, current_build_status, production_url, deleted_at | No circular FKs — custom domain and deployment resolved via child table queries |
| **project_deployments** | UUID | project_id FK, environment, deployment_status, provider, version, error_phase, error_details, various duration_ms | Deploy history |
| **project_custom_domains** | UUID | project_id FK (unique), subdomain (unique), full_domain, dns_status, ssl_status, deployment_id FK | DNS/SSL tracking |
| **project_databases** | UUID | session_id FK, source, connection_string, is_active | Provisioned DBs |

### 8. Content

| Table | PK | Key Columns | Notes |
|-------|-----|-------------|-------|
| **slide_contents** | UUID | session_id FK, presentation_name, slide_number | Unique(session, name, number) |
| **slide_versions** | UUID | session_id FK, presentation_name, slide_number, version, root_version_id (self-ref), parent_version_id (self-ref), image_url | Version tree |
| **slide_templates** | UUID | slide_template_name, slide_content, slide_template_images (ARRAY) | Standalone |
| **media_templates** | UUID | name, preview, type, prompt | Standalone |
| **storybooks** | UUID | session_id FK, name, version, root_storybook_id (self-ref), parent_storybook_id (self-ref), style_json, aspect_ratio | Version tree |
| **storybook_pages** | UUID | page_number, image_url, html_content, text_content, audio_link | Standalone pages |
| **storybook_page_links** | Composite(storybook_id, page_id) | created_at | M:N association, no UUID id |

### 9. Settings

| Table | PK | Key Columns | Notes |
|-------|-----|-------------|-------|
| **llm_settings** | UUID | user_id FK (nullable), model_id, provider, encrypted_api_key, base_url, display_name, configs (JSONB), pricing (JSONB), config_type, is_default, is_active | Partial unique indexes for user vs system rows |
| **mcp_settings** | UUID | user_id FK, mcp_config (JSONB), is_active | MCP server config |
| **skills** | UUID | user_id FK (nullable — NULL = builtin), name, source, skill_md_content, is_enabled | Unique(user_id, name) + partial unique on builtin |

### 10. Integrations

| Table | PK | Key Columns | Notes |
|-------|-----|-------------|-------|
| **connectors** | UUID | user_id FK, connector_type, access_token, refresh_token | Unique(user_id, connector_type) |
| **composio_profiles** | UUID | user_id FK, profile_name, toolkit_slug, encrypted_mcp_url, status, enabled_tools (JSONB) | Unique(user_id, profile_name) |
| **apple_credentials** | UUID | user_id FK, apple_id, auth_state, encrypted_* fields | Unique(user_id, apple_id) |

### 11. Events

| Table | PK | Key Columns | Notes |
|-------|-----|-------------|-------|
| **application_events** | UUID | event_type, event_group, session_id, run_id, user_id, content (JSONB) | No FKs (intentional — event log shouldn't block parent deletion) |

---

## Design Patterns

### Primary Keys
- All tables use `UUID` PK with `gen_random_uuid()` server default
- Exceptions: `task_logs` and `agent_run_messages` use `BigInteger` autoincrement, `waitlist` uses `email` as PK, `storybook_page_links` uses composite PK

### Timestamps
- All tables have `created_at` and `updated_at` with `DateTime(timezone=True)`
- Soft delete: `is_deleted` (Boolean) on `sessions`; `deleted_at` (DateTime) on `projects`
- Expiry: `expired_at` on `agent_sandboxes`; `expires_at` on chat_provider_containers/files/vector_stores

### Optimistic Locking
5 tables use `version` column for ORM-level optimistic concurrency:
- `sessions` (BigInteger, default 0)
- `run_tasks` (BigInteger, default 0)
- `agent_run_messages` (BigInteger, default 0)
- `credit_balances` (BigInteger, default 1)
- `chat_provider_vector_stores` (BigInteger, default 0)

### JSONB Usage
Heavy JSONB usage for flexible/nested data:
- `llm_settings.configs` — provider-specific settings (temperature, thinking_tokens, max_retries, vertex_region, azure_endpoint, etc.)
- `llm_settings.pricing` — PricingInfo data (input/output/cache prices per million tokens)
- Message content, tools, metrics, metadata across chat/agent tables
- Provider configs (mcp_config, composio enabled_tools)
- Deployment metadata, error details
- Style/template data for content domain

### Numeric Precision
Financial columns use `Numeric(18, 6)` for exact decimal arithmetic:
- `billing_transactions.amount`, `billing_transactions.credits`
- `credit_balances.credits`, `credit_balances.bonus_credits`
- `credit_transactions.amount`, `credit_transactions.balance_after`

### FK & Cascade Strategy

**Design principle:** FK constraints on reference/config tables for correctness; previously, no FKs on high-volume operational tables to avoid cascade lock storms (B-tree indexes provided join performance). As of PR-C (migration `20260428_000010_session_fk_constraints.py`), the operational tables now also carry FKs added with `NOT VALID` + `VALIDATE CONSTRAINT` so the cascade lock-storm risk is contained to a brief `ShareRowExclusiveLock` per ALTER. Cascade choice is dictated by `docs/design-docs/session-lifecycle-and-data-custody.md` §3.1: **CASCADE** when the row is operationally meaningless without its parent (chat history, sandbox state); **SET NULL** when audit/billing retention requires the row to outlive the parent (`credit_transactions`, `application_events`).

**Tables WITH FK constraints** (low-volume, correctness matters):
- `api_keys` → users (CASCADE)
- `llm_settings` → users (CASCADE)
- `mcp_settings` → users (CASCADE)
- `skills` → users (CASCADE)
- `sessions` → users (CASCADE), llm_settings (no action), sessions self-ref (no action)
- `session_pins` → users (CASCADE), sessions (CASCADE)
- `session_wishlists` → users (CASCADE), sessions (CASCADE)
- `user_assets` → users (CASCADE)
- `session_assets` → sessions (CASCADE), user_assets (CASCADE)
- `billing_transactions` → users (CASCADE)
- `credit_balances` → users (CASCADE)
- `projects` → users (CASCADE), sessions (SET NULL)
- `project_deployments` → projects (CASCADE), users (SET NULL)
- `project_custom_domains` → projects (CASCADE), deployments (SET NULL), users (SET NULL)
- `project_databases` → sessions (CASCADE)
- `slide_contents` → sessions (CASCADE)
- `slide_versions` → sessions (CASCADE), self-ref (SET NULL)
- `storybooks` → sessions (CASCADE), self-ref (SET NULL)
- `storybook_page_links` → storybooks (CASCADE), storybook_pages (CASCADE)
- `connectors`, `composio_profiles`, `apple_credentials` → users (CASCADE)
- `chat_provider_vector_stores` → users (CASCADE)

**Tables WITH FK constraints added by PR-C** (operational, NOT VALID + VALIDATE):
- `run_tasks` → sessions (CASCADE) [`fk_run_tasks_session_id`]
- `task_logs` → run_tasks (CASCADE) [`fk_task_logs_task_id`] — closes the §1 doc-quoted "62 orphans"
- `agent_run_messages` → sessions (CASCADE) [`fk_agent_run_messages_session_id`]
- `agent_sandboxes` → sessions (CASCADE) [`fk_agent_sandboxes_session_id`]
- `chat_messages` → sessions (CASCADE) [`fk_chat_messages_session_id`]
- `chat_summaries` → sessions (CASCADE) [`fk_chat_summaries_session_id`]
- `chat_provider_containers` → sessions (CASCADE) [`fk_chat_provider_containers_session_id`]
- `chat_provider_files` → sessions (CASCADE) [`fk_chat_provider_files_session_id`]
- `credit_transactions` → sessions (SET NULL) [`fk_credit_transactions_session_id`], users (SET NULL, **was NOT NULL**) [`fk_credit_transactions_user_id`]
- `application_events` → sessions (SET NULL) [`fk_application_events_session_id`], users (SET NULL) [`fk_application_events_user_id`]

**Tables intentionally WITHOUT FK constraints** (no clean parent or future migration):
- `agent_event_logs` — `session_id` is `String` (legacy schema mismatch); table currently unused
- `session_summaries` — `session_id` is `String` (legacy schema mismatch)

### Partial Indexes
- `application_events`: partial index on `run_id` WHERE `run_id IS NOT NULL`
- `run_tasks`: active-only unique constraint `WHERE status IN ('running', 'waiting_for_input')`
- `credit_transactions`: session index `WHERE session_id IS NOT NULL`, billing_transaction_id index `WHERE billing_transaction_id IS NOT NULL`
- `project_deployments`: deployed_by_user_id index `WHERE deployed_by_user_id IS NOT NULL`
- `project_custom_domains`: deployment_id index `WHERE deployment_id IS NOT NULL`
- `skills`: builtin name uniqueness `WHERE user_id IS NULL`
- `llm_settings`: separate unique indexes for user rows (`WHERE user_id IS NOT NULL`) and system rows (`WHERE user_id IS NULL`)

### BRIN Indexes
- `application_events.created_at` — BRIN index for efficient time-range scans on this append-only table

---

## LLM Settings Schema Detail

The `llm_settings` table uses a dual-mode design:

| Column | Type | Purpose |
|--------|------|---------|
| `user_id` | UUID (nullable) | NULL = system config, UUID = user-specific |
| `model_id` | String | Model identifier (e.g. "claude-sonnet-4-6") |
| `provider` | String | Provider name (e.g. "Anthropic", "OpenAI") |
| `encrypted_api_key` | String | Encrypted API key |
| `base_url` | String | Custom API endpoint URL |
| `display_name` | String | Human-readable label for UI |
| `configs` | JSONB | Provider settings: temperature, thinking_tokens, max_retries, max_message_chars, vertex_region, azure_endpoint |
| `pricing` | JSONB | PricingInfo: input_price, output_price, cache_price per million tokens |
| `config_type` | String | "user" or "system" discriminator |
| `is_default` | Boolean | Default model for user/system |
| `is_active` | Boolean | Soft-disable without deletion |

**Uniqueness enforcement:**
- Per-user: `UNIQUE(model_id, provider, user_id) WHERE user_id IS NOT NULL`
- System-wide: `UNIQUE(model_id, provider) WHERE user_id IS NULL`

---

## Review Items

### 1. `connectors.access_token` Stored as Plain `String`
OAuth tokens are sensitive. Verify these are encrypted at the application layer. Compare with `apple_credentials` which uses `encrypted_*` column names explicitly.

### 2. `chat_messages.file_ids` Uses `ARRAY(UUID)`
PostgreSQL arrays are difficult to index and query efficiently. If you need to find "all messages referencing file X", a junction table would be more performant. Current approach is acceptable if file_ids are only read, never queried.

### 3. High-Volume Tables Have No FK Constraints
Tables like `chat_messages`, `agent_run_messages`, `run_tasks`, `task_logs`, `agent_sandboxes`, `chat_summaries`, `chat_provider_*`, `credit_transactions`, and `application_events` intentionally omit FK constraints. This avoids cascade lock storms when deleting parent rows (e.g., a user with millions of messages). All lookup columns are still indexed. Orphaned rows from these tables should be cleaned up via periodic background jobs.

---

## Index Summary

| Table | Index Count | Notable |
|-------|------------|---------|
| users | 1 | email |
| sessions | 5 | user_id, status, created_at, llm_setting_id, parent_session_id |
| session_pins | 2 (1 unique) | user+session unique, session_id |
| session_wishlists | 2 (1 unique) | user+session unique, session_id |
| run_tasks | 8 (incl 2 unique) | Heaviest indexed table |
| agent_run_messages | 6 | session+run composite |
| chat_messages | 4 | session+created composite |
| application_events | 6 (1 partial, 1 BRIN) | run_id partial, created_at BRIN |
| credit_transactions | 4 (2 partial) | user+time, session+time, billing_tx |
| project_deployments | 5 (1 partial) | project+version, deployed_by |
| project_custom_domains | 3 (1 partial) | project, subdomain, deployment_id |
| skills | 5 (1 partial unique) | builtin name uniqueness |
| llm_settings | 3 (2 partial unique) | user_id, user vs system rows |
| mcp_settings | 1 | user_id |
| slide_versions | 4 | session, session+slide, root, parent |
| chat_provider_containers | 4 + 1 unique | session+provider composite |
| chat_provider_vector_stores | 4 + 1 unique | user+provider+store composite |

---

## Table Count by Domain

| Domain | Tables |
|--------|--------|
| Users & Auth | 3 |
| Sessions | 3 |
| Tasks & Runs | 4 |
| Chat | 5 |
| Files | 2 |
| Billing & Credits | 3 |
| Projects | 4 |
| Content | 7 |
| Settings | 3 |
| Integrations | 3 |
| Events | 1 |
| **Total** | **38** |
