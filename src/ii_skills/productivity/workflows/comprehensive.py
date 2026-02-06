"""
/update --comprehensive workflow — Deep scan.

Everything in /update PLUS:
1. Scan email for unread count / commitments (if configured)
2. Scan calendar for upcoming meetings that need prep (if configured)
3. Scan chat for unread channels (if configured)
4. Flag missed todos and suggest new memory entries

All connector interactions degrade gracefully when not configured.
"""

import logging
from datetime import datetime
from typing import Any, Dict, Optional

from ii_skills.productivity.workflows.update import update_workflow

logger = logging.getLogger(__name__)


async def comprehensive_workflow(
    task_skill: Any,
    memory_skill: Any,
    connector_skill: Optional[Any] = None,
) -> Dict[str, Any]:
    """Deep scan: full triage + email/calendar/chat scan.

    Extends update_workflow with connector-driven intelligence.
    """
    # Start with the standard update
    results = await update_workflow(task_skill, memory_skill, connector_skill)
    results["comprehensive"] = True

    if not connector_skill:
        results["scan"] = {
            "email": {"scanned": False, "reason": "No connector skill"},
            "calendar": {"scanned": False, "reason": "No connector skill"},
            "chat": {"scanned": False, "reason": "No connector skill"},
        }
        results["report"] = _extend_report(results["report"], results["scan"])
        return results

    scan: Dict[str, Any] = {}

    # Step 1: Scan email (if configured)
    try:
        email_result = connector_skill.execute("read_inbox", limit=10, unread_only=True)
        if "error" in email_result:
            scan["email"] = {"scanned": False, "reason": email_result["error"]}
        else:
            messages = email_result.get("messages", [])
            scan["email"] = {
                "scanned": True,
                "unread_count": email_result.get("count", len(messages)),
                "subjects": [m.get("subject", "?") for m in messages[:5]],
            }
    except Exception as e:
        scan["email"] = {"scanned": False, "reason": str(e)}

    # Step 2: Scan calendar (if configured)
    try:
        cal_result = connector_skill.execute("get_today_schedule")
        if "error" in cal_result:
            scan["calendar"] = {"scanned": False, "reason": cal_result["error"]}
        else:
            events = cal_result.get("events", [])
            scan["calendar"] = {
                "scanned": True,
                "event_count": cal_result.get("count", len(events)),
                "events": [e.get("title", "?") for e in events[:5]],
            }
    except Exception as e:
        scan["calendar"] = {"scanned": False, "reason": str(e)}

    # Step 3: Scan chat (if configured)
    try:
        chat_result = connector_skill.execute("read_messages", channel="general", limit=5)
        if "error" in chat_result:
            scan["chat"] = {"scanned": False, "reason": chat_result["error"]}
        else:
            messages = chat_result.get("messages", [])
            scan["chat"] = {
                "scanned": True,
                "recent_count": chat_result.get("count", len(messages)),
            }
    except Exception as e:
        scan["chat"] = {"scanned": False, "reason": str(e)}

    results["scan"] = scan
    results["report"] = _extend_report(results["report"], scan)
    return results


def _extend_report(base_report: str, scan: Dict[str, Any]) -> str:
    """Append comprehensive scan results to the base triage report."""
    lines = [base_report, "", "Comprehensive Scan", "-" * 40]

    # Email
    email = scan.get("email", {})
    if email.get("scanned"):
        lines.append(f"Email: {email.get('unread_count', 0)} unread")
        for subj in email.get("subjects", []):
            lines.append(f"  - {subj}")
    else:
        reason = email.get("reason", "Not configured")
        lines.append(f"Email: Skipped ({reason})")

    # Calendar
    cal = scan.get("calendar", {})
    if cal.get("scanned"):
        lines.append(f"Calendar: {cal.get('event_count', 0)} events today")
        for evt in cal.get("events", []):
            lines.append(f"  - {evt}")
    else:
        reason = cal.get("reason", "Not configured")
        lines.append(f"Calendar: Skipped ({reason})")

    # Chat
    chat = scan.get("chat", {})
    if chat.get("scanned"):
        lines.append(f"Chat: {chat.get('recent_count', 0)} recent messages")
    else:
        reason = chat.get("reason", "Not configured")
        lines.append(f"Chat: Skipped ({reason})")

    return "\n".join(lines)
