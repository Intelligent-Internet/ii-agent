"""Desktop proxy tools for Cowork desktop execution modes."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

from ii_agent.core.logger import logger
from ii_agent.agents.tools.function import Function


def _placeholder_tool_entrypoint(**_: Any) -> str:
    return "This tool is executed by the II Agent desktop runtime."


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


def _normalize_aliases(raw_aliases: Any) -> List[str]:
    if not isinstance(raw_aliases, list):
        return []

    aliases: List[str] = []
    for alias in raw_aliases:
        if not isinstance(alias, str):
            continue
        normalized = alias.strip()
        if not normalized:
            continue
        aliases.append(normalized)
    return aliases


def _normalize_requested_names(
    requested_tool_names: Optional[Iterable[str]],
) -> Optional[set[str]]:
    if not requested_tool_names:
        return None

    normalized_names = {
        tool_name.strip().lower()
        for tool_name in requested_tool_names
        if isinstance(tool_name, str) and tool_name.strip()
    }
    return normalized_names or None


def _iter_desktop_tool_descriptors(
    desktop_capabilities: Optional[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    if not isinstance(desktop_capabilities, dict):
        return []
    tools = desktop_capabilities.get("tools")
    if not isinstance(tools, list):
        return []
    return [tool for tool in tools if isinstance(tool, dict)]


def build_desktop_proxy_tools(
    desktop_capabilities: Optional[Dict[str, Any]] = None,
    requested_tool_names: Optional[Iterable[str]] = None,
) -> List[Function]:
    requested_names = _normalize_requested_names(requested_tool_names)
    tool_specs = _iter_desktop_tool_descriptors(desktop_capabilities)
    if not tool_specs:
        logger.warning(
            "Cowork desktop tool runtime requested but no desktop capability descriptors were provided"
        )
        return []

    proxy_tools = []
    for tool_spec in tool_specs:
        name = tool_spec.get("name")
        description = tool_spec.get("description")
        if not isinstance(name, str) or not name.strip():
            continue
        if not isinstance(description, str) or not description.strip():
            continue

        display_name = tool_spec.get("display_name")
        if not isinstance(display_name, str) or not display_name.strip():
            display_name = name
        parameters = tool_spec.get("input_schema")
        if not isinstance(parameters, dict):
            parameters = {"type": "object", "properties": {}, "required": []}
        aliases = _normalize_aliases(tool_spec.get("aliases"))

        names_to_publish: List[str]
        if requested_names is None:
            names_to_publish = [name]
        else:
            candidate_names = [name, *aliases]
            names_to_publish = []
            for candidate_name in candidate_names:
                if candidate_name.strip().lower() not in requested_names:
                    continue
                if candidate_name in names_to_publish:
                    continue
                names_to_publish.append(candidate_name)
            if not names_to_publish:
                continue

        for published_name in names_to_publish:
            proxy_tools.append(
                _build_external_function(
                    name=published_name,
                    display_name=display_name,
                    description=description,
                    parameters=parameters,
                )
            )

    return proxy_tools


def build_desktop_skill_context(
    desktop_capabilities: Optional[Dict[str, Any]] = None,
    requested_skill_names: Optional[Iterable[str]] = None,
) -> Optional[str]:
    if not isinstance(desktop_capabilities, dict):
        return None

    skills = desktop_capabilities.get("skills")
    if not isinstance(skills, list) or not skills:
        return None

    requested_names = _normalize_requested_names(requested_skill_names)
    skill_lines: List[str] = []
    for skill in skills:
        if not isinstance(skill, dict):
            continue
        name = skill.get("name")
        description = skill.get("description")
        if not isinstance(name, str) or not name.strip():
            continue
        if requested_names is not None and name.strip().lower() not in requested_names:
            continue
        if not isinstance(description, str) or not description.strip():
            continue
        skill_lines.append(f"- {name}: {description}")

    if not skill_lines:
        return None

    return "Desktop skills available in this runtime:\n" + "\n".join(skill_lines)
