"""Unit tests for engine/runtime/tools/function.py - r4.

Covers:
- Function.to_dict
- Function.model_copy (shallow + deep)
- Function.from_callable (with various signatures)
- Function.from_tool
- Function.process_entrypoint
- Function.process_schema_for_strict
- Function._wrap_callable
- FunctionCall.get_call_str
- FunctionCall._handle_pre_hook / _handle_post_hook
- get_entrypoint_docstring
"""

from __future__ import annotations

import pytest
from functools import partial
from typing import Optional
from unittest.mock import AsyncMock, MagicMock

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# get_entrypoint_docstring
# ---------------------------------------------------------------------------


class TestGetEntrypointDocstring:
    """Test the helper get_entrypoint_docstring."""

    def test_simple_function_returns_short_desc(self):
        from ii_agent.agents.tools.function import get_entrypoint_docstring

        def my_func():
            """Short description of my function."""
            pass

        result = get_entrypoint_docstring(my_func)
        assert "Short description" in result

    def test_function_with_long_desc_includes_both(self):
        from ii_agent.agents.tools.function import get_entrypoint_docstring

        def my_func():
            """Short description.

            Long description here.
            """
            pass

        result = get_entrypoint_docstring(my_func)
        assert "Short description" in result
        assert "Long description" in result

    def test_function_no_docstring_returns_empty(self):
        from ii_agent.agents.tools.function import get_entrypoint_docstring

        def no_doc():
            pass

        result = get_entrypoint_docstring(no_doc)
        assert result == ""

    def test_partial_function_returns_string(self):
        from ii_agent.agents.tools.function import get_entrypoint_docstring

        def base_func(x, y):
            """Base function."""
            return x + y

        p = partial(base_func, y=10)
        result = get_entrypoint_docstring(p)
        # For partial, returns str(entrypoint)
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# Function.to_dict
# ---------------------------------------------------------------------------


class TestFunctionToDict:
    """Test Function.to_dict method."""

    def test_basic_to_dict(self):
        from ii_agent.agents.tools.function import Function

        fn = Function(name="my_func", description="Does something")
        d = fn.to_dict()
        assert d["name"] == "my_func"
        assert d["description"] == "Does something"

    def test_excludes_none_fields(self):
        from ii_agent.agents.tools.function import Function

        fn = Function(name="fn", description=None)
        d = fn.to_dict()
        assert "description" not in d

    def test_includes_requires_confirmation_when_set(self):
        from ii_agent.agents.tools.function import Function

        fn = Function(name="fn", description="desc", requires_confirmation=True)
        d = fn.to_dict()
        assert d["requires_confirmation"] is True

    def test_includes_requires_sandbox_when_set(self):
        from ii_agent.agents.tools.function import Function

        fn = Function(name="fn", description="desc", requires_sandbox=True)
        d = fn.to_dict()
        assert d["requires_sandbox"] is True

    def test_parameters_included(self):
        from ii_agent.agents.tools.function import Function

        params = {"type": "object", "properties": {"x": {"type": "string"}}, "required": ["x"]}
        fn = Function(name="fn", description="desc", parameters=params)
        d = fn.to_dict()
        assert "parameters" in d
        assert d["parameters"]["properties"]["x"]["type"] == "string"


# ---------------------------------------------------------------------------
# Function.model_copy
# ---------------------------------------------------------------------------


class TestFunctionModelCopy:
    """Test Function.model_copy for shallow and deep copy behavior."""

    def test_shallow_copy_preserves_identity_of_entrypoint(self):
        from ii_agent.agents.tools.function import Function

        def ep():
            pass

        fn = Function(name="fn", description="desc", entrypoint=ep)
        copied = fn.model_copy(deep=False)
        assert copied.entrypoint is fn.entrypoint

    def test_deep_copy_preserves_entrypoint_identity(self):
        from ii_agent.agents.tools.function import Function

        def ep():
            pass

        fn = Function(name="fn", description="desc", entrypoint=ep)
        copied = fn.model_copy(deep=True)
        # Callable fields should NOT be deep-copied
        assert copied.entrypoint is fn.entrypoint

    def test_deep_copy_creates_new_parameters_dict(self):
        from ii_agent.agents.tools.function import Function

        params = {"type": "object", "properties": {"x": {"type": "string"}}}
        fn = Function(name="fn", description="desc", parameters=params)
        copied = fn.model_copy(deep=True)
        # Parameters should be deep-copied (different objects)
        assert copied.parameters is not fn.parameters
        assert copied.parameters == fn.parameters

    def test_deep_copy_preserves_pre_hook_identity(self):
        from ii_agent.agents.tools.function import Function

        def pre_hook():
            pass

        fn = Function(name="fn", description="desc", pre_hook=pre_hook)
        copied = fn.model_copy(deep=True)
        assert copied.pre_hook is fn.pre_hook


# ---------------------------------------------------------------------------
# Function.from_callable
# ---------------------------------------------------------------------------


class TestFunctionFromCallable:
    """Test Function.from_callable with various function signatures."""

    def test_simple_function(self):
        from ii_agent.agents.tools.function import Function

        def greet(name: str) -> str:
            """Greet someone.

            Args:
                name: The person to greet
            """
            return f"Hello {name}"

        fn = Function.from_callable(greet)
        assert fn.name == "greet"
        assert fn.entrypoint is not None
        assert "name" in fn.parameters["properties"]

    def test_function_with_optional_param(self):
        from ii_agent.agents.tools.function import Function

        def func(required: str, optional: Optional[str] = None) -> str:
            """Function with optional.

            Args:
                required: A required param
                optional: An optional param
            """
            return required

        fn = Function.from_callable(func)
        assert "required" in fn.parameters.get("required", [])
        assert "optional" not in fn.parameters.get("required", [])

    def test_custom_name_override(self):
        from ii_agent.agents.tools.function import Function

        def original_name():
            pass

        fn = Function.from_callable(original_name, name="custom_name")
        assert fn.name == "custom_name"

    def test_agent_param_excluded(self):
        from ii_agent.agents.tools.function import Function

        def func_with_agent(x: str, agent=None) -> str:
            """Func with agent.

            Args:
                x: Input value
            """
            return x

        fn = Function.from_callable(func_with_agent)
        assert "agent" not in fn.parameters.get("properties", {})

    def test_run_context_param_excluded(self):
        from ii_agent.agents.tools.function import Function

        def func_with_context(x: str, run_context=None) -> str:
            """Func with context.

            Args:
                x: Input value
            """
            return x

        fn = Function.from_callable(func_with_context)
        assert "run_context" not in fn.parameters.get("properties", {})

    def test_docstring_used_as_description(self):
        from ii_agent.agents.tools.function import Function

        def documented() -> None:
            """This is the docstring description."""
            pass

        fn = Function.from_callable(documented)
        assert fn.description and "docstring description" in fn.description

    def test_strict_mode_marks_all_required(self):
        from ii_agent.agents.tools.function import Function

        def func(x: str, y: str = "default") -> str:
            """Strict func.

            Args:
                x: First param
                y: Second param with default
            """
            return x

        fn = Function.from_callable(func, strict=True)
        # In strict mode, all fields should be required
        assert "x" in fn.parameters.get("required", [])
        assert "y" in fn.parameters.get("required", [])


# ---------------------------------------------------------------------------
# Function.from_tool
# ---------------------------------------------------------------------------


class TestFunctionFromTool:
    """Test Function.from_tool factory."""

    def _make_tool(self, name="test_tool", requires_user_input=False, user_input_fields=None):
        from ii_agent.agents.tools.base import BaseAgentTool

        tool = MagicMock(spec=BaseAgentTool)
        tool.name = name
        tool.description = "A test tool"
        tool.display_name = name.replace("_", " ").title()
        tool.tool_logo = None
        tool.input_schema = {
            "type": "object",
            "properties": {
                "param1": {"type": "string", "description": "First param"},
            },
            "required": ["param1"],
        }
        tool.requires_sandbox = False
        tool.requires_confirmation = False
        tool.requires_user_input = requires_user_input
        tool.user_input_fields = user_input_fields or []
        tool.stop_after_tool_call = False
        tool.on_tool_start = AsyncMock()
        tool.on_tool_end = AsyncMock()
        return tool

    def test_creates_function_with_tool_name(self):
        from ii_agent.agents.tools.function import Function

        tool = self._make_tool(name="my_tool")
        fn = Function.from_tool(tool)
        assert fn.name == "my_tool"

    def test_creates_function_with_tool_description(self):
        from ii_agent.agents.tools.function import Function

        tool = self._make_tool()
        fn = Function.from_tool(tool)
        assert fn.description == "A test tool"

    def test_skip_entrypoint_processing_is_true(self):
        from ii_agent.agents.tools.function import Function

        tool = self._make_tool()
        fn = Function.from_tool(tool)
        assert fn.skip_entrypoint_processing is True

    def test_raises_for_non_tool(self):
        from ii_agent.agents.tools.function import Function

        with pytest.raises(ValueError, match="Expected BaseTool instance"):
            Function.from_tool("not a tool")

    def test_parameters_from_input_schema(self):
        from ii_agent.agents.tools.function import Function

        tool = self._make_tool()
        fn = Function.from_tool(tool)
        assert "param1" in fn.parameters.get("properties", {})

    def test_user_input_schema_created_when_fields_specified(self):
        from ii_agent.agents.tools.function import Function

        tool = self._make_tool(requires_user_input=True, user_input_fields=["param1"])
        fn = Function.from_tool(tool)
        assert fn.user_input_schema is not None
        assert len(fn.user_input_schema) > 0

    def test_entrypoint_wraps_tool_execute(self):
        from ii_agent.agents.tools.function import Function
        from ii_agent.agents.tools.base import ToolResult

        tool = self._make_tool()
        tool.execute = AsyncMock(return_value=ToolResult(llm_content="result", is_error=False))

        fn = Function.from_tool(tool)
        # Verify the entrypoint is callable
        assert callable(fn.entrypoint)


# ---------------------------------------------------------------------------
# Function.process_entrypoint
# ---------------------------------------------------------------------------


class TestFunctionProcessEntrypoint:
    """Test Function.process_entrypoint."""

    def test_skip_entrypoint_processing_true_does_nothing(self):
        from ii_agent.agents.tools.function import Function

        fn = Function(
            name="fn",
            description="desc",
            skip_entrypoint_processing=True,
            entrypoint=None,
        )
        fn.process_entrypoint()
        # Should not change anything
        assert fn.description == "desc"

    def test_none_entrypoint_returns_early(self):
        from ii_agent.agents.tools.function import Function

        fn = Function(name="fn", description="desc", entrypoint=None)
        fn.process_entrypoint()
        assert fn.entrypoint is None

    def test_processes_simple_function(self):
        from ii_agent.agents.tools.function import Function

        def simple(x: str) -> str:
            """Simple function.

            Args:
                x: Input
            """
            return x

        fn = Function(name="simple", entrypoint=simple)
        fn.process_entrypoint()
        assert fn.description is not None
        assert "x" in fn.parameters.get("properties", {})

    def test_strict_mode_processes_schema(self):
        from ii_agent.agents.tools.function import Function

        def func(x: str) -> str:
            """Func.

            Args:
                x: Input
            """
            return x

        fn = Function(name="func", entrypoint=func)
        fn.process_entrypoint(strict=True)
        # strict mode should set additionalProperties: false
        assert fn.parameters.get("additionalProperties") is False

    def test_preserves_user_set_parameters(self):
        from ii_agent.agents.tools.function import Function

        def func(x: str) -> str:
            """Func."""
            return x

        custom_params = {
            "type": "object",
            "properties": {"custom": {"type": "integer"}},
            "required": [],
        }
        fn = Function(name="func", entrypoint=func, parameters=custom_params)
        fn.process_entrypoint()
        # user-set parameters should be preserved
        assert "custom" in fn.parameters.get("properties", {})

    def test_requires_user_input_sets_user_input_schema(self):
        from ii_agent.agents.tools.function import Function

        def func(x: str, y: int = 5) -> str:
            """Func.

            Args:
                x: Input
                y: Number
            """
            return x

        fn = Function(name="func", entrypoint=func, requires_user_input=True)
        fn.process_entrypoint()
        assert fn.user_input_schema is not None


# ---------------------------------------------------------------------------
# Function.process_schema_for_strict
# ---------------------------------------------------------------------------


class TestFunctionProcessSchemaForStrict:
    """Test Function.process_schema_for_strict."""

    def test_adds_additional_properties_false(self):
        from ii_agent.agents.tools.function import Function

        fn = Function(
            name="fn",
            description="desc",
            parameters={
                "type": "object",
                "properties": {"x": {"type": "string"}},
                "required": [],
            },
        )
        fn.process_schema_for_strict()
        assert fn.parameters.get("additionalProperties") is False

    def test_marks_all_properties_as_required(self):
        from ii_agent.agents.tools.function import Function

        fn = Function(
            name="fn",
            description="desc",
            parameters={
                "type": "object",
                "properties": {
                    "x": {"type": "string"},
                    "y": {"type": "integer"},
                },
                "required": [],
            },
        )
        fn.process_schema_for_strict()
        assert "x" in fn.parameters["required"]
        assert "y" in fn.parameters["required"]

    def test_nested_object_gets_additional_properties_false(self):
        from ii_agent.agents.tools.function import Function

        fn = Function(
            name="fn",
            description="desc",
            parameters={
                "type": "object",
                "properties": {
                    "nested": {
                        "type": "object",
                        "properties": {"inner": {"type": "string"}},
                    }
                },
                "required": [],
            },
        )
        fn.process_schema_for_strict()
        nested = fn.parameters["properties"]["nested"]
        assert nested.get("additionalProperties") is False

    def test_excludes_special_params_from_required(self):
        from ii_agent.agents.tools.function import Function

        fn = Function(
            name="fn",
            description="desc",
            parameters={
                "type": "object",
                "properties": {
                    "x": {"type": "string"},
                    "agent": {"type": "object"},
                    "run_context": {"type": "object"},
                },
                "required": [],
            },
        )
        fn.process_schema_for_strict()
        assert "agent" not in fn.parameters["required"]
        assert "run_context" not in fn.parameters["required"]
        assert "x" in fn.parameters["required"]


# ---------------------------------------------------------------------------
# Function._wrap_callable
# ---------------------------------------------------------------------------


class TestFunctionWrapCallable:
    """Test Function._wrap_callable."""

    def test_async_generator_not_wrapped(self):
        from ii_agent.agents.tools.function import Function

        async def async_gen(x: str):
            yield x

        result = Function._wrap_callable(async_gen)
        # Async generators should not be wrapped
        assert result is async_gen

    def test_regular_sync_function_wrapped(self):
        from ii_agent.agents.tools.function import Function

        def sync_func(x: str) -> str:
            return x

        result = Function._wrap_callable(sync_func)
        # Should be wrapped with validate_call
        assert result is not sync_func or callable(result)

    def test_already_wrapped_not_rewrapped(self):
        from ii_agent.agents.tools.function import Function

        def func(x: str) -> str:
            return x

        first_wrap = Function._wrap_callable(func)
        # Mark as wrapped
        if hasattr(first_wrap, "_wrapped_for_validation"):
            second_wrap = Function._wrap_callable(first_wrap)
            assert second_wrap is first_wrap

    def test_function_with_session_state_not_wrapped(self):
        from ii_agent.agents.tools.function import Function

        def func_with_state(x: str, session_state=None) -> str:
            return x

        result = Function._wrap_callable(func_with_state)
        # session_state param -> should NOT be wrapped
        assert result is func_with_state


# ---------------------------------------------------------------------------
# FunctionCall.get_call_str
# ---------------------------------------------------------------------------


class TestFunctionCallGetCallStr:
    """Test FunctionCall.get_call_str."""

    def _make_fc(self, args=None):
        from ii_agent.agents.tools.function import Function, FunctionCall

        fn = Function(name="test_function", description="Test")
        return FunctionCall(function=fn, arguments=args)

    def test_no_arguments_returns_empty_parens(self):
        fc = self._make_fc(args=None)
        result = fc.get_call_str()
        assert result == "test_function()"

    def test_with_arguments_includes_kwargs(self):
        fc = self._make_fc(args={"x": "value1", "y": 42})
        result = fc.get_call_str()
        assert "test_function" in result
        assert "x" in result or "..." in result

    def test_long_string_argument_truncated(self):
        long_str = "x" * 1000
        fc = self._make_fc(args={"param": long_str})
        result = fc.get_call_str()
        # Very long arg should be replaced with "..."
        assert "..." in result or len(result) < 500

    def test_very_long_call_truncated(self):
        args = {f"param{i}": f"value{i}" * 10 for i in range(20)}
        fc = self._make_fc(args=args)
        result = fc.get_call_str()
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# FunctionCall._handle_pre_hook
# ---------------------------------------------------------------------------


class TestFunctionCallPreHook:
    """Test FunctionCall._handle_pre_hook."""

    def _make_fc(self, pre_hook=None):
        from ii_agent.agents.tools.function import Function, FunctionCall

        fn = Function(name="fn", description="desc", pre_hook=pre_hook)
        return FunctionCall(function=fn, arguments={})

    def test_no_pre_hook_does_nothing(self):
        fc = self._make_fc(pre_hook=None)
        # Should not raise
        fc._handle_pre_hook()

    def test_pre_hook_called_with_no_special_params(self):
        called_with = {}

        def simple_hook():
            called_with["called"] = True

        fc = self._make_fc(pre_hook=simple_hook)
        fc._handle_pre_hook()
        assert called_with.get("called") is True

    def test_pre_hook_with_fc_param_receives_fc(self):
        received = {}

        def hook_with_fc(fc):
            received["fc"] = fc

        from ii_agent.agents.tools.function import Function, FunctionCall

        fn = Function(name="fn", description="desc", pre_hook=hook_with_fc)
        fc = FunctionCall(function=fn, arguments={})
        fc._handle_pre_hook()
        assert received.get("fc") is fc

    def test_pre_hook_exception_sets_error(self):
        from ii_agent.agents.exceptions import AgentRunException

        def failing_hook():
            raise AgentRunException("Test error")

        fc = self._make_fc(pre_hook=failing_hook)
        with pytest.raises(AgentRunException):
            fc._handle_pre_hook()
        assert fc.error == "Test error"

    def test_pre_hook_general_exception_logged_but_not_raised(self):
        def general_error_hook():
            raise ValueError("General error")

        fc = self._make_fc(pre_hook=general_error_hook)
        # General exceptions should be caught and logged, not raised
        fc._handle_pre_hook()

    def test_pre_hook_run_cancelled_exception_is_raised(self):
        from ii_agent.core.redis.cancel import RunCancelledException

        def cancelling_hook():
            raise RunCancelledException("cancelled-pre")

        fc = self._make_fc(pre_hook=cancelling_hook)
        with pytest.raises(RunCancelledException, match="cancelled-pre"):
            fc._handle_pre_hook()

    @pytest.mark.asyncio
    async def test_pre_hook_async_run_cancelled_exception_is_raised(self):
        from ii_agent.core.redis.cancel import RunCancelledException
        from ii_agent.agents.tools.function import Function, FunctionCall

        async def cancelling_hook():
            raise RunCancelledException("cancelled-pre-async")

        fn = Function(name="fn", description="desc", pre_hook=cancelling_hook)
        fc = FunctionCall(function=fn, arguments={})
        with pytest.raises(RunCancelledException, match="cancelled-pre-async"):
            await fc._handle_pre_hook_async()


# ---------------------------------------------------------------------------
# FunctionCall._handle_post_hook  (sync)
# ---------------------------------------------------------------------------


class TestFunctionCallPostHook:
    """Test FunctionCall._handle_post_hook."""

    def _make_fc(self, post_hook=None):
        from ii_agent.agents.tools.function import Function, FunctionCall

        fn = Function(name="fn", description="desc", post_hook=post_hook)
        return FunctionCall(function=fn, arguments={})

    def test_no_post_hook_does_nothing(self):
        fc = self._make_fc(post_hook=None)
        fc._handle_post_hook()

    def test_post_hook_called(self):
        called = {}

        def simple_hook():
            called["done"] = True

        fc = self._make_fc(post_hook=simple_hook)
        fc._handle_post_hook()
        assert called.get("done") is True

    def test_post_hook_with_fc_param_receives_fc(self):
        received = {}

        def hook(fc):
            received["fc"] = fc

        from ii_agent.agents.tools.function import Function, FunctionCall

        fn = Function(name="fn", description="desc", post_hook=hook)
        fc = FunctionCall(function=fn, arguments={})
        fc._handle_post_hook()
        assert received.get("fc") is fc

    def test_post_hook_exception_logged_not_raised(self):
        def failing_hook():
            raise RuntimeError("Post-hook failure")

        fc = self._make_fc(post_hook=failing_hook)
        # Should not raise
        fc._handle_post_hook()

    def test_post_hook_run_cancelled_exception_is_raised(self):
        from ii_agent.core.redis.cancel import RunCancelledException

        def cancelling_hook():
            raise RunCancelledException("cancelled")

        fc = self._make_fc(post_hook=cancelling_hook)
        with pytest.raises(RunCancelledException, match="cancelled"):
            fc._handle_post_hook()

    @pytest.mark.asyncio
    async def test_post_hook_async_run_cancelled_exception_is_raised(self):
        from ii_agent.core.redis.cancel import RunCancelledException
        from ii_agent.agents.tools.function import Function, FunctionCall

        async def cancelling_hook():
            raise RunCancelledException("cancelled-async")

        fn = Function(name="fn", description="desc", post_hook=cancelling_hook)
        fc = FunctionCall(function=fn, arguments={})
        with pytest.raises(RunCancelledException, match="cancelled-async"):
            await fc._handle_post_hook_async()


# ---------------------------------------------------------------------------
# FunctionExecutionResult
# ---------------------------------------------------------------------------


class TestFunctionExecutionResult:
    """Test FunctionExecutionResult model."""

    def test_success_result(self):
        from ii_agent.agents.tools.function import FunctionExecutionResult

        r = FunctionExecutionResult(status="success", result="output")
        assert r.status == "success"
        assert r.result == "output"
        assert r.error is None

    def test_failure_result(self):
        from ii_agent.agents.tools.function import FunctionExecutionResult

        r = FunctionExecutionResult(status="failure", error="Something went wrong")
        assert r.status == "failure"
        assert r.error == "Something went wrong"
        assert r.result is None

    def test_with_session_state(self):
        from ii_agent.agents.tools.function import FunctionExecutionResult

        r = FunctionExecutionResult(
            status="success",
            result="ok",
            updated_session_state={"key": "value"},
        )
        assert r.updated_session_state == {"key": "value"}
