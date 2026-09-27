"""Tests for the A2A tool bridge schema serialization module.

Tests cover:
  * serialize_tool_schemas — Function objects, dicts, CLI-native exclusion
  * _CLI_NATIVE_TOOL_NAMES — expected membership
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any


from ii_agent.integrations.a2a.tool_bridge import (
    _CLI_NATIVE_TOOL_NAMES,
    serialize_tool_schemas,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_function(name: str, description: str = "", parameters: dict | None = None) -> Any:
    """Build a minimal Function-like object with the attrs read by serialize_tool_schemas."""
    return SimpleNamespace(
        name=name,
        description=description,
        parameters=parameters or {"type": "object", "properties": {"query": {"type": "string"}}},
    )


def _make_dict_tool(name: str, description: str = "", parameters: dict | None = None) -> dict:
    """Build a dict tool definition."""
    return {
        "name": name,
        "description": description,
        "parameters": parameters or {"type": "object", "properties": {"q": {"type": "string"}}},
    }


# ---------------------------------------------------------------------------
# _CLI_NATIVE_TOOL_NAMES membership
# ---------------------------------------------------------------------------


class TestCliNativeToolNames:
    """Verify that the expected tools are classified as CLI-native."""

    def test_bash_tools_are_cli_native(self) -> None:
        for name in ("Bash", "BashView", "BashList", "WriteToProcess"):
            assert name in _CLI_NATIVE_TOOL_NAMES, f"{name} should be CLI-native"

    def test_file_tools_are_cli_native(self) -> None:
        for name in ("Read", "Write", "Edit", "ApplyPatch", "StrReplaceEditor"):
            assert name in _CLI_NATIVE_TOOL_NAMES, f"{name} should be CLI-native"

    def test_non_cli_tools_are_not_native(self) -> None:
        for name in ("WebSearch", "VisitWeb", "ImageGeneration", "DeployProject"):
            assert name not in _CLI_NATIVE_TOOL_NAMES, f"{name} should NOT be CLI-native"

    def test_count(self) -> None:
        assert len(_CLI_NATIVE_TOOL_NAMES) == 9


# ---------------------------------------------------------------------------
# serialize_tool_schemas — Function objects
# ---------------------------------------------------------------------------


class TestSerializeToolSchemasFunction:
    """Test serialization from Function-like objects."""

    def test_basic_function_serialization(self) -> None:
        tool = _make_function("WebSearch", "Search the web", {"type": "object", "properties": {}})
        result = serialize_tool_schemas([tool])
        assert len(result) == 1
        assert result[0]["name"] == "WebSearch"
        assert result[0]["description"] == "Search the web"
        assert result[0]["parameters"] == {"type": "object", "properties": {}}

    def test_excludes_cli_native_by_default(self) -> None:
        tools = [
            _make_function("Bash"),
            _make_function("WebSearch"),
            _make_function("Read"),
        ]
        result = serialize_tool_schemas(tools)
        names = [s["name"] for s in result]
        assert "WebSearch" in names
        assert "Bash" not in names
        assert "Read" not in names

    def test_include_cli_native_when_disabled(self) -> None:
        tools = [_make_function("Bash"), _make_function("WebSearch")]
        result = serialize_tool_schemas(tools, exclude_cli_native=False)
        names = [s["name"] for s in result]
        assert "Bash" in names
        assert "WebSearch" in names

    def test_empty_name_skipped(self) -> None:
        tool = _make_function("")
        result = serialize_tool_schemas([tool])
        assert result == []

    def test_none_description_becomes_empty(self) -> None:
        tool = SimpleNamespace(name="MyTool", description=None, parameters=None)
        result = serialize_tool_schemas([tool])
        assert len(result) == 1
        assert result[0]["description"] == ""
        assert result[0]["parameters"] == {"type": "object", "properties": {}}

    def test_none_parameters_gets_default(self) -> None:
        tool = SimpleNamespace(name="MyTool", description="desc", parameters=None)
        result = serialize_tool_schemas([tool])
        assert result[0]["parameters"] == {"type": "object", "properties": {}}

    def test_multiple_functions(self) -> None:
        tools = [
            _make_function("WebSearch", "search"),
            _make_function("VisitWeb", "visit"),
            _make_function("ImageGen", "generate"),
        ]
        result = serialize_tool_schemas(tools)
        assert len(result) == 3
        assert [s["name"] for s in result] == ["WebSearch", "VisitWeb", "ImageGen"]

    def test_empty_list(self) -> None:
        result = serialize_tool_schemas([])
        assert result == []


# ---------------------------------------------------------------------------
# serialize_tool_schemas — dict tools
# ---------------------------------------------------------------------------


class TestSerializeToolSchemasDict:
    """Test serialization from dict tool definitions."""

    def test_basic_dict_serialization(self) -> None:
        tool = _make_dict_tool("MyTool", "A tool", {"type": "object", "properties": {"x": {}}})
        result = serialize_tool_schemas([tool])
        assert len(result) == 1
        assert result[0]["name"] == "MyTool"
        assert result[0]["description"] == "A tool"

    def test_excludes_cli_native_dict(self) -> None:
        tools = [_make_dict_tool("Bash"), _make_dict_tool("WebSearch")]
        result = serialize_tool_schemas(tools)
        names = [s["name"] for s in result]
        assert "Bash" not in names
        assert "WebSearch" in names

    def test_empty_name_dict_skipped(self) -> None:
        result = serialize_tool_schemas([{"name": "", "description": "x"}])
        assert result == []

    def test_missing_name_dict_skipped(self) -> None:
        result = serialize_tool_schemas([{"description": "no name field"}])
        assert result == []

    def test_none_description_dict(self) -> None:
        result = serialize_tool_schemas([{"name": "T", "description": None}])
        assert result[0]["description"] == ""

    def test_none_parameters_dict(self) -> None:
        result = serialize_tool_schemas([{"name": "T"}])
        assert result[0]["parameters"] == {"type": "object", "properties": {}}


# ---------------------------------------------------------------------------
# serialize_tool_schemas — mixed inputs
# ---------------------------------------------------------------------------


class TestSerializeToolSchemasMixed:
    """Test with mixed Function objects and dicts."""

    def test_mixed_types(self) -> None:
        tools: list[Any] = [
            _make_function("WebSearch", "search the web"),
            _make_dict_tool("CustomTool", "a custom tool"),
        ]
        result = serialize_tool_schemas(tools)
        assert len(result) == 2
        assert result[0]["name"] == "WebSearch"
        assert result[1]["name"] == "CustomTool"

    def test_mixed_with_cli_native_exclusion(self) -> None:
        tools: list[Any] = [
            _make_function("Bash"),  # excluded
            _make_dict_tool("Edit"),  # excluded
            _make_function("WebSearch"),  # kept
            _make_dict_tool("CustomTool"),  # kept
        ]
        result = serialize_tool_schemas(tools)
        names = [s["name"] for s in result]
        assert names == ["WebSearch", "CustomTool"]

    def test_all_cli_native_yields_empty(self) -> None:
        tools: list[Any] = [
            _make_function("Bash"),
            _make_function("Read"),
            _make_dict_tool("Write"),
            _make_dict_tool("Edit"),
        ]
        result = serialize_tool_schemas(tools)
        assert result == []
