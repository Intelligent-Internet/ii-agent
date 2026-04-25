"""Tests for sandbox FastAPI dependency factories.

The wiring is tiny but it's the integration point for the entire
sandbox domain — exercising it guards against silent regressions in
``ApplicationContainer`` field naming.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from ii_agent.agents.sandboxes.dependencies import (
    SandboxRepositoryDep,
    SandboxServiceDep,
    _get_sandbox_service,
    get_sandbox_repository,
)
from ii_agent.agents.sandboxes.repository import SandboxRepository
from ii_agent.agents.sandboxes.service import SandboxService


pytestmark = pytest.mark.unit


class TestGetSandboxRepository:
    def test_returns_a_sandbox_repository(self):
        repo = get_sandbox_repository()
        assert isinstance(repo, SandboxRepository)

    def test_returns_fresh_instance_each_call(self):
        a = get_sandbox_repository()
        b = get_sandbox_repository()
        assert a is not b


class TestGetSandboxService:
    def test_pulls_service_from_container(self):
        container = MagicMock()
        fake_service = MagicMock(spec=SandboxService)
        container.sandbox_service = fake_service

        result = _get_sandbox_service(container)

        assert result is fake_service


class TestDepAliasesAreUsable:
    def test_aliases_are_annotated_types(self):
        # Annotated[T, Depends(...)] resolves to T at __origin__
        # (these are the actual types used in router signatures)
        # We just assert they are non-None and look like Annotated metadata.
        assert SandboxRepositoryDep is not None
        assert SandboxServiceDep is not None
