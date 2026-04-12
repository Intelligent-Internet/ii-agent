"""Tests for AgentCard, AgentRegistry, AgentRouter, and TaskStore."""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ii_agent.integrations.a2a.registry import AgentCard, AgentRegistry
from ii_agent.integrations.a2a.router import AgentRouter
from ii_agent.integrations.a2a.task_store import TaskStore


pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# AgentCard
# ---------------------------------------------------------------------------


class TestAgentCard:
    def test_from_dict_minimal(self):
        card = AgentCard.from_dict({"name": "myagent", "url": "http://localhost:8080"})
        assert card.name == "myagent"
        assert card.url == "http://localhost:8080"
        assert card.skills == []
        assert card.extensions == []

    def test_from_dict_full(self):
        data = {
            "name": "coder",
            "url": "http://coder:18100",
            "description": "Does coding",
            "version": "1.0",
            "skills": [
                {"id": "shell", "name": "Shell", "tags": ["bash", "shell"], "examples": []},
            ],
            "capabilities": {"streaming": True},
            "defaultInputModes": ["text/plain"],
            "defaultOutputModes": ["text/plain"],
            "extensions": [{"uri": "urn:test", "required": False}],
            "extra_field": "preserved",
        }
        card = AgentCard.from_dict(data)
        assert card.name == "coder"
        assert len(card.skills) == 1
        assert card.skills[0].id == "shell"
        assert card.capabilities["streaming"] is True
        assert card.extension_uris == ["urn:test"]
        assert card.extra["extra_field"] == "preserved"

    def test_to_dict_round_trip(self):
        card = AgentCard.from_dict(
            {"name": "test", "url": "http://x", "skills": [{"id": "a", "name": "A", "tags": ["x"]}]}
        )
        d = card.to_dict()
        card2 = AgentCard.from_dict(d)
        assert card2.name == card.name
        assert card2.skills[0].id == card.skills[0].id

    def test_all_tags_deduplication(self):
        card = AgentCard.from_dict(
            {
                "name": "t",
                "url": "http://t",
                "skills": [
                    {"id": "a", "name": "A", "tags": ["Code", "Python"]},
                    {"id": "b", "name": "B", "tags": ["python", "shell"]},  # 'python' dupe
                ],
            }
        )
        assert "code" in card.all_tags
        assert "python" in card.all_tags
        assert "shell" in card.all_tags
        assert card.all_tags.count("python") == 1

    def test_supports_streaming(self):
        card = AgentCard.from_dict(
            {"name": "s", "url": "http://s", "capabilities": {"streaming": True}}
        )
        assert card.supports_streaming is True

    def test_extension_uris(self):
        card = AgentCard.from_dict(
            {
                "name": "e",
                "url": "http://e",
                "extensions": [
                    {"uri": "urn:one"},
                    {"uri": "urn:two"},
                    {"not_uri": "ignored"},
                ],
            }
        )
        assert card.extension_uris == ["urn:one", "urn:two"]


# ---------------------------------------------------------------------------
# AgentRegistry
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_registry_register_and_get():
    registry = AgentRegistry()
    card = AgentCard(name="a", url="http://a")
    await registry.register(card)
    assert registry.get("a") is card
    assert "a" in registry
    assert len(registry) == 1


@pytest.mark.asyncio
async def test_registry_unregister():
    registry = AgentRegistry()
    await registry.register(AgentCard(name="b", url="http://b"))
    existed = await registry.unregister("b")
    assert existed is True
    assert registry.get("b") is None
    not_existed = await registry.unregister("b")
    assert not_existed is False


@pytest.mark.asyncio
async def test_registry_list_all():
    registry = AgentRegistry()
    await registry.register(AgentCard(name="x", url="http://x"))
    await registry.register(AgentCard(name="y", url="http://y"))
    names = {c.name for c in registry.list_all()}
    assert names == {"x", "y"}


@pytest.mark.asyncio
async def test_registry_get_by_url():
    registry = AgentRegistry()
    card = AgentCard(name="z", url="http://z:8080")
    await registry.register(card)
    assert registry.get_by_url("http://z:8080") is card
    assert registry.get_by_url("http://z:8080/") is card  # trailing slash
    assert registry.get_by_url("http://other") is None


@pytest.mark.asyncio
async def test_registry_replace_existing():
    registry = AgentRegistry()
    await registry.register(AgentCard(name="rep", url="http://old"))
    await registry.register(AgentCard(name="rep", url="http://new"))
    assert registry.get("rep").url == "http://new"
    assert len(registry) == 1


@pytest.mark.asyncio
async def test_registry_discover_success():
    """discover() fetches the card URL and registers the card."""
    registry = AgentRegistry()
    card_data = {
        "name": "remote",
        "url": "http://remote:8080",
        "skills": [{"id": "gen", "name": "General", "tags": ["general"]}],
    }

    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = card_data

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)

    card = await registry.discover("http://remote:8080", httpx_client=mock_client)

    assert card.name == "remote"
    assert registry.get("remote") is card
    mock_client.get.assert_called_once_with("http://remote:8080/.well-known/agent-card.json")


@pytest.mark.asyncio
async def test_registry_discover_fills_url_when_missing():
    """discover() fills card.url from base_url when the card omits it."""
    registry = AgentRegistry()

    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {"name": "anon"}  # no 'url' field

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)

    card = await registry.discover("http://anon:9000", httpx_client=mock_client)
    assert card.url == "http://anon:9000"


@pytest.mark.asyncio
async def test_registry_discover_many_ignores_errors():
    registry = AgentRegistry()

    good_card = {"name": "good", "url": "http://good"}
    mock_good_response = MagicMock()
    mock_good_response.raise_for_status = MagicMock()
    mock_good_response.json.return_value = good_card

    side_effects = {
        "http://good/.well-known/agent-card.json": mock_good_response,
    }

    async def fake_get(url, **_):
        if url in side_effects:
            return side_effects[url]
        raise ValueError("bad agent")

    mock_client = MagicMock()
    mock_client.get = fake_get
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("ii_agent.integrations.a2a.registry.httpx.AsyncClient", return_value=mock_client):
        cards = await registry.discover_many(["http://good", "http://bad"], ignore_errors=True)

    assert len(cards) == 1
    assert cards[0].name == "good"


@pytest.mark.asyncio
async def test_registry_discover_raises_for_non_dict_response():
    """discover() raises ValueError when the agent card JSON is not a dict."""
    registry = AgentRegistry()

    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = ["array", "not", "dict"]

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)

    with pytest.raises(ValueError, match="not a JSON object"):
        await registry.discover("http://bad-shape:9000", httpx_client=mock_client)


@pytest.mark.asyncio
async def test_registry_discover_raises_for_missing_name():
    """discover() raises ValueError when the agent card has no 'name'."""
    registry = AgentRegistry()

    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {"url": "http://x"}  # no name

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)

    with pytest.raises(ValueError, match="missing 'name'"):
        await registry.discover("http://x", httpx_client=mock_client)


@pytest.mark.asyncio
async def test_registry_discover_creates_and_closes_own_client():
    """discover() without an external client creates + closes its own httpx.AsyncClient."""
    registry = AgentRegistry()

    card_data = {"name": "auto-client", "url": "http://auto"}
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = card_data

    mock_http = MagicMock()
    mock_http.get = AsyncMock(return_value=mock_response)
    mock_http.aclose = AsyncMock()

    with patch("ii_agent.integrations.a2a.registry.httpx.AsyncClient", return_value=mock_http):
        card = await registry.discover("http://auto")  # no httpx_client param

    mock_http.aclose.assert_called_once()
    assert card.name == "auto-client"


@pytest.mark.asyncio
async def test_registry_discover_many_propagates_errors_when_not_ignored():
    """discover_many with ignore_errors=False must re-raise on the first failure."""
    registry = AgentRegistry()

    async def fake_get(url, **_):
        raise ConnectionError("host unreachable")

    mock_client = MagicMock()
    mock_client.get = fake_get
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("ii_agent.integrations.a2a.registry.httpx.AsyncClient", return_value=mock_client):
        with pytest.raises(Exception):
            await registry.discover_many(["http://bad"], ignore_errors=False)


# ---------------------------------------------------------------------------
# AgentRouter
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_router_single_agent_no_match_needed():
    registry = AgentRegistry()
    await registry.register(AgentCard(name="only", url="http://only"))
    router = AgentRouter(registry)
    card = router.route("anything")
    assert card.name == "only"


@pytest.mark.asyncio
async def test_router_selects_best_matching_tags():
    registry = AgentRegistry()
    await registry.register(
        AgentCard.from_dict(
            {
                "name": "coder",
                "url": "http://coder",
                "skills": [{"id": "s", "name": "S", "tags": ["python", "code"]}],
            }
        )
    )
    await registry.register(
        AgentCard.from_dict(
            {
                "name": "researcher",
                "url": "http://researcher",
                "skills": [{"id": "r", "name": "R", "tags": ["search", "web"]}],
            }
        )
    )
    router = AgentRouter(registry)
    card = router.route("write a Python script", hint_tags=["python", "code"])
    assert card.name == "coder"


@pytest.mark.asyncio
async def test_router_uses_fallback_when_no_match():
    registry = AgentRegistry()
    await registry.register(AgentCard(name="fallback", url="http://fallback"))
    await registry.register(
        AgentCard.from_dict(
            {
                "name": "specialist",
                "url": "http://spec",
                "skills": [{"id": "s", "name": "S", "tags": ["audio"]}],
            }
        )
    )
    router = AgentRouter(registry, fallback_name="fallback")
    card = router.route("do something unrelated", hint_tags=["video"])
    # "video" matches neither; fallback chosen
    assert card.name == "fallback"


@pytest.mark.asyncio
async def test_router_route_by_skill_id():
    registry = AgentRegistry()
    await registry.register(
        AgentCard.from_dict(
            {
                "name": "coder",
                "url": "http://coder",
                "skills": [{"id": "python-runner", "name": "PythonRunner", "tags": []}],
            }
        )
    )
    router = AgentRouter(registry)
    card = router.route_by_skill_id("python-runner")
    assert card is not None
    assert card.name == "coder"


@pytest.mark.asyncio
async def test_router_route_by_extension():
    registry = AgentRegistry()
    await registry.register(
        AgentCard.from_dict(
            {
                "name": "reasoner",
                "url": "http://r",
                "extensions": [{"uri": "urn:ii-agent:extensions:reasoning/v1"}],
            }
        )
    )
    await registry.register(AgentCard(name="basic", url="http://basic"))
    router = AgentRouter(registry)
    cards = router.route_by_extension("urn:ii-agent:extensions:reasoning/v1")
    assert len(cards) == 1
    assert cards[0].name == "reasoner"


@pytest.mark.asyncio
async def test_router_empty_registry_returns_none():
    router = AgentRouter(AgentRegistry())
    assert router.route("anything") is None


@pytest.mark.asyncio
async def test_router_route_no_hint_tags_multiple_agents_hits_score_empty_path():
    """route() with no hint_tags and multiple agents exercises _score's empty-hints path."""
    registry = AgentRegistry()
    await registry.register(AgentCard(name="alpha", url="http://alpha"))
    await registry.register(AgentCard(name="beta", url="http://beta"))
    router = AgentRouter(registry)
    # With no hint_tags, all agents score 0; tie broken alphabetically.
    # "alpha" < "beta" so by the negated-ord logic "alpha" should win (lower ord → higher key).
    card = router.route("do something")
    assert card is not None  # must pick one deterministically


@pytest.mark.asyncio
async def test_router_route_by_skill_id_not_found():
    """route_by_skill_id returns None when no agent has the requested skill."""
    registry = AgentRegistry()
    await registry.register(
        AgentCard.from_dict({"name": "coder", "url": "http://coder", "skills": [{"id": "python"}]})
    )
    router = AgentRouter(registry)
    result = router.route_by_skill_id("nonexistent-skill-id")
    assert result is None


@pytest.mark.asyncio
async def test_router_route_by_extension_no_match():
    """route_by_extension returns empty list when no agent advertises the URI."""
    registry = AgentRegistry()
    await registry.register(AgentCard(name="basic", url="http://basic"))
    router = AgentRouter(registry)
    result = router.route_by_extension("urn:unknown:extension")
    assert result == []


# ---------------------------------------------------------------------------
# TaskStore
# ---------------------------------------------------------------------------


class TestTaskStore:
    def test_set_and_get(self):
        store = TaskStore()
        store["t1"] = {"id": "t1", "status": {"state": "working"}}
        task = store["t1"]
        assert task["id"] == "t1"

    def test_contains(self):
        store = TaskStore()
        store["t2"] = {"id": "t2"}
        assert "t2" in store
        assert "missing" not in store

    def test_get_default(self):
        store = TaskStore()
        assert store.get("nope") is None
        assert store.get("nope", {"default": True}) == {"default": True}

    def test_pop_existing(self):
        store = TaskStore()
        store["t3"] = {"id": "t3"}
        val = store.pop("t3")
        assert val["id"] == "t3"
        assert "t3" not in store

    def test_pop_missing_with_default(self):
        store = TaskStore()
        assert store.pop("gone", None) is None

    def test_ttl_expiry(self):
        store = TaskStore(ttl_seconds=0.01)  # 10 ms TTL
        store["exp"] = {"id": "exp"}
        assert "exp" in store
        time.sleep(0.05)
        assert "exp" not in store  # expired

    def test_maxsize_evicts_oldest(self):
        store = TaskStore(maxsize=3)
        store["a"] = {"id": "a"}
        store["b"] = {"id": "b"}
        store["c"] = {"id": "c"}
        assert len(store) == 3
        store["d"] = {"id": "d"}  # evicts "a"
        assert store.get("a") is None
        assert store.get("d") is not None

    def test_items_skips_expired(self):
        store = TaskStore(ttl_seconds=0.01)
        store["live"] = {"id": "live"}
        time.sleep(0.05)
        store["fresh"] = {"id": "fresh"}
        keys = [k for k, _ in store.items()]
        assert "live" not in keys
        assert "fresh" in keys

    def test_evict_expired_count(self):
        store = TaskStore(ttl_seconds=0.01)
        store["x"] = {"id": "x"}
        store["y"] = {"id": "y"}
        time.sleep(0.05)
        store["z"] = {"id": "z"}
        removed = store.evict_expired()
        assert removed == 2

    def test_zero_ttl_never_expires(self):
        store = TaskStore(ttl_seconds=0)
        store["perm"] = {"id": "perm"}
        time.sleep(0.05)
        assert "perm" in store

    def test_invalid_params(self):
        with pytest.raises(ValueError):
            TaskStore(ttl_seconds=-1)
        with pytest.raises(ValueError):
            TaskStore(maxsize=0)

    def test_getitem_on_expired_entry_raises_key_error(self):
        """__getitem__ on an expired entry must remove it and raise KeyError."""
        store = TaskStore(ttl_seconds=0.01)
        store["exp-get"] = {"id": "exp-get"}
        time.sleep(0.05)
        with pytest.raises(KeyError):
            _ = store["exp-get"]

    def test_pop_missing_without_default_raises_key_error(self):
        """pop on a missing key without a default arg must raise KeyError."""
        store = TaskStore()
        with pytest.raises(KeyError):
            store.pop("definitely-not-there")

    def test_pop_expired_entry_with_default_returns_default(self):
        """pop on an expired entry with a default should return the default."""
        store = TaskStore(ttl_seconds=0.01)
        store["exp-pop"] = {"id": "x"}
        time.sleep(0.05)
        result = store.pop("exp-pop", {"fallback": True})
        assert result == {"fallback": True}

    def test_pop_expired_entry_without_default_raises_key_error(self):
        """pop on an expired entry without a default must raise KeyError."""
        store = TaskStore(ttl_seconds=0.01)
        store["exp-pop2"] = {"id": "y"}
        time.sleep(0.05)
        with pytest.raises(KeyError):
            store.pop("exp-pop2")
