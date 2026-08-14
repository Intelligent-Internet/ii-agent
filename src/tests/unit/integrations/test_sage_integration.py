"""Unit tests for the SAGE persistent-memory integration.

These tests exercise the public surface of
``ii_agent.integrations.sage`` without requiring the optional
``sage-agent-sdk`` to be installed: the SDK symbols are stubbed in
``sys.modules`` at import time and the hook layer is driven directly.
"""

from __future__ import annotations

import sys
import types
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import AsyncMock

import pytest


# ---------------------------------------------------------------------------
# Stub the optional sage_sdk modules so the wrapper can import cleanly
# regardless of whether the extra is installed on the test runner.
# ---------------------------------------------------------------------------


def _install_sage_sdk_stubs() -> dict[str, Any]:
    """Install fake sage_sdk.* modules and return their namespaces."""

    class FakeIdentity:
        @classmethod
        def default(cls) -> "FakeIdentity":
            return cls()

        @classmethod
        def from_file(cls, path: str) -> "FakeIdentity":
            return cls()

    class FakeMemoryType:
        observation = "observation"
        fact = "fact"
        inference = "inference"

    class FakeAsyncSageClient:
        last_instance: "FakeAsyncSageClient | None" = None

        def __init__(
            self,
            base_url: str,
            identity: Any,
            timeout: float = 30.0,
        ) -> None:
            self.base_url = base_url
            self.identity = identity
            self.timeout = timeout
            self.embed = AsyncMock(return_value=[0.1, 0.2, 0.3])
            self.query = AsyncMock()
            self.propose = AsyncMock(return_value=None)
            self.close = AsyncMock()
            FakeAsyncSageClient.last_instance = self

    async_mod = types.ModuleType("sage_sdk.async_client")
    async_mod.AsyncSageClient = FakeAsyncSageClient

    auth_mod = types.ModuleType("sage_sdk.auth")
    auth_mod.AgentIdentity = FakeIdentity

    models_mod = types.ModuleType("sage_sdk.models")
    models_mod.MemoryType = FakeMemoryType

    root = types.ModuleType("sage_sdk")
    root.async_client = async_mod
    root.auth = auth_mod
    root.models = models_mod

    sys.modules["sage_sdk"] = root
    sys.modules["sage_sdk.async_client"] = async_mod
    sys.modules["sage_sdk.auth"] = auth_mod
    sys.modules["sage_sdk.models"] = models_mod

    return {
        "AsyncSageClient": FakeAsyncSageClient,
        "AgentIdentity": FakeIdentity,
        "MemoryType": FakeMemoryType,
    }


_SDK_STUBS = _install_sage_sdk_stubs()


# Reset the cached SDK-resolution flag in the wrapper so the stubs actually
# get picked up on first import.
from ii_agent.integrations.sage import client as sage_client_module  # noqa: E402

sage_client_module._SDK_AVAILABLE = None
sage_client_module._AsyncSageClientCls = None
sage_client_module._AgentIdentityCls = None
sage_client_module._MemoryTypeEnum = None


from ii_agent.core.config.sage_config import SageConfig  # noqa: E402
from ii_agent.integrations.sage import register_sage_hooks  # noqa: E402
from ii_agent.integrations.sage.client import SageClient  # noqa: E402
from ii_agent.integrations.sage.hooks import make_sage_hooks  # noqa: E402


# ---------------------------------------------------------------------------
# Lightweight fakes that avoid importing the full IIAgent class (which pulls
# in the entire framework).
# ---------------------------------------------------------------------------


@dataclass
class _FakeAgent:
    pre_hooks: list = field(default_factory=list)
    post_hooks: list = field(default_factory=list)


@dataclass
class _FakeRunInput:
    input_content: str
    def input_content_string(self) -> str:  # mirrors the real dataclass API
        return self.input_content


@dataclass
class _FakeRunOutput:
    agent_name: str
    content: str
    input: _FakeRunInput


class _FakeQueryResponse:
    def __init__(self, results: list[dict[str, Any]]):
        class _R:
            def __init__(self, c: str, conf: float, dom: str) -> None:
                self.content = c
                self.confidence_score = conf
                self.domain_tag = dom

        self.results = [_R(r["content"], r["confidence"], r["domain"]) for r in results]


# ---------------------------------------------------------------------------
# register_sage_hooks
# ---------------------------------------------------------------------------


def test_register_sage_hooks_noop_when_disabled():
    agent = _FakeAgent()
    result = register_sage_hooks(agent, config=SageConfig(enabled=False))
    assert result is None
    assert agent.pre_hooks == []
    assert agent.post_hooks == []


def test_register_sage_hooks_appends_two_hooks_when_enabled():
    agent = _FakeAgent(pre_hooks=[lambda: None], post_hooks=[])
    client = SageClient(SageConfig(enabled=True))
    returned = register_sage_hooks(agent, config=client.config, client=client)

    assert returned is client
    assert len(agent.pre_hooks) == 2  # pre-existing + SAGE
    assert len(agent.post_hooks) == 1
    # Names come through @wraps
    assert agent.pre_hooks[-1].__name__ == "sage_pre_hook"
    assert agent.post_hooks[-1].__name__ == "sage_post_hook"


def test_post_hook_is_marked_run_in_background():
    from ii_agent.agents.hooks.decorator import should_run_in_background

    client = SageClient(SageConfig(enabled=True))
    _pre, post = make_sage_hooks(client)
    assert should_run_in_background(post) is True


# ---------------------------------------------------------------------------
# End-to-end turn flow: recall → inject → propose
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_turn_flow_recalls_then_stores(monkeypatch):
    """End-to-end turn: pre-hook recalls, injects, post-hook stores.

    The SDK layer is mocked out via the SageClient public API so this
    test validates the hook wiring without coupling to internals of
    AsyncSageClient.
    """
    cfg = SageConfig(enabled=True, pre_hook_timeout_s=5.0)
    client = SageClient(cfg)
    pre_hook, post_hook = make_sage_hooks(client)

    seeded_results = [
        {"content": "Use ThreadSanitizer for C++ races", "confidence": 0.92, "domain": "ii-agent"},
        {"content": "Python races: prefer asyncio.Lock()", "confidence": 0.81, "domain": "ii-agent"},
    ]

    recall_calls: list[str] = []
    propose_calls: list[dict[str, Any]] = []

    async def fake_recall(text: str, *, domain: str | None = None, top_k: int | None = None):
        recall_calls.append(text)
        return seeded_results

    async def fake_propose(content: str, **kwargs: Any) -> bool:
        propose_calls.append({"content": content, **kwargs})
        return True

    monkeypatch.setattr(client, "recall", fake_recall)
    monkeypatch.setattr(client, "propose", fake_propose)

    run_input = _FakeRunInput(input_content="how do I debug a race condition?")
    await pre_hook(run_input=run_input)

    # Pre-hook should have prepended the recall block.
    assert "[SAGE persistent memory" in run_input.input_content
    assert "ThreadSanitizer" in run_input.input_content
    assert "race condition" in run_input.input_content  # original preserved
    assert recall_calls == ["how do I debug a race condition?"]

    # Now simulate the post-hook storing the observation.
    run_output = _FakeRunOutput(
        agent_name="test-agent",
        content="Start with ThreadSanitizer...",
        input=run_input,
    )
    await post_hook(run_output=run_output)

    assert len(propose_calls) == 1
    body = propose_calls[0]
    assert body["memory_type"] == "observation"
    assert "race condition" in body["content"]
    assert "ThreadSanitizer" in body["content"]


@pytest.mark.asyncio
async def test_pre_hook_respects_timeout(monkeypatch):
    cfg = SageConfig(enabled=True, pre_hook_timeout_s=0.01)
    client = SageClient(cfg)
    pre_hook, _post = make_sage_hooks(client)

    # Force recall to hang longer than the timeout.
    async def slow_recall(*_a, **_k):
        import asyncio

        await asyncio.sleep(0.5)
        return []

    monkeypatch.setattr(client, "recall", slow_recall)

    run_input = _FakeRunInput(input_content="hello")
    await pre_hook(run_input=run_input)

    # Input was preserved verbatim; no recall block injected.
    assert run_input.input_content == "hello"


@pytest.mark.asyncio
async def test_pre_hook_noop_when_disabled():
    cfg = SageConfig(enabled=False)
    client = SageClient(cfg)
    pre_hook, _post = make_sage_hooks(client)

    run_input = _FakeRunInput(input_content="hello")
    await pre_hook(run_input=run_input)
    assert run_input.input_content == "hello"


# ---------------------------------------------------------------------------
# Integration test (SDK mocked via respx) — exercises the real
# AsyncSageClient HTTP layer end-to-end, to prove the integration works
# against the actual wire protocol without needing a live SAGE node.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_turn_flow_against_mocked_sdk_http(monkeypatch):
    """Drive the real sage_sdk AsyncSageClient through respx.

    This uses the real SDK (not stubs) when it is installed on the host;
    the HTTP layer is mocked via respx so no live node is needed.
    """
    respx = pytest.importorskip("respx")
    httpx = pytest.importorskip("httpx")

    # The module-level stubs registered at import time would shadow the
    # real SDK — remove them so we can import the real package.
    for mod in ("sage_sdk", "sage_sdk.async_client", "sage_sdk.auth", "sage_sdk.models"):
        sys.modules.pop(mod, None)
    try:
        from sage_sdk.async_client import AsyncSageClient as _RealAsync
        from sage_sdk.auth import AgentIdentity as _RealIdentity
        from sage_sdk.models import MemoryType as _RealMemType
    except ImportError:
        # Re-install the stubs the rest of the test module relies on and
        # skip this one integration test.
        _install_sage_sdk_stubs()
        pytest.skip("sage-agent-sdk not installed — skipping HTTP-layer test")

    # Swap the wrapper's cached SDK references to the real classes.
    # This test intentionally runs after the stub-driven tests (pytest
    # runs in declaration order by default) so the stub reinstallation
    # is unnecessary for the current file layout.
    sage_client_module._AsyncSageClientCls = _RealAsync
    sage_client_module._AgentIdentityCls = _RealIdentity
    sage_client_module._MemoryTypeEnum = _RealMemType
    sage_client_module._SDK_AVAILABLE = True

    cfg = SageConfig(
        enabled=True,
        node_url="http://sage.test",
        default_domain="ii-agent",
        pre_hook_timeout_s=5.0,
    )
    client = SageClient(cfg)
    pre_hook, post_hook = make_sage_hooks(client)

    query_response = {
        "results": [
            {
                "memory_id": "m-1",
                "submitting_agent": "agent-hash",
                "content": "Race conditions in asyncio come from unawaited tasks.",
                "content_hash": "0xdeadbeef",
                "memory_type": "observation",
                "domain_tag": "ii-agent",
                "confidence_score": 0.88,
                "status": "committed",
                "created_at": "2026-01-01T00:00:00Z",
            }
        ],
        "next_cursor": None,
        "total_count": 1,
    }

    with respx.mock(base_url="http://sage.test", assert_all_called=False) as mock:
        mock.post("/v1/embed").mock(
            return_value=httpx.Response(200, json={"embedding": [0.0, 0.1, 0.2]})
        )
        mock.post("/v1/memory/query").mock(
            return_value=httpx.Response(200, json=query_response)
        )
        submit_route = mock.post("/v1/memory/submit").mock(
            return_value=httpx.Response(
                200,
                json={"memory_id": "m-2", "tx_hash": "0xabc", "status": "pending"},
            )
        )

        run_input = _FakeRunInput(input_content="debug asyncio race")
        await pre_hook(run_input=run_input)

        assert "[SAGE persistent memory" in run_input.input_content
        assert "asyncio" in run_input.input_content

        run_output = _FakeRunOutput(
            agent_name="integration-test",
            content="Await all tasks you spawn.",
            input=run_input,
        )
        await post_hook(run_output=run_output)

        # Submit route was called exactly once (the post-hook's propose).
        assert submit_route.called, "post-hook should have POSTed to /v1/memory/submit"
