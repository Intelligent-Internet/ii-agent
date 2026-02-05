"""
Unit tests for workspace.py — WorkspaceManager, Workspace, artifacts, manifests.
"""

import json
import os
import tempfile
import pytest
from pathlib import Path

from ii_skills.shared.workspace import (
    WorkspaceManager,
    Workspace,
    WorkspaceManifest,
    ArtifactRecord,
    MANIFEST_SCHEMA_VERSION,
)


@pytest.fixture
def tmp_workspace_root(tmp_path):
    """Create a temporary workspace root directory."""
    return tmp_path / "workspaces"


@pytest.fixture
def manager(tmp_workspace_root):
    """Create a WorkspaceManager with a temp root."""
    return WorkspaceManager(root_dir=tmp_workspace_root)


# ---------------------------------------------------------------------------
# ArtifactRecord
# ---------------------------------------------------------------------------

class TestArtifactRecord:

    def test_to_dict(self):
        record = ArtifactRecord(
            path="outputs/test.xlsx",
            artifact_type="excel",
            size_bytes=12345,
            checksum_sha256="abc123",
        )
        d = record.to_dict()
        assert d["path"] == "outputs/test.xlsx"
        assert d["artifact_type"] == "excel"
        assert d["size_bytes"] == 12345
        assert "created_at" in d

    def test_defaults(self):
        record = ArtifactRecord(path="test.json", artifact_type="json")
        assert record.size_bytes == 0
        assert record.checksum_sha256 == ""
        assert record.metadata == {}


# ---------------------------------------------------------------------------
# WorkspaceManifest
# ---------------------------------------------------------------------------

class TestWorkspaceManifest:

    def test_defaults(self):
        m = WorkspaceManifest()
        assert m.schema_version == MANIFEST_SCHEMA_VERSION
        assert m.status == "running"
        assert m.run_id != ""
        assert m.inputs == {}
        assert m.outputs == []

    def test_to_dict(self):
        m = WorkspaceManifest(
            skill_name="ib_toolkit",
            action="quick_lbo",
            inputs={"ebitda": 50},
        )
        d = m.to_dict()
        assert d["skill_name"] == "ib_toolkit"
        assert d["action"] == "quick_lbo"
        assert d["inputs"]["ebitda"] == 50

    def test_to_json(self):
        m = WorkspaceManifest(skill_name="test")
        j = m.to_json()
        parsed = json.loads(j)
        assert parsed["skill_name"] == "test"
        assert parsed["schema_version"] == MANIFEST_SCHEMA_VERSION


# ---------------------------------------------------------------------------
# Workspace
# ---------------------------------------------------------------------------

class TestWorkspace:

    def test_creation_creates_directories(self, tmp_path):
        ws_dir = tmp_path / "test_workspace"
        manifest = WorkspaceManifest(skill_name="test", action="run")
        ws = Workspace(ws_dir, manifest)

        assert (ws_dir / "outputs").exists()
        assert (ws_dir / "inputs").exists()
        assert (ws_dir / "manifest.json").exists()
        assert (ws_dir / "events.jsonl").exists()

    def test_run_id(self, tmp_path):
        manifest = WorkspaceManifest(run_id="abcdef12-3456-7890-abcd-ef1234567890")
        ws = Workspace(tmp_path / "ws", manifest)
        assert ws.run_id == "abcdef12-3456-7890-abcd-ef1234567890"
        assert ws.short_run_id == "abcdef12"

    def test_get_output_path(self, tmp_path):
        manifest = WorkspaceManifest(
            run_id="a1b2c3d4-0000-0000-0000-000000000000",
            skill_name="ib_toolkit",
            action="quick_lbo",
        )
        ws = Workspace(tmp_path / "ws", manifest)
        path = ws.get_output_path("xlsx")

        assert path.suffix == ".xlsx"
        assert "ib_toolkit" in path.name
        assert "quick_lbo" in path.name
        assert "a1b2c3d4" in path.name
        assert path.parent == ws.outputs_dir

    def test_get_output_path_with_suffix(self, tmp_path):
        manifest = WorkspaceManifest(skill_name="test", action="run")
        ws = Workspace(tmp_path / "ws", manifest)
        path = ws.get_output_path("json", suffix="_summary")
        assert "_summary.json" in path.name

    def test_register_artifact(self, tmp_path):
        manifest = WorkspaceManifest(skill_name="test", action="run")
        ws = Workspace(tmp_path / "ws", manifest)

        # Create a test file
        test_file = ws.outputs_dir / "test_output.xlsx"
        test_file.write_bytes(b"fake excel content here")

        record = ws.register_artifact(test_file, artifact_type="excel")

        assert record.artifact_type == "excel"
        assert record.size_bytes > 0
        assert record.checksum_sha256 != ""
        assert len(ws.manifest.outputs) == 1

    def test_register_artifact_auto_type(self, tmp_path):
        manifest = WorkspaceManifest(skill_name="test", action="run")
        ws = Workspace(tmp_path / "ws", manifest)

        # Create files with various extensions
        for ext, expected_type in [
            ("xlsx", "excel"), ("pptx", "powerpoint"), ("pdf", "pdf"),
            ("json", "json"), ("csv", "csv"), ("png", "image"),
        ]:
            test_file = ws.outputs_dir / f"test.{ext}"
            test_file.write_bytes(b"content")
            record = ws.register_artifact(test_file)
            assert record.artifact_type == expected_type, f"Failed for .{ext}"

    def test_log_event(self, tmp_path):
        manifest = WorkspaceManifest(skill_name="test", action="run")
        ws = Workspace(tmp_path / "ws", manifest)

        ws.log_event("custom_event", {"key": "value"})

        events_path = tmp_path / "ws" / "events.jsonl"
        lines = events_path.read_text(encoding="utf-8").strip().split("\n")
        # At least workspace_created + custom_event
        assert len(lines) >= 2
        last_event = json.loads(lines[-1])
        assert last_event["event_type"] == "custom_event"
        assert last_event["data"]["key"] == "value"

    def test_save_inputs(self, tmp_path):
        manifest = WorkspaceManifest(skill_name="test", action="run")
        ws = Workspace(tmp_path / "ws", manifest)

        ws.save_inputs({"ebitda": 50, "multiple": 8.0})

        params_path = tmp_path / "ws" / "inputs" / "params.json"
        assert params_path.exists()
        data = json.loads(params_path.read_text(encoding="utf-8"))
        assert data["ebitda"] == 50
        assert ws.manifest.inputs["multiple"] == 8.0

    def test_complete(self, tmp_path):
        manifest = WorkspaceManifest(skill_name="test", action="run")
        ws = Workspace(tmp_path / "ws", manifest)

        ws.complete()

        assert ws.manifest.status == "completed"
        assert ws.manifest.completed_at is not None

        # Verify manifest was written to disk
        manifest_data = json.loads(
            (tmp_path / "ws" / "manifest.json").read_text(encoding="utf-8")
        )
        assert manifest_data["status"] == "completed"

    def test_fail(self, tmp_path):
        manifest = WorkspaceManifest(skill_name="test", action="run")
        ws = Workspace(tmp_path / "ws", manifest)

        ws.fail("Something broke")

        assert ws.manifest.status == "failed"
        assert ws.manifest.error == "Something broke"
        assert ws.manifest.completed_at is not None


# ---------------------------------------------------------------------------
# WorkspaceManager
# ---------------------------------------------------------------------------

class TestWorkspaceManager:

    def test_create_context_manager_success(self, manager):
        with manager.create("test_skill", "test_action", params={"x": 1}) as ws:
            assert ws.run_id != ""
            assert ws.workspace_dir.exists()

            # Create an output file
            output = ws.get_output_path("json")
            output.write_text('{"result": true}')
            ws.register_artifact(output)

        # After context exit, workspace should be completed
        manifest_path = ws.workspace_dir / "manifest.json"
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert data["status"] == "completed"
        assert len(data["outputs"]) == 1

    def test_create_context_manager_failure(self, manager):
        with pytest.raises(ValueError, match="intentional"):
            with manager.create("test_skill", "test_action") as ws:
                ws_dir = ws.workspace_dir
                raise ValueError("intentional error")

        # After exception, workspace should be failed
        manifest_path = ws_dir / "manifest.json"
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert data["status"] == "failed"
        assert "intentional" in data["error"]

    def test_create_with_custom_run_id(self, manager):
        custom_id = "custom-run-id-12345678"
        with manager.create("sk", "act", run_id=custom_id) as ws:
            assert ws.run_id == custom_id
            assert ws.short_run_id == "custom-r"

    def test_create_with_provenance(self, manager):
        provenance = {
            "parent_run_id": "parent-123",
            "deal_id": "acme_lbo_2026",
        }
        with manager.create("sk", "act", provenance=provenance) as ws:
            assert ws.manifest.provenance == provenance

    def test_list_workspaces_empty(self, manager):
        result = manager.list_workspaces()
        assert result == []

    def test_list_workspaces(self, manager):
        # Create a few workspaces
        with manager.create("skill_a", "action_1") as ws1:
            pass
        with manager.create("skill_b", "action_2") as ws2:
            pass

        workspaces = manager.list_workspaces()
        assert len(workspaces) == 2

    def test_list_workspaces_filter_skill(self, manager):
        with manager.create("skill_a", "action_1") as ws1:
            pass
        with manager.create("skill_b", "action_2") as ws2:
            pass

        result = manager.list_workspaces(skill_name="skill_a")
        assert len(result) == 1
        assert result[0]["skill_name"] == "skill_a"

    def test_get_workspace_by_run_id(self, manager):
        with manager.create("test", "act") as ws:
            run_id = ws.run_id

        found = manager.get_workspace_by_run_id(run_id)
        assert found is not None
        assert found["run_id"] == run_id

    def test_get_workspace_by_short_id(self, manager):
        with manager.create("test", "act") as ws:
            short_id = ws.short_run_id

        found = manager.get_workspace_by_run_id(short_id)
        assert found is not None

    def test_get_workspace_not_found(self, manager):
        assert manager.get_workspace_by_run_id("nonexistent") is None

    def test_deterministic_directory_structure(self, manager):
        with manager.create("ib_toolkit", "quick_lbo") as ws:
            ws_dir = ws.workspace_dir

        # Should be: root / YYYY-MM-DD / ib_toolkit_quick_lbo_<short_id>
        parts = ws_dir.parts
        date_part = parts[-2]
        name_part = parts[-1]

        # Date should be YYYY-MM-DD format
        assert len(date_part) == 10
        assert date_part.count("-") == 2

        # Name should contain skill and action
        assert name_part.startswith("ib_toolkit_quick_lbo_")
