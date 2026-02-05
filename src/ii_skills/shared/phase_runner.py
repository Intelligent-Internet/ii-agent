"""
Generic Phase Runner

Reusable multi-phase orchestration extracted from DealOrchestrator patterns.
Provides dependency-driven execution with status tracking and progress callbacks.

Usage:
    from ii_skills.shared.phase_runner import PhaseRunner, Phase, Task

    # Define phases
    phases = [
        Phase("data_collection", tasks=[
            Task("fetch_market_data", fetch_market_data),
            Task("fetch_company_data", fetch_company_data),
        ]),
        Phase("analysis", tasks=[
            Task("run_valuation", run_valuation, depends_on=["fetch_company_data"]),
        ]),
    ]

    # Run
    runner = PhaseRunner(phases)
    results = await runner.execute()
"""

import asyncio
import logging
from datetime import datetime
from enum import Enum
from typing import Dict, Any, Optional, List, Callable, Awaitable, Set
from dataclasses import dataclass, field
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class TaskStatus(Enum):
    """Task execution status."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    BLOCKED = "blocked"


class PhaseStatus(Enum):
    """Phase execution status."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class Task:
    """
    A single executable task within a phase.

    Attributes:
        id: Unique task identifier
        name: Human-readable task name
        executor: Async function to execute the task
        depends_on: List of task IDs this task depends on
        timeout_seconds: Optional execution timeout
        retry_count: Number of retries on failure
        metadata: Additional task metadata
    """
    id: str
    executor: Callable[..., Awaitable[Any]]
    name: Optional[str] = None
    depends_on: List[str] = field(default_factory=list)
    timeout_seconds: Optional[float] = None
    retry_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    # Runtime state
    status: TaskStatus = TaskStatus.PENDING
    result: Any = None
    error: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    attempts: int = 0

    def __post_init__(self):
        if self.name is None:
            self.name = self.id

    @property
    def duration_ms(self) -> Optional[float]:
        """Calculate execution duration in milliseconds."""
        if self.start_time and self.end_time:
            return (self.end_time - self.start_time).total_seconds() * 1000
        return None

    def reset(self):
        """Reset task state for re-execution."""
        self.status = TaskStatus.PENDING
        self.result = None
        self.error = None
        self.start_time = None
        self.end_time = None
        self.attempts = 0


@dataclass
class Phase:
    """
    A phase containing multiple tasks.

    Tasks within a phase can run in parallel if they have no dependencies.
    """
    id: str
    tasks: List[Task] = field(default_factory=list)
    name: Optional[str] = None
    depends_on_phases: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    # Runtime state
    status: PhaseStatus = PhaseStatus.PENDING
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None

    def __post_init__(self):
        if self.name is None:
            self.name = self.id

    @property
    def duration_ms(self) -> Optional[float]:
        """Calculate phase duration in milliseconds."""
        if self.start_time and self.end_time:
            return (self.end_time - self.start_time).total_seconds() * 1000
        return None

    def get_task(self, task_id: str) -> Optional[Task]:
        """Get a task by ID."""
        for task in self.tasks:
            if task.id == task_id:
                return task
        return None

    def reset(self):
        """Reset phase state for re-execution."""
        self.status = PhaseStatus.PENDING
        self.start_time = None
        self.end_time = None
        for task in self.tasks:
            task.reset()


class PhaseRunnerCallback(ABC):
    """Abstract callback interface for phase runner events."""

    @abstractmethod
    async def on_phase_start(self, phase: Phase):
        """Called when a phase starts."""
        pass

    @abstractmethod
    async def on_phase_complete(self, phase: Phase):
        """Called when a phase completes."""
        pass

    @abstractmethod
    async def on_task_start(self, task: Task, phase: Phase):
        """Called when a task starts."""
        pass

    @abstractmethod
    async def on_task_complete(self, task: Task, phase: Phase):
        """Called when a task completes."""
        pass

    @abstractmethod
    async def on_task_error(self, task: Task, phase: Phase, error: str):
        """Called when a task fails."""
        pass


class ConsolePhaseRunnerCallback(PhaseRunnerCallback):
    """Simple console-based progress callback."""

    async def on_phase_start(self, phase: Phase):
        print(f"\n{'='*60}")
        print(f"Phase: {phase.name}")
        print(f"Tasks: {len(phase.tasks)}")
        print(f"{'='*60}")

    async def on_phase_complete(self, phase: Phase):
        completed = sum(1 for t in phase.tasks if t.status == TaskStatus.COMPLETED)
        failed = sum(1 for t in phase.tasks if t.status == TaskStatus.FAILED)
        print(f"\nPhase {phase.name} complete: {completed} succeeded, {failed} failed")

    async def on_task_start(self, task: Task, phase: Phase):
        print(f"  [STARTED] {task.name}")

    async def on_task_complete(self, task: Task, phase: Phase):
        duration = f" ({task.duration_ms:.0f}ms)" if task.duration_ms else ""
        print(f"  [DONE] {task.name}{duration}")

    async def on_task_error(self, task: Task, phase: Phase, error: str):
        print(f"  [ERROR] {task.name}: {error}")


class NullPhaseRunnerCallback(PhaseRunnerCallback):
    """No-op callback for silent execution."""

    async def on_phase_start(self, phase: Phase):
        pass

    async def on_phase_complete(self, phase: Phase):
        pass

    async def on_task_start(self, task: Task, phase: Phase):
        pass

    async def on_task_complete(self, task: Task, phase: Phase):
        pass

    async def on_task_error(self, task: Task, phase: Phase, error: str):
        pass


@dataclass
class PhaseRunnerConfig:
    """Configuration for the phase runner."""
    max_parallel_tasks: int = 5
    fail_fast: bool = False  # Stop on first error
    skip_failed_dependencies: bool = True  # Skip tasks whose dependencies failed
    default_timeout_seconds: Optional[float] = None
    default_retry_count: int = 0


class PhaseRunner:
    """
    Generic multi-phase orchestration engine.

    Executes phases in order, with tasks within each phase
    running in parallel where dependencies allow.
    """

    def __init__(
        self,
        phases: List[Phase],
        config: Optional[PhaseRunnerConfig] = None,
        callback: Optional[PhaseRunnerCallback] = None,
        context: Optional[Dict[str, Any]] = None,
    ):
        """
        Initialize the phase runner.

        Args:
            phases: List of phases to execute
            config: Runner configuration
            callback: Progress callback
            context: Shared context passed to all task executors
        """
        self.phases = phases
        self.config = config or PhaseRunnerConfig()
        self.callback = callback or NullPhaseRunnerCallback()
        self.context = context or {}

        # Build task lookup
        self._all_tasks: Dict[str, Task] = {}
        for phase in phases:
            for task in phase.tasks:
                self._all_tasks[task.id] = task

    async def execute(self) -> Dict[str, Any]:
        """
        Execute all phases in order.

        Returns:
            Dictionary with execution results and statistics
        """
        start_time = datetime.now()
        results = {
            "phases": {},
            "tasks": {},
            "summary": {},
        }

        try:
            for phase in self.phases:
                # Check phase dependencies
                if not self._check_phase_dependencies(phase):
                    phase.status = PhaseStatus.SKIPPED
                    logger.info(f"Skipping phase {phase.id}: dependencies not met")
                    continue

                # Execute phase
                phase_result = await self._execute_phase(phase)
                results["phases"][phase.id] = phase_result

                # Check for fail-fast
                if self.config.fail_fast and phase.status == PhaseStatus.FAILED:
                    logger.warning(f"Fail-fast triggered at phase {phase.id}")
                    break

        except Exception as e:
            logger.error(f"Phase runner error: {e}")
            raise

        # Collect task results
        for task_id, task in self._all_tasks.items():
            results["tasks"][task_id] = {
                "status": task.status.value,
                "result": task.result,
                "error": task.error,
                "duration_ms": task.duration_ms,
                "attempts": task.attempts,
            }

        # Summary statistics
        end_time = datetime.now()
        total_tasks = len(self._all_tasks)
        completed_tasks = sum(1 for t in self._all_tasks.values() if t.status == TaskStatus.COMPLETED)
        failed_tasks = sum(1 for t in self._all_tasks.values() if t.status == TaskStatus.FAILED)

        results["summary"] = {
            "total_phases": len(self.phases),
            "completed_phases": sum(1 for p in self.phases if p.status == PhaseStatus.COMPLETED),
            "total_tasks": total_tasks,
            "completed_tasks": completed_tasks,
            "failed_tasks": failed_tasks,
            "success_rate": completed_tasks / total_tasks if total_tasks > 0 else 0,
            "duration_ms": (end_time - start_time).total_seconds() * 1000,
        }

        return results

    async def _execute_phase(self, phase: Phase) -> Dict[str, Any]:
        """Execute a single phase."""
        phase.status = PhaseStatus.RUNNING
        phase.start_time = datetime.now()

        await self.callback.on_phase_start(phase)

        try:
            # Build dependency graph for tasks in this phase
            pending_tasks = set(t.id for t in phase.tasks)
            completed_tasks: Set[str] = set()

            while pending_tasks:
                # Find tasks ready to run (dependencies satisfied)
                ready_tasks = []
                for task_id in pending_tasks:
                    task = self._all_tasks[task_id]
                    if self._can_run_task(task, completed_tasks):
                        ready_tasks.append(task)

                if not ready_tasks:
                    # No tasks ready - check for blocked tasks
                    blocked = [t for t in phase.tasks if t.id in pending_tasks]
                    for task in blocked:
                        task.status = TaskStatus.BLOCKED
                        task.error = "Dependencies cannot be satisfied"
                    break

                # Run ready tasks in parallel (up to max)
                batch = ready_tasks[:self.config.max_parallel_tasks]
                await asyncio.gather(
                    *[self._execute_task(task, phase) for task in batch],
                    return_exceptions=True,
                )

                # Update tracking
                for task in batch:
                    pending_tasks.discard(task.id)
                    if task.status == TaskStatus.COMPLETED:
                        completed_tasks.add(task.id)

                # Check fail-fast
                if self.config.fail_fast:
                    failed = [t for t in batch if t.status == TaskStatus.FAILED]
                    if failed:
                        phase.status = PhaseStatus.FAILED
                        break

            # Determine phase status
            if phase.status != PhaseStatus.FAILED:
                failed_count = sum(1 for t in phase.tasks if t.status == TaskStatus.FAILED)
                if failed_count > 0:
                    phase.status = PhaseStatus.FAILED
                else:
                    phase.status = PhaseStatus.COMPLETED

        except Exception as e:
            phase.status = PhaseStatus.FAILED
            logger.error(f"Phase {phase.id} error: {e}")

        phase.end_time = datetime.now()
        await self.callback.on_phase_complete(phase)

        return {
            "status": phase.status.value,
            "duration_ms": phase.duration_ms,
            "tasks_completed": sum(1 for t in phase.tasks if t.status == TaskStatus.COMPLETED),
            "tasks_failed": sum(1 for t in phase.tasks if t.status == TaskStatus.FAILED),
        }

    async def _execute_task(self, task: Task, phase: Phase):
        """Execute a single task with retry logic."""
        task.status = TaskStatus.RUNNING
        task.start_time = datetime.now()
        task.attempts = 0

        await self.callback.on_task_start(task, phase)

        max_attempts = task.retry_count + 1 or self.config.default_retry_count + 1
        timeout = task.timeout_seconds or self.config.default_timeout_seconds

        while task.attempts < max_attempts:
            task.attempts += 1
            try:
                # Execute with optional timeout
                if timeout:
                    task.result = await asyncio.wait_for(
                        task.executor(self.context, task),
                        timeout=timeout,
                    )
                else:
                    task.result = await task.executor(self.context, task)

                task.status = TaskStatus.COMPLETED
                task.end_time = datetime.now()
                await self.callback.on_task_complete(task, phase)
                return

            except asyncio.TimeoutError:
                task.error = f"Timeout after {timeout}s"
                logger.warning(f"Task {task.id} timeout (attempt {task.attempts}/{max_attempts})")

            except Exception as e:
                task.error = str(e)
                logger.warning(f"Task {task.id} error (attempt {task.attempts}/{max_attempts}): {e}")

        # All attempts exhausted
        task.status = TaskStatus.FAILED
        task.end_time = datetime.now()
        await self.callback.on_task_error(task, phase, task.error or "Unknown error")

    def _can_run_task(self, task: Task, completed_tasks: Set[str]) -> bool:
        """Check if a task's dependencies are satisfied."""
        for dep_id in task.depends_on:
            dep_task = self._all_tasks.get(dep_id)
            if not dep_task:
                continue  # Missing dependency

            if dep_task.status == TaskStatus.FAILED:
                if self.config.skip_failed_dependencies:
                    task.status = TaskStatus.SKIPPED
                    task.error = f"Dependency {dep_id} failed"
                    return False
                else:
                    return False  # Wait for potential retry

            if dep_id not in completed_tasks:
                return False  # Dependency not yet complete

        return True

    def _check_phase_dependencies(self, phase: Phase) -> bool:
        """Check if a phase's dependencies are satisfied."""
        for dep_phase_id in phase.depends_on_phases:
            dep_phase = next((p for p in self.phases if p.id == dep_phase_id), None)
            if dep_phase and dep_phase.status != PhaseStatus.COMPLETED:
                return False
        return True

    def get_task_result(self, task_id: str) -> Any:
        """Get the result of a specific task."""
        task = self._all_tasks.get(task_id)
        return task.result if task else None

    def reset(self):
        """Reset all phases and tasks for re-execution."""
        for phase in self.phases:
            phase.reset()


# Convenience function for simple phase creation
def create_phase(
    phase_id: str,
    task_definitions: List[Dict[str, Any]],
    phase_name: Optional[str] = None,
) -> Phase:
    """
    Create a phase from task definitions.

    Args:
        phase_id: Phase identifier
        task_definitions: List of dicts with 'id', 'executor', optional 'depends_on'
        phase_name: Optional human-readable name

    Returns:
        Configured Phase object
    """
    tasks = []
    for defn in task_definitions:
        task = Task(
            id=defn["id"],
            executor=defn["executor"],
            name=defn.get("name"),
            depends_on=defn.get("depends_on", []),
            timeout_seconds=defn.get("timeout"),
            retry_count=defn.get("retry_count", 0),
            metadata=defn.get("metadata", {}),
        )
        tasks.append(task)

    return Phase(id=phase_id, tasks=tasks, name=phase_name)
