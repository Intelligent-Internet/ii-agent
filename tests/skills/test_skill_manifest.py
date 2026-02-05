"""
Unit tests for skill_manifest.py — SkillManifest, ActionSchema, lifecycle types.
"""

import pytest
from datetime import datetime, timezone

from ii_skills.shared.skill_manifest import (
    RiskLevel,
    PermissionScope,
    SkillState,
    HealthStatus,
    ActionSchema,
    HealthReport,
    SkillStatus,
    SkillManifest,
)


# ---------------------------------------------------------------------------
# ActionSchema
# ---------------------------------------------------------------------------

class TestActionSchema:

    def test_from_capability_string(self):
        schema = ActionSchema.from_capability_string("quick_lbo_analysis")
        assert schema.name == "quick_lbo_analysis"
        assert schema.description == "Execute 'quick_lbo_analysis' action"
        assert schema.risk_level == RiskLevel.READ_ONLY
        assert schema.input_schema["type"] == "object"
        assert schema.required_permissions == []

    def test_to_dict(self):
        schema = ActionSchema(
            name="delete_deal",
            description="Delete a deal permanently",
            risk_level=RiskLevel.DESTRUCTIVE,
            required_permissions=[PermissionScope.DATABASE, PermissionScope.STORAGE],
            tags=["admin"],
        )
        d = schema.to_dict()
        assert d["name"] == "delete_deal"
        assert d["risk_level"] == "destructive"
        assert d["required_permissions"] == ["database", "storage"]
        assert d["tags"] == ["admin"]

    def test_defaults(self):
        schema = ActionSchema(name="test", description="test action")
        assert schema.risk_level == RiskLevel.READ_ONLY
        assert schema.input_schema == {}
        assert schema.output_schema == {}
        assert schema.examples == []
        assert schema.tags == []

    def test_rich_input_schema(self):
        schema = ActionSchema(
            name="build_model",
            description="Build an LBO model",
            input_schema={
                "type": "object",
                "properties": {
                    "ebitda": {"type": "number", "description": "EBITDA in $M"},
                    "entry_multiple": {"type": "number", "description": "Entry EV/EBITDA"},
                },
                "required": ["ebitda"],
            },
        )
        assert "ebitda" in schema.input_schema["properties"]
        assert schema.input_schema["required"] == ["ebitda"]


# ---------------------------------------------------------------------------
# HealthReport
# ---------------------------------------------------------------------------

class TestHealthReport:

    def test_healthy(self):
        report = HealthReport(status=HealthStatus.HEALTHY, message="All good")
        assert report.status == HealthStatus.HEALTHY
        d = report.to_dict()
        assert d["status"] == "healthy"
        assert d["message"] == "All good"
        assert "checked_at" in d

    def test_unhealthy_with_details(self):
        report = HealthReport(
            status=HealthStatus.UNHEALTHY,
            message="Templates missing",
            details={"missing": ["ref_template.xlsx"]},
        )
        d = report.to_dict()
        assert d["status"] == "unhealthy"
        assert d["details"]["missing"] == ["ref_template.xlsx"]


# ---------------------------------------------------------------------------
# SkillStatus
# ---------------------------------------------------------------------------

class TestSkillStatus:

    def test_to_dict(self):
        health = HealthReport(status=HealthStatus.HEALTHY)
        status = SkillStatus(
            state=SkillState.ACTIVE,
            health=health,
            uptime_seconds=120.5,
            action_count=5,
            last_action="quick_lbo_analysis",
        )
        d = status.to_dict()
        assert d["state"] == "active"
        assert d["health"]["status"] == "healthy"
        assert d["uptime_seconds"] == 120.5
        assert d["action_count"] == 5


# ---------------------------------------------------------------------------
# SkillManifest
# ---------------------------------------------------------------------------

class TestSkillManifest:

    def _make_manifest(self):
        return SkillManifest(
            name="test_skill",
            version="1.0.0",
            description="A test skill",
            actions={
                "read_data": ActionSchema(
                    name="read_data",
                    description="Read data from source",
                    risk_level=RiskLevel.READ_ONLY,
                ),
                "write_file": ActionSchema(
                    name="write_file",
                    description="Write output file",
                    risk_level=RiskLevel.WRITE,
                    required_permissions=[PermissionScope.FILESYSTEM],
                ),
                "delete_all": ActionSchema(
                    name="delete_all",
                    description="Delete all records",
                    risk_level=RiskLevel.DESTRUCTIVE,
                    required_permissions=[PermissionScope.DATABASE],
                ),
            },
            resource_requirements=[PermissionScope.NETWORK],
        )

    def test_get_action(self):
        m = self._make_manifest()
        action = m.get_action("read_data")
        assert action is not None
        assert action.risk_level == RiskLevel.READ_ONLY

        assert m.get_action("nonexistent") is None

    def test_get_action_names(self):
        m = self._make_manifest()
        names = m.get_action_names()
        assert names == ["delete_all", "read_data", "write_file"]

    def test_get_destructive_actions(self):
        m = self._make_manifest()
        assert m.get_destructive_actions() == ["delete_all"]

    def test_get_write_actions(self):
        m = self._make_manifest()
        assert m.get_write_actions() == ["write_file"]

    def test_get_all_permissions(self):
        m = self._make_manifest()
        perms = m.get_all_permissions()
        perm_values = [p.value for p in perms]
        assert "network" in perm_values
        assert "filesystem" in perm_values
        assert "database" in perm_values

    def test_to_dict(self):
        m = self._make_manifest()
        d = m.to_dict()
        assert d["name"] == "test_skill"
        assert d["version"] == "1.0.0"
        assert "read_data" in d["actions"]
        assert d["actions"]["delete_all"]["risk_level"] == "destructive"
        assert d["resource_requirements"] == ["network"]

    def test_build_action_docs(self):
        m = self._make_manifest()
        docs = m.build_action_docs()
        assert "read_data" in docs
        assert "[read_only]" in docs
        assert "[destructive]" in docs
        assert "[write]" in docs

    def test_build_action_docs_with_params(self):
        m = SkillManifest(
            name="test",
            version="1.0.0",
            description="test",
            actions={
                "analyze": ActionSchema(
                    name="analyze",
                    description="Run analysis",
                    input_schema={
                        "type": "object",
                        "properties": {
                            "ebitda": {"type": "number", "description": "EBITDA value"},
                        },
                        "required": ["ebitda"],
                    },
                ),
            },
        )
        docs = m.build_action_docs()
        assert "ebitda" in docs
        assert "(required)" in docs
        assert "number" in docs

    def test_build_action_docs_empty(self):
        m = SkillManifest(name="empty", version="0.0.0", description="empty")
        assert m.build_action_docs() == "No actions available."


# ---------------------------------------------------------------------------
# from_capabilities() auto-generation
# ---------------------------------------------------------------------------

class TestFromCapabilities:

    class MockSkill:
        name = "mock_skill"
        version = "1.2.3"
        description = "A mock skill"

        def get_capabilities(self):
            return ["action_a", "action_b", "action_c"]

    def test_auto_generation(self):
        skill = self.MockSkill()
        manifest = SkillManifest.from_capabilities(skill)

        assert manifest.name == "mock_skill"
        assert manifest.version == "1.2.3"
        assert manifest.description == "A mock skill"
        assert len(manifest.actions) == 3
        assert "action_a" in manifest.actions
        assert "action_b" in manifest.actions
        assert "action_c" in manifest.actions

        # All auto-generated actions should be READ_ONLY
        for action in manifest.actions.values():
            assert action.risk_level == RiskLevel.READ_ONLY
            assert action.input_schema["type"] == "object"

    def test_empty_capabilities(self):
        class EmptySkill:
            name = "empty"
            version = "0.0.0"
            description = "empty"
            def get_capabilities(self):
                return []

        manifest = SkillManifest.from_capabilities(EmptySkill())
        assert len(manifest.actions) == 0


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class TestEnums:

    def test_risk_level_values(self):
        assert RiskLevel.READ_ONLY.value == "read_only"
        assert RiskLevel.WRITE.value == "write"
        assert RiskLevel.DESTRUCTIVE.value == "destructive"

    def test_permission_scope_values(self):
        assert PermissionScope.NETWORK.value == "network"
        assert PermissionScope.CREDENTIALS.value == "credentials"
        assert PermissionScope.EXTERNAL_API.value == "external_api"

    def test_skill_state_values(self):
        assert SkillState.CREATED.value == "created"
        assert SkillState.ACTIVE.value == "active"
        assert SkillState.DEACTIVATED.value == "deactivated"

    def test_health_status_values(self):
        assert HealthStatus.HEALTHY.value == "healthy"
        assert HealthStatus.DEGRADED.value == "degraded"
        assert HealthStatus.UNKNOWN.value == "unknown"
