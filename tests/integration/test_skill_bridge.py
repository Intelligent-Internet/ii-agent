"""Integration tests for the skill bridge layer.

Tests that skills are properly discovered, wrapped as tools,
and can execute actions end-to-end.
"""

import json
import pytest


# ============================================================
# Skill Discovery
# ============================================================

class TestSkillDiscovery:
    """Test that skills are discovered and registered."""

    def test_skills_are_discovered(self):
        """Verify discover_skills() finds at least the IB toolkit."""
        from ii_skills import _SKILLS

        assert len(_SKILLS) > 0, "No skills were discovered"

    def test_ib_toolkit_is_registered(self):
        """Verify IB Toolkit is in the skill registry."""
        from ii_skills import _SKILLS

        assert "ib_toolkit" in _SKILLS, (
            f"ib_toolkit not found. Registered skills: {list(_SKILLS.keys())}"
        )

    def test_get_skill_returns_instance(self):
        """Verify get_skill() returns a working instance."""
        from ii_skills import get_skill

        skill = get_skill("ib_toolkit")
        assert skill is not None
        assert skill.name == "ib_toolkit"
        assert skill.version == "1.5.0"

    def test_list_skills_returns_metadata(self):
        """Verify list_skills() returns skill metadata."""
        from ii_skills import list_skills

        skills = list_skills()
        assert len(skills) > 0

        names = [s["name"] for s in skills]
        assert "ib_toolkit" in names


# ============================================================
# Bridge Wrapping
# ============================================================

class TestBridgeWrapping:
    """Test that SkillTool properly wraps BaseSkill."""

    def test_skill_tool_has_correct_name(self, skill_tool_ib):
        """SkillTool name should be 'skill_{skill_name}'."""
        assert skill_tool_ib.name == "skill_ib_toolkit"

    def test_skill_tool_has_input_schema(self, skill_tool_ib):
        """SkillTool should have a valid JSON schema."""
        schema = skill_tool_ib.input_schema
        assert schema["type"] == "object"
        assert "action" in schema["properties"]
        assert "params" in schema["properties"]
        assert "action" in schema["required"]

    def test_skill_tool_action_enum(self, skill_tool_ib):
        """SkillTool action should have enum constraint from capabilities."""
        schema = skill_tool_ib.input_schema
        action_enum = schema["properties"]["action"].get("enum", [])
        assert "quick_lbo_analysis" in action_enum
        assert "create_lbo_model" in action_enum

    def test_skill_tool_description_includes_actions(self, skill_tool_ib):
        """SkillTool description should list available actions."""
        assert "quick_lbo_analysis" in skill_tool_ib.description
        assert "create_lbo_model" in skill_tool_ib.description

    def test_get_skill_tools_returns_list(self, all_skill_tools):
        """get_skill_tools() should return a list of SkillTool instances."""
        assert isinstance(all_skill_tools, list)
        assert len(all_skill_tools) > 0

    def test_skill_tools_are_base_tool_compatible(self, all_skill_tools):
        """All skill tools should have BaseTool required attributes."""
        for tool in all_skill_tools:
            assert hasattr(tool, "name")
            assert hasattr(tool, "description")
            assert hasattr(tool, "input_schema")
            assert hasattr(tool, "execute")
            assert hasattr(tool, "read_only")


# ============================================================
# Skill Execution via Bridge
# ============================================================

class TestSkillExecution:
    """Test executing skill actions through the bridge."""

    @pytest.mark.asyncio
    async def test_quick_lbo_analysis(self, skill_tool_ib, sample_lbo_params):
        """Test LBO quick analysis through the bridge."""
        result = await skill_tool_ib.execute({
            "action": "quick_lbo_analysis",
            "params": sample_lbo_params,
        })

        assert result.is_error is not True
        data = json.loads(result.llm_content)
        assert data["success"] is True
        assert "moic" in data
        assert "irr" in data
        assert data["moic"] > 0
        assert data["irr"] > 0

    @pytest.mark.asyncio
    async def test_lbo_sensitivity(self, skill_tool_ib):
        """Test LBO sensitivity matrix through the bridge."""
        result = await skill_tool_ib.execute({
            "action": "lbo_sensitivity",
            "params": {
                "ebitda": 50.0,
                "entry_multiple": 8.0,
            },
        })

        assert result.is_error is not True
        data = json.loads(result.llm_content)
        assert data["success"] is True
        assert "entry_exit_sensitivity" in data

    @pytest.mark.asyncio
    async def test_capital_structure_analysis(
        self, skill_tool_ib, sample_capital_structure_params
    ):
        """Test capital structure analysis through the bridge."""
        result = await skill_tool_ib.execute({
            "action": "analyze_capital_structure",
            "params": sample_capital_structure_params,
        })

        assert result.is_error is not True
        data = json.loads(result.llm_content)
        assert data["success"] is True
        assert "max_debt_capacity" in data
        assert "recommended_structure" in data

    @pytest.mark.asyncio
    async def test_quality_of_earnings(self, skill_tool_ib, sample_qoe_params):
        """Test QoE analysis through the bridge."""
        result = await skill_tool_ib.execute({
            "action": "analyze_quality_of_earnings",
            "params": sample_qoe_params,
        })

        assert result.is_error is not True
        data = json.loads(result.llm_content)
        assert data["success"] is True
        assert "adjusted_ebitda" in data
        assert "report" in data

    @pytest.mark.asyncio
    async def test_create_lbo_model_excel(self, skill_tool_ib, test_output_dir):
        """Test Excel LBO model generation through the bridge."""
        result = await skill_tool_ib.execute({
            "action": "create_lbo_model",
            "params": {
                "company_name": "Test Corp",
                "entry_multiple": 8.0,
                "exit_multiple": 9.0,
                "hold_period": 5,
            },
        })

        assert result.is_error is not True
        data = json.loads(result.llm_content)
        assert data["success"] is True
        assert "output_path" in data
        # Verify file exists
        from pathlib import Path
        assert Path(data["output_path"]).exists()

    @pytest.mark.asyncio
    async def test_list_slide_modules(self, skill_tool_ib):
        """Test listing available slide modules."""
        result = await skill_tool_ib.execute({
            "action": "list_slide_modules",
            "params": {},
        })

        assert result.is_error is not True
        data = json.loads(result.llm_content)
        assert data["success"] is True
        assert "modules" in data


# ============================================================
# Error Handling
# ============================================================

class TestErrorHandling:
    """Test error handling in the bridge layer."""

    @pytest.mark.asyncio
    async def test_missing_action(self, skill_tool_ib):
        """Missing action should return error."""
        result = await skill_tool_ib.execute({"params": {}})
        assert result.is_error is True
        assert "action" in result.llm_content.lower()

    @pytest.mark.asyncio
    async def test_unknown_action(self, skill_tool_ib):
        """Unknown action should return error."""
        result = await skill_tool_ib.execute({
            "action": "nonexistent_action",
            "params": {},
        })
        assert result.is_error is True
        assert "Unknown action" in result.llm_content

    @pytest.mark.asyncio
    async def test_invalid_params(self, skill_tool_ib):
        """Invalid params should be handled gracefully."""
        result = await skill_tool_ib.execute({
            "action": "quick_lbo_analysis",
            "params": {"ebitda": "not_a_number"},
        })
        # Should return error, not crash
        assert result.is_error is True


# ============================================================
# Registry Functions
# ============================================================

class TestRegistryFunctions:
    """Test skill registry helper functions."""

    def test_list_available_skills(self):
        """list_available_skills() should return detailed skill info."""
        from ii_skills.bridge import list_available_skills

        skills = list_available_skills()
        assert len(skills) > 0

        ib = next((s for s in skills if s["name"] == "ib_toolkit"), None)
        assert ib is not None
        assert "capabilities" in ib
        assert "capability_count" in ib
        assert ib["capability_count"] > 0

    def test_get_skill_tool_specific(self):
        """get_skill_tool() should return a single skill tool."""
        from ii_skills.bridge import get_skill_tool

        tool = get_skill_tool("ib_toolkit")
        assert tool is not None
        assert tool.name == "skill_ib_toolkit"

    def test_get_skill_tool_nonexistent(self):
        """get_skill_tool() should return None for unknown skill."""
        from ii_skills.bridge import get_skill_tool

        tool = get_skill_tool("nonexistent_skill")
        assert tool is None

    def test_get_skill_tools_with_include_filter(self):
        """get_skill_tools(include=[...]) should filter results."""
        from ii_skills.bridge import get_skill_tools

        tools = get_skill_tools(include=["ib_toolkit"])
        names = [t.name for t in tools]
        assert "skill_ib_toolkit" in names
        # Should not include other skills
        assert all(n == "skill_ib_toolkit" for n in names)

    def test_get_skill_tools_with_exclude_filter(self):
        """get_skill_tools(exclude=[...]) should filter results."""
        from ii_skills.bridge import get_skill_tools

        tools = get_skill_tools(exclude=["ib_toolkit"])
        names = [t.name for t in tools]
        assert "skill_ib_toolkit" not in names
