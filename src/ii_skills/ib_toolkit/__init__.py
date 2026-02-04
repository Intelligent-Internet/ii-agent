"""
Investment Banking Toolkit Skill

Professional-grade tools for creating investment banking presentations,
financial models, and deal analysis frameworks.

Capabilities:
- PowerPoint Generation (Company profiles, IC decks, M&A pitch books)
- Excel Financial Models (DCF, LBO, Comps, 3-Statement)
- Orchestrated Deal Analysis (52-prompt system)
- Middle Market Case Study Support

Version: 1.2.0
"""

from typing import Dict, List, Optional
from pathlib import Path

from ii_skills import BaseSkill, register_skill

# Skill metadata
__version__ = "1.2.0"
__author__ = "Claire Agent System"


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
        ]


# Convenience function for direct imports
def get_toolkit(config: Optional[Dict] = None) -> IBToolkitSkill:
    """Get an instance of the IB Toolkit skill."""
    skill = IBToolkitSkill(config)
    skill.initialize()
    return skill
