"""
Run Budget Configuration

Provides configurable execution limits for orchestrated workflows.
Follows ralph's pattern of optional limits with defaults matching current behavior.

Usage:
    from ii_skills.shared.run_budgets import RunBudgetConfig, get_budget_for_timeframe

    # Use preset budgets
    budget = get_budget_for_timeframe("48_hour")

    # Or customize
    config = RunBudgetConfig(
        max_tasks=50,
        max_duration_minutes=30,
        max_parallel=5,
    )
"""

from dataclasses import dataclass, field
from typing import Optional, Dict, Any
from enum import Enum


class BudgetProfile(Enum):
    """Preset budget profiles."""
    QUICK = "quick"          # Fast, limited scope
    STANDARD = "standard"    # Normal operation
    THOROUGH = "thorough"    # Extended analysis
    UNLIMITED = "unlimited"  # No limits (legacy behavior)


@dataclass
class RunBudgetConfig:
    """
    Configuration for run execution budgets.

    Attributes:
        max_tasks: Maximum total tasks to execute (None = unlimited)
        max_failed_tasks: Maximum failed tasks before abort (None = unlimited)
        max_duration_minutes: Maximum total execution time (None = unlimited)
        max_parallel_tasks: Maximum concurrent tasks
        max_retries_per_task: Maximum retry attempts per task
        task_timeout_seconds: Default timeout per task
        max_api_calls: Maximum external API calls (None = unlimited)
        max_cache_size_mb: Maximum cache memory usage
        enable_checkpoints: Save checkpoints during execution
        checkpoint_interval_tasks: Tasks between checkpoints
    """
    # Task limits
    max_tasks: Optional[int] = None
    max_failed_tasks: Optional[int] = 10
    max_duration_minutes: Optional[float] = None

    # Concurrency
    max_parallel_tasks: int = 5
    max_retries_per_task: int = 3
    task_timeout_seconds: float = 60.0

    # Resource limits
    max_api_calls: Optional[int] = None
    max_cache_size_mb: Optional[float] = 100.0

    # Checkpointing
    enable_checkpoints: bool = True
    checkpoint_interval_tasks: int = 5

    # Profile name (for logging)
    profile: str = "custom"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "max_tasks": self.max_tasks,
            "max_failed_tasks": self.max_failed_tasks,
            "max_duration_minutes": self.max_duration_minutes,
            "max_parallel_tasks": self.max_parallel_tasks,
            "max_retries_per_task": self.max_retries_per_task,
            "task_timeout_seconds": self.task_timeout_seconds,
            "max_api_calls": self.max_api_calls,
            "max_cache_size_mb": self.max_cache_size_mb,
            "enable_checkpoints": self.enable_checkpoints,
            "checkpoint_interval_tasks": self.checkpoint_interval_tasks,
            "profile": self.profile,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'RunBudgetConfig':
        """Create from dictionary."""
        return cls(
            max_tasks=data.get("max_tasks"),
            max_failed_tasks=data.get("max_failed_tasks", 10),
            max_duration_minutes=data.get("max_duration_minutes"),
            max_parallel_tasks=data.get("max_parallel_tasks", 5),
            max_retries_per_task=data.get("max_retries_per_task", 3),
            task_timeout_seconds=data.get("task_timeout_seconds", 60.0),
            max_api_calls=data.get("max_api_calls"),
            max_cache_size_mb=data.get("max_cache_size_mb", 100.0),
            enable_checkpoints=data.get("enable_checkpoints", True),
            checkpoint_interval_tasks=data.get("checkpoint_interval_tasks", 5),
            profile=data.get("profile", "custom"),
        )


# Preset budget profiles
BUDGET_PROFILES: Dict[BudgetProfile, RunBudgetConfig] = {
    BudgetProfile.QUICK: RunBudgetConfig(
        max_tasks=20,
        max_failed_tasks=3,
        max_duration_minutes=5,
        max_parallel_tasks=3,
        max_retries_per_task=1,
        task_timeout_seconds=30.0,
        max_api_calls=50,
        enable_checkpoints=False,
        profile="quick",
    ),
    BudgetProfile.STANDARD: RunBudgetConfig(
        max_tasks=100,
        max_failed_tasks=10,
        max_duration_minutes=30,
        max_parallel_tasks=5,
        max_retries_per_task=3,
        task_timeout_seconds=60.0,
        max_api_calls=200,
        enable_checkpoints=True,
        checkpoint_interval_tasks=5,
        profile="standard",
    ),
    BudgetProfile.THOROUGH: RunBudgetConfig(
        max_tasks=500,
        max_failed_tasks=25,
        max_duration_minutes=120,
        max_parallel_tasks=10,
        max_retries_per_task=5,
        task_timeout_seconds=120.0,
        max_api_calls=1000,
        enable_checkpoints=True,
        checkpoint_interval_tasks=10,
        profile="thorough",
    ),
    BudgetProfile.UNLIMITED: RunBudgetConfig(
        max_tasks=None,
        max_failed_tasks=None,
        max_duration_minutes=None,
        max_parallel_tasks=5,
        max_retries_per_task=3,
        task_timeout_seconds=60.0,
        max_api_calls=None,
        enable_checkpoints=True,
        checkpoint_interval_tasks=5,
        profile="unlimited",
    ),
}


# Timeframe-specific budgets for deal analysis
TIMEFRAME_BUDGETS: Dict[str, RunBudgetConfig] = {
    "24_hour": RunBudgetConfig(
        max_tasks=30,
        max_failed_tasks=5,
        max_duration_minutes=15,
        max_parallel_tasks=5,
        task_timeout_seconds=45.0,
        max_api_calls=100,
        enable_checkpoints=True,
        profile="24_hour",
    ),
    "48_hour": RunBudgetConfig(
        max_tasks=75,
        max_failed_tasks=10,
        max_duration_minutes=45,
        max_parallel_tasks=5,
        task_timeout_seconds=60.0,
        max_api_calls=250,
        enable_checkpoints=True,
        profile="48_hour",
    ),
    "5_day": RunBudgetConfig(
        max_tasks=200,
        max_failed_tasks=20,
        max_duration_minutes=90,
        max_parallel_tasks=8,
        task_timeout_seconds=90.0,
        max_api_calls=500,
        enable_checkpoints=True,
        profile="5_day",
    ),
    "7_day_plus": RunBudgetConfig(
        max_tasks=500,
        max_failed_tasks=50,
        max_duration_minutes=180,
        max_parallel_tasks=10,
        task_timeout_seconds=120.0,
        max_api_calls=1000,
        enable_checkpoints=True,
        profile="7_day_plus",
    ),
}


# Skill-specific default budgets
SKILL_BUDGETS: Dict[str, RunBudgetConfig] = {
    "deal_analysis": RunBudgetConfig(
        max_tasks=100,
        max_failed_tasks=10,
        max_duration_minutes=60,
        max_parallel_tasks=5,
        profile="deal_analysis",
    ),
    "newsletter": RunBudgetConfig(
        max_tasks=20,
        max_failed_tasks=5,
        max_duration_minutes=10,
        max_parallel_tasks=3,
        profile="newsletter",
    ),
    "research": RunBudgetConfig(
        max_tasks=50,
        max_failed_tasks=10,
        max_duration_minutes=30,
        max_parallel_tasks=5,
        profile="research",
    ),
    "data_collection": RunBudgetConfig(
        max_tasks=200,
        max_failed_tasks=20,
        max_duration_minutes=45,
        max_parallel_tasks=10,
        profile="data_collection",
    ),
}


def get_budget_profile(profile: BudgetProfile) -> RunBudgetConfig:
    """Get a preset budget profile."""
    return BUDGET_PROFILES.get(profile, BUDGET_PROFILES[BudgetProfile.STANDARD])


def get_budget_for_timeframe(timeframe: str) -> RunBudgetConfig:
    """
    Get budget configuration for a deal analysis timeframe.

    Args:
        timeframe: One of "24_hour", "48_hour", "5_day", "7_day_plus"

    Returns:
        RunBudgetConfig for the timeframe, or standard if not found
    """
    return TIMEFRAME_BUDGETS.get(timeframe, BUDGET_PROFILES[BudgetProfile.STANDARD])


def get_budget_for_skill(skill_name: str) -> RunBudgetConfig:
    """
    Get budget configuration for a specific skill.

    Args:
        skill_name: Name of the skill

    Returns:
        RunBudgetConfig for the skill, or standard if not found
    """
    return SKILL_BUDGETS.get(skill_name, BUDGET_PROFILES[BudgetProfile.STANDARD])


def create_custom_budget(
    base: Optional[RunBudgetConfig] = None,
    **overrides,
) -> RunBudgetConfig:
    """
    Create a custom budget configuration.

    Args:
        base: Optional base configuration to extend
        **overrides: Values to override

    Returns:
        New RunBudgetConfig with overrides applied
    """
    if base is None:
        base = BUDGET_PROFILES[BudgetProfile.STANDARD]

    config_dict = base.to_dict()
    config_dict.update(overrides)
    config_dict["profile"] = "custom"

    return RunBudgetConfig.from_dict(config_dict)


class BudgetEnforcer:
    """
    Tracks and enforces budget constraints during execution.

    Usage:
        enforcer = BudgetEnforcer(budget)

        if enforcer.can_start_task():
            # run task
            enforcer.record_task_complete()
    """

    def __init__(self, budget: RunBudgetConfig):
        """Initialize with budget configuration."""
        self.budget = budget
        self.tasks_completed = 0
        self.tasks_failed = 0
        self.api_calls = 0
        self.start_time: Optional[float] = None
        self._violations: list = []

    def start(self):
        """Mark execution start."""
        import time
        self.start_time = time.time()

    def elapsed_minutes(self) -> float:
        """Get elapsed time in minutes."""
        if self.start_time is None:
            return 0.0
        import time
        return (time.time() - self.start_time) / 60.0

    def can_start_task(self) -> bool:
        """Check if a new task can be started within budget."""
        # Check task count
        if self.budget.max_tasks is not None:
            if self.tasks_completed + self.tasks_failed >= self.budget.max_tasks:
                self._violations.append("max_tasks exceeded")
                return False

        # Check failed tasks
        if self.budget.max_failed_tasks is not None:
            if self.tasks_failed >= self.budget.max_failed_tasks:
                self._violations.append("max_failed_tasks exceeded")
                return False

        # Check duration
        if self.budget.max_duration_minutes is not None:
            if self.elapsed_minutes() >= self.budget.max_duration_minutes:
                self._violations.append("max_duration exceeded")
                return False

        return True

    def can_make_api_call(self) -> bool:
        """Check if an API call is within budget."""
        if self.budget.max_api_calls is not None:
            if self.api_calls >= self.budget.max_api_calls:
                self._violations.append("max_api_calls exceeded")
                return False
        return True

    def record_task_complete(self, success: bool = True):
        """Record a task completion."""
        if success:
            self.tasks_completed += 1
        else:
            self.tasks_failed += 1

    def record_api_call(self, count: int = 1):
        """Record API calls made."""
        self.api_calls += count

    def should_checkpoint(self) -> bool:
        """Check if a checkpoint should be saved."""
        if not self.budget.enable_checkpoints:
            return False

        total_tasks = self.tasks_completed + self.tasks_failed
        return total_tasks > 0 and total_tasks % self.budget.checkpoint_interval_tasks == 0

    def get_status(self) -> Dict[str, Any]:
        """Get current enforcement status."""
        return {
            "tasks_completed": self.tasks_completed,
            "tasks_failed": self.tasks_failed,
            "api_calls": self.api_calls,
            "elapsed_minutes": round(self.elapsed_minutes(), 2),
            "violations": self._violations.copy(),
            "within_budget": len(self._violations) == 0,
            "budget_profile": self.budget.profile,
        }

    def get_remaining(self) -> Dict[str, Any]:
        """Get remaining budget capacity."""
        remaining = {}

        if self.budget.max_tasks is not None:
            remaining["tasks"] = max(0, self.budget.max_tasks - self.tasks_completed - self.tasks_failed)

        if self.budget.max_failed_tasks is not None:
            remaining["failed_tasks"] = max(0, self.budget.max_failed_tasks - self.tasks_failed)

        if self.budget.max_duration_minutes is not None:
            remaining["duration_minutes"] = max(0, self.budget.max_duration_minutes - self.elapsed_minutes())

        if self.budget.max_api_calls is not None:
            remaining["api_calls"] = max(0, self.budget.max_api_calls - self.api_calls)

        return remaining
