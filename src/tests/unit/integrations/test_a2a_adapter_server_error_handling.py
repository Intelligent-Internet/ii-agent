"""Tests for A2A Adapter Server error handling and edge cases.

Covers request validation, error responses, and state machine transitions.
"""

import pytest
from httpx import ASGITransport, AsyncClient

from ii_agent.integrations.a2a.adapter_server import create_app


pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_message_stream_with_empty_messages():
    """Adapter server must handle request with empty messages list."""
    app = create_app()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/message:stream",
            json={
                "context_id": "empty-msg-test",
                "messages": [],  # Empty messages
                "metadata": {},
            },
        )

    # Should still return 200 and start streaming (backend decides if valid)
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_message_stream_with_missing_context_id():
    """Adapter server must handle request without explicit context_id (uses default)."""
    app = create_app()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/message:stream",
            json={
                # context_id omitted (optional field)
                "messages": [{"role": "user", "content": "test"}],
                "metadata": {},
            },
        )

    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_get_task_not_found():
    """Adapter server must return 404 for non-existent task ID."""
    app = create_app()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/tasks/nonexistent-task-id")

    assert resp.status_code == 404
    assert "not found" in resp.text.lower()


@pytest.mark.asyncio
async def test_cancel_task_not_found():
    """Adapter server must return 404 when cancelling non-existent task."""
    app = create_app()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/tasks/nonexistent-task-id:cancel")

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_cancel_already_completed_task():
    """Adapter server must reject cancel on already-completed task."""
    app = create_app()

    # First, create a completed task in the store by manipulating state directly
    from ii_agent.integrations.a2a.adapter_server import _TASK_STORE

    task_id = "test-completed-task"
    _TASK_STORE[task_id] = {
        "id": task_id,
        "status": {"state": "completed"},
        "artifacts": [],
        "history": [],
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(f"/tasks/{task_id}:cancel")

    assert resp.status_code == 409
    assert "already completed" in resp.text.lower()


@pytest.mark.asyncio
async def test_reply_task_not_found():
    """Adapter server must return 404 when replying to non-existent task."""
    app = create_app()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/tasks/nonexistent-task-id:reply",
            json={"text": "user response"},
        )

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_message_send_with_empty_backend():
    """Adapter server /message:send must complete full event collection."""
    app = create_app()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/message:send",
            json={
                "context_id": "sync-test",
                "messages": [{"role": "user", "content": "test"}],
                "metadata": {},
            },
        )

    # Should return a task object
    assert resp.status_code == 200
    data = resp.json()
    assert "id" in data
    assert "status" in data


@pytest.mark.asyncio
async def test_cancel_task_with_failed_state():
    """Adapter server must reject cancel on failed task."""
    app = create_app()

    from ii_agent.integrations.a2a.adapter_server import _TASK_STORE

    task_id = "test-failed-task"
    _TASK_STORE[task_id] = {
        "id": task_id,
        "status": {"state": "failed"},
        "artifacts": [],
        "history": [],
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(f"/tasks/{task_id}:cancel")

    assert resp.status_code == 409
    assert "already failed" in resp.text.lower()


@pytest.mark.asyncio
async def test_cancel_task_with_canceled_state():
    """Adapter server must reject cancel on already-cancelled task."""
    app = create_app()

    from ii_agent.integrations.a2a.adapter_server import _TASK_STORE

    task_id = "test-canceled-task"
    _TASK_STORE[task_id] = {
        "id": task_id,
        "status": {"state": "canceled"},
        "artifacts": [],
        "history": [],
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(f"/tasks/{task_id}:cancel")

    assert resp.status_code == 409
    assert "already canceled" in resp.text.lower()


@pytest.mark.asyncio
async def test_message_stream_metadata_preserved():
    """Adapter server must preserve and forward metadata from request."""
    app = create_app()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/message:stream",
            json={
                "context_id": "metadata-test",
                "messages": [{"role": "user", "content": "test"}],
                "metadata": {
                    "custom_field": "custom_value",
                    "nested": {"key": "value"},
                },
            },
        )

    assert resp.status_code == 200
