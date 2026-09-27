"""Tool routing layer for hybrid A2A / native execution.

Determines whether a tool invocation should be handled by:

- **CLI** — the Copilot CLI A2A adapter running in the sandbox (file I/O,
  shell commands, code execution, web browsing).
- **NATIVE** — the II-Agent server-side tool executor (media generation,
  slides, storybook, project deployment, connector calls).
- **SPECIALIST** — a registered specialist sub-agent that owns the tool
  domain (future: multi-agent routing, Phase 4).

Decision precedence
-------------------
1. **Security gate** — tools flagged as security-sensitive always route
   NATIVE so they never cross a network boundary to the CLI.
2. **Proprietary categories** — ``media``, ``slides``, ``storybook``,
   ``planning``, ``connectors``, and ``dev`` tools are II-Agent-native and
   cannot be delegated.
3. **Specialist allowlist** — a configurable set of tool names explicitly
   mapped to a named specialist agent.
4. **CLI-eligible** — tools in the ``cli_eligible`` category set route to
   the Copilot CLI adapter.
5. **Fallback** — everything else routes NATIVE.

Usage
-----
::

    router = ToolRoutingLayer()
    decision = router.route("bash", category="shell")
    assert decision.owner == ToolOwner.CLI

    decision = router.route("generate_image", category="media")
    assert decision.owner == ToolOwner.NATIVE
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class ToolOwner(StrEnum):
    """Who executes the tool."""

    CLI = "cli"
    NATIVE = "native"
    SPECIALIST = "specialist"


@dataclass(frozen=True)
class RoutingDecision:
    """Result of a routing decision.

    Attributes
    ----------
    owner:
        Which execution backend owns this tool call.
    reason:
        Human-readable explanation (for logging / telemetry).
    specialist_name:
        If ``owner == ToolOwner.SPECIALIST``, the name of the target agent.
    metadata:
        Arbitrary extra context (risk level, category, etc.).
    """

    owner: ToolOwner
    reason: str
    specialist_name: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class ToolRoutingLayer:
    """Stateless routing layer for hybrid tool dispatch.

    Parameters
    ----------
    specialist_map:
        Mapping of ``tool_name → specialist_agent_name``.  Populated from
        user / admin configuration (e.g. LLM settings or MCP config).
    extra_native_categories:
        Additional category names to treat as NATIVE-only, beyond the
        built-in ``NATIVE_CATEGORIES`` set.
    extra_cli_categories:
        Additional category names eligible for CLI routing, beyond the
        built-in ``CLI_CATEGORIES`` set.
    """

    # Categories that must stay server-side — II-Agent intellectual property
    # or platform integrations that the CLI cannot fulfil.
    NATIVE_CATEGORIES: frozenset[str] = frozenset(
        {
            "media",
            "slides",
            "storybook",
            "planning",
            "connectors",
            "dev",
            "billing",
            "project",
            "deployment",
            "subdomain",
        }
    )

    # Tool names that are security-sensitive; must never be delegated.
    SECURITY_SENSITIVE_TOOLS: frozenset[str] = frozenset(
        {
            "get_secret",
            "set_secret",
            "delete_secret",
            "list_secrets",
            "get_api_key",
            "rotate_api_key",
            "read_credentials",
            "write_credentials",
        }
    )

    # Tool categories eligible for CLI delegation.
    CLI_CATEGORIES: frozenset[str] = frozenset(
        {
            "shell",
            "bash",
            "file",
            "filesystem",
            "code",
            "browser",
            "web",
            "search",
            "terminal",
            "general",
        }
    )

    def __init__(
        self,
        *,
        specialist_map: dict[str, str] | None = None,
        extra_native_categories: set[str] | None = None,
        extra_cli_categories: set[str] | None = None,
    ) -> None:
        self._specialist_map: dict[str, str] = specialist_map or {}
        self._native_categories: frozenset[str] = self.NATIVE_CATEGORIES | frozenset(
            extra_native_categories or set()
        )
        self._cli_categories: frozenset[str] = self.CLI_CATEGORIES | frozenset(
            extra_cli_categories or set()
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def route(
        self,
        tool_name: str,
        *,
        category: str = "general",
        risk_level: str = "low",
    ) -> RoutingDecision:
        """Return a :class:`RoutingDecision` for the given tool invocation.

        Parameters
        ----------
        tool_name:
            Canonical tool identifier (e.g. ``"bash"``, ``"generate_image"``).
        category:
            Broad functional category for the tool (used for group routing).
        risk_level:
            Caller-supplied risk classification ``"low" | "medium" | "high"``.
            High-risk tools always route NATIVE.
        """
        meta: dict[str, Any] = {
            "tool_name": tool_name,
            "category": category,
            "risk_level": risk_level,
        }

        # 1. Security gate — never leave the server.
        if tool_name in self.SECURITY_SENSITIVE_TOOLS:
            return RoutingDecision(
                owner=ToolOwner.NATIVE,
                reason=f"security-sensitive tool '{tool_name}' is always native",
                metadata=meta,
            )

        # 2. High-risk → native.
        if risk_level == "high":
            return RoutingDecision(
                owner=ToolOwner.NATIVE,
                reason=f"high-risk tool '{tool_name}' routes native",
                metadata=meta,
            )

        # 3. Proprietary / platform categories → native.
        if category in self._native_categories:
            return RoutingDecision(
                owner=ToolOwner.NATIVE,
                reason=f"category '{category}' is a native-only domain",
                metadata=meta,
            )

        # 4. Specialist allowlist.
        if tool_name in self._specialist_map:
            specialist = self._specialist_map[tool_name]
            return RoutingDecision(
                owner=ToolOwner.SPECIALIST,
                reason=f"tool '{tool_name}' is registered to specialist '{specialist}'",
                specialist_name=specialist,
                metadata=meta,
            )

        # 5. CLI-eligible categories.
        if category in self._cli_categories:
            return RoutingDecision(
                owner=ToolOwner.CLI,
                reason=f"category '{category}' is CLI-eligible",
                metadata=meta,
            )

        # 6. Fallback → native.
        return RoutingDecision(
            owner=ToolOwner.NATIVE,
            reason=f"no routing rule matched for tool '{tool_name}' in category '{category}'",
            metadata=meta,
        )

    def register_specialist(self, tool_name: str, specialist_name: str) -> None:
        """Add or update a specialist mapping at runtime."""
        self._specialist_map[tool_name] = specialist_name

    def unregister_specialist(self, tool_name: str) -> None:
        """Remove a specialist mapping (falls back to normal routing)."""
        self._specialist_map.pop(tool_name, None)

    def is_cli_eligible(self, tool_name: str, *, category: str = "general") -> bool:
        """Convenience predicate: True when :meth:`route` would return ``CLI``."""
        return self.route(tool_name, category=category).owner == ToolOwner.CLI
