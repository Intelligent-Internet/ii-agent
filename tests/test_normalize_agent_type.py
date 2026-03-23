"""Tests for normalize_agent_type and Pydantic field validators in messages.py.

Imports from ii_agent.server.models.messages are deferred to test time
to avoid triggering the full server init chain at collection time.
"""

import pytest
from ii_agent.config.agent_types import AgentType


def _msg():
    """Lazy-import the messages module."""
    from ii_agent.server.models.messages import (
        normalize_agent_type,
        InitAgentContent,
        QueryCommandContent,
    )
    return normalize_agent_type, InitAgentContent, QueryCommandContent


class TestNormalizeAgentType:
    """Tests for the normalize_agent_type helper function."""

    @pytest.fixture(autouse=True)
    def _load(self):
        self.normalize_agent_type, _, _ = _msg()

    def test_chat_string_maps_to_general(self):
        assert self.normalize_agent_type("chat") == AgentType.GENERAL

    def test_general_string_maps_to_general(self):
        assert self.normalize_agent_type("general") == AgentType.GENERAL

    def test_media_string_maps_to_media(self):
        assert self.normalize_agent_type("media") == AgentType.MEDIA

    def test_browser_string_maps_to_browser(self):
        assert self.normalize_agent_type("browser") == AgentType.BROWSER

    def test_slide_string_maps_to_slide(self):
        assert self.normalize_agent_type("slide") == AgentType.SLIDE

    def test_website_build_string_maps_correctly(self):
        assert self.normalize_agent_type("website_build") == AgentType.WEBSITE_BUILD

    def test_codex_string_maps_to_codex(self):
        assert self.normalize_agent_type("codex") == AgentType.CODEX

    def test_agent_type_enum_passes_through(self):
        assert self.normalize_agent_type(AgentType.GENERAL) == AgentType.GENERAL
        assert self.normalize_agent_type(AgentType.MEDIA) == AgentType.MEDIA

    def test_invalid_string_raises_value_error(self):
        with pytest.raises(ValueError):
            self.normalize_agent_type("nonexistent_type")

    def test_non_string_non_enum_raises_value_error(self):
        with pytest.raises(ValueError):
            self.normalize_agent_type(123)

    def test_none_raises_value_error(self):
        with pytest.raises(ValueError):
            self.normalize_agent_type(None)


class TestInitAgentContentValidator:
    """Tests for the field_validator on InitAgentContent.agent_type."""

    @pytest.fixture(autouse=True)
    def _load(self):
        _, self.InitAgentContent, _ = _msg()

    def test_chat_normalized_to_general(self):
        content = self.InitAgentContent(agent_type="chat")
        assert content.agent_type == AgentType.GENERAL

    def test_general_stays_general(self):
        content = self.InitAgentContent(agent_type="general")
        assert content.agent_type == AgentType.GENERAL

    def test_media_accepted(self):
        content = self.InitAgentContent(agent_type="media")
        assert content.agent_type == AgentType.MEDIA

    def test_enum_value_accepted(self):
        content = self.InitAgentContent(agent_type=AgentType.SLIDE)
        assert content.agent_type == AgentType.SLIDE

    def test_default_is_general(self):
        content = self.InitAgentContent()
        assert content.agent_type == AgentType.GENERAL

    def test_invalid_type_raises(self):
        with pytest.raises(ValueError):
            self.InitAgentContent(agent_type="bogus")


class TestQueryCommandContentValidator:
    """Tests for the field_validator on QueryCommandContent.agent_type."""

    @pytest.fixture(autouse=True)
    def _load(self):
        _, _, self.QueryCommandContent = _msg()

    def test_chat_normalized_to_general(self):
        content = self.QueryCommandContent(
            model_id="m", provider="p", agent_type="chat"
        )
        assert content.agent_type == AgentType.GENERAL

    def test_general_accepted(self):
        content = self.QueryCommandContent(
            model_id="m", provider="p", agent_type="general"
        )
        assert content.agent_type == AgentType.GENERAL

    def test_enum_value_accepted(self):
        content = self.QueryCommandContent(
            model_id="m", provider="p", agent_type=AgentType.BROWSER
        )
        assert content.agent_type == AgentType.BROWSER

    def test_invalid_type_raises(self):
        with pytest.raises(ValueError):
            self.QueryCommandContent(
                model_id="m", provider="p", agent_type="bogus"
            )
