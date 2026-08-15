"""Proxy capabilities — what each client exposes to the agent loop.

A "capability" is anything the LLM can invoke during an agent turn:
either a tool (callable with structured input) or a skill (advisory recipe
appended to the system prompt). Each request from a ``ii_agent.clients.*``
subpackage carries a single ``requested_capabilities`` payload that may
mix four sources:

* ``client_tools``  — JSON descriptors shipped over the wire by the client.
                      Become :class:`Function` stubs flagged
                      ``external_execution=True``: the agent loop pauses on
                      call and waits for the client to ship results back via
                      ``external_tool_results``.
* ``client_skills`` — JSON descriptors rendered into the system prompt as a
                      short advisory catalog. No Python execution.
* ``core_tools``    — names from ii-agent's :data:`TOOL_CLASS_MAP` that the
                      client wants to opt in to. Each client subpackage
                      decides which core tools it allows via an
                      ``allowed_core_tools`` whitelist.
* ``core_skills``   — names from the user's persisted ``SkillTool`` registry
                      to keep, gated by an ``allowed_core_skills`` whitelist.

By default each client subpackage loads nothing from the core catalog —
it only exposes what the request explicitly asks for AND what the client
has whitelisted.

Helpers are pure (no I/O, no DB) and parameterised by ``log_prefix`` /
``heading`` so multi-client deployments stay greppable.
"""

from __future__ import annotations

from typing import Any, Iterable, List, Optional

from ii_agent.agents.factory.tool_manager import AgentToolManager
from ii_agent.agents.factory.tools import TOOL_CLASS_MAP
from ii_agent.agents.skills.prompt_db import generate_skill_tool_description
from ii_agent.agents.tools.function import Function
from ii_agent.core.logger import logger


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _normalize_name_set(values: Optional[Iterable[str]]) -> Optional[set[str]]:
    if not values:
        return None
    normalized = {
        value.strip().lower()
        for value in values
        if isinstance(value, str) and value.strip()
    }
    return normalized or None


def _normalize_name_list(values: Optional[Iterable[str]]) -> List[str]:
    if not values:
        return []
    out: List[str] = []
    seen: set[str] = set()
    for value in values:
        if not isinstance(value, str):
            continue
        cleaned = value.strip().lower()
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        out.append(cleaned)
    return out


def _tool_name(tool: Any) -> str:
    name = getattr(tool, "name", "")
    return name.strip().lower() if isinstance(name, str) else ""


def _coerce_to_dict(value: Optional[Any]) -> Optional[dict[str, Any]]:
    """Accept either a Pydantic model (``model_dump``) or a plain ``dict``."""
    if value is None:
        return None
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if isinstance(value, dict):
        return value
    return None


def _pick_requested(
    requested: Optional[Iterable[str]],
    default: Optional[Iterable[str]],
) -> set[str]:
    """Union of the client default and the user's request.

    Both inputs are normalized (lowercased, stripped, de-duped). For
    example, ``default = {A, B}`` + ``requested = {A, C}`` → ``{A, B, C}``.
    Returns an empty set when neither side specifies anything.
    """
    return (_normalize_name_set(requested) or set()) | (
        _normalize_name_set(default) or set()
    )


# ---------------------------------------------------------------------------
# Requested capabilities (parsed view of the wire payload)
# ---------------------------------------------------------------------------


class RequestedCapabilities:
    """Normalized view of a client's ``requested_capabilities`` payload.

    Attributes are always lists (possibly empty), so callers don't have to
    juggle ``None`` checks at the use site.
    """

    __slots__ = (
        "client_tools",
        "client_skills",
        "core_tools",
        "core_skills",
        "connector",
        "raw",
    )

    def __init__(
        self,
        *,
        client_tools: List[dict[str, Any]],
        client_skills: List[dict[str, Any]],
        core_tools: List[str],
        core_skills: List[str],
        connector: Optional[str],
        raw: dict[str, Any],
    ) -> None:
        self.client_tools = client_tools
        self.client_skills = client_skills
        self.core_tools = core_tools
        self.core_skills = core_skills
        self.connector = connector
        self.raw = raw

    @classmethod
    def parse(cls, payload: Optional[Any]) -> "RequestedCapabilities":
        as_dict = _coerce_to_dict(payload) or {}

        def _list_of_dicts(key: str) -> List[dict[str, Any]]:
            value = as_dict.get(key) or []
            if not isinstance(value, list):
                return []
            return [item for item in value if isinstance(item, dict)]

        connector = as_dict.get("connector")
        if not isinstance(connector, str) or not connector.strip():
            connector = None
        else:
            connector = connector.strip().lower()

        return cls(
            client_tools=_list_of_dicts("client_tools"),
            client_skills=_list_of_dicts("client_skills"),
            core_tools=_normalize_name_list(as_dict.get("core_tools")),
            core_skills=_normalize_name_list(as_dict.get("core_skills")),
            connector=connector,
            raw=as_dict,
        )


# ---------------------------------------------------------------------------
# Core agent capabilities (per-client defaults unioned with the user request)
# ---------------------------------------------------------------------------


def include_core_tools(
    requested: Optional[Iterable[str]],
    *,
    default_core_tools: Optional[Iterable[str]] = None,
    log_prefix: str = "client",
) -> List[Any]:
    """Instantiate core tools from the union of the user request and
    ``default_core_tools``.

    No allow-list gating: both the request and the defaults are trusted.
    Names not registered in :data:`TOOL_CLASS_MAP` are dropped with a
    warning.
    """
    selected = _pick_requested(requested, default_core_tools)
    if not selected:
        return []

    instances: List[Any] = []
    for tool_name in sorted(selected):
        target_name = next(
            (
                registered
                for registered in TOOL_CLASS_MAP
                if registered.strip().lower() == tool_name
            ),
            None,
        )
        if target_name is None:
            logger.warning(
                "[%s] Core tool '%s' is not registered", log_prefix, tool_name
            )
            continue
        instance = AgentToolManager.convert_tool(target_name)
        if instance is None:
            logger.warning(
                "[%s] Failed to instantiate core tool '%s'", log_prefix, tool_name
            )
            continue
        instances.append(instance)
    return instances


async def include_core_skills(
    requested: Optional[Iterable[str]],
    *,
    skill_creator: Optional[Any],
    default_core_skills: Optional[Iterable[str]] = None,
    log_prefix: str = "client",
) -> tuple[Optional[Any], Optional[str]]:
    """Build a ``SkillTool`` for skills from the union of the user request
    and ``default_core_skills``.

    Returns ``(skill_tool, prompt_section)``. Either may be ``None`` —
    callers should treat ``None`` as "drop the skill tool entirely / don't
    append a prompt section".
    """
    if skill_creator is None:
        return None, None

    selected = _pick_requested(requested, default_core_skills)
    if not selected:
        return None, None

    skill_tool = await skill_creator.create_skill_tool()
    if skill_tool is None:
        return None, None

    registry = getattr(skill_tool, "_skills_registry", None)
    if not isinstance(registry, dict):
        return None, None

    filtered = {
        name: skill
        for name, skill in registry.items()
        if name.strip().lower() in selected
    }
    missing = selected - {name.strip().lower() for name in registry.keys()}
    for name in sorted(missing):
        logger.warning(
            "[%s] Core skill '%s' not found in user registry", log_prefix, name
        )

    if not filtered:
        return None, None

    skill_tool._skills_registry = filtered
    skill_tool.description = generate_skill_tool_description(list(filtered.values()))
    return skill_tool, skill_tool.description


async def include_connector_tools(
    requested: Optional[str],
    *,
    connector_tool: Optional[Any],
    workspace_manager: Optional[Any] = None,
    default_connectors: Optional[Iterable[str]] = None,
    log_prefix: str = "client",
) -> List[Any]:
    """Instantiate connector tools for the user-requested connector,
    falling back to the first entry of ``default_connectors``.

    Connector is a single-slot capability (one connector per agent run),
    so unlike tools/skills there's no union — the user's choice wins, and
    we only consult ``default_connectors`` when the request is silent.
    Returns ``[]`` when nothing is selected, no ``connector_tool`` is
    wired, or instantiation fails.
    """
    selected = (requested or "").strip().lower() or next(
        iter(sorted(_normalize_name_set(default_connectors) or set())), None
    )
    if not selected or connector_tool is None:
        return []

    try:
        connector_tools = await connector_tool.create_connector_tools(
            workspace_manager=workspace_manager,
        )
    except Exception as exc:
        logger.error(
            "[%s] Failed to load connector '%s': %s",
            log_prefix,
            selected,
            exc,
            exc_info=True,
        )
        return []

    if connector_tools:
        logger.info(
            "[%s] Added %d connector tools (%s)",
            log_prefix,
            len(connector_tools),
            selected,
        )
    return connector_tools or []


def dedupe_tools(agent_tools: List[Any]) -> List[Any]:
    """Drop duplicate tools by case-insensitive name, preserving order."""
    seen: set[str] = set()
    out: List[Any] = []
    for tool in agent_tools:
        name = _tool_name(tool)
        if not name:
            out.append(tool)
            continue
        if name in seen:
            continue
        seen.add(name)
        out.append(tool)
    return out


# ---------------------------------------------------------------------------
# Client-defined capabilities
# ---------------------------------------------------------------------------


def _placeholder_tool_entrypoint(**_: Any) -> str:
    """Body of every external-execution Function — never actually invoked."""
    return "This tool is executed by the client runtime."


def _build_external_function(
    *,
    name: str,
    display_name: str,
    description: str,
    parameters: dict[str, Any],
) -> Function:
    return Function(
        name=name,
        description=description,
        parameters=parameters,
        display_name=display_name,
        entrypoint=_placeholder_tool_entrypoint,
        skip_entrypoint_processing=True,
        external_execution=True,
        show_result=True,
    )


def build_client_tools(
    client_tool_specs: Optional[Iterable[dict[str, Any]]],
    *,
    log_prefix: str = "client",
) -> List[Function]:
    """Build external-execution Functions from ``client_tools`` descriptors.

    Each descriptor must carry ``name`` and ``description``; ``input_schema``
    falls back to an open object schema. ``aliases`` and ``display_name`` are
    optional.
    """
    if not client_tool_specs:
        return []

    client_tools: List[Function] = []
    for spec in client_tool_specs:
        if not isinstance(spec, dict):
            continue
        name = spec.get("name")
        description = spec.get("description")
        if not isinstance(name, str) or not name.strip():
            continue
        if not isinstance(description, str) or not description.strip():
            continue

        display_name = spec.get("display_name")
        if not isinstance(display_name, str) or not display_name.strip():
            display_name = name

        parameters = spec.get("input_schema")
        if not isinstance(parameters, dict) or not parameters:
            parameters = {"type": "object", "properties": {}, "required": []}

        aliases = spec.get("aliases") or []
        if not isinstance(aliases, list):
            aliases = []
        published_names = [name] + [
            a.strip() for a in aliases if isinstance(a, str) and a.strip()
        ]

        seen: set[str] = set()
        for published_name in published_names:
            if published_name in seen:
                continue
            seen.add(published_name)
            client_tools.append(
                _build_external_function(
                    name=published_name,
                    display_name=display_name,
                    description=description,
                    parameters=parameters,
                )
            )

    if not client_tools and any(
        isinstance(spec, dict) for spec in client_tool_specs
    ):
        logger.warning(
            "[%s] client_tools provided but no valid descriptors were published",
            log_prefix,
        )
    return client_tools


def build_client_skill_prompt(
    client_skill_specs: Optional[Iterable[dict[str, Any]]],
    *,
    heading: str = "Skills available in the client runtime:",
) -> Optional[str]:
    """Render a short skill catalog for inclusion in the system prompt."""
    if not client_skill_specs:
        return None

    lines: List[str] = []
    for skill in client_skill_specs:
        if not isinstance(skill, dict):
            continue
        name = skill.get("name")
        description = skill.get("description")
        if not isinstance(name, str) or not name.strip():
            continue
        if not isinstance(description, str) or not description.strip():
            continue
        lines.append(f"- {name}: {description}")

    if not lines:
        return None
    return f"{heading}\n" + "\n".join(lines)
