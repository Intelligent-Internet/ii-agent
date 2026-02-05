"""
IR Toolkit Orchestrator

Multi-phase orchestration for infrastructure investor relations analysis.
Follows the same patterns as DealOrchestrator but focused on IR use cases.

Phases:
- Phase 1: Data Collection (fund data, asset KPIs, benchmarks)
- Phase 2: Analysis (performance, cash flows, valuation, risk)
- Phase 3: Excel Generation (module outputs)
- Phase 4: Slide Generation (paired slides)
- Phase 5: QA & Packaging (consistency checks, final output)

Usage:
    from ii_skills.ir_toolkit.ir_orchestrator import IRToolkit, IRCaseType

    toolkit = IRToolkit(user_id="user123")
    result = await toolkit.run_ir_case(
        case_type=IRCaseType.LP_UPDATE,
        fund_name="Global Infra Fund IV",
        reporting_period="Q4 2025",
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


class IRCaseType(Enum):
    """Types of IR cases."""
    LP_UPDATE = "lp_update"
    FUNDRAISING = "fundraising"
    DDQ_RESPONSE = "ddq_response"
    ANNUAL_MEETING = "annual_meeting"
    CRISIS_COMMS = "crisis_comms"
    CUSTOM = "custom"


class IRPhase(Enum):
    """IR analysis phases."""
    DATA_COLLECTION = "data_collection"
    ANALYSIS = "analysis"
    EXCEL_GENERATION = "excel_generation"
    SLIDE_GENERATION = "slide_generation"
    QA_PACKAGING = "qa_packaging"


class IRTaskStatus(Enum):
    """Task execution status."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class IRModule:
    """Represents an IR analysis module."""
    id: str
    name: str
    category: str
    excel_output: str
    slide_output: str
    description: str
    infra_nuance: str
    dependencies: List[str] = field(default_factory=list)
    status: IRTaskStatus = IRTaskStatus.PENDING
    result: Any = None
    error: Optional[str] = None


@dataclass
class IRState:
    """State for IR case analysis."""
    case_id: str
    case_type: IRCaseType
    fund_name: str
    reporting_period: str

    # Phase tracking
    current_phase: IRPhase = IRPhase.DATA_COLLECTION
    completed_phases: List[str] = field(default_factory=list)

    # Module tracking
    modules: Dict[str, IRModule] = field(default_factory=dict)
    module_phases: Dict[str, List[str]] = field(default_factory=dict)  # module_id -> completed phases

    # Data
    fund_data: Dict = field(default_factory=dict)
    asset_data: Dict = field(default_factory=dict)
    performance_data: Dict = field(default_factory=dict)
    cash_flow_data: Dict = field(default_factory=dict)
    valuation_data: Dict = field(default_factory=dict)
    risk_data: Dict = field(default_factory=dict)

    # Outputs
    excel_outputs: Dict[str, str] = field(default_factory=dict)
    slide_outputs: Dict[str, str] = field(default_factory=dict)
    final_outputs: Dict[str, str] = field(default_factory=dict)

    # Metadata
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    user_id: Optional[str] = None

    # Phase 1: Ontology & Evidence (opt-in)
    ontology_tags: Dict[str, List[Dict]] = field(default_factory=dict)
    evidence_tracker_data: Optional[Dict] = None
    evidence_qa_results: Optional[Dict] = None


class IRProgressCallback:
    """Callback interface for progress updates."""

    async def on_phase_start(self, phase: IRPhase, modules: List[str]):
        """Called when a phase starts."""
        pass

    async def on_module_start(self, module: IRModule):
        """Called when a module starts."""
        pass

    async def on_module_complete(self, module: IRModule):
        """Called when a module completes."""
        pass

    async def on_module_error(self, module: IRModule, error: str):
        """Called when a module fails."""
        pass

    async def on_phase_complete(self, phase: IRPhase, results: Dict):
        """Called when a phase completes."""
        pass

    async def on_case_complete(self, state: IRState):
        """Called when IR case analysis completes."""
        pass


class ConsoleIRProgressCallback(IRProgressCallback):
    """Progress callback that prints to console."""

    async def on_phase_start(self, phase: IRPhase, modules: List[str]):
        print(f"\n{'='*60}")
        print(f"Phase: {phase.value.upper()}")
        print(f"Modules: {', '.join(modules)}")
        print(f"{'='*60}")

    async def on_module_start(self, module: IRModule):
        print(f"  [STARTED] {module.name}")

    async def on_module_complete(self, module: IRModule):
        print(f"  [DONE] {module.name}")

    async def on_module_error(self, module: IRModule, error: str):
        print(f"  [ERROR] {module.name}: {error}")

    async def on_phase_complete(self, phase: IRPhase, results: Dict):
        print(f"\nPhase {phase.value} complete. Results: {len(results)} modules")

    async def on_case_complete(self, state: IRState):
        print(f"\n{'='*60}")
        print(f"IR Case Complete: {state.fund_name}")
        print(f"Outputs: Excel={len(state.excel_outputs)}, Slides={len(state.slide_outputs)}")
        print(f"{'='*60}")


# Module definitions by case type
LP_UPDATE_MODULES = [
    IRModule("performance_summary", "Performance Summary", "Fund Overview",
             "Performance_Table.xlsx", "Performance_Slide.pptx",
             "Fund IRR, DPI, RVPI, TVPI", "Highlight cash yield stability"),
    IRModule("cash_flow_waterfall", "Cash Flow Waterfall", "Cash Flows",
             "CashFlow_Table.xlsx", "CashFlow_Slide.pptx",
             "Calls, distributions, net cash flow", "Infra-specific yield"),
    IRModule("asset_kpi_dashboard", "Asset KPI Dashboard", "Asset Performance",
             "AssetKPI_Table.xlsx", "AssetKPI_Slide.pptx",
             "Availability, utilization, uptime", "Contracted capacity"),
    IRModule("nav_rollforward", "NAV Roll-forward", "Valuation",
             "NAV_Table.xlsx", "NAV_Slide.pptx",
             "Period NAV with drivers", "Discount rate sensitivity"),
    IRModule("leverage_coverage", "Leverage & Coverage", "Risk",
             "Leverage_Table.xlsx", "Leverage_Slide.pptx",
             "Debt/EBITDA, DSCR", "Covenant headroom"),
    IRModule("risk_register", "Risk Register", "Risk",
             "Risk_Table.xlsx", "Risk_Slide.pptx",
             "Top risks with mitigation", "Regulatory, counterparty"),
]

FUNDRAISING_MODULES = LP_UPDATE_MODULES + [
    IRModule("fund_snapshot", "Fund Snapshot", "Fund Overview",
             "FundSnapshot_Table.xlsx", "FundOverview_Slide.pptx",
             "Fund size, strategy, vintage", "Regulatory regimes"),
    IRModule("portfolio_composition", "Portfolio Composition", "Fund Overview",
             "PortfolioMix_Table.xlsx", "PortfolioMix_Slide.pptx",
             "Sector, region, stage mix", "Regulated vs contracted"),
    IRModule("track_record", "Track Record", "Fund Overview",
             "TrackRecord_Table.xlsx", "TrackRecord_Slide.pptx",
             "Historical returns by fund", "Cash yield history"),
    IRModule("term_sheet", "Term Sheet", "Terms",
             "TermSheet_Table.xlsx", "TermSheet_Slide.pptx",
             "Fees, carry, hurdle, governance", "Infra protections"),
    IRModule("esg_metrics", "ESG Metrics", "ESG",
             "ESG_Table.xlsx", "ESG_Slide.pptx",
             "Emissions, safety, community", "Grid reliability"),
    IRModule("fundraising_pipeline", "Fundraising Pipeline", "Fundraising",
             "Pipeline_Table.xlsx", "Pipeline_Slide.pptx",
             "LP funnel by stage", "Region segmentation"),
]

DDQ_MODULES = [
    IRModule("ddq_tracker", "DDQ Tracker", "DDQ",
             "DDQ_Tracker.xlsx", "DDQ_Slide.pptx",
             "Questions, owners, status", "Time-to-response"),
    IRModule("risk_register", "Risk Register", "Risk",
             "Risk_Table.xlsx", "Risk_Slide.pptx",
             "Top risks with mitigation", "Regulatory, counterparty"),
    IRModule("esg_metrics", "ESG Metrics", "ESG",
             "ESG_Table.xlsx", "ESG_Slide.pptx",
             "Emissions, safety, community", "Grid reliability"),
]


class IRToolkit:
    """
    Orchestrates IR case analysis with Excel ↔ Slide pairing.

    Coordinates multi-phase analysis for LP updates, fundraising,
    DDQ responses, and other IR deliverables.
    """

    def __init__(
        self,
        user_id: str,
        output_dir: Optional[str] = None,
        progress_callback: Optional[IRProgressCallback] = None,
        enable_ontology: bool = False,
        enable_evidence: bool = False,
    ):
        """
        Initialize the IR toolkit.

        Args:
            user_id: User ID for tracking
            output_dir: Output directory for generated files
            progress_callback: Callback for progress updates
            enable_ontology: Enable ontology tagging (Phase 1)
            enable_evidence: Enable claim-evidence tracking (Phase 1)
        """
        self.user_id = user_id
        self.output_dir = Path(output_dir) if output_dir else Path(__file__).parent / "outputs"
        self.progress = progress_callback or ConsoleIRProgressCallback()

        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.state: Optional[IRState] = None

        # Phase 1: Ontology & Evidence (opt-in)
        self._ontology_tagger = None
        self._evidence_tracker = None

        if enable_ontology:
            try:
                from ii_skills.ir_toolkit.ontology import OntologyTagger
                self._ontology_tagger = OntologyTagger()
            except ImportError:
                logger.warning("Ontology module not available, skipping ontology tagging")

        if enable_evidence:
            try:
                from ii_skills.ir_toolkit.evidence import ClaimEvidenceTracker
                self._evidence_tracker = ClaimEvidenceTracker()
            except ImportError:
                logger.warning("Evidence module not available, skipping evidence tracking")

    def _get_modules_for_case(self, case_type: IRCaseType) -> List[IRModule]:
        """Get modules based on case type."""
        module_map = {
            IRCaseType.LP_UPDATE: LP_UPDATE_MODULES,
            IRCaseType.FUNDRAISING: FUNDRAISING_MODULES,
            IRCaseType.DDQ_RESPONSE: DDQ_MODULES,
            IRCaseType.ANNUAL_MEETING: FUNDRAISING_MODULES,  # Similar to fundraising
            IRCaseType.CRISIS_COMMS: LP_UPDATE_MODULES[:4],  # Quick subset
        }
        return [IRModule(**m.__dict__) for m in module_map.get(case_type, LP_UPDATE_MODULES)]

    async def run_ir_case(
        self,
        case_type: IRCaseType,
        fund_name: str,
        reporting_period: str,
        fund_data: Optional[Dict] = None,
        asset_data: Optional[Dict] = None,
        custom_modules: Optional[List[str]] = None,
    ) -> IRState:
        """
        Run a complete IR case analysis.

        Args:
            case_type: Type of IR case
            fund_name: Name of the fund
            reporting_period: Reporting period (e.g., "Q4 2025")
            fund_data: Optional fund data dictionary
            asset_data: Optional asset data dictionary
            custom_modules: Optional list of specific modules to run

        Returns:
            IRState with all analysis results
        """
        # Initialize state
        self.state = IRState(
            case_id=str(uuid.uuid4()),
            case_type=case_type,
            fund_name=fund_name,
            reporting_period=reporting_period,
            user_id=self.user_id,
        )

        if fund_data:
            self.state.fund_data = fund_data
        if asset_data:
            self.state.asset_data = asset_data

        # Get modules for this case type
        modules = self._get_modules_for_case(case_type)
        if custom_modules:
            modules = [m for m in modules if m.id in custom_modules]

        for module in modules:
            self.state.modules[module.id] = module

        # Run phases
        phases = [
            IRPhase.DATA_COLLECTION,
            IRPhase.ANALYSIS,
            IRPhase.EXCEL_GENERATION,
            IRPhase.SLIDE_GENERATION,
            IRPhase.QA_PACKAGING,
        ]

        for phase in phases:
            if phase.value in self.state.completed_phases:
                continue
            await self._run_phase(phase)

        await self.progress.on_case_complete(self.state)
        return self.state

    async def _run_phase(self, phase: IRPhase):
        """Run all modules in a phase."""
        self.state.current_phase = phase
        modules = list(self.state.modules.values())
        module_names = [m.name for m in modules]

        await self.progress.on_phase_start(phase, module_names)

        for module in modules:
            # Check if this module already completed this phase
            module_completed_phases = self.state.module_phases.get(module.id, [])
            if phase.value in module_completed_phases:
                continue

            await self._run_module(module, phase)

        self.state.completed_phases.append(phase.value)
        results = {m.id: m.result for m in modules}
        await self.progress.on_phase_complete(phase, results)

    async def _run_module(self, module: IRModule, phase: IRPhase):
        """Run a single module."""
        module.status = IRTaskStatus.RUNNING
        await self.progress.on_module_start(module)

        try:
            if phase == IRPhase.DATA_COLLECTION:
                module.result = await self._collect_data(module)
            elif phase == IRPhase.ANALYSIS:
                module.result = await self._run_analysis(module)
            elif phase == IRPhase.EXCEL_GENERATION:
                module.result = await self._generate_excel(module)
            elif phase == IRPhase.SLIDE_GENERATION:
                module.result = await self._generate_slide(module)
            elif phase == IRPhase.QA_PACKAGING:
                module.result = await self._run_qa(module)

            # Track phase completion for this module
            if module.id not in self.state.module_phases:
                self.state.module_phases[module.id] = []
            self.state.module_phases[module.id].append(phase.value)

            # Only mark fully completed after QA phase
            if phase == IRPhase.QA_PACKAGING:
                module.status = IRTaskStatus.COMPLETED
            else:
                module.status = IRTaskStatus.PENDING  # Ready for next phase

            await self.progress.on_module_complete(module)

        except Exception as e:
            module.status = IRTaskStatus.FAILED
            module.error = str(e)
            logger.error(f"Module {module.id} failed: {e}")
            await self.progress.on_module_error(module, str(e))

    async def _collect_data(self, module: IRModule) -> Dict:
        """Collect data for a module."""
        # Placeholder - would integrate with data sources
        return {
            "module_id": module.id,
            "data_collected": True,
            "timestamp": datetime.now().isoformat(),
        }

    async def _run_analysis(self, module: IRModule) -> Dict:
        """Run analysis for a module."""
        # Placeholder - would run actual analysis
        result = {
            "module_id": module.id,
            "analysis_complete": True,
            "infra_nuance": module.infra_nuance,
        }

        # Phase 1: Ontology tagging (opt-in)
        if self._ontology_tagger and self.state:
            tagged_elements = []
            # Tag module description and infra_nuance
            tagged_elements.append(
                self._ontology_tagger.tag_text(module.description, element_id=f"{module.id}.description")
            )
            tagged_elements.append(
                self._ontology_tagger.tag_text(module.infra_nuance, element_id=f"{module.id}.infra_nuance")
            )
            # Tag relevant state data
            if self.state.fund_data:
                tagged_elements.extend(
                    self._ontology_tagger.tag_data_dict(self.state.fund_data, prefix=f"{module.id}.fund")
                )
            if self.state.asset_data:
                tagged_elements.extend(
                    self._ontology_tagger.tag_data_dict(self.state.asset_data, prefix=f"{module.id}.asset")
                )
            # Store tagged elements (only those with tags)
            self.state.ontology_tags[module.id] = [
                e.to_dict() for e in tagged_elements if e.tags
            ]

        return result

    async def _generate_excel(self, module: IRModule) -> Dict:
        """Generate Excel output for a module."""
        try:
            from ii_skills.ir_toolkit.excel_generator import IRExcelGenerator

            generator = IRExcelGenerator(self.output_dir)
            excel_path = await generator.generate_module_excel(
                module, self.state
            )
            self.state.excel_outputs[module.id] = excel_path
            return {"excel_path": excel_path}
        except ImportError:
            # Fallback if generator not available
            return {"excel_path": None, "note": "Excel generator not available"}

    async def _generate_slide(self, module: IRModule) -> Dict:
        """Generate slide output for a module."""
        try:
            from ii_skills.ir_toolkit.pptx_generator import IRSlideGenerator

            generator = IRSlideGenerator(self.output_dir)
            slide_path = await generator.generate_module_slide(
                module, self.state
            )
            self.state.slide_outputs[module.id] = slide_path
            return {"slide_path": slide_path}
        except ImportError:
            # Fallback if generator not available
            return {"slide_path": None, "note": "Slide generator not available"}

    async def _run_qa(self, module: IRModule) -> Dict:
        """Run QA checks for a module."""
        # Check Excel ↔ Slide consistency
        excel_exists = module.id in self.state.excel_outputs
        slide_exists = module.id in self.state.slide_outputs

        result = {
            "module_id": module.id,
            "excel_exists": excel_exists,
            "slide_exists": slide_exists,
            "paired": excel_exists and slide_exists,
            "qa_passed": excel_exists and slide_exists,
        }

        # Phase 1: Ontology jargon QA (opt-in)
        if self._ontology_tagger and self.state:
            stored_tags = self.state.ontology_tags.get(module.id, [])
            if stored_tags:
                try:
                    from ii_skills.ir_toolkit.ontology import (
                        check_jargon_consistency, TaggedElement, SemanticTag,
                    )
                    # Reconstruct TaggedElements from stored dicts
                    elements = []
                    for td in stored_tags:
                        elem = TaggedElement(
                            element_id=td["element_id"],
                            element_type=td["element_type"],
                            content=td["content"],
                            tags=[SemanticTag(**t) for t in td.get("tags", [])],
                        )
                        elements.append(elem)
                    jargon_result = check_jargon_consistency(elements)
                    result["jargon_qa"] = {
                        "passed": jargon_result.passed,
                        "undefined_jargon": jargon_result.undefined_jargon_count,
                        "inconsistent_usage": jargon_result.inconsistent_usage_count,
                    }
                except ImportError:
                    pass

        # Phase 1: Evidence QA (opt-in, runs once on last module)
        if self._evidence_tracker and self.state:
            # Run evidence validation on the last QA module
            modules = list(self.state.modules.values())
            if module.id == modules[-1].id:
                report = self._evidence_tracker.validate(
                    current_period=self.state.reporting_period
                )
                self.state.evidence_tracker_data = self._evidence_tracker.to_dict()
                self.state.evidence_qa_results = {
                    "passed": report.passed,
                    "total_claims": report.total_claims,
                    "cited_claims": report.cited_claims,
                    "uncited_claims": report.uncited_claims,
                    "evidence_coverage_ratio": report.evidence_coverage_ratio,
                    "low_confidence_claim_count": report.low_confidence_claim_count,
                    "stale_evidence_count": report.stale_evidence_count,
                    "rule_results": [
                        {
                            "rule": r.rule,
                            "enforcement": r.enforcement,
                            "passed": r.passed,
                            "metric_name": r.metric_name,
                            "metric_value": r.metric_value,
                        }
                        for r in report.rule_results
                    ],
                }

        return result

    # Convenience methods for common case types
    async def generate_lp_update(
        self,
        fund_name: str,
        reporting_period: str,
        **kwargs,
    ) -> IRState:
        """Generate LP quarterly update."""
        return await self.run_ir_case(
            case_type=IRCaseType.LP_UPDATE,
            fund_name=fund_name,
            reporting_period=reporting_period,
            **kwargs,
        )

    async def generate_fundraising_deck(
        self,
        fund_name: str,
        **kwargs,
    ) -> IRState:
        """Generate fundraising deck."""
        return await self.run_ir_case(
            case_type=IRCaseType.FUNDRAISING,
            fund_name=fund_name,
            reporting_period="Current",
            **kwargs,
        )

    async def generate_ddq_response(
        self,
        fund_name: str,
        **kwargs,
    ) -> IRState:
        """Generate DDQ response pack."""
        return await self.run_ir_case(
            case_type=IRCaseType.DDQ_RESPONSE,
            fund_name=fund_name,
            reporting_period="Current",
            **kwargs,
        )
