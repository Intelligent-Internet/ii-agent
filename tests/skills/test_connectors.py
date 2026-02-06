"""Tests for the Connector skill, ConnectorRegistry, and adapter interfaces."""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

from ii_skills.connectors.adapters.base import (
    BaseConnectorAdapter,
    CalendarAdapter,
    ChatAdapter,
    EmailAdapter,
    KnowledgeBaseAdapter,
    ProjectTrackerAdapter,
)
from ii_skills.connectors.registry import CONNECTOR_CATEGORIES, ConnectorRegistry


# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------


@pytest.fixture
def tmp_config(tmp_path):
    """Write a sample .mcp.json and return its path."""
    config = {
        "connectors": {
            "chat": {
                "provider": "slack",
                "mcp_server": "slack-mcp-server",
                "config": {"workspace": "test", "token_env": "SLACK_TOKEN"},
            },
            "email": {
                "provider": "gmail",
                "mcp_server": "gmail-mcp-server",
                "config": {"credentials_env": "GMAIL_CREDS"},
            },
        }
    }
    config_path = tmp_path / ".mcp.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")
    return str(config_path)


@pytest.fixture
def empty_config(tmp_path):
    """Return a path to a nonexistent config file."""
    return str(tmp_path / ".mcp.json")


@pytest.fixture
def registry(tmp_config):
    """ConnectorRegistry with sample config."""
    return ConnectorRegistry(config_path=tmp_config)


@pytest.fixture
def empty_registry(empty_config):
    """ConnectorRegistry with no config file."""
    return ConnectorRegistry(config_path=empty_config)


# ------------------------------------------------------------------
# Stub adapter for testing
# ------------------------------------------------------------------


class StubChatAdapter(ChatAdapter):
    """Concrete stub for testing the ChatAdapter interface."""

    provider = "stub_chat"

    async def connect(self) -> bool:
        self._connected = True
        return True

    async def disconnect(self) -> None:
        self._connected = False

    async def health_check(self) -> Dict[str, Any]:
        return {"healthy": self._connected, "message": "stub"}

    async def send_message(self, channel: str, message: str) -> Dict[str, Any]:
        self._require_connection()
        return {"sent": True, "channel": channel}

    async def read_messages(self, channel: str, limit: int = 20) -> List[Dict[str, Any]]:
        self._require_connection()
        return [{"text": "hello", "channel": channel}]

    async def search_messages(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        self._require_connection()
        return [{"text": f"match: {query}"}]

    async def list_channels(self) -> List[Dict[str, Any]]:
        self._require_connection()
        return [{"name": "general"}]


# ------------------------------------------------------------------
# Registry Tests
# ------------------------------------------------------------------


class TestConnectorRegistry:
    def test_registry_loads_config(self, registry):
        """Registry should load .mcp.json successfully."""
        config = registry.load_config()
        assert "connectors" in config
        assert "chat" in config["connectors"]

    def test_list_configured(self, registry):
        """list_configured should return provider names keyed by category."""
        configured = registry.list_configured()
        assert configured["chat"] == "slack"
        assert configured["email"] == "gmail"
        assert "calendar" not in configured

    def test_is_configured(self, registry):
        """is_configured should return True for configured categories."""
        assert registry.is_configured("chat") is True
        assert registry.is_configured("email") is True
        assert registry.is_configured("calendar") is False

    def test_get_connector_by_category(self, registry):
        """Without registered adapters, get_connector returns None."""
        assert registry.get_connector("chat") is None

    def test_get_connector_with_registered_adapter(self, registry):
        """After manual registration, get_connector returns the adapter."""
        stub = StubChatAdapter()
        registry.register_adapter("chat", stub)
        adapter = registry.get_connector("chat")
        assert adapter is not None
        assert adapter.provider == "stub_chat"

    def test_unconfigured_category_returns_none(self, empty_registry):
        """Registry with no config should return None for all categories."""
        assert empty_registry.get_connector("chat") is None
        assert empty_registry.get_connector("email") is None

    def test_health_check_all_connectors(self, registry):
        """Health check should report status for configured connectors."""
        health = registry.health_check()
        assert "chat" in health
        assert "email" in health
        # Not connected since no adapters registered
        assert health["chat"]["healthy"] is False

    def test_health_check_with_connected_adapter(self, registry):
        """Connected adapter should report healthy."""
        stub = StubChatAdapter()
        stub._connected = True
        registry.register_adapter("chat", stub)
        health = registry.health_check()
        assert health["chat"]["healthy"] is True

    def test_list_categories(self, registry):
        """Should list all known categories."""
        cats = registry.list_categories()
        assert "chat" in cats
        assert "email" in cats
        assert "calendar" in cats

    def test_missing_config_file(self, empty_registry):
        """Missing config file should not raise."""
        config = empty_registry.load_config()
        assert config == {}


# ------------------------------------------------------------------
# Adapter Interface Tests
# ------------------------------------------------------------------


class TestAdapterInterface:
    def test_adapter_interface_contract(self):
        """Stub adapter should implement all ChatAdapter methods."""
        stub = StubChatAdapter()
        assert hasattr(stub, "connect")
        assert hasattr(stub, "disconnect")
        assert hasattr(stub, "health_check")
        assert hasattr(stub, "send_message")
        assert hasattr(stub, "read_messages")
        assert hasattr(stub, "search_messages")
        assert hasattr(stub, "list_channels")

    @pytest.mark.asyncio
    async def test_adapter_connect_disconnect(self):
        """Adapter should track connection state."""
        stub = StubChatAdapter()
        assert stub.is_connected is False
        await stub.connect()
        assert stub.is_connected is True
        await stub.disconnect()
        assert stub.is_connected is False

    @pytest.mark.asyncio
    async def test_adapter_requires_connection(self):
        """Methods should raise if not connected."""
        stub = StubChatAdapter()
        with pytest.raises(RuntimeError, match="not connected"):
            await stub.send_message("general", "hello")

    @pytest.mark.asyncio
    async def test_adapter_methods_work_when_connected(self):
        """Methods should succeed after connect()."""
        stub = StubChatAdapter()
        await stub.connect()
        result = await stub.send_message("general", "hello")
        assert result["sent"] is True

    def test_base_adapter_category_and_provider(self):
        """Concrete adapters should declare category and provider."""
        stub = StubChatAdapter()
        assert stub.category == "chat"
        assert stub.provider == "stub_chat"

    def test_category_abstract_classes_exist(self):
        """All category abstract adapter classes should be importable."""
        assert ChatAdapter.category == "chat"
        assert EmailAdapter.category == "email"
        assert CalendarAdapter.category == "calendar"
        assert KnowledgeBaseAdapter.category == "knowledge_base"
        assert ProjectTrackerAdapter.category == "project_tracker"


# ------------------------------------------------------------------
# Graceful Degradation Tests
# ------------------------------------------------------------------


class TestGracefulDegradation:
    def test_graceful_degradation_on_missing_config(self, tmp_path):
        """Skill should degrade gracefully when .mcp.json is missing."""
        from ii_skills import get_skill

        workspace = str(tmp_path)
        skill = get_skill("connectors", config={"workspace_root": workspace})
        skill.initialize()

        result = skill.execute("list_connectors")
        assert result["configured_count"] == 0

    def test_graceful_degradation_on_unconfigured_action(self, tmp_path):
        """Actions on unconfigured categories should return error dict, not crash."""
        from ii_skills import get_skill

        workspace = str(tmp_path)
        skill = get_skill("connectors", config={"workspace_root": workspace})
        skill.initialize()

        result = skill.execute("send_message", channel="general", message="hello")
        assert "error" in result
        assert result["available"] is False

    def test_all_category_actions_degrade_gracefully(self, tmp_path):
        """Every category action should return an error dict, not crash."""
        from ii_skills import get_skill

        workspace = str(tmp_path)
        skill = get_skill("connectors", config={"workspace_root": workspace})
        skill.initialize()

        category_actions = [
            ("send_message", {"channel": "x", "message": "y"}),
            ("read_messages", {"channel": "x"}),
            ("search_messages", {"query": "x"}),
            ("send_email", {"to": "x", "subject": "y", "body": "z"}),
            ("read_inbox", {}),
            ("search_email", {"query": "x"}),
            ("get_calendar", {"start": "2026-01-01", "end": "2026-01-02"}),
            ("get_today_schedule", {}),
            ("create_event", {"title": "x", "start": "2026-01-01", "end": "2026-01-01"}),
            ("search_kb", {"query": "x"}),
            ("get_kb_page", {"page_id": "x"}),
            ("get_tracker_tasks", {}),
            ("sync_tasks", {}),
        ]

        for action, kwargs in category_actions:
            result = skill.execute(action, **kwargs)
            assert "error" in result, f"Action '{action}' did not return error dict"
            assert result["available"] is False, f"Action '{action}' should report unavailable"


# ------------------------------------------------------------------
# Skill Integration Tests
# ------------------------------------------------------------------


class TestConnectorSkill:
    def test_skill_registers(self):
        """Connector skill should be discoverable."""
        from ii_skills import list_skills

        skills = list_skills()
        skill_names = [s["name"] for s in skills]
        assert "connectors" in skill_names

    def test_skill_capabilities(self):
        """Skill should report all 16 capabilities."""
        from ii_skills import get_skill

        skill = get_skill("connectors")
        caps = skill.get_capabilities()
        assert len(caps) == 16
        assert "list_connectors" in caps
        assert "check_health" in caps
        assert "send_message" in caps
        assert "sync_tasks" in caps
        assert "get_config_template" in caps

    def test_skill_list_connectors_with_config(self, tmp_path):
        """list_connectors should show configured providers."""
        # Write config
        config = {
            "connectors": {
                "chat": {"provider": "slack", "mcp_server": "slack-mcp"},
            }
        }
        (tmp_path / ".mcp.json").write_text(json.dumps(config), encoding="utf-8")

        from ii_skills import get_skill

        skill = get_skill("connectors", config={"workspace_root": str(tmp_path)})
        skill.initialize()

        result = skill.execute("list_connectors")
        assert result["configured_count"] == 1
        assert result["configured"]["chat"] == "slack"

    def test_skill_check_health_empty(self, tmp_path):
        """check_health with no connectors should report healthy."""
        from ii_skills import get_skill

        skill = get_skill("connectors", config={"workspace_root": str(tmp_path)})
        skill.initialize()

        result = skill.execute("check_health")
        assert result["overall"] == "healthy"  # No connectors = vacuously healthy

    def test_skill_get_config_template(self, tmp_path):
        """get_config_template should return the example JSON."""
        from ii_skills import get_skill

        skill = get_skill("connectors", config={"workspace_root": str(tmp_path)})
        skill.initialize()

        result = skill.execute("get_config_template")
        assert "template" in result
        assert "connectors" in result["template"]
