from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
import types
import sys

import pytest

from ii_agent.agents.factory.agent import AgentFactory, _append_prompt_section
from ii_agent.agents.factory.tools import AgentType
from ii_agent.agents.inner_loop import A2AInnerLoop, NativeInnerLoop


def _make_factory_config(
    *,
    mode: str = "native",
    url: str | None = None,
    timeout: float = 22.0,
    fallback: bool = True,
    context_reuse: bool = True,
):
    agent = SimpleNamespace(
        inner_loop_mode=mode,
        a2a_agent_url=url,
        a2a_timeout_seconds=timeout,
        a2a_fallback_to_native=fallback,
        a2a_context_reuse=context_reuse,
    )
    return SimpleNamespace(agent=agent)


def test_build_inner_loop_strategy_native_mode_returns_native() -> None:
    factory = AgentFactory(_make_factory_config(mode="native"))

    strategy = factory._build_inner_loop_strategy()

    assert isinstance(strategy, NativeInnerLoop)


def test_build_inner_loop_strategy_a2a_no_sandbox_no_url_creates_deferred_a2a() -> None:
    """No sandbox, no config URL → deferred A2A with sandbox binding slot."""
    factory = AgentFactory(_make_factory_config(mode="a2a", url=None))

    strategy = factory._build_inner_loop_strategy(sandbox=None)

    assert isinstance(strategy, A2AInnerLoop)
    assert strategy.client._url_factory is not None
    assert strategy.client._static_url is None
    assert strategy._sandbox_ref == [None]


def test_build_inner_loop_strategy_a2a_deferred_also_works_without_sandbox_kwarg() -> None:
    """Same deferred path when sandbox kwarg is omitted entirely."""
    factory = AgentFactory(_make_factory_config(mode="a2a", url=None))

    strategy = factory._build_inner_loop_strategy()

    assert isinstance(strategy, A2AInnerLoop)
    assert strategy._sandbox_ref == [None]


def test_build_inner_loop_strategy_a2a_with_sandbox_uses_url_factory() -> None:
    """Sandbox present → A2AInnerLoop backed by a lazy url_factory (not static URL)."""
    from unittest.mock import AsyncMock, MagicMock

    factory = AgentFactory(
        _make_factory_config(mode="a2a", url=None, timeout=9.0, fallback=True, context_reuse=False)
    )
    sandbox = MagicMock()
    sandbox.expose_port = AsyncMock(return_value="http://host:18100")

    strategy = factory._build_inner_loop_strategy(sandbox=sandbox)

    assert isinstance(strategy, A2AInnerLoop)
    # Static URL is None — URL will be resolved lazily via factory.
    assert strategy.client._static_url is None
    assert strategy.client._url_factory is not None
    assert strategy.client._timeout.connect == 9.0
    assert strategy.client._timeout.read == 120.0
    assert strategy.fallback_to_native is True
    assert strategy.context_reuse is False


def test_build_inner_loop_strategy_a2a_with_url_no_sandbox_uses_deferred_not_static() -> None:
    """When a2a_agent_url is set but no sandbox is provided, the factory MUST
    use the deferred sandbox path — NOT the static URL.  Agent sessions always
    create per-sandbox adapters whose env vars carry session-specific config
    (e.g. long-horizon timeouts for deep_research).  Using the static sidecar
    URL would bypass per-sandbox timeouts.

    Regression test for: Copilot CLI timed out after 900s on a deep_research
    session because the factory short-circuited to the shared sidecar adapter
    (a2a_agent_url) instead of the per-sandbox adapter that had the 3600s
    long-horizon timeout.
    """
    factory = AgentFactory(
        _make_factory_config(
            mode="a2a",
            url="http://a2a-adapter:18100",
            timeout=12.5,
            fallback=False,
            context_reuse=False,
        )
    )

    strategy = factory._build_inner_loop_strategy(sandbox=None)

    assert isinstance(strategy, A2AInnerLoop)
    # Must be deferred (url_factory), NOT static URL to the sidecar.
    assert strategy.client._static_url is None
    assert strategy.client._url_factory is not None
    assert strategy._sandbox_ref == [None]
    assert strategy.fallback_to_native is False
    assert strategy.context_reuse is False
    assert strategy.client._timeout.connect == 12.5
    assert strategy.client._timeout.read == 120.0


def test_append_prompt_section_behaviors() -> None:
    assert _append_prompt_section(None, None) is None
    assert _append_prompt_section("base", None) == "base"
    assert _append_prompt_section(None, "extra") == "extra"
    assert _append_prompt_section("base", "extra") == "base\n\nextra"


@pytest.mark.asyncio
async def test_deferred_url_factory_raises_before_sandbox_bound() -> None:
    """The deferred URL factory raises RuntimeError if sandbox was never wired."""
    factory = AgentFactory(_make_factory_config(mode="a2a", url=None))
    strategy = factory._build_inner_loop_strategy()
    assert isinstance(strategy, A2AInnerLoop)

    with pytest.raises(RuntimeError, match="sandbox not yet initialized"):
        await strategy.client._resolve_url()


@pytest.mark.asyncio
async def test_deferred_url_factory_resolves_after_sandbox_bound() -> None:
    """After binding a sandbox to _sandbox_ref, the URL factory resolves correctly."""
    factory = AgentFactory(_make_factory_config(mode="a2a", url=None, timeout=5.0))
    strategy = factory._build_inner_loop_strategy()
    assert isinstance(strategy, A2AInnerLoop)

    sandbox = MagicMock()
    sandbox.expose_port = AsyncMock(return_value="http://host:18100")
    strategy._sandbox_ref[0] = sandbox

    url = await strategy.client._resolve_url()
    assert url == "http://host:18100"
    sandbox.expose_port.assert_awaited_once()


def test_agent_sandbox_setter_wires_deferred_strategy() -> None:
    """IIAgent.sandbox setter populates _sandbox_ref on a deferred A2A strategy."""
    from ii_agent.agents.agent import IIAgent
    from ii_agent.agents.inner_loop import A2AInnerLoop

    fake_client = MagicMock()
    strategy = A2AInnerLoop(client=fake_client, fallback_to_native=True)
    assert strategy._sandbox_ref == [None]

    fake_model = MagicMock()
    fake_model.id = "test-model"
    agent = IIAgent(
        user_id="u",
        session_id="s",
        model=fake_model,
        inner_loop_strategy=strategy,
    )

    sandbox = MagicMock()
    agent.sandbox = sandbox

    assert strategy._sandbox_ref[0] is sandbox
    assert agent._sandbox is sandbox


def test_agent_sandbox_setter_noop_for_native_strategy() -> None:
    """Setting sandbox on an agent with NativeInnerLoop does not error."""
    from ii_agent.agents.agent import IIAgent

    fake_model = MagicMock()
    fake_model.id = "test-model"
    agent = IIAgent(
        user_id="u",
        session_id="s",
        model=fake_model,
        inner_loop_strategy=NativeInnerLoop(),
    )

    sandbox = MagicMock()
    agent.sandbox = sandbox  # should not raise
    assert agent._sandbox is sandbox


@pytest.mark.asyncio
async def test_create_agent_with_system_prompt_sets_agent_fields() -> None:
    factory = AgentFactory(_make_factory_config(mode="native"))
    llm_config = SimpleNamespace(provider="anthropic")
    fake_model = SimpleNamespace(id="m-1", name="Model One")

    with (
        patch("ii_agent.agents.factory.agent.get_model", return_value=fake_model),
        patch("ii_agent.agents.factory.agent.AgentToolManager.resolve_tools", return_value=[]),
        patch("ii_agent.agents.factory.agent.AgentToolManager.log_tool_summary"),
        patch("ii_agent.agents.factory.agent.IIAgent") as mock_agent_cls,
    ):
        fake_agent = MagicMock()
        mock_agent_cls.return_value = fake_agent

        agent = await factory.create_agent(
            user_id="user-1",
            session_id="session-1",
            llm_config=llm_config,
            system_prompt="custom prompt",
            metadata={"k": "v"},
        )

    assert agent is fake_agent
    kwargs = mock_agent_cls.call_args.kwargs
    assert kwargs["name"] == "general_agent"
    assert kwargs["system_message"] == "custom prompt"
    assert kwargs["metadata"] == {"k": "v"}
    assert kwargs["sub_agents"] == []
    assert isinstance(kwargs["inner_loop_strategy"], NativeInnerLoop)
    fake_agent.set_id.assert_called_once()


@pytest.mark.asyncio
async def test_create_agent_appends_skill_prompt_and_adds_skill_tool() -> None:
    factory = AgentFactory(_make_factory_config(mode="native"))
    llm_config = SimpleNamespace(provider="anthropic")
    fake_model = SimpleNamespace(id="m-2", name="Model Two")

    skill_tool = MagicMock()
    skill_tool.description = "<skill-rules/>"
    skill_tool._skills_registry = ["one", "two"]
    skill_creator = MagicMock()
    skill_creator.create_skill_tool = AsyncMock(return_value=skill_tool)

    with (
        patch("ii_agent.agents.factory.agent.get_model", return_value=fake_model),
        patch("ii_agent.agents.factory.agent.AgentToolManager.resolve_tools", return_value=[]),
        patch("ii_agent.agents.factory.agent.AgentToolManager.log_tool_summary"),
        patch("ii_agent.agents.factory.agent.IIAgent") as mock_agent_cls,
    ):
        fake_agent = MagicMock()
        mock_agent_cls.return_value = fake_agent

        await factory.create_agent(
            user_id="user-2",
            session_id="session-2",
            llm_config=llm_config,
            system_prompt="base prompt",
            skill_creator=skill_creator,
        )

    kwargs = mock_agent_cls.call_args.kwargs
    assert kwargs["tools"] == [skill_tool]
    assert kwargs["system_message"] == "base prompt\n\n<skill-rules/>"


@pytest.mark.asyncio
async def test_create_agent_with_task_agent_adds_sub_agent() -> None:
    factory = AgentFactory(_make_factory_config(mode="native"))
    llm_config = SimpleNamespace(provider="anthropic")
    fake_model = SimpleNamespace(id="m-3", name="Model Three")
    task_sub_agent = MagicMock(name="task-sub-agent")

    with (
        patch("ii_agent.agents.factory.agent.get_model", return_value=fake_model),
        patch("ii_agent.agents.factory.agent.AgentToolManager.resolve_tools", return_value=[]),
        patch("ii_agent.agents.factory.agent.AgentToolManager.log_tool_summary"),
        patch.object(factory, "create_task_agent_tool", new=AsyncMock(return_value=task_sub_agent)),
        patch("ii_agent.agents.factory.agent.IIAgent") as mock_agent_cls,
    ):
        fake_agent = MagicMock()
        mock_agent_cls.return_value = fake_agent

        await factory.create_agent(
            user_id="user-3",
            session_id="session-3",
            llm_config=llm_config,
            system_prompt="prompt",
            tool_args={"task_agent": True},
        )

    kwargs = mock_agent_cls.call_args.kwargs
    assert kwargs["sub_agents"] == [task_sub_agent]


@pytest.mark.asyncio
async def test_create_task_agent_tool_builds_task_agent() -> None:
    factory = AgentFactory(_make_factory_config(mode="native"))
    llm_config = SimpleNamespace(provider="anthropic")
    fake_model = SimpleNamespace(id="task-model", name="Task Model")

    with (
        patch("ii_agent.agents.factory.agent.get_model", return_value=fake_model),
        patch(
            "ii_agent.agents.factory.agent.AgentToolManager.resolve_tools", return_value=["tool-a"]
        ),
        patch("ii_agent.agents.factory.agent.IIAgent") as mock_agent_cls,
    ):
        task_agent_instance = MagicMock()
        mock_agent_cls.return_value = task_agent_instance

        result = await factory.create_task_agent_tool(
            user_id="user-task",
            session_id="session-task",
            llm_config=llm_config,
            tool_args={"any": True},
        )

    assert result is task_agent_instance
    kwargs = mock_agent_cls.call_args.kwargs
    assert kwargs["user_id"] == "user-task"
    assert kwargs["session_id"] == "session-task"
    assert kwargs["model"] == fake_model
    assert kwargs["tools"] == ["tool-a"]
    assert kwargs["stream"] is True
    assert kwargs["stream_events"] is True
    assert kwargs["store_events"] is False


def test_get_agent_config_delegates_to_manager() -> None:
    factory = AgentFactory(_make_factory_config(mode="native"))
    marker = object()

    with patch("ii_agent.agents.factory.agent.AgentConfigManager.get_config", return_value=marker):
        result = factory.get_agent_config(AgentType.GENERAL)

    assert result is marker


@pytest.mark.asyncio
async def test_create_general_agent_delegates_to_create_agent() -> None:
    factory = AgentFactory(_make_factory_config(mode="native"))
    llm_config = SimpleNamespace(provider="anthropic")
    expected_agent = MagicMock()

    with patch.object(
        factory, "create_agent", new=AsyncMock(return_value=expected_agent)
    ) as mock_create:
        result = await factory.create_general_agent(
            user_id="u-1",
            session_id="s-1",
            llm_config=llm_config,
        )

    assert result is expected_agent
    assert mock_create.await_args.kwargs["agent_type"] == AgentType.GENERAL


@pytest.mark.asyncio
async def test_create_agent_generates_system_prompt_from_flags_and_workspace() -> None:
    factory = AgentFactory(_make_factory_config(mode="native"))
    llm_config = SimpleNamespace(provider="anthropic")
    fake_model = SimpleNamespace(id="m-4", name="Model Four")
    workspace_manager = SimpleNamespace(
        workspace_path=SimpleNamespace(as_posix=lambda: "/workspace/custom")
    )

    with (
        patch("ii_agent.agents.factory.agent.get_model", return_value=fake_model),
        patch("ii_agent.agents.factory.agent.AgentToolManager.resolve_tools", return_value=[]),
        patch("ii_agent.agents.factory.agent.AgentToolManager.log_tool_summary"),
        patch(
            "ii_agent.agents.factory.agent.get_system_prompt_for_agent_type",
            new=AsyncMock(return_value="generated-prompt"),
        ) as mock_prompt,
        patch("ii_agent.agents.factory.agent.IIAgent") as mock_agent_cls,
    ):
        fake_agent = MagicMock()
        mock_agent_cls.return_value = fake_agent

        await factory.create_agent(
            user_id="user-4",
            session_id="session-4",
            llm_config=llm_config,
            system_prompt=None,
            workspace_manager=workspace_manager,
            tool_args={"deep_research": True, "design_document": True, "media_generation": True},
            metadata={"meta": "yes"},
        )

    prompt_kwargs = mock_prompt.await_args.kwargs
    assert prompt_kwargs["workspace_path"] == "/workspace/custom"
    assert prompt_kwargs["researcher"] is True
    assert prompt_kwargs["design_document"] is True
    assert prompt_kwargs["media"] is True
    assert prompt_kwargs["a2a_agents"] is False
    assert prompt_kwargs["provider"] == "anthropic"

    kwargs = mock_agent_cls.call_args.kwargs
    assert kwargs["system_message"] == "generated-prompt"


@pytest.mark.asyncio
async def test_create_agent_adds_connector_tools_when_present() -> None:
    factory = AgentFactory(_make_factory_config(mode="native"))
    llm_config = SimpleNamespace(provider="anthropic")
    fake_model = SimpleNamespace(id="m-5", name="Model Five")
    base_tool = MagicMock(name="base-tool")
    connector_tool_1 = MagicMock(name="connector-1")
    connector_tool_2 = MagicMock(name="connector-2")

    connector_loader = MagicMock()
    connector_loader.create_connector_tools = AsyncMock(
        return_value=[connector_tool_1, connector_tool_2]
    )

    with (
        patch("ii_agent.agents.factory.agent.get_model", return_value=fake_model),
        patch(
            "ii_agent.agents.factory.agent.AgentToolManager.resolve_tools", return_value=[base_tool]
        ),
        patch("ii_agent.agents.factory.agent.AgentToolManager.log_tool_summary"),
        patch("ii_agent.agents.factory.agent.IIAgent") as mock_agent_cls,
    ):
        mock_agent_cls.return_value = MagicMock()

        await factory.create_agent(
            user_id="user-5",
            session_id="session-5",
            llm_config=llm_config,
            system_prompt="prompt",
            connector_tool=connector_loader,
            workspace_manager=SimpleNamespace(),
        )

    kwargs = mock_agent_cls.call_args.kwargs
    assert kwargs["tools"] == [base_tool, connector_tool_1, connector_tool_2]


@pytest.mark.asyncio
async def test_create_agent_connector_loader_exception_is_non_fatal() -> None:
    factory = AgentFactory(_make_factory_config(mode="native"))
    llm_config = SimpleNamespace(provider="anthropic")
    fake_model = SimpleNamespace(id="m-6", name="Model Six")
    base_tool = MagicMock(name="base-tool")

    connector_loader = MagicMock()
    connector_loader.create_connector_tools = AsyncMock(side_effect=RuntimeError("connector boom"))

    with (
        patch("ii_agent.agents.factory.agent.get_model", return_value=fake_model),
        patch(
            "ii_agent.agents.factory.agent.AgentToolManager.resolve_tools", return_value=[base_tool]
        ),
        patch("ii_agent.agents.factory.agent.AgentToolManager.log_tool_summary"),
        patch("ii_agent.agents.factory.agent.IIAgent") as mock_agent_cls,
    ):
        mock_agent_cls.return_value = MagicMock()

        await factory.create_agent(
            user_id="user-6",
            session_id="session-6",
            llm_config=llm_config,
            system_prompt="prompt",
            connector_tool=connector_loader,
        )

    kwargs = mock_agent_cls.call_args.kwargs
    assert kwargs["tools"] == [base_tool]


@pytest.mark.asyncio
async def test_create_researcher_agent_tool_builds_researcher_agent() -> None:
    factory = AgentFactory(_make_factory_config(mode="native"))
    context_manager = MagicMock()
    event_stream = MagicMock()
    user_client = SimpleNamespace(model_name="model-x")

    class FakeResearcherAgent:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    fake_mod = types.ModuleType("ii_agent.sub_agent.researcher_agent_tool")
    fake_mod.ResearcherAgent = FakeResearcherAgent

    with (
        patch.dict(sys.modules, {"ii_agent.sub_agent.researcher_agent_tool": fake_mod}),
        patch(
            "ii_agent.agents.factory.agent.AgentToolManager.resolve_tools", return_value=["r-tool"]
        ),
        patch("ii_agent.agents.factory.agent.AgentToolManager.log_tool_summary"),
    ):
        agent = await factory.create_researcher_agent_tool(
            context_manager=context_manager,
            event_stream=event_stream,
            max_turns=33,
            user_client=user_client,
            session_id="sess-x",
            run_id="run-x",
        )

    assert agent.kwargs["tools"] == ["r-tool"]
    assert agent.kwargs["context_manager"] is context_manager
    assert agent.kwargs["event_stream"] is event_stream
    assert agent.kwargs["max_turns"] == 33
    assert agent.kwargs["user_client"] is user_client


@pytest.mark.asyncio
async def test_create_codex_agent_tool_success_and_failure_paths() -> None:
    factory = AgentFactory(SimpleNamespace(agent=_make_factory_config().agent, codex_port=6065))

    class FakeCodexAgent:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    fake_mod = types.ModuleType("ii_agent.sub_agent.codex")
    fake_mod.CodexAgent = FakeCodexAgent

    sandbox = MagicMock()
    sandbox.expose_port = AsyncMock(return_value="http://localhost:31234")
    event_stream = MagicMock()

    # Success (200)
    with (
        patch.dict(sys.modules, {"ii_agent.sub_agent.codex": fake_mod}),
        patch("httpx.AsyncClient") as mock_httpx_cls,
    ):
        mock_client = AsyncMock()
        mock_client.get.return_value = SimpleNamespace(status_code=200)
        mock_httpx_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_httpx_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await factory.create_codex_agent_tool(
            sandbox=sandbox,
            event_stream=event_stream,
            session_id="sess-c",
            run_id="run-c",
        )

    assert result.kwargs["event_stream"] is event_stream
    assert result.kwargs["codex_url"] == "http://localhost:31234/messages"

    # Unhealthy response
    with (
        patch.dict(sys.modules, {"ii_agent.sub_agent.codex": fake_mod}),
        patch("httpx.AsyncClient") as mock_httpx_cls,
    ):
        mock_client = AsyncMock()
        mock_client.get.return_value = SimpleNamespace(status_code=503)
        mock_httpx_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_httpx_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        unhealthy = await factory.create_codex_agent_tool(
            sandbox=sandbox,
            event_stream=event_stream,
            session_id="sess-c",
            run_id="run-c",
        )

    assert unhealthy is None

    # Exception path
    sandbox.expose_port = AsyncMock(side_effect=RuntimeError("no port"))
    with patch.dict(sys.modules, {"ii_agent.sub_agent.codex": fake_mod}):
        failed = await factory.create_codex_agent_tool(
            sandbox=sandbox,
            event_stream=event_stream,
            session_id="sess-c",
            run_id="run-c",
        )

    assert failed is None
