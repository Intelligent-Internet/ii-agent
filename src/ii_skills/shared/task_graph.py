"""
Reusable Task Graph Utility

Extracted from DealOrchestrator to provide a general-purpose task graph
execution engine for any multi-phase, dependency-aware workflow.

Follows ralph's task graph patterns with:
- DAG-based dependency resolution
- Parallel execution within phases
- Phase gating with completion criteria
- Progress callbacks
- Budget enforcement

Usage:
    from ii_skills.shared.task_graph import TaskGraph, Task, Phase

    # Define tasks
    graph = TaskGraph()
    graph.add_phase("collect", parallel=True)
    graph.add_phase("process", parallel=False, depends_on=["collect"])
    graph.add_phase("output", parallel=True, depends_on=["process"])

    graph.add_task(Task(
        id="fetch_data",
        phase="collect",
        handler=fetch_data_func,
    ))

    # Execute
    async with graph.execute(budget=budget, callbacks=callbacks) as executor:
        results = await executor.run_all()
"""

import asyncio
import logging
from datetime import datetime, timezone
from enum import Enum
from typing import (
    Optional, List, Dict, Any, Callable, Awaitable,
    Union, Set, TypeVar, Generic
)
from dataclasses import dataclass, field
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)

T = TypeVar('T')


class TaskStatus(Enum):
    """Task execution status."""
    PENDING = "pending"
    BLOCKED = "blocked"
    READY = "ready"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"


class PhaseStatus(Enum):
    """Phase execution status."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class TaskResult:
    """Result of a task execution."""
    task_id: str
    status: TaskStatus
    result: Any = None
    error: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_ms: Optional[float] = None
    retries: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Task:
    """
    A single executable task within a graph.

    Tasks can have dependencies on other tasks and belong to phases.
    """
    id: str
    name: Optional[str] = None
    phase: Optional[str] = None
    description: str = ""
    handler: Optional[Callable[..., Awaitable[Any]]] = None
    handler_name: str = ""  # For deferred handler lookup
    dependencies: List[str] = field(default_factory=list)
    timeout_ms: Optional[float] = None
    retries: int = 0
    retry_delay_ms: float = 1000
    skip_on_failure: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)

    # Runtime state
    status: TaskStatus = TaskStatus.PENDING
    result: Any = None
    error: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_ms: Optional[float] = None
    retry_count: int = 0

    def __post_init__(self):
        if self.name is None:
            self.name = self.id


@dataclass
class Phase:
    """
    A phase groups related tasks that can be executed together.

    Phases execute sequentially, but tasks within a phase can run in parallel.
    """
    id: str
    name: Optional[str] = None
    parallel: bool = True
    max_parallel: int = 5
    depends_on: List[str] = field(default_factory=list)
    gate_condition: Optional[Callable[['TaskGraph'], bool]] = None
    skip_on_failure: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)

    # Runtime state
    status: PhaseStatus = PhaseStatus.PENDING
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    tasks_completed: int = 0
    tasks_failed: int = 0

    def __post_init__(self):
        if self.name is None:
            self.name = self.id


class TaskGraphCallbacks(ABC):
    """Abstract base class for task graph execution callbacks."""

    async def on_graph_start(self, graph: 'TaskGraph'):
        """Called when graph execution starts."""
        pass

    async def on_phase_start(self, phase: Phase, tasks: List[Task]):
        """Called when a phase starts."""
        pass

    async def on_phase_complete(self, phase: Phase, results: Dict[str, TaskResult]):
        """Called when a phase completes."""
        pass

    async def on_task_start(self, task: Task):
        """Called when a task starts."""
        pass

    async def on_task_complete(self, task: Task, result: TaskResult):
        """Called when a task completes (success or failure)."""
        pass

    async def on_graph_complete(self, graph: 'TaskGraph', results: Dict[str, TaskResult]):
        """Called when graph execution completes."""
        pass


class LoggingCallbacks(TaskGraphCallbacks):
    """Simple logging callbacks for debugging."""

    async def on_graph_start(self, graph: 'TaskGraph'):
        logger.info(f"Starting task graph: {len(graph.tasks)} tasks in {len(graph.phases)} phases")

    async def on_phase_start(self, phase: Phase, tasks: List[Task]):
        task_names = [t.name for t in tasks]
        logger.info(f"Phase '{phase.name}': Starting {len(tasks)} tasks - {task_names}")

    async def on_phase_complete(self, phase: Phase, results: Dict[str, TaskResult]):
        completed = sum(1 for r in results.values() if r.status == TaskStatus.COMPLETED)
        failed = sum(1 for r in results.values() if r.status == TaskStatus.FAILED)
        logger.info(f"Phase '{phase.name}': Completed ({completed} success, {failed} failed)")

    async def on_task_start(self, task: Task):
        logger.debug(f"Task '{task.name}': Starting")

    async def on_task_complete(self, task: Task, result: TaskResult):
        status = result.status.value
        duration = f" ({result.duration_ms:.0f}ms)" if result.duration_ms else ""
        logger.debug(f"Task '{task.name}': {status}{duration}")

    async def on_graph_complete(self, graph: 'TaskGraph', results: Dict[str, TaskResult]):
        completed = sum(1 for r in results.values() if r.status == TaskStatus.COMPLETED)
        failed = sum(1 for r in results.values() if r.status == TaskStatus.FAILED)
        logger.info(f"Task graph complete: {completed} succeeded, {failed} failed")


@dataclass
class ExecutionBudget:
    """
    Budget constraints for task graph execution.

    Follows ralph's pattern of optional limits defaulting to current behavior.
    """
    max_total_tasks: Optional[int] = None
    max_failed_tasks: Optional[int] = None
    max_duration_ms: Optional[float] = None
    max_parallel_tasks: int = 5
    max_retries_per_task: int = 3
    task_timeout_ms: float = 60000  # 1 minute default

    def validate_task_count(self, completed: int, failed: int) -> bool:
        """Check if task counts are within budget."""
        if self.max_total_tasks and (completed + failed) >= self.max_total_tasks:
            return False
        if self.max_failed_tasks and failed >= self.max_failed_tasks:
            return False
        return True

    def validate_duration(self, elapsed_ms: float) -> bool:
        """Check if duration is within budget."""
        if self.max_duration_ms and elapsed_ms >= self.max_duration_ms:
            return False
        return True


class TaskGraph:
    """
    A directed acyclic graph of tasks organized into phases.

    Provides:
    - Phase-based execution with dependency resolution
    - Parallel execution within phases
    - Budget enforcement
    - Progress callbacks
    - State persistence
    """

    def __init__(
        self,
        name: str = "TaskGraph",
        handler_registry: Optional[Dict[str, Callable]] = None,
    ):
        """
        Initialize task graph.

        Args:
            name: Name for this graph instance
            handler_registry: Optional dict mapping handler names to callables
        """
        self.name = name
        self.phases: Dict[str, Phase] = {}
        self.tasks: Dict[str, Task] = {}
        self._phase_order: List[str] = []
        self._handler_registry = handler_registry or {}

    def add_phase(
        self,
        phase_id: str,
        name: Optional[str] = None,
        parallel: bool = True,
        max_parallel: int = 5,
        depends_on: Optional[List[str]] = None,
        gate_condition: Optional[Callable[['TaskGraph'], bool]] = None,
    ) -> Phase:
        """Add a phase to the graph."""
        phase = Phase(
            id=phase_id,
            name=name or phase_id,
            parallel=parallel,
            max_parallel=max_parallel,
            depends_on=depends_on or [],
            gate_condition=gate_condition,
        )
        self.phases[phase_id] = phase
        if phase_id not in self._phase_order:
            self._phase_order.append(phase_id)
        return phase

    def add_task(self, task: Task) -> Task:
        """Add a task to the graph."""
        if task.phase and task.phase not in self.phases:
            self.add_phase(task.phase)
        self.tasks[task.id] = task
        return task

    def register_handler(self, name: str, handler: Callable):
        """Register a handler function by name."""
        self._handler_registry[name] = handler

    def get_handler(self, task: Task) -> Optional[Callable]:
        """Get the handler for a task."""
        if task.handler:
            return task.handler
        if task.handler_name and task.handler_name in self._handler_registry:
            return self._handler_registry[task.handler_name]
        return None

    def get_phase_tasks(self, phase_id: str) -> List[Task]:
        """Get all tasks belonging to a phase."""
        return [t for t in self.tasks.values() if t.phase == phase_id]

    def get_ready_tasks(self, completed_ids: Set[str]) -> List[Task]:
        """Get tasks that are ready to execute (all dependencies met)."""
        ready = []
        for task in self.tasks.values():
            if task.status != TaskStatus.PENDING:
                continue
            if all(dep in completed_ids for dep in task.dependencies):
                ready.append(task)
        return ready

    def validate(self) -> List[str]:
        """
        Validate the task graph for cycles and missing dependencies.

        Returns list of validation errors.
        """
        errors = []

        # Check for missing dependencies
        for task in self.tasks.values():
            for dep in task.dependencies:
                if dep not in self.tasks:
                    errors.append(f"Task '{task.id}' has unknown dependency '{dep}'")

        # Check for cycles using topological sort
        visited = set()
        rec_stack = set()

        def has_cycle(task_id: str) -> bool:
            visited.add(task_id)
            rec_stack.add(task_id)

            task = self.tasks.get(task_id)
            if task:
                for dep in task.dependencies:
                    if dep not in visited:
                        if has_cycle(dep):
                            return True
                    elif dep in rec_stack:
                        return True

            rec_stack.remove(task_id)
            return False

        for task_id in self.tasks:
            if task_id not in visited:
                if has_cycle(task_id):
                    errors.append(f"Cycle detected involving task '{task_id}'")
                    break

        # Check phase dependencies
        for phase in self.phases.values():
            for dep in phase.depends_on:
                if dep not in self.phases:
                    errors.append(f"Phase '{phase.id}' has unknown dependency '{dep}'")

        return errors

    def reset(self):
        """Reset all task and phase states."""
        for task in self.tasks.values():
            task.status = TaskStatus.PENDING
            task.result = None
            task.error = None
            task.started_at = None
            task.completed_at = None
            task.duration_ms = None
            task.retry_count = 0

        for phase in self.phases.values():
            phase.status = PhaseStatus.PENDING
            phase.started_at = None
            phase.completed_at = None
            phase.tasks_completed = 0
            phase.tasks_failed = 0

    def to_dict(self) -> Dict[str, Any]:
        """Serialize graph to dictionary."""
        return {
            "name": self.name,
            "phases": [
                {
                    "id": p.id,
                    "name": p.name,
                    "status": p.status.value,
                    "parallel": p.parallel,
                    "depends_on": p.depends_on,
                    "tasks_completed": p.tasks_completed,
                    "tasks_failed": p.tasks_failed,
                }
                for p in self.phases.values()
            ],
            "tasks": [
                {
                    "id": t.id,
                    "name": t.name,
                    "phase": t.phase,
                    "status": t.status.value,
                    "dependencies": t.dependencies,
                    "duration_ms": t.duration_ms,
                    "error": t.error,
                }
                for t in self.tasks.values()
            ],
        }


class TaskGraphExecutor:
    """
    Executes a task graph with budget constraints and callbacks.
    """

    def __init__(
        self,
        graph: TaskGraph,
        budget: Optional[ExecutionBudget] = None,
        callbacks: Optional[TaskGraphCallbacks] = None,
        context: Optional[Dict[str, Any]] = None,
    ):
        """
        Initialize executor.

        Args:
            graph: The task graph to execute
            budget: Optional execution budget constraints
            callbacks: Optional progress callbacks
            context: Optional context passed to task handlers
        """
        self.graph = graph
        self.budget = budget or ExecutionBudget()
        self.callbacks = callbacks or LoggingCallbacks()
        self.context = context or {}

        self._results: Dict[str, TaskResult] = {}
        self._completed_ids: Set[str] = set()
        self._started_at: Optional[datetime] = None
        self._cancelled = False

    async def run_all(self) -> Dict[str, TaskResult]:
        """
        Execute the entire task graph.

        Returns dict mapping task IDs to results.
        """
        # Validate graph
        errors = self.graph.validate()
        if errors:
            raise ValueError(f"Invalid task graph: {errors}")

        # Reset state
        self.graph.reset()
        self._results.clear()
        self._completed_ids.clear()
        self._started_at = datetime.now(timezone.utc)

        await self.callbacks.on_graph_start(self.graph)

        try:
            # Execute phases in order
            for phase_id in self.graph._phase_order:
                if self._cancelled:
                    break

                phase = self.graph.phases[phase_id]

                # Check phase dependencies
                if not self._can_start_phase(phase):
                    phase.status = PhaseStatus.SKIPPED
                    continue

                # Check gate condition
                if phase.gate_condition and not phase.gate_condition(self.graph):
                    phase.status = PhaseStatus.SKIPPED
                    continue

                await self._run_phase(phase)

                # Check if we should continue
                if phase.status == PhaseStatus.FAILED and not phase.skip_on_failure:
                    break

        finally:
            await self.callbacks.on_graph_complete(self.graph, self._results)

        return self._results

    async def run_phase(self, phase_id: str) -> Dict[str, TaskResult]:
        """Run a specific phase only."""
        if phase_id not in self.graph.phases:
            raise ValueError(f"Unknown phase: {phase_id}")

        phase = self.graph.phases[phase_id]
        await self._run_phase(phase)

        phase_tasks = self.graph.get_phase_tasks(phase_id)
        return {t.id: self._results[t.id] for t in phase_tasks if t.id in self._results}

    def cancel(self):
        """Cancel graph execution."""
        self._cancelled = True

    def _can_start_phase(self, phase: Phase) -> bool:
        """Check if phase dependencies are satisfied."""
        for dep_id in phase.depends_on:
            dep_phase = self.graph.phases.get(dep_id)
            if not dep_phase or dep_phase.status != PhaseStatus.COMPLETED:
                return False
        return True

    def _check_budget(self) -> bool:
        """Check if execution is within budget."""
        if self._started_at:
            elapsed = (datetime.now(timezone.utc) - self._started_at).total_seconds() * 1000
            if not self.budget.validate_duration(elapsed):
                logger.warning("Budget exceeded: max duration reached")
                return False

        completed = sum(1 for r in self._results.values() if r.status == TaskStatus.COMPLETED)
        failed = sum(1 for r in self._results.values() if r.status == TaskStatus.FAILED)

        if not self.budget.validate_task_count(completed, failed):
            logger.warning("Budget exceeded: task count limit reached")
            return False

        return True

    async def _run_phase(self, phase: Phase):
        """Execute a single phase."""
        tasks = self.graph.get_phase_tasks(phase.id)

        if not tasks:
            phase.status = PhaseStatus.COMPLETED
            return

        phase.status = PhaseStatus.RUNNING
        phase.started_at = datetime.now(timezone.utc)

        await self.callbacks.on_phase_start(phase, tasks)

        try:
            if phase.parallel:
                await self._run_tasks_parallel(tasks, phase.max_parallel)
            else:
                await self._run_tasks_sequential(tasks)

            # Determine phase status
            phase_results = {t.id: self._results[t.id] for t in tasks if t.id in self._results}
            failed = sum(1 for r in phase_results.values() if r.status == TaskStatus.FAILED)

            phase.tasks_completed = sum(1 for r in phase_results.values() if r.status == TaskStatus.COMPLETED)
            phase.tasks_failed = failed

            if failed > 0 and not phase.skip_on_failure:
                phase.status = PhaseStatus.FAILED
            else:
                phase.status = PhaseStatus.COMPLETED

            await self.callbacks.on_phase_complete(phase, phase_results)

        finally:
            phase.completed_at = datetime.now(timezone.utc)

    async def _run_tasks_parallel(self, tasks: List[Task], max_parallel: int):
        """Run tasks in parallel with concurrency limit."""
        semaphore = asyncio.Semaphore(min(max_parallel, self.budget.max_parallel_tasks))
        pending_tasks = list(tasks)
        running_futures: Dict[asyncio.Task, Task] = {}

        while pending_tasks or running_futures:
            if self._cancelled or not self._check_budget():
                # Cancel running tasks
                for future in running_futures:
                    future.cancel()
                break

            # Start ready tasks up to limit
            ready = [t for t in pending_tasks if self._is_task_ready(t)]

            for task in ready[:max_parallel - len(running_futures)]:
                pending_tasks.remove(task)

                async def run_with_semaphore(t: Task):
                    async with semaphore:
                        return await self._run_task(t)

                future = asyncio.create_task(run_with_semaphore(task))
                running_futures[future] = task

            if running_futures:
                # Wait for at least one task to complete
                done, _ = await asyncio.wait(
                    running_futures.keys(),
                    return_when=asyncio.FIRST_COMPLETED,
                )

                for future in done:
                    task = running_futures.pop(future)
                    try:
                        await future
                    except Exception as e:
                        logger.error(f"Task {task.id} failed: {e}")

            elif pending_tasks:
                # All pending tasks are blocked, wait a bit
                await asyncio.sleep(0.1)

    async def _run_tasks_sequential(self, tasks: List[Task]):
        """Run tasks sequentially."""
        for task in tasks:
            if self._cancelled or not self._check_budget():
                break

            if not self._is_task_ready(task):
                task.status = TaskStatus.BLOCKED
                continue

            await self._run_task(task)

    def _is_task_ready(self, task: Task) -> bool:
        """Check if task dependencies are satisfied."""
        for dep in task.dependencies:
            if dep not in self._completed_ids:
                return False
        return True

    async def _run_task(self, task: Task):
        """Execute a single task with retries."""
        task.status = TaskStatus.RUNNING
        task.started_at = datetime.now(timezone.utc)

        await self.callbacks.on_task_start(task)

        result = TaskResult(
            task_id=task.id,
            status=TaskStatus.RUNNING,
            started_at=task.started_at,
        )

        try:
            handler = self.graph.get_handler(task)
            if not handler:
                raise ValueError(f"No handler for task: {task.id}")

            # Execute with timeout and retries
            max_retries = min(task.retries, self.budget.max_retries_per_task)
            timeout = task.timeout_ms or self.budget.task_timeout_ms

            for attempt in range(max_retries + 1):
                try:
                    if asyncio.iscoroutinefunction(handler):
                        task_result = await asyncio.wait_for(
                            handler(self.context),
                            timeout=timeout / 1000,
                        )
                    else:
                        task_result = handler(self.context)

                    task.result = task_result
                    task.status = TaskStatus.COMPLETED
                    result.status = TaskStatus.COMPLETED
                    result.result = task_result
                    break

                except asyncio.TimeoutError:
                    task.retry_count = attempt + 1
                    if attempt < max_retries:
                        await asyncio.sleep(task.retry_delay_ms / 1000)
                    else:
                        raise TimeoutError(f"Task timed out after {timeout}ms")

                except Exception as e:
                    task.retry_count = attempt + 1
                    if attempt < max_retries:
                        logger.warning(f"Task {task.id} attempt {attempt + 1} failed: {e}")
                        await asyncio.sleep(task.retry_delay_ms / 1000)
                    else:
                        raise

        except Exception as e:
            task.status = TaskStatus.FAILED
            task.error = str(e)
            result.status = TaskStatus.FAILED
            result.error = str(e)

        finally:
            task.completed_at = datetime.now(timezone.utc)
            task.duration_ms = (task.completed_at - task.started_at).total_seconds() * 1000

            result.completed_at = task.completed_at
            result.duration_ms = task.duration_ms
            result.retries = task.retry_count

            self._results[task.id] = result

            if task.status == TaskStatus.COMPLETED:
                self._completed_ids.add(task.id)

            await self.callbacks.on_task_complete(task, result)


# Factory function for quick graph creation
def create_task_graph(
    phases: List[Dict[str, Any]],
    tasks: List[Dict[str, Any]],
    handlers: Optional[Dict[str, Callable]] = None,
) -> TaskGraph:
    """
    Create a task graph from configuration.

    Args:
        phases: List of phase configs
        tasks: List of task configs
        handlers: Optional handler registry

    Returns:
        Configured TaskGraph
    """
    graph = TaskGraph(handler_registry=handlers or {})

    for phase_config in phases:
        graph.add_phase(
            phase_id=phase_config["id"],
            name=phase_config.get("name"),
            parallel=phase_config.get("parallel", True),
            max_parallel=phase_config.get("max_parallel", 5),
            depends_on=phase_config.get("depends_on", []),
        )

    for task_config in tasks:
        graph.add_task(Task(
            id=task_config["id"],
            name=task_config.get("name"),
            phase=task_config.get("phase"),
            description=task_config.get("description", ""),
            handler_name=task_config.get("handler"),
            dependencies=task_config.get("dependencies", []),
            timeout_ms=task_config.get("timeout_ms"),
            retries=task_config.get("retries", 0),
        ))

    return graph
