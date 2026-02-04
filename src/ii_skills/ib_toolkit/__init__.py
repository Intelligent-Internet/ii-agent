"""
Investment Banking Toolkit Skill

Professional-grade tools for creating investment banking presentations,
financial models, and deal analysis frameworks.

Capabilities:
- PowerPoint Generation (Company profiles, IC decks, M&A pitch books)
- Excel Financial Models (DCF, LBO, Comps, 3-Statement)
- Orchestrated Deal Analysis (52-prompt system)
- Middle Market Case Study Support
- LBO Quick Calculator (IRR/MOIC analysis, sensitivity)
- Capital Structure Analyzer (debt capacity, optimal financing)
- Quality of Earnings Analyzer (EBITDA normalization, due diligence)

Version: 1.3.0
"""

from typing import Dict, List, Optional
from pathlib import Path

from ii_skills import BaseSkill, register_skill

# Skill metadata
__version__ = "1.3.0"
__author__ = "II-Agent System"


@register_skill
class IBToolkitSkill(BaseSkill):
    """Investment Banking Toolkit skill for ii-agent."""

    name = "ib_toolkit"
    version = __version__
    description = "Investment banking presentations, Excel models, and deal analysis"

    # Paths relative to this module
    SKILL_DIR = Path(__file__).parent
    OUTPUT_DIR = SKILL_DIR / "output"
    TEMPLATES_DIR = SKILL_DIR / "templates"
    MODULES_DIR = SKILL_DIR / "modules"

    def __init__(self, config: Optional[Dict] = None):
        super().__init__(config)
        self.OUTPUT_DIR.mkdir(exist_ok=True)

    def validate_config(self) -> List[str]:
        """Validate configuration. Most features work without API keys."""
        issues = []
        # Yahoo Finance doesn't require API key
        # Optional: FMP, Alpha Vantage for enhanced data
        return issues

    def get_capabilities(self) -> List[str]:
        """Return list of skill capabilities."""
        return [
            "create_company_deck",
            "create_industry_deck",
            "create_ic_presentation",
            "create_dcf_model",
            "create_lbo_model",
            "create_comps_model",
            "create_three_statement_model",
            "fetch_company_data",
            "run_case_intake",
            "execute_analysis_module",
            # New PE-informed capabilities
            "quick_lbo_analysis",
            "lbo_sensitivity",
            "analyze_capital_structure",
            "analyze_quality_of_earnings",
            "generate_dd_questions",
        ]

    def execute(self, action: str, **kwargs) -> Dict:
        """Execute an IB toolkit action."""

        if action == "create_company_deck":
            return self._create_company_deck(**kwargs)
        elif action == "create_dcf_model":
            return self._create_dcf_model(**kwargs)
        elif action == "create_lbo_model":
            return self._create_lbo_model(**kwargs)
        elif action == "fetch_company_data":
            return self._fetch_company_data(**kwargs)
        elif action == "run_case_intake":
            return self._run_case_intake(**kwargs)
        elif action == "execute_analysis_module":
            return self._execute_module(**kwargs)
        # New PE-informed actions
        elif action == "quick_lbo_analysis":
            return self._quick_lbo_analysis(**kwargs)
        elif action == "lbo_sensitivity":
            return self._lbo_sensitivity(**kwargs)
        elif action == "analyze_capital_structure":
            return self._analyze_capital_structure(**kwargs)
        elif action == "analyze_quality_of_earnings":
            return self._analyze_qoe(**kwargs)
        elif action == "generate_dd_questions":
            return self._generate_dd_questions(**kwargs)
        else:
            raise NotImplementedError(f"Action '{action}' not implemented")

    def _create_company_deck(
        self,
        ticker: str,
        comp_tickers: Optional[List[str]] = None,
        output_name: Optional[str] = None,
    ) -> Dict:
        """Create a company profile deck with live data."""
        from .pptx_generator import create_company_deck

        output_path = create_company_deck(
            ticker,
            comp_tickers=comp_tickers or [],
            output_dir=str(self.OUTPUT_DIR),
            output_name=output_name,
        )
        return {"success": True, "output_path": output_path}

    def _create_dcf_model(
        self,
        company_name: str,
        wacc: float = 0.10,
        terminal_growth: float = 0.025,
        projection_years: int = 5,
    ) -> Dict:
        """Create a DCF valuation model."""
        from .excel_models import create_dcf_model

        output_path = create_dcf_model(
            company_name,
            wacc=wacc,
            terminal_growth=terminal_growth,
            projection_years=projection_years,
            output_dir=str(self.OUTPUT_DIR),
        )
        return {"success": True, "output_path": output_path}

    def _create_lbo_model(
        self,
        company_name: str,
        entry_multiple: float = 8.0,
        exit_multiple: float = 8.0,
        hold_period: int = 5,
    ) -> Dict:
        """Create an LBO model."""
        from .excel_models import create_lbo_model

        output_path = create_lbo_model(
            company_name,
            entry_multiple=entry_multiple,
            exit_multiple=exit_multiple,
            hold_period=hold_period,
            output_dir=str(self.OUTPUT_DIR),
        )
        return {"success": True, "output_path": output_path}

    def _fetch_company_data(self, ticker: str) -> Dict:
        """Fetch company financial data."""
        from .data_fetcher import get_company_data

        data = get_company_data(ticker)
        return {"success": True, "data": data}

    def _run_case_intake(
        self,
        company_name: str,
        deal_type: str,
        materials_summary: Optional[str] = None,
    ) -> Dict:
        """Run the case intake protocol for middle market analysis."""
        # Returns structured intake template
        return {
            "success": True,
            "case_type": "pending_identification",
            "company": company_name,
            "deal_type": deal_type,
            "next_steps": [
                "Identify case type (A-F)",
                "Inventory materials",
                "Select analysis modules",
                "Create time budget",
            ],
            "modules_available": self._get_available_modules(),
        }

    def _execute_module(self, module_id: str, **kwargs) -> Dict:
        """Execute a specific analysis module."""
        modules = self._get_available_modules()
        if module_id not in [m["id"] for m in modules]:
            return {"success": False, "error": f"Module {module_id} not found"}

        # Module execution would load the markdown template and return structured output
        module_path = self.MODULES_DIR / f"{module_id}.md"
        if module_path.exists():
            return {
                "success": True,
                "module_id": module_id,
                "template_path": str(module_path),
                "status": "ready_for_execution",
            }
        return {"success": False, "error": f"Module file not found: {module_id}"}

    def _quick_lbo_analysis(
        self,
        ebitda: float,
        entry_multiple: float = 8.0,
        exit_multiple: float = 8.0,
        leverage: float = 4.0,
        hold_years: int = 5,
        ebitda_growth: float = 0.08,
    ) -> Dict:
        """Run quick LBO returns analysis."""
        from .lbo_calculator import quick_lbo, generate_lbo_summary, LBOAssumptions

        # Quick analysis
        result = quick_lbo(
            ebitda=ebitda,
            entry_multiple=entry_multiple,
            exit_multiple=exit_multiple,
            leverage=leverage,
            hold_years=hold_years,
            ebitda_growth=ebitda_growth,
        )

        # Full summary
        assumptions = LBOAssumptions(
            entry_ebitda=ebitda,
            entry_multiple=entry_multiple,
            senior_debt_multiple=min(leverage * 0.75, 4.0),
            sub_debt_multiple=max(0, leverage - min(leverage * 0.75, 4.0)),
            ebitda_growth_rate=ebitda_growth,
            exit_multiple=exit_multiple,
            hold_period=hold_years,
        )
        summary = generate_lbo_summary(assumptions)

        return {
            "success": True,
            "moic": result["moic"],
            "irr": result["irr"],
            "value_creation": result["value_creation"],
            "summary_report": summary,
        }

    def _lbo_sensitivity(
        self,
        ebitda: float,
        entry_multiple: float = 8.0,
        exit_multiples: Optional[List[float]] = None,
        leverage_levels: Optional[List[float]] = None,
    ) -> Dict:
        """Generate LBO sensitivity matrices."""
        from .lbo_calculator import build_sensitivity_matrix, LBOAssumptions

        if exit_multiples is None:
            exit_multiples = [6.0, 7.0, 8.0, 9.0, 10.0]
        if leverage_levels is None:
            leverage_levels = [3.0, 4.0, 5.0, 6.0]

        base = LBOAssumptions(
            entry_ebitda=ebitda,
            entry_multiple=entry_multiple,
        )

        # Entry vs Exit multiple sensitivity
        entry_exit_matrix = build_sensitivity_matrix(
            base,
            row_param="entry_multiple",
            row_values=[entry_multiple - 1, entry_multiple, entry_multiple + 1],
            col_param="exit_multiple",
            col_values=exit_multiples,
            output_metric="moic",
        )

        return {
            "success": True,
            "entry_exit_sensitivity": entry_exit_matrix,
        }

    def _analyze_capital_structure(
        self,
        ebitda: float,
        revenue: float,
        capex: float,
        industry: str = "industrials",
        existing_debt: float = 0,
        revenue_volatility: str = "moderate",
    ) -> Dict:
        """Analyze debt capacity and optimal capital structure."""
        from .capital_structure import (
            CompanyFinancials, Industry, calculate_debt_capacity,
            generate_structure_report
        )

        # Map industry string to enum
        industry_map = {
            "technology": Industry.TECHNOLOGY,
            "healthcare": Industry.HEALTHCARE,
            "industrials": Industry.INDUSTRIALS,
            "consumer": Industry.CONSUMER,
            "business_services": Industry.BUSINESS_SERVICES,
            "financial_services": Industry.FINANCIAL_SERVICES,
            "real_estate": Industry.REAL_ESTATE,
            "energy": Industry.ENERGY,
            "retail": Industry.RETAIL,
            "media": Industry.MEDIA,
        }

        company = CompanyFinancials(
            ebitda=ebitda,
            revenue=revenue,
            capex=capex,
            existing_debt=existing_debt,
            industry=industry_map.get(industry.lower(), Industry.INDUSTRIALS),
            revenue_volatility=revenue_volatility,
        )

        result = calculate_debt_capacity(company)
        report = generate_structure_report(company)

        return {
            "success": True,
            "max_debt_capacity": result.max_total_debt,
            "max_leverage": result.debt_to_ebitda,
            "interest_coverage": result.interest_coverage,
            "recommended_structure": result.recommended_structure,
            "risk_assessment": result.risk_assessment,
            "report": report,
        }

    def _analyze_qoe(
        self,
        revenue: float,
        reported_ebitda: float,
        adjustments: Optional[List[Dict]] = None,
        company_name: str = "Target",
        period: str = "LTM",
    ) -> Dict:
        """Analyze quality of earnings and EBITDA adjustments."""
        from .qoe_analyzer import (
            QoEAnalysis, EBITDAAdjustment, AdjustmentCategory,
            AdjustmentRisk, generate_qoe_report
        )

        # Build adjustment list
        adj_list = []
        if adjustments:
            for adj in adjustments:
                adj_list.append(EBITDAAdjustment(
                    description=adj.get("description", "Adjustment"),
                    amount=adj.get("amount", 0),
                    category=AdjustmentCategory[adj.get("category", "ONE_TIME").upper()],
                    risk=AdjustmentRisk[adj.get("risk", "MODERATE").upper()],
                    notes=adj.get("notes", ""),
                ))

        analysis = QoEAnalysis(
            company_name=company_name,
            period=period,
            reported_revenue=revenue,
            reported_ebitda=reported_ebitda,
            adjustments=adj_list,
        )

        report = generate_qoe_report(analysis)

        return {
            "success": True,
            "reported_ebitda": reported_ebitda,
            "adjusted_ebitda": analysis.adjusted_ebitda(),
            "buyer_adjusted_ebitda": analysis.buyer_adjusted_ebitda(),
            "total_adjustments": sum(a.amount for a in adj_list),
            "high_risk_adjustments": analysis.high_risk_adjustments(),
            "report": report,
        }

    def _generate_dd_questions(
        self,
        adjustments: Optional[List[Dict]] = None,
    ) -> Dict:
        """Generate due diligence questions based on adjustments."""
        from .qoe_analyzer import (
            EBITDAAdjustment, AdjustmentCategory, AdjustmentRisk,
            generate_due_diligence_questions
        )

        adj_list = []
        if adjustments:
            for adj in adjustments:
                adj_list.append(EBITDAAdjustment(
                    description=adj.get("description", "Adjustment"),
                    amount=adj.get("amount", 0),
                    category=AdjustmentCategory[adj.get("category", "ONE_TIME").upper()],
                    risk=AdjustmentRisk[adj.get("risk", "MODERATE").upper()],
                ))

        questions = generate_due_diligence_questions(adj_list)

        return {
            "success": True,
            "questions": questions,
        }

    def _get_available_modules(self) -> List[Dict]:
        """Get list of available analysis modules."""
        return [
            {"id": "M1", "name": "Business Quality Assessment", "phase": "Foundation"},
            {"id": "M2", "name": "Market & Competitive Position", "phase": "Foundation"},
            {"id": "M3", "name": "Management & Operational Assessment", "phase": "Foundation"},
            {"id": "M4", "name": "Historical Financial Analysis", "phase": "Financial"},
            {"id": "M5", "name": "Projection Build / Validation", "phase": "Financial"},
            {"id": "M6", "name": "Working Capital & Cash Conversion", "phase": "Financial"},
            {"id": "M7", "name": "Valuation (Comps / DCF / LBO)", "phase": "Financial"},
            {"id": "M8", "name": "Deal Structure & Sources/Uses", "phase": "Deal"},
            {"id": "M9", "name": "Debt Capacity & Financing", "phase": "Deal"},
            {"id": "M10", "name": "Returns Analysis & Sensitivity", "phase": "Deal"},
            {"id": "M11", "name": "Value Creation Levers", "phase": "Deal"},
            {"id": "M12", "name": "Investment Recommendation", "phase": "Output"},
            {"id": "M13", "name": "Risk Assessment & Mitigants", "phase": "Output"},
            {"id": "M14", "name": "Due Diligence Questions", "phase": "Output"},
            # New PE-informed modules
            {"id": "M15", "name": "LBO Quick Calculator", "phase": "Quick Analysis"},
            {"id": "M16", "name": "Capital Structure Analysis", "phase": "Quick Analysis"},
            {"id": "M17", "name": "Quality of Earnings Analysis", "phase": "Due Diligence"},
        ]


# Convenience function for direct imports
def get_toolkit(config: Optional[Dict] = None) -> IBToolkitSkill:
    """Get an instance of the IB Toolkit skill."""
    skill = IBToolkitSkill(config)
    skill.initialize()
    return skill
