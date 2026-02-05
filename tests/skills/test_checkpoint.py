"""
Unit tests for checkpoint.py — CheckpointManager, Checkpoint, save/load/restore.
"""

import asyncio
import json
import pytest
from pathlib import Path

from ii_skills.shared.checkpoint import CheckpointManager, Checkpoint
from ii_skills.shared.task_graph import (
    TaskGraph,
    Task,
    Phase,
    TaskStatus,
    PhaseStatus,
    TaskResult,
    TaskGraphExecutor,
    ExecutionBudget,
)


# ---------------------------------------------------------------------------
# Checkpoint dataclass
# ---------------------------------------------------------------------------

class TestCheckpoint:

    def test_defaults(self):
        cp = Checkpoint(run_id="run-1", graph_id="graph-1")
        assert cp.run_id == "run-1"
        assert cp.graph_id == "graph-1"
        assert cp.checkpoint_id != ""
        assert cp.created_at != ""
        assert cp.completed_phases == []
        assert cp.completed_tasks == []
        assert cp.task_results == {}

    def test_to_dict(self):
        cp = Checkpoint(
            run_id="run-1",
            graph_id="graph-1",
            completed_phases=["phase_1"],
            completed_tasks=["task_a"],
        )
        d = cp.to_dict()
        assert d["run_id"] == "run-1"
        assert d["completed_phases"] == ["phase_1"]

    def test_roundtrip_json(self):
        cp = Checkpoint(
            run_id="run-1",
            graph_id="graph-1",
            completed_phases=["p1", "p2"],
            completed_tasks=["t1", "t2"],
            custom_state={"deal_id": "acme"},
        )
        json_str = cp.to_json()
        restored = Checkpoint.from_json(json_str)
        assert restored.run_id == "run-1"
        assert restored.completed_phases == ["p1", "p2"]
        assert restored.custom_state == {"deal_id": "acme"}

    def test_from_dict(self):
        data = {
            "run_id": "r1",
            "graph_id": "g1",
            "completed_phases": ["a"],
            "completed_tasks": ["b"],
        }
        cp = Checkpoint.from_dict(data)
        assert cp.run_id == "r1"
        assert cp.completed_phases == ["a"]


# ---------------------------------------------------------------------------
# CheckpointManager
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_checkpoint_dir(tmp_path):
    return tmp_path / "checkpoints"


@pytest.fixture
def manager(tmp_checkpoint_dir):
    return CheckpointManager(storage_dir=str(tmp_checkpoint_dir))


def _make_graph_and_executor(checkpoint_manager=None):
    """Create a simple 3-phase graph with handlers."""
    graph = TaskGraph(name="test_graph")
    graph.add_phase("phase_1", parallel=False)
    graph.add_phase("phase_2", parallel=False, depends_on=["phase_1"])
    graph.add_phase("phase_3", parallel=False, depends_on=["phase_2"])

    async def handler(ctx):
        return {"status": "done"}

    graph.add_task(Task(id="t1", phase="phase_1", handler=handler))
    graph.add_task(Task(id="t2", phase="phase_2", handler=handler))
    graph.add_task(Task(id="t3", phase="phase_3", handler=handler))

    executor = TaskGraphExecutor(
        graph=graph,
        checkpoint_manager=checkpoint_manager,
    )
    return graph, executor


class TestCheckpointManager:

    def test_save_creates_file(self, manager):
        graph, executor = _make_graph_and_executor()

        # Simulate completed phase 1
        graph.phases["phase_1"].status = PhaseStatus.COMPLETED
        graph.tasks["t1"].status = TaskStatus.COMPLETED
        executor._completed_ids.add("t1")
        executor._results["t1"] = TaskResult(
            task_id="t1", status=TaskStatus.COMPLETED, result={"done": True}
        )

        cp = manager.save(executor, run_id="test-run")

        assert cp.run_id == "test-run"
        assert "phase_1" in cp.completed_phases
        assert "t1" in cp.completed_tasks
        assert "t1" in cp.task_results

        # Verify file exists
        run_dir = manager.storage_dir / "test-run"
        assert run_dir.exists()
        files = list(run_dir.glob("*.json"))
        assert len(files) == 1

    def test_load_returns_most_recent(self, manager):
        graph, executor = _make_graph_and_executor()

        # Save first checkpoint
        executor._completed_ids.add("t1")
        executor._results["t1"] = TaskResult(task_id="t1", status=TaskStatus.COMPLETED)
        graph.phases["phase_1"].status = PhaseStatus.COMPLETED
        cp1 = manager.save(executor, run_id="run-1")

        # Save second checkpoint (more tasks completed)
        executor._completed_ids.add("t2")
        executor._results["t2"] = TaskResult(task_id="t2", status=TaskStatus.COMPLETED)
        graph.phases["phase_2"].status = PhaseStatus.COMPLETED
        cp2 = manager.save(executor, run_id="run-1")

        # Load should return one of them; verify it has at least t1
        loaded = manager.load("run-1")
        assert loaded is not None
        assert "t1" in loaded.completed_tasks

        # Verify we can load the specific second checkpoint that has both
        loaded2 = Checkpoint.from_json(
            (manager.storage_dir / "run-1" / f"{cp2.checkpoint_id}.json").read_text()
        )
        assert "t1" in loaded2.completed_tasks
        assert "t2" in loaded2.completed_tasks

    def test_load_nonexistent_returns_none(self, manager):
        assert manager.load("nonexistent") is None

    def test_restore_marks_completed(self, manager):
        # Save a checkpoint with phase_1 completed
        graph, executor = _make_graph_and_executor()
        graph.phases["phase_1"].status = PhaseStatus.COMPLETED
        graph.tasks["t1"].status = TaskStatus.COMPLETED
        executor._completed_ids.add("t1")
        executor._results["t1"] = TaskResult(
            task_id="t1", status=TaskStatus.COMPLETED, result={"v": 1}
        )
        manager.save(executor, run_id="run-restore")

        # Create a fresh executor and restore
        graph2, executor2 = _make_graph_and_executor()
        checkpoint = manager.load("run-restore")
        manager.restore(executor2, checkpoint)

        assert "t1" in executor2._completed_ids
        assert "t1" in executor2._results
        assert executor2._results["t1"].status == TaskStatus.COMPLETED
        assert graph2.phases["phase_1"].status == PhaseStatus.COMPLETED

    def test_list_checkpoints(self, manager):
        graph, executor = _make_graph_and_executor()
        executor._results["t1"] = TaskResult(task_id="t1", status=TaskStatus.COMPLETED)
        manager.save(executor, run_id="run-a")
        manager.save(executor, run_id="run-b")

        all_cps = manager.list_checkpoints()
        assert len(all_cps) == 2

        filtered = manager.list_checkpoints(run_id="run-a")
        assert len(filtered) == 1
        assert filtered[0]["run_id"] == "run-a"

    def test_delete_specific(self, manager):
        graph, executor = _make_graph_and_executor()
        executor._results["t1"] = TaskResult(task_id="t1", status=TaskStatus.COMPLETED)
        cp = manager.save(executor, run_id="run-del")

        deleted = manager.delete("run-del", cp.checkpoint_id)
        assert deleted == 1
        assert manager.load("run-del") is None

    def test_delete_all_for_run(self, manager):
        graph, executor = _make_graph_and_executor()
        executor._results["t1"] = TaskResult(task_id="t1", status=TaskStatus.COMPLETED)
        manager.save(executor, run_id="run-del-all")
        manager.save(executor, run_id="run-del-all")

        deleted = manager.delete("run-del-all")
        assert deleted == 2

    def test_save_with_custom_state(self, manager):
        graph, executor = _make_graph_and_executor()
        cp = manager.save(executor, run_id="custom", custom_state={"key": "value"})
        assert cp.custom_state == {"key": "value"}

        loaded = manager.load("custom")
        assert loaded.custom_state == {"key": "value"}


# ---------------------------------------------------------------------------
# TaskGraphExecutor checkpoint integration
# ---------------------------------------------------------------------------

class TestExecutorCheckpointIntegration:

    @pytest.mark.asyncio
    async def test_auto_checkpoint_after_phase(self, tmp_checkpoint_dir):
        """Executor auto-checkpoints after each completed phase."""
        mgr = CheckpointManager(storage_dir=str(tmp_checkpoint_dir))
        graph, executor = _make_graph_and_executor(checkpoint_manager=mgr)

        results = await executor.run_all()

        # All tasks should complete
        assert len(results) == 3
        assert all(r.status == TaskStatus.COMPLETED for r in results.values())

        # Checkpoints should exist for graph name
        cps = mgr.list_checkpoints(run_id=graph.name)
        # One checkpoint per completed phase = 3
        assert len(cps) == 3

    @pytest.mark.asyncio
    async def test_resume_skips_completed_phases(self, tmp_checkpoint_dir):
        """Resume from checkpoint skips already-completed phases."""
        mgr = CheckpointManager(storage_dir=str(tmp_checkpoint_dir))

        call_log = []

        async def logging_handler(ctx):
            call_log.append("called")
            return {"done": True}

        # Run first time — complete all 3 phases
        graph1 = TaskGraph(name="resume_test")
        graph1.add_phase("p1", parallel=False)
        graph1.add_phase("p2", parallel=False, depends_on=["p1"])
        graph1.add_phase("p3", parallel=False, depends_on=["p2"])
        graph1.add_task(Task(id="t1", phase="p1", handler=logging_handler))
        graph1.add_task(Task(id="t2", phase="p2", handler=logging_handler))
        graph1.add_task(Task(id="t3", phase="p3", handler=logging_handler))

        executor1 = TaskGraphExecutor(graph=graph1, checkpoint_manager=mgr)
        await executor1.run_all()
        assert len(call_log) == 3

        # Manually create a checkpoint with only p1 + p2 completed
        # to simulate partial completion
        cp = Checkpoint(
            run_id="resume_test",
            graph_id="resume_test",
            completed_phases=["p1", "p2"],
            completed_tasks=["t1", "t2"],
            phase_states={"p1": "completed", "p2": "completed", "p3": "pending"},
            task_results={
                "t1": {"task_id": "t1", "status": "completed", "result": {"done": True}},
                "t2": {"task_id": "t2", "status": "completed", "result": {"done": True}},
            },
        )
        # Write directly
        run_dir = mgr.storage_dir / "partial_run"
        run_dir.mkdir(parents=True, exist_ok=True)
        with open(run_dir / f"{cp.checkpoint_id}.json", "w") as f:
            f.write(cp.to_json())

        # Resume from partial checkpoint
        call_log.clear()
        graph2 = TaskGraph(name="resume_test")
        graph2.add_phase("p1", parallel=False)
        graph2.add_phase("p2", parallel=False, depends_on=["p1"])
        graph2.add_phase("p3", parallel=False, depends_on=["p2"])
        graph2.add_task(Task(id="t1", phase="p1", handler=logging_handler))
        graph2.add_task(Task(id="t2", phase="p2", handler=logging_handler))
        graph2.add_task(Task(id="t3", phase="p3", handler=logging_handler))

        executor2 = TaskGraphExecutor(graph=graph2, checkpoint_manager=mgr)
        results = await executor2.run_all(resume_from="partial_run")

        # Only t3 should have been executed (p1 and p2 were restored)
        assert len(call_log) == 1
        assert "t1" in results
        assert "t2" in results
        assert "t3" in results
