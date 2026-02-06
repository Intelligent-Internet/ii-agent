"""Tests for the Task Management skill and TaskStore."""

import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from ii_skills.task_management.task_store import Task, TaskStore, _task_to_dict


@pytest.fixture
def tmp_tasks_file(tmp_path):
    """Provide a path for a temporary TASKS.md."""
    return str(tmp_path / "TASKS.md")


@pytest.fixture
def store(tmp_tasks_file):
    """Provide an initialized TaskStore with sample content."""
    s = TaskStore(tasks_file=tmp_tasks_file)
    # Write sample content
    Path(tmp_tasks_file).write_text(
        "# Tasks\n\n"
        "## Active\n"
        "- [ ] **Send proposal** - for Todd, due 2026-02-10\n"
        "- [ ] **Review PR #42** - code review\n"
        "\n"
        "## Waiting On\n"
        "- [ ] **Feedback from Sarah** - since 2026-02-03\n"
        "\n"
        "## Someday\n"
        "- [ ] **Learn Rust** - programming language\n"
        "\n"
        "## Done\n"
        "- [x] ~~Setup CI~~ (2026-02-05)\n"
        "\n",
        encoding="utf-8",
    )
    return s


@pytest.fixture
def empty_store(tmp_tasks_file):
    """Provide an empty TaskStore (no file yet)."""
    return TaskStore(tasks_file=tmp_tasks_file)


# ------------------------------------------------------------------
# Initialization
# ------------------------------------------------------------------


class TestInitialization:
    def test_initialize_creates_tasks_md(self, tmp_path):
        """Initialize should create TASKS.md from template."""
        from ii_skills import get_skill

        workspace = str(tmp_path)
        skill = get_skill("task_management", config={"workspace_root": workspace})
        skill.initialize()
        result = skill.execute("initialize_tasks", workspace_root=workspace)
        assert result["success"] is True
        assert result["created"] is True
        assert (tmp_path / "TASKS.md").exists()

    def test_initialize_idempotent(self, tmp_path):
        """Initialize twice should not overwrite."""
        from ii_skills import get_skill

        workspace = str(tmp_path)
        skill = get_skill("task_management", config={"workspace_root": workspace})
        skill.initialize()
        skill.execute("initialize_tasks", workspace_root=workspace)

        # Write custom content
        (tmp_path / "TASKS.md").write_text("# Tasks\n\n## Active\n- [ ] **My task**\n", encoding="utf-8")

        result = skill.execute("initialize_tasks", workspace_root=workspace)
        assert result["created"] is False  # Did not overwrite

        # Content preserved
        content = (tmp_path / "TASKS.md").read_text(encoding="utf-8")
        assert "My task" in content


# ------------------------------------------------------------------
# Parsing
# ------------------------------------------------------------------


class TestParsing:
    def test_parse_markdown_sections(self, store):
        """All four sections should parse correctly."""
        sections = store.load()
        assert len(sections["active"]) == 2
        assert len(sections["waiting_on"]) == 1
        assert len(sections["someday"]) == 1
        assert len(sections["done"]) == 1

    def test_parse_active_task_details(self, store):
        """Active tasks should have parsed title, for_whom, due_date."""
        sections = store.load()
        proposal = sections["active"][0]
        assert proposal.title == "Send proposal"
        assert proposal.for_whom == "Todd"
        assert proposal.due_date == "2026-02-10"
        assert proposal.completed is False

    def test_parse_done_task(self, store):
        """Done tasks should have strikethrough title and completed date."""
        sections = store.load()
        done = sections["done"][0]
        assert done.title == "Setup CI"
        assert done.completed is True
        assert done.completed_date == "2026-02-05"

    def test_parse_waiting_on(self, store):
        """Waiting On tasks should parse since date in context."""
        sections = store.load()
        waiting = sections["waiting_on"][0]
        assert waiting.title == "Feedback from Sarah"
        assert "since 2026-02-03" in waiting.context


# ------------------------------------------------------------------
# Write Operations
# ------------------------------------------------------------------


class TestWriteOperations:
    def test_add_task_to_active(self, store):
        """Adding a task should appear in active section."""
        task = store.add_task("New task", context="test context")
        assert task.title == "New task"
        assert task.section == "active"

        # Verify persisted
        sections = store.load()
        titles = [t.title for t in sections["active"]]
        assert "New task" in titles

    def test_add_task_with_due_date(self, store):
        """Task with due date should be stored correctly."""
        task = store.add_task("Deadline task", due_date="2026-03-01")
        assert task.due_date == "2026-03-01"

    def test_complete_task_moves_to_done(self, store):
        """Completing a task should move it to Done."""
        store.load()
        completed = store.complete_task("Send proposal")
        assert completed is not None
        assert completed.completed is True
        assert completed.section == "done"

        sections = store.load()
        active_titles = [t.title for t in sections["active"]]
        assert "Send proposal" not in active_titles
        done_titles = [t.title for t in sections["done"]]
        assert "Send proposal" in done_titles

    def test_complete_task_adds_date_and_strikethrough(self, store):
        """Completed tasks should get a date stamp."""
        store.load()
        completed = store.complete_task("Review PR #42")
        assert completed.completed_date == datetime.now().strftime("%Y-%m-%d")

        # Check rendered markdown
        content = Path(store.tasks_file).read_text(encoding="utf-8")
        assert "~~Review PR #42~~" in content
        assert completed.completed_date in content

    def test_move_task_between_sections(self, store):
        """Moving a task should update its section."""
        store.load()
        moved = store.move_task("Send proposal", "waiting_on")
        assert moved is not None
        assert moved.section == "waiting_on"

        sections = store.load()
        assert any(t.title == "Send proposal" for t in sections["waiting_on"])
        assert not any(t.title == "Send proposal" for t in sections["active"])

    def test_delete_task(self, store):
        """Deleting a task should remove it completely."""
        store.load()
        assert store.delete_task("Learn Rust") is True
        sections = store.load()
        assert len(sections["someday"]) == 0

    def test_update_task(self, store):
        """Updating task fields should persist."""
        store.load()
        updated = store.update_task("Send proposal", context="updated context")
        assert updated is not None
        assert updated.context == "updated context"


# ------------------------------------------------------------------
# Maintenance
# ------------------------------------------------------------------


class TestMaintenance:
    def test_clean_done_removes_old_items(self, tmp_tasks_file):
        """Clean should remove done items older than threshold."""
        old_date = (datetime.now() - timedelta(days=10)).strftime("%Y-%m-%d")
        recent_date = datetime.now().strftime("%Y-%m-%d")

        Path(tmp_tasks_file).write_text(
            "# Tasks\n\n"
            "## Active\n\n"
            "## Waiting On\n\n"
            "## Someday\n\n"
            "## Done\n"
            f"- [x] ~~Old task~~ ({old_date})\n"
            f"- [x] ~~Recent task~~ ({recent_date})\n"
            "\n",
            encoding="utf-8",
        )

        store = TaskStore(tasks_file=tmp_tasks_file)
        removed = store.clean_done(older_than_days=7)
        assert removed == 1

        sections = store.load()
        done_titles = [t.title for t in sections["done"]]
        assert "Old task" not in done_titles
        assert "Recent task" in done_titles


# ------------------------------------------------------------------
# Overdue Detection
# ------------------------------------------------------------------


class TestOverdue:
    def test_get_overdue_detects_past_due_dates(self, tmp_tasks_file):
        """Tasks with past due dates should be flagged overdue."""
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")

        Path(tmp_tasks_file).write_text(
            "# Tasks\n\n"
            "## Active\n"
            f"- [ ] **Past due task** - due {yesterday}\n"
            f"- [ ] **Future task** - due {tomorrow}\n"
            "\n"
            "## Waiting On\n\n"
            "## Someday\n\n"
            "## Done\n\n",
            encoding="utf-8",
        )

        store = TaskStore(tasks_file=tmp_tasks_file)
        overdue = store.get_overdue()
        assert len(overdue) == 1
        assert overdue[0].title == "Past due task"


# ------------------------------------------------------------------
# Summary
# ------------------------------------------------------------------


class TestSummary:
    def test_get_summary_counts(self, store):
        """Summary should return correct counts."""
        summary = store.get_summary()
        assert summary["active_count"] == 2
        assert summary["waiting_count"] == 1
        assert summary["someday_count"] == 1
        assert summary["done_count"] == 1


# ------------------------------------------------------------------
# Text Extraction
# ------------------------------------------------------------------


class TestExtraction:
    def test_extract_tasks_from_meeting_notes(self, store):
        """Should extract action items from free text."""
        text = (
            "Meeting notes:\n"
            "I'll send the PSR to Todd by Friday.\n"
            "Need to review the budget proposal.\n"
            "Action item: schedule follow-up with Sarah.\n"
        )
        extracted = store.extract_tasks_from_text(text)
        assert len(extracted) >= 2  # At least the I'll and Need to
        titles = [e["title"] for e in extracted]
        assert any("PSR" in t or "send" in t.lower() for t in titles)


# ------------------------------------------------------------------
# Roundtrip
# ------------------------------------------------------------------


class TestRoundtrip:
    def test_roundtrip_parse_render_preserves_content(self, store):
        """Parse -> render -> parse should preserve all tasks."""
        sections = store.load()
        original_counts = {k: len(v) for k, v in sections.items()}

        # Re-render
        store.save()

        # Re-parse
        sections2 = store.load()
        for key in original_counts:
            assert len(sections2.get(key, [])) == original_counts[key], (
                f"Section '{key}' count changed: {original_counts[key]} -> {len(sections2.get(key, []))}"
            )

    def test_roundtrip_preserves_task_titles(self, store):
        """Task titles should survive a parse-render-parse cycle."""
        sections = store.load()
        original_titles = {
            k: [t.title for t in v]
            for k, v in sections.items()
        }

        store.save()
        sections2 = store.load()

        for key, titles in original_titles.items():
            new_titles = [t.title for t in sections2.get(key, [])]
            assert new_titles == titles, f"Titles changed in '{key}': {titles} -> {new_titles}"


# ------------------------------------------------------------------
# Skill Integration
# ------------------------------------------------------------------


class TestTaskSkill:
    """Test the TaskManagementSkill class."""

    def test_skill_registers(self):
        """Task management skill should be discoverable."""
        from ii_skills import list_skills
        skills = list_skills()
        skill_names = [s["name"] for s in skills]
        assert "task_management" in skill_names

    def test_skill_capabilities(self):
        """Skill should report all 12 capabilities."""
        from ii_skills import get_skill
        skill = get_skill("task_management")
        caps = skill.get_capabilities()
        assert len(caps) == 12
        assert "add_task" in caps
        assert "complete_task" in caps
        assert "get_tasks" in caps
        assert "extract_tasks_from_text" in caps

    def test_skill_execute_add_and_get(self, tmp_path):
        """Skill should support add_task + get_tasks roundtrip."""
        from ii_skills import get_skill
        workspace = str(tmp_path)
        skill = get_skill("task_management", config={"workspace_root": workspace})
        skill.initialize()
        skill.execute("initialize_tasks", workspace_root=workspace)

        skill.execute("add_task", title="Test task", context="via skill")
        result = skill.execute("get_tasks")
        active_titles = [t["title"] for t in result.get("active", [])]
        assert "Test task" in active_titles
