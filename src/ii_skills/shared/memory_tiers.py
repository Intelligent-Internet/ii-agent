"""
Two-tier memory system: hot cache (hot_cache.md) + deep storage (memory/ directory).

Hot cache: ~100 lines in memory/hot_cache.md — frequently accessed context.
Deep storage: memory/ directory with glossary.md, people/, projects/, context/ subdirs.

The hot cache is NOT injected into CLAUDE.md (fork safety). It lives in its own
file that the productivity orchestrator can read on demand.

Usage:
    store = TieredMemoryStore(workspace_root="/path/to/workspace")
    store.initialize()
    store.add_person("todd", {"full_name": "Todd Martinez", "role": "Finance Lead"})
    result = store.lookup("todd")  # Tiered: hot cache -> glossary -> people/ -> not found
    store.promote("todd")  # Move from deep storage to hot cache
    store.demote("todd")   # Remove from hot cache (keep in deep)
"""

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class TieredMemoryStore:
    """Two-tier workplace memory: hot cache + deep file-based storage."""

    def __init__(self, workspace_root: str):
        self.workspace_root = Path(workspace_root)
        self.memory_dir = self.workspace_root / "memory"
        self.hot_cache_path = self.memory_dir / "hot_cache.md"
        self.glossary_path = self.memory_dir / "glossary.md"
        self.people_dir = self.memory_dir / "people"
        self.projects_dir = self.memory_dir / "projects"
        self.context_dir = self.memory_dir / "context"

    # ------------------------------------------------------------------
    # Initialization
    # ------------------------------------------------------------------

    def initialize(self) -> List[str]:
        """Create directory structure and seed files if missing.

        Returns list of created paths.
        """
        created: List[str] = []

        for d in [self.memory_dir, self.people_dir, self.projects_dir, self.context_dir]:
            if not d.exists():
                d.mkdir(parents=True, exist_ok=True)
                created.append(str(d))

        if not self.hot_cache_path.exists():
            self._write_hot_cache({"me": "", "people": {}, "terms": {}, "projects": {}, "preferences": []})
            created.append(str(self.hot_cache_path))

        if not self.glossary_path.exists():
            self.glossary_path.write_text(
                "# Glossary\n\n"
                "| Term | Meaning | Context |\n"
                "|------|---------|--------|\n",
                encoding="utf-8",
            )
            created.append(str(self.glossary_path))

        return created

    # ------------------------------------------------------------------
    # Tiered Lookup (core value)
    # ------------------------------------------------------------------

    def lookup(self, term: str) -> Optional[Dict[str, Any]]:
        """Look up a term across all tiers.

        Order: hot cache -> glossary -> people/ -> projects/ -> None
        """
        key = term.strip().lower()

        # Tier 1: Hot cache
        hot = self._read_hot_cache()
        if key in hot.get("people", {}):
            return {"found": True, "tier": "hot_cache", "type": "person", "data": hot["people"][key]}
        if key in hot.get("terms", {}):
            return {"found": True, "tier": "hot_cache", "type": "term", "data": hot["terms"][key]}
        if key in hot.get("projects", {}):
            return {"found": True, "tier": "hot_cache", "type": "project", "data": hot["projects"][key]}

        # Tier 2: Glossary
        glossary = self._read_glossary()
        if key in glossary:
            return {"found": True, "tier": "glossary", "type": "term", "data": glossary[key]}

        # Tier 3: Deep storage profiles
        person = self._read_profile("people", key)
        if person:
            return {"found": True, "tier": "deep", "type": "person", "data": person}

        project = self._read_profile("projects", key)
        if project:
            return {"found": True, "tier": "deep", "type": "project", "data": project}

        return None

    # ------------------------------------------------------------------
    # Write Operations
    # ------------------------------------------------------------------

    def add_person(self, short_name: str, profile: Dict[str, Any]) -> None:
        """Add or update a person profile in deep storage."""
        key = short_name.strip().lower()
        profile["short_name"] = key
        profile.setdefault("added_at", datetime.now(timezone.utc).isoformat())
        self._write_profile("people", key, profile)

    def add_term(self, term: str, meaning: str, context: str = "") -> None:
        """Add a term to the glossary."""
        glossary = self._read_glossary()
        key = term.strip().lower()
        glossary[key] = {"term": term, "meaning": meaning, "context": context}
        self._write_glossary(glossary)

    def add_project(self, name: str, details: Dict[str, Any]) -> None:
        """Add or update a project in deep storage."""
        key = name.strip().lower()
        details["name"] = name
        details.setdefault("added_at", datetime.now(timezone.utc).isoformat())
        self._write_profile("projects", key, details)

    def add_preference(self, key: str, value: str) -> None:
        """Add a preference to the hot cache."""
        hot = self._read_hot_cache()
        prefs = hot.get("preferences", [])
        # Update existing or append
        for i, p in enumerate(prefs):
            if p.get("key") == key:
                prefs[i] = {"key": key, "value": value}
                hot["preferences"] = prefs
                self._write_hot_cache(hot)
                return
        prefs.append({"key": key, "value": value})
        hot["preferences"] = prefs
        self._write_hot_cache(hot)

    def update_company_context(self, section: str, content: str) -> None:
        """Update a section in company context."""
        ctx_path = self.context_dir / "company.json"
        ctx: Dict[str, str] = {}
        if ctx_path.exists():
            try:
                ctx = json.loads(ctx_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                ctx = {}
        ctx[section] = content
        ctx_path.write_text(json.dumps(ctx, indent=2), encoding="utf-8")

    # ------------------------------------------------------------------
    # Promotion / Demotion
    # ------------------------------------------------------------------

    def promote(self, term: str) -> bool:
        """Move an item from deep storage to the hot cache."""
        key = term.strip().lower()
        result = self.lookup(key)
        if not result or not result["found"]:
            return False
        if result["tier"] == "hot_cache":
            return True  # Already in hot cache

        hot = self._read_hot_cache()
        item_type = result["type"]
        data = result["data"]

        if item_type == "person":
            hot.setdefault("people", {})[key] = data
        elif item_type == "term":
            hot.setdefault("terms", {})[key] = data
        elif item_type == "project":
            hot.setdefault("projects", {})[key] = data

        self._write_hot_cache(hot)
        return True

    def demote(self, term: str) -> bool:
        """Remove an item from the hot cache (keep in deep storage)."""
        key = term.strip().lower()
        hot = self._read_hot_cache()
        removed = False

        for section in ("people", "terms", "projects"):
            if key in hot.get(section, {}):
                # Ensure deep copy exists before removing from hot cache
                data = hot[section][key]
                if section == "people":
                    self._ensure_deep_copy("people", key, data)
                elif section == "terms":
                    # Ensure term is in glossary
                    glossary = self._read_glossary()
                    if key not in glossary:
                        glossary[key] = data
                        self._write_glossary(glossary)
                elif section == "projects":
                    self._ensure_deep_copy("projects", key, data)

                del hot[section][key]
                removed = True

        if removed:
            self._write_hot_cache(hot)
        return removed

    # ------------------------------------------------------------------
    # Bulk Operations
    # ------------------------------------------------------------------

    def get_hot_cache(self) -> str:
        """Return the hot cache formatted as markdown."""
        hot = self._read_hot_cache()
        return self._render_hot_cache_markdown(hot)

    def get_full_glossary(self) -> Dict[str, Any]:
        """Return the complete glossary."""
        return self._read_glossary()

    def search(self, query: str) -> List[Dict[str, Any]]:
        """Search across all memory tiers."""
        query_lower = query.lower()
        results: List[Dict[str, Any]] = []

        # Search hot cache
        hot = self._read_hot_cache()
        for section in ("people", "terms", "projects"):
            for key, data in hot.get(section, {}).items():
                if self._matches_query(query_lower, key, data):
                    results.append({"tier": "hot_cache", "type": section.rstrip("s"), "key": key, "data": data})

        # Search glossary
        for key, data in self._read_glossary().items():
            if self._matches_query(query_lower, key, data):
                if not any(r["key"] == key and r["type"] == "term" for r in results):
                    results.append({"tier": "glossary", "type": "term", "key": key, "data": data})

        # Search deep profiles
        for category in ("people", "projects"):
            category_dir = getattr(self, f"{category}_dir")
            if category_dir.exists():
                for f in category_dir.glob("*.json"):
                    key = f.stem
                    if any(r["key"] == key and r["type"] == category.rstrip("s") for r in results):
                        continue
                    try:
                        data = json.loads(f.read_text(encoding="utf-8"))
                        if self._matches_query(query_lower, key, data):
                            results.append({"tier": "deep", "type": category.rstrip("s"), "key": key, "data": data})
                    except (json.JSONDecodeError, OSError):
                        continue

        return results

    def export_all(self) -> Dict[str, Any]:
        """Export full memory as structured data."""
        result: Dict[str, Any] = {
            "hot_cache": self._read_hot_cache(),
            "glossary": self._read_glossary(),
            "people": {},
            "projects": {},
            "context": {},
        }

        if self.people_dir.exists():
            for f in self.people_dir.glob("*.json"):
                try:
                    result["people"][f.stem] = json.loads(f.read_text(encoding="utf-8"))
                except (json.JSONDecodeError, OSError):
                    continue

        if self.projects_dir.exists():
            for f in self.projects_dir.glob("*.json"):
                try:
                    result["projects"][f.stem] = json.loads(f.read_text(encoding="utf-8"))
                except (json.JSONDecodeError, OSError):
                    continue

        ctx_path = self.context_dir / "company.json"
        if ctx_path.exists():
            try:
                result["context"] = json.loads(ctx_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass

        return result

    # ------------------------------------------------------------------
    # File I/O Helpers
    # ------------------------------------------------------------------

    def _read_hot_cache(self) -> Dict[str, Any]:
        """Read hot cache from JSON sidecar (hot_cache.json)."""
        json_path = self.hot_cache_path.with_suffix(".json")
        if json_path.exists():
            try:
                return json.loads(json_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass
        return {"me": "", "people": {}, "terms": {}, "projects": {}, "preferences": []}

    def _write_hot_cache(self, data: Dict[str, Any]) -> None:
        """Write hot cache to both JSON sidecar and markdown."""
        json_path = self.hot_cache_path.with_suffix(".json")
        json_path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
        # Also render the markdown view
        self.hot_cache_path.write_text(self._render_hot_cache_markdown(data), encoding="utf-8")

    def _read_glossary(self) -> Dict[str, Any]:
        """Parse glossary.md into a dict of term -> {term, meaning, context}."""
        if not self.glossary_path.exists():
            return {}

        content = self.glossary_path.read_text(encoding="utf-8")
        glossary: Dict[str, Any] = {}
        # Parse markdown table rows: | Term | Meaning | Context |
        for line in content.splitlines():
            line = line.strip()
            if not line.startswith("|") or line.startswith("| Term") or line.startswith("|---"):
                continue
            parts = [p.strip() for p in line.split("|")]
            # parts: ['', 'Term', 'Meaning', 'Context', '']
            parts = [p for p in parts if p]
            if len(parts) >= 2:
                term = parts[0]
                meaning = parts[1]
                context = parts[2] if len(parts) >= 3 else ""
                glossary[term.lower()] = {"term": term, "meaning": meaning, "context": context}

        return glossary

    def _write_glossary(self, glossary: Dict[str, Any]) -> None:
        """Write glossary dict back to markdown table."""
        lines = [
            "# Glossary\n",
            "| Term | Meaning | Context |",
            "|------|---------|--------|",
        ]
        for _key, entry in sorted(glossary.items()):
            term = entry.get("term", _key)
            meaning = entry.get("meaning", "")
            context = entry.get("context", "")
            lines.append(f"| {term} | {meaning} | {context} |")

        self.glossary_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def _read_profile(self, category: str, name: str) -> Optional[Dict[str, Any]]:
        """Read a profile JSON from people/ or projects/."""
        category_dir = getattr(self, f"{category}_dir", None)
        if not category_dir:
            return None
        profile_path = category_dir / f"{name}.json"
        if not profile_path.exists():
            return None
        try:
            return json.loads(profile_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None

    def _write_profile(self, category: str, name: str, data: Dict[str, Any]) -> None:
        """Write a profile JSON to people/ or projects/."""
        category_dir = getattr(self, f"{category}_dir", None)
        if not category_dir:
            return
        category_dir.mkdir(parents=True, exist_ok=True)
        profile_path = category_dir / f"{name}.json"
        profile_path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")

    def _ensure_deep_copy(self, category: str, key: str, data: Dict[str, Any]) -> None:
        """Ensure a deep storage copy exists before removing from hot cache."""
        existing = self._read_profile(category, key)
        if not existing:
            self._write_profile(category, key, data)

    def _render_hot_cache_markdown(self, data: Dict[str, Any]) -> str:
        """Render hot cache data as readable markdown."""
        lines = ["# Memory — Hot Cache\n"]

        me = data.get("me", "")
        if me:
            lines.append(f"## Me\n{me}\n")

        people = data.get("people", {})
        if people:
            lines.append("## People")
            lines.append("| Who | Role |")
            lines.append("|-----|------|")
            for key, info in people.items():
                full_name = info.get("full_name", key)
                role = info.get("role", "")
                lines.append(f"| **{key}** | {full_name}, {role} |")
            lines.append("")

        terms = data.get("terms", {})
        if terms:
            lines.append("## Terms")
            lines.append("| Term | Meaning |")
            lines.append("|------|---------|")
            for key, info in terms.items():
                term_display = info.get("term", key)
                meaning = info.get("meaning", "")
                lines.append(f"| {term_display} | {meaning} |")
            lines.append("")

        projects = data.get("projects", {})
        if projects:
            lines.append("## Projects")
            lines.append("| Name | What |")
            lines.append("|------|------|")
            for key, info in projects.items():
                name_display = info.get("name", key)
                description = info.get("description", "")
                lines.append(f"| **{name_display}** | {description} |")
            lines.append("")

        preferences = data.get("preferences", [])
        if preferences:
            lines.append("## Preferences")
            for pref in preferences:
                lines.append(f"- {pref.get('key', '')}: {pref.get('value', '')}")
            lines.append("")

        return "\n".join(lines) + "\n"

    def _matches_query(self, query_lower: str, key: str, data: Any) -> bool:
        """Check if a query matches a key or any string value in data."""
        if query_lower in key:
            return True
        if isinstance(data, dict):
            for v in data.values():
                if isinstance(v, str) and query_lower in v.lower():
                    return True
        elif isinstance(data, str) and query_lower in data.lower():
            return True
        return False
