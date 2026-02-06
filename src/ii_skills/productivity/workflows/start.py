"""
/start workflow — Bootstrap a productivity workspace.

Steps:
1. Initialize TASKS.md from template (if missing)
2. Initialize memory/ directory structure (if missing)
3. If connectors configured: report available integrations
4. Output a welcome summary
"""

import logging
from datetime import datetime
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


async def start_workflow(
    task_skill: Any,
    memory_skill: Any,
    connector_skill: Optional[Any] = None,
    workspace_root: str = "",
) -> Dict[str, Any]:
    """Bootstrap the productivity workspace.

    Creates TASKS.md, memory/ directory, and reports available connectors.
    All parameters are skill instances obtained via ``get_skill()``.
    """
    results: Dict[str, Any] = {"timestamp": datetime.now().isoformat()}

    # Step 1: Initialize tasks
    try:
        kwargs = {"workspace_root": workspace_root} if workspace_root else {}
        tasks_result = task_skill.execute("initialize_tasks", **kwargs)
        results["tasks"] = tasks_result
    except Exception as e:
        logger.warning(f"Task initialization failed: {e}")
        results["tasks"] = {"success": False, "error": str(e)}

    # Step 2: Initialize memory
    try:
        kwargs = {"workspace_root": workspace_root} if workspace_root else {}
        memory_result = memory_skill.execute("initialize_memory", **kwargs)
        results["memory"] = memory_result
    except Exception as e:
        logger.warning(f"Memory initialization failed: {e}")
        results["memory"] = {"success": False, "error": str(e)}

    # Step 3: Check connectors (if available)
    if connector_skill:
        try:
            connectors_result = connector_skill.execute("list_connectors")
            results["connectors"] = connectors_result
        except Exception as e:
            logger.warning(f"Connector listing failed: {e}")
            results["connectors"] = {"configured_count": 0, "error": str(e)}
    else:
        results["connectors"] = {"configured_count": 0, "message": "No connector skill available"}

    # Step 4: Generate welcome summary
    results["summary"] = _generate_welcome_summary(results)
    results["success"] = True
    return results


def _generate_welcome_summary(results: Dict[str, Any]) -> str:
    """Build a human-readable welcome message."""
    lines = ["Productivity workspace initialized!"]

    # Tasks
    tasks = results.get("tasks", {})
    if tasks.get("created"):
        lines.append("- TASKS.md created from template")
    elif tasks.get("success"):
        lines.append("- TASKS.md already exists")

    # Memory
    memory = results.get("memory", {})
    created = memory.get("created", [])
    if created:
        lines.append(f"- Memory directory initialized ({len(created)} items created)")
    elif memory.get("success"):
        lines.append("- Memory directory already exists")

    # Connectors
    connectors = results.get("connectors", {})
    configured = connectors.get("configured_count", 0)
    if configured > 0:
        providers = connectors.get("configured", {})
        provider_list = ", ".join(f"{cat}={prov}" for cat, prov in providers.items())
        lines.append(f"- {configured} connector(s) configured: {provider_list}")
    else:
        lines.append("- No external connectors configured (add .mcp.json to enable)")

    lines.append("")
    lines.append("Ready! Try: 'What's on my plate?', 'Add a task', or 'Update my tasks'")
    return "\n".join(lines)
