"""A2A Agent Tool — allows one II-Agent to call another via the A2A protocol."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Set, Tuple

from ii_agent.agents.tools.base import ToolResult
from ii_agent.integrations.a2a.as_client import IIAgentA2AClient
from ii_agent.realtime.events.app_events import EventType

logger = logging.getLogger(__name__)


class A2AAgentTool:
    """Tool that delegates a query to a remote II-Agent via the A2A protocol."""

    # Tool metadata expected by the agent framework
    name: str = "a2a_agent"
    display_name: str = "A2A Agent"
    read_only: bool = True

    input_schema: Dict[str, Any] = {
        "type": "object",
        "properties": {
            "agent_url": {
                "type": "string",
                "description": "URL or registered alias of the target A2A agent.",
            },
            "query": {
                "type": "string",
                "description": "The task or question to send to the agent.",
            },
            "context": {
                "type": "object",
                "description": "Optional execution context passed to the agent.",
            },
        },
        "required": ["agent_url", "query"],
    }

    # ------------------------------------------------------------------ #
    # Construction                                                         #
    # ------------------------------------------------------------------ #

    def __init__(self, default_agents: Optional[Dict[str, Any]] = None) -> None:
        raw = default_agents or {}
        self.default_agents: Dict[str, Dict[str, Any]] = {}
        for name, config in raw.items():
            normalized = self._normalize_agent_config(name, config)
            if normalized is not None:
                self.default_agents[name] = normalized

        # Per-URL state caches
        self._clients: Dict[str, IIAgentA2AClient] = {}
        self._agent_cards: Dict[str, Any] = {}
        self._agent_descriptions: Dict[str, str] = {}
        self._agent_extensions: Dict[str, Set[str]] = {}
        # Stores the canonicalized header tuple used when the client was created
        self._client_headers: Dict[str, Tuple[Tuple[str, str], ...]] = {}

        self._initialized: bool = False
        self._event_stream: Any = None  # Optional event stream for progress events

    # ------------------------------------------------------------------ #
    # Static helpers                                                       #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _normalize_agent_config(name: str, config: Any) -> Optional[Dict[str, Any]]:
        """Normalise an agent entry into a canonical dict or return None."""
        if isinstance(config, str):
            url = config.strip()
            if not url:
                return None
            return {"url": url, "name": name}

        if isinstance(config, dict):
            url = config.get("url", "")
            if not url or not isinstance(url, str) or not url.strip():
                return None
            result: Dict[str, Any] = {"url": url.strip(), "name": config.get("name") or name}
            if "description" in config:
                result["description"] = config["description"]
            if "metadata" in config and isinstance(config["metadata"], dict):
                result["metadata"] = config["metadata"]
            raw_headers = config.get("headers")
            sanitized = A2AAgentTool._sanitize_headers(raw_headers)
            if sanitized:
                result["headers"] = sanitized
            return result

        return None

    @staticmethod
    def _sanitize_headers(headers: Any) -> Dict[str, str]:
        """Return a cleaned dict of string headers; ignore invalid entries."""
        if not isinstance(headers, dict):
            return {}
        result: Dict[str, str] = {}
        for k, v in headers.items():
            if not k or not isinstance(k, str) or not k.strip():
                continue
            if v is None:
                continue
            result[k] = str(v)
        return result

    @staticmethod
    def _canonicalize_headers(
        headers: Dict[str, str],
    ) -> Tuple[Tuple[str, str], ...]:
        """Return a sorted, lowercase-keyed tuple for cache-hit comparison."""
        return tuple(sorted((k.lower(), v) for k, v in headers.items()))

    @staticmethod
    def _coerce_bool(value: Any) -> bool:
        """Coerce a value to bool, understanding common string representations."""
        if isinstance(value, bool):
            return value
        if isinstance(value, int):
            return value != 0
        if isinstance(value, str):
            if value.lower() in ("true", "1", "yes", "on"):
                return True
            if value.lower() in ("false", "0", "no", "off"):
                return False
            return bool(value)  # non-empty string → True
        return bool(value)

    @staticmethod
    def _coerce_timeout(value: Any) -> Optional[float]:
        """Coerce a value to a float timeout in seconds, or None."""
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            s = value.strip()
            try:
                if s.endswith("ms"):
                    return float(s[:-2]) / 1000.0
                if s.endswith("s"):
                    return float(s[:-1])
                return float(s)
            except (ValueError, AttributeError):
                return None
        return None

    # ------------------------------------------------------------------ #
    # Instance helpers                                                     #
    # ------------------------------------------------------------------ #

    def _negotiate_extensions(
        self,
        supported: List[str],
        context: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Compute extension negotiation result."""
        ctx = context or {}
        requested: List[str] = list(ctx.get("requested_extensions") or [])
        supported_set = set(supported)
        active = [e for e in requested if e in supported_set]
        missing = [e for e in requested if e not in supported_set]
        return {
            "requested_extensions": requested,
            "active_extensions": active,
            "missing_extensions": missing,
        }

    def _prepare_context(
        self,
        *,
        query: str,
        context: Optional[Dict[str, Any]],
        negotiation: Dict[str, Any],
        agent_description: str,
    ) -> Tuple[str, Dict[str, Any]]:
        """Build the final query string and outgoing context dict."""
        ctx: Dict[str, Any] = dict(context or {})
        ctx["a2a_negotiation"] = negotiation

        if negotiation.get("missing_extensions"):
            # Append fallback context to the query so the remote agent can adapt
            fallback = ctx.pop("fallback_briefing", None) or ctx.pop("briefing", None)
            if fallback:
                query = f"{query}\n\n[Fallback Context]\n{fallback}"

        return query, ctx

    def _find_agent_defaults_by_url(self, url: str) -> Optional[Dict[str, Any]]:
        """Return the defaults dict for a given URL, if registered."""
        for cfg in self.default_agents.values():
            if cfg.get("url") == url:
                return cfg
        return None

    def _resolve_timeout_seconds(self, url: str) -> Optional[float]:
        """Return the configured timeout for a URL, if any."""
        cfg = self._find_agent_defaults_by_url(url) or {}
        metadata = cfg.get("metadata") or {}
        raw = metadata.get("timeout_seconds") or metadata.get("timeout")
        result = self._coerce_timeout(raw)
        if result is not None and result <= 0:
            return None
        return result

    def _resolve_headers(self, url: str) -> Dict[str, str]:
        """Return headers for a given URL from the defaults config."""
        cfg = self._find_agent_defaults_by_url(url) or {}
        return self._sanitize_headers(cfg.get("headers") or {})

    def _map_task_state(self, state: Any) -> EventType:
        """Map an A2A TaskState to an EventType for progress reporting."""
        try:
            from a2a.types import TaskState  # type: ignore[import-untyped]

            if state == TaskState.working:
                return EventType.PROCESSING
        except ImportError:
            pass
        return EventType.STATUS_UPDATE

    def _extract_text_from_message(self, message: Any) -> Optional[str]:
        """Extract plain text from an A2A Message object."""
        if message is None:
            return None
        try:
            parts = message.parts
        except AttributeError:
            return None
        if not parts:
            return None
        for part in parts:
            try:
                if isinstance(part, dict):
                    text = part.get("text")
                    if text is not None:
                        return str(text)
                    continue
                root = getattr(part, "root", None)
                if root is not None:
                    text = getattr(root, "text", None)
                    if text is not None:
                        return str(text)
                text = getattr(part, "text", None)
                if text is not None:
                    return str(text)
            except Exception:
                continue
        return None

    def _extract_text_from_artifact(self, event: Any) -> Optional[str]:
        """Extract plain text from an A2A artifact event."""
        artifact = getattr(event, "artifact", None)
        if artifact is None:
            return None
        try:
            parts = artifact.parts
            if parts:
                for part in parts:
                    try:
                        if isinstance(part, dict):
                            text = part.get("text")
                            if text is not None:
                                return str(text)
                            continue
                        root = getattr(part, "root", None)
                        if root is not None:
                            text = getattr(root, "text", None)
                            if text is not None:
                                return str(text)
                        text = getattr(part, "text", None)
                        if text is not None:
                            return str(text)
                    except Exception:
                        continue
        except Exception:
            pass
        data = getattr(artifact, "data", None)
        if data is not None:
            return str(data)
        return None

    def set_event_stream(self, stream: Any) -> None:
        """Attach an event stream for emitting progress events."""
        self._event_stream = stream

    async def _emit_stream_event(self, event_type: EventType, payload: Dict[str, Any]) -> None:
        """Emit a progress event to the attached stream, if any."""
        if self._event_stream is None:
            return
        try:
            await self._event_stream.add_event(event_type, payload)
        except Exception:
            logger.debug("Failed to emit stream event", exc_info=True)

    # ------------------------------------------------------------------ #
    # Async client management                                              #
    # ------------------------------------------------------------------ #

    async def _get_client(
        self, url: str, headers: Optional[Dict[str, str]] = None
    ) -> IIAgentA2AClient:
        """Return a cached client for *url*, creating (or replacing) if needed."""
        resolved_headers = headers if headers is not None else self._resolve_headers(url)
        new_sig = self._canonicalize_headers(resolved_headers)

        cached = self._clients.get(url)
        if cached is not None:
            old_sig = self._client_headers.get(url, ())
            if old_sig == new_sig:
                return cached
            # Headers changed — close old client and create a fresh one
            try:
                await cached.close()
            except Exception:
                pass

        httpx_client = None
        if resolved_headers:
            import httpx as _httpx

            httpx_client = _httpx.AsyncClient(headers=resolved_headers, timeout=30.0)

        client = IIAgentA2AClient(agent_url=url, httpx_client=httpx_client)
        self._clients[url] = client
        self._client_headers[url] = new_sig
        return client

    # ------------------------------------------------------------------ #
    # Agent card / metadata                                                #
    # ------------------------------------------------------------------ #

    async def get_agent_description(self, url: str) -> str:
        """Return a short text description of the agent at *url*."""
        cached = self._agent_descriptions.get(url)
        if cached is not None:
            return cached

        # Check the static config first
        cfg = self._find_agent_defaults_by_url(url)
        if cfg and cfg.get("description"):
            desc = str(cfg["description"])
            self._agent_descriptions[url] = desc
            return desc

        # Try to fetch agent card
        try:
            client = await self._get_client(url)
            card = await client.get_agent_card()
            self._agent_cards[url] = card
            desc = getattr(card, "description", None) or str(url)
            self._agent_descriptions[url] = desc
            exts = list(getattr(card, "extensions", None) or [])
            self._agent_extensions[url] = set(str(e) for e in exts)
            return desc
        except Exception:
            fallback = str(url)
            self._agent_descriptions[url] = fallback
            return fallback

    async def get_agent_extensions(self, url: str) -> List[str]:
        """Return the list of A2A extensions supported by the agent at *url*."""
        if url in self._agent_extensions:
            return list(self._agent_extensions[url])

        client = await self._get_client(url)
        card = await client.get_agent_card()
        self._agent_cards[url] = card
        desc = getattr(card, "description", None) or str(url)
        if url not in self._agent_descriptions:
            self._agent_descriptions[url] = desc
        exts = list(getattr(card, "extensions", None) or [])
        ext_set = set(str(e) for e in exts)
        self._agent_extensions[url] = ext_set
        return list(ext_set)

    # ------------------------------------------------------------------ #
    # Lifecycle                                                            #
    # ------------------------------------------------------------------ #

    async def initialize(self) -> None:
        """Pre-fetch agent cards for all registered default agents."""
        if self._initialized:
            return

        for _alias, cfg in self.default_agents.items():
            url = cfg["url"]
            headers = self._sanitize_headers(cfg.get("headers") or {})
            try:
                client = await self._get_client(url, headers=headers or None)
                card = await client.get_agent_card()
                self._agent_cards[url] = card
                desc = getattr(card, "description", None) or cfg.get("description") or url
                self._agent_descriptions[url] = str(desc)
                exts = list(getattr(card, "extensions", None) or [])
                self._agent_extensions[url] = set(str(e) for e in exts)
            except Exception as exc:
                logger.warning("Failed to initialize A2A agent %s: %s", url, exc)
                # Still record a description so we don't fail at call time
                desc = cfg.get("description") or url
                if url not in self._agent_descriptions:
                    self._agent_descriptions[url] = str(desc)
                if url not in self._agent_extensions:
                    self._agent_extensions[url] = set()

        self._initialized = True

    async def close_all_clients(self) -> None:
        """Close every cached client and clear the cache."""
        for client in list(self._clients.values()):
            await client.close()
        self._clients.clear()
        self._client_headers.clear()

    # ------------------------------------------------------------------ #
    # Execution                                                            #
    # ------------------------------------------------------------------ #

    async def execute(self, params: Dict[str, Any]) -> ToolResult:
        """Execute the tool: delegate *query* to the selected A2A agent."""
        if not self._initialized:
            await self.initialize()

        agent_url_raw: str = params.get("agent_url") or ""
        query: str = params.get("query") or ""
        context: Optional[Dict[str, Any]] = params.get("context") or None

        if not agent_url_raw.strip():
            return ToolResult(
                llm_content="Error: agent_url is required",
                is_error=True,
            )
        if not query.strip():
            return ToolResult(
                llm_content="Error: query must not be empty",
                is_error=True,
            )

        # Resolve alias → URL
        agent_name = agent_url_raw.strip()
        url: str
        if agent_name in self.default_agents:
            url = self.default_agents[agent_name]["url"]
        else:
            url = agent_name  # treat as a direct URL

        try:
            client = await self._get_client(url)

            # Ensure we have description and extensions
            if url not in self._agent_descriptions or url not in self._agent_extensions:
                try:
                    card = await client.get_agent_card()
                    self._agent_cards[url] = card
                    self._agent_descriptions[url] = getattr(card, "description", None) or url
                    exts = list(getattr(card, "extensions", None) or [])
                    self._agent_extensions[url] = set(str(e) for e in exts)
                except Exception:
                    self._agent_descriptions.setdefault(url, url)
                    self._agent_extensions.setdefault(url, set())

            agent_description = self._agent_descriptions.get(url, url)
            supported_extensions = list(self._agent_extensions.get(url, set()))

            negotiation = self._negotiate_extensions(supported_extensions, context)
            effective_query, outgoing_context = self._prepare_context(
                query=query,
                context=context,
                negotiation=negotiation,
                agent_description=agent_description,
            )

            result = await client.call_agent(
                messages=[],
                context_id=url,
                metadata={"query": effective_query, "context": outgoing_context},
            )

            content = result.get("content", "")
            if not result.get("success", False):
                return ToolResult(llm_content=content, is_error=True)

            return ToolResult(
                llm_content=content,
                user_display_content=result.get("user_display_content", content),
            )

        except Exception as exc:
            logger.exception("A2AAgentTool.execute failed for %s", url)
            return ToolResult(
                llm_content=f"Error: {exc}",
                is_error=True,
            )
