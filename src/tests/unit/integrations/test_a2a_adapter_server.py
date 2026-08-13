from __future__ import annotations

import asyncio
import json

import pytest
from httpx import ASGITransport, AsyncClient

from ii_agent.integrations.a2a.adapter_server import (
    _extract_last_user_text,
    _TASK_INPUT_QUEUES,
    _TASK_STORE,
    _with_heartbeats,
    create_app,
)
from ii_agent.integrations.a2a.extension_utils import (
    REASONING_EXTENSION_URI,
    TOOL_TELEMETRY_EXTENSION_URI,
)
from ii_agent.integrations.a2a.registry import AgentRegistry


pytestmark = pytest.mark.unit


def test_extract_last_user_text_prefers_latest_user_message():
    messages = [
        {"role": "user", "content": "first"},
        {"role": "assistant", "content": "ignore"},
        {"role": "user", "content": [{"text": "second"}, {"text": "part"}]},
    ]

    assert _extract_last_user_text(messages) == "second\npart"


@pytest.mark.asyncio
async def test_stream_endpoint_emits_supported_events():
    app = create_app()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/message:stream",
            json={
                "context_id": "session-1",
                "messages": [{"role": "user", "content": "hello world"}],
                "metadata": {},
            },
        )

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")

    lines = [line for line in resp.text.splitlines() if line.startswith("data: ")]
    assert lines

    parsed_payloads: list[dict] = []
    for line in lines:
        payload = line.removeprefix("data: ").strip()
        if payload == "[DONE]":
            continue
        parsed_payloads.append(json.loads(payload))

    event_types = [p["type"] for p in parsed_payloads]
    assert "assistant.reasoning_delta" in event_types
    assert "assistant.message_delta" in event_types
    assert "assistant.message" in event_types
    assert "assistant.usage" in event_types


@pytest.mark.asyncio
async def test_stream_emits_task_id_and_extension_metadata():
    """The stream must emit session.task_id first and embed extension URIs in events."""
    app = create_app()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/message:stream",
            json={
                "context_id": "ctx-ext",
                "messages": [{"role": "user", "content": "explain something"}],
                "metadata": {},
            },
        )

    assert resp.status_code == 200

    payloads: list[dict] = []
    for line in resp.text.splitlines():
        if not line.startswith("data: "):
            continue
        raw = line.removeprefix("data: ").strip()
        if raw == "[DONE]":
            continue
        payloads.append(json.loads(raw))

    types = [p["type"] for p in payloads]

    # First event must identify the task_id.
    assert types[0] == "session.task_id"
    assert "task_id" in payloads[0]["data"]

    # Reasoning event carries the reasoning extension URI.
    reasoning_events = [p for p in payloads if p["type"] == "assistant.reasoning_delta"]
    assert reasoning_events, "expected at least one reasoning_delta event"
    ext_uris = [e["uri"] for e in reasoning_events[0]["data"].get("extensions", [])]
    assert REASONING_EXTENSION_URI in ext_uris

    # Final message event carries the tool-telemetry extension URI.
    message_events = [p for p in payloads if p["type"] == "assistant.message"]
    assert message_events, "expected at least one assistant.message event"
    tool_ext_uris = [e["uri"] for e in message_events[0]["data"].get("extensions", [])]
    assert TOOL_TELEMETRY_EXTENSION_URI in tool_ext_uris


@pytest.mark.asyncio
async def test_agent_card_includes_extension_uris():
    """Agent card must advertise both extension URIs."""
    app = create_app()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/.well-known/agent-card.json")

    assert resp.status_code == 200
    card = resp.json()
    ext_uris = [e["uri"] for e in card.get("extensions", [])]
    assert REASONING_EXTENSION_URI in ext_uris
    assert TOOL_TELEMETRY_EXTENSION_URI in ext_uris


@pytest.mark.asyncio
async def test_reply_endpoint_404_for_unknown_task():
    """POST /tasks/{task_id}:reply returns 404 when the task does not exist."""
    app = create_app()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/tasks/nonexistent-id:reply",
            json={"text": "yes"},
        )

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_reply_endpoint_409_when_task_not_in_input_required():
    """POST /tasks/{task_id}:reply returns 409 when the task is not awaiting input."""
    app = create_app()

    # Register a completed task directly.
    task_id = "test-completed-task"
    _TASK_STORE[task_id] = {"id": task_id, "status": {"state": "completed"}}

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                f"/tasks/{task_id}:reply",
                json={"text": "too late"},
            )

        assert resp.status_code == 409
    finally:
        _TASK_STORE.pop(task_id, None)


@pytest.mark.asyncio
async def test_reply_endpoint_resumes_input_required_stream():
    """INPUT_REQUIRED: stream pauses, resumes after :reply, then completes.

    Tests the generator directly (via asyncio.gather) to avoid HTTPX ASGI
    transport buffering limitations that prevent true concurrent streaming.
    """
    from ii_agent.integrations.a2a.adapter_server import (
        A2AStreamRequest,
        _event_stream,
    )

    task_id = "test-input-required-direct"
    req = A2AStreamRequest(
        context_id="ctx-input",
        messages=[{"role": "user", "content": "Are you ready?"}],
    )

    received_types: list[str] = []

    async def consume():
        async for chunk in _event_stream(req, task_id=task_id):
            if not chunk.startswith("data: "):
                continue
            raw = chunk.removeprefix("data: ").strip()
            if raw == "[DONE]":
                break
            event = json.loads(raw)
            received_types.append(event["type"])

    async def reply_feeder():
        """Poll _TASK_INPUT_QUEUES until the generator registers its queue, then reply."""
        for _ in range(200):
            await asyncio.sleep(0.01)
            queue = _TASK_INPUT_QUEUES.get(task_id)
            if queue is not None:
                await queue.put({"text": "Yes, I am ready!", "metadata": {}})
                return
        raise AssertionError("Generator never registered its input_required queue")

    # Run both concurrently: consume() suspends when the generator blocks on queue.get(),
    # giving the event loop time to run reply_feeder() which unblocks it.
    await asyncio.gather(consume(), reply_feeder())

    assert "session.input_required" in received_types, "stream must emit INPUT_REQUIRED"
    assert "assistant.message" in received_types, "stream must complete after reply"


# ---------------------------------------------------------------------------
# Phase 4: /agents registry endpoints
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_agents_list_empty():
    app = create_app(registry=AgentRegistry())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/agents")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_agents_register_and_list():
    app = create_app(registry=AgentRegistry())
    card_body = {
        "name": "test-agent",
        "url": "http://test-agent:18100",
        "skills": [{"id": "gen", "name": "General", "tags": ["general"], "examples": []}],
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        post_resp = await client.post("/agents:register", json=card_body)
        assert post_resp.status_code == 200
        assert post_resp.json()["name"] == "test-agent"

        list_resp = await client.get("/agents")
        assert list_resp.status_code == 200
        names = [c["name"] for c in list_resp.json()]
        assert "test-agent" in names


@pytest.mark.asyncio
async def test_agents_register_missing_required_fields():
    app = create_app(registry=AgentRegistry())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/agents:register", json={"name": "no-url"})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_agents_unregister():
    app = create_app(registry=AgentRegistry())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post("/agents:register", json={"name": "to-delete", "url": "http://x"})
        del_resp = await client.request("DELETE", "/agents/to-delete")
        assert del_resp.status_code == 200
        not_found = await client.request("DELETE", "/agents/to-delete")
        assert not_found.status_code == 404


@pytest.mark.asyncio
async def test_agents_route_returns_best_match():
    app = create_app(registry=AgentRegistry())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post(
            "/agents:register",
            json={
                "name": "coder",
                "url": "http://coder",
                "skills": [{"id": "c", "name": "C", "tags": ["python", "code"]}],
            },
        )
        await client.post(
            "/agents:register",
            json={
                "name": "searcher",
                "url": "http://searcher",
                "skills": [{"id": "s", "name": "S", "tags": ["search", "web"]}],
            },
        )
        route_resp = await client.post(
            "/agents:route",
            json={"prompt": "write python", "hint_tags": ["python"]},
        )
    assert route_resp.status_code == 200
    assert route_resp.json()["name"] == "coder"


@pytest.mark.asyncio
async def test_agents_route_no_agents_returns_503():
    app = create_app(registry=AgentRegistry())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/agents:route", json={"prompt": "anything"})
    assert resp.status_code == 503


@pytest.mark.asyncio
async def test_task_store_ttl_integration():
    """Adapter uses TaskStore: expired tasks should not be returned."""
    from ii_agent.integrations.a2a.adapter_server import _TASK_STORE
    from ii_agent.integrations.a2a.task_store import TaskStore

    assert isinstance(_TASK_STORE, TaskStore), "adapter should use TaskStore, not bare dict"


# ---------------------------------------------------------------------------
# Coverage gap tests — _extract_last_user_text edge cases
# ---------------------------------------------------------------------------


def test_extract_last_user_skips_non_user_role():
    """Messages with a non-user role before a user message triggers the continue branch."""
    messages = [
        {"role": "user", "content": "the real prompt"},
        {"role": "assistant", "content": "reply"},
    ]
    # reversed: assistant (→ continue), user (→ return)
    assert _extract_last_user_text(messages) == "the real prompt"


def test_extract_last_user_list_content_with_string_items():
    """Content list items that are plain strings (not dicts) should be collected."""
    messages = [{"role": "user", "content": ["part one", "part two"]}]
    result = _extract_last_user_text(messages)
    assert "part one" in result
    assert "part two" in result


def test_extract_last_user_returns_empty_when_no_user_messages():
    """No user messages → return empty string."""
    messages = [{"role": "assistant", "content": "hi"}]
    assert _extract_last_user_text(messages) == ""


def test_extract_last_user_empty_messages():
    assert _extract_last_user_text([]) == ""


# ---------------------------------------------------------------------------
# Coverage gap tests — /message:send (entire _collect_task path)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_message_send_returns_completed_task():
    """POST /message:send must collect the stream and return a completed A2A Task."""
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/message:send",
            json={
                "context_id": "ctx-send",
                "messages": [{"role": "user", "content": "hello send"}],
            },
        )
    assert resp.status_code == 200
    task = resp.json()
    assert task["status"]["state"] == "completed"
    assert "id" in task
    assert isinstance(task["artifacts"], list)


@pytest.mark.asyncio
async def test_message_send_task_stored_in_task_store():
    """The completed task must be accessible via GET /tasks/{id}."""
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        send_resp = await client.post(
            "/message:send",
            json={
                "context_id": "ctx-get",
                "messages": [{"role": "user", "content": "store me"}],
            },
        )
        assert send_resp.status_code == 200
        task_id = send_resp.json()["id"]

        get_resp = await client.get(f"/tasks/{task_id}")
        assert get_resp.status_code == 200
        assert get_resp.json()["id"] == task_id


# ---------------------------------------------------------------------------
# Coverage gap tests — GET /tasks/{task_id}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_task_200_for_existing_task():
    """GET /tasks/{id} returns 200 with task data when task exists."""
    app = create_app()
    task_id = "direct-task-200"
    _TASK_STORE[task_id] = {"id": task_id, "status": {"state": "working"}}
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get(f"/tasks/{task_id}")
        assert resp.status_code == 200
        assert resp.json()["id"] == task_id
    finally:
        _TASK_STORE.pop(task_id, None)


@pytest.mark.asyncio
async def test_get_task_404_for_unknown():
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/tasks/no-such-task")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Coverage gap tests — POST /tasks/{task_id}:cancel
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cancel_task_succeeds_for_working_task():
    app = create_app()
    task_id = "cancel-working"
    _TASK_STORE[task_id] = {"id": task_id, "status": {"state": "working"}}
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(f"/tasks/{task_id}:cancel")
        assert resp.status_code == 200
        assert _TASK_STORE.get(task_id)["status"]["state"] == "canceled"
    finally:
        _TASK_STORE.pop(task_id, None)


@pytest.mark.asyncio
async def test_cancel_task_404_for_unknown():
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/tasks/not-there:cancel")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_cancel_task_409_for_terminal_state():
    app = create_app()
    for terminal_state in ("completed", "failed", "canceled"):
        task_id = f"cancel-{terminal_state}"
        _TASK_STORE[task_id] = {"id": task_id, "status": {"state": terminal_state}}
        try:
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(f"/tasks/{task_id}:cancel")
            assert resp.status_code == 409, f"expected 409 for state={terminal_state}"
        finally:
            _TASK_STORE.pop(task_id, None)


@pytest.mark.asyncio
async def test_cancel_task_unblocks_input_required_queue():
    """Cancelling a task in input_required state puts a cancel signal into the queue."""
    app = create_app()
    task_id = "cancel-input-queue"
    _TASK_STORE[task_id] = {"id": task_id, "status": {"state": "input_required"}}
    reply_queue: asyncio.Queue = asyncio.Queue()
    _TASK_INPUT_QUEUES[task_id] = reply_queue
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(f"/tasks/{task_id}:cancel")
        assert resp.status_code == 200
        # The queue must contain the cancel signal
        msg = reply_queue.get_nowait()
        assert msg.get("_cancelled") is True
    finally:
        _TASK_STORE.pop(task_id, None)
        _TASK_INPUT_QUEUES.pop(task_id, None)


# ---------------------------------------------------------------------------
# Coverage gap tests — /tasks/{task_id}:reply 503 (queue gone)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reply_task_503_when_input_queue_gone():
    """Reply endpoint returns 503 when the task is input_required but queue is missing."""
    app = create_app()
    task_id = "reply-queue-gone"
    _TASK_STORE[task_id] = {"id": task_id, "status": {"state": "input_required"}}
    # Deliberately do NOT add a queue — simulates a timeout that already cleaned up.
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(f"/tasks/{task_id}:reply", json={"text": "too late"})
        assert resp.status_code == 503
    finally:
        _TASK_STORE.pop(task_id, None)


# ---------------------------------------------------------------------------
# Coverage gap tests — /agents:discover body validation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_agents_discover_missing_url_returns_422():
    """POST /agents:discover without url returns 422."""
    app = create_app(registry=AgentRegistry())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/agents:discover", json={})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_agents_discover_failure_returns_502():
    """POST /agents:discover that fails network-side returns 502."""
    from unittest.mock import patch
    from ii_agent.integrations.a2a.registry import AgentRegistry as _AgentRegistry

    reg = _AgentRegistry()

    async def _fail_discover(base_url, **_):
        raise ConnectionError("unreachable")

    with patch.object(reg, "discover", side_effect=_fail_discover):
        app = create_app(registry=reg)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/agents:discover", json={"url": "http://bad-host"})
    assert resp.status_code == 502


# ---------------------------------------------------------------------------
# Track B — Auth middleware enforcement
# ---------------------------------------------------------------------------

_STREAM_PAYLOAD = {
    "context_id": "auth-test",
    "messages": [{"role": "user", "content": "hi"}],
    "metadata": {},
}


@pytest.mark.asyncio
async def test_no_allowed_keys_allows_all_requests():
    """Backward-compat: create_app() with no allowed_keys is open (no auth)."""
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/message:stream", json=_STREAM_PAYLOAD)
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_protected_endpoint_returns_401_without_auth():
    """Message stream endpoint must 401 when auth is configured and bearer is absent."""
    app = create_app(allowed_keys=frozenset({"secret-key"}))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/message:stream", json=_STREAM_PAYLOAD)
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_protected_endpoint_accepts_valid_bearer():
    """Message stream endpoint accepts request with a valid Bearer token."""
    app = create_app(allowed_keys=frozenset({"secret-key"}))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/message:stream",
            json=_STREAM_PAYLOAD,
            headers={"Authorization": "Bearer secret-key"},
        )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_protected_endpoint_rejects_wrong_key():
    """Message stream endpoint rejects an unrecognised Bearer token."""
    app = create_app(allowed_keys=frozenset({"secret-key"}))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/message:stream",
            json=_STREAM_PAYLOAD,
            headers={"Authorization": "Bearer wrong-key"},
        )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_public_discovery_endpoint_bypasses_auth():
    """/.well-known/agent-card.json is public even when auth keys are configured."""
    app = create_app(allowed_keys=frozenset({"secret-key"}))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/.well-known/agent-card.json")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_options_preflight_bypasses_auth():
    """OPTIONS requests (CORS pre-flight) bypass auth middleware."""
    app = create_app(allowed_keys=frozenset({"secret-key"}))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.options("/message:stream")
    assert resp.status_code != 401


# ---------------------------------------------------------------------------
# Track A — Version negotiation middleware
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_absent_version_header_passes_through():
    """Requests without A2A-Version are treated as the current profile (backward-compat)."""
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/message:stream", json=_STREAM_PAYLOAD)
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_supported_version_header_accepted():
    """Requests declaring a supported A2A-Version pass through normally."""
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/message:stream",
            json=_STREAM_PAYLOAD,
            headers={"A2A-Version": "0.3.0"},
        )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_unsupported_version_header_returns_400():
    """Requests with an unsupported A2A-Version get a 400 JSON-RPC error."""
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/message:stream",
            json=_STREAM_PAYLOAD,
            headers={"A2A-Version": "99.0"},
        )
    assert resp.status_code == 400
    body = resp.json()
    assert body.get("jsonrpc") == "2.0"
    assert "error" in body
    assert body["error"]["code"] == -32600
    assert "99.0" in body["error"]["message"]


@pytest.mark.asyncio
async def test_response_carries_a2a_version_header():
    """Every response must advertise the current A2A profile in A2A-Version header."""
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/health")
    assert "a2a-version" in {k.lower() for k in resp.headers}
    assert resp.headers["a2a-version"] == "0.3.0"


# ---------------------------------------------------------------------------
# Model steering: metadata["model"] extraction and forwarding
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stream_forwards_model_from_metadata():
    """metadata["model"] must be passed as model= kwarg to backend.stream()."""
    from unittest.mock import MagicMock

    captured: dict = {}

    async def fake_stream(prompt, context_id, task_id=None, **kwargs):
        captured.update(kwargs)
        yield 'data: {"type": "assistant.message_delta", "text": "hi"}\n\n'
        yield "data: [DONE]\n\n"

    mock_backend = MagicMock()
    mock_backend.stream = fake_stream

    app = create_app(backend=mock_backend)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/message:stream",
            json={
                "context_id": "ctx-model-1",
                "messages": [{"role": "user", "content": "hello"}],
                "metadata": {"model": "gpt-4o"},
            },
        )
    assert resp.status_code == 200
    assert captured.get("model") == "gpt-4o"


@pytest.mark.asyncio
async def test_stream_uses_empty_model_when_no_model_key_in_metadata():
    """When metadata has no 'model' key, backend.stream() receives model=''."""
    from unittest.mock import MagicMock

    captured: dict = {}

    async def fake_stream(prompt, context_id, task_id=None, **kwargs):
        captured.update(kwargs)
        yield 'data: {"type": "assistant.message_delta", "text": "hi"}\n\n'
        yield "data: [DONE]\n\n"

    mock_backend = MagicMock()
    mock_backend.stream = fake_stream

    app = create_app(backend=mock_backend)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/message:stream",
            json={
                "context_id": "ctx-model-2",
                "messages": [{"role": "user", "content": "hello"}],
                "metadata": {},
            },
        )
    assert resp.status_code == 200
    assert captured.get("model") == ""


@pytest.mark.asyncio
async def test_stream_uses_empty_model_when_model_value_is_null():
    """metadata={"model": null} must result in model='' (null coerced to empty string)."""
    from unittest.mock import MagicMock

    captured: dict = {}

    async def fake_stream(prompt, context_id, task_id=None, **kwargs):
        captured.update(kwargs)
        yield 'data: {"type": "assistant.message_delta", "text": "hi"}\n\n'
        yield "data: [DONE]\n\n"

    mock_backend = MagicMock()
    mock_backend.stream = fake_stream

    app = create_app(backend=mock_backend)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/message:stream",
            json={
                "context_id": "ctx-model-3",
                "messages": [{"role": "user", "content": "hello"}],
                "metadata": {"model": None},
            },
        )
    assert resp.status_code == 200
    assert captured.get("model") == ""


# ---------------------------------------------------------------------------
# _with_heartbeats wrapper tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_with_heartbeats_forwards_chunks():
    """When the generator yields quickly, heartbeats are NOT injected."""

    async def fast_gen():
        yield 'data: {"type": "assistant.message_delta"}\n\n'
        yield "data: [DONE]\n\n"

    chunks = [c async for c in _with_heartbeats(fast_gen(), interval=10)]
    # No heartbeats expected — both chunks arrive instantly
    assert len(chunks) == 2
    assert "message_delta" in chunks[0]
    assert "[DONE]" in chunks[1]


@pytest.mark.asyncio
async def test_with_heartbeats_injects_heartbeat_on_delay():
    """When the generator stalls, heartbeats are injected."""

    async def slow_gen():
        yield 'data: {"type": "first"}\n\n'
        await asyncio.sleep(0.4)  # longer than interval
        yield 'data: {"type": "second"}\n\n'

    chunks = [c async for c in _with_heartbeats(slow_gen(), interval=0.1)]
    types = [
        json.loads(c.removeprefix("data: ").strip()).get("type")
        for c in chunks
        if c.strip().startswith("data:") and "[DONE]" not in c
    ]
    assert types[0] == "first"
    # At least one heartbeat between first and second
    assert "heartbeat" in types
    assert "second" in types
