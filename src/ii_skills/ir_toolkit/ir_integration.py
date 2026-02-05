"""
IR Toolkit Integration with Shared Infrastructure

Connects the IR toolkit with:
- Event telemetry (run start/end hooks)
- Task graph executor (dependency-aware execution)
- Run budgets (configurable limits)
- Event schema (typed payloads)
"""

import logging
from datetime import datetime
from typing import Optional, Dict, Any, List
from pathlib import Path

from ii_skills.ir_toolkit.ir_orchestrator import (
    IRToolkit,
    IRCaseType,
    IRPhase,
    IRState,
    IRProgressCallback,
    IRModule,
    IRTaskStatus,
)

logger = logging.getLogger(__name__)

# Try to import shared infrastructure
try:
    from ii_skills.shared.event_telemetry import TelemetryLogger, RunRecord
    from ii_skills.shared.run_budgets import RunBudgetConfig, BudgetEnforcer, BudgetProfile
    from ii_skills.shared.event_schema import (
        EventPayload,
        RunStartedPayload,
        RunCompletedPayload,
        PhaseStartedPayload,
        PhaseCompletedPayload,
        TaskCompletedPayload,
    )
    SHARED_INFRA_AVAILABLE = True
except ImportError:
    SHARED_INFRA_AVAILABLE = False
    logger.warning("Shared infrastructure not available. Running in standalone mode.")


class TelemetryIRProgressCallback(IRProgressCallback):
    """
    Progress callback that emits telemetry events.

    Integrates with the shared event_telemetry module for
    run tracking and persistence.
    """

    def __init__(
        self,
        telemetry: "TelemetryLogger",
        run_record: "RunRecord",
        emit_events: bool = True,
    ):
        self.telemetry = telemetry
        self.run_record = run_record
        self.emit_events = emit_events
        self.phase_start_times: Dict[str, datetime] = {}

    async def on_phase_start(self, phase: IRPhase, modules: List[str]):
        """Record phase start for telemetry."""
        self.phase_start_times[phase.value] = datetime.now()

        if self.emit_events and SHARED_INFRA_AVAILABLE:
            payload = PhaseStartedPayload(
                event_type="phase_started",
                timestamp=datetime.now(),
                run_id=self.run_record.run_id,
                phase_name=phase.value,
                total_tasks=len(modules),
            )
            # Log via telemetry
            logger.info(f"Phase started: {phase.value} with {len(modules)} modules")

    async def on_module_complete(self, module: IRModule):
        """Record module completion."""
        if self.emit_events and SHARED_INFRA_AVAILABLE:
            payload = TaskCompletedPayload(
                event_type="task_completed",
                timestamp=datetime.now(),
                run_id=self.run_record.run_id,
                task_id=module.id,
                task_name=module.name,
                success=module.status == IRTaskStatus.COMPLETED,
                error_message=module.error,
            )
            logger.info(f"Module completed: {module.name}")

    async def on_module_error(self, module: IRModule, error: str):
        """Record module error."""
        logger.error(f"Module error: {module.name} - {error}")

    async def on_phase_complete(self, phase: IRPhase, results: Dict):
        """Record phase completion."""
        start_time = self.phase_start_times.get(phase.value)
        duration = None
        if start_time:
            duration = (datetime.now() - start_time).total_seconds()

        if self.emit_events and SHARED_INFRA_AVAILABLE:
            payload = PhaseCompletedPayload(
                event_type="phase_completed",
                timestamp=datetime.now(),
                run_id=self.run_record.run_id,
                phase_name=phase.value,
                completed_tasks=len(results),
                duration_seconds=duration,
            )
            logger.info(f"Phase completed: {phase.value} ({len(results)} modules)")

    async def on_case_complete(self, state: IRState):
        """Record case completion and finalize telemetry."""
        logger.info(f"IR case complete: {state.fund_name}")

        # Update run record
        self.run_record.end_time = datetime.now()
        self.run_record.status = "completed"
        self.run_record.outputs = {
            "excel_count": len(state.excel_outputs),
            "slide_count": len(state.slide_outputs),
            "excel_files": list(state.excel_outputs.values()),
            "slide_files": list(state.slide_outputs.values()),
        }

        # Save via telemetry
        if SHARED_INFRA_AVAILABLE:
            await self.telemetry.on_run_end(self.run_record)


class BudgetAwareIRToolkit(IRToolkit):
    """
    IR toolkit with budget enforcement.

    Extends the base toolkit to track execution against
    configurable budgets (max tasks, duration, parallel).
    """

    def __init__(
        self,
        user_id: str,
        output_dir: Optional[str] = None,
        progress_callback: Optional[IRProgressCallback] = None,
        budget_config: Optional["RunBudgetConfig"] = None,
    ):
        super().__init__(user_id, output_dir, progress_callback)

        self.budget_config = budget_config
        self.budget_enforcer: Optional["BudgetEnforcer"] = None

        if SHARED_INFRA_AVAILABLE and budget_config:
            self.budget_enforcer = BudgetEnforcer(budget_config)

    async def _run_module(self, module: IRModule, phase: IRPhase):
        """Run module with budget checking."""
        # Check budget before running
        if self.budget_enforcer:
            budget_status = self.budget_enforcer.check_budget()
            if budget_status.get("budget_exhausted"):
                logger.warning(f"Budget exhausted, skipping module: {module.name}")
                module.status = IRTaskStatus.SKIPPED
                module.error = "Budget exhausted"
                return

        # Run module
        await super()._run_module(module, phase)

        # Record task completion for budget tracking
        if self.budget_enforcer:
            self.budget_enforcer.record_task()


async def run_ir_case_with_telemetry(
    case_type: IRCaseType,
    fund_name: str,
    reporting_period: str,
    user_id: str = "default",
    output_dir: Optional[str] = None,
    budget_profile: str = "standard",
    **kwargs,
) -> IRState:
    """
    Run an IR case with full telemetry integration.

    Args:
        case_type: Type of IR case
        fund_name: Name of the fund
        reporting_period: Reporting period
        user_id: User ID for tracking
        output_dir: Output directory
        budget_profile: Budget profile name
        **kwargs: Additional arguments for run_ir_case

    Returns:
        IRState with results
    """
    # Set up output directory
    if output_dir is None:
        output_dir = Path(__file__).parent / "outputs" / fund_name.replace(" ", "_")
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # Initialize telemetry if available
    telemetry = None
    run_record = None
    progress_callback = None

    if SHARED_INFRA_AVAILABLE:
        telemetry = TelemetryLogger(
            storage_dir=output_path / "telemetry",
            user_id=user_id,
        )

        run_record = await telemetry.on_run_start(
            run_type=f"ir_{case_type.value}",
            metadata={
                "fund_name": fund_name,
                "reporting_period": reporting_period,
                "case_type": case_type.value,
            },
        )

        progress_callback = TelemetryIRProgressCallback(
            telemetry=telemetry,
            run_record=run_record,
        )

    # Get budget config
    budget_config = None
    if SHARED_INFRA_AVAILABLE:
        budget_config = BudgetProfile.get_profile(budget_profile)

    # Create toolkit
    toolkit = BudgetAwareIRToolkit(
        user_id=user_id,
        output_dir=str(output_path),
        progress_callback=progress_callback,
        budget_config=budget_config,
    )

    # Run case
    state = await toolkit.run_ir_case(
        case_type=case_type,
        fund_name=fund_name,
        reporting_period=reporting_period,
        **kwargs,
    )

    return state


# Convenience functions for common case types
async def generate_lp_update_with_telemetry(
    fund_name: str,
    reporting_period: str,
    **kwargs,
) -> IRState:
    """Generate LP update with telemetry."""
    return await run_ir_case_with_telemetry(
        case_type=IRCaseType.LP_UPDATE,
        fund_name=fund_name,
        reporting_period=reporting_period,
        **kwargs,
    )


async def generate_fundraising_deck_with_telemetry(
    fund_name: str,
    **kwargs,
) -> IRState:
    """Generate fundraising deck with telemetry."""
    return await run_ir_case_with_telemetry(
        case_type=IRCaseType.FUNDRAISING,
        fund_name=fund_name,
        reporting_period="Current",
        **kwargs,
    )


async def generate_ddq_response_with_telemetry(
    fund_name: str,
    **kwargs,
) -> IRState:
    """Generate DDQ response with telemetry."""
    return await run_ir_case_with_telemetry(
        case_type=IRCaseType.DDQ_RESPONSE,
        fund_name=fund_name,
        reporting_period="Current",
        **kwargs,
    )
