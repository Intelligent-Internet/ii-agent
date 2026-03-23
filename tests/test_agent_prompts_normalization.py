"""Tests for agent_type normalization in agent_prompts.py.

agent_prompts.py imports ii_agent.server.slides at module level, which triggers
the full server __init__ chain and causes a circular import.  We pre-seed
ii_agent.server.slides in sys.modules as a proper package stub so the import
succeeds without triggering the heavy server initialization.
"""

import sys
import types
from unittest.mock import MagicMock
import pathlib

import pytest
from ii_agent.config.agent_types import AgentType

# Pre-seed ii_agent.server.slides in sys.modules BEFORE importing
# agent_prompts.  The stub has __path__ pointing to the real slides dir
# so sub-modules (e.g. slides.views) can still be found by later imports.
# We do NOT stub ii_agent.server itself — it must run its real __init__
# to establish the correct import ordering for event_stream / subscriber.
_SRC = pathlib.Path(__file__).resolve().parent.parent / "src"

if "ii_agent.server.slides" not in sys.modules:
    _slides_stub = types.ModuleType("ii_agent.server.slides")
    _slides_stub.__path__ = [str(_SRC / "ii_agent" / "server" / "slides")]
    _slides_stub.__package__ = "ii_agent.server.slides"
    _slides_stub.template_service = MagicMock()  # type: ignore[attr-defined]
    sys.modules["ii_agent.server.slides"] = _slides_stub

from ii_agent.prompts.agent_prompts import (
    get_specialized_instructions,
    get_system_prompt_for_agent_type,
)


class TestGetSpecializedInstructionsNormalization:
    """Tests that get_specialized_instructions normalizes string agent_type values."""

    @pytest.mark.asyncio
    async def test_chat_string_normalized_to_general_raises(self):
        # 'chat' normalizes to AgentType.GENERAL, which has no specialized instructions
        with pytest.raises(ValueError, match="No specialized instructions found"):
            await get_specialized_instructions("chat")

    @pytest.mark.asyncio
    async def test_media_string_accepted(self):
        result = await get_specialized_instructions("media")
        expected = await get_specialized_instructions(AgentType.MEDIA)
        assert result == expected

    @pytest.mark.asyncio
    async def test_slide_enum_value_works(self):
        result = await get_specialized_instructions(AgentType.SLIDE)
        assert isinstance(result, str)
        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_invalid_string_raises(self):
        with pytest.raises(ValueError):
            await get_specialized_instructions("nonexistent")


class TestGetSystemPromptForAgentTypeNormalization:
    """Tests that get_system_prompt_for_agent_type normalizes string agent_type values."""

    @pytest.mark.asyncio
    async def test_chat_string_returns_general_prompt(self):
        result = await get_system_prompt_for_agent_type("chat", workspace_path="/tmp/ws")
        expected = await get_system_prompt_for_agent_type(AgentType.GENERAL, workspace_path="/tmp/ws")
        assert result == expected

    @pytest.mark.asyncio
    async def test_general_string_accepted(self):
        result = await get_system_prompt_for_agent_type("general", workspace_path="/tmp/ws")
        assert isinstance(result, str)
        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_invalid_string_raises(self):
        with pytest.raises(ValueError):
            await get_system_prompt_for_agent_type("bogus", workspace_path="/tmp/ws")
