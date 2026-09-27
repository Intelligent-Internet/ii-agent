from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from ii_agent.projects.databases.models import ProjectDatabase
from ii_agent.projects.databases.repository import ProjectDatabaseRepository
from ii_agent.projects.deployments.models import ProjectDeployment
from ii_agent.projects.deployments.repository import DeploymentsRepository
from ii_agent.projects.models import Project
from ii_agent.projects.repository import ProjectRepository
from ii_agent.projects.subdomains.models import ProjectCustomDomain
from ii_agent.projects.subdomains.repository import SubdomainRepository

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_project_repository_soft_delete_and_updates(
    db_session: AsyncSession,
    user_factory,
    session_factory,
    project_factory,
) -> None:
    repo = ProjectRepository()
    user = await user_factory()
    active_session = await session_factory(user_id=user.id)
    deleted_session = await session_factory(user_id=user.id)

    active = await project_factory(user_id=user.id, session_id=active_session.id, name="Active")
    deleted = Project(
        id=uuid.uuid4(),
        user_id=user.id,
        session_id=deleted_session.id,
        name="Deleted",
        deleted_at=datetime.now(timezone.utc),
    )
    db_session.add(deleted)
    await db_session.flush()

    assert await repo.get_by_id(db_session, active.id) is not None
    assert await repo.get_by_id(db_session, deleted.id) is None
    assert await repo.get_by_id_and_user(db_session, active.id, user.id) is not None
    assert await repo.get_by_session_id(db_session, active_session.id) is not None
    assert await repo.get_by_session_and_user(db_session, active_session.id, user.id) is not None
    assert await repo.get_owner_user_id(db_session, active.id) == user.id

    custom_domain = ProjectCustomDomain(
        id=uuid.uuid4(),
        project_id=active.id,
        subdomain="active-subdomain",
        full_domain="active-subdomain.example.com",
    )
    db_session.add(custom_domain)
    await db_session.flush()

    # update_production_url is the only URL mutation on ProjectRepository
    await repo.update_production_url(db_session, active.id, "https://prod.example.com")
    assert active.production_url == "https://prod.example.com"

    # Missing project should be silently ignored
    await repo.update_production_url(
        db_session,
        uuid.uuid4(),
        "https://missing.example.com",
    )


async def test_deployments_repository_latest_and_max_version(
    db_session: AsyncSession,
    project_factory,
) -> None:
    repo = DeploymentsRepository()
    project = await project_factory()

    await repo.save(
        db_session,
        ProjectDeployment(
            id=uuid.uuid4(),
            project_id=project.id,
            environment="prod",
            deployment_status="success",
            provider="cloud_run",
            version=1,
        ),
    )
    deployment_v2 = await repo.save(
        db_session,
        ProjectDeployment(
            id=uuid.uuid4(),
            project_id=project.id,
            environment="prod",
            deployment_status="success",
            provider="cloud_run",
            version=2,
        ),
    )
    await repo.save(
        db_session,
        ProjectDeployment(
            id=uuid.uuid4(),
            project_id=project.id,
            environment="prod",
            deployment_status="success",
            provider="vercel",
            version=1,
        ),
    )

    latest_any = await repo.get_latest_deployment(db_session, project.id)
    latest_cloud_run = await repo.get_latest_deployment(
        db_session, project.id, provider="cloud_run"
    )
    max_version = await repo.get_max_version(db_session, project.id)

    assert latest_any is not None
    assert latest_any.id == deployment_v2.id
    assert latest_cloud_run is not None
    assert latest_cloud_run.version == 2
    assert max_version == 2


async def test_project_database_repository_crud_and_active_count(
    db_session: AsyncSession,
    session_factory,
) -> None:
    session = await session_factory()
    repo = ProjectDatabaseRepository()

    first = await repo.save(
        db_session,
        ProjectDatabase(
            session_id=session.id,
            source="neondb",
            connection_string="postgres://a",
            host="localhost",
        ),
    )
    second = await repo.save(
        db_session,
        ProjectDatabase(
            session_id=session.id,
            source="supabase",
            connection_string="postgres://b",
            host="remote",
        ),
    )

    active = await repo.get_active_by_session_id(db_session, session.id)
    all_records = await repo.get_all_by_session_id(db_session, session.id)
    assert active is not None
    assert active.id == second.id
    assert len(all_records) == 2

    by_id = await repo.get_by_id(db_session, first.id)
    assert by_id is not None
    by_id.host = "127.0.0.1"
    updated = await repo.update(db_session, by_id)
    assert updated.host == "127.0.0.1"

    deactivated = await repo.deactivate(db_session, second.id)
    assert deactivated is not None
    assert deactivated.is_active is False
    assert await repo.count_active_by_session(db_session, session.id) == 1
    assert await repo.deactivate(db_session, uuid.uuid4()) is None


async def test_subdomain_repository_create_update_delete(
    db_session: AsyncSession,
    user_factory,
    project_factory,
) -> None:
    user = await user_factory()
    project = await project_factory(user_id=user.id)
    repo = SubdomainRepository()

    domain = await repo.save(
        db_session,
        ProjectCustomDomain(
            project_id=project.id,
            claimed_by_user_id=user.id,
            subdomain="my-app",
            full_domain="my-app.example.com",
        ),
    )

    by_project = await repo.get_by_project_id(db_session, project.id)
    by_subdomain = await repo.get_by_subdomain(db_session, "my-app")
    by_full_domain = await repo.get_by_full_domain(db_session, "my-app.example.com")
    assert by_project is not None
    assert by_subdomain is not None
    assert by_full_domain is not None

    domain.dns_status = "propagating"
    updated = await repo.update(db_session, domain)
    assert updated.dns_status == "propagating"

    await repo.delete(db_session, domain)
    assert await repo.get_by_project_id(db_session, project.id) is None
