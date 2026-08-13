"""Agent registry for A2A multi-agent discovery and routing.

The registry maintains a collection of *known* A2A agents, each described by
an ``AgentCard``.  Agents self-register via ``register()`` or are discovered
by crawling a remote agent's ``/.well-known/agent-card.json`` endpoint via
``discover()``.  The registry is intentionally in-memory for now; persistence
(Redis / DB) is deferred to a later phase.

Routing semantics are in :mod:`ii_agent.integrations.a2a.router`.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)


@dataclass
class AgentSkill:
    """One entry from an agent card's ``skills`` array."""

    id: str
    name: str
    description: str = ""
    tags: List[str] = field(default_factory=list)
    examples: List[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AgentSkill":
        return cls(
            id=str(data.get("id") or ""),
            name=str(data.get("name") or ""),
            description=str(data.get("description") or ""),
            tags=list(data.get("tags") or []),
            examples=list(data.get("examples") or []),
        )


@dataclass
class AgentCard:
    """Parsed representation of an A2A ``/.well-known/agent-card.json`` document.

    Only the fields relevant to routing and display are captured; unknown fields
    are preserved in ``extra`` so round-trip fidelity is not lost.
    """

    name: str
    url: str
    description: str = ""
    version: str = ""
    skills: List[AgentSkill] = field(default_factory=list)
    capabilities: Dict[str, Any] = field(default_factory=dict)
    default_input_modes: List[str] = field(default_factory=list)
    default_output_modes: List[str] = field(default_factory=list)
    extensions: List[Dict[str, Any]] = field(default_factory=list)
    extra: Dict[str, Any] = field(default_factory=dict)

    # Populated by the registry when the card was fetched.
    fetched_from: Optional[str] = field(default=None, compare=False)

    @classmethod
    def from_dict(cls, data: Dict[str, Any], *, fetched_from: Optional[str] = None) -> "AgentCard":
        known_keys = {
            "name",
            "url",
            "description",
            "version",
            "skills",
            "capabilities",
            "defaultInputModes",
            "defaultOutputModes",
            "extensions",
        }
        extra = {k: v for k, v in data.items() if k not in known_keys}
        return cls(
            name=str(data.get("name") or ""),
            url=str(data.get("url") or ""),
            description=str(data.get("description") or ""),
            version=str(data.get("version") or ""),
            skills=[AgentSkill.from_dict(s) for s in (data.get("skills") or [])],
            capabilities=dict(data.get("capabilities") or {}),
            default_input_modes=list(data.get("defaultInputModes") or []),
            default_output_modes=list(data.get("defaultOutputModes") or []),
            extensions=list(data.get("extensions") or []),
            extra=extra,
            fetched_from=fetched_from,
        )

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "name": self.name,
            "url": self.url,
            "description": self.description,
            "version": self.version,
            "skills": [
                {
                    "id": s.id,
                    "name": s.name,
                    "description": s.description,
                    "tags": s.tags,
                    "examples": s.examples,
                }
                for s in self.skills
            ],
            "capabilities": self.capabilities,
            "defaultInputModes": self.default_input_modes,
            "defaultOutputModes": self.default_output_modes,
            "extensions": self.extensions,
        }
        d.update(self.extra)
        return d

    @property
    def all_tags(self) -> List[str]:
        """Flat list of all tags across all skills (deduplicated, lowercased)."""
        seen: set[str] = set()
        result: List[str] = []
        for skill in self.skills:
            for tag in skill.tags:
                t = tag.lower()
                if t not in seen:
                    seen.add(t)
                    result.append(t)
        return result

    @property
    def supports_streaming(self) -> bool:
        return bool(self.capabilities.get("streaming", False))

    @property
    def extension_uris(self) -> List[str]:
        return [str(e.get("uri") or "") for e in self.extensions if e.get("uri")]


class AgentRegistry:
    """In-memory registry of known A2A agents.

    Thread-safe via an ``asyncio.Lock`` so it can be shared across concurrent
    request handlers.

    Typical usage
    -------------
    ::

        registry = AgentRegistry()
        # Register a statically known agent (e.g. the sandbox-local adapter):
        await registry.register(AgentCard(name="local", url="http://localhost:18100"))

        # Discover (crawl) a remote agent card:
        card = await registry.discover("http://remote-agent:8080")

        # Look up by name or URL:
        agent = registry.get("local")
        all_agents = registry.list_all()
    """

    def __init__(self) -> None:
        self._agents: Dict[str, AgentCard] = {}  # keyed by card.name
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Mutation
    # ------------------------------------------------------------------

    async def register(self, card: AgentCard) -> None:
        """Add or replace a card.  Key is ``card.name``."""
        async with self._lock:
            if card.name in self._agents:
                logger.debug("AgentRegistry: replacing card for %r", card.name)
            else:
                logger.info("AgentRegistry: registered agent %r at %s", card.name, card.url)
            self._agents[card.name] = card

    async def unregister(self, name: str) -> bool:
        """Remove a card by name.  Returns True if it existed."""
        async with self._lock:
            existed = name in self._agents
            self._agents.pop(name, None)
            if existed:
                logger.info("AgentRegistry: unregistered agent %r", name)
            return existed

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    async def discover(
        self,
        base_url: str,
        *,
        timeout: float = 10.0,
        httpx_client: Optional[httpx.AsyncClient] = None,
    ) -> AgentCard:
        """Fetch ``/.well-known/agent-card.json`` from *base_url* and register it.

        Raises ``httpx.HTTPError`` on network failure, ``ValueError`` on malformed
        cards.  The card is registered (keyed by ``card.name``) on success.
        """
        base = base_url.rstrip("/")
        card_url = f"{base}/.well-known/agent-card.json"

        own_client = httpx_client is None
        client: httpx.AsyncClient = httpx_client or httpx.AsyncClient(timeout=timeout)
        try:
            resp = await client.get(card_url)
            resp.raise_for_status()
            data = resp.json()
        finally:
            if own_client:
                await client.aclose()

        if not isinstance(data, dict):
            raise ValueError(f"Agent card at {card_url} is not a JSON object")
        if not data.get("name"):
            raise ValueError(f"Agent card at {card_url} is missing 'name'")

        # Resolve the url field: prefer what the card says, fall back to base_url.
        if not data.get("url"):
            data["url"] = base_url

        card = AgentCard.from_dict(data, fetched_from=card_url)
        await self.register(card)
        logger.info("AgentRegistry: discovered %r from %s", card.name, card_url)
        return card

    async def discover_many(
        self,
        base_urls: List[str],
        *,
        timeout: float = 10.0,
        ignore_errors: bool = True,
    ) -> List[AgentCard]:
        """Discover multiple agents concurrently.

        When *ignore_errors* is True, failures are logged and skipped rather
        than propagated — suitable for startup-time registry population where
        some agents may be transiently unavailable.
        """
        async with httpx.AsyncClient(timeout=timeout) as client:
            tasks = [self.discover(url, httpx_client=client) for url in base_urls]
            results = await asyncio.gather(*tasks, return_exceptions=True)

        cards: List[AgentCard] = []
        for url, result in zip(base_urls, results):
            if isinstance(result, BaseException):
                if ignore_errors:
                    logger.warning("AgentRegistry: discovery failed for %s: %s", url, result)
                else:
                    raise result
            else:
                cards.append(result)
        return cards

    # ------------------------------------------------------------------
    # Lookup
    # ------------------------------------------------------------------

    def get(self, name: str) -> Optional[AgentCard]:
        """Return a card by agent name, or None."""
        return self._agents.get(name)

    def get_by_url(self, url: str) -> Optional[AgentCard]:
        """Return the first card whose URL matches (prefix match on base URL)."""
        normalised = url.rstrip("/")
        for card in self._agents.values():
            if card.url.rstrip("/") == normalised:
                return card
        return None

    def list_all(self) -> List[AgentCard]:
        """Return a snapshot of all registered cards."""
        return list(self._agents.values())

    def __len__(self) -> int:
        return len(self._agents)

    def __contains__(self, name: object) -> bool:
        return name in self._agents
