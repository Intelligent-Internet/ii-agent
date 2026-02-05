"""
Case Workflow Orchestrator — end-to-end case study pipeline.

Chains together:
1. CaseStudyTrigger — create deal folder structure
2. ExcelModelGenerator — generate LBO model with live formulas
3. TerminalModelRenderer — display results in terminal
4. ProgressReporter — real-time progress updates

Usage:
    from ii_skills.shared.case_orchestrator import CaseWorkflowOrchestrator

    orch = CaseWorkflowOrchestrator()
    result = orch.run(
        company_name="Acme Corp",
        case_type="lbo",
        timeframe="24-hour",
        assumptions={"ltm_revenue": 100, "ltm_ebitda": 20, ...},
    )

    # result.deal_folder — path to case folder
    # result.model_path  — path to generated Excel
    # result.terminal_output — rendered text summary
    # result.timeline    — progress timeline
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)


@dataclass
class CaseResult:
    """Result of a full case workflow run."""
    success: bool = True
    company_name: str = ""
    case_type: str = ""
    timeframe: str = ""

    # Outputs
    deal_folder: str = ""
    model_path: str = ""
    terminal_output: str = ""
    timeline: str = ""
    metrics: Dict[str, Any] = field(default_factory=dict)

    # Files produced
    files_created: List[Dict[str, str]] = field(default_factory=list)

    # Errors (non-fatal)
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    @property
    def summary(self) -> str:
        lines = []
        lines.append(f"Case: {self.company_name} ({self.case_type})")
        lines.append(f"Status: {'OK' if self.success else 'FAILED'}")
        if self.deal_folder:
            lines.append(f"Folder: {self.deal_folder}")
        if self.model_path:
            lines.append(f"Model: {self.model_path}")
        if self.metrics:
            for k, v in self.metrics.items():
                lines.append(f"  {k}: {v}")
        if self.files_created:
            lines.append(f"Files: {len(self.files_created)}")
        if self.warnings:
            lines.append(f"Warnings: {len(self.warnings)}")
        if self.errors:
            lines.append(f"Errors: {len(self.errors)}")
            for e in self.errors:
                lines.append(f"  - {e}")
        return "\n".join(lines)


# Timeframe → ModelDepth + sheet set mapping
TIMEFRAME_CONFIG = {
    "24-hour": {
        "depth": "QUICK",
        "sheets": [
            "assumptions", "sources_uses", "operating_model",
            "returns", "sensitivity",
        ],
    },
    "48-hour": {
        "depth": "STANDARD",
        "sheets": [
            "assumptions", "sources_uses", "operating_model",
            "revenue_build", "expense_build", "debt_schedule",
            "working_capital", "wacc", "returns", "sensitivity",
        ],
    },
    "5-day": {
        "depth": "STANDARD",
        "sheets": [
            "assumptions", "sources_uses", "operating_model",
            "revenue_build", "expense_build", "debt_schedule",
            "working_capital", "wacc", "returns", "sensitivity",
            "scenario_analysis", "management_vs_buyer",
            "dcf_valuation", "covenant_analysis",
        ],
    },
    "7-day": {
        "depth": "COMPREHENSIVE",
        "sheets": [
            "assumptions", "sources_uses", "operating_model",
            "revenue_build", "expense_build", "debt_schedule",
            "working_capital", "wacc", "returns", "sensitivity",
            "scenario_analysis", "management_vs_buyer",
            "dcf_valuation", "covenant_analysis",
            "quality_of_earnings",
        ],
    },
}

# Sheet name → ExcelModelGenerator method mapping
SHEET_METHOD_MAP = {
    "assumptions": "add_assumptions_sheet",
    "sources_uses": "add_sources_uses",
    "operating_model": "add_operating_model",
    "revenue_build": "add_revenue_build",
    "expense_build": "add_expense_build",
    "debt_schedule": "add_debt_schedule",
    "working_capital": "add_working_capital",
    "wacc": "add_wacc_analysis",
    "returns": "add_returns_analysis",
    "sensitivity": "add_sensitivity_tables",
    "scenario_analysis": "add_scenario_analysis",
    "management_vs_buyer": "add_management_vs_buyer",
    "dcf_valuation": "add_dcf_valuation",
    "covenant_analysis": "add_covenant_analysis",
    "quality_of_earnings": "add_quality_of_earnings",
}


class CaseWorkflowOrchestrator:
    """
    End-to-end case study pipeline.

    Orchestrates folder creation, model generation, terminal rendering,
    and progress reporting into a single run() call.
    """

    def __init__(
        self,
        base_dir: str = "output/cases",
        quiet: bool = False,
        use_color: bool = True,
    ):
        self.base_dir = base_dir
        self.quiet = quiet
        self.use_color = use_color

    def run(
        self,
        company_name: str,
        case_type: str = "lbo",
        timeframe: str = "24-hour",
        assumptions: Optional[Dict[str, Any]] = None,
        cim_path: Optional[str] = None,
        model_path: Optional[str] = None,
        additional_files: Optional[Dict[str, str]] = None,
        data: Optional[Dict[str, Any]] = None,
    ) -> CaseResult:
        """
        Execute the full case workflow.

        Args:
            company_name: Target company name.
            case_type: Deal type (lbo, growth_equity, add_on, carve_out).
            timeframe: Analysis depth (24-hour, 48-hour, 5-day, 7-day).
            assumptions: Override model assumptions dict.
            cim_path: Path to CIM PDF to copy into deal folder.
            model_path: Path to existing model to copy.
            additional_files: Extra files {filename: path} to place.
            data: Extra data to pass to sheet generators.

        Returns:
            CaseResult with all outputs and paths.
        """
        # Lazy imports to avoid circular deps and keep module light
        from ii_skills.shared.case_trigger import CaseStudyTrigger
        from ii_skills.shared.progress import ProgressReporter
        from ii_skills.shared.terminal_renderer import (
            TerminalModelRenderer, render_from_assumptions,
        )
        from ii_skills.ib_toolkit.templates.excel_models.excel_modules import (
            ExcelModelGenerator, ModelDepth, ModelAssumptions,
        )

        result = CaseResult(
            company_name=company_name,
            case_type=case_type,
            timeframe=timeframe,
        )

        # Resolve timeframe config
        config = TIMEFRAME_CONFIG.get(timeframe, TIMEFRAME_CONFIG["24-hour"])
        depth_str = config["depth"]
        sheet_list = config["sheets"]

        # Count phases: folder + model + render + (optional CIM)
        total_phases = 3
        progress = ProgressReporter(
            total_phases=total_phases,
            case_name=f"{company_name} {case_type.upper()}",
            quiet=self.quiet,
        )
        progress.case_start()

        # ── PHASE 1: Create Deal Folder ──
        progress.phase_start("Create Deal Folder")
        try:
            trigger = CaseStudyTrigger(base_dir=self.base_dir)
            setup = trigger.start_case(
                company_name=company_name,
                case_type=case_type,
                cim_path=cim_path,
                model_path=model_path,
                additional_files=additional_files,
                timeframe=timeframe,
            )
            result.deal_folder = setup.deal_folder
            result.files_created.extend(setup.files_copied)
            if setup.errors:
                result.warnings.extend(setup.errors)
            progress.phase_complete("Create Deal Folder", {
                "folder": setup.deal_folder,
                "subfolders": len(setup.subfolders),
            })
        except Exception as exc:
            result.errors.append(f"Folder creation failed: {exc}")
            progress.error(f"Folder creation failed: {exc}")
            progress.phase_complete("Create Deal Folder")

        # ── PHASE 2: Generate LBO Model ──
        progress.phase_start("Generate LBO Model")
        try:
            # Build ModelAssumptions from dict
            depth = getattr(ModelDepth, depth_str, ModelDepth.QUICK)
            model_assumptions = ModelAssumptions(company_name=company_name)

            if assumptions:
                for key, val in assumptions.items():
                    if hasattr(model_assumptions, key):
                        setattr(model_assumptions, key, val)

            gen = ExcelModelGenerator(
                company_name=company_name,
                depth=depth,
                assumptions=model_assumptions,
            )

            # Generate each sheet in order
            sheets_generated = []
            for sheet_key in sheet_list:
                method_name = SHEET_METHOD_MAP.get(sheet_key)
                if method_name and hasattr(gen, method_name):
                    try:
                        method = getattr(gen, method_name)
                        if data:
                            method(data=data)
                        else:
                            method()
                        sheets_generated.append(sheet_key)
                    except Exception as sheet_exc:
                        result.warnings.append(
                            f"Sheet '{sheet_key}' failed: {sheet_exc}"
                        )

            # Save workbook
            if result.deal_folder:
                models_dir = Path(result.deal_folder) / "02_models"
                if not models_dir.exists():
                    models_dir.mkdir(parents=True, exist_ok=True)
                safe_name = company_name.lower().replace(" ", "_")
                wb_path = str(models_dir / f"{safe_name}_lbo_model.xlsx")
            else:
                # Fallback if folder creation failed
                safe_name = company_name.lower().replace(" ", "_")
                wb_path = f"{safe_name}_lbo_model.xlsx"

            gen.save(wb_path)
            result.model_path = wb_path
            result.files_created.append({
                "filename": Path(wb_path).name,
                "destination": wb_path,
                "subfolder": "02_models",
            })

            progress.metric("Sheets", str(len(sheets_generated)))
            progress.metric("Depth", depth_str)
            progress.file_created(wb_path, "LBO Model")
            progress.phase_complete("Generate LBO Model", {
                "sheets": len(sheets_generated),
                "depth": depth_str,
            })

        except Exception as exc:
            result.errors.append(f"Model generation failed: {exc}")
            progress.error(f"Model generation failed: {exc}")
            progress.phase_complete("Generate LBO Model")

        # ── PHASE 3: Terminal Render ──
        progress.phase_start("Render Terminal Output")
        try:
            # Build assumptions dict for render_from_assumptions
            render_assumptions = {"company_name": company_name}
            if assumptions:
                render_assumptions.update(assumptions)
            else:
                # Use defaults from ModelAssumptions
                render_assumptions.update({
                    "ltm_revenue": model_assumptions.ltm_revenue,
                    "ltm_ebitda": model_assumptions.ltm_ebitda,
                    "entry_multiple": model_assumptions.entry_multiple,
                    "exit_multiple": model_assumptions.exit_multiple,
                    "hold_period": model_assumptions.hold_period,
                    "senior_debt_multiple": model_assumptions.senior_debt_multiple,
                    "senior_interest_rate": model_assumptions.senior_interest_rate,
                    "senior_amortization": model_assumptions.senior_amortization,
                    "sub_debt_multiple": model_assumptions.sub_debt_multiple,
                    "sub_interest_rate": model_assumptions.sub_interest_rate,
                    "transaction_fee_pct": model_assumptions.transaction_fee_pct,
                    "financing_fee_pct": model_assumptions.financing_fee_pct,
                    "revenue_growth": list(model_assumptions.revenue_growth),
                    "ebitda_margin": list(model_assumptions.ebitda_margin),
                })

            terminal_text = render_from_assumptions(render_assumptions)
            result.terminal_output = terminal_text

            # Extract key metrics for the result
            renderer = TerminalModelRenderer(use_color=False)
            from ii_skills.shared.terminal_renderer import (
                ModelMetrics, _compute_sources_uses, _compute_projections,
                _compute_debt_schedule, _compute_returns,
            )
            m = ModelMetrics()
            for k, v in render_assumptions.items():
                if hasattr(m, k):
                    setattr(m, k, v)
            _compute_sources_uses(m)
            _compute_projections(m)
            _compute_debt_schedule(m)
            _compute_returns(m)

            result.metrics = {
                "Entry EV": f"${m.entry_ev:.1f}M",
                "Equity Check": f"${m.equity_invested:.1f}M",
                "MOIC": f"{m.moic:.2f}x",
                "IRR": f"{m.irr * 100:.1f}%",
                "Exit EV": f"${m.exit_ev:.1f}M",
            }

            for label, val in result.metrics.items():
                progress.metric(label, val)

            progress.phase_complete("Render Terminal Output")

        except Exception as exc:
            result.errors.append(f"Terminal render failed: {exc}")
            progress.error(f"Terminal render failed: {exc}")
            progress.phase_complete("Render Terminal Output")

        # ── Finalize ──
        progress.case_complete(result.metrics)
        result.timeline = progress.get_timeline()

        if result.errors:
            result.success = all(
                "failed" not in e.lower() for e in result.errors
                if "Model generation" in e or "Folder creation" in e
            )

        return result
