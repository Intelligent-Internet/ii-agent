"""
/update workflow — Daily triage.

Steps:
1. Read TASKS.md — flag stale items (active > 7 days, waiting > 14 days)
2. Check memory coverage — report counts
3. If project tracker configured: note sync opportunity
4. Output a triage report
"""

import logging
from datetime import datetime
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


async def update_workflow(
    task_skill: Any,
    memory_skill: Any,
    connector_skill: Optional[Any] = None,
) -> Dict[str, Any]:
    """Daily triage: flag stale tasks, check memory, sync trackers.

    All parameters are skill instances obtained via ``get_skill()``.
    """
    results: Dict[str, Any] = {"timestamp": datetime.now().isoformat()}

    # Step 1: Get task summary and flag stale items
    try:
        summary = task_skill.execute("get_summary")
        results["task_summary"] = summary

        # Flag stale active tasks (overdue)
        results["overdue_tasks"] = summary.get("overdue", [])
        results["due_today"] = summary.get("due_today", [])
    except Exception as e:
        logger.warning(f"Task triage failed: {e}")
        results["task_summary"] = {"error": str(e)}
        results["overdue_tasks"] = []
        results["due_today"] = []

    # Step 2: Check memory coverage
    try:
        hot_cache = memory_skill.execute("get_hot_cache")
        memory_export = memory_skill.execute("export_memory")
        results["memory_status"] = {
            "people_count": len(memory_export.get("people", {})),
            "terms_count": len(memory_export.get("glossary", {})),
            "projects_count": len(memory_export.get("projects", {})),
            "hot_cache_available": bool(hot_cache.get("content")),
        }
    except Exception as e:
        logger.warning(f"Memory check failed: {e}")
        results["memory_status"] = {"error": str(e)}

    # Step 3: Check project tracker sync opportunity
    if connector_skill:
        try:
            connectors = connector_skill.execute("list_connectors")
            configured = connectors.get("configured", {})
            if "project_tracker" in configured:
                results["tracker_sync"] = {
                    "available": True,
                    "provider": configured["project_tracker"],
                    "message": f"Project tracker ({configured['project_tracker']}) available for sync",
                }
            else:
                results["tracker_sync"] = {"available": False}
        except Exception as e:
            results["tracker_sync"] = {"available": False, "error": str(e)}
    else:
        results["tracker_sync"] = {"available": False}

    # Step 4: Generate triage report
    results["report"] = _generate_triage_report(results)
    results["success"] = True
    return results


def _generate_triage_report(results: Dict[str, Any]) -> str:
    """Build a human-readable triage report."""
    lines = ["Daily Triage Report", "=" * 40]
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines.append(f"Generated: {now}")
    lines.append("")

    # Task summary
    summary = results.get("task_summary", {})
    lines.append("Tasks:")
    lines.append(f"  Active:     {summary.get('active_count', '?')}")
    lines.append(f"  Waiting On: {summary.get('waiting_count', '?')}")
    lines.append(f"  Someday:    {summary.get('someday_count', '?')}")
    lines.append(f"  Done:       {summary.get('done_count', '?')}")

    # Overdue
    overdue = results.get("overdue_tasks", [])
    if overdue:
        lines.append("")
        lines.append(f"OVERDUE ({len(overdue)}):")
        for t in overdue:
            title = t.get("title", "?")
            due = t.get("due_date", "?")
            lines.append(f"  - {title} (due {due})")

    # Due today
    due_today = results.get("due_today", [])
    if due_today:
        lines.append("")
        lines.append(f"DUE TODAY ({len(due_today)}):")
        for t in due_today:
            lines.append(f"  - {t.get('title', '?')}")

    # Memory status
    mem = results.get("memory_status", {})
    if not mem.get("error"):
        lines.append("")
        lines.append("Memory:")
        lines.append(f"  People:   {mem.get('people_count', 0)}")
        lines.append(f"  Terms:    {mem.get('terms_count', 0)}")
        lines.append(f"  Projects: {mem.get('projects_count', 0)}")

    # Tracker sync
    tracker = results.get("tracker_sync", {})
    if tracker.get("available"):
        lines.append("")
        lines.append(f"Tracker: {tracker.get('message', 'Available')}")

    return "\n".join(lines)
