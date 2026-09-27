"""Tests for ii_agent.projects schemas — deployments, database, project response schemas."""

from __future__ import annotations

import uuid


class TestProjectDeploymentHasDeployment:
    def test_has_deployment_true_when_id_set(self):
        from ii_agent.projects.deployments.schemas import ProjectDeploymentResponse

        resp = ProjectDeploymentResponse(
            id=uuid.uuid4(),
            project_id=uuid.uuid4(),
        )
        assert resp.has_deployment is True

    def test_has_deployment_false_when_id_none(self):
        from ii_agent.projects.deployments.schemas import ProjectDeploymentResponse

        resp = ProjectDeploymentResponse(
            id=None,
            project_id=uuid.uuid4(),
        )
        assert resp.has_deployment is False


class TestDeploymentNotFoundError:
    def test_deployment_not_found_sets_project_id(self):
        from ii_agent.projects.deployments.exceptions import DeploymentNotFoundError

        exc = DeploymentNotFoundError("proj-abc-123")
        assert exc.project_id == "proj-abc-123"
        assert "proj-abc-123" in str(exc)


class TestSessionProjectResponseProjectName:
    def test_project_name_returns_name(self):
        from ii_agent.projects.schemas import SessionProjectResponse

        resp = SessionProjectResponse(
            id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            session_id=None,
            name="My Project",
            description=None,
            status="active",
            current_build_status="ready",
            framework=None,
            project_path=None,
            production_url=None,
            created_at=None,
            updated_at=None,
        )
        assert resp.project_name == "My Project"

    def test_project_name_returns_none_when_no_name(self):
        from ii_agent.projects.schemas import SessionProjectResponse

        resp = SessionProjectResponse(
            id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            session_id=None,
            name=None,
            description=None,
            status="active",
            current_build_status="ready",
            framework=None,
            project_path=None,
            production_url=None,
            created_at=None,
            updated_at=None,
        )
        assert resp.project_name is None


class TestTableRecordsResult:
    def test_init_stores_rows_and_total(self):
        from ii_agent.projects.databases.schemas import TableRecordsResult

        result = TableRecordsResult(rows=[{"col": "val"}], total=42)
        assert result.rows == [{"col": "val"}]
        assert result.total == 42

    def test_init_empty_rows(self):
        from ii_agent.projects.databases.schemas import TableRecordsResult

        result = TableRecordsResult(rows=[], total=0)
        assert result.rows == []
        assert result.total == 0
