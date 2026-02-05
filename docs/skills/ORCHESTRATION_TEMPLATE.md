# Standardized Skill Orchestration Template

A template for building consistent, well-orchestrated skills following patterns proven in the IB and IR toolkits.

---

## Overview

This template provides a standardized approach to skill orchestration with:
- Multi-phase execution
- Dependency-driven task graphs
- Progress callbacks
- Budget enforcement
- Telemetry integration

---

## Template Structure

```
src/ii_skills/my_skill/
├── __init__.py           # Package exports
├── orchestrator.py       # Main orchestrator class
├── config.py             # Skill configuration
├── modules/              # Analysis modules
│   ├── module_a.py
│   └── module_b.py
├── generators/           # Output generators
│   ├── excel_generator.py
│   └── pptx_generator.py
├── templates/            # Reference templates
└── outputs/              # Generated outputs
```

---

## Core Orchestrator Template

```python
"""
My Skill Orchestrator

Multi-phase orchestration for [skill purpose].

Usage:
    from ii_skills.my_skill import MyToolkit, CaseType

    toolkit = MyToolkit(user_id="user123")
    result = await toolkit.run_case(
        case_type=CaseType.TYPE_A,
        **inputs,
    )
"""

import asyncio
import logging
import uuid
from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field
from pathlib import Path

# Import shared infrastructure
from ii_skills.shared import (
    PhaseRunner,
    PhaseRunnerConfig,
    PhaseRunnerCallback,
    ConsolePhaseRunnerCallback,
    PhaseTask,
    RunnerPhase,
    create_phase,
    TelemetryLogger,
    RunRecord,
    BudgetEnforcer,
    BudgetProfile,
    track_tool_execution,
    ToolErrorType,
)

logger = logging.getLogger(__name__)


# =============================================================================
# ENUMS AND DATA CLASSES
# =============================================================================

class CaseType(Enum):
    """Types of cases this skill handles."""
    TYPE_A = "type_a"
    TYPE_B = "type_b"
    CUSTOM = "custom"


class Phase(Enum):
    """Execution phases."""
    DATA_COLLECTION = "data_collection"
    ANALYSIS = "analysis"
    GENERATION = "generation"
    QA = "qa"


class TaskStatus(Enum):
    """Task status."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class Module:
    """Represents an analysis module."""
    id: str
    name: str
    category: str
    description: str
    dependencies: List[str] = field(default_factory=list)
    status: TaskStatus = TaskStatus.PENDING
    result: Any = None
    error: Optional[str] = None


@dataclass
class State:
    """State for skill execution."""
    case_id: str
    case_type: CaseType

    # Phase tracking
    current_phase: Phase = Phase.DATA_COLLECTION
    completed_phases: List[str] = field(default_factory=list)
    module_phases: Dict[str, List[str]] = field(default_factory=dict)

    # Module tracking
    modules: Dict[str, Module] = field(default_factory=dict)

    # Data containers (customize for your skill)
    input_data: Dict = field(default_factory=dict)
    analysis_data: Dict = field(default_factory=dict)

    # Outputs
    outputs: Dict[str, str] = field(default_factory=dict)

    # Metadata
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    user_id: Optional[str] = None


# =============================================================================
# MODULE DEFINITIONS
# =============================================================================

# Define modules for each case type
TYPE_A_MODULES = [
    Module("module_1", "Module One", "Core", "First analysis module"),
    Module("module_2", "Module Two", "Core", "Second module", depends_on=["module_1"]),
    Module("module_3", "Module Three", "Output", "Output generation"),
]

TYPE_B_MODULES = [
    Module("module_1", "Module One", "Core", "First analysis module"),
    Module("module_4", "Module Four", "Extended", "Extended analysis"),
]


# =============================================================================
# PROGRESS CALLBACK
# =============================================================================

class ProgressCallback:
    """Callback interface for progress updates."""

    async def on_phase_start(self, phase: Phase, modules: List[str]):
        pass

    async def on_module_start(self, module: Module):
        pass

    async def on_module_complete(self, module: Module):
        pass

    async def on_module_error(self, module: Module, error: str):
        pass

    async def on_phase_complete(self, phase: Phase, results: Dict):
        pass

    async def on_case_complete(self, state: State):
        pass


class ConsoleProgressCallback(ProgressCallback):
    """Console-based progress output."""

    async def on_phase_start(self, phase: Phase, modules: List[str]):
        print(f"\n{'='*60}")
        print(f"Phase: {phase.value.upper()}")
        print(f"Modules: {', '.join(modules)}")
        print(f"{'='*60}")

    async def on_module_start(self, module: Module):
        print(f"  [STARTED] {module.name}")

    async def on_module_complete(self, module: Module):
        print(f"  [DONE] {module.name}")

    async def on_module_error(self, module: Module, error: str):
        print(f"  [ERROR] {module.name}: {error}")

    async def on_phase_complete(self, phase: Phase, results: Dict):
        print(f"\nPhase {phase.value} complete. Modules: {len(results)}")

    async def on_case_complete(self, state: State):
        print(f"\n{'='*60}")
        print(f"Case Complete: {state.case_id[:8]}")
        print(f"Outputs: {len(state.outputs)}")
        print(f"{'='*60}")


# =============================================================================
# MAIN TOOLKIT CLASS
# =============================================================================

class MyToolkit:
    """
    Main orchestrator for [skill name].

    Coordinates multi-phase analysis with dependency tracking,
    progress callbacks, and budget enforcement.
    """

    def __init__(
        self,
        user_id: str,
        output_dir: Optional[str] = None,
        progress_callback: Optional[ProgressCallback] = None,
        budget_profile: str = "standard",
    ):
        """
        Initialize the toolkit.

        Args:
            user_id: User ID for tracking
            output_dir: Output directory for generated files
            progress_callback: Callback for progress updates
            budget_profile: Budget profile name
        """
        self.user_id = user_id
        self.output_dir = Path(output_dir) if output_dir else Path(__file__).parent / "outputs"
        self.progress = progress_callback or ConsoleProgressCallback()
        self.budget_profile = budget_profile

        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.state: Optional[State] = None
        self.budget_enforcer: Optional[BudgetEnforcer] = None

    def _get_modules_for_case(self, case_type: CaseType) -> List[Module]:
        """Get modules based on case type."""
        module_map = {
            CaseType.TYPE_A: TYPE_A_MODULES,
            CaseType.TYPE_B: TYPE_B_MODULES,
        }
        # Create copies to avoid state pollution
        return [Module(**m.__dict__) for m in module_map.get(case_type, TYPE_A_MODULES)]

    async def run_case(
        self,
        case_type: CaseType,
        input_data: Optional[Dict] = None,
        custom_modules: Optional[List[str]] = None,
    ) -> State:
        """
        Run a complete case analysis.

        Args:
            case_type: Type of case
            input_data: Input data dictionary
            custom_modules: Optional list of specific modules to run

        Returns:
            State with all analysis results
        """
        # Initialize state
        self.state = State(
            case_id=str(uuid.uuid4()),
            case_type=case_type,
            user_id=self.user_id,
        )

        if input_data:
            self.state.input_data = input_data

        # Initialize budget
        budget_config = BudgetProfile.get_profile(self.budget_profile)
        self.budget_enforcer = BudgetEnforcer(budget_config)

        # Get modules
        modules = self._get_modules_for_case(case_type)
        if custom_modules:
            modules = [m for m in modules if m.id in custom_modules]

        for module in modules:
            self.state.modules[module.id] = module

        # Run phases
        phases = [
            Phase.DATA_COLLECTION,
            Phase.ANALYSIS,
            Phase.GENERATION,
            Phase.QA,
        ]

        for phase in phases:
            if phase.value in self.state.completed_phases:
                continue

            # Check budget
            if self.budget_enforcer:
                status = self.budget_enforcer.check_budget()
                if status.get("budget_exhausted"):
                    logger.warning(f"Budget exhausted at phase {phase.value}")
                    break

            await self._run_phase(phase)

        await self.progress.on_case_complete(self.state)
        return self.state

    async def _run_phase(self, phase: Phase):
        """Run all modules in a phase."""
        self.state.current_phase = phase
        modules = list(self.state.modules.values())
        module_names = [m.name for m in modules]

        await self.progress.on_phase_start(phase, module_names)

        for module in modules:
            # Check if already completed this phase
            module_phases = self.state.module_phases.get(module.id, [])
            if phase.value in module_phases:
                continue

            await self._run_module(module, phase)

        self.state.completed_phases.append(phase.value)
        results = {m.id: m.result for m in modules}
        await self.progress.on_phase_complete(phase, results)

    async def _run_module(self, module: Module, phase: Phase):
        """Run a single module for a phase."""
        module.status = TaskStatus.RUNNING
        await self.progress.on_module_start(module)

        try:
            # Use tool metrics tracking
            with track_tool_execution(f"{module.id}_{phase.value}") as tracker:
                if phase == Phase.DATA_COLLECTION:
                    module.result = await self._collect_data(module)
                elif phase == Phase.ANALYSIS:
                    module.result = await self._run_analysis(module)
                elif phase == Phase.GENERATION:
                    module.result = await self._generate_output(module)
                elif phase == Phase.QA:
                    module.result = await self._run_qa(module)

            # Track phase completion
            if module.id not in self.state.module_phases:
                self.state.module_phases[module.id] = []
            self.state.module_phases[module.id].append(phase.value)

            if phase == Phase.QA:
                module.status = TaskStatus.COMPLETED
            else:
                module.status = TaskStatus.PENDING

            await self.progress.on_module_complete(module)

            # Record task for budget
            if self.budget_enforcer:
                self.budget_enforcer.record_task()

        except Exception as e:
            module.status = TaskStatus.FAILED
            module.error = str(e)
            logger.error(f"Module {module.id} failed: {e}")
            await self.progress.on_module_error(module, str(e))

    # ==========================================================================
    # PHASE IMPLEMENTATIONS (customize for your skill)
    # ==========================================================================

    async def _collect_data(self, module: Module) -> Dict:
        """Collect data for a module. Override in subclass."""
        return {
            "module_id": module.id,
            "data_collected": True,
            "timestamp": datetime.now().isoformat(),
        }

    async def _run_analysis(self, module: Module) -> Dict:
        """Run analysis for a module. Override in subclass."""
        return {
            "module_id": module.id,
            "analysis_complete": True,
        }

    async def _generate_output(self, module: Module) -> Dict:
        """Generate output for a module. Override in subclass."""
        return {
            "module_id": module.id,
            "output_generated": True,
        }

    async def _run_qa(self, module: Module) -> Dict:
        """Run QA checks for a module. Override in subclass."""
        return {
            "module_id": module.id,
            "qa_passed": True,
        }


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

async def run_type_a_case(input_data: Dict, user_id: str = "default") -> State:
    """Convenience function for Type A cases."""
    toolkit = MyToolkit(user_id=user_id)
    return await toolkit.run_case(
        case_type=CaseType.TYPE_A,
        input_data=input_data,
    )
```

---

## Integration Patterns

### 1. Telemetry Integration

```python
from ii_skills.shared import TelemetryLogger, get_telemetry_logger

class TelemetryProgressCallback(ProgressCallback):
    """Progress callback that emits telemetry events."""

    def __init__(self, telemetry: TelemetryLogger, run_record: RunRecord):
        self.telemetry = telemetry
        self.run_record = run_record

    async def on_module_complete(self, module: Module):
        # Emit event via telemetry
        await self.telemetry.emit_event(
            event_type="module_completed",
            run_id=self.run_record.run_id,
            data={"module_id": module.id, "status": module.status.value},
        )
```

### 2. Sub-Agent Integration

```python
from ii_skills.shared import traced_subagent

async def _run_analysis(self, module: Module) -> Dict:
    """Run analysis with sub-agent tracing."""
    async with traced_subagent(
        parent_run_id=self.state.case_id,
        agent_type="analysis",
        task_description=f"Analyze {module.name}",
    ) as ctx:
        result = await self._do_analysis(module)
        ctx.set_result(result)
        return result
```

### 3. Budget Enforcement

```python
from ii_skills.shared import BudgetEnforcer, BudgetProfile

# In run_case:
budget_config = BudgetProfile.get_profile("thorough")
self.budget_enforcer = BudgetEnforcer(budget_config)

# Before each task:
status = self.budget_enforcer.check_budget()
if status.get("budget_exhausted"):
    raise BudgetExceededError(status.get("reason"))

# After each task:
self.budget_enforcer.record_task()
```

### 4. Using PhaseRunner Directly

```python
from ii_skills.shared import PhaseRunner, PhaseRunnerConfig, create_phase

# Define phases with task executors
phases = [
    create_phase("data_collection", [
        {"id": "fetch_data", "executor": fetch_data_func},
        {"id": "validate", "executor": validate_func, "depends_on": ["fetch_data"]},
    ]),
    create_phase("analysis", [
        {"id": "analyze", "executor": analyze_func},
    ]),
]

# Create runner
config = PhaseRunnerConfig(max_parallel_tasks=5, fail_fast=False)
runner = PhaseRunner(phases, config=config)

# Execute
results = await runner.execute()
```

---

## Checklist for New Skills

- [ ] Define `CaseType` enum for supported case types
- [ ] Define `Module` dataclass with skill-specific fields
- [ ] Define phases appropriate for your workflow
- [ ] Create module definitions for each case type
- [ ] Implement phase methods (`_collect_data`, `_run_analysis`, etc.)
- [ ] Add progress callback for user feedback
- [ ] Integrate budget enforcement
- [ ] Add telemetry for observability
- [ ] Create output generators (Excel, PowerPoint, etc.)
- [ ] Write tests for each phase
- [ ] Document in CAPABILITIES.md and QUICK_REFERENCE.md

---

## Examples

### IB Toolkit

```python
# See: src/ii_skills/ib_toolkit/deal_orchestrator.py
from ii_skills.ib_toolkit import DealOrchestrator, DealType

orchestrator = DealOrchestrator(user_id="analyst")
result = await orchestrator.run_deal(
    deal_type=DealType.LBO,
    company_name="Target Corp",
    entry_multiple=8.0,
)
```

### IR Toolkit

```python
# See: src/ii_skills/ir_toolkit/ir_orchestrator.py
from ii_skills.ir_toolkit import IRToolkit, IRCaseType

toolkit = IRToolkit(user_id="ir_team")
result = await toolkit.generate_lp_update(
    fund_name="Global Infrastructure Fund IV",
    reporting_period="Q4 2025",
)
```

---

*Last Updated: 2026-02-04*
