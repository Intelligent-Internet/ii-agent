"""
Productivity Skill

Orchestrates cross-skill workflows that tie memory, tasks, and connectors
into cohesive daily productivity routines.

Workflows:
    /start                  — Bootstrap workspace (TASKS.md + memory + connectors)
    /update                 — Daily triage (stale tasks, memory gaps, tracker sync)
    /update --comprehensive — Deep scan (email, calendar, chat)
    daily_brief             — Generate morning briefing
    weekly_review           — Generate weekly review summary

Cross-skill references use ``get_skill()`` — no import coupling.

Fork safety: Entirely new directory, no modifications to existing files.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from ii_skills import BaseSkill, register_skill

logger = logging.getLogger(__name__)

__version__ = "1.0.0"
__author__ = "II-Agent System"


@register_skill
class ProductivitySkill(BaseSkill):
    """Productivity workflows: /start, /update, daily briefing."""

    name = "productivity"
    version = __version__
    description = "Productivity workflows: /start, /update, daily briefing"

    SKILL_DIR = Path(__file__).parent

    def __init__(self, config: Optional[Dict] = None):
        super().__init__(config)
        self._task_skill = None
        self._memory_skill = None
        self._connector_skill = None

    def initialize(self) -> bool:
        """Resolve dependent skills via get_skill()."""
        from ii_skills import get_skill

        workspace_root = self.config.get("workspace_root", str(Path.cwd()))
        skill_config = {"workspace_root": workspace_root}

        self._task_skill = get_skill("task_management", config=skill_config)
        if self._task_skill:
            self._task_skill.initialize()

        self._memory_skill = get_skill("memory", config=skill_config)
        if self._memory_skill:
            self._memory_skill.initialize()

        self._connector_skill = get_skill("connectors", config=skill_config)
        if self._connector_skill:
            self._connector_skill.initialize()

        self._initialized = True
        return True

    def validate_config(self) -> List[str]:
        """Check that required dependent skills are available."""
        issues = []
        from ii_skills import get_skill

        if not get_skill("task_management"):
            issues.append("task_management skill not found")
        if not get_skill("memory"):
            issues.append("memory skill not found")
        # connectors is optional
        return issues

    def get_capabilities(self) -> List[str]:
        """Return list of actions this skill provides."""
        return [
            "start",
            "update",
            "update_comprehensive",
            "daily_brief",
            "weekly_review",
        ]

    def execute(self, action: str, **kwargs) -> Dict:
        """Execute a productivity action."""
        loop = None
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            pass

        if loop and loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, self._execute_async(action, **kwargs))
                return future.result()
        return asyncio.run(self._execute_async(action, **kwargs))

    async def _execute_async(self, action: str, **kwargs) -> Dict:
        """Async action router."""
        actions = {
            "start": self._start,
            "update": self._update,
            "update_comprehensive": self._update_comprehensive,
            "daily_brief": self._daily_brief,
            "weekly_review": self._weekly_review,
        }

        handler = actions.get(action)
        if not handler:
            raise NotImplementedError(f"Action '{action}' not implemented")
        return await handler(**kwargs)

    # ------------------------------------------------------------------
    # Ensure skills are resolved
    # ------------------------------------------------------------------

    def _ensure_initialized(self) -> None:
        """Lazily initialize if needed."""
        if not self._initialized:
            self.initialize()

    # ------------------------------------------------------------------
    # Workflow Actions
    # ------------------------------------------------------------------

    async def _start(self, **kwargs) -> Dict:
        """/start — Bootstrap workspace."""
        self._ensure_initialized()
        from ii_skills.productivity.workflows.start import start_workflow

        workspace_root = kwargs.get("workspace_root", self.config.get("workspace_root", ""))
        return await start_workflow(
            task_skill=self._task_skill,
            memory_skill=self._memory_skill,
            connector_skill=self._connector_skill,
            workspace_root=workspace_root,
        )

    async def _update(self, **kwargs) -> Dict:
        """/update — Daily triage."""
        self._ensure_initialized()
        from ii_skills.productivity.workflows.update import update_workflow

        return await update_workflow(
            task_skill=self._task_skill,
            memory_skill=self._memory_skill,
            connector_skill=self._connector_skill,
        )

    async def _update_comprehensive(self, **kwargs) -> Dict:
        """/update --comprehensive — Deep scan."""
        self._ensure_initialized()
        from ii_skills.productivity.workflows.comprehensive import comprehensive_workflow

        return await comprehensive_workflow(
            task_skill=self._task_skill,
            memory_skill=self._memory_skill,
            connector_skill=self._connector_skill,
        )

    async def _daily_brief(self, **kwargs) -> Dict:
        """Generate a morning briefing from tasks + memory + connectors."""
        self._ensure_initialized()

        brief: Dict[str, Any] = {
            "date": datetime.now().strftime("%Y-%m-%d"),
            "timestamp": datetime.now().isoformat(),
        }

        # Tasks
        try:
            summary = self._task_skill.execute("get_summary")
            active = self._task_skill.execute("get_active")
            brief["tasks"] = {
                "summary": summary,
                "active": active.get("active", []),
                "overdue": summary.get("overdue", []),
                "due_today": summary.get("due_today", []),
            }
        except Exception as e:
            brief["tasks"] = {"error": str(e)}

        # Memory snapshot
        try:
            export = self._memory_skill.execute("export_memory")
            brief["memory"] = {
                "people_count": len(export.get("people", {})),
                "terms_count": len(export.get("glossary", {})),
                "projects_count": len(export.get("projects", {})),
            }
        except Exception as e:
            brief["memory"] = {"error": str(e)}

        # Connector status
        if self._connector_skill:
            try:
                health = self._connector_skill.execute("check_health")
                brief["connectors"] = health
            except Exception as e:
                brief["connectors"] = {"error": str(e)}
        else:
            brief["connectors"] = {"overall": "none", "message": "No connectors configured"}

        # Format
        brief["formatted"] = self._format_brief(brief)
        brief["success"] = True
        return brief

    async def _weekly_review(self, **kwargs) -> Dict:
        """Generate a weekly review summary."""
        self._ensure_initialized()

        review: Dict[str, Any] = {
            "week_ending": datetime.now().strftime("%Y-%m-%d"),
            "timestamp": datetime.now().isoformat(),
        }

        # Tasks summary
        try:
            summary = self._task_skill.execute("get_summary")
            tasks = self._task_skill.execute("get_tasks")
            done_this_week = [
                t for t in tasks.get("done", [])
                if t.get("completed_date") and self._is_this_week(t["completed_date"])
            ]
            review["tasks"] = {
                "active_count": summary.get("active_count", 0),
                "waiting_count": summary.get("waiting_count", 0),
                "completed_this_week": len(done_this_week),
                "completed_items": [t["title"] for t in done_this_week],
                "overdue_count": len(summary.get("overdue", [])),
            }
        except Exception as e:
            review["tasks"] = {"error": str(e)}

        # Memory growth
        try:
            export = self._memory_skill.execute("export_memory")
            review["memory"] = {
                "total_people": len(export.get("people", {})),
                "total_terms": len(export.get("glossary", {})),
                "total_projects": len(export.get("projects", {})),
            }
        except Exception as e:
            review["memory"] = {"error": str(e)}

        review["formatted"] = self._format_weekly_review(review)
        review["success"] = True
        return review

    # ------------------------------------------------------------------
    # Formatting Helpers
    # ------------------------------------------------------------------

    def _format_brief(self, brief: Dict) -> str:
        """Format daily brief as readable text."""
        lines = [f"Daily Briefing — {brief['date']}", "=" * 40, ""]

        # Tasks
        tasks = brief.get("tasks", {})
        if not tasks.get("error"):
            summary = tasks.get("summary", {})
            lines.append(f"Tasks: {summary.get('active_count', 0)} active, "
                         f"{summary.get('waiting_count', 0)} waiting")

            overdue = tasks.get("overdue", [])
            if overdue:
                lines.append(f"  OVERDUE: {len(overdue)}")
                for t in overdue:
                    lines.append(f"    - {t.get('title', '?')}")

            due_today = tasks.get("due_today", [])
            if due_today:
                lines.append(f"  Due today: {len(due_today)}")
                for t in due_today:
                    lines.append(f"    - {t.get('title', '?')}")
        else:
            lines.append(f"Tasks: Error — {tasks['error']}")

        # Memory
        mem = brief.get("memory", {})
        if not mem.get("error"):
            lines.append(f"\nMemory: {mem.get('people_count', 0)} people, "
                         f"{mem.get('terms_count', 0)} terms, "
                         f"{mem.get('projects_count', 0)} projects")

        # Connectors
        connectors = brief.get("connectors", {})
        lines.append(f"\nConnectors: {connectors.get('overall', 'none')}")

        return "\n".join(lines)

    def _format_weekly_review(self, review: Dict) -> str:
        """Format weekly review as readable text."""
        lines = [f"Weekly Review — w/e {review['week_ending']}", "=" * 40, ""]

        tasks = review.get("tasks", {})
        if not tasks.get("error"):
            lines.append(f"Completed this week: {tasks.get('completed_this_week', 0)}")
            for item in tasks.get("completed_items", []):
                lines.append(f"  - {item}")
            lines.append(f"Still active: {tasks.get('active_count', 0)}")
            lines.append(f"Waiting on: {tasks.get('waiting_count', 0)}")
            overdue = tasks.get("overdue_count", 0)
            if overdue:
                lines.append(f"OVERDUE: {overdue}")

        mem = review.get("memory", {})
        if not mem.get("error"):
            lines.append(f"\nMemory: {mem.get('total_people', 0)} people, "
                         f"{mem.get('total_terms', 0)} terms, "
                         f"{mem.get('total_projects', 0)} projects")

        return "\n".join(lines)

    @staticmethod
    def _is_this_week(date_str: str) -> bool:
        """Check if a date string falls within the current week."""
        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d")
            today = datetime.now()
            week_start = today - timedelta(days=today.weekday())
            week_start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)
            return dt >= week_start
        except (ValueError, TypeError):
            return False


def get_productivity_skill(config: Optional[Dict] = None) -> ProductivitySkill:
    """Get an instance of the Productivity skill."""
    skill = ProductivitySkill(config)
    skill.initialize()
    return skill
