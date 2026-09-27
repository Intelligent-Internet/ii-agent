"""Unit tests for get_entrypoint_docstring and Function.from_callable."""

from __future__ import annotations

from functools import partial
from typing import Optional


from ii_agent.agents.tools.function import Function, get_entrypoint_docstring


# ---------------------------------------------------------------------------
# get_entrypoint_docstring
# ---------------------------------------------------------------------------


class TestGetEntrypointDocstring:
    def test_function_with_no_docstring_returns_empty(self):
        def no_doc():
            pass

        result = get_entrypoint_docstring(no_doc)
        assert result == ""

    def test_function_with_short_description(self):
        def fn():
            """Short description only."""

        result = get_entrypoint_docstring(fn)
        assert result == "Short description only."

    def test_function_with_long_description(self):
        def fn():
            """Short line.

            Long line here.
            Another long line.
            """

        result = get_entrypoint_docstring(fn)
        assert "Short line." in result
        assert "Long line here." in result

    def test_partial_function_returns_str(self):
        def base(x: int) -> int:
            return x * 2

        p = partial(base, 5)
        result = get_entrypoint_docstring(p)
        # partial returns str(partial_object)
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# Function.from_callable — special parameter filtering
# ---------------------------------------------------------------------------


class TestFunctionFromCallable:
    def test_basic_function_no_params(self):
        def greet() -> str:
            """Greet the user."""

        fn = Function.from_callable(greet)
        assert fn.name == "greet"
        assert fn.description == "Greet the user."
        assert fn.parameters["properties"] == {}

    def test_basic_function_with_typed_param(self):
        def search(query: str) -> str:
            """Search for something.

            Args:
                query: The search query.
            """

        fn = Function.from_callable(search)
        assert fn.name == "search"
        assert "query" in fn.parameters["properties"]

    def test_custom_name_overrides_callable_name(self):
        def inner_fn() -> None:
            """Do a thing."""

        fn = Function.from_callable(inner_fn, name="my_custom_name")
        assert fn.name == "my_custom_name"

    def test_agent_param_stripped(self):
        def run_with_agent(agent, query: str) -> str:
            """Run with agent param."""

        fn = Function.from_callable(run_with_agent)
        # 'agent' should not appear in schema properties
        assert "agent" not in fn.parameters.get("properties", {})
        assert "query" in fn.parameters.get("properties", {})

    def test_run_context_param_stripped(self):
        def run_with_context(run_context, x: int) -> int:
            """Run with run_context."""

        fn = Function.from_callable(run_with_context)
        assert "run_context" not in fn.parameters.get("properties", {})
        assert "x" in fn.parameters.get("properties", {})

    def test_session_state_param_stripped(self):
        def with_session(session_state, count: int) -> int:
            """With session_state param."""

        fn = Function.from_callable(with_session)
        assert "session_state" not in fn.parameters.get("properties", {})
        assert "count" in fn.parameters.get("properties", {})

    def test_dependencies_param_stripped(self):
        def with_deps(dependencies, name: str) -> str:
            """With dependencies param."""

        fn = Function.from_callable(with_deps)
        assert "dependencies" not in fn.parameters.get("properties", {})
        assert "name" in fn.parameters.get("properties", {})

    def test_images_param_stripped(self):
        def with_images(images, description: str) -> str:
            """With images param."""

        fn = Function.from_callable(with_images)
        assert "images" not in fn.parameters.get("properties", {})
        assert "description" in fn.parameters.get("properties", {})

    def test_videos_param_stripped(self):
        def with_videos(videos, description: str) -> str:
            """With videos."""

        fn = Function.from_callable(with_videos)
        assert "videos" not in fn.parameters.get("properties", {})

    def test_audios_param_stripped(self):
        def with_audios(audios, description: str) -> str:
            """With audios."""

        fn = Function.from_callable(with_audios)
        assert "audios" not in fn.parameters.get("properties", {})

    def test_files_param_stripped(self):
        def with_files(files, description: str) -> str:
            """With files."""

        fn = Function.from_callable(with_files)
        assert "files" not in fn.parameters.get("properties", {})

    def test_optional_param_in_schema(self):
        def search(query: str, limit: Optional[int] = None) -> str:
            """Search with optional limit.

            Args:
                query: Search query.
                limit: Max results.
            """

        fn = Function.from_callable(search)
        props = fn.parameters.get("properties", {})
        assert "query" in props
        assert "limit" in props
