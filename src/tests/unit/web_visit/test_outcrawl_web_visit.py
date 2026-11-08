"""Unit tests for the Outcrawl web visit client and its factory wiring."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from ii_agent_tools.integrations.web_visit.base import (
    WEB_VISIT_SERVICE_TYPES,
    WebVisitError,
    WebVisitResult,
)
from ii_agent_tools.integrations.web_visit.beautifulsoup import (
    BeautifulSoupWebVisitClient,
)
from ii_agent_tools.integrations.web_visit.config import WebVisitConfig
from ii_agent_tools.integrations.web_visit.factory import (
    create_all_web_visit_clients,
    create_web_visit_client,
)
from ii_agent_tools.integrations.web_visit.outcrawl import OutcrawlWebVisitClient


class _FakeResponse:
    def __init__(self, payload: dict, status: int = 200):
        self._payload = payload
        self.status = status

    def raise_for_status(self) -> None:
        if self.status >= 400:
            raise RuntimeError(f"HTTP {self.status}")

    async def json(self) -> dict:
        return self._payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class _FakeSession:
    """Stands in for aiohttp.ClientSession and records the POST it receives."""

    def __init__(self, response: _FakeResponse):
        self.response = response
        self.calls: list[tuple[str, dict]] = []

    def post(self, url: str, **kwargs):
        self.calls.append((url, kwargs))
        return self.response

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


def _patch_session(response: _FakeResponse):
    session = _FakeSession(response)
    return session, patch(
        "ii_agent_tools.integrations.web_visit.outcrawl.aiohttp.ClientSession",
        return_value=session,
    )


async def test_extract_posts_scrape_request_and_returns_markdown():
    session, patcher = _patch_session(
        _FakeResponse({"url": "https://example.com/", "statusCode": 200, "markdown": "# Hello"})
    )
    with patcher:
        result = await OutcrawlWebVisitClient(api_key="oc-test").extract("https://example.com")

    assert isinstance(result, WebVisitResult)
    assert result.content == "# Hello"
    url, kwargs = session.calls[0]
    assert url == "https://api.outcrawl.ai/v1/scrape"
    assert kwargs["headers"]["Authorization"] == "Bearer oc-test"
    assert kwargs["json"] == {"url": "https://example.com", "formats": ["markdown"]}


@pytest.mark.parametrize("payload", [{}, {"markdown": None}, {"markdown": "   "}])
async def test_extract_raises_when_no_content(payload):
    _, patcher = _patch_session(_FakeResponse(payload))
    with patcher:
        with pytest.raises(WebVisitError, match="No content could be extracted"):
            await OutcrawlWebVisitClient(api_key="oc-test").extract("https://example.com")


async def test_extract_wraps_http_errors():
    _, patcher = _patch_session(_FakeResponse({}, status=401))
    with patcher:
        with pytest.raises(WebVisitError, match="Outcrawl extraction error"):
            await OutcrawlWebVisitClient(api_key="oc-test").extract("https://example.com")


async def test_batch_extract_joins_pages():
    client = OutcrawlWebVisitClient(api_key="oc-test")
    with patch.object(
        client,
        "extract",
        AsyncMock(
            side_effect=[
                WebVisitResult(content="a", cost=0.0),
                WebVisitResult(content="b", cost=0.0),
            ]
        ),
    ):
        result = await client.batch_extract(["https://a.example", "https://b.example"])

    assert result.content == "a\nb"
    assert result.cost == 0.0


def test_outcrawl_is_a_known_service_type():
    assert "outcrawl" in WEB_VISIT_SERVICE_TYPES


def test_factory_uses_outcrawl_when_requested_and_configured():
    client = create_web_visit_client(WebVisitConfig(outcrawl_api_key="oc-test"), "outcrawl")
    assert isinstance(client, OutcrawlWebVisitClient)


def test_factory_falls_back_when_outcrawl_key_is_missing():
    client = create_web_visit_client(WebVisitConfig(), "outcrawl")
    assert isinstance(client, BeautifulSoupWebVisitClient)


def test_factory_default_picks_outcrawl_only_after_the_other_keyed_clients():
    only_outcrawl = create_web_visit_client(WebVisitConfig(outcrawl_api_key="oc-test"))
    assert isinstance(only_outcrawl, OutcrawlWebVisitClient)

    with_jina = create_web_visit_client(
        WebVisitConfig(jina_api_key="jina-test", outcrawl_api_key="oc-test")
    )
    assert not isinstance(with_jina, OutcrawlWebVisitClient)


def test_all_clients_list_includes_outcrawl_before_the_soup_fallback():
    clients = create_all_web_visit_clients(WebVisitConfig(outcrawl_api_key="oc-test"))
    assert [type(c) for c in clients] == [OutcrawlWebVisitClient, BeautifulSoupWebVisitClient]
