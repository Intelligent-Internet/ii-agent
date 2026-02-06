"""Tests for the Memory Management skill and TieredMemoryStore."""

import json
import os
import tempfile
from pathlib import Path

import pytest

from ii_skills.shared.memory_tiers import TieredMemoryStore


@pytest.fixture
def tmp_workspace(tmp_path):
    """Provide a temporary workspace directory."""
    return str(tmp_path)


@pytest.fixture
def store(tmp_workspace):
    """Provide an initialized TieredMemoryStore."""
    s = TieredMemoryStore(workspace_root=tmp_workspace)
    s.initialize()
    return s


# ------------------------------------------------------------------
# Initialization
# ------------------------------------------------------------------


class TestInitialization:
    def test_initialize_creates_directory_structure(self, tmp_workspace):
        store = TieredMemoryStore(workspace_root=tmp_workspace)
        created = store.initialize()
        assert len(created) > 0
        assert store.memory_dir.exists()
        assert store.people_dir.exists()
        assert store.projects_dir.exists()
        assert store.context_dir.exists()
        assert store.hot_cache_path.exists()
        assert store.glossary_path.exists()

    def test_initialize_idempotent(self, store):
        """Calling initialize twice should not fail or duplicate."""
        created = store.initialize()
        assert created == []  # Already exists, nothing new created


# ------------------------------------------------------------------
# Lookup
# ------------------------------------------------------------------


class TestLookup:
    def test_lookup_hot_cache_first(self, store):
        """Items in hot cache should be found before deep storage."""
        # Add person to both hot cache and deep
        store.add_person("todd", {"full_name": "Todd Martinez", "role": "Finance Lead"})
        store.promote("todd")

        result = store.lookup("todd")
        assert result is not None
        assert result["found"] is True
        assert result["tier"] == "hot_cache"
        assert result["type"] == "person"

    def test_lookup_falls_through_to_glossary(self, store):
        """Terms not in hot cache should be found in glossary."""
        store.add_term("PSR", "Pipeline Status Report", "Weekly sales doc")

        result = store.lookup("psr")
        assert result is not None
        assert result["found"] is True
        assert result["tier"] == "glossary"
        assert result["type"] == "term"
        assert result["data"]["meaning"] == "Pipeline Status Report"

    def test_lookup_falls_through_to_profiles(self, store):
        """People not in hot cache or glossary should be found in deep profiles."""
        store.add_person("sarah", {"full_name": "Sarah Chen", "role": "VP Engineering"})

        result = store.lookup("sarah")
        assert result is not None
        assert result["found"] is True
        assert result["tier"] == "deep"
        assert result["type"] == "person"

    def test_lookup_returns_none_when_not_found(self, store):
        """Unknown terms should return None."""
        result = store.lookup("nonexistent")
        assert result is None

    def test_lookup_case_insensitive(self, store):
        """Lookups should be case-insensitive."""
        store.add_term("PSR", "Pipeline Status Report")

        assert store.lookup("PSR") is not None
        assert store.lookup("psr") is not None
        assert store.lookup("Psr") is not None


# ------------------------------------------------------------------
# Write Operations
# ------------------------------------------------------------------


class TestWriteOperations:
    def test_remember_person_creates_profile(self, store):
        """Adding a person should create a JSON file in people/."""
        store.add_person("todd", {"full_name": "Todd Martinez", "role": "Finance Lead"})

        profile_path = store.people_dir / "todd.json"
        assert profile_path.exists()

        data = json.loads(profile_path.read_text(encoding="utf-8"))
        assert data["full_name"] == "Todd Martinez"
        assert data["role"] == "Finance Lead"
        assert data["short_name"] == "todd"

    def test_remember_term_adds_to_glossary(self, store):
        """Adding a term should appear in the glossary file."""
        store.add_term("PSR", "Pipeline Status Report", "Weekly sales doc")

        glossary = store._read_glossary()
        assert "psr" in glossary
        assert glossary["psr"]["meaning"] == "Pipeline Status Report"

    def test_add_project_creates_profile(self, store):
        """Adding a project should create a JSON file in projects/."""
        store.add_project("Phoenix", {"description": "DB migration", "status": "active"})

        profile_path = store.projects_dir / "phoenix.json"
        assert profile_path.exists()

        data = json.loads(profile_path.read_text(encoding="utf-8"))
        assert data["name"] == "Phoenix"
        assert data["description"] == "DB migration"

    def test_add_preference(self, store):
        """Adding a preference should update the hot cache."""
        store.add_preference("meeting_length", "25-min with buffers")

        hot = store._read_hot_cache()
        prefs = hot.get("preferences", [])
        assert any(p["key"] == "meeting_length" for p in prefs)

    def test_update_preference_replaces(self, store):
        """Updating an existing preference should replace, not duplicate."""
        store.add_preference("meeting_length", "25-min")
        store.add_preference("meeting_length", "30-min")

        hot = store._read_hot_cache()
        prefs = [p for p in hot.get("preferences", []) if p["key"] == "meeting_length"]
        assert len(prefs) == 1
        assert prefs[0]["value"] == "30-min"

    def test_update_company_context(self, store):
        """Updating company context should persist to file."""
        store.update_company_context("tools", "Slack for comms, Asana for tasks")

        ctx_path = store.context_dir / "company.json"
        assert ctx_path.exists()
        data = json.loads(ctx_path.read_text(encoding="utf-8"))
        assert data["tools"] == "Slack for comms, Asana for tasks"


# ------------------------------------------------------------------
# Promotion / Demotion
# ------------------------------------------------------------------


class TestPromotionDemotion:
    def test_promote_moves_to_hot_cache(self, store):
        """Promoting a deep item should add it to the hot cache."""
        store.add_person("todd", {"full_name": "Todd Martinez", "role": "Finance Lead"})

        # Initially in deep storage
        result = store.lookup("todd")
        assert result["tier"] == "deep"

        # Promote to hot cache
        assert store.promote("todd") is True

        result = store.lookup("todd")
        assert result["tier"] == "hot_cache"

    def test_demote_removes_from_hot_cache(self, store):
        """Demoting should remove from hot cache but keep in deep storage."""
        store.add_person("todd", {"full_name": "Todd Martinez", "role": "Finance Lead"})
        store.promote("todd")

        # Verify in hot cache
        result = store.lookup("todd")
        assert result["tier"] == "hot_cache"

        # Demote
        assert store.demote("todd") is True

        # Should now resolve from deep
        result = store.lookup("todd")
        assert result is not None
        assert result["tier"] == "deep"

    def test_promote_nonexistent_returns_false(self, store):
        """Promoting a nonexistent term should return False."""
        assert store.promote("nonexistent") is False

    def test_demote_nonexistent_returns_false(self, store):
        """Demoting a term not in hot cache should return False."""
        assert store.demote("nonexistent") is False

    def test_promote_already_hot_is_noop(self, store):
        """Promoting something already in hot cache returns True."""
        store.add_person("todd", {"full_name": "Todd", "role": "Lead"})
        store.promote("todd")
        assert store.promote("todd") is True

    def test_demote_ensures_deep_copy(self, store):
        """Demoting a term-only-in-hot-cache should create deep copy first."""
        # Manually add to hot cache without deep copy
        hot = store._read_hot_cache()
        hot["terms"]["xyz"] = {"term": "XYZ", "meaning": "Test term"}
        store._write_hot_cache(hot)

        store.demote("xyz")

        # Should now be in glossary
        glossary = store._read_glossary()
        assert "xyz" in glossary


# ------------------------------------------------------------------
# Search
# ------------------------------------------------------------------


class TestSearch:
    def test_search_across_all_tiers(self, store):
        """Search should find results across hot cache, glossary, and deep storage."""
        store.add_person("todd", {"full_name": "Todd Martinez", "role": "Finance Lead"})
        store.add_term("PSR", "Pipeline Status Report", "Sales")
        store.add_project("Phoenix", {"description": "DB migration"})

        results = store.search("finance")
        assert len(results) >= 1
        assert any(r["key"] == "todd" for r in results)

    def test_search_returns_empty_for_no_match(self, store):
        """Search with no matches should return empty list."""
        results = store.search("zzzznonexistent")
        assert results == []


# ------------------------------------------------------------------
# Export
# ------------------------------------------------------------------


class TestExport:
    def test_export_full_memory(self, store):
        """Export should include all tiers."""
        store.add_person("todd", {"full_name": "Todd Martinez", "role": "Finance Lead"})
        store.add_term("PSR", "Pipeline Status Report")
        store.add_project("Phoenix", {"description": "DB migration"})

        export = store.export_all()
        assert "hot_cache" in export
        assert "glossary" in export
        assert "people" in export
        assert "projects" in export
        assert "todd" in export["people"]
        assert "phoenix" in export["projects"]


# ------------------------------------------------------------------
# Hot Cache Rendering
# ------------------------------------------------------------------


class TestHotCacheRendering:
    def test_get_hot_cache_returns_markdown(self, store):
        """Hot cache content should be valid markdown."""
        store.add_person("todd", {"full_name": "Todd Martinez", "role": "Finance Lead"})
        store.promote("todd")

        content = store.get_hot_cache()
        assert "# Memory — Hot Cache" in content
        assert "todd" in content.lower()

    def test_hot_cache_includes_all_sections(self, store):
        """Hot cache should render people, terms, projects, and preferences."""
        store.add_person("todd", {"full_name": "Todd", "role": "Lead"})
        store.promote("todd")
        store.add_term("PSR", "Pipeline Status Report")
        # Promote term manually
        hot = store._read_hot_cache()
        hot["terms"]["psr"] = {"term": "PSR", "meaning": "Pipeline Status Report"}
        hot["projects"]["phoenix"] = {"name": "Phoenix", "description": "DB migration"}
        store._write_hot_cache(hot)
        store.add_preference("comms", "Slack")

        content = store.get_hot_cache()
        assert "## People" in content
        assert "## Terms" in content
        assert "## Projects" in content
        assert "## Preferences" in content


# ------------------------------------------------------------------
# Skill Integration
# ------------------------------------------------------------------


class TestMemorySkill:
    """Test the MemoryManagementSkill class."""

    def test_skill_registers(self):
        """Memory skill should be discoverable."""
        from ii_skills import list_skills
        skills = list_skills()
        skill_names = [s["name"] for s in skills]
        assert "memory" in skill_names

    def test_skill_capabilities(self):
        """Skill should report all 14 capabilities."""
        from ii_skills import get_skill
        skill = get_skill("memory")
        caps = skill.get_capabilities()
        assert len(caps) == 14
        assert "lookup" in caps
        assert "remember_person" in caps
        assert "promote" in caps
        assert "initialize_memory" in caps

    def test_skill_execute_initialize(self, tmp_workspace):
        """Skill should create memory directory on initialize."""
        from ii_skills import get_skill
        skill = get_skill("memory", config={"workspace_root": tmp_workspace})
        skill.initialize()
        result = skill.execute("initialize_memory", workspace_root=tmp_workspace)
        assert result["success"] is True

    def test_skill_execute_remember_and_lookup(self, tmp_workspace):
        """Skill should support remember + lookup roundtrip."""
        from ii_skills import get_skill
        skill = get_skill("memory", config={"workspace_root": tmp_workspace})
        skill.initialize()
        skill.execute("initialize_memory", workspace_root=tmp_workspace)

        skill.execute("remember_term", term="PSR", meaning="Pipeline Status Report")
        result = skill.execute("lookup", term="psr")
        assert result["found"] is True
        assert result["data"]["meaning"] == "Pipeline Status Report"
