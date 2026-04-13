"""Unit tests for agents/models/anthropic/claude.py pure helper functions."""

from __future__ import annotations

from unittest.mock import MagicMock


from ii_agent.agents.models.anthropic.claude import (
    _normalize_tool_definition,
    format_tools_for_model,
)


# ---------------------------------------------------------------------------
# _normalize_tool_definition
# ---------------------------------------------------------------------------


class TestNormalizeToolDefinition:
    def test_none_returns_none(self):
        assert _normalize_tool_definition(None) is None

    def test_dict_without_function_key_returned_as_is(self):
        tool = {"name": "search", "description": "search the web"}
        result = _normalize_tool_definition(tool)
        assert result == tool

    def test_dict_with_function_key_returns_inner(self):
        inner = {"name": "search", "description": "search"}
        tool = {"function": inner}
        result = _normalize_tool_definition(tool)
        assert result == inner

    def test_object_with_to_dict_returns_dict(self):
        tool = MagicMock()
        tool.to_dict.return_value = {"name": "my_tool", "description": "does stuff"}
        del tool.model_dump  # Ensure model_dump not called
        result = _normalize_tool_definition(tool)
        assert result == {"name": "my_tool", "description": "does stuff"}

    def test_object_with_to_dict_raising_falls_through_to_model_dump(self):
        tool = MagicMock()
        tool.to_dict.side_effect = Exception("broken")
        tool.model_dump.return_value = {"name": "tool2"}
        result = _normalize_tool_definition(tool)
        assert result == {"name": "tool2"}

    def test_object_with_model_dump_returns_dict(self):
        tool = MagicMock(spec=["model_dump"])
        tool.model_dump.return_value = {"name": "pydantic_tool", "description": "test"}
        result = _normalize_tool_definition(tool)
        assert result == {"name": "pydantic_tool", "description": "test"}

    def test_object_with_model_dump_raising_returns_none(self):
        class BadTool:
            def model_dump(self, **kwargs):
                raise RuntimeError("boom")

        result = _normalize_tool_definition(BadTool())
        assert result is None

    def test_plain_object_with_no_methods_returns_none(self):
        result = _normalize_tool_definition(object())
        assert result is None

    def test_to_dict_returning_non_dict_skipped(self):
        tool = MagicMock()
        tool.to_dict.return_value = "not a dict"
        tool.model_dump.return_value = {"name": "fallback"}
        result = _normalize_tool_definition(tool)
        assert result == {"name": "fallback"}


# ---------------------------------------------------------------------------
# format_tools_for_model
# ---------------------------------------------------------------------------


class TestFormatToolsForModel:
    def test_none_tools_returns_empty_list(self):
        assert format_tools_for_model(None) == []

    def test_empty_list_returns_empty_list(self):
        assert format_tools_for_model([]) == []

    def test_tool_without_name_skipped(self):
        tool = {"description": "search the web"}  # no 'name' key
        result = format_tools_for_model([tool])
        assert result == []

    def test_tool_without_definition_skipped(self):
        result = format_tools_for_model([None])
        assert result == []

    def test_valid_tool_formatted_correctly(self):
        tool = {"name": "search", "description": "search the web"}
        result = format_tools_for_model([tool])
        assert len(result) == 1
        assert result[0]["name"] == "search"
        assert result[0]["description"] == "search the web"
        # Default empty parameters
        assert result[0]["input_schema"] == {"type": "object", "properties": {}}

    def test_tool_with_parameters_passed_through(self):
        tool = {
            "name": "query",
            "description": "query db",
            "parameters": {"type": "object", "properties": {"q": {"type": "string"}}},
        }
        result = format_tools_for_model([tool])
        assert result[0]["input_schema"]["properties"]["q"]["type"] == "string"

    def test_multiple_tools(self):
        tools = [
            {"name": "tool_a", "description": "a"},
            {"name": "tool_b", "description": "b"},
        ]
        result = format_tools_for_model(tools)
        assert len(result) == 2
        assert {r["name"] for r in result} == {"tool_a", "tool_b"}

    def test_mixed_valid_invalid_tools(self):
        tools = [
            None,  # no definition → skipped
            {"name": "valid", "description": "works"},
            {},  # no name → skipped
        ]
        result = format_tools_for_model(tools)
        assert len(result) == 1
        assert result[0]["name"] == "valid"
