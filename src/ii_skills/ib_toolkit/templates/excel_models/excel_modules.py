#!/usr/bin/env python3
"""
Modular Excel Financial Model Generator

Creates individual model components that can be combined based on:
- Time available (24hr, 48hr, 7-day case)
- Analysis depth required
- Specific module requests

Based on PE textbook frameworks (Pignataro, Rosenbaum & Pearl, Zeisberger)
"""

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Border, Side, Alignment, NamedStyle
from openpyxl.utils import get_column_letter
from openpyxl.chart import LineChart, BarChart, Reference
from openpyxl.formatting.rule import DataBarRule
from datetime import datetime
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any, Tuple
from enum import Enum
import os

# ============================================================
# STYLE CONSTANTS (Goldman Sachs / Institutional Standards)
# ============================================================

# Colors
INPUT_FILL = PatternFill(start_color="FFF3CD", end_color="FFF3CD", fill_type="solid")  # Light yellow
CALC_FILL = PatternFill(start_color="FFFFFF", end_color="FFFFFF", fill_type="solid")   # White
HEADER_FILL = PatternFill(start_color="00365B", end_color="00365B", fill_type="solid") # Navy
SUBTOTAL_FILL = PatternFill(start_color="E8E8E8", end_color="E8E8E8", fill_type="solid")
TOTAL_FILL = PatternFill(start_color="D0D0D0", end_color="D0D0D0", fill_type="solid")

# Fonts
INPUT_FONT = Font(color="0000FF", bold=False)      # Blue for inputs
CALC_FONT = Font(color="000000", bold=False)       # Black for formulas
HEADER_FONT = Font(color="FFFFFF", bold=True)      # White on navy
TITLE_FONT = Font(size=14, bold=True)
SECTION_FONT = Font(size=11, bold=True)

# Borders
THIN_BORDER = Border(
    left=Side(style='thin'),
    right=Side(style='thin'),
    top=Side(style='thin'),
    bottom=Side(style='thin')
)
BOTTOM_BORDER = Border(bottom=Side(style='thin'))
DOUBLE_BORDER = Border(bottom=Side(style='double'))


class ModelDepth(Enum):
    """Model complexity levels based on time available."""
    QUICK = "quick"           # 24-48 hours - essentials only
    STANDARD = "standard"     # 3-5 days - detailed analysis
    COMPREHENSIVE = "comprehensive"  # 7+ days - full institutional


# ============================================================
# MODEL MODULE REGISTRY
# ============================================================

MODEL_MODULES = {
    # Core Financial Modules
    "revenue_build": {
        "name": "Revenue Build",
        "description": "Revenue by segment/product with growth assumptions",
        "quick_version": "Top-line with growth rate",
        "standard_version": "Segment breakdown with drivers",
        "comprehensive_version": "Unit economics, cohorts, customer-level",
        "function": "add_revenue_build"
    },
    "expense_build": {
        "name": "Expense / SG&A Build",
        "description": "Cost structure breakdown (COGS, SG&A components)",
        "quick_version": "% of revenue assumptions",
        "standard_version": "Line-item breakdown",
        "comprehensive_version": "Headcount model, vendor analysis",
        "function": "add_expense_build"
    },
    "operating_model": {
        "name": "Operating Model",
        "description": "Income statement through EBITDA with projections",
        "quick_version": "Revenue → EBITDA (5 lines)",
        "standard_version": "Full P&L with margins",
        "comprehensive_version": "Segment P&Ls, detailed bridge",
        "function": "add_operating_model"
    },

    # Debt & Capital Structure
    "debt_schedule": {
        "name": "Debt Schedule",
        "description": "Debt tranches, amortization, interest, cash sweep",
        "quick_version": "Single tranche, simple paydown",
        "standard_version": "Multi-tranche with mandatory amort",
        "comprehensive_version": "Cash sweep, revolver, PIK, covenants",
        "function": "add_debt_schedule"
    },
    "wacc_calculation": {
        "name": "WACC Calculation",
        "description": "Cost of capital with component breakdown",
        "quick_version": "Simple WACC assumption",
        "standard_version": "CAPM with beta, debt cost",
        "comprehensive_version": "Unlevering/relevering, size premium",
        "function": "add_wacc_calculation"
    },

    # Working Capital
    "working_capital": {
        "name": "Working Capital Analysis",
        "description": "NWC components, days calculations, cash conversion",
        "quick_version": "NWC as % of revenue",
        "standard_version": "AR/AP/Inventory days",
        "comprehensive_version": "Seasonal patterns, normalization",
        "function": "add_working_capital"
    },

    # Transaction / LBO
    "sources_uses": {
        "name": "Sources & Uses",
        "description": "Transaction funding structure",
        "quick_version": "Simple S&U table",
        "standard_version": "Detailed with fees breakdown",
        "comprehensive_version": "Multiple scenarios, rollover equity",
        "function": "add_sources_uses"
    },
    "returns_analysis": {
        "name": "Returns Analysis",
        "description": "MOIC, IRR, value creation attribution",
        "quick_version": "MOIC and IRR calculation",
        "standard_version": "Exit year sensitivity, value bridge",
        "comprehensive_version": "Full attribution, management vs. buyer",
        "function": "add_returns_analysis"
    },
    "sensitivity_tables": {
        "name": "Sensitivity Analysis",
        "description": "2-way sensitivity matrices",
        "quick_version": "Entry/exit multiple matrix",
        "standard_version": "Multiple matrices (growth, margin)",
        "comprehensive_version": "Monte Carlo, tornado chart data",
        "function": "add_sensitivity_tables"
    },

    # Valuation
    "dcf_model": {
        "name": "DCF Valuation",
        "description": "Discounted cash flow analysis",
        "quick_version": "Terminal value + 5-year DCF",
        "standard_version": "Full FCF build, sensitivity",
        "comprehensive_version": "Multiple terminal methods, scenarios",
        "function": "add_dcf_model"
    },
    "trading_comps": {
        "name": "Trading Comps",
        "description": "Public comparable companies analysis",
        "quick_version": "5 comps with key multiples",
        "standard_version": "10+ comps with full metrics",
        "comprehensive_version": "Regression analysis, adjustments",
        "function": "add_trading_comps"
    },
    "transaction_comps": {
        "name": "Transaction Comps",
        "description": "Precedent transactions analysis",
        "quick_version": "5 deals with multiples",
        "standard_version": "10+ deals with context",
        "comprehensive_version": "Control premium analysis",
        "function": "add_transaction_comps"
    },

    # Advanced Modules
    "three_statement": {
        "name": "3-Statement Model",
        "description": "Linked IS, BS, CF statements",
        "quick_version": "Not recommended for quick cases",
        "standard_version": "Simplified linked statements",
        "comprehensive_version": "Full circular model",
        "function": "add_three_statement"
    },
    "covenant_analysis": {
        "name": "Covenant Analysis",
        "description": "Debt covenant compliance tracking",
        "quick_version": "Simple leverage test",
        "standard_version": "Leverage + coverage tests",
        "comprehensive_version": "Full covenant package, headroom",
        "function": "add_covenant_analysis"
    },
    "synergy_model": {
        "name": "Synergy Model",
        "description": "Revenue and cost synergy quantification",
        "quick_version": "High-level synergy estimate",
        "standard_version": "Phased synergy build",
        "comprehensive_version": "Bottom-up with implementation costs",
        "function": "add_synergy_model"
    },
}


# ============================================================
# TIME-BASED MODULE RECOMMENDATIONS
# ============================================================

CASE_FRAMEWORKS = {
    "24_hour": {
        "name": "24-Hour Sprint Case",
        "description": "Essential analysis only - focus on key decision drivers",
        "required_modules": [
            "sources_uses",
            "operating_model",  # Quick version
            "returns_analysis",
        ],
        "optional_modules": [
            "sensitivity_tables",  # Entry/exit only
        ],
        "depth": ModelDepth.QUICK,
        "tips": [
            "Use management projections directly if provided",
            "Simple debt structure (single tranche)",
            "Focus on MOIC/IRR, not detailed attribution",
            "One sensitivity table maximum",
        ]
    },
    "48_hour": {
        "name": "48-Hour Standard Case",
        "description": "Solid analysis with key supporting detail",
        "required_modules": [
            "sources_uses",
            "operating_model",
            "debt_schedule",
            "returns_analysis",
            "sensitivity_tables",
        ],
        "optional_modules": [
            "revenue_build",
            "working_capital",
            "dcf_model",
        ],
        "depth": ModelDepth.QUICK,
        "tips": [
            "Challenge 1-2 management assumptions",
            "Multi-tranche debt if relevant",
            "2-3 sensitivity matrices",
            "Simple value creation bridge",
        ]
    },
    "5_day": {
        "name": "5-Day Detailed Case",
        "description": "Comprehensive analysis with supporting detail",
        "required_modules": [
            "sources_uses",
            "revenue_build",
            "expense_build",
            "operating_model",
            "debt_schedule",
            "working_capital",
            "returns_analysis",
            "sensitivity_tables",
        ],
        "optional_modules": [
            "dcf_model",
            "trading_comps",
            "covenant_analysis",
            "wacc_calculation",
        ],
        "depth": ModelDepth.STANDARD,
        "tips": [
            "Build revenue from segment drivers",
            "Detailed SG&A breakdown",
            "Cash sweep mechanics",
            "Multiple scenarios (base/upside/downside)",
            "Full value creation attribution",
        ]
    },
    "7_day_plus": {
        "name": "7+ Day Institutional Case",
        "description": "Full institutional-quality model",
        "required_modules": [
            "sources_uses",
            "revenue_build",
            "expense_build",
            "operating_model",
            "debt_schedule",
            "working_capital",
            "wacc_calculation",
            "returns_analysis",
            "sensitivity_tables",
            "dcf_model",
            "trading_comps",
            "transaction_comps",
            "covenant_analysis",
        ],
        "optional_modules": [
            "three_statement",
            "synergy_model",
        ],
        "depth": ModelDepth.COMPREHENSIVE,
        "tips": [
            "Unit economics and cohort analysis",
            "Headcount-driven SG&A model",
            "Complex debt with revolver, PIK",
            "Management case vs. buyer case comparison",
            "Full covenant analysis with headroom",
            "Monte Carlo or scenario probability weighting",
        ]
    },
}


@dataclass
class ModelAssumptions:
    """Container for model assumptions."""
    # Company info
    company_name: str = "Target Company"
    fiscal_year_end: str = "December"

    # Historical
    ltm_revenue: float = 100.0
    ltm_ebitda: float = 20.0
    ltm_capex: float = 5.0

    # Growth assumptions
    revenue_growth: List[float] = field(default_factory=lambda: [0.08, 0.07, 0.06, 0.05, 0.05])
    ebitda_margin: List[float] = field(default_factory=lambda: [0.20, 0.21, 0.22, 0.22, 0.22])
    capex_pct_revenue: float = 0.05
    nwc_pct_revenue: float = 0.10

    # Transaction
    entry_multiple: float = 8.0
    exit_multiple: float = 8.0
    hold_period: int = 5

    # Debt structure
    senior_debt_multiple: float = 4.0
    senior_interest_rate: float = 0.08
    senior_amortization: float = 0.01  # 1% per year
    sub_debt_multiple: float = 1.5
    sub_interest_rate: float = 0.12

    # WACC inputs
    risk_free_rate: float = 0.04
    equity_risk_premium: float = 0.06
    beta: float = 1.0
    size_premium: float = 0.02
    cost_of_debt: float = 0.08
    tax_rate: float = 0.25
    target_debt_equity: float = 0.50


class ExcelModelGenerator:
    """
    Modular Excel model generator.

    Example:
        gen = ExcelModelGenerator("Acme Corp", depth=ModelDepth.STANDARD)
        gen.add_sources_uses()
        gen.add_operating_model()
        gen.add_debt_schedule()
        gen.add_returns_analysis()
        gen.save("acme_model.xlsx")
    """

    def __init__(self, company_name: str = "Target Company",
                 depth: ModelDepth = ModelDepth.STANDARD,
                 assumptions: ModelAssumptions = None):
        """Initialize the Excel model generator."""
        self.wb = Workbook()
        self.company_name = company_name
        self.depth = depth
        self.assumptions = assumptions or ModelAssumptions(company_name=company_name)
        self.projection_years = self.assumptions.hold_period

        # Remove default sheet
        self.wb.remove(self.wb.active)

        # Track created sheets
        self.sheets_created = []

    def _format_header_row(self, ws, row: int, start_col: int, end_col: int):
        """Apply header formatting to a row."""
        for col in range(start_col, end_col + 1):
            cell = ws.cell(row=row, column=col)
            cell.fill = HEADER_FILL
            cell.font = HEADER_FONT
            cell.alignment = Alignment(horizontal='center')

    def _format_input_cell(self, ws, row: int, col: int):
        """Format a cell as an input."""
        cell = ws.cell(row=row, column=col)
        cell.fill = INPUT_FILL
        cell.font = INPUT_FONT

    def _add_title(self, ws, title: str, row: int = 1, col: int = 1):
        """Add a section title."""
        cell = ws.cell(row=row, column=col, value=title)
        cell.font = TITLE_FONT

    def _add_section_header(self, ws, title: str, row: int, col: int = 1):
        """Add a section header."""
        cell = ws.cell(row=row, column=col, value=title)
        cell.font = SECTION_FONT

    def _year_headers(self, ws, start_row: int, start_col: int):
        """Add year column headers."""
        headers = ["LTM"] + [f"Year {i}" for i in range(1, self.projection_years + 1)]
        for i, header in enumerate(headers):
            cell = ws.cell(row=start_row, column=start_col + i, value=header)
            cell.font = Font(bold=True)
            cell.alignment = Alignment(horizontal='center')

    # ============================================================
    # MODULE: SOURCES & USES
    # ============================================================

    def add_sources_uses(self, data: Dict = None) -> 'ExcelModelGenerator':
        """Add Sources & Uses sheet."""
        ws = self.wb.create_sheet("Sources & Uses")
        self.sheets_created.append("Sources & Uses")

        a = self.assumptions

        # Calculate transaction values
        ev = a.ltm_ebitda * a.entry_multiple
        senior_debt = a.ltm_ebitda * a.senior_debt_multiple
        sub_debt = a.ltm_ebitda * a.sub_debt_multiple
        total_debt = senior_debt + sub_debt

        # Fees (typical estimates)
        transaction_fees = ev * 0.015  # 1.5% of EV
        financing_fees = total_debt * 0.025  # 2.5% of debt

        equity_check = ev + transaction_fees + financing_fees - total_debt

        # Title
        self._add_title(ws, f"{self.company_name} - Sources & Uses", 1, 1)

        # Sources section
        self._add_section_header(ws, "Sources", 3, 1)
        ws.cell(row=3, column=2, value="$M")
        ws.cell(row=3, column=3, value="% of Total")
        self._format_header_row(ws, 3, 1, 3)

        sources = [
            ("Senior Secured Debt", senior_debt),
            ("Subordinated Debt", sub_debt),
            ("Sponsor Equity", equity_check),
        ]

        total_sources = sum(s[1] for s in sources)

        for i, (name, amount) in enumerate(sources):
            row = 4 + i
            ws.cell(row=row, column=1, value=name)
            ws.cell(row=row, column=2, value=amount)
            self._format_input_cell(ws, row, 2)
            ws.cell(row=row, column=3, value=amount / total_sources)
            ws.cell(row=row, column=3).number_format = '0.0%'

        # Total sources
        total_row = 4 + len(sources)
        ws.cell(row=total_row, column=1, value="Total Sources")
        ws.cell(row=total_row, column=2, value=total_sources)
        ws.cell(row=total_row, column=3, value=1.0)
        ws.cell(row=total_row, column=3).number_format = '0.0%'
        for col in range(1, 4):
            ws.cell(row=total_row, column=col).font = Font(bold=True)
            ws.cell(row=total_row, column=col).border = DOUBLE_BORDER

        # Uses section
        uses_start = total_row + 2
        self._add_section_header(ws, "Uses", uses_start, 1)
        ws.cell(row=uses_start, column=2, value="$M")
        ws.cell(row=uses_start, column=3, value="% of Total")
        self._format_header_row(ws, uses_start, 1, 3)

        uses = [
            ("Purchase Enterprise Value", ev),
            ("Transaction Fees", transaction_fees),
            ("Financing Fees", financing_fees),
        ]

        total_uses = sum(u[1] for u in uses)

        for i, (name, amount) in enumerate(uses):
            row = uses_start + 1 + i
            ws.cell(row=row, column=1, value=name)
            ws.cell(row=row, column=2, value=amount)
            ws.cell(row=row, column=3, value=amount / total_uses)
            ws.cell(row=row, column=3).number_format = '0.0%'

        # Total uses
        uses_total_row = uses_start + 1 + len(uses)
        ws.cell(row=uses_total_row, column=1, value="Total Uses")
        ws.cell(row=uses_total_row, column=2, value=total_uses)
        ws.cell(row=uses_total_row, column=3, value=1.0)
        ws.cell(row=uses_total_row, column=3).number_format = '0.0%'
        for col in range(1, 4):
            ws.cell(row=uses_total_row, column=col).font = Font(bold=True)
            ws.cell(row=uses_total_row, column=col).border = DOUBLE_BORDER

        # Key metrics
        metrics_start = uses_total_row + 2
        self._add_section_header(ws, "Key Metrics", metrics_start, 1)

        metrics = [
            ("Entry EV / EBITDA", f"{a.entry_multiple:.1f}x"),
            ("Total Debt / EBITDA", f"{(senior_debt + sub_debt) / a.ltm_ebitda:.1f}x"),
            ("Senior Debt / EBITDA", f"{senior_debt / a.ltm_ebitda:.1f}x"),
            ("Equity Check", f"${equity_check:.1f}M"),
            ("Equity / EV", f"{equity_check / ev:.1%}"),
        ]

        for i, (name, value) in enumerate(metrics):
            row = metrics_start + 1 + i
            ws.cell(row=row, column=1, value=name)
            ws.cell(row=row, column=2, value=value)

        # Set column widths
        ws.column_dimensions['A'].width = 25
        ws.column_dimensions['B'].width = 15
        ws.column_dimensions['C'].width = 12

        return self

    # ============================================================
    # MODULE: OPERATING MODEL
    # ============================================================

    def add_operating_model(self, data: Dict = None) -> 'ExcelModelGenerator':
        """Add Operating Model sheet."""
        ws = self.wb.create_sheet("Operating Model")
        self.sheets_created.append("Operating Model")

        a = self.assumptions

        # Title
        self._add_title(ws, f"{self.company_name} - Operating Model", 1, 1)

        # Year headers
        self._year_headers(ws, 3, 2)

        # Assumptions section
        self._add_section_header(ws, "Assumptions", 4, 1)

        # Revenue growth
        ws.cell(row=5, column=1, value="Revenue Growth %")
        ws.cell(row=5, column=2, value="—")
        for i, growth in enumerate(a.revenue_growth):
            cell = ws.cell(row=5, column=3 + i, value=growth)
            cell.number_format = '0.0%'
            self._format_input_cell(ws, 5, 3 + i)

        # EBITDA margin
        ws.cell(row=6, column=1, value="EBITDA Margin %")
        for i, margin in enumerate([a.ltm_ebitda / a.ltm_revenue] + list(a.ebitda_margin)):
            cell = ws.cell(row=6, column=2 + i, value=margin)
            cell.number_format = '0.0%'
            if i > 0:
                self._format_input_cell(ws, 6, 2 + i)

        # CapEx % of revenue
        ws.cell(row=7, column=1, value="CapEx % Revenue")
        for i in range(self.projection_years + 1):
            cell = ws.cell(row=7, column=2 + i, value=a.capex_pct_revenue)
            cell.number_format = '0.0%'
            self._format_input_cell(ws, 7, 2 + i)

        # Operating Model
        self._add_section_header(ws, "Operating Model ($M)", 9, 1)

        # Calculate projections
        revenues = [a.ltm_revenue]
        for growth in a.revenue_growth:
            revenues.append(revenues[-1] * (1 + growth))

        ebitdas = [a.ltm_ebitda]
        margins = [a.ltm_ebitda / a.ltm_revenue] + list(a.ebitda_margin)
        for i, margin in enumerate(margins[1:], 1):
            ebitdas.append(revenues[i] * margin)

        capex = [rev * a.capex_pct_revenue for rev in revenues]

        # Revenue row
        ws.cell(row=10, column=1, value="Revenue")
        for i, rev in enumerate(revenues):
            ws.cell(row=10, column=2 + i, value=rev)
            ws.cell(row=10, column=2 + i).number_format = '#,##0.0'

        # Growth % row
        ws.cell(row=11, column=1, value="  % Growth")
        ws.cell(row=11, column=2, value="—")
        for i in range(len(revenues) - 1):
            growth = (revenues[i + 1] / revenues[i]) - 1
            cell = ws.cell(row=11, column=3 + i, value=growth)
            cell.number_format = '0.0%'
            cell.font = Font(italic=True, color="666666")

        # EBITDA row
        ws.cell(row=13, column=1, value="EBITDA")
        for i, ebitda in enumerate(ebitdas):
            ws.cell(row=13, column=2 + i, value=ebitda)
            ws.cell(row=13, column=2 + i).number_format = '#,##0.0'

        # Margin % row
        ws.cell(row=14, column=1, value="  % Margin")
        for i in range(len(ebitdas)):
            margin = ebitdas[i] / revenues[i]
            cell = ws.cell(row=14, column=2 + i, value=margin)
            cell.number_format = '0.0%'
            cell.font = Font(italic=True, color="666666")

        # CapEx row
        ws.cell(row=16, column=1, value="CapEx")
        for i, cx in enumerate(capex):
            ws.cell(row=16, column=2 + i, value=-cx)
            ws.cell(row=16, column=2 + i).number_format = '(#,##0.0)'

        # D&A (assume = CapEx for simplicity)
        ws.cell(row=17, column=1, value="D&A")
        for i, cx in enumerate(capex):
            ws.cell(row=17, column=2 + i, value=cx)
            ws.cell(row=17, column=2 + i).number_format = '#,##0.0'

        # EBITDA - CapEx
        ws.cell(row=19, column=1, value="EBITDA - CapEx")
        for i in range(len(ebitdas)):
            val = ebitdas[i] - capex[i]
            ws.cell(row=19, column=2 + i, value=val)
            ws.cell(row=19, column=2 + i).number_format = '#,##0.0'
            ws.cell(row=19, column=2 + i).font = Font(bold=True)

        # Set column widths
        ws.column_dimensions['A'].width = 20
        for i in range(self.projection_years + 2):
            ws.column_dimensions[get_column_letter(2 + i)].width = 12

        return self

    # ============================================================
    # MODULE: REVENUE BUILD
    # ============================================================

    def add_revenue_build(self, data: Dict = None) -> 'ExcelModelGenerator':
        """Add detailed Revenue Build sheet."""
        ws = self.wb.create_sheet("Revenue Build")
        self.sheets_created.append("Revenue Build")

        a = self.assumptions

        # Title
        self._add_title(ws, f"{self.company_name} - Revenue Build", 1, 1)

        # Year headers
        self._year_headers(ws, 3, 2)

        if self.depth == ModelDepth.QUICK:
            # Simple: Just total revenue with growth
            self._add_section_header(ws, "Revenue Projections ($M)", 4, 1)

            revenues = [a.ltm_revenue]
            for growth in a.revenue_growth:
                revenues.append(revenues[-1] * (1 + growth))

            ws.cell(row=5, column=1, value="Total Revenue")
            for i, rev in enumerate(revenues):
                ws.cell(row=5, column=2 + i, value=rev)
                ws.cell(row=5, column=2 + i).number_format = '#,##0.0'

            ws.cell(row=6, column=1, value="  % Growth")
            ws.cell(row=6, column=2, value="—")
            for i, growth in enumerate(a.revenue_growth):
                cell = ws.cell(row=6, column=3 + i, value=growth)
                cell.number_format = '0.0%'
                self._format_input_cell(ws, 6, 3 + i)

        else:
            # Standard/Comprehensive: Segment breakdown
            data = data or {}
            segments = data.get('segments', [
                {"name": "Segment A", "pct": 0.50, "growth": [0.10, 0.09, 0.08, 0.07, 0.06]},
                {"name": "Segment B", "pct": 0.30, "growth": [0.06, 0.05, 0.05, 0.04, 0.04]},
                {"name": "Segment C", "pct": 0.20, "growth": [0.04, 0.03, 0.03, 0.02, 0.02]},
            ])

            # Segment assumptions
            self._add_section_header(ws, "Segment Assumptions", 4, 1)
            ws.cell(row=5, column=1, value="Segment")
            ws.cell(row=5, column=2, value="LTM %")
            for i in range(self.projection_years):
                ws.cell(row=5, column=3 + i, value=f"Y{i+1} Growth")
            self._format_header_row(ws, 5, 1, 2 + self.projection_years)

            for j, seg in enumerate(segments):
                row = 6 + j
                ws.cell(row=row, column=1, value=seg["name"])
                ws.cell(row=row, column=2, value=seg["pct"])
                ws.cell(row=row, column=2).number_format = '0.0%'
                self._format_input_cell(ws, row, 2)

                for i, g in enumerate(seg["growth"]):
                    cell = ws.cell(row=row, column=3 + i, value=g)
                    cell.number_format = '0.0%'
                    self._format_input_cell(ws, row, 3 + i)

            # Revenue by segment
            seg_start = 6 + len(segments) + 1
            self._add_section_header(ws, "Revenue by Segment ($M)", seg_start, 1)

            for j, seg in enumerate(segments):
                row = seg_start + 1 + j
                ws.cell(row=row, column=1, value=seg["name"])

                seg_rev = [a.ltm_revenue * seg["pct"]]
                for g in seg["growth"]:
                    seg_rev.append(seg_rev[-1] * (1 + g))

                for i, rev in enumerate(seg_rev):
                    ws.cell(row=row, column=2 + i, value=rev)
                    ws.cell(row=row, column=2 + i).number_format = '#,##0.0'

            # Total revenue
            total_row = seg_start + 1 + len(segments)
            ws.cell(row=total_row, column=1, value="Total Revenue")

            for i in range(self.projection_years + 1):
                # Sum formula
                start_row = seg_start + 1
                end_row = total_row - 1
                col_letter = get_column_letter(2 + i)
                ws.cell(row=total_row, column=2 + i,
                       value=f"=SUM({col_letter}{start_row}:{col_letter}{end_row})")
                ws.cell(row=total_row, column=2 + i).number_format = '#,##0.0'
                ws.cell(row=total_row, column=2 + i).font = Font(bold=True)
                ws.cell(row=total_row, column=2 + i).border = DOUBLE_BORDER

        # Set column widths
        ws.column_dimensions['A'].width = 20
        for i in range(self.projection_years + 2):
            ws.column_dimensions[get_column_letter(2 + i)].width = 12

        return self

    # ============================================================
    # MODULE: EXPENSE BUILD (SG&A BREAKOUT)
    # ============================================================

    def add_expense_build(self, data: Dict = None) -> 'ExcelModelGenerator':
        """Add Expense / SG&A Build sheet."""
        ws = self.wb.create_sheet("Expense Build")
        self.sheets_created.append("Expense Build")

        a = self.assumptions

        # Calculate revenues for reference
        revenues = [a.ltm_revenue]
        for growth in a.revenue_growth:
            revenues.append(revenues[-1] * (1 + growth))

        # Title
        self._add_title(ws, f"{self.company_name} - Expense Build", 1, 1)

        # Year headers
        self._year_headers(ws, 3, 2)

        if self.depth == ModelDepth.QUICK:
            # Simple: COGS and SG&A as % of revenue
            self._add_section_header(ws, "Cost Assumptions (% Revenue)", 4, 1)

            cogs_pct = 0.60
            sga_pct = 0.20

            ws.cell(row=5, column=1, value="COGS %")
            for i in range(len(revenues)):
                cell = ws.cell(row=5, column=2 + i, value=cogs_pct)
                cell.number_format = '0.0%'
                self._format_input_cell(ws, 5, 2 + i)

            ws.cell(row=6, column=1, value="SG&A %")
            for i in range(len(revenues)):
                cell = ws.cell(row=6, column=2 + i, value=sga_pct)
                cell.number_format = '0.0%'
                self._format_input_cell(ws, 6, 2 + i)

            # Calculated values
            self._add_section_header(ws, "Expense Summary ($M)", 8, 1)

            ws.cell(row=9, column=1, value="COGS")
            for i, rev in enumerate(revenues):
                ws.cell(row=9, column=2 + i, value=rev * cogs_pct)
                ws.cell(row=9, column=2 + i).number_format = '#,##0.0'

            ws.cell(row=10, column=1, value="Gross Profit")
            for i, rev in enumerate(revenues):
                ws.cell(row=10, column=2 + i, value=rev * (1 - cogs_pct))
                ws.cell(row=10, column=2 + i).number_format = '#,##0.0'
                ws.cell(row=10, column=2 + i).font = Font(bold=True)

            ws.cell(row=12, column=1, value="SG&A")
            for i, rev in enumerate(revenues):
                ws.cell(row=12, column=2 + i, value=rev * sga_pct)
                ws.cell(row=12, column=2 + i).number_format = '#,##0.0'

        else:
            # Standard/Comprehensive: Detailed breakdown
            data = data or {}
            self._add_section_header(ws, "COGS Breakdown ($M)", 4, 1)

            cogs_items = data.get('cogs_items', [
                {"name": "Materials", "pct": 0.35},
                {"name": "Direct Labor", "pct": 0.15},
                {"name": "Manufacturing OH", "pct": 0.10},
            ])

            for j, item in enumerate(cogs_items):
                row = 5 + j
                ws.cell(row=row, column=1, value=item["name"])
                for i, rev in enumerate(revenues):
                    ws.cell(row=row, column=2 + i, value=rev * item["pct"])
                    ws.cell(row=row, column=2 + i).number_format = '#,##0.0'

            cogs_total_row = 5 + len(cogs_items)
            ws.cell(row=cogs_total_row, column=1, value="Total COGS")
            total_cogs_pct = sum(item["pct"] for item in cogs_items)
            for i, rev in enumerate(revenues):
                ws.cell(row=cogs_total_row, column=2 + i, value=rev * total_cogs_pct)
                ws.cell(row=cogs_total_row, column=2 + i).number_format = '#,##0.0'
                ws.cell(row=cogs_total_row, column=2 + i).font = Font(bold=True)
                ws.cell(row=cogs_total_row, column=2 + i).border = BOTTOM_BORDER

            # SG&A breakdown
            sga_start = cogs_total_row + 2
            self._add_section_header(ws, "SG&A Breakdown ($M)", sga_start, 1)

            sga_items = data.get('sga_items', [
                {"name": "Sales & Marketing", "pct": 0.08},
                {"name": "General & Admin", "pct": 0.05},
                {"name": "R&D", "pct": 0.04},
                {"name": "Other", "pct": 0.03},
            ])

            for j, item in enumerate(sga_items):
                row = sga_start + 1 + j
                ws.cell(row=row, column=1, value=item["name"])
                for i, rev in enumerate(revenues):
                    ws.cell(row=row, column=2 + i, value=rev * item["pct"])
                    ws.cell(row=row, column=2 + i).number_format = '#,##0.0'

            sga_total_row = sga_start + 1 + len(sga_items)
            ws.cell(row=sga_total_row, column=1, value="Total SG&A")
            total_sga_pct = sum(item["pct"] for item in sga_items)
            for i, rev in enumerate(revenues):
                ws.cell(row=sga_total_row, column=2 + i, value=rev * total_sga_pct)
                ws.cell(row=sga_total_row, column=2 + i).number_format = '#,##0.0'
                ws.cell(row=sga_total_row, column=2 + i).font = Font(bold=True)
                ws.cell(row=sga_total_row, column=2 + i).border = BOTTOM_BORDER

            # Summary
            summary_start = sga_total_row + 2
            self._add_section_header(ws, "P&L Summary ($M)", summary_start, 1)

            ws.cell(row=summary_start + 1, column=1, value="Revenue")
            for i, rev in enumerate(revenues):
                ws.cell(row=summary_start + 1, column=2 + i, value=rev)
                ws.cell(row=summary_start + 1, column=2 + i).number_format = '#,##0.0'

            ws.cell(row=summary_start + 2, column=1, value="Gross Profit")
            for i, rev in enumerate(revenues):
                ws.cell(row=summary_start + 2, column=2 + i, value=rev * (1 - total_cogs_pct))
                ws.cell(row=summary_start + 2, column=2 + i).number_format = '#,##0.0'

            ws.cell(row=summary_start + 3, column=1, value="  Gross Margin %")
            for i in enumerate(revenues):
                cell = ws.cell(row=summary_start + 3, column=2 + i[0], value=1 - total_cogs_pct)
                cell.number_format = '0.0%'
                cell.font = Font(italic=True, color="666666")

            ws.cell(row=summary_start + 5, column=1, value="EBITDA")
            for i, rev in enumerate(revenues):
                ebitda = rev * (1 - total_cogs_pct - total_sga_pct)
                ws.cell(row=summary_start + 5, column=2 + i, value=ebitda)
                ws.cell(row=summary_start + 5, column=2 + i).number_format = '#,##0.0'
                ws.cell(row=summary_start + 5, column=2 + i).font = Font(bold=True)

            ws.cell(row=summary_start + 6, column=1, value="  EBITDA Margin %")
            for i in range(len(revenues)):
                cell = ws.cell(row=summary_start + 6, column=2 + i,
                              value=1 - total_cogs_pct - total_sga_pct)
                cell.number_format = '0.0%'
                cell.font = Font(italic=True, color="666666")

        # Set column widths
        ws.column_dimensions['A'].width = 20
        for i in range(self.projection_years + 2):
            ws.column_dimensions[get_column_letter(2 + i)].width = 12

        return self

    # ============================================================
    # MODULE: DEBT SCHEDULE
    # ============================================================

    def add_debt_schedule(self, data: Dict = None) -> 'ExcelModelGenerator':
        """Add Debt Schedule sheet."""
        ws = self.wb.create_sheet("Debt Schedule")
        self.sheets_created.append("Debt Schedule")

        a = self.assumptions

        # Calculate initial debt
        senior_debt_initial = a.ltm_ebitda * a.senior_debt_multiple
        sub_debt_initial = a.ltm_ebitda * a.sub_debt_multiple

        # Calculate EBITDA projections for cash sweep
        revenues = [a.ltm_revenue]
        for growth in a.revenue_growth:
            revenues.append(revenues[-1] * (1 + growth))

        margins = [a.ltm_ebitda / a.ltm_revenue] + list(a.ebitda_margin)
        ebitdas = [revenues[i] * margins[i] for i in range(len(revenues))]

        # Title
        self._add_title(ws, f"{self.company_name} - Debt Schedule", 1, 1)

        # Year headers
        ws.cell(row=3, column=1, value="")
        ws.cell(row=3, column=2, value="Entry")
        for i in range(self.projection_years):
            ws.cell(row=3, column=3 + i, value=f"Year {i + 1}")
        self._format_header_row(ws, 3, 1, 2 + self.projection_years)

        if self.depth == ModelDepth.QUICK:
            # Simple: Single debt tranche with flat paydown
            self._add_section_header(ws, "Debt Assumptions", 4, 1)

            ws.cell(row=5, column=1, value="Initial Debt ($M)")
            ws.cell(row=5, column=2, value=senior_debt_initial + sub_debt_initial)
            self._format_input_cell(ws, 5, 2)

            ws.cell(row=6, column=1, value="Interest Rate")
            ws.cell(row=6, column=2, value=(a.senior_interest_rate + a.sub_interest_rate) / 2)
            ws.cell(row=6, column=2).number_format = '0.0%'
            self._format_input_cell(ws, 6, 2)

            ws.cell(row=7, column=1, value="Annual Paydown ($M)")
            annual_paydown = (senior_debt_initial + sub_debt_initial) * 0.10
            ws.cell(row=7, column=2, value=annual_paydown)
            self._format_input_cell(ws, 7, 2)

            # Debt schedule
            self._add_section_header(ws, "Debt Schedule ($M)", 9, 1)

            debt_balance = [senior_debt_initial + sub_debt_initial]
            for i in range(self.projection_years):
                debt_balance.append(max(0, debt_balance[-1] - annual_paydown))

            ws.cell(row=10, column=1, value="Beginning Balance")
            for i, bal in enumerate(debt_balance[:-1]):
                ws.cell(row=10, column=2 + i, value=bal)
                ws.cell(row=10, column=2 + i).number_format = '#,##0.0'

            ws.cell(row=11, column=1, value="Paydown")
            for i in range(self.projection_years):
                ws.cell(row=11, column=3 + i, value=-annual_paydown)
                ws.cell(row=11, column=3 + i).number_format = '(#,##0.0)'

            ws.cell(row=12, column=1, value="Ending Balance")
            for i, bal in enumerate(debt_balance[1:]):
                ws.cell(row=12, column=3 + i, value=bal)
                ws.cell(row=12, column=3 + i).number_format = '#,##0.0'
                ws.cell(row=12, column=3 + i).font = Font(bold=True)

            ws.cell(row=14, column=1, value="Interest Expense")
            avg_rate = (a.senior_interest_rate + a.sub_interest_rate) / 2
            for i in range(self.projection_years):
                avg_debt = (debt_balance[i] + debt_balance[i + 1]) / 2
                interest = avg_debt * avg_rate
                ws.cell(row=14, column=3 + i, value=interest)
                ws.cell(row=14, column=3 + i).number_format = '#,##0.0'

        else:
            # Standard/Comprehensive: Multi-tranche with cash sweep

            # Senior Debt section
            self._add_section_header(ws, "Senior Secured Debt ($M)", 4, 1)

            ws.cell(row=5, column=1, value="Beginning Balance")
            ws.cell(row=5, column=2, value=senior_debt_initial)

            # Calculate senior debt with mandatory amortization
            senior_balance = [senior_debt_initial]
            senior_amort = senior_debt_initial * a.senior_amortization

            for i in range(self.projection_years):
                new_bal = max(0, senior_balance[-1] - senior_amort)
                senior_balance.append(new_bal)
                ws.cell(row=5, column=3 + i, value=senior_balance[i])
                ws.cell(row=5, column=3 + i).number_format = '#,##0.0'

            ws.cell(row=6, column=1, value="Mandatory Amortization")
            for i in range(self.projection_years):
                ws.cell(row=6, column=3 + i, value=-senior_amort)
                ws.cell(row=6, column=3 + i).number_format = '(#,##0.0)'

            # Cash sweep (simplified - 50% of excess cash)
            ws.cell(row=7, column=1, value="Cash Sweep")
            capex = [rev * a.capex_pct_revenue for rev in revenues]
            for i in range(self.projection_years):
                ebitda = ebitdas[i + 1]
                interest = senior_balance[i] * a.senior_interest_rate
                fcf = ebitda - capex[i + 1] - interest - senior_amort
                sweep = max(0, fcf * 0.50)  # 50% sweep
                ws.cell(row=7, column=3 + i, value=-sweep)
                ws.cell(row=7, column=3 + i).number_format = '(#,##0.0)'

            ws.cell(row=8, column=1, value="Ending Balance")
            for i in range(self.projection_years):
                ws.cell(row=8, column=3 + i, value=senior_balance[i + 1])
                ws.cell(row=8, column=3 + i).number_format = '#,##0.0'
                ws.cell(row=8, column=3 + i).font = Font(bold=True)

            ws.cell(row=9, column=1, value="Interest Rate")
            ws.cell(row=9, column=2, value=a.senior_interest_rate)
            ws.cell(row=9, column=2).number_format = '0.0%'
            self._format_input_cell(ws, 9, 2)

            ws.cell(row=10, column=1, value="Interest Expense")
            for i in range(self.projection_years):
                avg_bal = (senior_balance[i] + senior_balance[i + 1]) / 2
                interest = avg_bal * a.senior_interest_rate
                ws.cell(row=10, column=3 + i, value=interest)
                ws.cell(row=10, column=3 + i).number_format = '#,##0.0'

            # Subordinated Debt section
            sub_start = 12
            self._add_section_header(ws, "Subordinated Debt ($M)", sub_start, 1)

            ws.cell(row=sub_start + 1, column=1, value="Beginning Balance")
            ws.cell(row=sub_start + 1, column=2, value=sub_debt_initial)

            # Sub debt typically no amortization
            sub_balance = [sub_debt_initial] * (self.projection_years + 1)
            for i in range(self.projection_years):
                ws.cell(row=sub_start + 1, column=3 + i, value=sub_balance[i])
                ws.cell(row=sub_start + 1, column=3 + i).number_format = '#,##0.0'

            ws.cell(row=sub_start + 2, column=1, value="Ending Balance")
            for i in range(self.projection_years):
                ws.cell(row=sub_start + 2, column=3 + i, value=sub_balance[i + 1])
                ws.cell(row=sub_start + 2, column=3 + i).number_format = '#,##0.0'
                ws.cell(row=sub_start + 2, column=3 + i).font = Font(bold=True)

            ws.cell(row=sub_start + 3, column=1, value="Interest Rate")
            ws.cell(row=sub_start + 3, column=2, value=a.sub_interest_rate)
            ws.cell(row=sub_start + 3, column=2).number_format = '0.0%'
            self._format_input_cell(ws, sub_start + 3, 2)

            ws.cell(row=sub_start + 4, column=1, value="Interest Expense")
            for i in range(self.projection_years):
                interest = sub_balance[i] * a.sub_interest_rate
                ws.cell(row=sub_start + 4, column=3 + i, value=interest)
                ws.cell(row=sub_start + 4, column=3 + i).number_format = '#,##0.0'

            # Summary section
            summary_start = sub_start + 6
            self._add_section_header(ws, "Debt Summary", summary_start, 1)

            ws.cell(row=summary_start + 1, column=1, value="Total Debt")
            for i in range(self.projection_years + 1):
                total = senior_balance[i] + sub_balance[i]
                ws.cell(row=summary_start + 1, column=2 + i, value=total)
                ws.cell(row=summary_start + 1, column=2 + i).number_format = '#,##0.0'
                ws.cell(row=summary_start + 1, column=2 + i).font = Font(bold=True)

            ws.cell(row=summary_start + 2, column=1, value="Total Interest")
            for i in range(self.projection_years):
                senior_int = (senior_balance[i] + senior_balance[i + 1]) / 2 * a.senior_interest_rate
                sub_int = sub_balance[i] * a.sub_interest_rate
                ws.cell(row=summary_start + 2, column=3 + i, value=senior_int + sub_int)
                ws.cell(row=summary_start + 2, column=3 + i).number_format = '#,##0.0'

            ws.cell(row=summary_start + 4, column=1, value="Debt / EBITDA")
            for i in range(self.projection_years + 1):
                total = senior_balance[i] + sub_balance[i]
                ratio = total / ebitdas[i] if ebitdas[i] > 0 else 0
                ws.cell(row=summary_start + 4, column=2 + i, value=ratio)
                ws.cell(row=summary_start + 4, column=2 + i).number_format = '0.0x'

        # Set column widths
        ws.column_dimensions['A'].width = 22
        for i in range(self.projection_years + 2):
            ws.column_dimensions[get_column_letter(2 + i)].width = 12

        return self

    # ============================================================
    # MODULE: WACC CALCULATION
    # ============================================================

    def add_wacc_calculation(self, data: Dict = None) -> 'ExcelModelGenerator':
        """Add WACC Calculation sheet."""
        ws = self.wb.create_sheet("WACC")
        self.sheets_created.append("WACC")

        a = self.assumptions

        # Title
        self._add_title(ws, f"{self.company_name} - WACC Calculation", 1, 1)

        if self.depth == ModelDepth.QUICK:
            # Simple: Just show WACC assumption
            self._add_section_header(ws, "WACC Assumption", 3, 1)

            ws.cell(row=4, column=1, value="WACC")
            wacc = 0.10  # Default assumption
            ws.cell(row=4, column=2, value=wacc)
            ws.cell(row=4, column=2).number_format = '0.0%'
            self._format_input_cell(ws, 4, 2)

            ws.cell(row=6, column=1, value="Note: For quick analysis, using market standard")

        else:
            # Standard/Comprehensive: Full CAPM calculation

            # Cost of Equity section
            self._add_section_header(ws, "Cost of Equity (CAPM)", 3, 1)

            capm_items = [
                ("Risk-Free Rate (10Y Treasury)", a.risk_free_rate, True),
                ("Equity Risk Premium", a.equity_risk_premium, True),
                ("Beta (Levered)", a.beta, True),
                ("Size Premium", a.size_premium, True),
            ]

            for i, (name, value, is_input) in enumerate(capm_items):
                row = 4 + i
                ws.cell(row=row, column=1, value=name)
                ws.cell(row=row, column=2, value=value)
                ws.cell(row=row, column=2).number_format = '0.00%' if 'Rate' in name or 'Premium' in name else '0.00'
                if is_input:
                    self._format_input_cell(ws, row, 2)

            # Cost of equity calculation
            cost_of_equity = a.risk_free_rate + (a.beta * a.equity_risk_premium) + a.size_premium

            ws.cell(row=9, column=1, value="Cost of Equity")
            ws.cell(row=9, column=2, value=cost_of_equity)
            ws.cell(row=9, column=2).number_format = '0.0%'
            ws.cell(row=9, column=2).font = Font(bold=True)
            ws.cell(row=9, column=2).border = DOUBLE_BORDER

            # Cost of Debt section
            self._add_section_header(ws, "Cost of Debt", 11, 1)

            ws.cell(row=12, column=1, value="Pre-Tax Cost of Debt")
            ws.cell(row=12, column=2, value=a.cost_of_debt)
            ws.cell(row=12, column=2).number_format = '0.0%'
            self._format_input_cell(ws, 12, 2)

            ws.cell(row=13, column=1, value="Tax Rate")
            ws.cell(row=13, column=2, value=a.tax_rate)
            ws.cell(row=13, column=2).number_format = '0.0%'
            self._format_input_cell(ws, 13, 2)

            after_tax_debt = a.cost_of_debt * (1 - a.tax_rate)
            ws.cell(row=14, column=1, value="After-Tax Cost of Debt")
            ws.cell(row=14, column=2, value=after_tax_debt)
            ws.cell(row=14, column=2).number_format = '0.0%'
            ws.cell(row=14, column=2).font = Font(bold=True)
            ws.cell(row=14, column=2).border = DOUBLE_BORDER

            # Capital Structure
            self._add_section_header(ws, "Capital Structure", 16, 1)

            debt_weight = a.target_debt_equity / (1 + a.target_debt_equity)
            equity_weight = 1 - debt_weight

            ws.cell(row=17, column=1, value="Target Debt / Equity")
            ws.cell(row=17, column=2, value=a.target_debt_equity)
            ws.cell(row=17, column=2).number_format = '0.0%'
            self._format_input_cell(ws, 17, 2)

            ws.cell(row=18, column=1, value="Debt Weight")
            ws.cell(row=18, column=2, value=debt_weight)
            ws.cell(row=18, column=2).number_format = '0.0%'

            ws.cell(row=19, column=1, value="Equity Weight")
            ws.cell(row=19, column=2, value=equity_weight)
            ws.cell(row=19, column=2).number_format = '0.0%'

            # WACC Calculation
            self._add_section_header(ws, "WACC Calculation", 21, 1)

            wacc = (equity_weight * cost_of_equity) + (debt_weight * after_tax_debt)

            ws.cell(row=22, column=1, value="WACC")
            ws.cell(row=22, column=2, value=wacc)
            ws.cell(row=22, column=2).number_format = '0.0%'
            ws.cell(row=22, column=2).font = Font(bold=True, size=14)
            ws.cell(row=22, column=2).fill = PatternFill(start_color="90EE90", end_color="90EE90", fill_type="solid")

            # Formula breakdown
            ws.cell(row=24, column=1, value="Formula: (E/V × Re) + (D/V × Rd × (1-T))")
            ws.cell(row=25, column=1, value=f"= ({equity_weight:.1%} × {cost_of_equity:.1%}) + ({debt_weight:.1%} × {after_tax_debt:.1%})")

        # Set column widths
        ws.column_dimensions['A'].width = 30
        ws.column_dimensions['B'].width = 15

        return self

    # ============================================================
    # MODULE: WORKING CAPITAL
    # ============================================================

    def add_working_capital(self, data: Dict = None) -> 'ExcelModelGenerator':
        """Add Working Capital Analysis sheet."""
        ws = self.wb.create_sheet("Working Capital")
        self.sheets_created.append("Working Capital")

        a = self.assumptions

        # Calculate revenues
        revenues = [a.ltm_revenue]
        for growth in a.revenue_growth:
            revenues.append(revenues[-1] * (1 + growth))

        # Title
        self._add_title(ws, f"{self.company_name} - Working Capital Analysis", 1, 1)

        # Year headers
        self._year_headers(ws, 3, 2)

        if self.depth == ModelDepth.QUICK:
            # Simple: NWC as % of revenue
            self._add_section_header(ws, "Working Capital Assumptions", 4, 1)

            ws.cell(row=5, column=1, value="NWC % of Revenue")
            for i in range(len(revenues)):
                cell = ws.cell(row=5, column=2 + i, value=a.nwc_pct_revenue)
                cell.number_format = '0.0%'
                self._format_input_cell(ws, 5, 2 + i)

            self._add_section_header(ws, "Working Capital ($M)", 7, 1)

            nwc = [rev * a.nwc_pct_revenue for rev in revenues]

            ws.cell(row=8, column=1, value="Net Working Capital")
            for i, val in enumerate(nwc):
                ws.cell(row=8, column=2 + i, value=val)
                ws.cell(row=8, column=2 + i).number_format = '#,##0.0'

            ws.cell(row=9, column=1, value="Change in NWC")
            ws.cell(row=9, column=2, value="—")
            for i in range(len(nwc) - 1):
                change = nwc[i + 1] - nwc[i]
                ws.cell(row=9, column=3 + i, value=change)
                ws.cell(row=9, column=3 + i).number_format = '#,##0.0'

        else:
            # Standard/Comprehensive: Days-based calculation
            data = data or {}
            self._add_section_header(ws, "Working Capital Assumptions (Days)", 4, 1)

            days = data.get('days', {
                'ar_days': 45,
                'inventory_days': 60,
                'ap_days': 30,
                'other_ca_pct': 0.02,
                'other_cl_pct': 0.03,
            })

            ws.cell(row=5, column=1, value="Accounts Receivable Days")
            for i in range(len(revenues)):
                ws.cell(row=5, column=2 + i, value=days['ar_days'])
                self._format_input_cell(ws, 5, 2 + i)

            ws.cell(row=6, column=1, value="Inventory Days")
            for i in range(len(revenues)):
                ws.cell(row=6, column=2 + i, value=days['inventory_days'])
                self._format_input_cell(ws, 6, 2 + i)

            ws.cell(row=7, column=1, value="Accounts Payable Days")
            for i in range(len(revenues)):
                ws.cell(row=7, column=2 + i, value=days['ap_days'])
                self._format_input_cell(ws, 7, 2 + i)

            # Current Assets
            self._add_section_header(ws, "Current Assets ($M)", 9, 1)

            # Assume COGS = 60% of revenue for inventory calc
            cogs_pct = 0.60

            ar = [rev * days['ar_days'] / 365 for rev in revenues]
            inventory = [rev * cogs_pct * days['inventory_days'] / 365 for rev in revenues]
            other_ca = [rev * days['other_ca_pct'] for rev in revenues]

            ws.cell(row=10, column=1, value="Accounts Receivable")
            for i, val in enumerate(ar):
                ws.cell(row=10, column=2 + i, value=val)
                ws.cell(row=10, column=2 + i).number_format = '#,##0.0'

            ws.cell(row=11, column=1, value="Inventory")
            for i, val in enumerate(inventory):
                ws.cell(row=11, column=2 + i, value=val)
                ws.cell(row=11, column=2 + i).number_format = '#,##0.0'

            ws.cell(row=12, column=1, value="Other Current Assets")
            for i, val in enumerate(other_ca):
                ws.cell(row=12, column=2 + i, value=val)
                ws.cell(row=12, column=2 + i).number_format = '#,##0.0'

            total_ca = [ar[i] + inventory[i] + other_ca[i] for i in range(len(revenues))]
            ws.cell(row=13, column=1, value="Total Current Assets")
            for i, val in enumerate(total_ca):
                ws.cell(row=13, column=2 + i, value=val)
                ws.cell(row=13, column=2 + i).number_format = '#,##0.0'
                ws.cell(row=13, column=2 + i).font = Font(bold=True)

            # Current Liabilities
            self._add_section_header(ws, "Current Liabilities ($M)", 15, 1)

            ap = [rev * cogs_pct * days['ap_days'] / 365 for rev in revenues]
            other_cl = [rev * days['other_cl_pct'] for rev in revenues]

            ws.cell(row=16, column=1, value="Accounts Payable")
            for i, val in enumerate(ap):
                ws.cell(row=16, column=2 + i, value=val)
                ws.cell(row=16, column=2 + i).number_format = '#,##0.0'

            ws.cell(row=17, column=1, value="Other Current Liabilities")
            for i, val in enumerate(other_cl):
                ws.cell(row=17, column=2 + i, value=val)
                ws.cell(row=17, column=2 + i).number_format = '#,##0.0'

            total_cl = [ap[i] + other_cl[i] for i in range(len(revenues))]
            ws.cell(row=18, column=1, value="Total Current Liabilities")
            for i, val in enumerate(total_cl):
                ws.cell(row=18, column=2 + i, value=val)
                ws.cell(row=18, column=2 + i).number_format = '#,##0.0'
                ws.cell(row=18, column=2 + i).font = Font(bold=True)

            # Net Working Capital
            self._add_section_header(ws, "Net Working Capital ($M)", 20, 1)

            nwc = [total_ca[i] - total_cl[i] for i in range(len(revenues))]

            ws.cell(row=21, column=1, value="Net Working Capital")
            for i, val in enumerate(nwc):
                ws.cell(row=21, column=2 + i, value=val)
                ws.cell(row=21, column=2 + i).number_format = '#,##0.0'
                ws.cell(row=21, column=2 + i).font = Font(bold=True)

            ws.cell(row=22, column=1, value="NWC % of Revenue")
            for i in range(len(revenues)):
                pct = nwc[i] / revenues[i]
                ws.cell(row=22, column=2 + i, value=pct)
                ws.cell(row=22, column=2 + i).number_format = '0.0%'

            ws.cell(row=23, column=1, value="Change in NWC")
            ws.cell(row=23, column=2, value="—")
            for i in range(len(nwc) - 1):
                change = nwc[i + 1] - nwc[i]
                ws.cell(row=23, column=3 + i, value=change)
                ws.cell(row=23, column=3 + i).number_format = '#,##0.0'

            # Cash Conversion Cycle
            self._add_section_header(ws, "Cash Conversion Cycle", 25, 1)

            dso = days['ar_days']
            dio = days['inventory_days']
            dpo = days['ap_days']
            ccc = dso + dio - dpo

            ws.cell(row=26, column=1, value="DSO (Days Sales Outstanding)")
            ws.cell(row=26, column=2, value=dso)

            ws.cell(row=27, column=1, value="DIO (Days Inventory Outstanding)")
            ws.cell(row=27, column=2, value=dio)

            ws.cell(row=28, column=1, value="DPO (Days Payable Outstanding)")
            ws.cell(row=28, column=2, value=dpo)

            ws.cell(row=29, column=1, value="Cash Conversion Cycle")
            ws.cell(row=29, column=2, value=ccc)
            ws.cell(row=29, column=2).font = Font(bold=True)

        # Set column widths
        ws.column_dimensions['A'].width = 28
        for i in range(self.projection_years + 2):
            ws.column_dimensions[get_column_letter(2 + i)].width = 12

        return self

    # ============================================================
    # MODULE: RETURNS ANALYSIS
    # ============================================================

    def add_returns_analysis(self, data: Dict = None) -> 'ExcelModelGenerator':
        """Add Returns Analysis sheet."""
        ws = self.wb.create_sheet("Returns Analysis")
        self.sheets_created.append("Returns Analysis")

        a = self.assumptions

        # Calculate model outputs
        ev = a.ltm_ebitda * a.entry_multiple
        senior_debt = a.ltm_ebitda * a.senior_debt_multiple
        sub_debt = a.ltm_ebitda * a.sub_debt_multiple
        total_debt = senior_debt + sub_debt
        fees = ev * 0.04  # Approximate total fees
        equity_check = ev + fees - total_debt

        # EBITDA projections
        revenues = [a.ltm_revenue]
        for growth in a.revenue_growth:
            revenues.append(revenues[-1] * (1 + growth))

        margins = [a.ltm_ebitda / a.ltm_revenue] + list(a.ebitda_margin)
        ebitdas = [revenues[i] * margins[i] for i in range(len(revenues))]

        # Debt paydown (simplified)
        annual_paydown = total_debt * 0.10
        debt_balances = [total_debt]
        for i in range(self.projection_years):
            debt_balances.append(max(0, debt_balances[-1] - annual_paydown))

        # Title
        self._add_title(ws, f"{self.company_name} - Returns Analysis", 1, 1)

        # Entry assumptions
        self._add_section_header(ws, "Entry Assumptions", 3, 1)

        entry_items = [
            ("LTM EBITDA ($M)", a.ltm_ebitda),
            ("Entry Multiple", f"{a.entry_multiple:.1f}x"),
            ("Enterprise Value ($M)", ev),
            ("Total Debt ($M)", total_debt),
            ("Equity Investment ($M)", equity_check),
        ]

        for i, (name, value) in enumerate(entry_items):
            row = 4 + i
            ws.cell(row=row, column=1, value=name)
            if isinstance(value, str):
                ws.cell(row=row, column=2, value=value)
            else:
                ws.cell(row=row, column=2, value=value)
                ws.cell(row=row, column=2).number_format = '#,##0.0'

        # Exit assumptions
        self._add_section_header(ws, "Exit Assumptions", 10, 1)

        ws.cell(row=11, column=1, value="Exit Multiple")
        ws.cell(row=11, column=2, value=a.exit_multiple)
        ws.cell(row=11, column=2).number_format = '0.0x'
        self._format_input_cell(ws, 11, 2)

        ws.cell(row=12, column=1, value="Hold Period (Years)")
        ws.cell(row=12, column=2, value=a.hold_period)
        self._format_input_cell(ws, 12, 2)

        # Returns by exit year
        self._add_section_header(ws, "Returns by Exit Year", 14, 1)

        headers = ["Exit Year", "EBITDA", "Exit EV", "Net Debt", "Equity Value", "MOIC", "IRR"]
        for i, header in enumerate(headers):
            ws.cell(row=15, column=1 + i, value=header)
        self._format_header_row(ws, 15, 1, len(headers))

        for year in range(3, self.projection_years + 1):
            row = 16 + (year - 3)
            exit_ebitda = ebitdas[year]
            exit_ev = exit_ebitda * a.exit_multiple
            net_debt = debt_balances[year]
            equity_value = exit_ev - net_debt
            moic = equity_value / equity_check
            irr = (moic ** (1 / year)) - 1

            ws.cell(row=row, column=1, value=f"Year {year}")
            ws.cell(row=row, column=2, value=exit_ebitda)
            ws.cell(row=row, column=2).number_format = '#,##0.0'
            ws.cell(row=row, column=3, value=exit_ev)
            ws.cell(row=row, column=3).number_format = '#,##0.0'
            ws.cell(row=row, column=4, value=net_debt)
            ws.cell(row=row, column=4).number_format = '#,##0.0'
            ws.cell(row=row, column=5, value=equity_value)
            ws.cell(row=row, column=5).number_format = '#,##0.0'
            ws.cell(row=row, column=6, value=moic)
            ws.cell(row=row, column=6).number_format = '0.00x'
            ws.cell(row=row, column=7, value=irr)
            ws.cell(row=row, column=7).number_format = '0.0%'

        # Highlight base case (Year 5)
        base_row = 16 + (5 - 3)
        for col in range(1, 8):
            ws.cell(row=base_row, column=col).fill = PatternFill(start_color="90EE90", end_color="90EE90", fill_type="solid")

        # Value Creation Bridge
        if self.depth != ModelDepth.QUICK:
            bridge_start = 16 + (self.projection_years - 2) + 2
            self._add_section_header(ws, "Value Creation Bridge (Base Case)", bridge_start, 1)

            # Base case = Year 5
            exit_year = 5
            exit_ebitda = ebitdas[exit_year]
            exit_ev = exit_ebitda * a.exit_multiple
            equity_value = exit_ev - debt_balances[exit_year]
            total_gain = equity_value - equity_check

            # Attribution
            ebitda_growth_value = (exit_ebitda - a.ltm_ebitda) * a.exit_multiple
            multiple_expansion_value = 0  # Same entry/exit multiple
            debt_paydown_value = total_debt - debt_balances[exit_year]

            bridge_items = [
                ("Entry Equity", equity_check, ""),
                ("(+) EBITDA Growth", ebitda_growth_value, f"{ebitda_growth_value / total_gain:.0%} of gain" if total_gain > 0 else ""),
                ("(+) Multiple Expansion", multiple_expansion_value, "Same entry/exit"),
                ("(+) Debt Paydown", debt_paydown_value, f"{debt_paydown_value / total_gain:.0%} of gain" if total_gain > 0 else ""),
                ("(=) Exit Equity", equity_value, ""),
            ]

            for i, (name, value, note) in enumerate(bridge_items):
                row = bridge_start + 1 + i
                ws.cell(row=row, column=1, value=name)
                ws.cell(row=row, column=2, value=value)
                ws.cell(row=row, column=2).number_format = '#,##0.0'
                if note:
                    ws.cell(row=row, column=3, value=note)

                if name.startswith("(=)"):
                    ws.cell(row=row, column=1).font = Font(bold=True)
                    ws.cell(row=row, column=2).font = Font(bold=True)
                    ws.cell(row=row, column=2).border = DOUBLE_BORDER

        # Set column widths
        ws.column_dimensions['A'].width = 22
        for i in range(7):
            ws.column_dimensions[get_column_letter(2 + i)].width = 12

        return self

    # ============================================================
    # MODULE: SENSITIVITY TABLES
    # ============================================================

    def add_sensitivity_tables(self, data: Dict = None) -> 'ExcelModelGenerator':
        """Add Sensitivity Analysis sheet."""
        ws = self.wb.create_sheet("Sensitivity")
        self.sheets_created.append("Sensitivity")

        a = self.assumptions

        # Base case calculations
        ev = a.ltm_ebitda * a.entry_multiple
        total_debt = a.ltm_ebitda * (a.senior_debt_multiple + a.sub_debt_multiple)
        fees = ev * 0.04
        equity_check = ev + fees - total_debt

        # EBITDA at exit
        revenues = [a.ltm_revenue]
        for growth in a.revenue_growth:
            revenues.append(revenues[-1] * (1 + growth))
        exit_ebitda = revenues[-1] * a.ebitda_margin[-1]

        # Debt at exit (simplified)
        debt_at_exit = total_debt * 0.50  # Assume 50% paydown

        # Title
        self._add_title(ws, f"{self.company_name} - Sensitivity Analysis", 1, 1)

        # Entry vs Exit Multiple Matrix
        self._add_section_header(ws, "IRR Sensitivity: Entry Multiple vs Exit Multiple", 3, 1)

        entry_multiples = [7.0, 7.5, 8.0, 8.5, 9.0]
        exit_multiples = [7.0, 7.5, 8.0, 8.5, 9.0]

        # Headers
        ws.cell(row=4, column=1, value="Entry \\ Exit")
        for i, em in enumerate(exit_multiples):
            ws.cell(row=4, column=2 + i, value=f"{em:.1f}x")
        self._format_header_row(ws, 4, 1, 1 + len(exit_multiples))

        # Matrix
        for j, entry_mult in enumerate(entry_multiples):
            row = 5 + j
            ws.cell(row=row, column=1, value=f"{entry_mult:.1f}x")
            ws.cell(row=row, column=1).font = Font(bold=True)
            ws.cell(row=row, column=1).fill = HEADER_FILL
            ws.cell(row=row, column=1).font = HEADER_FONT

            entry_ev = a.ltm_ebitda * entry_mult
            entry_equity = entry_ev + fees - total_debt

            for i, exit_mult in enumerate(exit_multiples):
                exit_ev = exit_ebitda * exit_mult
                exit_equity = exit_ev - debt_at_exit
                moic = exit_equity / entry_equity
                irr = (moic ** (1 / a.hold_period)) - 1

                cell = ws.cell(row=row, column=2 + i, value=irr)
                cell.number_format = '0.0%'

                # Color code
                if irr >= 0.25:
                    cell.fill = PatternFill(start_color="90EE90", end_color="90EE90", fill_type="solid")
                elif irr >= 0.20:
                    cell.fill = PatternFill(start_color="FFFF90", end_color="FFFF90", fill_type="solid")
                elif irr >= 0.15:
                    cell.fill = PatternFill(start_color="FFD090", end_color="FFD090", fill_type="solid")
                else:
                    cell.fill = PatternFill(start_color="FF9090", end_color="FF9090", fill_type="solid")

        # MOIC Matrix
        moic_start = 5 + len(entry_multiples) + 2
        self._add_section_header(ws, "MOIC Sensitivity: Entry Multiple vs Exit Multiple", moic_start, 1)

        # Headers
        ws.cell(row=moic_start + 1, column=1, value="Entry \\ Exit")
        for i, em in enumerate(exit_multiples):
            ws.cell(row=moic_start + 1, column=2 + i, value=f"{em:.1f}x")
        self._format_header_row(ws, moic_start + 1, 1, 1 + len(exit_multiples))

        # Matrix
        for j, entry_mult in enumerate(entry_multiples):
            row = moic_start + 2 + j
            ws.cell(row=row, column=1, value=f"{entry_mult:.1f}x")
            ws.cell(row=row, column=1).font = Font(bold=True)
            ws.cell(row=row, column=1).fill = HEADER_FILL
            ws.cell(row=row, column=1).font = HEADER_FONT

            entry_ev = a.ltm_ebitda * entry_mult
            entry_equity = entry_ev + fees - total_debt

            for i, exit_mult in enumerate(exit_multiples):
                exit_ev = exit_ebitda * exit_mult
                exit_equity = exit_ev - debt_at_exit
                moic = exit_equity / entry_equity

                cell = ws.cell(row=row, column=2 + i, value=moic)
                cell.number_format = '0.00x'

                # Color code
                if moic >= 3.0:
                    cell.fill = PatternFill(start_color="90EE90", end_color="90EE90", fill_type="solid")
                elif moic >= 2.5:
                    cell.fill = PatternFill(start_color="FFFF90", end_color="FFFF90", fill_type="solid")
                elif moic >= 2.0:
                    cell.fill = PatternFill(start_color="FFD090", end_color="FFD090", fill_type="solid")
                else:
                    cell.fill = PatternFill(start_color="FF9090", end_color="FF9090", fill_type="solid")

        # Legend
        legend_start = moic_start + 2 + len(entry_multiples) + 2
        ws.cell(row=legend_start, column=1, value="Legend:")
        ws.cell(row=legend_start + 1, column=1, value="IRR ≥ 25%")
        ws.cell(row=legend_start + 1, column=2).fill = PatternFill(start_color="90EE90", end_color="90EE90", fill_type="solid")
        ws.cell(row=legend_start + 2, column=1, value="IRR 20-25%")
        ws.cell(row=legend_start + 2, column=2).fill = PatternFill(start_color="FFFF90", end_color="FFFF90", fill_type="solid")
        ws.cell(row=legend_start + 3, column=1, value="IRR 15-20%")
        ws.cell(row=legend_start + 3, column=2).fill = PatternFill(start_color="FFD090", end_color="FFD090", fill_type="solid")
        ws.cell(row=legend_start + 4, column=1, value="IRR < 15%")
        ws.cell(row=legend_start + 4, column=2).fill = PatternFill(start_color="FF9090", end_color="FF9090", fill_type="solid")

        # Set column widths
        ws.column_dimensions['A'].width = 15
        for i in range(6):
            ws.column_dimensions[get_column_letter(2 + i)].width = 10

        return self

    # ============================================================
    # CASE FRAMEWORK GENERATION
    # ============================================================

    def build_for_timeframe(self, timeframe: str) -> 'ExcelModelGenerator':
        """
        Build a model based on available time.

        Args:
            timeframe: One of "24_hour", "48_hour", "5_day", "7_day_plus"
        """
        if timeframe not in CASE_FRAMEWORKS:
            raise ValueError(f"Unknown timeframe: {timeframe}. Use: {list(CASE_FRAMEWORKS.keys())}")

        framework = CASE_FRAMEWORKS[timeframe]
        self.depth = framework["depth"]

        # Add required modules
        for module in framework["required_modules"]:
            method_name = f"add_{module}"
            if hasattr(self, method_name):
                getattr(self, method_name)()

        return self

    # ============================================================
    # OUTPUT
    # ============================================================

    def save(self, filepath: str) -> str:
        """Save the workbook to file."""
        # Add cover sheet
        cover = self.wb.create_sheet("Cover", 0)
        cover.cell(row=2, column=2, value=self.company_name)
        cover.cell(row=2, column=2).font = Font(size=24, bold=True)
        cover.cell(row=4, column=2, value="Financial Model")
        cover.cell(row=4, column=2).font = Font(size=18)
        cover.cell(row=6, column=2, value=f"Generated: {datetime.now().strftime('%B %d, %Y')}")
        cover.cell(row=8, column=2, value=f"Depth: {self.depth.value.title()}")
        cover.cell(row=10, column=2, value="Sheets:")
        for i, sheet in enumerate(self.sheets_created):
            cover.cell(row=11 + i, column=2, value=f"  • {sheet}")

        cover.column_dimensions['B'].width = 40

        self.wb.save(filepath)
        print(f"Model saved: {filepath}")
        print(f"Sheets created: {len(self.sheets_created)}")
        return filepath

    def get_workbook(self) -> Workbook:
        """Return the raw workbook for further manipulation."""
        return self.wb


# ============================================================
# QUICK GENERATION FUNCTIONS
# ============================================================

def generate_quick_lbo(company_name: str, output_path: str, assumptions: Dict = None) -> str:
    """Generate a quick 24-hour LBO model."""
    a = ModelAssumptions(company_name=company_name)
    if assumptions:
        for key, value in assumptions.items():
            if hasattr(a, key):
                setattr(a, key, value)

    gen = ExcelModelGenerator(company_name, ModelDepth.QUICK, a)
    gen.add_sources_uses()
    gen.add_operating_model()
    gen.add_returns_analysis()
    gen.add_sensitivity_tables()
    return gen.save(output_path)


def generate_standard_lbo(company_name: str, output_path: str, assumptions: Dict = None) -> str:
    """Generate a standard 48-hour to 5-day LBO model."""
    a = ModelAssumptions(company_name=company_name)
    if assumptions:
        for key, value in assumptions.items():
            if hasattr(a, key):
                setattr(a, key, value)

    gen = ExcelModelGenerator(company_name, ModelDepth.STANDARD, a)
    gen.add_sources_uses()
    gen.add_revenue_build()
    gen.add_expense_build()
    gen.add_operating_model()
    gen.add_debt_schedule()
    gen.add_working_capital()
    gen.add_returns_analysis()
    gen.add_sensitivity_tables()
    return gen.save(output_path)


def generate_comprehensive_lbo(company_name: str, output_path: str, assumptions: Dict = None) -> str:
    """Generate a comprehensive 7+ day LBO model."""
    a = ModelAssumptions(company_name=company_name)
    if assumptions:
        for key, value in assumptions.items():
            if hasattr(a, key):
                setattr(a, key, value)

    gen = ExcelModelGenerator(company_name, ModelDepth.COMPREHENSIVE, a)
    gen.add_sources_uses()
    gen.add_revenue_build()
    gen.add_expense_build()
    gen.add_operating_model()
    gen.add_debt_schedule()
    gen.add_working_capital()
    gen.add_wacc_calculation()
    gen.add_returns_analysis()
    gen.add_sensitivity_tables()
    return gen.save(output_path)


def generate_debt_schedule(company_name: str, output_path: str, assumptions: Dict = None) -> str:
    """Generate standalone debt schedule."""
    a = ModelAssumptions(company_name=company_name)
    if assumptions:
        for key, value in assumptions.items():
            if hasattr(a, key):
                setattr(a, key, value)

    gen = ExcelModelGenerator(company_name, ModelDepth.STANDARD, a)
    gen.add_debt_schedule()
    return gen.save(output_path)


def generate_wacc_model(company_name: str, output_path: str, assumptions: Dict = None) -> str:
    """Generate standalone WACC calculation."""
    a = ModelAssumptions(company_name=company_name)
    if assumptions:
        for key, value in assumptions.items():
            if hasattr(a, key):
                setattr(a, key, value)

    gen = ExcelModelGenerator(company_name, ModelDepth.STANDARD, a)
    gen.add_wacc_calculation()
    return gen.save(output_path)


def generate_revenue_build(company_name: str, output_path: str, assumptions: Dict = None) -> str:
    """Generate standalone revenue build."""
    a = ModelAssumptions(company_name=company_name)
    if assumptions:
        for key, value in assumptions.items():
            if hasattr(a, key):
                setattr(a, key, value)

    gen = ExcelModelGenerator(company_name, ModelDepth.STANDARD, a)
    gen.add_revenue_build()
    return gen.save(output_path)


def generate_expense_build(company_name: str, output_path: str, assumptions: Dict = None) -> str:
    """Generate standalone expense/SG&A build."""
    a = ModelAssumptions(company_name=company_name)
    if assumptions:
        for key, value in assumptions.items():
            if hasattr(a, key):
                setattr(a, key, value)

    gen = ExcelModelGenerator(company_name, ModelDepth.STANDARD, a)
    gen.add_expense_build()
    return gen.save(output_path)


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def list_model_modules() -> Dict:
    """Return the registry of available model modules."""
    return MODEL_MODULES


def list_case_frameworks() -> Dict:
    """Return the available case frameworks by time."""
    return CASE_FRAMEWORKS


def get_framework_recommendation(hours_available: int) -> Dict:
    """Get recommended framework based on hours available."""
    if hours_available <= 24:
        return CASE_FRAMEWORKS["24_hour"]
    elif hours_available <= 48:
        return CASE_FRAMEWORKS["48_hour"]
    elif hours_available <= 120:  # 5 days
        return CASE_FRAMEWORKS["5_day"]
    else:
        return CASE_FRAMEWORKS["7_day_plus"]


if __name__ == "__main__":
    print("=" * 60)
    print("Modular Excel Model Generator")
    print("=" * 60)

    print("\nAvailable Modules:")
    for key, info in MODEL_MODULES.items():
        print(f"  {key}: {info['name']}")

    print("\nCase Frameworks:")
    for key, info in CASE_FRAMEWORKS.items():
        print(f"\n  {info['name']}:")
        print(f"    Required: {', '.join(info['required_modules'])}")
        print(f"    Depth: {info['depth'].value}")
