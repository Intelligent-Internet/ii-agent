# Productivity Layer Implementation Plan

## For: ii-agent (fork of robertodbabaran/ii-agent)
## Date: 2026-02-06
## Branch: claude/evaluate-agent-capabilities-Ut8a8

---

## Executive Summary

Add a full productivity layer to ii-agent by implementing 5 new components that close the gaps identified against the [Anthropic Productivity Plugin](https://github.com/anthropics/knowledge-work-plugins/tree/main/productivity). All work uses the existing `BaseSkill` + `@register_skill` pattern so new skills auto-discover without modifying core framework files.

### Scope

| Component | New Skill Directory | Estimated LOC | Priority |
|-----------|-------------------|---------------|----------|
| **Memory Management** | `src/ii_skills/memory/` (implement placeholder) | ~600 | P0 — Foundation |
| **Task Management** | `src/ii_skills/task_management/` (new) | ~700 | P1 — Core |
| **MCP Connector Layer** | `src/ii_skills/connectors/` (new) | ~500 | P2 — Integration |
| **Productivity Orchestrator** | `src/ii_skills/productivity/` (new) | ~450 | P3 — Workflow |
| **Visual Dashboard** | `src/ii_skills/task_management/dashboard/` (new) | ~400 | P4 — Polish |

**Total estimated new code: ~2,650 lines across 15-20 new files.**

---

## Fork Safety Strategy

### Problem
This repo is a fork of `robertodbabaran/ii-agent`. The upstream `develop` branch will continue to receive edits. Our changes must not create merge conflicts when pulling upstream.

### Upstream "Heat Map" (from git log analysis)

| Risk Level | Files | Edit Count |
|------------|-------|------------|
| **HIGH** | `src/ii_skills/shared/__init__.py` | 10 edits |
| **HIGH** | `CLAUDE.md` | 9 edits |
| **MEDIUM** | `src/ii_skills/ib_toolkit/__init__.py` | 4 edits |
| **MEDIUM** | `src/ii_skills/bridge/skill_tool.py` | 3 edits |
| **MEDIUM** | `src/ii_skills/shared/datastore.py` | 3 edits |
| **LOW** | `src/ii_skills/deal_memory/` | 1 edit (added once) |
| **NONE** | `src/ii_agent/` (core framework) | 0 edits since import |

### Mitigation Rules

1. **NEW DIRECTORIES ONLY** — All new skills go in their own directories under `src/ii_skills/`. The `discover_skills()` function auto-imports any subdirectory, so no registration changes are needed.

2. **NEVER MODIFY hot files inline** — Do not add imports/exports to `src/ii_skills/shared/__init__.py`. New shared utilities go in new files within `shared/` (e.g., `shared/memory_tiers.py`, `shared/connector_registry.py`). Import them directly in the skill that needs them.

3. **CLAUDE.md update goes LAST** — Add a single new section at the bottom of CLAUDE.md in the final commit. This localizes any merge conflict to one predictable block.

4. **ZERO changes to bridge layer** — `skill_tool.py` and `skill_registry.py` are not modified. New skills use the existing `BaseSkill` → `@register_skill` → auto-discovery pipeline exactly as-is.

5. **ZERO changes to existing skills** — `ib_toolkit`, `ir_toolkit`, `deal_memory`, `pdf_extractor`, `spaced_repetition`, `output_organizer` are not touched.

6. **Separate config files** — MCP connector config goes in a new `.mcp.json` file (gitignored if it contains secrets, or committed with placeholders). Not added to `pyproject.toml`.

7. **New dependencies added to `pyproject.toml` only if strictly required** — Prefer stdlib. If a dep is needed, add it at the END of the dependency list to minimize diff overlap.

### File Ownership Matrix

| New File/Directory | Upstream Risk | Why Safe |
|-------------------|---------------|----------|
| `src/ii_skills/memory/__init__.py` | **LOW** — placeholder exists but is empty (just a docstring) | We implement the empty file; upstream hasn't touched it since creation |
| `src/ii_skills/task_management/` | **NONE** — directory doesn't exist upstream | Entirely new |
| `src/ii_skills/connectors/` | **NONE** — directory doesn't exist upstream | Entirely new |
| `src/ii_skills/productivity/` | **NONE** — directory doesn't exist upstream | Entirely new |
| `src/ii_skills/shared/memory_tiers.py` | **NONE** — new file in shared/ | New file, not exported from `__init__.py` |
| `src/ii_skills/shared/connector_registry.py` | **NONE** — new file in shared/ | New file, not exported from `__init__.py` |
| `.mcp.json` | **NONE** — doesn't exist upstream | Entirely new |
| `TASKS.md` | **NONE** — doesn't exist upstream | Runtime-generated, gitignored |
| `PRODUCTIVITY_IMPLEMENTATION_PLAN.md` | **NONE** — doesn't exist upstream | This file |

---

## Phase 0: Pre-Flight Checks

**Before writing any code, verify:**

```bash
# 1. Confirm branch
git branch --show-current
# Expected: claude/evaluate-agent-capabilities-Ut8a8

# 2. Confirm existing tests pass
cd /home/user/ii-agent && python -m pytest tests/ -x -q

# 3. Confirm skill discovery works
python -c "import ii_skills; print(ii_skills.list_skills())"

# 4. Confirm memory placeholder exists and is empty
cat src/ii_skills/memory/__init__.py
```

---

## Phase 1: Memory Management Skill (P0 — Foundation)

### Goal
Implement the empty `src/ii_skills/memory/` placeholder into a full two-tier workplace memory system. This is the foundation — task management and the productivity orchestrator depend on it.

### Architecture

```
src/ii_skills/memory/
├── __init__.py              # MemoryManagementSkill (BaseSkill subclass)
└── templates/
    ├── claude_md.md         # Hot-cache template for CLAUDE.md Memory section
    ├── glossary.md          # Full decoder ring template
    ├── person.md            # Person profile template
    ├── project.md           # Project profile template
    └── company_context.md   # Company context template

src/ii_skills/shared/
└── memory_tiers.py          # TieredMemoryStore — two-tier read/write engine
```

### New File: `src/ii_skills/shared/memory_tiers.py`

The core engine for the two-tier memory system. Separate from existing `memory.py` to avoid conflicts.

```python
"""
Two-tier memory system: hot cache (CLAUDE.md) + deep storage (memory/ directory).

Hot cache: ~100 lines in a designated section of CLAUDE.md or a separate memory file.
Deep storage: memory/ directory with glossary.md, people/, projects/, context/ subdirs.

Usage:
    store = TieredMemoryStore(workspace_root="/path/to/workspace")
    store.initialize()  # Creates directory structure if missing
    store.add_person("Todd", {"full_name": "Todd Martinez", "role": "Finance Lead", ...})
    result = store.lookup("todd")  # Tiered: hot cache → glossary → people/ → not found
    store.promote("todd")  # Move from deep storage to hot cache
    store.demote("todd")   # Move from hot cache to deep storage only
"""
```

**Key classes and methods:**

```python
class TieredMemoryStore:
    def __init__(self, workspace_root: str)
    def initialize(self) -> None
        # Creates: memory/, memory/glossary.md, memory/people/, memory/projects/, memory/context/

    # --- Tiered Lookup (the core value) ---
    def lookup(self, term: str) -> Optional[Dict]
        # 1. Check hot cache (CLAUDE.md Memory section or memory_hot_cache.md)
        # 2. Check memory/glossary.md
        # 3. Check memory/people/{term}.md, memory/projects/{term}.md
        # 4. Return None (caller should ask user)

    # --- Write Operations ---
    def add_person(self, short_name: str, profile: Dict) -> None
    def add_term(self, term: str, meaning: str, context: str = "") -> None
    def add_project(self, name: str, details: Dict) -> None
    def add_preference(self, key: str, value: str) -> None
    def update_company_context(self, section: str, content: str) -> None

    # --- Promotion / Demotion ---
    def promote(self, term: str) -> bool  # Deep → hot cache
    def demote(self, term: str) -> bool   # Hot cache → deep only

    # --- Bulk Operations ---
    def get_hot_cache(self) -> str  # Return formatted hot cache content
    def get_full_glossary(self) -> Dict
    def search(self, query: str) -> List[Dict]
    def export_all(self) -> Dict  # Full memory dump as structured data

    # --- File I/O Helpers ---
    def _read_hot_cache(self) -> Dict
    def _write_hot_cache(self, data: Dict) -> None
    def _read_glossary(self) -> Dict
    def _write_glossary(self, data: Dict) -> None
    def _read_profile(self, category: str, name: str) -> Optional[Dict]
    def _write_profile(self, category: str, name: str, data: Dict) -> None
```

**Hot cache format** (stored as `memory/hot_cache.md` — NOT modifying the repo CLAUDE.md):

```markdown
# Memory — Hot Cache

## Me
[Name], [Role]. [One-liner.]

## People
| Who | Role |
|-----|------|
| **Todd** | Todd Martinez, Finance Lead |

## Terms
| Term | Meaning |
|------|---------|
| PSR | Pipeline Status Report |

## Projects
| Name | What |
|------|------|
| **Phoenix** | DB migration, Q2 launch |

## Preferences
- Async-first, Slack over email
```

> **Fork safety note:** We use `memory/hot_cache.md` instead of injecting into the repo's `CLAUDE.md`. This avoids any conflict with the hot `CLAUDE.md` file and keeps memory data separate from project documentation.

### New File: `src/ii_skills/memory/__init__.py`

```python
@register_skill
class MemoryManagementSkill(BaseSkill):
    name = "memory"
    version = "1.0.0"
    description = "Two-tier workplace memory: decode shorthand, track people/projects/terms"

    def get_capabilities(self) -> List[str]:
        return [
            # Lookup
            "lookup",             # Tiered lookup of any term/person/project
            "who_is",             # Lookup a person specifically
            "what_is",            # Lookup a term/project specifically

            # Write
            "remember_person",    # Add/update person profile
            "remember_term",      # Add/update glossary term
            "remember_project",   # Add/update project
            "remember_preference",# Add/update preference
            "update_context",     # Update company context

            # Manage
            "promote",            # Move item to hot cache
            "demote",             # Remove item from hot cache (keep in deep)
            "search_memory",      # Search across all memory
            "export_memory",      # Export full memory as JSON

            # Bootstrap
            "initialize_memory",  # Create directory structure + templates
            "get_hot_cache",      # Return current hot cache content
        ]
```

### Actions Detail

| Action | Input | Output | Risk Level |
|--------|-------|--------|------------|
| `lookup` | `{"term": "todd"}` | `{"found": true, "tier": "hot_cache", "type": "person", "data": {...}}` | READ_ONLY |
| `who_is` | `{"name": "todd"}` | `{"found": true, "profile": {...}}` | READ_ONLY |
| `what_is` | `{"term": "PSR"}` | `{"found": true, "meaning": "Pipeline Status Report", ...}` | READ_ONLY |
| `remember_person` | `{"short_name": "todd", "full_name": "Todd Martinez", "role": "Finance Lead", ...}` | `{"success": true}` | WRITE |
| `remember_term` | `{"term": "PSR", "meaning": "Pipeline Status Report", "context": "Weekly sales doc"}` | `{"success": true}` | WRITE |
| `remember_project` | `{"name": "phoenix", "description": "DB migration", "codenames": ["the migration"], ...}` | `{"success": true}` | WRITE |
| `remember_preference` | `{"key": "meeting_length", "value": "25-min with buffers"}` | `{"success": true}` | WRITE |
| `update_context` | `{"section": "tools", "content": "Slack for comms, Asana for tasks"}` | `{"success": true}` | WRITE |
| `promote` | `{"term": "todd"}` | `{"success": true, "promoted": true}` | WRITE |
| `demote` | `{"term": "todd"}` | `{"success": true, "demoted": true}` | WRITE |
| `search_memory` | `{"query": "finance"}` | `{"results": [{...}, ...]}` | READ_ONLY |
| `export_memory` | `{}` | `{"people": {...}, "terms": {...}, "projects": {...}, ...}` | READ_ONLY |
| `initialize_memory` | `{"workspace_root": "/path"}` | `{"success": true, "created": ["memory/", ...]}` | WRITE |
| `get_hot_cache` | `{}` | `{"content": "# Memory — Hot Cache\n..."}` | READ_ONLY |

### Integration with Existing MemoryService

The `TieredMemoryStore` is a **file-based** system (markdown files in `memory/`). It complements but does NOT replace the existing `MemoryService` in `shared/memory.py` which is a programmatic key-value store. The relationship:

```
TieredMemoryStore  →  File-based (memory/*.md) — for workplace context, human-readable
MemoryService      →  Programmatic (key-value)  — for deal context, API-driven
DealMemory         →  Domain-specific wrapper    — for deal/company facts
```

The `MemoryManagementSkill` can optionally sync between the two: when `remember_person` is called, it writes to both the file-based store AND calls `MemoryService.remember()` so the data is available to other skills.

### Test File: `tests/skills/test_memory_management.py`

```
- test_initialize_creates_directory_structure
- test_lookup_hot_cache_first
- test_lookup_falls_through_to_glossary
- test_lookup_falls_through_to_profiles
- test_lookup_returns_none_when_not_found
- test_remember_person_creates_profile
- test_remember_term_adds_to_glossary
- test_promote_moves_to_hot_cache
- test_demote_removes_from_hot_cache
- test_search_across_all_tiers
- test_export_full_memory
```

### Acceptance Criteria

- [ ] `discover_skills()` finds and registers the `memory` skill
- [ ] Tiered lookup resolves terms from hot cache first, then deep storage
- [ ] Person profiles are stored as individual markdown files in `memory/people/`
- [ ] Hot cache stays under ~100 lines with promote/demote
- [ ] Existing `MemoryService` and `DealMemory` continue to work unchanged
- [ ] All tests pass

---

## Phase 2: Task Management Skill (P1 — Core)

### Goal
Implement markdown-based task tracking with `TASKS.md`, supporting Active / Waiting On / Someday / Done sections.

### Architecture

```
src/ii_skills/task_management/
├── __init__.py              # TaskManagementSkill (BaseSkill subclass)
├── task_store.py            # TASKS.md read/write/parse engine
├── dashboard/
│   └── dashboard.html       # Static HTML dashboard (Phase 4)
└── templates/
    └── tasks_template.md    # Initial TASKS.md template
```

### New File: `src/ii_skills/task_management/task_store.py`

The engine for reading, writing, and manipulating `TASKS.md`.

```python
"""
TASKS.md parser and writer.

Format:
    # Tasks

    ## Active
    - [ ] **Task title** - context, for whom, due date
      - Sub-bullet for details

    ## Waiting On
    - [ ] **Task** - since [date]

    ## Someday
    - [ ] **Future task**

    ## Done
    - [x] ~~Completed task~~ (2026-02-06)
"""

class Task:
    title: str
    context: str          # Free-text context
    for_whom: Optional[str]
    due_date: Optional[str]
    sub_items: List[str]
    completed: bool
    completed_date: Optional[str]
    section: str          # "active", "waiting_on", "someday", "done"

class TaskStore:
    def __init__(self, tasks_file: str = "TASKS.md")

    # --- Read ---
    def load(self) -> Dict[str, List[Task]]   # section → tasks
    def get_active(self) -> List[Task]
    def get_waiting(self) -> List[Task]
    def get_someday(self) -> List[Task]
    def get_done(self) -> List[Task]
    def get_overdue(self) -> List[Task]
    def get_summary(self) -> Dict              # Counts + overdue + urgent

    # --- Write ---
    def add_task(self, title, section="active", context="", for_whom=None, due_date=None) -> Task
    def complete_task(self, title_or_index: str) -> Task   # Move to Done with date
    def move_task(self, title_or_index: str, to_section: str) -> Task
    def update_task(self, title_or_index: str, **updates) -> Task
    def delete_task(self, title_or_index: str) -> bool
    def reorder_task(self, title_or_index: str, new_position: int) -> bool

    # --- Maintenance ---
    def clean_done(self, older_than_days: int = 7) -> int  # Remove old done items
    def save(self) -> None                                   # Write back to TASKS.md

    # --- Parsing Internals ---
    def _parse_markdown(self, content: str) -> Dict[str, List[Task]]
    def _render_markdown(self, sections: Dict[str, List[Task]]) -> str
    def _match_task(self, query: str, tasks: List[Task]) -> Optional[Task]
```

### New File: `src/ii_skills/task_management/__init__.py`

```python
@register_skill
class TaskManagementSkill(BaseSkill):
    name = "task_management"
    version = "1.0.0"
    description = "Markdown-based task tracking with TASKS.md — Active/Waiting/Someday/Done"

    def get_capabilities(self) -> List[str]:
        return [
            # Read
            "get_tasks",          # Return all tasks grouped by section
            "get_summary",        # Quick summary with counts + overdue
            "get_active",         # Active tasks only
            "get_waiting",        # Waiting On tasks only

            # Write
            "add_task",           # Add a new task
            "complete_task",      # Mark task as done
            "move_task",          # Move between sections
            "update_task",        # Edit task details
            "delete_task",        # Remove a task

            # Maintenance
            "clean_done",         # Clear old done items
            "initialize_tasks",   # Create TASKS.md from template if missing

            # Meeting extraction (future: parse meeting notes for action items)
            "extract_tasks_from_text",  # Parse text for commitments/action items
        ]
```

### Actions Detail

| Action | Input | Output | Risk Level |
|--------|-------|--------|------------|
| `get_tasks` | `{}` | `{"active": [...], "waiting_on": [...], "someday": [...], "done": [...]}` | READ_ONLY |
| `get_summary` | `{}` | `{"active_count": 5, "waiting_count": 2, "overdue": [...], "due_today": [...]}` | READ_ONLY |
| `add_task` | `{"title": "Send proposal", "for_whom": "Todd", "due_date": "2026-02-10"}` | `{"success": true, "task": {...}}` | WRITE |
| `complete_task` | `{"task": "Send proposal"}` | `{"success": true, "completed": {...}}` | WRITE |
| `move_task` | `{"task": "Send proposal", "to_section": "waiting_on"}` | `{"success": true}` | WRITE |
| `extract_tasks_from_text` | `{"text": "I'll send the PSR to Todd by Friday"}` | `{"extracted": [{"title": "Send PSR to Todd", "due": "Friday"}]}` | READ_ONLY |
| `initialize_tasks` | `{}` | `{"success": true, "created": "TASKS.md"}` | WRITE |

### TASKS.md Location

The `TASKS.md` file lives at the **workspace root** (`/home/user/ii-agent/TASKS.md`). It should be added to `.gitignore` since it contains personal task data, not project code.

```gitignore
# Task management (personal, not committed)
TASKS.md
memory/
```

### Test File: `tests/skills/test_task_management.py`

```
- test_initialize_creates_tasks_md
- test_parse_markdown_sections
- test_add_task_to_active
- test_complete_task_moves_to_done
- test_complete_task_adds_date_and_strikethrough
- test_move_task_between_sections
- test_clean_done_removes_old_items
- test_get_overdue_detects_past_due_dates
- test_get_summary_counts
- test_extract_tasks_from_meeting_notes
- test_roundtrip_parse_render_preserves_content
```

### Acceptance Criteria

- [ ] `TASKS.md` is created from template on first use
- [ ] All 4 sections parse and render correctly
- [ ] Tasks can be added, completed, moved, and deleted
- [ ] Completed tasks get strikethrough and date
- [ ] Overdue detection works based on due dates
- [ ] File roundtrip (parse → render) preserves content exactly
- [ ] `TASKS.md` is gitignored

---

## Phase 3: MCP Connector Layer (P2 — Integration)

### Goal
Create a tool-agnostic connector architecture that allows the agent to interact with external services (Slack, email, calendar, project trackers, knowledge bases) via MCP servers.

### Architecture

```
src/ii_skills/connectors/
├── __init__.py              # ConnectorSkill (BaseSkill subclass)
├── registry.py              # ConnectorRegistry — category → MCP server mapping
├── adapters/
│   ├── __init__.py
│   ├── base.py              # BaseConnectorAdapter (abstract)
│   ├── slack.py             # SlackAdapter (~~chat)
│   ├── email.py             # EmailAdapter (~~email) — extends existing Gmail SMTP
│   ├── calendar.py          # CalendarAdapter (~~calendar)
│   ├── notion.py            # NotionAdapter (~~knowledge_base)
│   └── project_tracker.py   # ProjectTrackerAdapter (~~project_tracker)
└── config/
    └── connectors.example.json  # Example connector configuration

.mcp.json                    # MCP server configuration (workspace root, gitignored)
```

### Design: Tool-Agnostic Categories

Following the Anthropic productivity plugin pattern, connectors are referenced by **category**, not product:

```python
CONNECTOR_CATEGORIES = {
    "chat":             ["slack", "teams", "discord"],
    "email":            ["microsoft365", "gmail"],
    "calendar":         ["microsoft365", "google_calendar"],
    "knowledge_base":   ["notion", "confluence", "coda"],
    "project_tracker":  ["asana", "linear", "jira", "monday", "clickup"],
    "office_suite":     ["microsoft365", "google_workspace"],
}
```

### New File: `src/ii_skills/connectors/registry.py`

```python
"""
ConnectorRegistry: Maps ~~category placeholders to configured MCP servers.

Design principle: Skills reference connectors by category (e.g., "chat"),
not by product (e.g., "slack"). The registry resolves the category to
the user's configured MCP server for that category.

This allows workflows to be portable across different tool stacks:
- Company A uses Slack + Asana + Notion
- Company B uses Teams + Jira + Confluence
- Same skill code works for both
"""

class ConnectorRegistry:
    def __init__(self, config_path: str = ".mcp.json")

    def get_connector(self, category: str) -> Optional[BaseConnectorAdapter]
    def list_categories(self) -> List[str]
    def list_configured(self) -> Dict[str, str]  # category → server name
    def is_configured(self, category: str) -> bool
    def health_check(self) -> Dict[str, str]     # category → status

    def register_adapter(self, category: str, adapter: BaseConnectorAdapter) -> None
    def _load_config(self) -> Dict
```

### New File: `src/ii_skills/connectors/adapters/base.py`

```python
class BaseConnectorAdapter(ABC):
    """Abstract base for all connector adapters."""
    category: str           # "chat", "email", etc.
    provider: str           # "slack", "microsoft365", etc.

    @abstractmethod
    async def connect(self) -> bool
    @abstractmethod
    async def disconnect(self) -> None
    @abstractmethod
    async def health_check(self) -> Dict

    # Category-specific methods are defined in subclasses
```

### Adapter Method Signatures

**ChatAdapter** (Slack/Teams):
```python
async def send_message(self, channel: str, message: str) -> Dict
async def read_messages(self, channel: str, limit: int = 20) -> List[Dict]
async def search_messages(self, query: str, limit: int = 10) -> List[Dict]
async def list_channels(self) -> List[Dict]
```

**EmailAdapter** (Gmail/M365):
```python
async def send_email(self, to: str, subject: str, body: str) -> Dict
async def read_inbox(self, limit: int = 20, unread_only: bool = False) -> List[Dict]
async def search_email(self, query: str, limit: int = 10) -> List[Dict]
async def get_email(self, message_id: str) -> Dict
```

**CalendarAdapter** (Google/M365):
```python
async def get_events(self, start: str, end: str) -> List[Dict]
async def create_event(self, title: str, start: str, end: str, **kwargs) -> Dict
async def get_today(self) -> List[Dict]
async def get_next_event(self) -> Optional[Dict]
```

**KnowledgeBaseAdapter** (Notion/Confluence):
```python
async def search(self, query: str, limit: int = 10) -> List[Dict]
async def get_page(self, page_id: str) -> Dict
async def create_page(self, title: str, content: str, parent_id: str = None) -> Dict
```

**ProjectTrackerAdapter** (Asana/Linear/Jira):
```python
async def get_my_tasks(self, status: str = "open") -> List[Dict]
async def create_task(self, title: str, **kwargs) -> Dict
async def update_task(self, task_id: str, **kwargs) -> Dict
async def sync_to_local(self) -> List[Dict]  # Pull tasks into TASKS.md
async def sync_from_local(self) -> List[Dict]  # Push TASKS.md changes upstream
```

### New File: `src/ii_skills/connectors/__init__.py`

```python
@register_skill
class ConnectorSkill(BaseSkill):
    name = "connectors"
    version = "1.0.0"
    description = "Tool-agnostic connectors for chat, email, calendar, knowledge base, project trackers"

    def get_capabilities(self) -> List[str]:
        return [
            # Discovery
            "list_connectors",      # Show configured connectors by category
            "check_health",         # Health check all connectors

            # Chat
            "send_message",         # Send via ~~chat
            "read_messages",        # Read from ~~chat
            "search_messages",      # Search ~~chat history

            # Email
            "send_email",           # Send via ~~email
            "read_inbox",           # Read ~~email inbox
            "search_email",         # Search ~~email

            # Calendar
            "get_calendar",         # Get ~~calendar events
            "get_today_schedule",   # Today's events
            "create_event",         # Create ~~calendar event

            # Knowledge Base
            "search_kb",            # Search ~~knowledge_base
            "get_kb_page",          # Read ~~knowledge_base page

            # Project Tracker
            "get_tracker_tasks",    # Get tasks from ~~project_tracker
            "sync_tasks",           # Bidirectional sync with TASKS.md
        ]
```

### `.mcp.json` Configuration Format

```json
{
  "connectors": {
    "chat": {
      "provider": "slack",
      "mcp_server": "slack-mcp-server",
      "config": {
        "workspace": "mycompany",
        "token_env": "SLACK_BOT_TOKEN"
      }
    },
    "email": {
      "provider": "gmail",
      "mcp_server": "gmail-mcp-server",
      "config": {
        "credentials_env": "GMAIL_CREDENTIALS_PATH"
      }
    },
    "calendar": {
      "provider": "google_calendar",
      "mcp_server": "gcal-mcp-server",
      "config": {
        "credentials_env": "GCAL_CREDENTIALS_PATH"
      }
    },
    "knowledge_base": {
      "provider": "notion",
      "mcp_server": "notion-mcp-server",
      "config": {
        "token_env": "NOTION_TOKEN"
      }
    },
    "project_tracker": {
      "provider": "linear",
      "mcp_server": "linear-mcp-server",
      "config": {
        "token_env": "LINEAR_API_KEY"
      }
    }
  }
}
```

### Graceful Degradation

Connectors that aren't configured simply return `{"error": "No connector configured for category 'chat'", "available": false}`. The system never crashes due to missing connectors. Skills that use connectors check availability first:

```python
if self.registry.is_configured("chat"):
    await self.registry.get_connector("chat").send_message(...)
else:
    return {"warning": "Chat connector not configured. Skipping notification."}
```

### Test File: `tests/skills/test_connectors.py`

```
- test_registry_loads_config
- test_get_connector_by_category
- test_unconfigured_category_returns_none
- test_health_check_all_connectors
- test_adapter_interface_contract
- test_graceful_degradation_on_missing_config
```

### Acceptance Criteria

- [ ] ConnectorRegistry loads `.mcp.json` configuration
- [ ] Adapters follow a consistent interface per category
- [ ] Unconfigured connectors degrade gracefully (no crashes)
- [ ] Connector health checks report status
- [ ] `.mcp.json` is gitignored (contains token references)

---

## Phase 4: Productivity Orchestrator (P3 — Workflow)

### Goal
Implement the `/start`, `/update`, and `/update --comprehensive` workflows that tie together memory, tasks, and connectors into cohesive daily workflows.

### Architecture

```
src/ii_skills/productivity/
├── __init__.py              # ProductivitySkill (BaseSkill subclass)
├── workflows/
│   ├── __init__.py
│   ├── start.py             # /start workflow
│   ├── update.py            # /update workflow
│   └── comprehensive.py     # /update --comprehensive workflow
└── templates/
    └── daily_brief.md       # Template for daily briefing output
```

### Workflow: `/start` (Bootstrap)

**What it does:**
1. Initialize `TASKS.md` from template (if missing)
2. Initialize `memory/` directory structure (if missing)
3. Copy dashboard HTML to workspace
4. If connectors configured: scan email/calendar/chat to seed initial memory
5. Output a welcome summary

```python
async def start_workflow(
    task_skill: TaskManagementSkill,
    memory_skill: MemoryManagementSkill,
    connector_skill: Optional[ConnectorSkill] = None,
) -> Dict:
    results = {}

    # Step 1: Initialize tasks
    results["tasks"] = task_skill.execute("initialize_tasks")

    # Step 2: Initialize memory
    results["memory"] = memory_skill.execute("initialize_memory",
                                              workspace_root=workspace_root)

    # Step 3: Copy dashboard
    results["dashboard"] = _copy_dashboard()

    # Step 4: Bootstrap from connected sources (if available)
    if connector_skill and connector_skill.execute("list_connectors")["configured"]:
        # Scan calendar for upcoming meetings → seed projects
        # Scan email for recent contacts → seed people
        # Scan chat for common terms → seed glossary
        results["bootstrap"] = await _bootstrap_from_sources(connector_skill, memory_skill)

    # Step 5: Summary
    results["summary"] = _generate_welcome_summary(results)
    return results
```

### Workflow: `/update` (Daily Triage)

**What it does:**
1. Read `TASKS.md` — flag stale items (active > 7 days, waiting > 14 days)
2. Check memory gaps — terms used in recent conversations not in glossary
3. If project tracker configured: pull new/updated tasks
4. Output a triage report

```python
async def update_workflow(
    task_skill: TaskManagementSkill,
    memory_skill: MemoryManagementSkill,
    connector_skill: Optional[ConnectorSkill] = None,
) -> Dict:
    results = {}

    # Step 1: Triage stale tasks
    summary = task_skill.execute("get_summary")
    stale = [t for t in summary["active"] if _is_stale(t, days=7)]
    results["stale_tasks"] = stale

    # Step 2: Check memory coverage
    hot_cache = memory_skill.execute("get_hot_cache")
    results["memory_status"] = {
        "people_count": ...,
        "terms_count": ...,
        "projects_count": ...,
    }

    # Step 3: Sync from project tracker (if configured)
    if connector_skill and connector_skill.execute("list_connectors")["configured"].get("project_tracker"):
        results["synced_tasks"] = connector_skill.execute("sync_tasks")

    # Step 4: Generate triage report
    results["report"] = _generate_triage_report(results)
    return results
```

### Workflow: `/update --comprehensive` (Deep Scan)

**What it does:**
Everything in `/update` PLUS:
1. Scan email for commitments/action items missed
2. Scan calendar for upcoming meetings that need prep
3. Scan chat for messages needing response
4. Flag missed todos and suggest new memory entries

### New File: `src/ii_skills/productivity/__init__.py`

```python
@register_skill
class ProductivitySkill(BaseSkill):
    name = "productivity"
    version = "1.0.0"
    description = "Productivity workflows: /start, /update, daily briefing"

    def get_capabilities(self) -> List[str]:
        return [
            "start",                  # Bootstrap workspace
            "update",                 # Daily triage
            "update_comprehensive",   # Deep scan with email/calendar/chat
            "daily_brief",            # Generate morning briefing
            "weekly_review",          # Generate weekly review
        ]
```

### Cross-Skill Coordination

The productivity orchestrator calls other skills by getting them from the registry:

```python
def initialize(self) -> bool:
    from ii_skills import get_skill
    self._task_skill = get_skill("task_management")
    self._memory_skill = get_skill("memory")
    self._connector_skill = get_skill("connectors")  # May be None
    return True
```

This is the same pattern used by `deal_orchestrator.py` in the IB toolkit — skills reference each other through `get_skill()`, not through imports.

### Test File: `tests/skills/test_productivity.py`

```
- test_start_initializes_tasks_and_memory
- test_start_without_connectors_still_works
- test_update_flags_stale_tasks
- test_update_syncs_from_tracker
- test_comprehensive_scans_email
- test_daily_brief_format
```

### Acceptance Criteria

- [ ] `/start` creates TASKS.md + memory/ in one action
- [ ] `/update` identifies stale tasks and reports them
- [ ] `/update --comprehensive` scans connected sources
- [ ] All workflows degrade gracefully when connectors unavailable
- [ ] Cross-skill references use `get_skill()` (no import coupling)

---

## Phase 5: Visual Dashboard (P4 — Polish)

### Goal
A local HTML dashboard that displays tasks in a board view with bidirectional sync to `TASKS.md`.

### Architecture

```
src/ii_skills/task_management/dashboard/
├── dashboard.html          # Single-file HTML/CSS/JS application
└── README.md               # Usage instructions
```

### Design: Single-File HTML App

The dashboard is a **self-contained HTML file** (no build step, no npm, no server). It:

1. Reads `TASKS.md` via `FileReader` API (user opens the file)
2. Renders a Kanban board with 4 columns (Active, Waiting On, Someday, Done)
3. Supports drag-and-drop between columns
4. Auto-saves changes back to `TASKS.md` format
5. Detects external changes (polling or FileSystemObserver)

### Dashboard Features

```
┌─────────────────────────────────────────────────────────────┐
│  📋 Tasks                                    [Refresh] [⚙]  │
├──────────────┬──────────────┬──────────────┬────────────────┤
│   Active     │  Waiting On  │   Someday    │     Done       │
│              │              │              │                │
│ ┌──────────┐ │ ┌──────────┐ │ ┌──────────┐ │ ┌────────────┐ │
│ │Send prop │ │ │Feedback  │ │ │Learn Rust│ │ │~~Setup CI~~│ │
│ │for Todd  │ │ │from Sarah│ │ │          │ │ │(2026-02-05)│ │
│ │due 02/10 │ │ │since 02/3│ │ │          │ │ │            │ │
│ └──────────┘ │ └──────────┘ │ └──────────┘ │ └────────────┘ │
│ ┌──────────┐ │              │              │                │
│ │Review PR │ │              │              │                │
│ │#42       │ │              │              │                │
│ └──────────┘ │              │              │                │
└──────────────┴──────────────┴──────────────┴────────────────┘
```

### Implementation Notes

- **No server required** — opens as `file://` or served via `python -m http.server`
- **Vanilla JS** — no React/Vue/framework dependencies
- **CSS Grid** for the Kanban layout
- **localStorage** for draft edits (in case of unsaved changes)
- **~400 lines** total (HTML + CSS + JS in one file)

### Serving Options

```bash
# Option 1: Direct file open
open src/ii_skills/task_management/dashboard/dashboard.html

# Option 2: Local server (enables file watching)
python -m http.server 8080 --directory src/ii_skills/task_management/dashboard/
```

### Acceptance Criteria

- [ ] Dashboard renders TASKS.md content as a Kanban board
- [ ] Drag-and-drop moves tasks between columns
- [ ] Changes sync back to TASKS.md markdown format
- [ ] Works as a standalone HTML file (no build step)
- [ ] External edits to TASKS.md are detected and reflected

---

## Phase 6: Integration & Final Wiring

### 6a. `.gitignore` Updates

Add to `.gitignore` (at the END to minimize merge conflict):

```gitignore
# Productivity layer (personal data, not committed)
TASKS.md
memory/
.mcp.json
```

### 6b. CLAUDE.md Update

Add a **single new section** at the bottom of `CLAUDE.md` (not interspersed with existing content — this keeps merge conflicts to one block):

```markdown
---

## Productivity Layer

**New Skills:**

| Skill | Location | Actions |
|-------|----------|---------|
| **memory** | `src/ii_skills/memory/` | 14 actions — Two-tier workplace memory |
| **task_management** | `src/ii_skills/task_management/` | 12 actions — TASKS.md tracking |
| **connectors** | `src/ii_skills/connectors/` | 16 actions — MCP connector layer |
| **productivity** | `src/ii_skills/productivity/` | 5 actions — /start, /update workflows |

**Quick Commands:**
| Command | What it does |
|---------|-------------|
| "Start my productivity workspace" | Initialize TASKS.md + memory + dashboard |
| "What's on my plate?" | Show active tasks and overdue items |
| "Add a task: Send proposal to Todd by Friday" | Add task with context and due date |
| "Done with the proposal" | Complete task, move to Done |
| "Who is Todd?" | Tiered memory lookup |
| "Remember that PSR means Pipeline Status Report" | Add to glossary |
| "Update my tasks" | Triage stale items, sync from trackers |
| "Deep update" | Comprehensive scan of email/calendar/chat |
```

### 6c. Dependency Check

**No new dependencies required for Phase 1-2.** The memory and task management skills use only:
- `pathlib` (stdlib)
- `json` (stdlib)
- `datetime` (stdlib)
- `re` (stdlib)
- `dataclasses` (stdlib)

**Phase 3 (connectors) may require:**
- MCP client libraries (specific to chosen providers)
- These would be optional dependencies, not breaking if missing

### 6d. Test Suite

Run the full test suite after each phase:

```bash
# After each phase
python -m pytest tests/ -x -q

# Verify skill discovery
python -c "
import ii_skills
skills = ii_skills.list_skills()
for s in skills:
    print(f'{s[\"name\"]:20s} v{s[\"version\"]}  ({len(ii_skills.get_skill(s[\"name\"]).get_capabilities())} actions)')
"
```

Expected output after all phases:

```
ib_toolkit           v1.5.0  (28 actions)
ir_toolkit           v1.0.0  (X actions)
deal_memory          v1.0.0  (10 actions)
pdf_extractor        v1.0.0  (6 actions)
spaced_repetition    v1.0.0  (8 actions)
output_organizer     v1.0.0  (7 actions)
memory               v1.0.0  (14 actions)    ← NEW
task_management      v1.0.0  (12 actions)    ← NEW
connectors           v1.0.0  (16 actions)    ← NEW
productivity         v1.0.0  (5 actions)     ← NEW
```

---

## Implementation Timeline

### Recommended Execution Order

| Phase | What | Depends On | Estimated Files | Est. LOC |
|-------|------|-----------|-----------------|----------|
| **Phase 0** | Pre-flight checks | — | 0 | 0 |
| **Phase 1** | Memory Management | Phase 0 | 4 files | ~600 |
| **Phase 2** | Task Management | Phase 0 | 4 files | ~700 |
| **Phase 3** | MCP Connectors | Phase 0 | 8 files | ~500 |
| **Phase 4** | Productivity Orchestrator | Phases 1, 2, 3 | 5 files | ~450 |
| **Phase 5** | Visual Dashboard | Phase 2 | 2 files | ~400 |
| **Phase 6** | Integration & wiring | All above | 2 edits | ~50 |

**Phases 1, 2, and 3 can be developed in parallel** — they have no dependencies on each other. Phase 4 depends on all three. Phase 5 depends on Phase 2.

```
Phase 0 ─┬─ Phase 1 (Memory) ────────┐
          ├─ Phase 2 (Tasks) ─────────┼─ Phase 4 (Orchestrator) ─ Phase 6 (Integration)
          └─ Phase 3 (Connectors) ────┘         │
                                        Phase 5 (Dashboard) ──┘
```

### Git Commit Strategy

One commit per phase, with descriptive messages:

```
Phase 1: feat(memory): implement two-tier workplace memory system
Phase 2: feat(tasks): implement TASKS.md task management skill
Phase 3: feat(connectors): implement MCP connector layer
Phase 4: feat(productivity): implement /start and /update workflows
Phase 5: feat(dashboard): add visual task board (HTML)
Phase 6: chore: wire productivity layer into CLAUDE.md and .gitignore
```

---

## Appendix A: Complete New File Inventory

```
NEW FILES (17 total):
├── src/ii_skills/memory/__init__.py                         # MemoryManagementSkill
├── src/ii_skills/memory/templates/claude_md.md              # Hot-cache template
├── src/ii_skills/memory/templates/glossary.md               # Glossary template
├── src/ii_skills/memory/templates/person.md                 # Person profile template
├── src/ii_skills/memory/templates/project.md                # Project profile template
├── src/ii_skills/shared/memory_tiers.py                     # TieredMemoryStore engine
├── src/ii_skills/task_management/__init__.py                # TaskManagementSkill
├── src/ii_skills/task_management/task_store.py              # TASKS.md parser/writer
├── src/ii_skills/task_management/templates/tasks_template.md # TASKS.md template
├── src/ii_skills/task_management/dashboard/dashboard.html   # Visual dashboard
├── src/ii_skills/connectors/__init__.py                     # ConnectorSkill
├── src/ii_skills/connectors/registry.py                     # ConnectorRegistry
├── src/ii_skills/connectors/adapters/__init__.py            # Adapter package
├── src/ii_skills/connectors/adapters/base.py                # BaseConnectorAdapter
├── src/ii_skills/connectors/config/connectors.example.json  # Example config
├── src/ii_skills/productivity/__init__.py                   # ProductivitySkill
├── src/ii_skills/productivity/workflows/__init__.py         # Workflow package
├── src/ii_skills/productivity/workflows/start.py            # /start workflow
├── src/ii_skills/productivity/workflows/update.py           # /update workflow
├── src/ii_skills/productivity/workflows/comprehensive.py    # /update --comprehensive
├── src/ii_skills/productivity/templates/daily_brief.md      # Briefing template

MODIFIED FILES (2 total):
├── .gitignore                                               # Add TASKS.md, memory/, .mcp.json
└── CLAUDE.md                                                # Add Productivity Layer section (at bottom)

TEST FILES (4 total):
├── tests/skills/test_memory_management.py
├── tests/skills/test_task_management.py
├── tests/skills/test_connectors.py
└── tests/skills/test_productivity.py
```

## Appendix B: Cross-Reference with Gap Analysis

| Gap Identified | Addressed In | Phase |
|----------------|-------------|-------|
| Task Management (TASKS.md) | `task_management` skill | Phase 2 |
| Visual Dashboard | `task_management/dashboard/` | Phase 5 |
| Two-Tier Memory (hot cache + deep) | `memory` skill + `shared/memory_tiers.py` | Phase 1 |
| Workplace Shorthand Decoding | `memory` skill — `lookup` action | Phase 1 |
| People Directory | `memory` skill — `remember_person`, `who_is` | Phase 1 |
| Project Tracking (in memory) | `memory` skill — `remember_project` | Phase 1 |
| Chat Integration (Slack/Teams) | `connectors` skill — ChatAdapter | Phase 3 |
| Email Reading/Scanning | `connectors` skill — EmailAdapter | Phase 3 |
| Calendar Integration | `connectors` skill — CalendarAdapter | Phase 3 |
| Knowledge Base (Notion/Confluence) | `connectors` skill — KnowledgeBaseAdapter | Phase 3 |
| Project Trackers (Asana/Linear/Jira) | `connectors` skill — ProjectTrackerAdapter | Phase 3 |
| Bootstrap Workflow (/start) | `productivity` skill — `start` action | Phase 4 |
| Daily Sync (/update) | `productivity` skill — `update` action | Phase 4 |
| Tool-Agnostic Connector Architecture | `connectors/registry.py` + `.mcp.json` | Phase 3 |

**All 14 identified gaps are addressed.**
