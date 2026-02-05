"""
Checkpoint Manager — Generic save/restore for TaskGraph state.

Enables checkpoint/resume for long-running DAG workflows.
Serializes completed tasks/phases, results, and budget state to JSON.

Usage:
    from ii_skills.shared.checkpoint import CheckpointManager

    manager = CheckpointManager()
    manager.save(executor, custom_state={"deal_id": "acme"})

    # Later, in a new process:
    checkpoint = manager.load(run_id)
    manager.restore(executor, checkpoint)
    results = await executor.run_all()  # Skips completed phases
"""

import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

logger = logging.getLogger(__name__)


@dataclass
class Checkpoint:
    """Serializable snapshot of TaskGraphExecutor state."""
    run_id: str
    graph_id: str
    checkpoint_id: str = field(default_factory=lambda: str(uuid4()))
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    completed_phases: List[str] = field(default_factory=list)
    completed_tasks: List[str] = field(default_factory=list)
    task_results: Dict[str, Dict] = field(default_factory=dict)
    phase_states: Dict[str, str] = field(default_factory=dict)
    budget_state: Dict[str, Any] = field(default_factory=dict)
    custom_state: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Checkpoint":
        """Deserialize from dictionary."""
        return cls(
            run_id=data.get("run_id", ""),
            graph_id=data.get("graph_id", ""),
            checkpoint_id=data.get("checkpoint_id", str(uuid4())),
            created_at=data.get("created_at", ""),
            completed_phases=data.get("completed_phases", []),
            completed_tasks=data.get("completed_tasks", []),
            task_results=data.get("task_results", {}),
            phase_states=data.get("phase_states", {}),
            budget_state=data.get("budget_state", {}),
            custom_state=data.get("custom_state", {}),
            metadata=data.get("metadata", {}),
        )

    def to_json(self, indent: int = 2) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict(), indent=indent, default=str)

    @classmethod
    def from_json(cls, json_str: str) -> "Checkpoint":
        """Deserialize from JSON string."""
        return cls.from_dict(json.loads(json_str))


class CheckpointManager:
    """Manages save/load/restore of TaskGraph checkpoints.

    Checkpoints are stored as JSON files under:
        storage_dir/<run_id>/<checkpoint_id>.json
    """

    def __init__(self, storage_dir: Optional[str] = None):
        """Initialize CheckpointManager.

        Args:
            storage_dir: Directory for checkpoint files.
                         Defaults to "output/checkpoints".
        """
        self._storage_dir = Path(storage_dir) if storage_dir else Path("output/checkpoints")

    @property
    def storage_dir(self) -> Path:
        return self._storage_dir

    def save(
        self,
        executor,
        run_id: Optional[str] = None,
        custom_state: Optional[Dict[str, Any]] = None,
    ) -> Checkpoint:
        """Save current executor state as a checkpoint.

        Args:
            executor: A TaskGraphExecutor instance.
            run_id: Optional run ID (auto-generated if not provided).
            custom_state: Optional user-provided state dict.

        Returns:
            The created Checkpoint.
        """
        from ii_skills.shared.task_graph import TaskStatus, PhaseStatus

        graph = executor.graph
        run_id = run_id or str(uuid4())

        # Collect completed phases
        completed_phases = [
            pid for pid, phase in graph.phases.items()
            if phase.status == PhaseStatus.COMPLETED
        ]

        # Collect phase states
        phase_states = {
            pid: phase.status.value
            for pid, phase in graph.phases.items()
        }

        # Collect completed tasks and their results
        completed_tasks = list(executor._completed_ids)
        task_results = {}
        for task_id, result in executor._results.items():
            task_results[task_id] = {
                "task_id": result.task_id,
                "status": result.status.value,
                "result": result.result,
                "error": result.error,
                "duration_ms": result.duration_ms,
                "retries": result.retries,
                "metadata": result.metadata,
            }

        checkpoint = Checkpoint(
            run_id=run_id,
            graph_id=graph.name,
            completed_phases=completed_phases,
            completed_tasks=completed_tasks,
            task_results=task_results,
            phase_states=phase_states,
            custom_state=custom_state or {},
        )

        # Persist to disk
        run_dir = self._storage_dir / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        filepath = run_dir / f"{checkpoint.checkpoint_id}.json"

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(checkpoint.to_json())

        logger.info(
            f"Checkpoint saved: {filepath} "
            f"({len(completed_phases)} phases, {len(completed_tasks)} tasks)"
        )

        return checkpoint

    def load(self, run_id: str) -> Optional[Checkpoint]:
        """Load the most recent checkpoint for a run.

        Args:
            run_id: The run ID to load.

        Returns:
            Most recent Checkpoint, or None if not found.
        """
        run_dir = self._storage_dir / run_id
        if not run_dir.exists():
            return None

        # Find most recent checkpoint by file modification time
        checkpoint_files = sorted(
            run_dir.glob("*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )

        if not checkpoint_files:
            return None

        try:
            with open(checkpoint_files[0], "r", encoding="utf-8") as f:
                data = json.load(f)
            checkpoint = Checkpoint.from_dict(data)
            logger.info(
                f"Checkpoint loaded: {checkpoint_files[0]} "
                f"({len(checkpoint.completed_phases)} phases, "
                f"{len(checkpoint.completed_tasks)} tasks)"
            )
            return checkpoint
        except Exception as e:
            logger.error(f"Failed to load checkpoint: {e}")
            return None

    def restore(self, executor, checkpoint: Checkpoint) -> None:
        """Restore executor state from a checkpoint.

        Marks completed tasks/phases and injects saved results
        so that run_all() can skip already-completed work.

        Args:
            executor: A TaskGraphExecutor instance.
            checkpoint: The checkpoint to restore from.
        """
        from ii_skills.shared.task_graph import TaskStatus, PhaseStatus, TaskResult

        graph = executor.graph

        # Restore phase states
        for phase_id, status_str in checkpoint.phase_states.items():
            if phase_id in graph.phases:
                try:
                    graph.phases[phase_id].status = PhaseStatus(status_str)
                except ValueError:
                    pass

        # Restore task states and results
        for task_id in checkpoint.completed_tasks:
            if task_id in graph.tasks:
                graph.tasks[task_id].status = TaskStatus.COMPLETED
                executor._completed_ids.add(task_id)

        # Inject saved task results
        for task_id, result_dict in checkpoint.task_results.items():
            try:
                status = TaskStatus(result_dict.get("status", "completed"))
            except ValueError:
                status = TaskStatus.COMPLETED

            result = TaskResult(
                task_id=task_id,
                status=status,
                result=result_dict.get("result"),
                error=result_dict.get("error"),
                duration_ms=result_dict.get("duration_ms"),
                retries=result_dict.get("retries", 0),
                metadata=result_dict.get("metadata", {}),
            )
            executor._results[task_id] = result

        logger.info(
            f"Restored checkpoint: {len(checkpoint.completed_phases)} phases, "
            f"{len(checkpoint.completed_tasks)} tasks"
        )

    def list_checkpoints(self, run_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """List available checkpoints.

        Args:
            run_id: Optional filter by run ID.

        Returns:
            List of checkpoint summary dicts.
        """
        results = []

        if run_id:
            run_dirs = [self._storage_dir / run_id]
        else:
            if not self._storage_dir.exists():
                return []
            run_dirs = [d for d in self._storage_dir.iterdir() if d.is_dir()]

        for run_dir in run_dirs:
            if not run_dir.exists():
                continue
            for filepath in sorted(run_dir.glob("*.json"), reverse=True):
                try:
                    with open(filepath, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    results.append({
                        "run_id": data.get("run_id"),
                        "checkpoint_id": data.get("checkpoint_id"),
                        "graph_id": data.get("graph_id"),
                        "created_at": data.get("created_at"),
                        "completed_phases": len(data.get("completed_phases", [])),
                        "completed_tasks": len(data.get("completed_tasks", [])),
                        "path": str(filepath),
                    })
                except Exception as e:
                    logger.warning(f"Failed to read checkpoint {filepath}: {e}")

        return results

    def delete(self, run_id: str, checkpoint_id: Optional[str] = None) -> int:
        """Delete checkpoint(s).

        Args:
            run_id: The run ID.
            checkpoint_id: Optional specific checkpoint to delete.
                           If None, deletes all checkpoints for the run.

        Returns:
            Number of checkpoints deleted.
        """
        run_dir = self._storage_dir / run_id
        if not run_dir.exists():
            return 0

        deleted = 0
        if checkpoint_id:
            filepath = run_dir / f"{checkpoint_id}.json"
            if filepath.exists():
                filepath.unlink()
                deleted = 1
        else:
            for filepath in run_dir.glob("*.json"):
                filepath.unlink()
                deleted += 1
            # Remove empty directory
            try:
                run_dir.rmdir()
            except OSError:
                pass

        return deleted
