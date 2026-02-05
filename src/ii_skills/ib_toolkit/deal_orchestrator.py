"""
Deal Orchestrator for IB Toolkit

Multi-agent orchestration system for comprehensive deal analysis.
Coordinates parallel execution of specialized analysis agents across
multiple phases with real-time progress tracking.

Phases:
- Phase 0: Data Collection (parallel)
- Phase 1: Foundation Analysis (parallel)
- Phase 2: Financial Deep Dive (sequential)
- Phase 3: Deal Structuring (sequential)
- Phase 4: Output Generation (parallel)

Usage:
    from ii_skills.ib_toolkit.deal_orchestrator import DealOrchestrator

    orchestrator = DealOrchestrator(
        user_id="...",
        session_id="...",
    )

    result = await orchestrator.run_deal_analysis(
        company_name="Acme Corp",
        ticker="ACME",
        deal_type="lbo",
        timeframe="48_hour",
    )
"""

import asyncio
import logging
import uuid
from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict, Any, Callable
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

# Import run budgets (optional)
try:
    from ii_skills.shared.run_budgets import (
        RunBudgetConfig,
        BudgetEnforcer,
        get_budget_for_timeframe,
        BUDGET_PROFILES,
        BudgetProfile,
    )
    BUDGETS_AVAILABLE = True
except ImportError:
    BUDGETS_AVAILABLE = False
    RunBudgetConfig = None
    BudgetEnforcer = None


class DealPhase(Enum):
    """Deal analysis phases."""
    DATA_COLLECTION = "data_collection"
    FOUNDATION = "foundation"
    FINANCIAL = "financial"
    DEAL_STRUCTURE = "deal_structure"
    OUTPUT = "output"


class TaskStatus(Enum):
    """Task execution status."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class AnalysisTask:
    """Represents a single analysis task."""
    id: str
    name: str
    phase: DealPhase
    description: str
    handler: str  # Method name to execute
    dependencies: List[str] = field(default_factory=list)
    status: TaskStatus = TaskStatus.PENDING
    result: Any = None
    error: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_ms: Optional[float] = None


@dataclass
class DealState:
    """Persistent state for deal analysis."""
    deal_id: str
    company_name: str
    ticker: str
    deal_type: str
    timeframe: str

    # Phase tracking
    current_phase: DealPhase = DealPhase.DATA_COLLECTION
    completed_phases: List[str] = field(default_factory=list)

    # Task tracking
    tasks: Dict[str, AnalysisTask] = field(default_factory=dict)

    # Accumulated data
    company_data: Dict = field(default_factory=dict)
    research_data: Dict = field(default_factory=dict)
    financial_analysis: Dict = field(default_factory=dict)
    deal_structure: Dict = field(default_factory=dict)

    # Outputs
    outputs: Dict[str, str] = field(default_factory=dict)

    # Metadata
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    user_id: Optional[str] = None
    session_id: Optional[str] = None


class ProgressCallback:
    """Callback interface for progress updates."""

    async def on_phase_start(self, phase: DealPhase, tasks: List[str]):
        """Called when a phase starts."""
        pass

    async def on_task_start(self, task: AnalysisTask):
        """Called when a task starts."""
        pass

    async def on_task_complete(self, task: AnalysisTask):
        """Called when a task completes."""
        pass

    async def on_task_error(self, task: AnalysisTask, error: str):
        """Called when a task fails."""
        pass

    async def on_phase_complete(self, phase: DealPhase, results: Dict):
        """Called when a phase completes."""
        pass

    async def on_deal_complete(self, state: DealState):
        """Called when deal analysis completes."""
        pass


class ConsoleProgressCallback(ProgressCallback):
    """Progress callback that prints to console."""

    async def on_phase_start(self, phase: DealPhase, tasks: List[str]):
        print(f"\n{'='*60}")
        print(f"Phase: {phase.value.upper()}")
        print(f"Tasks: {', '.join(tasks)}")
        print(f"{'='*60}")

    async def on_task_start(self, task: AnalysisTask):
        print(f"  [STARTED] {task.name}")

    async def on_task_complete(self, task: AnalysisTask):
        duration = f" ({task.duration_ms:.0f}ms)" if task.duration_ms else ""
        print(f"  [DONE] {task.name}{duration}")

    async def on_task_error(self, task: AnalysisTask, error: str):
        print(f"  [ERROR] {task.name}: {error}")

    async def on_phase_complete(self, phase: DealPhase, results: Dict):
        print(f"\nPhase {phase.value} complete. Results: {len(results)} tasks")

    async def on_deal_complete(self, state: DealState):
        print(f"\n{'='*60}")
        print(f"Deal Analysis Complete: {state.company_name}")
        print(f"Outputs: {list(state.outputs.keys())}")
        print(f"{'='*60}")


class DealOrchestrator:
    """
    Orchestrates multi-phase deal analysis with parallel execution.

    Coordinates specialized analysis tasks across phases:
    - Phase 0: Data Collection (company data, news, industry)
    - Phase 1: Foundation (business quality, market position, management)
    - Phase 2: Financial (historical, projections, working capital)
    - Phase 3: Deal Structure (valuation, debt capacity, returns)
    - Phase 4: Output Generation (model, slides, report)
    """

    def __init__(
        self,
        user_id: str,
        session_id: Optional[str] = None,
        output_dir: Optional[str] = None,
        progress_callback: Optional[ProgressCallback] = None,
        max_parallel_tasks: int = 5,
        budget: Optional['RunBudgetConfig'] = None,
    ):
        """
        Initialize the deal orchestrator.

        Args:
            user_id: User ID for tracking
            session_id: Optional session ID
            output_dir: Output directory for generated files
            progress_callback: Callback for progress updates
            max_parallel_tasks: Maximum tasks to run in parallel
            budget: Optional run budget configuration (defaults to timeframe-based)
        """
        self.user_id = user_id
        self.session_id = session_id or str(uuid.uuid4())
        self.output_dir = Path(output_dir) if output_dir else Path(__file__).parent / "outputs"
        self.progress = progress_callback or ConsoleProgressCallback()
        self.max_parallel_tasks = max_parallel_tasks

        # Budget configuration (optional, defaults set per timeframe)
        self._budget_config = budget
        self._budget_enforcer: Optional['BudgetEnforcer'] = None

        # Ensure output directory exists
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Current state
        self.state: Optional[DealState] = None

        # Task registry
        self._task_handlers: Dict[str, Callable] = {}
        self._register_task_handlers()

    def _register_task_handlers(self):
        """Register all task handler methods."""
        self._task_handlers = {
            # Phase 0: Data Collection
            "fetch_company_data": self._fetch_company_data,
            "fetch_news": self._fetch_news,
            "fetch_industry_data": self._fetch_industry_data,
            "fetch_competitors": self._fetch_competitors,

            # Phase 1: Foundation
            "analyze_business_quality": self._analyze_business_quality,
            "analyze_market_position": self._analyze_market_position,
            "analyze_management": self._analyze_management,

            # Phase 2: Financial
            "analyze_historical_financials": self._analyze_historical_financials,
            "build_projections": self._build_projections,
            "analyze_working_capital": self._analyze_working_capital,

            # Phase 3: Deal Structure
            "run_valuation": self._run_valuation,
            "analyze_debt_capacity": self._analyze_debt_capacity,
            "calculate_returns": self._calculate_returns,
            "build_sensitivity": self._build_sensitivity,

            # Phase 4: Outputs
            "generate_excel_model": self._generate_excel_model,
            "generate_slides": self._generate_slides,
            "generate_research_report": self._generate_research_report,
        }

    def _get_phase_tasks(self, phase: DealPhase, deal_type: str, timeframe: str) -> List[AnalysisTask]:
        """Get tasks for a specific phase based on deal type and timeframe."""

        # Task definitions by phase
        phase_tasks = {
            DealPhase.DATA_COLLECTION: [
                AnalysisTask("fetch_company_data", "Fetch Company Data", phase, "Get financial data from Yahoo Finance", "fetch_company_data"),
                AnalysisTask("fetch_news", "Fetch News", phase, "Get recent news articles", "fetch_news"),
                AnalysisTask("fetch_industry_data", "Fetch Industry Data", phase, "Get industry trends and benchmarks", "fetch_industry_data"),
                AnalysisTask("fetch_competitors", "Fetch Competitors", phase, "Identify and research competitors", "fetch_competitors"),
            ],
            DealPhase.FOUNDATION: [
                AnalysisTask("analyze_business_quality", "Business Quality", phase, "Assess business model and quality", "analyze_business_quality", ["fetch_company_data"]),
                AnalysisTask("analyze_market_position", "Market Position", phase, "Analyze competitive positioning", "analyze_market_position", ["fetch_competitors", "fetch_industry_data"]),
                AnalysisTask("analyze_management", "Management Assessment", phase, "Evaluate management team", "analyze_management", ["fetch_company_data", "fetch_news"]),
            ],
            DealPhase.FINANCIAL: [
                AnalysisTask("analyze_historical_financials", "Historical Analysis", phase, "Analyze historical financial performance", "analyze_historical_financials", ["fetch_company_data"]),
                AnalysisTask("build_projections", "Build Projections", phase, "Create financial projections", "build_projections", ["analyze_historical_financials"]),
                AnalysisTask("analyze_working_capital", "Working Capital", phase, "Analyze NWC and cash conversion", "analyze_working_capital", ["analyze_historical_financials"]),
            ],
            DealPhase.DEAL_STRUCTURE: [
                AnalysisTask("run_valuation", "Valuation", phase, "Run DCF and comps valuation", "run_valuation", ["build_projections"]),
                AnalysisTask("analyze_debt_capacity", "Debt Capacity", phase, "Analyze leverage and debt capacity", "analyze_debt_capacity", ["build_projections"]),
                AnalysisTask("calculate_returns", "Returns Analysis", phase, "Calculate IRR and MOIC", "calculate_returns", ["run_valuation", "analyze_debt_capacity"]),
                AnalysisTask("build_sensitivity", "Sensitivity", phase, "Build sensitivity tables", "build_sensitivity", ["calculate_returns"]),
            ],
            DealPhase.OUTPUT: [
                AnalysisTask("generate_excel_model", "Excel Model", phase, "Generate LBO model", "generate_excel_model", ["calculate_returns"]),
                AnalysisTask("generate_slides", "PowerPoint Deck", phase, "Generate investment slides", "generate_slides", ["analyze_business_quality", "analyze_market_position"]),
                AnalysisTask("generate_research_report", "Research Report", phase, "Generate markdown report", "generate_research_report", ["calculate_returns"]),
            ],
        }

        # Adjust tasks based on timeframe
        if timeframe == "24_hour":
            # Minimal tasks for 24-hour turnaround
            if phase == DealPhase.FOUNDATION:
                return [t for t in phase_tasks[phase] if t.id in ["analyze_business_quality"]]
            elif phase == DealPhase.FINANCIAL:
                return [t for t in phase_tasks[phase] if t.id in ["analyze_historical_financials", "build_projections"]]
            elif phase == DealPhase.DEAL_STRUCTURE:
                return [t for t in phase_tasks[phase] if t.id in ["calculate_returns", "build_sensitivity"]]
            elif phase == DealPhase.OUTPUT:
                return [t for t in phase_tasks[phase] if t.id in ["generate_excel_model"]]

        return phase_tasks.get(phase, [])

    async def run_deal_analysis(
        self,
        company_name: str,
        ticker: str,
        deal_type: str = "lbo",
        timeframe: str = "48_hour",
        resume_from: Optional[str] = None,
    ) -> DealState:
        """
        Run a complete deal analysis.

        Args:
            company_name: Target company name
            ticker: Stock ticker symbol
            deal_type: Type of deal (lbo, growth_equity, add_on, carve_out)
            timeframe: Analysis timeframe (24_hour, 48_hour, 5_day, 7_day_plus)
            resume_from: Optional deal ID to resume from checkpoint

        Returns:
            DealState with all analysis results
        """
        # Initialize or restore state
        if resume_from:
            self.state = await self._restore_state(resume_from)
        else:
            self.state = DealState(
                deal_id=str(uuid.uuid4()),
                company_name=company_name,
                ticker=ticker,
                deal_type=deal_type,
                timeframe=timeframe,
                user_id=self.user_id,
                session_id=self.session_id,
            )

        # Initialize budget enforcer if budgets are available
        if BUDGETS_AVAILABLE:
            budget = self._budget_config or get_budget_for_timeframe(timeframe)
            self._budget_enforcer = BudgetEnforcer(budget)
            self._budget_enforcer.start()
            logger.info(f"Budget profile: {budget.profile} (max_tasks={budget.max_tasks}, max_duration={budget.max_duration_minutes}min)")

        # Call run start hook if progress callback supports it
        if hasattr(self.progress, 'on_deal_start'):
            await self.progress.on_deal_start(
                self.state.deal_id,
                company_name,
                deal_type,
            )

        # Run phases in order
        phases = [
            DealPhase.DATA_COLLECTION,
            DealPhase.FOUNDATION,
            DealPhase.FINANCIAL,
            DealPhase.DEAL_STRUCTURE,
            DealPhase.OUTPUT,
        ]

        try:
            for phase in phases:
                # Check budget before starting phase
                if self._budget_enforcer and not self._budget_enforcer.can_start_task():
                    logger.warning(f"Budget exceeded, stopping before phase: {phase.value}")
                    break

                # Skip completed phases
                if phase.value in self.state.completed_phases:
                    logger.info(f"Skipping completed phase: {phase.value}")
                    continue

                await self._run_phase(phase, deal_type, timeframe)

                # Checkpoint after each phase
                await self._save_checkpoint()

                # Check if we should checkpoint based on budget
                if self._budget_enforcer and self._budget_enforcer.should_checkpoint():
                    await self._save_checkpoint()

        except Exception as e:
            logger.error(f"Deal analysis failed: {e}")
            raise

        finally:
            # Log budget status
            if self._budget_enforcer:
                status = self._budget_enforcer.get_status()
                logger.info(f"Budget status: {status}")

        await self.progress.on_deal_complete(self.state)
        return self.state

    async def _run_phase(self, phase: DealPhase, deal_type: str, timeframe: str):
        """Run all tasks in a phase."""
        tasks = self._get_phase_tasks(phase, deal_type, timeframe)

        if not tasks:
            return

        # Register tasks in state
        for task in tasks:
            self.state.tasks[task.id] = task

        task_names = [t.name for t in tasks]
        await self.progress.on_phase_start(phase, task_names)

        self.state.current_phase = phase

        # Identify parallelizable tasks (no pending dependencies)
        completed_tasks = set()

        while len(completed_tasks) < len(tasks):
            # Find ready tasks
            ready_tasks = [
                t for t in tasks
                if t.id not in completed_tasks
                and t.status != TaskStatus.COMPLETED
                and all(dep in completed_tasks or self.state.tasks.get(dep, AnalysisTask("", "", phase, "", "")).status == TaskStatus.COMPLETED
                        for dep in t.dependencies)
            ]

            if not ready_tasks:
                # Check for failed dependencies
                failed = [t for t in tasks if t.status == TaskStatus.FAILED]
                if failed:
                    logger.error(f"Phase {phase.value} has failed tasks: {[t.id for t in failed]}")
                    break
                await asyncio.sleep(0.1)
                continue

            # Run ready tasks in parallel (up to max)
            batch = ready_tasks[:self.max_parallel_tasks]
            await asyncio.gather(*[self._run_task(task) for task in batch])

            # Update completed set
            for task in batch:
                if task.status == TaskStatus.COMPLETED:
                    completed_tasks.add(task.id)

        # Mark phase complete
        self.state.completed_phases.append(phase.value)
        results = {t.id: t.result for t in tasks if t.status == TaskStatus.COMPLETED}
        await self.progress.on_phase_complete(phase, results)

    async def _run_task(self, task: AnalysisTask):
        """Run a single analysis task."""
        # Check budget before running
        if self._budget_enforcer and not self._budget_enforcer.can_start_task():
            task.status = TaskStatus.SKIPPED
            task.error = "Budget exceeded"
            logger.warning(f"Task {task.id} skipped: budget exceeded")
            return

        task.status = TaskStatus.RUNNING
        task.started_at = datetime.now()
        await self.progress.on_task_start(task)

        try:
            handler = self._task_handlers.get(task.handler)
            if handler:
                task.result = await handler()
            else:
                raise ValueError(f"No handler for task: {task.handler}")

            task.status = TaskStatus.COMPLETED
            task.completed_at = datetime.now()
            task.duration_ms = (task.completed_at - task.started_at).total_seconds() * 1000
            await self.progress.on_task_complete(task)

            # Record successful task in budget
            if self._budget_enforcer:
                self._budget_enforcer.record_task_complete(success=True)

        except Exception as e:
            task.status = TaskStatus.FAILED
            task.error = str(e)
            task.completed_at = datetime.now()
            logger.error(f"Task {task.id} failed: {e}")
            await self.progress.on_task_error(task, str(e))

            # Record failed task in budget
            if self._budget_enforcer:
                self._budget_enforcer.record_task_complete(success=False)

    # =========================================================================
    # PHASE 0: DATA COLLECTION HANDLERS
    # =========================================================================

    async def _fetch_company_data(self) -> Dict:
        """Fetch company financial data."""
        from ii_skills.ib_toolkit.enriched_data import EnrichedDataFetcher

        fetcher = EnrichedDataFetcher()
        company_data = await fetcher.get_company_data(
            self.state.ticker,
            include_news=False,  # Separate task
            include_competitors=False,  # Separate task
        )

        self.state.company_data = company_data.__dict__
        return self.state.company_data

    async def _fetch_news(self) -> List[Dict]:
        """Fetch recent news."""
        try:
            from ii_skills.shared.research import get_research_client

            client = get_research_client()
            results = await client.search(
                f"{self.state.company_name} {self.state.ticker} news",
                max_results=10,
            )

            news = [{"title": r.title, "url": r.url, "snippet": r.snippet} for r in results]
            self.state.research_data["news"] = news
            return news
        except Exception as e:
            logger.warning(f"News fetch failed: {e}")
            return []

    async def _fetch_industry_data(self) -> Dict:
        """Fetch industry data and trends."""
        try:
            from ii_skills.shared.research import get_research_client

            industry = self.state.company_data.get("industry", "")
            if not industry:
                return {}

            client = get_research_client()
            results = await client.search(
                f"{industry} industry trends outlook 2024 2025",
                max_results=5,
            )

            trends = [r.snippet for r in results if r.snippet]
            self.state.research_data["industry_trends"] = trends
            return {"industry": industry, "trends": trends}
        except Exception as e:
            logger.warning(f"Industry data fetch failed: {e}")
            return {}

    async def _fetch_competitors(self) -> List[str]:
        """Identify competitors."""
        try:
            from ii_skills.shared.research import get_research_client

            client = get_research_client()
            results = await client.search(
                f"{self.state.company_name} competitors market share",
                max_results=5,
            )

            competitors = [r.snippet[:100] for r in results if r.snippet]
            self.state.research_data["competitors"] = competitors
            return competitors
        except Exception as e:
            logger.warning(f"Competitor fetch failed: {e}")
            return []

    # =========================================================================
    # PHASE 1: FOUNDATION HANDLERS
    # =========================================================================

    async def _analyze_business_quality(self) -> Dict:
        """Analyze business model and quality."""
        cd = self.state.company_data

        analysis = {
            "sector": cd.get("sector", "Unknown"),
            "industry": cd.get("industry", "Unknown"),
            "description": cd.get("description", "")[:500],
            "revenue_model": "Identified from description",
            "quality_indicators": [],
        }

        # Quality indicators based on margins
        if cd.get("ebitda_margin", 0) > 0.2:
            analysis["quality_indicators"].append("High EBITDA margins (>20%)")
        if cd.get("gross_margin", 0) > 0.4:
            analysis["quality_indicators"].append("Strong gross margins (>40%)")
        if cd.get("revenue_growth_yoy", 0) > 0.1:
            analysis["quality_indicators"].append("Growing revenue (>10% YoY)")

        self.state.financial_analysis["business_quality"] = analysis
        return analysis

    async def _analyze_market_position(self) -> Dict:
        """Analyze competitive positioning."""
        analysis = {
            "competitors": self.state.research_data.get("competitors", []),
            "industry_trends": self.state.research_data.get("industry_trends", []),
            "market_position": "Analysis based on research",
        }

        self.state.financial_analysis["market_position"] = analysis
        return analysis

    async def _analyze_management(self) -> Dict:
        """Evaluate management team."""
        analysis = {
            "news_sentiment": "Based on recent news",
            "news_count": len(self.state.research_data.get("news", [])),
        }

        self.state.financial_analysis["management"] = analysis
        return analysis

    # =========================================================================
    # PHASE 2: FINANCIAL HANDLERS
    # =========================================================================

    async def _analyze_historical_financials(self) -> Dict:
        """Analyze historical financial performance."""
        cd = self.state.company_data

        analysis = {
            "revenue_ttm": cd.get("revenue_ttm", 0),
            "ebitda_ttm": cd.get("ebitda_ttm", 0),
            "ebitda_margin": cd.get("ebitda_margin", 0),
            "net_income_ttm": cd.get("net_income_ttm", 0),
            "free_cash_flow": cd.get("free_cash_flow", 0),
            "revenue_growth": cd.get("revenue_growth_yoy", 0),
        }

        self.state.financial_analysis["historical"] = analysis
        return analysis

    async def _build_projections(self) -> Dict:
        """Build financial projections."""
        hist = self.state.financial_analysis.get("historical", {})

        # Simple projection based on historical growth
        growth_rate = hist.get("revenue_growth", 0.05) or 0.05
        revenue = hist.get("revenue_ttm", 0)
        ebitda_margin = hist.get("ebitda_margin", 0.15) or 0.15

        projections = {
            "years": 5,
            "revenue_growth": growth_rate,
            "ebitda_margin": ebitda_margin,
            "projected_revenue": [revenue * (1 + growth_rate) ** i for i in range(1, 6)],
            "projected_ebitda": [revenue * (1 + growth_rate) ** i * ebitda_margin for i in range(1, 6)],
        }

        self.state.financial_analysis["projections"] = projections
        return projections

    async def _analyze_working_capital(self) -> Dict:
        """Analyze working capital."""
        analysis = {
            "nwc_analysis": "Working capital analysis based on available data",
            "cash_conversion": "Cash conversion cycle estimate",
        }

        self.state.financial_analysis["working_capital"] = analysis
        return analysis

    # =========================================================================
    # PHASE 3: DEAL STRUCTURE HANDLERS
    # =========================================================================

    async def _run_valuation(self) -> Dict:
        """Run valuation analysis."""
        cd = self.state.company_data
        proj = self.state.financial_analysis.get("projections", {})

        valuation = {
            "enterprise_value": cd.get("enterprise_value", 0),
            "ev_ebitda": cd.get("ev_ebitda", 0),
            "ev_revenue": cd.get("ev_revenue", 0),
            "market_cap": cd.get("market_cap", 0),
        }

        # Implied value from projections
        if proj.get("projected_ebitda") and valuation["ev_ebitda"]:
            implied_ev = proj["projected_ebitda"][-1] * valuation["ev_ebitda"]
            valuation["implied_exit_value"] = implied_ev

        self.state.deal_structure["valuation"] = valuation
        return valuation

    async def _analyze_debt_capacity(self) -> Dict:
        """Analyze debt capacity."""
        cd = self.state.company_data
        ebitda = cd.get("ebitda_ttm", 0)

        # Estimate debt capacity based on EBITDA
        max_leverage = 5.0 if cd.get("ebitda_margin", 0) > 0.2 else 4.0

        debt_analysis = {
            "ltm_ebitda": ebitda,
            "max_leverage": max_leverage,
            "max_debt": ebitda * max_leverage if ebitda else 0,
            "current_debt": cd.get("total_debt", 0),
            "current_leverage": cd.get("total_debt", 0) / ebitda if ebitda else 0,
        }

        self.state.deal_structure["debt_capacity"] = debt_analysis
        return debt_analysis

    async def _calculate_returns(self) -> Dict:
        """Calculate IRR and MOIC."""
        valuation = self.state.deal_structure.get("valuation", {})
        debt = self.state.deal_structure.get("debt_capacity", {})
        proj = self.state.financial_analysis.get("projections", {})

        entry_ev = valuation.get("enterprise_value", 0)
        exit_ev = valuation.get("implied_exit_value", entry_ev * 1.5)
        debt_amount = debt.get("max_debt", 0)
        equity_check = entry_ev - debt_amount

        if equity_check > 0:
            exit_equity = exit_ev - debt_amount * 0.5  # Assume 50% debt paydown
            moic = exit_equity / equity_check
            # Simplified IRR calculation
            irr = (moic ** (1/5)) - 1 if moic > 0 else 0
        else:
            moic = 0
            irr = 0

        returns = {
            "entry_ev": entry_ev,
            "exit_ev": exit_ev,
            "equity_check": equity_check,
            "exit_equity": exit_ev - debt_amount * 0.5 if equity_check > 0 else 0,
            "moic": moic,
            "irr": irr,
            "hold_period": 5,
        }

        self.state.deal_structure["returns"] = returns
        return returns

    async def _build_sensitivity(self) -> Dict:
        """Build sensitivity analysis."""
        returns = self.state.deal_structure.get("returns", {})
        base_moic = returns.get("moic", 2.0)

        # Simple sensitivity matrix
        sensitivity = {
            "exit_multiple_sensitivity": {
                "6x": base_moic * 0.75,
                "7x": base_moic * 0.875,
                "8x": base_moic,
                "9x": base_moic * 1.125,
                "10x": base_moic * 1.25,
            },
            "leverage_sensitivity": {
                "3x": base_moic * 0.8,
                "4x": base_moic * 0.9,
                "5x": base_moic,
                "6x": base_moic * 1.1,
            },
        }

        self.state.deal_structure["sensitivity"] = sensitivity
        return sensitivity

    # =========================================================================
    # PHASE 4: OUTPUT HANDLERS
    # =========================================================================

    async def _generate_excel_model(self) -> Dict:
        """Generate LBO Excel model."""
        try:
            from ii_skills.ib_toolkit.storage_integration import IBToolkitStorage

            storage = IBToolkitStorage(
                user_id=self.user_id,
                session_id=self.session_id,
                output_dir=str(self.output_dir),
            )

            # Build assumptions from analysis
            cd = self.state.company_data
            assumptions = {}
            if cd.get("ebitda_ttm"):
                assumptions["ltm_ebitda"] = cd["ebitda_ttm"] / 1e6
            if cd.get("ev_ebitda"):
                assumptions["entry_multiple"] = cd["ev_ebitda"]

            result = await storage.generate_lbo_model(
                company_name=self.state.company_name,
                company_symbol=self.state.ticker,
                timeframe=self.state.timeframe,
                assumptions=assumptions,
            )

            self.state.outputs["excel_model"] = result.get("local_path", "")
            return result

        except Exception as e:
            logger.error(f"Excel generation failed: {e}")
            return {"error": str(e)}

    async def _generate_slides(self) -> Dict:
        """Generate PowerPoint deck."""
        try:
            from ii_skills.ib_toolkit.storage_integration import IBToolkitStorage

            storage = IBToolkitStorage(
                user_id=self.user_id,
                session_id=self.session_id,
                output_dir=str(self.output_dir),
            )

            result = await storage.generate_investment_deck(
                company_name=self.state.company_name,
                company_symbol=self.state.ticker,
                deck_type="standard",
            )

            self.state.outputs["slides"] = result.get("local_path", "")
            return result

        except Exception as e:
            logger.error(f"Slide generation failed: {e}")
            return {"error": str(e)}

    async def _generate_research_report(self) -> Dict:
        """Generate markdown research report."""
        try:
            report_lines = [
                f"# {self.state.company_name} ({self.state.ticker}) - Deal Analysis",
                f"",
                f"**Deal Type:** {self.state.deal_type.upper()}",
                f"**Date:** {datetime.now().strftime('%B %d, %Y')}",
                "",
                "---",
                "",
                "## Executive Summary",
                "",
            ]

            # Add returns summary
            returns = self.state.deal_structure.get("returns", {})
            if returns:
                report_lines.extend([
                    f"- **Entry EV:** ${returns.get('entry_ev', 0)/1e9:.1f}B",
                    f"- **MOIC:** {returns.get('moic', 0):.2f}x",
                    f"- **IRR:** {returns.get('irr', 0):.1%}",
                    "",
                ])

            # Add business quality
            bq = self.state.financial_analysis.get("business_quality", {})
            if bq:
                report_lines.extend([
                    "## Business Quality",
                    "",
                    f"**Sector:** {bq.get('sector', 'N/A')}",
                    f"**Industry:** {bq.get('industry', 'N/A')}",
                    "",
                ])
                for indicator in bq.get("quality_indicators", []):
                    report_lines.append(f"- {indicator}")
                report_lines.append("")

            # Add valuation
            val = self.state.deal_structure.get("valuation", {})
            if val:
                report_lines.extend([
                    "## Valuation",
                    "",
                    f"- EV/EBITDA: {val.get('ev_ebitda', 0):.1f}x",
                    f"- EV/Revenue: {val.get('ev_revenue', 0):.1f}x",
                    "",
                ])

            # Write report
            report_path = self.output_dir / f"{self.state.company_name.replace(' ', '_')}_Analysis.md"
            with open(report_path, "w") as f:
                f.write("\n".join(report_lines))

            self.state.outputs["research_report"] = str(report_path)
            return {"path": str(report_path)}

        except Exception as e:
            logger.error(f"Report generation failed: {e}")
            return {"error": str(e)}

    # =========================================================================
    # STATE MANAGEMENT
    # =========================================================================

    async def _save_checkpoint(self):
        """Save state checkpoint to database or file."""
        try:
            from ii_skills.shared.datastore import get_datastore

            datastore = get_datastore()
            if datastore.is_connected:
                # Update deal in database
                await datastore.update_deal(
                    deal_id=self.state.deal_id,
                    current_phase=self.state.current_phase.value,
                    completed_prompts=self.state.completed_phases,
                    state_data={
                        "company_data": self.state.company_data,
                        "research_data": self.state.research_data,
                        "financial_analysis": self.state.financial_analysis,
                        "deal_structure": self.state.deal_structure,
                        "outputs": self.state.outputs,
                    },
                )
                logger.info(f"Checkpoint saved for deal {self.state.deal_id}")
        except Exception as e:
            logger.warning(f"Failed to save checkpoint: {e}")

    async def _restore_state(self, deal_id: str) -> DealState:
        """Restore state from checkpoint."""
        try:
            from ii_skills.shared.datastore import get_datastore

            datastore = get_datastore()
            if datastore.is_connected:
                deal = await datastore.get_deal(deal_id)
                if deal:
                    state = DealState(
                        deal_id=deal_id,
                        company_name=deal.get("company_name", ""),
                        ticker=deal.get("company_symbol", ""),
                        deal_type=deal.get("deal_type", "lbo"),
                        timeframe="48_hour",
                        current_phase=DealPhase(deal.get("current_phase", "data_collection")),
                        completed_phases=deal.get("completed_prompts", []),
                    )

                    state_data = deal.get("state_data", {})
                    state.company_data = state_data.get("company_data", {})
                    state.research_data = state_data.get("research_data", {})
                    state.financial_analysis = state_data.get("financial_analysis", {})
                    state.deal_structure = state_data.get("deal_structure", {})
                    state.outputs = state_data.get("outputs", {})

                    logger.info(f"Restored state for deal {deal_id}")
                    return state
        except Exception as e:
            logger.warning(f"Failed to restore state: {e}")

        raise ValueError(f"Could not restore deal: {deal_id}")


# Convenience function
async def run_deal_analysis(
    user_id: str,
    company_name: str,
    ticker: str,
    deal_type: str = "lbo",
    timeframe: str = "48_hour",
) -> DealState:
    """Quick function to run deal analysis."""
    orchestrator = DealOrchestrator(user_id=user_id)
    return await orchestrator.run_deal_analysis(
        company_name=company_name,
        ticker=ticker,
        deal_type=deal_type,
        timeframe=timeframe,
    )
