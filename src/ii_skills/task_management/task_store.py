"""
TASKS.md parser and writer.

Reads, writes, and manipulates a markdown-based task file with four sections:
Active, Waiting On, Someday, Done.

Format:
    # Tasks

    ## Active
    - [ ] **Task title** - context, for whom, due date
      - Sub-bullet for details

    ## Waiting On
    - [ ] **Task** - since [date]

    ## Someday
    - [ ] **Future task**

    ## Done
    - [x] ~~Completed task~~ (2026-02-06)
"""

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

SECTION_NAMES = {
    "active": "Active",
    "waiting_on": "Waiting On",
    "someday": "Someday",
    "done": "Done",
}

# Regex patterns
TASK_RE = re.compile(
    r"^- \[([ xX])\] (.+)$"
)
SUB_ITEM_RE = re.compile(r"^  - (.+)$")
SECTION_RE = re.compile(r"^## (.+)$")
BOLD_TITLE_RE = re.compile(r"\*\*(.+?)\*\*")
DUE_DATE_RE = re.compile(r"due\s+(\d{4}-\d{2}-\d{2}|\d{2}/\d{2})")
FOR_WHOM_RE = re.compile(r"for\s+(\w+)")
SINCE_DATE_RE = re.compile(r"since\s+(\d{4}-\d{2}-\d{2}|\d{2}/\d{2})")
COMPLETED_DATE_RE = re.compile(r"\((\d{4}-\d{2}-\d{2})\)\s*$")
STRIKETHROUGH_RE = re.compile(r"~~(.+?)~~")


@dataclass
class Task:
    """A single task entry."""

    title: str
    context: str = ""
    for_whom: Optional[str] = None
    due_date: Optional[str] = None
    sub_items: List[str] = field(default_factory=list)
    completed: bool = False
    completed_date: Optional[str] = None
    section: str = "active"
    raw_line: str = ""

    @property
    def is_overdue(self) -> bool:
        """Check if task is past due date."""
        if not self.due_date or self.completed:
            return False
        try:
            due = self._parse_date(self.due_date)
            return due is not None and due.date() < datetime.now().date()
        except (ValueError, TypeError):
            return False

    @property
    def days_old(self) -> int:
        """Rough age estimate based on due_date or since_date context."""
        return 0  # Would need creation date tracking for precision

    @staticmethod
    def _parse_date(date_str: str) -> Optional[datetime]:
        """Parse various date formats."""
        for fmt in ("%Y-%m-%d", "%m/%d", "%m/%d/%Y"):
            try:
                d = datetime.strptime(date_str, fmt)
                if d.year == 1900:  # %m/%d defaults to 1900
                    d = d.replace(year=datetime.now().year)
                return d
            except ValueError:
                continue
        return None


class TaskStore:
    """TASKS.md read/write/parse engine."""

    def __init__(self, tasks_file: str = "TASKS.md"):
        self.tasks_file = Path(tasks_file)
        self._sections: Dict[str, List[Task]] = {
            "active": [],
            "waiting_on": [],
            "someday": [],
            "done": [],
        }

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def load(self) -> Dict[str, List[Task]]:
        """Parse TASKS.md into sections."""
        if not self.tasks_file.exists():
            return self._sections

        content = self.tasks_file.read_text(encoding="utf-8")
        self._sections = self._parse_markdown(content)
        return self._sections

    def get_active(self) -> List[Task]:
        """Return active tasks."""
        self.load()
        return self._sections.get("active", [])

    def get_waiting(self) -> List[Task]:
        """Return waiting-on tasks."""
        self.load()
        return self._sections.get("waiting_on", [])

    def get_someday(self) -> List[Task]:
        """Return someday tasks."""
        self.load()
        return self._sections.get("someday", [])

    def get_done(self) -> List[Task]:
        """Return done tasks."""
        self.load()
        return self._sections.get("done", [])

    def get_overdue(self) -> List[Task]:
        """Return active tasks that are past due."""
        return [t for t in self.get_active() if t.is_overdue]

    def get_summary(self) -> Dict:
        """Quick summary with counts and overdue list."""
        self.load()
        overdue = [t for t in self._sections.get("active", []) if t.is_overdue]
        today = datetime.now().strftime("%Y-%m-%d")
        due_today = [
            t for t in self._sections.get("active", [])
            if t.due_date and t.due_date == today
        ]

        return {
            "active_count": len(self._sections.get("active", [])),
            "waiting_count": len(self._sections.get("waiting_on", [])),
            "someday_count": len(self._sections.get("someday", [])),
            "done_count": len(self._sections.get("done", [])),
            "overdue": [_task_to_dict(t) for t in overdue],
            "due_today": [_task_to_dict(t) for t in due_today],
        }

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def add_task(
        self,
        title: str,
        section: str = "active",
        context: str = "",
        for_whom: Optional[str] = None,
        due_date: Optional[str] = None,
        sub_items: Optional[List[str]] = None,
    ) -> Task:
        """Add a new task to a section."""
        self.load()
        section_key = self._normalize_section(section)

        task = Task(
            title=title,
            context=context,
            for_whom=for_whom,
            due_date=due_date,
            sub_items=sub_items or [],
            completed=False,
            section=section_key,
        )

        self._sections.setdefault(section_key, []).append(task)
        self.save()
        return task

    def complete_task(self, title_or_index: str) -> Optional[Task]:
        """Mark a task as done. Move to Done section with date and strikethrough."""
        self.load()
        task = self._match_task(title_or_index)
        if not task:
            return None

        # Remove from current section
        self._sections.get(task.section, []).remove(task)

        # Mark complete
        task.completed = True
        task.completed_date = datetime.now().strftime("%Y-%m-%d")
        task.section = "done"

        self._sections.setdefault("done", []).insert(0, task)
        self.save()
        return task

    def move_task(self, title_or_index: str, to_section: str) -> Optional[Task]:
        """Move a task between sections."""
        self.load()
        task = self._match_task(title_or_index)
        if not task:
            return None

        target = self._normalize_section(to_section)
        self._sections.get(task.section, []).remove(task)
        task.section = target
        self._sections.setdefault(target, []).append(task)
        self.save()
        return task

    def update_task(self, title_or_index: str, **updates) -> Optional[Task]:
        """Update task fields."""
        self.load()
        task = self._match_task(title_or_index)
        if not task:
            return None

        for key, value in updates.items():
            if hasattr(task, key) and key not in ("section", "completed"):
                setattr(task, key, value)

        self.save()
        return task

    def delete_task(self, title_or_index: str) -> bool:
        """Remove a task entirely."""
        self.load()
        task = self._match_task(title_or_index)
        if not task:
            return False

        self._sections.get(task.section, []).remove(task)
        self.save()
        return True

    def reorder_task(self, title_or_index: str, new_position: int) -> bool:
        """Move a task to a new position within its section."""
        self.load()
        task = self._match_task(title_or_index)
        if not task:
            return False

        section_list = self._sections.get(task.section, [])
        section_list.remove(task)
        new_position = max(0, min(new_position, len(section_list)))
        section_list.insert(new_position, task)
        self.save()
        return True

    # ------------------------------------------------------------------
    # Maintenance
    # ------------------------------------------------------------------

    def clean_done(self, older_than_days: int = 7) -> int:
        """Remove done items older than N days. Returns count removed."""
        self.load()
        cutoff = datetime.now() - timedelta(days=older_than_days)
        done = self._sections.get("done", [])
        original_count = len(done)

        kept = []
        for task in done:
            if task.completed_date:
                try:
                    completed = datetime.strptime(task.completed_date, "%Y-%m-%d")
                    if completed >= cutoff:
                        kept.append(task)
                    # else: older than cutoff, discard
                    continue
                except ValueError:
                    kept.append(task)
                    continue
            # No date — keep it
            kept.append(task)

        removed = original_count - len(kept)
        self._sections["done"] = kept
        if removed > 0:
            self.save()
        return removed

    def save(self) -> None:
        """Write sections back to TASKS.md."""
        content = self._render_markdown(self._sections)
        self.tasks_file.parent.mkdir(parents=True, exist_ok=True)
        self.tasks_file.write_text(content, encoding="utf-8")

    # ------------------------------------------------------------------
    # Text Extraction
    # ------------------------------------------------------------------

    def extract_tasks_from_text(self, text: str) -> List[Dict]:
        """Parse free text for commitments and action items.

        Looks for patterns like:
        - "I'll [verb] [thing] by [date]"
        - "Need to [verb] [thing]"
        - "Action item: [thing]"
        - "[Person] will [verb] [thing]"
        """
        extracted: List[Dict] = []
        patterns = [
            # "I'll send the PSR to Todd by Friday"
            re.compile(r"I(?:'ll|'m going to| will| need to)\s+(.+?)(?:\.|$)", re.IGNORECASE),
            # "Need to review the doc"
            re.compile(r"[Nn]eed to\s+(.+?)(?:\.|$)"),
            # "Action item: review the proposal"
            re.compile(r"[Aa]ction\s*(?:item)?:\s*(.+?)(?:\.|$)"),
            # "TODO: fix the bug"
            re.compile(r"TODO:\s*(.+?)(?:\.|$)", re.IGNORECASE),
        ]

        for line in text.split("\n"):
            line = line.strip()
            if not line:
                continue
            for pattern in patterns:
                match = pattern.search(line)
                if match:
                    task_text = match.group(1).strip()
                    if len(task_text) > 5:  # Filter noise
                        due = None
                        due_match = DUE_DATE_RE.search(task_text)
                        if due_match:
                            due = due_match.group(1)

                        for_match = FOR_WHOM_RE.search(task_text)
                        for_whom = for_match.group(1) if for_match else None

                        extracted.append({
                            "title": task_text[:100],
                            "due": due,
                            "for_whom": for_whom,
                            "source_line": line,
                        })
                    break

        return extracted

    # ------------------------------------------------------------------
    # Parsing Internals
    # ------------------------------------------------------------------

    def _parse_markdown(self, content: str) -> Dict[str, List[Task]]:
        """Parse TASKS.md content into sections with tasks."""
        sections: Dict[str, List[Task]] = {
            "active": [],
            "waiting_on": [],
            "someday": [],
            "done": [],
        }

        current_section: Optional[str] = None
        current_task: Optional[Task] = None

        for line in content.splitlines():
            # Section header
            section_match = SECTION_RE.match(line)
            if section_match:
                section_name = section_match.group(1).strip()
                current_section = self._normalize_section(section_name)
                current_task = None
                continue

            if current_section is None:
                continue

            # Task line
            task_match = TASK_RE.match(line)
            if task_match:
                checkbox = task_match.group(1)
                rest = task_match.group(2)
                completed = checkbox.lower() == "x"

                task = self._parse_task_line(rest, completed, current_section, line)
                sections.setdefault(current_section, []).append(task)
                current_task = task
                continue

            # Sub-item line
            sub_match = SUB_ITEM_RE.match(line)
            if sub_match and current_task is not None:
                current_task.sub_items.append(sub_match.group(1))
                continue

        return sections

    def _parse_task_line(self, text: str, completed: bool, section: str, raw_line: str) -> Task:
        """Parse the text after the checkbox into a Task object."""
        title = text
        context = ""
        for_whom = None
        due_date = None
        completed_date = None

        # Extract bold title
        bold_match = BOLD_TITLE_RE.search(text)
        if bold_match:
            title = bold_match.group(1)
            # Everything after the bold title is context
            remainder = text[bold_match.end():].strip()
            if remainder.startswith("- ") or remainder.startswith("— "):
                remainder = remainder[2:].strip()
            context = remainder

        # Handle strikethrough in done items
        strike_match = STRIKETHROUGH_RE.search(text)
        if strike_match and completed:
            title = strike_match.group(1)
            remainder = text[strike_match.end():].strip()
            context = remainder

        # Extract completed date
        date_match = COMPLETED_DATE_RE.search(text)
        if date_match:
            completed_date = date_match.group(1)
            context = context.replace(f"({completed_date})", "").strip()

        # Extract due date from context
        due_match = DUE_DATE_RE.search(context)
        if due_match:
            due_date = due_match.group(1)

        # Extract for_whom from context
        for_match = FOR_WHOM_RE.search(context)
        if for_match:
            for_whom = for_match.group(1)

        # Extract since date (for waiting_on)
        since_match = SINCE_DATE_RE.search(context)
        # Store since info in context — it's informational

        return Task(
            title=title,
            context=context,
            for_whom=for_whom,
            due_date=due_date,
            completed=completed,
            completed_date=completed_date,
            section=section,
            raw_line=raw_line,
        )

    def _render_markdown(self, sections: Dict[str, List[Task]]) -> str:
        """Render sections back to TASKS.md markdown format."""
        lines = ["# Tasks", ""]

        for section_key in ("active", "waiting_on", "someday", "done"):
            section_name = SECTION_NAMES.get(section_key, section_key.replace("_", " ").title())
            lines.append(f"## {section_name}")

            tasks = sections.get(section_key, [])
            if not tasks:
                lines.append("")
                continue

            for task in tasks:
                lines.append(self._render_task(task))
                for sub in task.sub_items:
                    lines.append(f"  - {sub}")

            lines.append("")

        return "\n".join(lines) + "\n"

    def _render_task(self, task: Task) -> str:
        """Render a single task as a markdown line."""
        checkbox = "[x]" if task.completed else "[ ]"

        if task.completed:
            title_part = f"~~{task.title}~~"
        else:
            title_part = f"**{task.title}**"

        parts = [title_part]

        # Add context details
        context_parts = []
        if task.context:
            context_parts.append(task.context)
        elif task.for_whom or task.due_date:
            if task.for_whom:
                context_parts.append(f"for {task.for_whom}")
            if task.due_date:
                context_parts.append(f"due {task.due_date}")

        if context_parts:
            parts.append(" - ".join(context_parts))

        if task.completed_date:
            parts.append(f"({task.completed_date})")

        task_text = " ".join(parts) if len(parts) == 1 else f"{parts[0]} - {' '.join(parts[1:])}"
        return f"- {checkbox} {task_text}"

    def _match_task(self, query: str, section: Optional[str] = None) -> Optional[Task]:
        """Find a task by title substring or index (e.g., '#1')."""
        query_lower = query.strip().lower()

        # Index-based lookup: "#1", "1", etc.
        index_match = re.match(r"#?(\d+)", query_lower)

        # Search across all non-done sections by default, or specific section
        search_sections = [section] if section else ["active", "waiting_on", "someday"]

        if index_match:
            idx = int(index_match.group(1)) - 1  # 1-based
            all_tasks = []
            for s in search_sections:
                all_tasks.extend(self._sections.get(s, []))
            if 0 <= idx < len(all_tasks):
                return all_tasks[idx]

        # Title-based fuzzy match
        for s in search_sections:
            for task in self._sections.get(s, []):
                if query_lower in task.title.lower():
                    return task

        # Also search done
        for task in self._sections.get("done", []):
            if query_lower in task.title.lower():
                return task

        return None

    @staticmethod
    def _normalize_section(name: str) -> str:
        """Normalize section names to internal keys."""
        name_lower = name.strip().lower().replace(" ", "_")
        mapping = {
            "active": "active",
            "waiting_on": "waiting_on",
            "waiting on": "waiting_on",
            "waiting": "waiting_on",
            "someday": "someday",
            "someday/maybe": "someday",
            "done": "done",
            "completed": "done",
        }
        return mapping.get(name_lower, "active")


def _task_to_dict(task: Task) -> Dict:
    """Convert Task to a serializable dict."""
    return {
        "title": task.title,
        "context": task.context,
        "for_whom": task.for_whom,
        "due_date": task.due_date,
        "completed": task.completed,
        "completed_date": task.completed_date,
        "section": task.section,
        "sub_items": task.sub_items,
        "is_overdue": task.is_overdue,
    }
