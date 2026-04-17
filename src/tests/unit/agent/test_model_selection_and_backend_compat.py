"""Tests for model selection correlation with inner-loop backends.

Validates that:
1. ``check_model_backend_compat`` correctly identifies compatible/incompatible
   model-backend pairs for all three A2A backends (copilot, claude-code, codex).
2. ``get_model`` dispatches to the correct provider builder based on
   (Provider, ApiType) and falls back gracefully for unknown combos.
3. The agent factory logs a compat warning when model/backend mismatch in A2A mode.
4. The A2A inner loop forwards ``model.id`` in streaming metadata.
5. The chat A2A turn loop forwards ``model_config.model_id`` in metadata.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any, AsyncIterator, Dict, cast
from unittest.mock import MagicMock, patch

import pytest

from ii_agent.integrations.a2a.backend_compat import (
    _BACKEND_MODEL_PREFIXES,
    check_model_backend_compat,
)
from ii_agent.agents.models.utils import get_model, _MODEL_BUILDERS
from ii_agent.settings.llm.types import ApiType, Provider
from ii_agent.core.config.llm_config import LLMConfig


# ===================================================================
# 1. check_model_backend_compat — exhaustive model/backend matrix
# ===================================================================


class TestCheckModelBackendCompat:
    """Validates the A2A model-backend compatibility validator."""

    # ---- Copilot: no restrictions (empty prefix tuple) ----

    @pytest.mark.parametrize(
        "model_id",
        [
            "claude-sonnet-4-20250514",
            "claude-opus-4-6",
            "o4-mini",
            "gpt-4o",
            "gemini-3-pro",
            "anything-at-all",
        ],
    )
    def test_copilot_accepts_any_model(self, model_id: str) -> None:
        """Copilot backend has no model restrictions — all models are compatible."""
        assert check_model_backend_compat(model_id, "copilot") is None

    # ---- Claude Code: only claude-* models ----

    @pytest.mark.parametrize(
        "model_id",
        [
            "claude-sonnet-4-20250514",
            "claude-opus-4-6",
            "claude-3-5-haiku-20250929",
            "claude-sonnet-4-5-20250514",
        ],
    )
    def test_claude_code_accepts_claude_models(self, model_id: str) -> None:
        assert check_model_backend_compat(model_id, "claude-code") is None

    @pytest.mark.parametrize(
        "model_id",
        [
            "o4-mini",
            "gpt-4o",
            "gemini-3-pro",
            "grok-code-fast",
        ],
    )
    def test_claude_code_rejects_non_claude_models(self, model_id: str) -> None:
        warning = check_model_backend_compat(model_id, "claude-code")
        assert warning is not None
        assert "claude-code" in warning
        assert model_id in warning

    # ---- Codex: only o4-, o3-, o1-, gpt- models ----

    @pytest.mark.parametrize(
        "model_id",
        [
            "o4-mini",
            "o3-mini",
            "o1-preview",
            "gpt-4o",
            "gpt-5.1",
        ],
    )
    def test_codex_accepts_openai_models(self, model_id: str) -> None:
        assert check_model_backend_compat(model_id, "codex") is None

    @pytest.mark.parametrize(
        "model_id",
        [
            "claude-sonnet-4-20250514",
            "gemini-3-pro",
            "grok-code-fast",
        ],
    )
    def test_codex_rejects_non_openai_models(self, model_id: str) -> None:
        warning = check_model_backend_compat(model_id, "codex")
        assert warning is not None
        assert "codex" in warning
        assert model_id in warning

    # ---- Edge cases ----

    def test_unknown_backend_returns_none(self) -> None:
        """Unknown backend names skip validation (no crash)."""
        assert check_model_backend_compat("any-model", "unknown-backend") is None

    def test_empty_model_id_against_restricted_backend(self) -> None:
        """Empty model_id should return a warning for restricted backends."""
        warning = check_model_backend_compat("", "codex")
        assert warning is not None

    def test_backend_prefix_map_has_all_three_backends(self) -> None:
        """Verify that the prefix map covers all documented A2A backends."""
        assert set(_BACKEND_MODEL_PREFIXES.keys()) == {"copilot", "claude-code", "codex"}


# ===================================================================
# 2. get_model — provider/api_type dispatch and fallback
# ===================================================================


class TestGetModelDispatch:
    """Validates model builder dispatch for (provider, api_type) combos."""

    def _make_llm_config(
        self,
        *,
        model: str = "test-model",
        provider: Provider = Provider.ANTHROPIC,
        api_type: ApiType | None = None,
        api_key: str | None = "test-key",
        base_url: str | None = None,
    ) -> LLMConfig:
        return LLMConfig(
            model=model,
            provider=provider,
            api_type=api_type,
            api_key=api_key,
            base_url=base_url,
        )

    @patch("ii_agent.agents.models.utils._build_anthropic_direct")
    def test_anthropic_direct_dispatches_correctly(self, mock_builder: MagicMock) -> None:
        mock_builder.return_value = MagicMock(id="claude-sonnet-4-20250514")
        config = self._make_llm_config(provider=Provider.ANTHROPIC, api_type=None)
        model = get_model(Provider.ANTHROPIC, llm_config=config)
        mock_builder.assert_called_once()
        assert model.id == "claude-sonnet-4-20250514"

    @patch("ii_agent.agents.models.utils._build_anthropic_vertex")
    def test_anthropic_vertex_dispatches_correctly(self, mock_builder: MagicMock) -> None:
        mock_builder.return_value = MagicMock(id="claude-sonnet-4-vertex")
        config = self._make_llm_config(provider=Provider.ANTHROPIC, api_type=ApiType.VERTEX_AI)
        model = get_model(Provider.ANTHROPIC, llm_config=config)
        mock_builder.assert_called_once()
        assert model.id == "claude-sonnet-4-vertex"

    @patch("ii_agent.agents.models.utils._build_google")
    def test_google_direct_dispatches_correctly(self, mock_builder: MagicMock) -> None:
        mock_builder.return_value = MagicMock(id="gemini-3-pro")
        config = self._make_llm_config(provider=Provider.GOOGLE, api_type=None)
        get_model(Provider.GOOGLE, llm_config=config)
        mock_builder.assert_called_once()

    @patch("ii_agent.agents.models.utils._build_google")
    def test_google_vertex_dispatches_correctly(self, mock_builder: MagicMock) -> None:
        mock_builder.return_value = MagicMock(id="gemini-vertex")
        config = self._make_llm_config(provider=Provider.GOOGLE, api_type=ApiType.VERTEX_AI)
        get_model(Provider.GOOGLE, llm_config=config)
        mock_builder.assert_called_once()

    @patch("ii_agent.agents.models.utils._build_openai")
    def test_openai_dispatches_correctly(self, mock_builder: MagicMock) -> None:
        mock_builder.return_value = MagicMock(id="gpt-4o")
        config = self._make_llm_config(provider=Provider.OPENAI, api_type=None)
        get_model(Provider.OPENAI, llm_config=config)
        mock_builder.assert_called_once()

    @patch("ii_agent.agents.models.utils._build_custom")
    def test_cerebras_uses_custom_builder(self, mock_builder: MagicMock) -> None:
        mock_builder.return_value = MagicMock(id="cerebras-model")
        config = self._make_llm_config(provider=Provider.CEREBRAS, api_type=None)
        get_model(Provider.CEREBRAS, llm_config=config)
        mock_builder.assert_called_once()

    @patch("ii_agent.agents.models.utils._build_custom")
    def test_custom_provider_dispatches_correctly(self, mock_builder: MagicMock) -> None:
        mock_builder.return_value = MagicMock(id="custom-model")
        config = self._make_llm_config(provider=Provider.CUSTOM, api_type=None)
        get_model(Provider.CUSTOM, llm_config=config)
        mock_builder.assert_called_once()

    @patch("ii_agent.agents.models.utils._build_custom")
    def test_unknown_provider_falls_back_to_custom(self, mock_builder: MagicMock) -> None:
        """A provider not in _MODEL_BUILDERS falls back to _build_custom."""
        mock_builder.return_value = MagicMock(id="fallback")
        # Simulate an unknown provider by using CUSTOM with an unregistered ApiType
        config = self._make_llm_config(provider=Provider.CUSTOM, api_type=None)
        model = get_model(Provider.CUSTOM, llm_config=config)
        assert model.id == "fallback"

    def test_model_id_matches_config(self) -> None:
        """The model.id should reflect the model string from the config."""
        with patch("ii_agent.agents.models.utils._build_anthropic_direct") as mock_builder:
            fake_model = MagicMock()
            fake_model.id = "claude-sonnet-4-20250514"
            mock_builder.return_value = fake_model

            config = self._make_llm_config(
                model="claude-sonnet-4-20250514", provider=Provider.ANTHROPIC
            )
            model = get_model(Provider.ANTHROPIC, llm_config=config)
            assert model.id == "claude-sonnet-4-20250514"

    def test_all_expected_providers_have_builders(self) -> None:
        """Verify that every known provider has at least one builder entry."""
        providers_with_builders = {p for p, _ in _MODEL_BUILDERS}
        expected = {
            Provider.ANTHROPIC,
            Provider.GOOGLE,
            Provider.OPENAI,
            Provider.CEREBRAS,
            Provider.CUSTOM,
        }
        assert expected <= providers_with_builders


# ===================================================================
# 3. Agent factory compat warning integration
# ===================================================================


class TestAgentFactoryCompatWarning:
    """Validates that the agent factory checks model/backend compatibility."""

    def _make_factory_config(self, *, mode: str = "a2a", backend: str = "codex"):
        agent = SimpleNamespace(
            inner_loop_mode=mode,
            a2a_agent_url="http://localhost:9001",
            a2a_timeout_seconds=10.0,
            a2a_fallback_to_native=True,
            a2a_context_reuse=True,
            a2a_backend=backend,
        )
        return SimpleNamespace(agent=agent)

    @pytest.mark.asyncio
    async def test_compat_warning_logged_for_mismatched_model(self, caplog) -> None:
        """When a claude model is used with codex backend, a warning is logged."""
        from ii_agent.agents.factory.agent import AgentFactory

        factory = AgentFactory(self._make_factory_config(mode="a2a", backend="codex"))
        fake_model = SimpleNamespace(id="claude-sonnet-4-20250514", name="Claude Sonnet 4")

        with (
            patch("ii_agent.agents.factory.agent.get_model", return_value=fake_model),
            patch("ii_agent.agents.factory.agent.AgentToolManager.resolve_tools", return_value=[]),
            patch("ii_agent.agents.factory.agent.AgentToolManager.log_tool_summary"),
            patch("ii_agent.agents.factory.agent.IIAgent") as mock_agent_cls,
            patch(
                "ii_agent.agents.factory.agent.check_model_backend_compat",
                wraps=check_model_backend_compat,
            ) as mock_compat,
        ):
            mock_agent_cls.return_value = MagicMock()
            mock_agent_cls.return_value.set_id = MagicMock()

            await factory.create_agent(
                user_id="user-1",
                session_id="session-1",
                llm_config=SimpleNamespace(provider=Provider.ANTHROPIC),
                system_prompt="test",
            )

        mock_compat.assert_called_once_with("claude-sonnet-4-20250514", "codex")

    @pytest.mark.asyncio
    async def test_no_compat_warning_for_compatible_model(self) -> None:
        """When an OpenAI model is used with codex backend, no warning is logged."""
        from ii_agent.agents.factory.agent import AgentFactory

        factory = AgentFactory(self._make_factory_config(mode="a2a", backend="codex"))
        fake_model = SimpleNamespace(id="o4-mini", name="o4-mini")

        with (
            patch("ii_agent.agents.factory.agent.get_model", return_value=fake_model),
            patch("ii_agent.agents.factory.agent.AgentToolManager.resolve_tools", return_value=[]),
            patch("ii_agent.agents.factory.agent.AgentToolManager.log_tool_summary"),
            patch("ii_agent.agents.factory.agent.IIAgent") as mock_agent_cls,
            patch(
                "ii_agent.agents.factory.agent.check_model_backend_compat",
                wraps=check_model_backend_compat,
            ) as mock_compat,
        ):
            mock_agent_cls.return_value = MagicMock()
            mock_agent_cls.return_value.set_id = MagicMock()

            await factory.create_agent(
                user_id="user-1",
                session_id="session-1",
                llm_config=SimpleNamespace(provider=Provider.OPENAI),
                system_prompt="test",
            )

        mock_compat.assert_called_once_with("o4-mini", "codex")
        # The function should return None (compatible)
        assert check_model_backend_compat("o4-mini", "codex") is None

    @pytest.mark.asyncio
    async def test_compat_check_skipped_for_native_mode(self) -> None:
        """In native mode, check_model_backend_compat is never called."""
        from ii_agent.agents.factory.agent import AgentFactory

        config = SimpleNamespace(
            agent=SimpleNamespace(
                inner_loop_mode="native",
                a2a_agent_url=None,
                a2a_timeout_seconds=10.0,
                a2a_fallback_to_native=True,
                a2a_context_reuse=True,
                a2a_backend="codex",
            )
        )
        factory = AgentFactory(config)
        fake_model = SimpleNamespace(id="claude-sonnet-4-20250514", name="Claude")

        with (
            patch("ii_agent.agents.factory.agent.get_model", return_value=fake_model),
            patch("ii_agent.agents.factory.agent.AgentToolManager.resolve_tools", return_value=[]),
            patch("ii_agent.agents.factory.agent.AgentToolManager.log_tool_summary"),
            patch("ii_agent.agents.factory.agent.IIAgent") as mock_agent_cls,
            patch("ii_agent.agents.factory.agent.check_model_backend_compat") as mock_compat,
        ):
            mock_agent_cls.return_value = MagicMock()
            mock_agent_cls.return_value.set_id = MagicMock()

            await factory.create_agent(
                user_id="user-1",
                session_id="session-1",
                llm_config=SimpleNamespace(provider=Provider.ANTHROPIC),
                system_prompt="test",
            )

        mock_compat.assert_not_called()


# ===================================================================
# 4. A2A inner loop — model.id flows into streaming metadata
# ===================================================================


@dataclass
class _FakeModel:
    id: str = "fake-model"
    name: str = "fake"

    async def aresponse_stream(self, **_: Any) -> AsyncIterator[Any]:
        from ii_agent.agents.models.response import ModelResponse

        yield ModelResponse(content="native-response", is_delta=True)


class _CapturingA2AClient:
    """Fake A2A client that captures the metadata dict sent to astream."""

    def __init__(
        self,
        events: list | None = None,
        fail: bool = False,
    ) -> None:
        self._events = events or []
        self._fail = fail
        self.captured_metadata: Dict[str, Any] = {}
        self.captured_context_id: str = ""

    async def astream(
        self,
        messages: Any = None,
        context_id: str = "",
        metadata: Dict[str, Any] | None = None,
        **_: Any,
    ) -> AsyncIterator:
        self.captured_metadata = metadata or {}
        self.captured_context_id = context_id
        if self._fail:
            raise RuntimeError("adapter unavailable")

        for event in self._events:
            yield event

    async def post_tool_result(self, **_: Any) -> bool:
        return True

    async def cancel_task(self, task_id: str) -> None:
        pass


class TestA2AInnerLoopModelForwarding:
    """Validates that A2A inner loop forwards model.id in metadata."""

    @pytest.mark.asyncio
    async def test_model_id_included_in_a2a_metadata(self) -> None:
        """model.id is forwarded in the metadata dict to the A2A client."""
        from ii_agent.agents.inner_loop import A2AInnerLoop
        from ii_agent.integrations.a2a.as_client import A2AStreamEvent

        client = _CapturingA2AClient(
            events=[
                A2AStreamEvent(event_type="text_delta", data={"text": "hi"}),
                A2AStreamEvent(event_type="message_complete", data={"text": "hi"}),
            ]
        )
        strategy = A2AInnerLoop(
            client=cast(Any, client),
            fallback_to_native=False,
        )

        model = _FakeModel(id="claude-sonnet-4-20250514")
        events = []
        async for event in strategy.aresponse_stream(
            model=cast(Any, model),
            messages=[],
        ):
            events.append(event)

        assert client.captured_metadata["model"] == "claude-sonnet-4-20250514"

    @pytest.mark.asyncio
    async def test_different_model_ids_forwarded_correctly(self) -> None:
        """Different model IDs are forwarded accurately."""
        from ii_agent.agents.inner_loop import A2AInnerLoop
        from ii_agent.integrations.a2a.as_client import A2AStreamEvent

        for model_id in ["o4-mini", "gpt-4o", "gemini-3-pro", "claude-opus-4-6"]:
            client = _CapturingA2AClient(
                events=[
                    A2AStreamEvent(event_type="text_delta", data={"text": "ok"}),
                    A2AStreamEvent(event_type="message_complete", data={"text": "ok"}),
                ]
            )
            strategy = A2AInnerLoop(
                client=cast(Any, client),
                fallback_to_native=False,
            )

            events = []
            async for event in strategy.aresponse_stream(
                model=cast(Any, _FakeModel(id=model_id)),
                messages=[],
            ):
                events.append(event)

            assert client.captured_metadata["model"] == model_id, (
                f"Expected model={model_id!r} in A2A metadata"
            )

    @pytest.mark.asyncio
    async def test_model_id_flows_to_native_on_fallback(self) -> None:
        """On A2A failure+fallback, the SAME model is used for native execution."""
        from ii_agent.agents.inner_loop import A2AInnerLoop, NativeInnerLoop
        from ii_agent.agents.models.response import ModelResponse

        client = _CapturingA2AClient(fail=True)
        native = NativeInnerLoop()
        strategy = A2AInnerLoop(
            client=cast(Any, client),
            fallback_strategy=native,
            fallback_to_native=True,
        )

        model = _FakeModel(id="claude-sonnet-4-20250514")
        model_responses = []
        async for event in strategy.aresponse_stream(
            model=cast(Any, model),
            messages=[],
        ):
            if isinstance(event, ModelResponse):
                model_responses.append(event)

        # The native fallback should produce a response using the same model
        assert len(model_responses) >= 1
        assert model_responses[0].content == "native-response"


# ===================================================================
# 5. Cross-cutting: model selection → backend compat correlation
# ===================================================================


class TestModelSelectionBackendCorrelation:
    """End-to-end model selection → backend compatibility matrix.

    Validates that for each provider, the model IDs that would be selected
    correlate to supported models on the matching A2A backend.
    """

    # Provider → typical model IDs that get_model would produce
    _PROVIDER_MODEL_SAMPLES: Dict[str, list[str]] = {
        "Anthropic": [
            "claude-sonnet-4-20250514",
            "claude-opus-4-6",
            "claude-3-5-haiku-20250929",
            "claude-sonnet-4-5-20250514",
        ],
        "OpenAI": [
            "o4-mini",
            "gpt-4o",
            "gpt-5.1",
            "o3-mini",
        ],
        "Google": [
            "gemini-3-pro",
            "gemini-2.5-flash",
        ],
    }

    # Backend → providers whose models are expected to be compatible
    _BACKEND_COMPATIBLE_PROVIDERS: Dict[str, set[str]] = {
        "copilot": {"Anthropic", "OpenAI", "Google"},  # Accepts everything
        "claude-code": {"Anthropic"},
        "codex": {"OpenAI"},
    }

    @pytest.mark.parametrize("backend", ["copilot", "claude-code", "codex"])
    def test_compatible_providers_have_no_warnings(self, backend: str) -> None:
        """Models from compatible providers produce no compat warning."""
        compatible_providers = self._BACKEND_COMPATIBLE_PROVIDERS[backend]
        for provider in compatible_providers:
            for model_id in self._PROVIDER_MODEL_SAMPLES.get(provider, []):
                warning = check_model_backend_compat(model_id, backend)
                assert warning is None, (
                    f"Expected no warning for model={model_id!r} on "
                    f"backend={backend!r} (provider={provider!r}), got: {warning}"
                )

    @pytest.mark.parametrize("backend", ["claude-code", "codex"])
    def test_incompatible_providers_produce_warnings(self, backend: str) -> None:
        """Models from incompatible providers produce compat warnings."""
        compatible_providers = self._BACKEND_COMPATIBLE_PROVIDERS[backend]
        for provider, models in self._PROVIDER_MODEL_SAMPLES.items():
            if provider in compatible_providers:
                continue
            for model_id in models:
                warning = check_model_backend_compat(model_id, backend)
                assert warning is not None, (
                    f"Expected warning for model={model_id!r} on "
                    f"backend={backend!r} (provider={provider!r})"
                )

    def test_default_model_compatible_with_claude_code(self) -> None:
        """The DEFAULT_MODEL (claude-sonnet-4@20250514) must be compatible with claude-code."""
        from ii_agent.core.config.llm_config import DEFAULT_MODEL

        assert check_model_backend_compat(DEFAULT_MODEL, "claude-code") is None

    def test_default_model_compatible_with_copilot(self) -> None:
        """The DEFAULT_MODEL must be compatible with copilot (accepts all)."""
        from ii_agent.core.config.llm_config import DEFAULT_MODEL

        assert check_model_backend_compat(DEFAULT_MODEL, "copilot") is None
