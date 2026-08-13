from types import SimpleNamespace

import pytest

from ii_agent.settings.mcp.exceptions import MCPOAuthError
from ii_agent.settings.mcp.schemas import MCPServersConfig
from ii_agent.settings.mcp.service import MCPSettingService


class FakeMCPRepo:
    """In-memory stand-in. Method names MUST match the real
    ``MCPSettingRepository`` (which inherits ``save`` / ``update`` from
    ``BaseRepository``) so tests catch service-vs-repo drift.
    """

    def __init__(self):
        self.active = []
        self.saved = []
        self.updated = []
        self.by_tool = {}

    async def list_active_by_user(self, db, user_id):
        return self.active

    async def update(self, db, setting):
        self.updated.append(setting)
        return setting

    async def save(self, db, setting):
        self.saved.append(setting)
        return setting

    async def get_by_user_and_tool_type(self, db, user_id, tool_type):
        return self.by_tool.get(tool_type)

    async def get_by_id_and_user(self, db, setting_id, user_id):
        return None

    async def list_by_user(self, db, user_id, only_active=False, no_metadata=False):
        return []

    async def delete(self, db, setting):
        return None


@pytest.mark.asyncio
async def test_create_mcp_settings_deactivates_previous_active(settings_factory):
    active_setting = SimpleNamespace(is_active=True, updated_at=None)
    repo = FakeMCPRepo()
    repo.active = [active_setting]

    service = MCPSettingService(repo=repo, config=settings_factory())

    result = await service.create_mcp_settings(
        db=None,
        user_id="u1",
        mcp_setting_in=SimpleNamespace(
            mcp_config=MCPServersConfig(mcpServers={}),
            metadata=None,
        ),
    )

    assert active_setting.is_active is False
    assert len(repo.saved) == 1
    assert result.is_active is True


@pytest.mark.asyncio
async def test_configure_codex_requires_auth_or_api_key(settings_factory):
    service = MCPSettingService(repo=FakeMCPRepo(), config=settings_factory())

    with pytest.raises(MCPOAuthError):
        await service.configure_codex(
            db=None,
            user_id="u1",
            auth_json=None,
            apikey=None,
            model=None,
            reasoning_effort=None,
            search=False,
        )


@pytest.mark.asyncio
async def test_configure_claude_code_validates_authorization_format(settings_factory):
    service = MCPSettingService(repo=FakeMCPRepo(), config=settings_factory())

    with pytest.raises(MCPOAuthError, match="Invalid authorization code format"):
        await service.configure_claude_code(
            db=None,
            user_id="u1",
            authorization_code="invalid-format",
        )


def test_real_repository_implements_every_method_service_uses():
    """Contract test: every ``self._repo.<method>`` call inside ``MCPSettingService``
    must be present on the real ``MCPSettingRepository`` class.

    This guards against the regression where the service called ``repo.create``
    while the repository (via ``BaseRepository``) only exposed ``save`` —
    a 500 that the existing ``FakeMCPRepo`` masked.
    """
    import inspect
    import re

    from ii_agent.settings.mcp.repository import MCPSettingRepository

    source = inspect.getsource(MCPSettingService)
    called_methods = set(re.findall(r"self\._repo\.([a-zA-Z_][a-zA-Z0-9_]*)", source))

    missing = sorted(m for m in called_methods if not hasattr(MCPSettingRepository, m))
    assert not missing, (
        f"MCPSettingService calls these methods that MCPSettingRepository "
        f"does not implement: {missing}"
    )
