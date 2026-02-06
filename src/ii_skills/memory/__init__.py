"""
Memory Management Skill

Two-tier workplace memory system: hot cache for frequently accessed context
plus deep file-based storage for people, projects, terms, and preferences.

Tiers:
    Hot cache  (memory/hot_cache.md)  — ~100 lines, most-used context
    Deep store (memory/people/, memory/projects/, memory/glossary.md) — full profiles

Lookup order: hot cache -> glossary -> people/ -> projects/ -> not found

Fork safety: Uses memory/hot_cache.md instead of modifying CLAUDE.md.
New file in shared/ (memory_tiers.py), not exported from shared/__init__.py.
"""

import asyncio
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from ii_skills import BaseSkill, register_skill

logger = logging.getLogger(__name__)

__version__ = "1.0.0"
__author__ = "II-Agent System"


@register_skill
class MemoryManagementSkill(BaseSkill):
    """Two-tier workplace memory: decode shorthand, track people/projects/terms."""

    name = "memory"
    version = __version__
    description = "Two-tier workplace memory: decode shorthand, track people/projects/terms"

    SKILL_DIR = Path(__file__).parent

    def __init__(self, config: Optional[Dict] = None):
        super().__init__(config)
        self._store = None

    def initialize(self) -> bool:
        """Initialize the skill and memory store."""
        from ii_skills.shared.memory_tiers import TieredMemoryStore

        workspace_root = self.config.get("workspace_root", str(Path.cwd()))
        self._store = TieredMemoryStore(workspace_root=workspace_root)
        self._initialized = True
        return True

    def validate_config(self) -> List[str]:
        """No required config for memory skill."""
        return []

    def get_capabilities(self) -> List[str]:
        """Return list of actions this skill provides."""
        return [
            # Lookup
            "lookup",
            "who_is",
            "what_is",
            # Write
            "remember_person",
            "remember_term",
            "remember_project",
            "remember_preference",
            "update_context",
            # Manage
            "promote",
            "demote",
            "search_memory",
            "export_memory",
            # Bootstrap
            "initialize_memory",
            "get_hot_cache",
        ]

    def execute(self, action: str, **kwargs) -> Dict:
        """Execute a memory action."""
        loop = None
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            pass

        if loop and loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, self._execute_async(action, **kwargs))
                return future.result()
        return asyncio.run(self._execute_async(action, **kwargs))

    async def _execute_async(self, action: str, **kwargs) -> Dict:
        """Async action router."""
        actions = {
            "lookup": self._lookup,
            "who_is": self._who_is,
            "what_is": self._what_is,
            "remember_person": self._remember_person,
            "remember_term": self._remember_term,
            "remember_project": self._remember_project,
            "remember_preference": self._remember_preference,
            "update_context": self._update_context,
            "promote": self._promote,
            "demote": self._demote,
            "search_memory": self._search_memory,
            "export_memory": self._export_memory,
            "initialize_memory": self._initialize_memory,
            "get_hot_cache": self._get_hot_cache,
        }

        handler = actions.get(action)
        if not handler:
            raise NotImplementedError(f"Action '{action}' not implemented")
        return await handler(**kwargs)

    # ------------------------------------------------------------------
    # Ensure store is initialized
    # ------------------------------------------------------------------

    def _ensure_store(self) -> None:
        """Lazily initialize store if needed."""
        if self._store is None:
            self.initialize()

    # ------------------------------------------------------------------
    # Lookup Actions
    # ------------------------------------------------------------------

    async def _lookup(self, term: str, **kwargs) -> Dict:
        """Tiered lookup of any term/person/project."""
        self._ensure_store()
        result = self._store.lookup(term)
        if result:
            return result
        return {"found": False, "term": term}

    async def _who_is(self, name: str, **kwargs) -> Dict:
        """Look up a person specifically."""
        self._ensure_store()
        result = self._store.lookup(name)
        if result and result.get("type") == "person":
            return {"found": True, "profile": result["data"]}
        return {"found": False, "name": name}

    async def _what_is(self, term: str, **kwargs) -> Dict:
        """Look up a term or project specifically."""
        self._ensure_store()
        result = self._store.lookup(term)
        if result and result.get("type") in ("term", "project"):
            return {"found": True, "type": result["type"], "data": result["data"]}
        return {"found": False, "term": term}

    # ------------------------------------------------------------------
    # Write Actions
    # ------------------------------------------------------------------

    async def _remember_person(self, short_name: str, **kwargs) -> Dict:
        """Add or update a person profile."""
        self._ensure_store()
        profile = {k: v for k, v in kwargs.items() if k != "short_name"}
        self._store.add_person(short_name, profile)

        # Optionally sync to MemoryService if available
        await self._sync_to_memory_service(
            key=f"person_{short_name}",
            content={"short_name": short_name, **profile},
            memory_type="fact",
        )

        return {"success": True, "short_name": short_name}

    async def _remember_term(self, term: str, meaning: str, context: str = "", **kwargs) -> Dict:
        """Add a term to the glossary."""
        self._ensure_store()
        self._store.add_term(term, meaning, context)
        return {"success": True, "term": term}

    async def _remember_project(self, name: str, **kwargs) -> Dict:
        """Add or update a project."""
        self._ensure_store()
        details = {k: v for k, v in kwargs.items() if k != "name"}
        self._store.add_project(name, details)
        return {"success": True, "name": name}

    async def _remember_preference(self, key: str, value: str, **kwargs) -> Dict:
        """Add or update a preference."""
        self._ensure_store()
        self._store.add_preference(key, value)
        return {"success": True, "key": key}

    async def _update_context(self, section: str, content: str, **kwargs) -> Dict:
        """Update a company context section."""
        self._ensure_store()
        self._store.update_company_context(section, content)
        return {"success": True, "section": section}

    # ------------------------------------------------------------------
    # Manage Actions
    # ------------------------------------------------------------------

    async def _promote(self, term: str, **kwargs) -> Dict:
        """Move an item to the hot cache."""
        self._ensure_store()
        promoted = self._store.promote(term)
        return {"success": True, "promoted": promoted}

    async def _demote(self, term: str, **kwargs) -> Dict:
        """Remove an item from the hot cache (keep in deep storage)."""
        self._ensure_store()
        demoted = self._store.demote(term)
        return {"success": True, "demoted": demoted}

    async def _search_memory(self, query: str, **kwargs) -> Dict:
        """Search across all memory tiers."""
        self._ensure_store()
        results = self._store.search(query)
        return {"results": results, "count": len(results)}

    async def _export_memory(self, **kwargs) -> Dict:
        """Export full memory as structured data."""
        self._ensure_store()
        return self._store.export_all()

    # ------------------------------------------------------------------
    # Bootstrap Actions
    # ------------------------------------------------------------------

    async def _initialize_memory(self, workspace_root: str = "", **kwargs) -> Dict:
        """Create directory structure and templates if missing."""
        if workspace_root:
            from ii_skills.shared.memory_tiers import TieredMemoryStore
            self._store = TieredMemoryStore(workspace_root=workspace_root)
            self._initialized = True

        self._ensure_store()
        created = self._store.initialize()
        return {"success": True, "created": created}

    async def _get_hot_cache(self, **kwargs) -> Dict:
        """Return current hot cache content as markdown."""
        self._ensure_store()
        content = self._store.get_hot_cache()
        return {"content": content}

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _sync_to_memory_service(self, key: str, content: Dict, memory_type: str = "fact") -> None:
        """Optionally sync to the existing MemoryService for cross-skill access.

        Fails silently if MemoryService is not available or not configured.
        """
        try:
            from ii_skills.shared.memory import MemoryService, MemoryType
            user_id = self.config.get("user_id", "default")
            memory = MemoryService(user_id=user_id, skill_name="memory")
            mt = getattr(MemoryType, memory_type.upper(), MemoryType.FACT)
            await memory.remember(key=key, content=content, memory_type=mt)
        except Exception:
            # MemoryService sync is best-effort — don't break the skill
            logger.debug("MemoryService sync skipped (not configured or unavailable)")


def get_memory_skill(config: Optional[Dict] = None) -> MemoryManagementSkill:
    """Get an instance of the Memory Management skill."""
    skill = MemoryManagementSkill(config)
    skill.initialize()
    return skill
