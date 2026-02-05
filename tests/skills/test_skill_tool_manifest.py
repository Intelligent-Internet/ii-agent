"""
Integration tests for SkillTool + SkillManifest + Workspace.

Tests that:
- SkillTool resolves manifests (auto-generated and explicit)
- Enriched descriptions include per-action parameter docs
- should_confirm_execute() gates DESTRUCTIVE actions
- Param validation catches missing required fields and type errors
- Workspace integration creates artifacts and manifests
- Action tracking updates skill state
- Backward compatibility with legacy skills
"""

import json
import pytest
import asyncio
from typing import Dict, List, Optional

from ii_skills import BaseSkill
from ii_skills.bridge.skill_tool import SkillTool
from ii_skills.shared.skill_manifest import (
    SkillManifest,
    ActionSchema,
    RiskLevel,
    PermissionScope,
)
from ii_skills.shared.workspace import WorkspaceManager


# ---------------------------------------------------------------------------
# Test Skills
# ---------------------------------------------------------------------------

class LegacySkill(BaseSkill):
    """A legacy skill with only get_capabilities() — no manifest override."""
    name = "legacy_skill"
    version = "1.0.0"
    description = "Legacy skill for testing"

    def get_capabilities(self) -> List[str]:
        return ["search", "analyze", "export"]

    def execute(self, action: str, **kwargs) -> Dict:
        return {"action": action, "status": "done", "params": kwargs}


class ManifestSkill(BaseSkill):
    """A skill with a rich typed manifest."""
    name = "manifest_skill"
    version = "2.0.0"
    description = "Manifest-aware skill for testing"

    def get_capabilities(self) -> List[str]:
        return ["read_data", "write_file", "delete_all"]

    def get_manifest(self) -> SkillManifest:
        return SkillManifest(
            name=self.name,
            version=self.version,
            description=self.description,
            actions={
                "read_data": ActionSchema(
                    name="read_data",
                    description="Read data from source",
                    input_schema={
                        "type": "object",
                        "properties": {
                            "source": {"type": "string", "description": "Data source"},
                            "limit": {"type": "integer", "description": "Max records"},
                        },
                        "required": ["source"],
                    },
                    risk_level=RiskLevel.READ_ONLY,
                ),
                "write_file": ActionSchema(
                    name="write_file",
                    description="Write an output file",
                    input_schema={
                        "type": "object",
                        "properties": {
                            "filename": {"type": "string", "description": "Output filename"},
                            "format": {"type": "string", "description": "File format"},
                        },
                        "required": ["filename"],
                    },
                    risk_level=RiskLevel.WRITE,
                    required_permissions=[PermissionScope.FILESYSTEM],
                ),
                "delete_all": ActionSchema(
                    name="delete_all",
                    description="Delete all records permanently",
                    risk_level=RiskLevel.DESTRUCTIVE,
                    required_permissions=[PermissionScope.DATABASE],
                ),
            },
        )

    def execute(self, action: str, **kwargs) -> Dict:
        # Accept and ignore _workspace kwarg via **kwargs
        return {"action": action, "status": "done", "params": {
            k: v for k, v in kwargs.items() if not k.startswith("_")
        }}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def legacy_skill():
    skill = LegacySkill()
    skill.initialize()
    return skill


@pytest.fixture
def manifest_skill():
    skill = ManifestSkill()
    skill.initialize()
    return skill


@pytest.fixture
def legacy_tool(legacy_skill):
    return SkillTool(legacy_skill)


@pytest.fixture
def manifest_tool(manifest_skill):
    return SkillTool(manifest_skill)


# ---------------------------------------------------------------------------
# Manifest Resolution
# ---------------------------------------------------------------------------

class TestManifestResolution:

    def test_legacy_skill_auto_generates_manifest(self, legacy_tool):
        manifest = legacy_tool._manifest
        assert manifest.name == "legacy_skill"
        assert len(manifest.actions) == 3
        assert "search" in manifest.actions
        assert "analyze" in manifest.actions
        assert "export" in manifest.actions

    def test_manifest_skill_uses_explicit_manifest(self, manifest_tool):
        manifest = manifest_tool._manifest
        assert manifest.name == "manifest_skill"
        assert len(manifest.actions) == 3
        assert manifest.get_action("read_data").risk_level == RiskLevel.READ_ONLY
        assert manifest.get_action("write_file").risk_level == RiskLevel.WRITE
        assert manifest.get_action("delete_all").risk_level == RiskLevel.DESTRUCTIVE


# ---------------------------------------------------------------------------
# Enriched Description
# ---------------------------------------------------------------------------

class TestEnrichedDescription:

    def test_legacy_description_has_actions(self, legacy_tool):
        desc = legacy_tool.description
        assert "analyze" in desc
        assert "export" in desc
        assert "search" in desc

    def test_manifest_description_has_risk_levels(self, manifest_tool):
        desc = manifest_tool.description
        assert "[read_only]" in desc
        assert "[write]" in desc
        assert "[destructive]" in desc

    def test_manifest_description_has_param_docs(self, manifest_tool):
        desc = manifest_tool.description
        assert "source" in desc
        assert "filename" in desc

    def test_input_schema_has_enum(self, manifest_tool):
        schema = manifest_tool.input_schema
        action_enum = schema["properties"]["action"]["enum"]
        assert "read_data" in action_enum
        assert "write_file" in action_enum
        assert "delete_all" in action_enum

    def test_input_schema_params_desc(self, manifest_tool):
        schema = manifest_tool.input_schema
        params_desc = schema["properties"]["params"]["description"]
        assert "read_data" in params_desc
        assert "source" in params_desc


# ---------------------------------------------------------------------------
# should_confirm_execute
# ---------------------------------------------------------------------------

class TestConfirmation:

    def test_read_only_no_confirm(self, manifest_tool):
        assert manifest_tool.should_confirm_execute({"action": "read_data"}) is False

    def test_write_no_confirm(self, manifest_tool):
        assert manifest_tool.should_confirm_execute({"action": "write_file"}) is False

    def test_destructive_requires_confirm(self, manifest_tool):
        assert manifest_tool.should_confirm_execute({"action": "delete_all"}) is True

    def test_unknown_action_no_confirm(self, manifest_tool):
        assert manifest_tool.should_confirm_execute({"action": "unknown"}) is False

    def test_legacy_no_confirm(self, legacy_tool):
        # All auto-generated actions are READ_ONLY
        assert legacy_tool.should_confirm_execute({"action": "search"}) is False


# ---------------------------------------------------------------------------
# Param Validation
# ---------------------------------------------------------------------------

class TestParamValidation:

    def test_valid_params(self, manifest_tool):
        error = manifest_tool._validate_params("read_data", {"source": "db"})
        assert error is None

    def test_missing_required(self, manifest_tool):
        error = manifest_tool._validate_params("read_data", {})
        assert error is not None
        assert "source" in error

    def test_wrong_type(self, manifest_tool):
        error = manifest_tool._validate_params(
            "read_data", {"source": "db", "limit": "not_a_number"}
        )
        assert error is not None
        assert "limit" in error
        assert "integer" in error

    def test_extra_params_ok(self, manifest_tool):
        error = manifest_tool._validate_params(
            "read_data", {"source": "db", "extra_field": True}
        )
        assert error is None

    def test_no_schema_passes(self, manifest_tool):
        # delete_all has no input_schema properties
        error = manifest_tool._validate_params("delete_all", {"anything": True})
        assert error is None

    def test_legacy_no_validation(self, legacy_tool):
        # Auto-generated schemas have no properties to validate
        error = legacy_tool._validate_params("search", {"anything": True})
        assert error is None


# ---------------------------------------------------------------------------
# Execute
# ---------------------------------------------------------------------------

class TestExecute:

    @pytest.mark.asyncio
    async def test_execute_success(self, manifest_tool):
        result = await manifest_tool.execute({
            "action": "read_data",
            "params": {"source": "database"},
        })
        assert result.is_error is None or result.is_error is False
        data = json.loads(result.llm_content)
        assert data["action"] == "read_data"
        assert data["params"]["source"] == "database"

    @pytest.mark.asyncio
    async def test_execute_missing_action(self, manifest_tool):
        result = await manifest_tool.execute({"params": {}})
        assert result.is_error is True
        assert "action" in result.llm_content.lower()

    @pytest.mark.asyncio
    async def test_execute_unknown_action(self, manifest_tool):
        result = await manifest_tool.execute({"action": "nonexistent"})
        assert result.is_error is True
        assert "nonexistent" in result.llm_content

    @pytest.mark.asyncio
    async def test_execute_validation_failure(self, manifest_tool):
        result = await manifest_tool.execute({
            "action": "read_data",
            "params": {},  # Missing required 'source'
        })
        assert result.is_error is True
        assert "source" in result.llm_content

    @pytest.mark.asyncio
    async def test_execute_legacy_skill(self, legacy_tool):
        result = await legacy_tool.execute({
            "action": "search",
            "params": {"query": "test"},
        })
        assert result.is_error is None or result.is_error is False
        data = json.loads(result.llm_content)
        assert data["action"] == "search"


# ---------------------------------------------------------------------------
# Action Tracking
# ---------------------------------------------------------------------------

class TestActionTracking:

    @pytest.mark.asyncio
    async def test_action_count_increments(self, manifest_tool):
        skill = manifest_tool._skill
        assert skill._action_count == 0

        await manifest_tool.execute({
            "action": "read_data",
            "params": {"source": "db"},
        })
        assert skill._action_count == 1

        await manifest_tool.execute({
            "action": "read_data",
            "params": {"source": "api"},
        })
        assert skill._action_count == 2

    @pytest.mark.asyncio
    async def test_last_action_tracked(self, manifest_tool):
        skill = manifest_tool._skill
        assert skill._last_action is None

        await manifest_tool.execute({
            "action": "write_file",
            "params": {"filename": "test.xlsx"},
        })
        assert skill._last_action == "write_file"
        assert skill._last_action_at is not None


# ---------------------------------------------------------------------------
# Workspace Integration
# ---------------------------------------------------------------------------

class TestWorkspaceIntegration:

    @pytest.mark.asyncio
    async def test_execute_with_workspace(self, manifest_skill, tmp_path):
        manager = WorkspaceManager(root_dir=tmp_path / "workspaces")
        tool = SkillTool(manifest_skill, workspace_manager=manager)

        result = await tool.execute({
            "action": "read_data",
            "params": {"source": "database"},
        })

        assert result.is_error is None or result.is_error is False
        data = json.loads(result.llm_content)
        assert "_workspace_id" in data
        assert "_workspace_path" in data

    @pytest.mark.asyncio
    async def test_execute_without_workspace(self, manifest_skill):
        tool = SkillTool(manifest_skill)  # No workspace_manager

        result = await tool.execute({
            "action": "read_data",
            "params": {"source": "database"},
        })

        data = json.loads(result.llm_content)
        assert "_workspace_id" not in data


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------

class TestLifecycle:

    def test_base_skill_lifecycle(self):
        skill = LegacySkill()
        assert skill._state == "created"

        skill.initialize()
        skill.on_activate()
        assert skill._state == "active"
        assert skill._activated_at is not None

        status = skill.get_status()
        assert status.state.value == "active"
        assert status.health.status.value == "healthy"

        skill.on_deactivate()
        assert skill._state == "deactivated"

    def test_health_check_uninitialized(self):
        skill = LegacySkill()
        health = skill.health_check()
        assert health.status.value == "unhealthy"

    def test_health_check_initialized(self):
        skill = LegacySkill()
        skill.initialize()
        health = skill.health_check()
        assert health.status.value == "healthy"

    def test_manifest_auto_generation(self):
        skill = LegacySkill()
        manifest = skill.get_manifest()
        assert manifest.name == "legacy_skill"
        assert len(manifest.actions) == 3
