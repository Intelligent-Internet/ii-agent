"""Regression tests for the ``_ainvoke_stream_with_retry`` retry-classifier.

HTTP 4xx responses (other than 429) indicate a malformed request body —
retrying the same bad payload deterministically fails with the same
error.  The bug that motivated these tests caused a 4× retry storm each
time the native-LLM fallback path hit Anthropic's 400
``invalid_request_error`` ("temperature may only be set to 1 when
thinking is enabled"), burning provider quota and latency with zero
chance of success.
"""

from __future__ import annotations

import asyncio
import dataclasses
from typing import AsyncIterator, Dict, Type

import pytest

from ii_agent.agents.exceptions import ModelProviderError, ModelRateLimitError
from ii_agent.agents.models.base import Model
from ii_agent.agents.models.response import ModelResponse


@dataclasses.dataclass
class _StubModel(Model):
    """Stub model that raises a pre-seeded exception on every stream attempt."""

    exc_factory: Type[ModelProviderError] | None = None
    _attempts: int = 0

    async def ainvoke(self, *args, **kwargs) -> ModelResponse:  # pragma: no cover
        raise NotImplementedError

    async def ainvoke_stream(self, *args, **kwargs) -> AsyncIterator[ModelResponse]:
        self._attempts += 1
        assert self.exc_factory is not None
        raise self.exc_factory()
        yield  # pragma: no cover — unreachable, makes this a generator

    def _parse_provider_response(self, response, **kwargs):  # pragma: no cover
        raise NotImplementedError

    def _parse_provider_response_delta(self, response, **kwargs):  # pragma: no cover
        raise NotImplementedError


def _build_error(status: int, message: str = "test") -> ModelProviderError:
    return ModelProviderError(message=message, status_code=status)


@pytest.mark.asyncio
async def test_400_invalid_request_is_not_retried(monkeypatch):
    """A 400 ``invalid_request_error`` must raise on the first attempt."""
    # Skip real sleeps so test stays fast.
    monkeypatch.setattr(asyncio, "sleep", lambda *_a, **_kw: asyncio.sleep(0))

    class Err(ModelProviderError):
        def __init__(self):
            super().__init__(
                message="`temperature` may only be set to 1 when thinking is enabled",
                status_code=400,
            )

    model = _StubModel(id="stub", retries=4, exc_factory=Err)

    with pytest.raises(ModelProviderError) as excinfo:
        async for _ in model._ainvoke_stream_with_retry():
            pass

    assert excinfo.value.status_code == 400
    # Must have been called exactly once — no retry storm.
    assert model._attempts == 1


@pytest.mark.asyncio
async def test_429_rate_limit_is_retried(monkeypatch):
    """Rate limits remain retriable (the historical behaviour)."""
    # No-op sleep
    async def _fast_sleep(*_a, **_kw):
        return

    monkeypatch.setattr(asyncio, "sleep", _fast_sleep)

    class Err(ModelRateLimitError):
        def __init__(self):
            super().__init__(message="slow down", status_code=429)

    model = _StubModel(id="stub", retries=3, exc_factory=Err)

    with pytest.raises(ModelProviderError):
        async for _ in model._ainvoke_stream_with_retry():
            pass

    # retries + 1 = 4 total attempts
    assert model._attempts == 4


@pytest.mark.asyncio
async def test_500_server_error_is_retried(monkeypatch):
    """5xx is transient — must retry the full budget."""
    async def _fast_sleep(*_a, **_kw):
        return

    monkeypatch.setattr(asyncio, "sleep", _fast_sleep)

    class Err(ModelProviderError):
        def __init__(self):
            super().__init__(message="upstream blew up", status_code=502)

    model = _StubModel(id="stub", retries=2, exc_factory=Err)

    with pytest.raises(ModelProviderError):
        async for _ in model._ainvoke_stream_with_retry():
            pass

    assert model._attempts == 3


@pytest.mark.asyncio
async def test_401_auth_error_is_not_retried(monkeypatch):
    """Auth failures are deterministic — must not retry."""
    monkeypatch.setattr(asyncio, "sleep", lambda *_a, **_kw: asyncio.sleep(0))

    class Err(ModelProviderError):
        def __init__(self):
            super().__init__(message="bad api key", status_code=401)

    model = _StubModel(id="stub", retries=4, exc_factory=Err)

    with pytest.raises(ModelProviderError):
        async for _ in model._ainvoke_stream_with_retry():
            pass

    assert model._attempts == 1
