"""Skill-based A2A agent routing.

Given a task description (prompt text and optional hint tags), the router
selects the most appropriate registered agent from an :class:`AgentRegistry`.

The routing algorithm is intentionally lightweight for the Phase 4
placeholder:

1. If the registry contains exactly one agent, return it unconditionally.
2. Score each agent by how many of *hint_tags* appear in the flat tag set
   across all of its skills.
3. Break ties by name (alphabetical) for determinism.
4. If no agent has any matching tag *and* a ``fallback_name`` is registered,
   return it.  Otherwise return the highest-scoring agent (or None if the
   registry is empty).

This module intentionally has no I/O and no async — it operates on
an already-populated registry snapshot so callers can use it synchronously.
"""

from __future__ import annotations

import logging
from typing import List, Optional

from ii_agent.integrations.a2a.registry import AgentCard, AgentRegistry

logger = logging.getLogger(__name__)


class AgentRouter:
    """Select the best-matching A2A agent for a task.

    Parameters
    ----------
    registry:
        The live registry to query.
    fallback_name:
        Name of the agent to use when no skill-tag match is found.
        If *None* and no match exists, the highest-scoring (by name) agent
        is returned.
    """

    def __init__(
        self,
        registry: AgentRegistry,
        *,
        fallback_name: Optional[str] = None,
    ) -> None:
        self._registry = registry
        self._fallback_name = fallback_name

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def route(
        self,
        prompt: str,
        *,
        hint_tags: Optional[List[str]] = None,
    ) -> Optional[AgentCard]:
        """Return the best agent for *prompt*, or None if the registry is empty.

        Parameters
        ----------
        prompt:
            The user-facing task description.  Used for logging only at this
            phase; future phases may add semantic similarity scoring.
        hint_tags:
            Optional list of tags (e.g. ``["code", "python"]``) to steer
            routing.  Case-insensitive.
        """
        agents = self._registry.list_all()
        if not agents:
            logger.warning("AgentRouter: registry is empty, no agent available")
            return None

        if len(agents) == 1:
            card = agents[0]
            logger.debug("AgentRouter: single agent %r selected (no routing needed)", card.name)
            return card

        normalised_hints = [t.lower() for t in (hint_tags or [])]
        scored = self._score(agents, normalised_hints)

        # Best match: highest score, then alphabetical name for determinism.
        best = max(scored, key=lambda t: (t[1], -ord(t[0].name[0]) if t[0].name else 0))
        best_card, best_score = best

        if best_score == 0 and self._fallback_name:
            fallback = self._registry.get(self._fallback_name)
            if fallback is not None:
                logger.info(
                    "AgentRouter: no tag match for %r; using fallback agent %r",
                    prompt[:80],
                    self._fallback_name,
                )
                return fallback

        logger.info(
            "AgentRouter: selected agent %r (score=%d) for prompt %r",
            best_card.name,
            best_score,
            prompt[:80],
        )
        return best_card

    def route_by_skill_id(self, skill_id: str) -> Optional[AgentCard]:
        """Return the agent that exposes a skill with the given *skill_id*."""
        for card in self._registry.list_all():
            for skill in card.skills:
                if skill.id == skill_id:
                    return card
        return None

    def route_by_extension(self, extension_uri: str) -> List[AgentCard]:
        """Return all agents that advertise *extension_uri* in their agent card."""
        return [card for card in self._registry.list_all() if extension_uri in card.extension_uris]

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    @staticmethod
    def _score(agents: List[AgentCard], hint_tags: List[str]) -> List[tuple[AgentCard, int]]:
        """Assign each agent a score = number of hint_tags found in its tag set."""
        if not hint_tags:
            return [(a, 0) for a in agents]

        scored: List[tuple[AgentCard, int]] = []
        for card in agents:
            agent_tags = set(card.all_tags)
            score = sum(1 for t in hint_tags if t in agent_tags)
            scored.append((card, score))
        return scored
