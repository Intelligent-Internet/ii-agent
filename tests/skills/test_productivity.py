"""Tests for the Productivity orchestrator skill and workflows."""

import json
from datetime import datetime
from pathlib import Path

import pytest


@pytest.fixture
def workspace(tmp_path):
    """Provide a temporary workspace with initialized tasks and memory."""
    workspace_root = str(tmp_path)

    from ii_skills import get_skill

    # Initialize task_management
    task_skill = get_skill("task_management", config={"workspace_root": workspace_root})
    task_skill.initialize()
    task_skill.execute("initialize_tasks", workspace_root=workspace_root)

    # Initialize memory
    memory_skill = get_skill("memory", config={"workspace_root": workspace_root})
    memory_skill.initialize()
    memory_skill.execute("initialize_memory", workspace_root=workspace_root)

    return workspace_root


@pytest.fixture
def prod_skill(workspace):
    """Provide an initialized ProductivitySkill."""
    from ii_skills import get_skill

    skill = get_skill("productivity", config={"workspace_root": workspace})
    skill.initialize()
    return skill


# ------------------------------------------------------------------
# /start Workflow
# ------------------------------------------------------------------


class TestStartWorkflow:
    def test_start_initializes_tasks_and_memory(self, tmp_path):
        """Start should create both TASKS.md and memory/ in one action."""
        from ii_skills import get_skill

        workspace_root = str(tmp_path)
        skill = get_skill("productivity", config={"workspace_root": workspace_root})
        skill.initialize()

        result = skill.execute("start", workspace_root=workspace_root)

        assert result["success"] is True
        assert "summary" in result
        assert (tmp_path / "TASKS.md").exists()
        assert (tmp_path / "memory").exists()

    def test_start_without_connectors_still_works(self, tmp_path):
        """Start should work even when no connectors are configured."""
        from ii_skills import get_skill

        workspace_root = str(tmp_path)
        skill = get_skill("productivity", config={"workspace_root": workspace_root})
        skill.initialize()

        result = skill.execute("start", workspace_root=workspace_root)

        assert result["success"] is True
        connectors = result.get("connectors", {})
        assert connectors.get("configured_count", 0) == 0

    def test_start_idempotent(self, workspace):
        """Running start twice should not fail."""
        from ii_skills import get_skill

        skill = get_skill("productivity", config={"workspace_root": workspace})
        skill.initialize()

        result1 = skill.execute("start", workspace_root=workspace)
        result2 = skill.execute("start", workspace_root=workspace)

        assert result1["success"] is True
        assert result2["success"] is True

    def test_start_summary_is_readable(self, tmp_path):
        """Start summary should be a non-empty string."""
        from ii_skills import get_skill

        workspace_root = str(tmp_path)
        skill = get_skill("productivity", config={"workspace_root": workspace_root})
        skill.initialize()

        result = skill.execute("start", workspace_root=workspace_root)
        summary = result.get("summary", "")
        assert len(summary) > 50
        assert "Ready!" in summary


# ------------------------------------------------------------------
# /update Workflow
# ------------------------------------------------------------------


class TestUpdateWorkflow:
    def test_update_returns_task_summary(self, prod_skill):
        """Update should return task counts."""
        result = prod_skill.execute("update")

        assert result["success"] is True
        assert "task_summary" in result
        summary = result["task_summary"]
        assert "active_count" in summary

    def test_update_flags_stale_tasks(self, workspace):
        """Update should detect overdue tasks."""
        from ii_skills import get_skill

        # Add an overdue task
        task_skill = get_skill("task_management", config={"workspace_root": workspace})
        task_skill.initialize()
        task_skill.execute("add_task", title="Overdue item", due_date="2020-01-01")

        prod_skill = get_skill("productivity", config={"workspace_root": workspace})
        prod_skill.initialize()

        result = prod_skill.execute("update")
        assert result["success"] is True
        assert len(result.get("overdue_tasks", [])) >= 1

    def test_update_includes_memory_status(self, prod_skill):
        """Update should report memory coverage."""
        result = prod_skill.execute("update")

        mem = result.get("memory_status", {})
        assert "people_count" in mem
        assert "terms_count" in mem

    def test_update_report_is_readable(self, prod_skill):
        """Update report should be a formatted string."""
        result = prod_skill.execute("update")

        report = result.get("report", "")
        assert "Daily Triage Report" in report
        assert "Tasks:" in report

    def test_update_without_connectors(self, prod_skill):
        """Update should work without project tracker configured."""
        result = prod_skill.execute("update")

        tracker = result.get("tracker_sync", {})
        assert tracker.get("available") is False


# ------------------------------------------------------------------
# /update --comprehensive Workflow
# ------------------------------------------------------------------


class TestComprehensiveWorkflow:
    def test_comprehensive_includes_scan(self, prod_skill):
        """Comprehensive should include scan section."""
        result = prod_skill.execute("update_comprehensive")

        assert result["success"] is True
        assert result.get("comprehensive") is True
        assert "scan" in result

    def test_comprehensive_scans_degrade_gracefully(self, prod_skill):
        """With no connectors, scans should report skipped, not crash."""
        result = prod_skill.execute("update_comprehensive")

        scan = result.get("scan", {})
        for category in ("email", "calendar", "chat"):
            assert category in scan
            assert scan[category].get("scanned") is False

    def test_comprehensive_report_extends_base(self, prod_skill):
        """Comprehensive report should include both base triage and scan results."""
        result = prod_skill.execute("update_comprehensive")

        report = result.get("report", "")
        assert "Daily Triage Report" in report
        assert "Comprehensive Scan" in report


# ------------------------------------------------------------------
# Daily Brief
# ------------------------------------------------------------------


class TestDailyBrief:
    def test_daily_brief_format(self, prod_skill):
        """Daily brief should be formatted and include key sections."""
        result = prod_skill.execute("daily_brief")

        assert result["success"] is True
        assert "formatted" in result
        assert "Daily Briefing" in result["formatted"]

    def test_daily_brief_includes_tasks(self, prod_skill):
        """Brief should include task counts."""
        result = prod_skill.execute("daily_brief")

        assert "tasks" in result
        tasks = result["tasks"]
        assert "summary" in tasks or "error" in tasks

    def test_daily_brief_includes_memory(self, prod_skill):
        """Brief should include memory snapshot."""
        result = prod_skill.execute("daily_brief")

        mem = result.get("memory", {})
        assert "people_count" in mem or "error" in mem


# ------------------------------------------------------------------
# Weekly Review
# ------------------------------------------------------------------


class TestWeeklyReview:
    def test_weekly_review_format(self, prod_skill):
        """Weekly review should produce formatted output."""
        result = prod_skill.execute("weekly_review")

        assert result["success"] is True
        assert "formatted" in result
        assert "Weekly Review" in result["formatted"]

    def test_weekly_review_counts_completed(self, workspace):
        """Weekly review should count tasks completed this week."""
        from ii_skills import get_skill

        # Add and complete a task
        task_skill = get_skill("task_management", config={"workspace_root": workspace})
        task_skill.initialize()
        task_skill.execute("add_task", title="Done today")
        task_skill.execute("complete_task", task="Done today")

        prod_skill = get_skill("productivity", config={"workspace_root": workspace})
        prod_skill.initialize()

        result = prod_skill.execute("weekly_review")
        tasks = result.get("tasks", {})
        assert tasks.get("completed_this_week", 0) >= 1


# ------------------------------------------------------------------
# Skill Integration
# ------------------------------------------------------------------


class TestProductivitySkill:
    def test_skill_registers(self):
        """Productivity skill should be discoverable."""
        from ii_skills import list_skills

        skills = list_skills()
        skill_names = [s["name"] for s in skills]
        assert "productivity" in skill_names

    def test_skill_capabilities(self):
        """Skill should report all 5 capabilities."""
        from ii_skills import get_skill

        skill = get_skill("productivity")
        caps = skill.get_capabilities()
        assert len(caps) == 5
        assert "start" in caps
        assert "update" in caps
        assert "update_comprehensive" in caps
        assert "daily_brief" in caps
        assert "weekly_review" in caps

    def test_cross_skill_references_use_get_skill(self):
        """Productivity should resolve dependencies via get_skill(), not imports."""
        from ii_skills import get_skill

        skill = get_skill("productivity")
        # validate_config checks for dependent skills
        issues = skill.validate_config()
        assert len(issues) == 0  # Both task_management and memory are available
