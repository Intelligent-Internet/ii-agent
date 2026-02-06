"""
Task Management Skill

Markdown-based task tracking with TASKS.md. Supports four sections:
Active, Waiting On, Someday, Done.

Features:
- Add, complete, move, update, delete tasks
- Overdue detection from due dates
- Extract action items from meeting notes
- Clean old done items
- TASKS.md lives at workspace root (gitignored — personal data)

Fork safety: Entirely new directory, no modifications to existing files.
"""

import asyncio
import logging
import shutil
from pathlib import Path
from typing import Dict, List, Optional

from ii_skills import BaseSkill, register_skill

logger = logging.getLogger(__name__)

__version__ = "1.0.0"
__author__ = "II-Agent System"


@register_skill
class TaskManagementSkill(BaseSkill):
    """Markdown-based task tracking with TASKS.md — Active/Waiting/Someday/Done."""

    name = "task_management"
    version = __version__
    description = "Markdown-based task tracking with TASKS.md — Active/Waiting/Someday/Done"

    SKILL_DIR = Path(__file__).parent
    TEMPLATE_PATH = SKILL_DIR / "templates" / "tasks_template.md"

    def __init__(self, config: Optional[Dict] = None):
        super().__init__(config)
        self._store = None

    def initialize(self) -> bool:
        """Initialize the skill and task store."""
        from ii_skills.task_management.task_store import TaskStore

        workspace_root = self.config.get("workspace_root", str(Path.cwd()))
        tasks_path = Path(workspace_root) / "TASKS.md"
        self._store = TaskStore(tasks_file=str(tasks_path))
        self._initialized = True
        return True

    def validate_config(self) -> List[str]:
        """No required config for task management."""
        return []

    def get_capabilities(self) -> List[str]:
        """Return list of actions this skill provides."""
        return [
            # Read
            "get_tasks",
            "get_summary",
            "get_active",
            "get_waiting",
            # Write
            "add_task",
            "complete_task",
            "move_task",
            "update_task",
            "delete_task",
            # Maintenance
            "clean_done",
            "initialize_tasks",
            # Extraction
            "extract_tasks_from_text",
        ]

    def execute(self, action: str, **kwargs) -> Dict:
        """Execute a task management action."""
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
            "get_tasks": self._get_tasks,
            "get_summary": self._get_summary,
            "get_active": self._get_active,
            "get_waiting": self._get_waiting,
            "add_task": self._add_task,
            "complete_task": self._complete_task,
            "move_task": self._move_task,
            "update_task": self._update_task,
            "delete_task": self._delete_task,
            "clean_done": self._clean_done,
            "initialize_tasks": self._initialize_tasks,
            "extract_tasks_from_text": self._extract_tasks_from_text,
        }

        handler = actions.get(action)
        if not handler:
            raise NotImplementedError(f"Action '{action}' not implemented")
        return await handler(**kwargs)

    # ------------------------------------------------------------------
    # Ensure store is initialized
    # ------------------------------------------------------------------

    def _ensure_store(self) -> None:
        """Lazily initialize store if needed."""
        if self._store is None:
            self.initialize()

    # ------------------------------------------------------------------
    # Read Actions
    # ------------------------------------------------------------------

    async def _get_tasks(self, **kwargs) -> Dict:
        """Return all tasks grouped by section."""
        self._ensure_store()
        from ii_skills.task_management.task_store import _task_to_dict
        sections = self._store.load()
        return {
            section: [_task_to_dict(t) for t in tasks]
            for section, tasks in sections.items()
        }

    async def _get_summary(self, **kwargs) -> Dict:
        """Quick summary with counts and overdue items."""
        self._ensure_store()
        return self._store.get_summary()

    async def _get_active(self, **kwargs) -> Dict:
        """Active tasks only."""
        self._ensure_store()
        from ii_skills.task_management.task_store import _task_to_dict
        tasks = self._store.get_active()
        return {"active": [_task_to_dict(t) for t in tasks]}

    async def _get_waiting(self, **kwargs) -> Dict:
        """Waiting On tasks only."""
        self._ensure_store()
        from ii_skills.task_management.task_store import _task_to_dict
        tasks = self._store.get_waiting()
        return {"waiting_on": [_task_to_dict(t) for t in tasks]}

    # ------------------------------------------------------------------
    # Write Actions
    # ------------------------------------------------------------------

    async def _add_task(
        self,
        title: str,
        section: str = "active",
        context: str = "",
        for_whom: Optional[str] = None,
        due_date: Optional[str] = None,
        **kwargs,
    ) -> Dict:
        """Add a new task."""
        self._ensure_store()
        from ii_skills.task_management.task_store import _task_to_dict
        task = self._store.add_task(
            title=title,
            section=section,
            context=context,
            for_whom=for_whom,
            due_date=due_date,
        )
        return {"success": True, "task": _task_to_dict(task)}

    async def _complete_task(self, task: str, **kwargs) -> Dict:
        """Mark a task as done."""
        self._ensure_store()
        from ii_skills.task_management.task_store import _task_to_dict
        completed = self._store.complete_task(task)
        if completed:
            return {"success": True, "completed": _task_to_dict(completed)}
        return {"success": False, "error": f"Task not found: {task}"}

    async def _move_task(self, task: str, to_section: str, **kwargs) -> Dict:
        """Move a task between sections."""
        self._ensure_store()
        moved = self._store.move_task(task, to_section)
        if moved:
            return {"success": True, "task": moved.title, "to_section": to_section}
        return {"success": False, "error": f"Task not found: {task}"}

    async def _update_task(self, task: str, **kwargs) -> Dict:
        """Update task fields."""
        self._ensure_store()
        updates = {k: v for k, v in kwargs.items() if k != "task"}
        updated = self._store.update_task(task, **updates)
        if updated:
            from ii_skills.task_management.task_store import _task_to_dict
            return {"success": True, "task": _task_to_dict(updated)}
        return {"success": False, "error": f"Task not found: {task}"}

    async def _delete_task(self, task: str, **kwargs) -> Dict:
        """Delete a task."""
        self._ensure_store()
        deleted = self._store.delete_task(task)
        return {"success": deleted, "deleted": task if deleted else None}

    # ------------------------------------------------------------------
    # Maintenance Actions
    # ------------------------------------------------------------------

    async def _clean_done(self, older_than_days: int = 7, **kwargs) -> Dict:
        """Remove old done items."""
        self._ensure_store()
        removed = self._store.clean_done(older_than_days=older_than_days)
        return {"success": True, "removed_count": removed}

    async def _initialize_tasks(self, workspace_root: str = "", **kwargs) -> Dict:
        """Create TASKS.md from template if missing."""
        if workspace_root:
            from ii_skills.task_management.task_store import TaskStore
            tasks_path = Path(workspace_root) / "TASKS.md"
            self._store = TaskStore(tasks_file=str(tasks_path))
            self._initialized = True

        self._ensure_store()
        tasks_path = self._store.tasks_file

        if tasks_path.exists():
            return {"success": True, "created": False, "message": "TASKS.md already exists"}

        # Copy template
        if self.TEMPLATE_PATH.exists():
            shutil.copy2(self.TEMPLATE_PATH, tasks_path)
        else:
            # Fallback — write minimal template
            tasks_path.write_text(
                "# Tasks\n\n## Active\n\n## Waiting On\n\n## Someday\n\n## Done\n",
                encoding="utf-8",
            )

        return {"success": True, "created": True, "path": str(tasks_path)}

    # ------------------------------------------------------------------
    # Extraction Actions
    # ------------------------------------------------------------------

    async def _extract_tasks_from_text(self, text: str, **kwargs) -> Dict:
        """Extract action items from meeting notes or free text."""
        self._ensure_store()
        extracted = self._store.extract_tasks_from_text(text)
        return {"extracted": extracted, "count": len(extracted)}


def get_task_skill(config: Optional[Dict] = None) -> TaskManagementSkill:
    """Get an instance of the Task Management skill."""
    skill = TaskManagementSkill(config)
    skill.initialize()
    return skill
