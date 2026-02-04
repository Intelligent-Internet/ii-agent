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
    # MODULE: SCENARIO ANALYSIS (Bull/Bear/Base)
    # ============================================================

    def add_scenario_analysis(self, data: Dict = None) -> 'ExcelModelGenerator':
        """Add Bull/Bear/Base scenario comparison sheet."""
        ws = self.wb.create_sheet("Scenario Analysis")
        self.sheets_created.append("Scenario Analysis")

        a = self.assumptions
        data = data or {}

        # Define scenarios
        scenarios = data.get('scenarios', {
            'bear': {
                'name': 'Bear Case',
                'revenue_growth': [0.03, 0.02, 0.02, 0.02, 0.02],
                'ebitda_margin': [0.18, 0.18, 0.18, 0.18, 0.18],
                'exit_multiple': a.exit_multiple - 1.0,
                'probability': 0.25,
            },
            'base': {
                'name': 'Base Case',
                'revenue_growth': list(a.revenue_growth),
                'ebitda_margin': list(a.ebitda_margin),
                'exit_multiple': a.exit_multiple,
                'probability': 0.50,
            },
            'bull': {
                'name': 'Bull Case',
                'revenue_growth': [0.12, 0.10, 0.09, 0.08, 0.07],
                'ebitda_margin': [0.22, 0.24, 0.25, 0.26, 0.26],
                'exit_multiple': a.exit_multiple + 1.0,
                'probability': 0.25,
            },
        })

        # Calculate entry values (same across scenarios)
        ev = a.ltm_ebitda * a.entry_multiple
        total_debt = a.ltm_ebitda * (a.senior_debt_multiple + a.sub_debt_multiple)
        fees = ev * 0.04
        equity_check = ev + fees - total_debt

        # Title
        self._add_title(ws, f"{self.company_name} - Scenario Analysis", 1, 1)

        # Scenario Assumptions
        self._add_section_header(ws, "Scenario Assumptions", 3, 1)

        headers = ["Assumption", "Bear Case", "Base Case", "Bull Case"]
        for i, h in enumerate(headers):
            ws.cell(row=4, column=1 + i, value=h)
        self._format_header_row(ws, 4, 1, 4)

        # Revenue growth (Year 1)
        ws.cell(row=5, column=1, value="Revenue Growth (Y1)")
        ws.cell(row=5, column=2, value=scenarios['bear']['revenue_growth'][0])
        ws.cell(row=5, column=3, value=scenarios['base']['revenue_growth'][0])
        ws.cell(row=5, column=4, value=scenarios['bull']['revenue_growth'][0])
        for col in range(2, 5):
            ws.cell(row=5, column=col).number_format = '0.0%'
            self._format_input_cell(ws, 5, col)

        # EBITDA margin (Exit)
        ws.cell(row=6, column=1, value="Exit EBITDA Margin")
        ws.cell(row=6, column=2, value=scenarios['bear']['ebitda_margin'][-1])
        ws.cell(row=6, column=3, value=scenarios['base']['ebitda_margin'][-1])
        ws.cell(row=6, column=4, value=scenarios['bull']['ebitda_margin'][-1])
        for col in range(2, 5):
            ws.cell(row=6, column=col).number_format = '0.0%'
            self._format_input_cell(ws, 6, col)

        # Exit multiple
        ws.cell(row=7, column=1, value="Exit Multiple")
        ws.cell(row=7, column=2, value=scenarios['bear']['exit_multiple'])
        ws.cell(row=7, column=3, value=scenarios['base']['exit_multiple'])
        ws.cell(row=7, column=4, value=scenarios['bull']['exit_multiple'])
        for col in range(2, 5):
            ws.cell(row=7, column=col).number_format = '0.0x'
            self._format_input_cell(ws, 7, col)

        # Probability
        ws.cell(row=8, column=1, value="Probability Weight")
        ws.cell(row=8, column=2, value=scenarios['bear']['probability'])
        ws.cell(row=8, column=3, value=scenarios['base']['probability'])
        ws.cell(row=8, column=4, value=scenarios['bull']['probability'])
        for col in range(2, 5):
            ws.cell(row=8, column=col).number_format = '0%'
            self._format_input_cell(ws, 8, col)

        # Calculate returns for each scenario
        scenario_results = {}
        for key, scenario in scenarios.items():
            # Calculate exit EBITDA
            revenues = [a.ltm_revenue]
            for g in scenario['revenue_growth']:
                revenues.append(revenues[-1] * (1 + g))
            exit_ebitda = revenues[-1] * scenario['ebitda_margin'][-1]

            # Exit EV and equity
            exit_ev = exit_ebitda * scenario['exit_multiple']
            debt_at_exit = total_debt * 0.50  # Simplified
            exit_equity = exit_ev - debt_at_exit

            moic = exit_equity / equity_check
            irr = (moic ** (1 / a.hold_period)) - 1

            scenario_results[key] = {
                'exit_revenue': revenues[-1],
                'exit_ebitda': exit_ebitda,
                'exit_ev': exit_ev,
                'exit_equity': exit_equity,
                'moic': moic,
                'irr': irr,
            }

        # Scenario Outputs
        self._add_section_header(ws, "Scenario Outputs ($M)", 10, 1)

        output_headers = ["Metric", "Bear Case", "Base Case", "Bull Case"]
        for i, h in enumerate(output_headers):
            ws.cell(row=11, column=1 + i, value=h)
        self._format_header_row(ws, 11, 1, 4)

        outputs = [
            ("Exit Revenue", 'exit_revenue', '#,##0.0'),
            ("Exit EBITDA", 'exit_ebitda', '#,##0.0'),
            ("Exit EV", 'exit_ev', '#,##0.0'),
            ("Exit Equity Value", 'exit_equity', '#,##0.0'),
            ("MOIC", 'moic', '0.00x'),
            ("IRR", 'irr', '0.0%'),
        ]

        for i, (label, key, fmt) in enumerate(outputs):
            row = 12 + i
            ws.cell(row=row, column=1, value=label)
            ws.cell(row=row, column=2, value=scenario_results['bear'][key])
            ws.cell(row=row, column=3, value=scenario_results['base'][key])
            ws.cell(row=row, column=4, value=scenario_results['bull'][key])
            for col in range(2, 5):
                ws.cell(row=row, column=col).number_format = fmt

        # Highlight MOIC and IRR rows
        for col in range(1, 5):
            ws.cell(row=17, column=col).font = Font(bold=True)
            ws.cell(row=18, column=col).font = Font(bold=True)

        # Probability-Weighted Returns
        self._add_section_header(ws, "Probability-Weighted Returns", 20, 1)

        weighted_moic = sum(scenario_results[k]['moic'] * scenarios[k]['probability'] for k in scenarios)
        weighted_irr = sum(scenario_results[k]['irr'] * scenarios[k]['probability'] for k in scenarios)

        ws.cell(row=21, column=1, value="Expected MOIC")
        ws.cell(row=21, column=2, value=weighted_moic)
        ws.cell(row=21, column=2).number_format = '0.00x'
        ws.cell(row=21, column=2).font = Font(bold=True, size=14)
        ws.cell(row=21, column=2).fill = PatternFill(start_color="90EE90", end_color="90EE90", fill_type="solid")

        ws.cell(row=22, column=1, value="Expected IRR")
        ws.cell(row=22, column=2, value=weighted_irr)
        ws.cell(row=22, column=2).number_format = '0.0%'
        ws.cell(row=22, column=2).font = Font(bold=True, size=14)
        ws.cell(row=22, column=2).fill = PatternFill(start_color="90EE90", end_color="90EE90", fill_type="solid")

        # Downside Protection
        self._add_section_header(ws, "Downside Protection", 24, 1)

        bear_moic = scenario_results['bear']['moic']
        ws.cell(row=25, column=1, value="Bear Case MOIC")
        ws.cell(row=25, column=2, value=bear_moic)
        ws.cell(row=25, column=2).number_format = '0.00x'

        ws.cell(row=26, column=1, value="Capital Protected?")
        ws.cell(row=26, column=2, value="Yes" if bear_moic >= 1.0 else "No")
        if bear_moic >= 1.0:
            ws.cell(row=26, column=2).fill = PatternFill(start_color="90EE90", end_color="90EE90", fill_type="solid")
        else:
            ws.cell(row=26, column=2).fill = PatternFill(start_color="FF9090", end_color="FF9090", fill_type="solid")

        # Set column widths
        ws.column_dimensions['A'].width = 22
        for col in ['B', 'C', 'D']:
            ws.column_dimensions[col].width = 14

        return self

    # ============================================================
    # MODULE: MANAGEMENT VS BUYER CASE
    # ============================================================

    def add_management_vs_buyer(self, data: Dict = None) -> 'ExcelModelGenerator':
        """Add Management Case vs Buyer Case comparison sheet."""
        ws = self.wb.create_sheet("Mgmt vs Buyer Case")
        self.sheets_created.append("Mgmt vs Buyer Case")

        a = self.assumptions
        data = data or {}

        # Define cases
        mgmt_case = data.get('management', {
            'revenue_growth': [0.12, 0.10, 0.09, 0.08, 0.07],
            'ebitda_margin': [0.22, 0.24, 0.25, 0.26, 0.27],
            'capex_pct': 0.04,
            'nwc_pct': 0.08,
        })

        buyer_case = data.get('buyer', {
            'revenue_growth': [0.08, 0.07, 0.06, 0.05, 0.05],
            'ebitda_margin': [0.20, 0.21, 0.22, 0.22, 0.22],
            'capex_pct': 0.05,
            'nwc_pct': 0.10,
        })

        # Title
        self._add_title(ws, f"{self.company_name} - Management vs Buyer Case", 1, 1)

        # Year headers
        ws.cell(row=3, column=1, value="")
        ws.cell(row=3, column=2, value="LTM")
        for i in range(self.projection_years):
            ws.cell(row=3, column=3 + i, value=f"Year {i + 1}")
        self._format_header_row(ws, 3, 1, 2 + self.projection_years)

        # Management Case Section
        self._add_section_header(ws, "MANAGEMENT CASE", 4, 1)

        # Management revenue
        mgmt_revenues = [a.ltm_revenue]
        for g in mgmt_case['revenue_growth']:
            mgmt_revenues.append(mgmt_revenues[-1] * (1 + g))

        ws.cell(row=5, column=1, value="Revenue")
        for i, rev in enumerate(mgmt_revenues):
            ws.cell(row=5, column=2 + i, value=rev)
            ws.cell(row=5, column=2 + i).number_format = '#,##0.0'

        # Management growth
        ws.cell(row=6, column=1, value="  % Growth")
        ws.cell(row=6, column=2, value="—")
        for i, g in enumerate(mgmt_case['revenue_growth']):
            ws.cell(row=6, column=3 + i, value=g)
            ws.cell(row=6, column=3 + i).number_format = '0.0%'
            ws.cell(row=6, column=3 + i).font = Font(italic=True, color="666666")

        # Management EBITDA
        mgmt_ebitdas = [a.ltm_ebitda]
        for i, margin in enumerate(mgmt_case['ebitda_margin']):
            mgmt_ebitdas.append(mgmt_revenues[i + 1] * margin)

        ws.cell(row=7, column=1, value="EBITDA")
        for i, ebitda in enumerate(mgmt_ebitdas):
            ws.cell(row=7, column=2 + i, value=ebitda)
            ws.cell(row=7, column=2 + i).number_format = '#,##0.0'
            ws.cell(row=7, column=2 + i).font = Font(bold=True)

        # Management margin
        ws.cell(row=8, column=1, value="  % Margin")
        ws.cell(row=8, column=2, value=a.ltm_ebitda / a.ltm_revenue)
        ws.cell(row=8, column=2).number_format = '0.0%'
        for i, margin in enumerate(mgmt_case['ebitda_margin']):
            ws.cell(row=8, column=3 + i, value=margin)
            ws.cell(row=8, column=3 + i).number_format = '0.0%'
            ws.cell(row=8, column=3 + i).font = Font(italic=True, color="666666")

        # Buyer Case Section
        self._add_section_header(ws, "BUYER CASE (HAIRCUT)", 10, 1)

        # Buyer revenue
        buyer_revenues = [a.ltm_revenue]
        for g in buyer_case['revenue_growth']:
            buyer_revenues.append(buyer_revenues[-1] * (1 + g))

        ws.cell(row=11, column=1, value="Revenue")
        for i, rev in enumerate(buyer_revenues):
            ws.cell(row=11, column=2 + i, value=rev)
            ws.cell(row=11, column=2 + i).number_format = '#,##0.0'

        # Buyer growth
        ws.cell(row=12, column=1, value="  % Growth")
        ws.cell(row=12, column=2, value="—")
        for i, g in enumerate(buyer_case['revenue_growth']):
            ws.cell(row=12, column=3 + i, value=g)
            ws.cell(row=12, column=3 + i).number_format = '0.0%'
            ws.cell(row=12, column=3 + i).font = Font(italic=True, color="666666")

        # Buyer EBITDA
        buyer_ebitdas = [a.ltm_ebitda]
        for i, margin in enumerate(buyer_case['ebitda_margin']):
            buyer_ebitdas.append(buyer_revenues[i + 1] * margin)

        ws.cell(row=13, column=1, value="EBITDA")
        for i, ebitda in enumerate(buyer_ebitdas):
            ws.cell(row=13, column=2 + i, value=ebitda)
            ws.cell(row=13, column=2 + i).number_format = '#,##0.0'
            ws.cell(row=13, column=2 + i).font = Font(bold=True)

        # Buyer margin
        ws.cell(row=14, column=1, value="  % Margin")
        ws.cell(row=14, column=2, value=a.ltm_ebitda / a.ltm_revenue)
        ws.cell(row=14, column=2).number_format = '0.0%'
        for i, margin in enumerate(buyer_case['ebitda_margin']):
            ws.cell(row=14, column=3 + i, value=margin)
            ws.cell(row=14, column=3 + i).number_format = '0.0%'
            ws.cell(row=14, column=3 + i).font = Font(italic=True, color="666666")

        # Variance Analysis
        self._add_section_header(ws, "VARIANCE ANALYSIS", 16, 1)

        ws.cell(row=17, column=1, value="Revenue Variance")
        for i in range(len(mgmt_revenues)):
            variance = buyer_revenues[i] - mgmt_revenues[i]
            pct_variance = variance / mgmt_revenues[i] if mgmt_revenues[i] != 0 else 0
            ws.cell(row=17, column=2 + i, value=variance)
            ws.cell(row=17, column=2 + i).number_format = '#,##0.0'
            if variance < 0:
                ws.cell(row=17, column=2 + i).font = Font(color="FF0000")

        ws.cell(row=18, column=1, value="  % Variance")
        for i in range(len(mgmt_revenues)):
            pct_variance = (buyer_revenues[i] - mgmt_revenues[i]) / mgmt_revenues[i] if mgmt_revenues[i] != 0 else 0
            ws.cell(row=18, column=2 + i, value=pct_variance)
            ws.cell(row=18, column=2 + i).number_format = '0.0%'
            if pct_variance < 0:
                ws.cell(row=18, column=2 + i).font = Font(color="FF0000", italic=True)

        ws.cell(row=20, column=1, value="EBITDA Variance")
        for i in range(len(mgmt_ebitdas)):
            variance = buyer_ebitdas[i] - mgmt_ebitdas[i]
            ws.cell(row=20, column=2 + i, value=variance)
            ws.cell(row=20, column=2 + i).number_format = '#,##0.0'
            if variance < 0:
                ws.cell(row=20, column=2 + i).font = Font(color="FF0000")

        ws.cell(row=21, column=1, value="  % Variance")
        for i in range(len(mgmt_ebitdas)):
            pct_variance = (buyer_ebitdas[i] - mgmt_ebitdas[i]) / mgmt_ebitdas[i] if mgmt_ebitdas[i] != 0 else 0
            ws.cell(row=21, column=2 + i, value=pct_variance)
            ws.cell(row=21, column=2 + i).number_format = '0.0%'
            if pct_variance < 0:
                ws.cell(row=21, column=2 + i).font = Font(color="FF0000", italic=True)

        # Returns Comparison
        self._add_section_header(ws, "RETURNS COMPARISON (Year 5 Exit)", 23, 1)

        ev = a.ltm_ebitda * a.entry_multiple
        total_debt = a.ltm_ebitda * (a.senior_debt_multiple + a.sub_debt_multiple)
        fees = ev * 0.04
        equity_check = ev + fees - total_debt
        debt_at_exit = total_debt * 0.50

        # Management case returns
        mgmt_exit_ev = mgmt_ebitdas[-1] * a.exit_multiple
        mgmt_exit_equity = mgmt_exit_ev - debt_at_exit
        mgmt_moic = mgmt_exit_equity / equity_check
        mgmt_irr = (mgmt_moic ** (1 / a.hold_period)) - 1

        # Buyer case returns
        buyer_exit_ev = buyer_ebitdas[-1] * a.exit_multiple
        buyer_exit_equity = buyer_exit_ev - debt_at_exit
        buyer_moic = buyer_exit_equity / equity_check
        buyer_irr = (buyer_moic ** (1 / a.hold_period)) - 1

        ws.cell(row=24, column=1, value="")
        ws.cell(row=24, column=2, value="Management")
        ws.cell(row=24, column=3, value="Buyer")
        ws.cell(row=24, column=4, value="Difference")
        self._format_header_row(ws, 24, 1, 4)

        ws.cell(row=25, column=1, value="Exit EBITDA")
        ws.cell(row=25, column=2, value=mgmt_ebitdas[-1])
        ws.cell(row=25, column=3, value=buyer_ebitdas[-1])
        ws.cell(row=25, column=4, value=buyer_ebitdas[-1] - mgmt_ebitdas[-1])
        for col in range(2, 5):
            ws.cell(row=25, column=col).number_format = '#,##0.0'

        ws.cell(row=26, column=1, value="Exit Equity")
        ws.cell(row=26, column=2, value=mgmt_exit_equity)
        ws.cell(row=26, column=3, value=buyer_exit_equity)
        ws.cell(row=26, column=4, value=buyer_exit_equity - mgmt_exit_equity)
        for col in range(2, 5):
            ws.cell(row=26, column=col).number_format = '#,##0.0'

        ws.cell(row=27, column=1, value="MOIC")
        ws.cell(row=27, column=2, value=mgmt_moic)
        ws.cell(row=27, column=3, value=buyer_moic)
        ws.cell(row=27, column=4, value=buyer_moic - mgmt_moic)
        for col in range(2, 5):
            ws.cell(row=27, column=col).number_format = '0.00x'
            ws.cell(row=27, column=col).font = Font(bold=True)

        ws.cell(row=28, column=1, value="IRR")
        ws.cell(row=28, column=2, value=mgmt_irr)
        ws.cell(row=28, column=3, value=buyer_irr)
        ws.cell(row=28, column=4, value=buyer_irr - mgmt_irr)
        for col in range(2, 5):
            ws.cell(row=28, column=col).number_format = '0.0%'
            ws.cell(row=28, column=col).font = Font(bold=True)

        # Color code the buyer case (what we're underwriting to)
        for row in range(25, 29):
            ws.cell(row=row, column=3).fill = PatternFill(start_color="90EE90", end_color="90EE90", fill_type="solid")

        # Set column widths
        ws.column_dimensions['A'].width = 20
        for i in range(self.projection_years + 3):
            ws.column_dimensions[get_column_letter(2 + i)].width = 12

        return self

    # ============================================================
    # MODULE: DCF VALUATION
    # ============================================================

    def add_dcf_valuation(self, data: Dict = None) -> 'ExcelModelGenerator':
        """Add DCF Valuation sheet."""
        ws = self.wb.create_sheet("DCF Valuation")
        self.sheets_created.append("DCF Valuation")

        a = self.assumptions
        data = data or {}

        # WACC
        wacc = data.get('wacc', 0.10)
        terminal_growth = data.get('terminal_growth', 0.025)

        # Calculate projections
        revenues = [a.ltm_revenue]
        for g in a.revenue_growth:
            revenues.append(revenues[-1] * (1 + g))

        margins = [a.ltm_ebitda / a.ltm_revenue] + list(a.ebitda_margin)
        ebitdas = [revenues[i] * margins[i] for i in range(len(revenues))]

        # Title
        self._add_title(ws, f"{self.company_name} - DCF Valuation", 1, 1)

        # Assumptions
        self._add_section_header(ws, "DCF Assumptions", 3, 1)

        ws.cell(row=4, column=1, value="WACC")
        ws.cell(row=4, column=2, value=wacc)
        ws.cell(row=4, column=2).number_format = '0.0%'
        self._format_input_cell(ws, 4, 2)

        ws.cell(row=5, column=1, value="Terminal Growth Rate")
        ws.cell(row=5, column=2, value=terminal_growth)
        ws.cell(row=5, column=2).number_format = '0.0%'
        self._format_input_cell(ws, 5, 2)

        ws.cell(row=6, column=1, value="Tax Rate")
        ws.cell(row=6, column=2, value=a.tax_rate)
        ws.cell(row=6, column=2).number_format = '0.0%'
        self._format_input_cell(ws, 6, 2)

        # Year headers
        ws.cell(row=8, column=1, value="")
        for i in range(self.projection_years):
            ws.cell(row=8, column=2 + i, value=f"Year {i + 1}")
        ws.cell(row=8, column=2 + self.projection_years, value="Terminal")
        self._format_header_row(ws, 8, 1, 2 + self.projection_years)

        # Free Cash Flow Build
        self._add_section_header(ws, "Unlevered Free Cash Flow ($M)", 9, 1)

        # EBITDA
        ws.cell(row=10, column=1, value="EBITDA")
        for i in range(self.projection_years):
            ws.cell(row=10, column=2 + i, value=ebitdas[i + 1])
            ws.cell(row=10, column=2 + i).number_format = '#,##0.0'

        # D&A (assume = CapEx)
        capex = [rev * a.capex_pct_revenue for rev in revenues]
        ws.cell(row=11, column=1, value="Less: D&A")
        for i in range(self.projection_years):
            ws.cell(row=11, column=2 + i, value=-capex[i + 1])
            ws.cell(row=11, column=2 + i).number_format = '(#,##0.0)'

        # EBIT
        ws.cell(row=12, column=1, value="EBIT")
        for i in range(self.projection_years):
            ebit = ebitdas[i + 1] - capex[i + 1]
            ws.cell(row=12, column=2 + i, value=ebit)
            ws.cell(row=12, column=2 + i).number_format = '#,##0.0'

        # Taxes
        ws.cell(row=13, column=1, value="Less: Taxes")
        for i in range(self.projection_years):
            ebit = ebitdas[i + 1] - capex[i + 1]
            taxes = -ebit * a.tax_rate
            ws.cell(row=13, column=2 + i, value=taxes)
            ws.cell(row=13, column=2 + i).number_format = '(#,##0.0)'

        # NOPAT
        ws.cell(row=14, column=1, value="NOPAT")
        for i in range(self.projection_years):
            ebit = ebitdas[i + 1] - capex[i + 1]
            nopat = ebit * (1 - a.tax_rate)
            ws.cell(row=14, column=2 + i, value=nopat)
            ws.cell(row=14, column=2 + i).number_format = '#,##0.0'

        # Add back D&A
        ws.cell(row=15, column=1, value="Plus: D&A")
        for i in range(self.projection_years):
            ws.cell(row=15, column=2 + i, value=capex[i + 1])
            ws.cell(row=15, column=2 + i).number_format = '#,##0.0'

        # CapEx
        ws.cell(row=16, column=1, value="Less: CapEx")
        for i in range(self.projection_years):
            ws.cell(row=16, column=2 + i, value=-capex[i + 1])
            ws.cell(row=16, column=2 + i).number_format = '(#,##0.0)'

        # Change in NWC
        nwc = [rev * a.nwc_pct_revenue for rev in revenues]
        ws.cell(row=17, column=1, value="Less: Change in NWC")
        for i in range(self.projection_years):
            delta_nwc = -(nwc[i + 1] - nwc[i])
            ws.cell(row=17, column=2 + i, value=delta_nwc)
            ws.cell(row=17, column=2 + i).number_format = '(#,##0.0)'

        # Unlevered FCF
        ufcfs = []
        ws.cell(row=18, column=1, value="Unlevered FCF")
        for i in range(self.projection_years):
            ebit = ebitdas[i + 1] - capex[i + 1]
            nopat = ebit * (1 - a.tax_rate)
            delta_nwc = nwc[i + 1] - nwc[i]
            ufcf = nopat - delta_nwc  # D&A and CapEx cancel out
            ufcfs.append(ufcf)
            ws.cell(row=18, column=2 + i, value=ufcf)
            ws.cell(row=18, column=2 + i).number_format = '#,##0.0'
            ws.cell(row=18, column=2 + i).font = Font(bold=True)
            ws.cell(row=18, column=2 + i).border = DOUBLE_BORDER

        # Terminal Value
        terminal_fcf = ufcfs[-1] * (1 + terminal_growth)
        terminal_value = terminal_fcf / (wacc - terminal_growth)

        ws.cell(row=18, column=2 + self.projection_years, value=terminal_value)
        ws.cell(row=18, column=2 + self.projection_years).number_format = '#,##0.0'
        ws.cell(row=18, column=2 + self.projection_years).font = Font(bold=True)

        # Discount Factors
        self._add_section_header(ws, "Present Value Calculation", 20, 1)

        ws.cell(row=21, column=1, value="Discount Factor")
        for i in range(self.projection_years):
            df = 1 / ((1 + wacc) ** (i + 1))
            ws.cell(row=21, column=2 + i, value=df)
            ws.cell(row=21, column=2 + i).number_format = '0.000'

        # Terminal discount factor
        terminal_df = 1 / ((1 + wacc) ** self.projection_years)
        ws.cell(row=21, column=2 + self.projection_years, value=terminal_df)
        ws.cell(row=21, column=2 + self.projection_years).number_format = '0.000'

        # Present Values
        ws.cell(row=22, column=1, value="Present Value")
        pv_fcfs = []
        for i in range(self.projection_years):
            df = 1 / ((1 + wacc) ** (i + 1))
            pv = ufcfs[i] * df
            pv_fcfs.append(pv)
            ws.cell(row=22, column=2 + i, value=pv)
            ws.cell(row=22, column=2 + i).number_format = '#,##0.0'

        pv_terminal = terminal_value * terminal_df
        ws.cell(row=22, column=2 + self.projection_years, value=pv_terminal)
        ws.cell(row=22, column=2 + self.projection_years).number_format = '#,##0.0'

        # Valuation Summary
        self._add_section_header(ws, "Valuation Summary ($M)", 24, 1)

        sum_pv_fcf = sum(pv_fcfs)

        ws.cell(row=25, column=1, value="PV of Projection Period FCF")
        ws.cell(row=25, column=2, value=sum_pv_fcf)
        ws.cell(row=25, column=2).number_format = '#,##0.0'

        ws.cell(row=26, column=1, value="PV of Terminal Value")
        ws.cell(row=26, column=2, value=pv_terminal)
        ws.cell(row=26, column=2).number_format = '#,##0.0'

        enterprise_value = sum_pv_fcf + pv_terminal
        ws.cell(row=27, column=1, value="Enterprise Value")
        ws.cell(row=27, column=2, value=enterprise_value)
        ws.cell(row=27, column=2).number_format = '#,##0.0'
        ws.cell(row=27, column=2).font = Font(bold=True, size=14)
        ws.cell(row=27, column=2).fill = PatternFill(start_color="90EE90", end_color="90EE90", fill_type="solid")

        # Implied multiples
        ws.cell(row=29, column=1, value="Implied EV / LTM EBITDA")
        ws.cell(row=29, column=2, value=enterprise_value / a.ltm_ebitda)
        ws.cell(row=29, column=2).number_format = '0.0x'

        ws.cell(row=30, column=1, value="Implied EV / Exit EBITDA")
        ws.cell(row=30, column=2, value=enterprise_value / ebitdas[-1])
        ws.cell(row=30, column=2).number_format = '0.0x'

        # Terminal Value as % of total
        tv_pct = pv_terminal / enterprise_value
        ws.cell(row=31, column=1, value="Terminal Value % of EV")
        ws.cell(row=31, column=2, value=tv_pct)
        ws.cell(row=31, column=2).number_format = '0.0%'

        # Set column widths
        ws.column_dimensions['A'].width = 25
        for i in range(self.projection_years + 2):
            ws.column_dimensions[get_column_letter(2 + i)].width = 12

        return self

    # ============================================================
    # MODULE: COVENANT ANALYSIS
    # ============================================================

    def add_covenant_analysis(self, data: Dict = None) -> 'ExcelModelGenerator':
        """Add Covenant Analysis sheet."""
        ws = self.wb.create_sheet("Covenant Analysis")
        self.sheets_created.append("Covenant Analysis")

        a = self.assumptions
        data = data or {}

        # Covenant thresholds
        covenants = data.get('covenants', {
            'max_leverage': 6.0,
            'min_interest_coverage': 2.0,
            'min_fixed_charge': 1.1,
        })

        # Calculate projections
        revenues = [a.ltm_revenue]
        for g in a.revenue_growth:
            revenues.append(revenues[-1] * (1 + g))

        margins = [a.ltm_ebitda / a.ltm_revenue] + list(a.ebitda_margin)
        ebitdas = [revenues[i] * margins[i] for i in range(len(revenues))]

        # Debt balances (simplified)
        total_debt_initial = a.ltm_ebitda * (a.senior_debt_multiple + a.sub_debt_multiple)
        debt_balances = [total_debt_initial]
        annual_paydown = total_debt_initial * 0.10
        for i in range(self.projection_years):
            debt_balances.append(max(0, debt_balances[-1] - annual_paydown))

        # Interest (blended rate)
        blended_rate = (a.senior_interest_rate * a.senior_debt_multiple +
                       a.sub_interest_rate * a.sub_debt_multiple) / (a.senior_debt_multiple + a.sub_debt_multiple)

        # Title
        self._add_title(ws, f"{self.company_name} - Covenant Analysis", 1, 1)

        # Covenant Thresholds
        self._add_section_header(ws, "Covenant Thresholds", 3, 1)

        ws.cell(row=4, column=1, value="Maximum Leverage (Debt/EBITDA)")
        ws.cell(row=4, column=2, value=covenants['max_leverage'])
        ws.cell(row=4, column=2).number_format = '0.0x'
        self._format_input_cell(ws, 4, 2)

        ws.cell(row=5, column=1, value="Minimum Interest Coverage")
        ws.cell(row=5, column=2, value=covenants['min_interest_coverage'])
        ws.cell(row=5, column=2).number_format = '0.0x'
        self._format_input_cell(ws, 5, 2)

        ws.cell(row=6, column=1, value="Minimum Fixed Charge Coverage")
        ws.cell(row=6, column=2, value=covenants['min_fixed_charge'])
        ws.cell(row=6, column=2).number_format = '0.0x'
        self._format_input_cell(ws, 6, 2)

        # Year headers
        ws.cell(row=8, column=1, value="")
        ws.cell(row=8, column=2, value="Entry")
        for i in range(self.projection_years):
            ws.cell(row=8, column=3 + i, value=f"Year {i + 1}")
        self._format_header_row(ws, 8, 1, 2 + self.projection_years)

        # Leverage Ratio
        self._add_section_header(ws, "Leverage Ratio (Debt / EBITDA)", 9, 1)

        ws.cell(row=10, column=1, value="Total Debt")
        for i, debt in enumerate(debt_balances):
            ws.cell(row=10, column=2 + i, value=debt)
            ws.cell(row=10, column=2 + i).number_format = '#,##0.0'

        ws.cell(row=11, column=1, value="EBITDA")
        for i, ebitda in enumerate(ebitdas):
            ws.cell(row=11, column=2 + i, value=ebitda)
            ws.cell(row=11, column=2 + i).number_format = '#,##0.0'

        ws.cell(row=12, column=1, value="Leverage Ratio")
        for i in range(len(debt_balances)):
            ratio = debt_balances[i] / ebitdas[i] if ebitdas[i] > 0 else 0
            cell = ws.cell(row=12, column=2 + i, value=ratio)
            cell.number_format = '0.0x'
            cell.font = Font(bold=True)
            # Color code vs covenant
            if ratio <= covenants['max_leverage']:
                cell.fill = PatternFill(start_color="90EE90", end_color="90EE90", fill_type="solid")
            else:
                cell.fill = PatternFill(start_color="FF9090", end_color="FF9090", fill_type="solid")

        ws.cell(row=13, column=1, value="Covenant")
        for i in range(len(debt_balances)):
            ws.cell(row=13, column=2 + i, value=covenants['max_leverage'])
            ws.cell(row=13, column=2 + i).number_format = '0.0x'
            ws.cell(row=13, column=2 + i).font = Font(italic=True, color="666666")

        ws.cell(row=14, column=1, value="Headroom")
        for i in range(len(debt_balances)):
            ratio = debt_balances[i] / ebitdas[i] if ebitdas[i] > 0 else 0
            headroom = covenants['max_leverage'] - ratio
            cell = ws.cell(row=14, column=2 + i, value=headroom)
            cell.number_format = '0.0x'
            if headroom < 0.5:
                cell.font = Font(color="FF0000")

        # Interest Coverage
        self._add_section_header(ws, "Interest Coverage (EBITDA / Interest)", 16, 1)

        ws.cell(row=17, column=1, value="EBITDA")
        for i in range(self.projection_years):
            ws.cell(row=17, column=3 + i, value=ebitdas[i + 1])
            ws.cell(row=17, column=3 + i).number_format = '#,##0.0'

        ws.cell(row=18, column=1, value="Interest Expense")
        for i in range(self.projection_years):
            avg_debt = (debt_balances[i] + debt_balances[i + 1]) / 2
            interest = avg_debt * blended_rate
            ws.cell(row=18, column=3 + i, value=interest)
            ws.cell(row=18, column=3 + i).number_format = '#,##0.0'

        ws.cell(row=19, column=1, value="Interest Coverage")
        for i in range(self.projection_years):
            avg_debt = (debt_balances[i] + debt_balances[i + 1]) / 2
            interest = avg_debt * blended_rate
            coverage = ebitdas[i + 1] / interest if interest > 0 else 99
            cell = ws.cell(row=19, column=3 + i, value=coverage)
            cell.number_format = '0.0x'
            cell.font = Font(bold=True)
            if coverage >= covenants['min_interest_coverage']:
                cell.fill = PatternFill(start_color="90EE90", end_color="90EE90", fill_type="solid")
            else:
                cell.fill = PatternFill(start_color="FF9090", end_color="FF9090", fill_type="solid")

        ws.cell(row=20, column=1, value="Covenant")
        for i in range(self.projection_years):
            ws.cell(row=20, column=3 + i, value=covenants['min_interest_coverage'])
            ws.cell(row=20, column=3 + i).number_format = '0.0x'
            ws.cell(row=20, column=3 + i).font = Font(italic=True, color="666666")

        # Compliance Summary
        self._add_section_header(ws, "Compliance Summary", 22, 1)

        # Check all years
        all_compliant = True
        for i in range(self.projection_years):
            leverage = debt_balances[i + 1] / ebitdas[i + 1] if ebitdas[i + 1] > 0 else 99
            avg_debt = (debt_balances[i] + debt_balances[i + 1]) / 2
            interest = avg_debt * blended_rate
            coverage = ebitdas[i + 1] / interest if interest > 0 else 99

            if leverage > covenants['max_leverage'] or coverage < covenants['min_interest_coverage']:
                all_compliant = False
                break

        ws.cell(row=23, column=1, value="Overall Compliance")
        ws.cell(row=23, column=2, value="PASS" if all_compliant else "FAIL")
        if all_compliant:
            ws.cell(row=23, column=2).fill = PatternFill(start_color="90EE90", end_color="90EE90", fill_type="solid")
        else:
            ws.cell(row=23, column=2).fill = PatternFill(start_color="FF9090", end_color="FF9090", fill_type="solid")
        ws.cell(row=23, column=2).font = Font(bold=True, size=14)

        # Set column widths
        ws.column_dimensions['A'].width = 28
        for i in range(self.projection_years + 2):
            ws.column_dimensions[get_column_letter(2 + i)].width = 12

        return self

    # ============================================================
    # DUE DILIGENCE & QUALITY MODULES
    # ============================================================

    # ============================================================
    # MODULE: QUALITY OF EARNINGS (QoE)
    # ============================================================

    def add_quality_of_earnings(self, data: Dict = None) -> 'ExcelModelGenerator':
        """
        Add Quality of Earnings analysis sheet.
        Includes EBITDA normalization, one-time adjustments, and run-rate analysis.
        """
        ws = self.wb.create_sheet("Quality of Earnings")
        self.sheets_created.append("Quality of Earnings")

        a = self.assumptions
        data = data or {}

        # Title
        self._add_title(ws, f"{self.company_name} - Quality of Earnings Analysis", 1, 1)

        # Reported EBITDA Section
        self._add_section_header(ws, "REPORTED EBITDA ($M)", 3, 1)

        # Headers
        ws.cell(row=4, column=1, value="")
        ws.cell(row=4, column=2, value="LTM")
        ws.cell(row=4, column=3, value="FY-1")
        ws.cell(row=4, column=4, value="FY-2")
        self._format_header_row(ws, 4, 1, 4)

        # Reported figures
        reported_ltm = data.get('reported_ebitda_ltm', a.ltm_ebitda)
        reported_fy1 = data.get('reported_ebitda_fy1', a.ltm_ebitda * 0.92)
        reported_fy2 = data.get('reported_ebitda_fy2', a.ltm_ebitda * 0.85)

        ws.cell(row=5, column=1, value="Reported EBITDA")
        ws.cell(row=5, column=2, value=reported_ltm)
        ws.cell(row=5, column=3, value=reported_fy1)
        ws.cell(row=5, column=4, value=reported_fy2)
        for col in range(2, 5):
            ws.cell(row=5, column=col).number_format = '#,##0.0'
            ws.cell(row=5, column=col).font = Font(bold=True)

        # Adjustments Section
        self._add_section_header(ws, "EBITDA ADJUSTMENTS", 7, 1)

        adjustments = data.get('adjustments', [
            {'name': 'Owner compensation normalization', 'ltm': 2.0, 'fy1': 1.8, 'fy2': 1.5},
            {'name': 'One-time legal/settlement costs', 'ltm': 1.5, 'fy1': 0.5, 'fy2': 2.0},
            {'name': 'Non-recurring consulting fees', 'ltm': 0.8, 'fy1': 1.2, 'fy2': 0.3},
            {'name': 'Related party transaction adjustment', 'ltm': 0.5, 'fy1': 0.5, 'fy2': 0.5},
            {'name': 'Inventory write-down (non-recurring)', 'ltm': 0.0, 'fy1': 1.0, 'fy2': 0.0},
            {'name': 'Stock-based compensation', 'ltm': 1.2, 'fy1': 1.0, 'fy2': 0.8},
            {'name': 'Transaction costs (add-back)', 'ltm': 0.5, 'fy1': 0.0, 'fy2': 0.0},
            {'name': 'Cost savings (run-rate)', 'ltm': 1.5, 'fy1': 0.0, 'fy2': 0.0},
        ])

        row = 8
        total_adj = {'ltm': 0, 'fy1': 0, 'fy2': 0}
        for adj in adjustments:
            ws.cell(row=row, column=1, value=f"  {adj['name']}")
            ws.cell(row=row, column=2, value=adj['ltm'])
            ws.cell(row=row, column=3, value=adj['fy1'])
            ws.cell(row=row, column=4, value=adj['fy2'])
            total_adj['ltm'] += adj['ltm']
            total_adj['fy1'] += adj['fy1']
            total_adj['fy2'] += adj['fy2']
            for col in range(2, 5):
                ws.cell(row=row, column=col).number_format = '#,##0.0'
                ws.cell(row=row, column=col).font = Font(color="0066CC")
            row += 1

        # Total Adjustments
        row += 1
        ws.cell(row=row, column=1, value="Total Adjustments")
        ws.cell(row=row, column=2, value=total_adj['ltm'])
        ws.cell(row=row, column=3, value=total_adj['fy1'])
        ws.cell(row=row, column=4, value=total_adj['fy2'])
        for col in range(2, 5):
            ws.cell(row=row, column=col).number_format = '#,##0.0'
            ws.cell(row=row, column=col).font = Font(bold=True)
            ws.cell(row=row, column=col).border = Border(top=Side(style='thin'))

        # Adjusted EBITDA
        row += 2
        self._add_section_header(ws, "ADJUSTED EBITDA", row, 1)
        row += 1

        adj_ltm = reported_ltm + total_adj['ltm']
        adj_fy1 = reported_fy1 + total_adj['fy1']
        adj_fy2 = reported_fy2 + total_adj['fy2']

        ws.cell(row=row, column=1, value="Adjusted EBITDA")
        ws.cell(row=row, column=2, value=adj_ltm)
        ws.cell(row=row, column=3, value=adj_fy1)
        ws.cell(row=row, column=4, value=adj_fy2)
        for col in range(2, 5):
            ws.cell(row=row, column=col).number_format = '#,##0.0'
            ws.cell(row=row, column=col).font = Font(bold=True)
            ws.cell(row=row, column=col).fill = PatternFill(start_color="90EE90", end_color="90EE90", fill_type="solid")

        row += 1
        ws.cell(row=row, column=1, value="  % Adjustment")
        ws.cell(row=row, column=2, value=total_adj['ltm'] / reported_ltm if reported_ltm else 0)
        ws.cell(row=row, column=3, value=total_adj['fy1'] / reported_fy1 if reported_fy1 else 0)
        ws.cell(row=row, column=4, value=total_adj['fy2'] / reported_fy2 if reported_fy2 else 0)
        for col in range(2, 5):
            ws.cell(row=row, column=col).number_format = '0.0%'
            ws.cell(row=row, column=col).font = Font(italic=True, color="666666")

        # Run-Rate Analysis
        row += 2
        self._add_section_header(ws, "RUN-RATE EBITDA ANALYSIS", row, 1)
        row += 1

        run_rate_items = data.get('run_rate_items', [
            {'name': 'Adjusted LTM EBITDA', 'value': adj_ltm, 'type': 'base'},
            {'name': 'Full-year impact of price increase', 'value': 1.5, 'type': 'add'},
            {'name': 'Annualized new customer wins', 'value': 2.0, 'type': 'add'},
            {'name': 'Full-year cost savings', 'value': 1.0, 'type': 'add'},
            {'name': 'Lost customer annualization', 'value': -0.5, 'type': 'add'},
        ])

        run_rate = 0
        for item in run_rate_items:
            ws.cell(row=row, column=1, value=item['name'])
            if item['type'] == 'base':
                ws.cell(row=row, column=2, value=item['value'])
                run_rate = item['value']
            else:
                ws.cell(row=row, column=2, value=item['value'])
                run_rate += item['value']
            ws.cell(row=row, column=2).number_format = '#,##0.0'
            row += 1

        row += 1
        ws.cell(row=row, column=1, value="Run-Rate EBITDA")
        ws.cell(row=row, column=2, value=run_rate)
        ws.cell(row=row, column=2).number_format = '#,##0.0'
        ws.cell(row=row, column=2).font = Font(bold=True)
        ws.cell(row=row, column=2).fill = PatternFill(start_color="FFFF99", end_color="FFFF99", fill_type="solid")

        # Summary Box
        row += 3
        self._add_section_header(ws, "QoE SUMMARY", row, 1)
        row += 1

        ws.cell(row=row, column=1, value="Reported LTM EBITDA")
        ws.cell(row=row, column=2, value=reported_ltm)
        ws.cell(row=row, column=2).number_format = '#,##0.0'
        row += 1

        ws.cell(row=row, column=1, value="Adjusted LTM EBITDA")
        ws.cell(row=row, column=2, value=adj_ltm)
        ws.cell(row=row, column=2).number_format = '#,##0.0'
        row += 1

        ws.cell(row=row, column=1, value="Run-Rate EBITDA")
        ws.cell(row=row, column=2, value=run_rate)
        ws.cell(row=row, column=2).number_format = '#,##0.0'
        row += 1

        ws.cell(row=row, column=1, value="Implied Adjustment %")
        ws.cell(row=row, column=2, value=(run_rate - reported_ltm) / reported_ltm if reported_ltm else 0)
        ws.cell(row=row, column=2).number_format = '0.0%'
        ws.cell(row=row, column=2).font = Font(bold=True)

        # Column widths
        ws.column_dimensions['A'].width = 35
        ws.column_dimensions['B'].width = 15
        ws.column_dimensions['C'].width = 15
        ws.column_dimensions['D'].width = 15

        return self

    # ============================================================
    # MODULE: WORKING CAPITAL NORMALIZATION
    # ============================================================

    def add_working_capital_normalization(self, data: Dict = None) -> 'ExcelModelGenerator':
        """
        Add Working Capital Normalization analysis sheet.
        Includes target vs actual NWC, peg mechanism analysis.
        """
        ws = self.wb.create_sheet("NWC Normalization")
        self.sheets_created.append("NWC Normalization")

        a = self.assumptions
        data = data or {}

        # Title
        self._add_title(ws, f"{self.company_name} - Working Capital Normalization", 1, 1)

        # Historical NWC Section
        self._add_section_header(ws, "HISTORICAL WORKING CAPITAL ($M)", 3, 1)

        # Headers
        headers = ["", "LTM", "FY-1", "FY-2", "FY-3", "Average"]
        for i, h in enumerate(headers):
            ws.cell(row=4, column=1 + i, value=h)
        self._format_header_row(ws, 4, 1, len(headers))

        # Historical data
        historical = data.get('historical_nwc', {
            'accounts_receivable': [25.0, 23.0, 22.0, 20.0],
            'inventory': [15.0, 14.0, 13.0, 12.0],
            'prepaid_expenses': [3.0, 2.8, 2.5, 2.3],
            'accounts_payable': [18.0, 16.0, 15.0, 14.0],
            'accrued_expenses': [8.0, 7.5, 7.0, 6.5],
            'deferred_revenue': [5.0, 4.5, 4.0, 3.5],
            'revenue': [200.0, 185.0, 170.0, 155.0],
        })

        row = 5
        # Current Assets
        ws.cell(row=row, column=1, value="Current Assets")
        ws.cell(row=row, column=1).font = Font(bold=True, italic=True)
        row += 1

        for item_name, values in [
            ("  Accounts Receivable", historical['accounts_receivable']),
            ("  Inventory", historical['inventory']),
            ("  Prepaid Expenses", historical['prepaid_expenses']),
        ]:
            ws.cell(row=row, column=1, value=item_name)
            for i, v in enumerate(values):
                ws.cell(row=row, column=2 + i, value=v)
                ws.cell(row=row, column=2 + i).number_format = '#,##0.0'
            ws.cell(row=row, column=6, value=sum(values) / len(values))
            ws.cell(row=row, column=6).number_format = '#,##0.0'
            row += 1

        # Total Current Assets
        ca_totals = []
        for i in range(4):
            total = (historical['accounts_receivable'][i] +
                    historical['inventory'][i] +
                    historical['prepaid_expenses'][i])
            ca_totals.append(total)

        ws.cell(row=row, column=1, value="Total Current Assets")
        for i, t in enumerate(ca_totals):
            ws.cell(row=row, column=2 + i, value=t)
            ws.cell(row=row, column=2 + i).number_format = '#,##0.0'
        ws.cell(row=row, column=6, value=sum(ca_totals) / len(ca_totals))
        ws.cell(row=row, column=6).number_format = '#,##0.0'
        ws.cell(row=row, column=1).font = Font(bold=True)
        row += 2

        # Current Liabilities
        ws.cell(row=row, column=1, value="Current Liabilities")
        ws.cell(row=row, column=1).font = Font(bold=True, italic=True)
        row += 1

        for item_name, values in [
            ("  Accounts Payable", historical['accounts_payable']),
            ("  Accrued Expenses", historical['accrued_expenses']),
            ("  Deferred Revenue", historical['deferred_revenue']),
        ]:
            ws.cell(row=row, column=1, value=item_name)
            for i, v in enumerate(values):
                ws.cell(row=row, column=2 + i, value=v)
                ws.cell(row=row, column=2 + i).number_format = '#,##0.0'
            ws.cell(row=row, column=6, value=sum(values) / len(values))
            ws.cell(row=row, column=6).number_format = '#,##0.0'
            row += 1

        # Total Current Liabilities
        cl_totals = []
        for i in range(4):
            total = (historical['accounts_payable'][i] +
                    historical['accrued_expenses'][i] +
                    historical['deferred_revenue'][i])
            cl_totals.append(total)

        ws.cell(row=row, column=1, value="Total Current Liabilities")
        for i, t in enumerate(cl_totals):
            ws.cell(row=row, column=2 + i, value=t)
            ws.cell(row=row, column=2 + i).number_format = '#,##0.0'
        ws.cell(row=row, column=6, value=sum(cl_totals) / len(cl_totals))
        ws.cell(row=row, column=6).number_format = '#,##0.0'
        ws.cell(row=row, column=1).font = Font(bold=True)
        row += 2

        # Net Working Capital
        nwc_totals = [ca_totals[i] - cl_totals[i] for i in range(4)]

        ws.cell(row=row, column=1, value="Net Working Capital")
        for i, nwc in enumerate(nwc_totals):
            ws.cell(row=row, column=2 + i, value=nwc)
            ws.cell(row=row, column=2 + i).number_format = '#,##0.0'
            ws.cell(row=row, column=2 + i).font = Font(bold=True)
        avg_nwc = sum(nwc_totals) / len(nwc_totals)
        ws.cell(row=row, column=6, value=avg_nwc)
        ws.cell(row=row, column=6).number_format = '#,##0.0'
        ws.cell(row=row, column=6).font = Font(bold=True)
        ws.cell(row=row, column=6).fill = PatternFill(start_color="FFFF99", end_color="FFFF99", fill_type="solid")
        row += 2

        # NWC as % of Revenue
        ws.cell(row=row, column=1, value="NWC as % of Revenue")
        revenues = historical['revenue']
        nwc_pcts = [nwc_totals[i] / revenues[i] for i in range(4)]
        for i, pct in enumerate(nwc_pcts):
            ws.cell(row=row, column=2 + i, value=pct)
            ws.cell(row=row, column=2 + i).number_format = '0.0%'
        ws.cell(row=row, column=6, value=sum(nwc_pcts) / len(nwc_pcts))
        ws.cell(row=row, column=6).number_format = '0.0%'
        ws.cell(row=row, column=6).font = Font(bold=True)
        row += 3

        # Target NWC / Peg Analysis
        self._add_section_header(ws, "NWC PEG MECHANISM", row, 1)
        row += 1

        target_nwc = data.get('target_nwc', avg_nwc)
        actual_nwc = data.get('actual_nwc', nwc_totals[0])

        ws.cell(row=row, column=1, value="Target NWC (Peg)")
        ws.cell(row=row, column=2, value=target_nwc)
        ws.cell(row=row, column=2).number_format = '#,##0.0'
        self._format_input_cell(ws, row, 2)
        row += 1

        ws.cell(row=row, column=1, value="Estimated Closing NWC")
        ws.cell(row=row, column=2, value=actual_nwc)
        ws.cell(row=row, column=2).number_format = '#,##0.0'
        self._format_input_cell(ws, row, 2)
        row += 2

        variance = actual_nwc - target_nwc
        ws.cell(row=row, column=1, value="NWC Variance")
        ws.cell(row=row, column=2, value=variance)
        ws.cell(row=row, column=2).number_format = '#,##0.0'
        if variance < 0:
            ws.cell(row=row, column=2).font = Font(bold=True, color="FF0000")
            ws.cell(row=row, column=3, value="← Buyer receives adjustment")
        else:
            ws.cell(row=row, column=2).font = Font(bold=True, color="008000")
            ws.cell(row=row, column=3, value="← Seller receives adjustment")
        row += 2

        # Days Analysis
        self._add_section_header(ws, "DAYS ANALYSIS", row, 1)
        row += 1

        ws.cell(row=row, column=1, value="")
        ws.cell(row=row, column=2, value="Current")
        ws.cell(row=row, column=3, value="Target")
        ws.cell(row=row, column=4, value="Benchmark")
        self._format_header_row(ws, row, 1, 4)
        row += 1

        ltm_revenue = revenues[0]
        ltm_cogs = ltm_revenue * 0.6  # Assume 60% COGS

        days_data = [
            ("Days Sales Outstanding (DSO)",
             historical['accounts_receivable'][0] / ltm_revenue * 365,
             data.get('target_dso', 40),
             data.get('benchmark_dso', 45)),
            ("Days Inventory Outstanding (DIO)",
             historical['inventory'][0] / ltm_cogs * 365,
             data.get('target_dio', 35),
             data.get('benchmark_dio', 40)),
            ("Days Payable Outstanding (DPO)",
             historical['accounts_payable'][0] / ltm_cogs * 365,
             data.get('target_dpo', 45),
             data.get('benchmark_dpo', 40)),
        ]

        for name, current, target, benchmark in days_data:
            ws.cell(row=row, column=1, value=name)
            ws.cell(row=row, column=2, value=current)
            ws.cell(row=row, column=3, value=target)
            ws.cell(row=row, column=4, value=benchmark)
            for col in range(2, 5):
                ws.cell(row=row, column=col).number_format = '0'
            row += 1

        # Cash Conversion Cycle
        row += 1
        dso = days_data[0][1]
        dio = days_data[1][1]
        dpo = days_data[2][1]
        ccc = dso + dio - dpo

        ws.cell(row=row, column=1, value="Cash Conversion Cycle")
        ws.cell(row=row, column=2, value=ccc)
        ws.cell(row=row, column=2).number_format = '0'
        ws.cell(row=row, column=2).font = Font(bold=True)

        # Column widths
        ws.column_dimensions['A'].width = 30
        for col in ['B', 'C', 'D', 'E', 'F']:
            ws.column_dimensions[col].width = 12

        return self

    # ============================================================
    # MODULE: CUSTOMER/REVENUE QUALITY
    # ============================================================

    def add_customer_revenue_quality(self, data: Dict = None) -> 'ExcelModelGenerator':
        """
        Add Customer/Revenue Quality analysis sheet.
        Includes cohort analysis, churn, LTV/CAC, customer concentration.
        """
        ws = self.wb.create_sheet("Revenue Quality")
        self.sheets_created.append("Revenue Quality")

        a = self.assumptions
        data = data or {}

        # Title
        self._add_title(ws, f"{self.company_name} - Customer & Revenue Quality", 1, 1)

        # Customer Concentration
        self._add_section_header(ws, "CUSTOMER CONCENTRATION", 3, 1)

        headers = ["Customer", "Revenue ($M)", "% of Total", "Tenure (Yrs)", "Contract Type"]
        for i, h in enumerate(headers):
            ws.cell(row=4, column=1 + i, value=h)
        self._format_header_row(ws, 4, 1, len(headers))

        customers = data.get('top_customers', [
            {'name': 'Customer A', 'revenue': 25.0, 'tenure': 8, 'contract': 'Multi-year'},
            {'name': 'Customer B', 'revenue': 18.0, 'tenure': 5, 'contract': 'Annual'},
            {'name': 'Customer C', 'revenue': 15.0, 'tenure': 6, 'contract': 'Multi-year'},
            {'name': 'Customer D', 'revenue': 12.0, 'tenure': 3, 'contract': 'Annual'},
            {'name': 'Customer E', 'revenue': 10.0, 'tenure': 4, 'contract': 'Month-to-month'},
            {'name': 'Other', 'revenue': 120.0, 'tenure': None, 'contract': 'Various'},
        ])

        total_revenue = sum(c['revenue'] for c in customers)
        row = 5
        cumulative = 0
        for cust in customers:
            pct = cust['revenue'] / total_revenue
            cumulative += pct
            ws.cell(row=row, column=1, value=cust['name'])
            ws.cell(row=row, column=2, value=cust['revenue'])
            ws.cell(row=row, column=2).number_format = '#,##0.0'
            ws.cell(row=row, column=3, value=pct)
            ws.cell(row=row, column=3).number_format = '0.0%'
            ws.cell(row=row, column=4, value=cust['tenure'] if cust['tenure'] else "—")
            ws.cell(row=row, column=5, value=cust['contract'])
            row += 1

        # Concentration summary
        row += 1
        ws.cell(row=row, column=1, value="Total Revenue")
        ws.cell(row=row, column=2, value=total_revenue)
        ws.cell(row=row, column=2).number_format = '#,##0.0'
        ws.cell(row=row, column=2).font = Font(bold=True)
        row += 1

        top5_rev = sum(c['revenue'] for c in customers[:5])
        ws.cell(row=row, column=1, value="Top 5 Concentration")
        ws.cell(row=row, column=2, value=top5_rev / total_revenue)
        ws.cell(row=row, column=2).number_format = '0.0%'
        ws.cell(row=row, column=2).font = Font(bold=True)
        if top5_rev / total_revenue > 0.5:
            ws.cell(row=row, column=3, value="⚠ High concentration risk")
            ws.cell(row=row, column=3).font = Font(color="FF0000")
        row += 1

        top1_rev = customers[0]['revenue']
        ws.cell(row=row, column=1, value="Top 1 Concentration")
        ws.cell(row=row, column=2, value=top1_rev / total_revenue)
        ws.cell(row=row, column=2).number_format = '0.0%'
        row += 3

        # Revenue Retention / Churn
        self._add_section_header(ws, "REVENUE RETENTION & CHURN", row, 1)
        row += 1

        headers = ["Metric", "FY-2", "FY-1", "LTM", "Trend"]
        for i, h in enumerate(headers):
            ws.cell(row=row, column=1 + i, value=h)
        self._format_header_row(ws, row, 1, len(headers))
        row += 1

        retention_data = data.get('retention_metrics', [
            {'name': 'Gross Revenue Retention', 'values': [0.92, 0.94, 0.95], 'good': 'up'},
            {'name': 'Net Revenue Retention', 'values': [1.05, 1.08, 1.12], 'good': 'up'},
            {'name': 'Logo Churn Rate', 'values': [0.08, 0.06, 0.05], 'good': 'down'},
            {'name': 'Dollar Churn Rate', 'values': [0.08, 0.06, 0.05], 'good': 'down'},
        ])

        for metric in retention_data:
            ws.cell(row=row, column=1, value=metric['name'])
            for i, v in enumerate(metric['values']):
                ws.cell(row=row, column=2 + i, value=v)
                ws.cell(row=row, column=2 + i).number_format = '0.0%'

            # Trend indicator
            trend = metric['values'][-1] - metric['values'][0]
            if (trend > 0 and metric['good'] == 'up') or (trend < 0 and metric['good'] == 'down'):
                ws.cell(row=row, column=5, value="✓ Improving")
                ws.cell(row=row, column=5).font = Font(color="008000")
            else:
                ws.cell(row=row, column=5, value="⚠ Declining")
                ws.cell(row=row, column=5).font = Font(color="FF0000")
            row += 1

        row += 2

        # Unit Economics (for recurring revenue businesses)
        self._add_section_header(ws, "UNIT ECONOMICS", row, 1)
        row += 1

        unit_econ = data.get('unit_economics', {
            'arpu': 15000,
            'cac': 8000,
            'gross_margin': 0.75,
            'churn_rate': 0.05,
        })

        arpu = unit_econ['arpu']
        cac = unit_econ['cac']
        gross_margin = unit_econ['gross_margin']
        churn = unit_econ['churn_rate']

        ltv = (arpu * gross_margin) / churn if churn > 0 else 0
        ltv_cac = ltv / cac if cac > 0 else 0
        payback = cac / (arpu * gross_margin / 12) if arpu * gross_margin > 0 else 0

        metrics = [
            ("Average Revenue Per User (ARPU)", arpu, '#,##0'),
            ("Customer Acquisition Cost (CAC)", cac, '#,##0'),
            ("Gross Margin", gross_margin, '0.0%'),
            ("Annual Churn Rate", churn, '0.0%'),
            ("Customer Lifetime Value (LTV)", ltv, '#,##0'),
            ("LTV/CAC Ratio", ltv_cac, '0.0x'),
            ("CAC Payback (months)", payback, '0.0'),
        ]

        for name, value, fmt in metrics:
            ws.cell(row=row, column=1, value=name)
            ws.cell(row=row, column=2, value=value)
            ws.cell(row=row, column=2).number_format = fmt
            if name == "LTV/CAC Ratio":
                ws.cell(row=row, column=2).font = Font(bold=True)
                if ltv_cac >= 3:
                    ws.cell(row=row, column=3, value="✓ Healthy (>3x)")
                    ws.cell(row=row, column=3).font = Font(color="008000")
                elif ltv_cac >= 1:
                    ws.cell(row=row, column=3, value="⚠ Marginal (1-3x)")
                    ws.cell(row=row, column=3).font = Font(color="FFA500")
                else:
                    ws.cell(row=row, column=3, value="✗ Unhealthy (<1x)")
                    ws.cell(row=row, column=3).font = Font(color="FF0000")
            row += 1

        row += 2

        # Revenue Quality Score
        self._add_section_header(ws, "REVENUE QUALITY ASSESSMENT", row, 1)
        row += 1

        quality_factors = data.get('quality_factors', [
            {'factor': 'Recurring vs. One-time', 'score': 4, 'notes': '85% recurring revenue'},
            {'factor': 'Contract Length', 'score': 3, 'notes': 'Mix of annual and multi-year'},
            {'factor': 'Customer Concentration', 'score': 3, 'notes': 'Top 5 = 40% of revenue'},
            {'factor': 'Retention Rate', 'score': 4, 'notes': 'NRR > 110%'},
            {'factor': 'Pricing Power', 'score': 3, 'notes': '3-5% annual price increases'},
        ])

        headers = ["Quality Factor", "Score (1-5)", "Notes"]
        for i, h in enumerate(headers):
            ws.cell(row=row, column=1 + i, value=h)
        self._format_header_row(ws, row, 1, 3)
        row += 1

        total_score = 0
        for factor in quality_factors:
            ws.cell(row=row, column=1, value=factor['factor'])
            ws.cell(row=row, column=2, value=factor['score'])
            ws.cell(row=row, column=3, value=factor['notes'])
            total_score += factor['score']
            row += 1

        row += 1
        avg_score = total_score / len(quality_factors)
        ws.cell(row=row, column=1, value="Overall Quality Score")
        ws.cell(row=row, column=2, value=avg_score)
        ws.cell(row=row, column=2).number_format = '0.0'
        ws.cell(row=row, column=2).font = Font(bold=True)
        ws.cell(row=row, column=2).fill = PatternFill(start_color="90EE90", end_color="90EE90", fill_type="solid")

        # Column widths
        ws.column_dimensions['A'].width = 30
        ws.column_dimensions['B'].width = 15
        ws.column_dimensions['C'].width = 15
        ws.column_dimensions['D'].width = 15
        ws.column_dimensions['E'].width = 20

        return self

    # ============================================================
    # MODULE: CREDIT/DEBT SIZING
    # ============================================================

    def add_credit_debt_sizing(self, data: Dict = None) -> 'ExcelModelGenerator':
        """
        Add Credit/Debt Sizing analysis sheet.
        Includes rating agency metrics, stress testing, coverage floors.
        """
        ws = self.wb.create_sheet("Credit Analysis")
        self.sheets_created.append("Credit Analysis")

        a = self.assumptions
        data = data or {}

        # Title
        self._add_title(ws, f"{self.company_name} - Credit & Debt Sizing Analysis", 1, 1)

        # Company Credit Profile
        self._add_section_header(ws, "CREDIT PROFILE", 3, 1)

        credit_metrics = data.get('credit_profile', {
            'ltm_ebitda': a.ltm_ebitda,
            'ltm_revenue': a.ltm_revenue,
            'total_debt': a.ltm_ebitda * (a.senior_debt_multiple + a.sub_debt_multiple),
            'cash': 10.0,
            'interest_expense': a.ltm_ebitda * a.senior_debt_multiple * 0.08,
            'capex': a.ltm_revenue * a.capex_pct_revenue,
        })

        row = 4
        profile_items = [
            ("LTM EBITDA", credit_metrics['ltm_ebitda'], '#,##0.0'),
            ("LTM Revenue", credit_metrics['ltm_revenue'], '#,##0.0'),
            ("Total Debt", credit_metrics['total_debt'], '#,##0.0'),
            ("Cash & Equivalents", credit_metrics['cash'], '#,##0.0'),
            ("Net Debt", credit_metrics['total_debt'] - credit_metrics['cash'], '#,##0.0'),
            ("Interest Expense", credit_metrics['interest_expense'], '#,##0.0'),
            ("CapEx", credit_metrics['capex'], '#,##0.0'),
        ]

        for name, value, fmt in profile_items:
            ws.cell(row=row, column=1, value=name)
            ws.cell(row=row, column=2, value=value)
            ws.cell(row=row, column=2).number_format = fmt
            row += 1

        row += 1

        # Key Credit Ratios
        self._add_section_header(ws, "KEY CREDIT RATIOS", row, 1)
        row += 1

        headers = ["Ratio", "Current", "Threshold", "Status"]
        for i, h in enumerate(headers):
            ws.cell(row=row, column=1 + i, value=h)
        self._format_header_row(ws, row, 1, 4)
        row += 1

        ebitda = credit_metrics['ltm_ebitda']
        debt = credit_metrics['total_debt']
        net_debt = debt - credit_metrics['cash']
        interest = credit_metrics['interest_expense']
        capex = credit_metrics['capex']

        ratios = [
            ("Total Debt / EBITDA", debt / ebitda if ebitda else 0, 5.5, "max"),
            ("Net Debt / EBITDA", net_debt / ebitda if ebitda else 0, 5.0, "max"),
            ("EBITDA / Interest", ebitda / interest if interest else 0, 2.0, "min"),
            ("(EBITDA - CapEx) / Interest", (ebitda - capex) / interest if interest else 0, 1.5, "min"),
            ("Debt / Revenue", debt / credit_metrics['ltm_revenue'] if credit_metrics['ltm_revenue'] else 0, 0.5, "max"),
        ]

        for name, current, threshold, direction in ratios:
            ws.cell(row=row, column=1, value=name)
            ws.cell(row=row, column=2, value=current)
            ws.cell(row=row, column=2).number_format = '0.00x'
            ws.cell(row=row, column=3, value=threshold)
            ws.cell(row=row, column=3).number_format = '0.00x'

            if direction == "max":
                passed = current <= threshold
            else:
                passed = current >= threshold

            if passed:
                ws.cell(row=row, column=4, value="✓ Pass")
                ws.cell(row=row, column=4).font = Font(color="008000")
            else:
                ws.cell(row=row, column=4, value="✗ Fail")
                ws.cell(row=row, column=4).font = Font(color="FF0000")
            row += 1

        row += 2

        # Debt Capacity Analysis
        self._add_section_header(ws, "DEBT CAPACITY ANALYSIS", row, 1)
        row += 1

        headers = ["Constraint", "Max Debt ($M)", "Implied Multiple"]
        for i, h in enumerate(headers):
            ws.cell(row=row, column=1 + i, value=h)
        self._format_header_row(ws, row, 1, 3)
        row += 1

        constraints = data.get('debt_constraints', [
            {'name': 'Leverage Ratio (5.5x EBITDA)', 'multiple': 5.5},
            {'name': 'Interest Coverage (2.0x floor)', 'multiple': 4.5},  # Implied from coverage
            {'name': 'Fixed Charge Coverage (1.5x)', 'multiple': 4.0},
            {'name': 'Senior Secured (4.0x)', 'multiple': 4.0},
        ])

        min_capacity = float('inf')
        for constraint in constraints:
            max_debt = ebitda * constraint['multiple']
            ws.cell(row=row, column=1, value=constraint['name'])
            ws.cell(row=row, column=2, value=max_debt)
            ws.cell(row=row, column=2).number_format = '#,##0.0'
            ws.cell(row=row, column=3, value=constraint['multiple'])
            ws.cell(row=row, column=3).number_format = '0.0x'
            min_capacity = min(min_capacity, max_debt)
            row += 1

        row += 1
        ws.cell(row=row, column=1, value="Binding Constraint (Max Debt)")
        ws.cell(row=row, column=2, value=min_capacity)
        ws.cell(row=row, column=2).number_format = '#,##0.0'
        ws.cell(row=row, column=2).font = Font(bold=True)
        ws.cell(row=row, column=2).fill = PatternFill(start_color="90EE90", end_color="90EE90", fill_type="solid")
        ws.cell(row=row, column=3, value=min_capacity / ebitda if ebitda else 0)
        ws.cell(row=row, column=3).number_format = '0.0x'
        ws.cell(row=row, column=3).font = Font(bold=True)
        row += 3

        # Stress Test
        self._add_section_header(ws, "EBITDA STRESS TEST", row, 1)
        row += 1

        headers = ["EBITDA Decline", "Stressed EBITDA", "Leverage", "Coverage", "Status"]
        for i, h in enumerate(headers):
            ws.cell(row=row, column=1 + i, value=h)
        self._format_header_row(ws, row, 1, 5)
        row += 1

        stress_levels = [0.0, -0.10, -0.20, -0.30, -0.40]
        for decline in stress_levels:
            stressed_ebitda = ebitda * (1 + decline)
            leverage = debt / stressed_ebitda if stressed_ebitda > 0 else 999
            coverage = stressed_ebitda / interest if interest > 0 else 0

            ws.cell(row=row, column=1, value=decline)
            ws.cell(row=row, column=1).number_format = '0%'
            ws.cell(row=row, column=2, value=stressed_ebitda)
            ws.cell(row=row, column=2).number_format = '#,##0.0'
            ws.cell(row=row, column=3, value=leverage)
            ws.cell(row=row, column=3).number_format = '0.0x'
            ws.cell(row=row, column=4, value=coverage)
            ws.cell(row=row, column=4).number_format = '0.0x'

            if leverage <= 6.0 and coverage >= 1.5:
                ws.cell(row=row, column=5, value="✓ Serviceable")
                ws.cell(row=row, column=5).font = Font(color="008000")
            elif leverage <= 7.0 and coverage >= 1.0:
                ws.cell(row=row, column=5, value="⚠ Tight")
                ws.cell(row=row, column=5).font = Font(color="FFA500")
            else:
                ws.cell(row=row, column=5, value="✗ Distressed")
                ws.cell(row=row, column=5).font = Font(color="FF0000")
            row += 1

        row += 2

        # Implied Rating
        self._add_section_header(ws, "IMPLIED CREDIT RATING", row, 1)
        row += 1

        leverage = debt / ebitda if ebitda else 999
        coverage = ebitda / interest if interest else 0

        # Simplified rating matrix
        if leverage < 2.0 and coverage > 8.0:
            rating = "BBB / Baa2"
            color = "008000"
        elif leverage < 3.5 and coverage > 4.0:
            rating = "BB / Ba2"
            color = "008000"
        elif leverage < 5.0 and coverage > 2.5:
            rating = "B+ / B1"
            color = "FFA500"
        elif leverage < 6.0 and coverage > 2.0:
            rating = "B / B2"
            color = "FFA500"
        else:
            rating = "B- / B3 or lower"
            color = "FF0000"

        ws.cell(row=row, column=1, value="Implied Rating")
        ws.cell(row=row, column=2, value=rating)
        ws.cell(row=row, column=2).font = Font(bold=True, color=color)

        # Column widths
        ws.column_dimensions['A'].width = 30
        for col in ['B', 'C', 'D', 'E']:
            ws.column_dimensions[col].width = 15

        return self

    # ============================================================
    # RETURNS & CAPITAL STRUCTURE MODULES
    # ============================================================

    # ============================================================
    # MODULE: DIVIDEND RECAPITALIZATION
    # ============================================================

    def add_dividend_recap(self, data: Dict = None) -> 'ExcelModelGenerator':
        """
        Add Dividend Recapitalization analysis sheet.
        Models mid-hold dividend to return capital while maintaining ownership.
        """
        ws = self.wb.create_sheet("Dividend Recap")
        self.sheets_created.append("Dividend Recap")

        a = self.assumptions
        data = data or {}

        # Title
        self._add_title(ws, f"{self.company_name} - Dividend Recapitalization Analysis", 1, 1)

        # Current Capital Structure
        self._add_section_header(ws, "CURRENT CAPITAL STRUCTURE ($M)", 3, 1)

        ev = a.ltm_ebitda * a.entry_multiple
        current_debt = a.ltm_ebitda * (a.senior_debt_multiple + a.sub_debt_multiple)
        equity_value = ev - current_debt

        row = 4
        ws.cell(row=row, column=1, value="Enterprise Value")
        ws.cell(row=row, column=2, value=ev)
        ws.cell(row=row, column=2).number_format = '#,##0.0'
        row += 1

        ws.cell(row=row, column=1, value="Less: Existing Debt")
        ws.cell(row=row, column=2, value=-current_debt)
        ws.cell(row=row, column=2).number_format = '(#,##0.0)'
        row += 1

        ws.cell(row=row, column=1, value="Equity Value")
        ws.cell(row=row, column=2, value=equity_value)
        ws.cell(row=row, column=2).number_format = '#,##0.0'
        ws.cell(row=row, column=2).font = Font(bold=True)
        row += 1

        ws.cell(row=row, column=1, value="Current Leverage")
        ws.cell(row=row, column=2, value=current_debt / a.ltm_ebitda)
        ws.cell(row=row, column=2).number_format = '0.0x'
        row += 3

        # Dividend Recap Parameters
        self._add_section_header(ws, "DIVIDEND RECAP PARAMETERS", row, 1)
        row += 1

        recap_year = data.get('recap_year', 2)
        new_debt_amount = data.get('new_debt_amount', a.ltm_ebitda * 1.5)
        recap_rate = data.get('recap_debt_rate', 0.09)

        # Project EBITDA at recap year
        ebitda_at_recap = a.ltm_ebitda
        for i in range(recap_year):
            if i < len(a.ebitda_margin):
                ebitda_at_recap *= (1 + a.revenue_growth[i])

        ws.cell(row=row, column=1, value="Recap Timing (Year)")
        ws.cell(row=row, column=2, value=recap_year)
        self._format_input_cell(ws, row, 2)
        row += 1

        ws.cell(row=row, column=1, value="EBITDA at Recap")
        ws.cell(row=row, column=2, value=ebitda_at_recap)
        ws.cell(row=row, column=2).number_format = '#,##0.0'
        row += 1

        ws.cell(row=row, column=1, value="New Debt Amount")
        ws.cell(row=row, column=2, value=new_debt_amount)
        ws.cell(row=row, column=2).number_format = '#,##0.0'
        self._format_input_cell(ws, row, 2)
        row += 1

        ws.cell(row=row, column=1, value="New Debt Rate")
        ws.cell(row=row, column=2, value=recap_rate)
        ws.cell(row=row, column=2).number_format = '0.0%'
        self._format_input_cell(ws, row, 2)
        row += 1

        # Existing debt at recap (assume 20% paid down per year)
        existing_debt_at_recap = current_debt * (0.8 ** recap_year)
        ws.cell(row=row, column=1, value="Existing Debt at Recap")
        ws.cell(row=row, column=2, value=existing_debt_at_recap)
        ws.cell(row=row, column=2).number_format = '#,##0.0'
        row += 1

        total_debt_post_recap = existing_debt_at_recap + new_debt_amount
        ws.cell(row=row, column=1, value="Total Debt Post-Recap")
        ws.cell(row=row, column=2, value=total_debt_post_recap)
        ws.cell(row=row, column=2).number_format = '#,##0.0'
        ws.cell(row=row, column=2).font = Font(bold=True)
        row += 1

        ws.cell(row=row, column=1, value="Post-Recap Leverage")
        ws.cell(row=row, column=2, value=total_debt_post_recap / ebitda_at_recap)
        ws.cell(row=row, column=2).number_format = '0.0x'
        ws.cell(row=row, column=2).font = Font(bold=True)
        row += 3

        # Dividend Distribution
        self._add_section_header(ws, "DIVIDEND DISTRIBUTION", row, 1)
        row += 1

        fees = new_debt_amount * 0.02  # 2% financing fees
        dividend = new_debt_amount - fees

        ws.cell(row=row, column=1, value="Gross Proceeds")
        ws.cell(row=row, column=2, value=new_debt_amount)
        ws.cell(row=row, column=2).number_format = '#,##0.0'
        row += 1

        ws.cell(row=row, column=1, value="Less: Financing Fees (2%)")
        ws.cell(row=row, column=2, value=-fees)
        ws.cell(row=row, column=2).number_format = '(#,##0.0)'
        row += 1

        ws.cell(row=row, column=1, value="Net Dividend to Equity")
        ws.cell(row=row, column=2, value=dividend)
        ws.cell(row=row, column=2).number_format = '#,##0.0'
        ws.cell(row=row, column=2).font = Font(bold=True)
        ws.cell(row=row, column=2).fill = PatternFill(start_color="90EE90", end_color="90EE90", fill_type="solid")
        row += 3

        # Returns Impact
        self._add_section_header(ws, "RETURNS IMPACT ANALYSIS", row, 1)
        row += 1

        headers = ["Metric", "Without Recap", "With Recap", "Impact"]
        for i, h in enumerate(headers):
            ws.cell(row=row, column=1 + i, value=h)
        self._format_header_row(ws, row, 1, 4)
        row += 1

        # Calculate returns
        fees_initial = ev * 0.04
        initial_equity = ev + fees_initial - current_debt

        # Exit assumptions
        exit_year = a.hold_period
        exit_ebitda = a.ltm_ebitda
        for i in range(exit_year):
            if i < len(a.revenue_growth):
                exit_ebitda *= (1 + a.revenue_growth[i])

        exit_ev = exit_ebitda * a.exit_multiple

        # Without recap
        debt_at_exit_no_recap = current_debt * (0.5)  # Assume 50% paydown
        exit_equity_no_recap = exit_ev - debt_at_exit_no_recap
        moic_no_recap = exit_equity_no_recap / initial_equity
        irr_no_recap = (moic_no_recap ** (1 / exit_year)) - 1

        # With recap
        debt_at_exit_recap = total_debt_post_recap * (0.6)  # Less paydown due to higher debt
        exit_equity_recap = exit_ev - debt_at_exit_recap
        total_proceeds_recap = dividend + exit_equity_recap
        moic_recap = total_proceeds_recap / initial_equity
        # Simplified IRR (doesn't account for timing perfectly)
        irr_recap = (moic_recap ** (1 / exit_year)) - 1

        metrics = [
            ("Initial Equity Investment", initial_equity, initial_equity, 0),
            ("Dividend Proceeds (Year {})".format(recap_year), 0, dividend, dividend),
            ("Exit Equity Proceeds", exit_equity_no_recap, exit_equity_recap, exit_equity_recap - exit_equity_no_recap),
            ("Total Proceeds", exit_equity_no_recap, total_proceeds_recap, total_proceeds_recap - exit_equity_no_recap),
            ("MOIC", moic_no_recap, moic_recap, moic_recap - moic_no_recap),
            ("IRR (approx)", irr_no_recap, irr_recap, irr_recap - irr_no_recap),
        ]

        for name, without, with_recap, impact in metrics:
            ws.cell(row=row, column=1, value=name)
            if "MOIC" in name:
                fmt = '0.00x'
            elif "IRR" in name:
                fmt = '0.0%'
            else:
                fmt = '#,##0.0'

            ws.cell(row=row, column=2, value=without)
            ws.cell(row=row, column=2).number_format = fmt
            ws.cell(row=row, column=3, value=with_recap)
            ws.cell(row=row, column=3).number_format = fmt
            ws.cell(row=row, column=4, value=impact)
            ws.cell(row=row, column=4).number_format = fmt if "MOIC" not in name else '+0.00x;-0.00x'

            if "MOIC" in name or "IRR" in name:
                ws.cell(row=row, column=1).font = Font(bold=True)
                ws.cell(row=row, column=2).font = Font(bold=True)
                ws.cell(row=row, column=3).font = Font(bold=True)
                ws.cell(row=row, column=4).font = Font(bold=True)
            row += 1

        # Column widths
        ws.column_dimensions['A'].width = 30
        for col in ['B', 'C', 'D']:
            ws.column_dimensions[col].width = 15

        return self

    # ============================================================
    # MODULE: REFINANCING ANALYSIS
    # ============================================================

    def add_refinancing_analysis(self, data: Dict = None) -> 'ExcelModelGenerator':
        """
        Add Refinancing Analysis sheet.
        Analyzes optimal timing to refinance at lower rates or extend maturities.
        """
        ws = self.wb.create_sheet("Refinancing")
        self.sheets_created.append("Refinancing")

        a = self.assumptions
        data = data or {}

        # Title
        self._add_title(ws, f"{self.company_name} - Refinancing Analysis", 1, 1)

        # Current Debt Structure
        self._add_section_header(ws, "CURRENT DEBT STRUCTURE", 3, 1)

        current_debt = data.get('current_debt', [
            {'tranche': 'Term Loan A', 'amount': 150.0, 'rate': 0.085, 'maturity': 2027, 'callable': 'Par'},
            {'tranche': 'Term Loan B', 'amount': 100.0, 'rate': 0.095, 'maturity': 2028, 'callable': '101'},
            {'tranche': 'Senior Notes', 'amount': 50.0, 'rate': 0.0875, 'maturity': 2029, 'callable': 'NC-2'},
        ])

        headers = ["Tranche", "Amount ($M)", "Rate", "Maturity", "Call Protection"]
        row = 4
        for i, h in enumerate(headers):
            ws.cell(row=row, column=1 + i, value=h)
        self._format_header_row(ws, row, 1, len(headers))
        row += 1

        total_debt = 0
        weighted_rate = 0
        for debt in current_debt:
            ws.cell(row=row, column=1, value=debt['tranche'])
            ws.cell(row=row, column=2, value=debt['amount'])
            ws.cell(row=row, column=2).number_format = '#,##0.0'
            ws.cell(row=row, column=3, value=debt['rate'])
            ws.cell(row=row, column=3).number_format = '0.00%'
            ws.cell(row=row, column=4, value=debt['maturity'])
            ws.cell(row=row, column=5, value=debt['callable'])
            total_debt += debt['amount']
            weighted_rate += debt['amount'] * debt['rate']
            row += 1

        row += 1
        ws.cell(row=row, column=1, value="Total / Weighted Average")
        ws.cell(row=row, column=2, value=total_debt)
        ws.cell(row=row, column=2).number_format = '#,##0.0'
        ws.cell(row=row, column=2).font = Font(bold=True)
        ws.cell(row=row, column=3, value=weighted_rate / total_debt if total_debt else 0)
        ws.cell(row=row, column=3).number_format = '0.00%'
        ws.cell(row=row, column=3).font = Font(bold=True)
        row += 3

        # Market Conditions
        self._add_section_header(ws, "CURRENT MARKET CONDITIONS", row, 1)
        row += 1

        market = data.get('market_conditions', {
            'tla_rate': 0.070,
            'tlb_rate': 0.080,
            'notes_rate': 0.075,
            'sofr': 0.045,
        })

        ws.cell(row=row, column=1, value="New TLA Rate (est.)")
        ws.cell(row=row, column=2, value=market['tla_rate'])
        ws.cell(row=row, column=2).number_format = '0.00%'
        self._format_input_cell(ws, row, 2)
        row += 1

        ws.cell(row=row, column=1, value="New TLB Rate (est.)")
        ws.cell(row=row, column=2, value=market['tlb_rate'])
        ws.cell(row=row, column=2).number_format = '0.00%'
        self._format_input_cell(ws, row, 2)
        row += 1

        ws.cell(row=row, column=1, value="New Notes Rate (est.)")
        ws.cell(row=row, column=2, value=market['notes_rate'])
        ws.cell(row=row, column=2).number_format = '0.00%'
        self._format_input_cell(ws, row, 2)
        row += 1

        ws.cell(row=row, column=1, value="Current SOFR")
        ws.cell(row=row, column=2, value=market['sofr'])
        ws.cell(row=row, column=2).number_format = '0.00%'
        row += 3

        # Refinancing Scenario
        self._add_section_header(ws, "REFINANCING SCENARIO", row, 1)
        row += 1

        new_structure = data.get('new_structure', [
            {'tranche': 'New Term Loan', 'amount': total_debt, 'rate': market['tlb_rate'], 'maturity': 2031},
        ])

        headers = ["New Tranche", "Amount ($M)", "Rate", "Maturity"]
        for i, h in enumerate(headers):
            ws.cell(row=row, column=1 + i, value=h)
        self._format_header_row(ws, row, 1, 4)
        row += 1

        new_total = 0
        new_weighted = 0
        for debt in new_structure:
            ws.cell(row=row, column=1, value=debt['tranche'])
            ws.cell(row=row, column=2, value=debt['amount'])
            ws.cell(row=row, column=2).number_format = '#,##0.0'
            ws.cell(row=row, column=3, value=debt['rate'])
            ws.cell(row=row, column=3).number_format = '0.00%'
            ws.cell(row=row, column=4, value=debt['maturity'])
            new_total += debt['amount']
            new_weighted += debt['amount'] * debt['rate']
            row += 1

        row += 1
        ws.cell(row=row, column=1, value="Total / Weighted Average")
        ws.cell(row=row, column=2, value=new_total)
        ws.cell(row=row, column=2).number_format = '#,##0.0'
        ws.cell(row=row, column=2).font = Font(bold=True)
        ws.cell(row=row, column=3, value=new_weighted / new_total if new_total else 0)
        ws.cell(row=row, column=3).number_format = '0.00%'
        ws.cell(row=row, column=3).font = Font(bold=True)
        row += 3

        # Savings Analysis
        self._add_section_header(ws, "ANNUAL SAVINGS ANALYSIS", row, 1)
        row += 1

        old_rate = weighted_rate / total_debt if total_debt else 0
        new_rate = new_weighted / new_total if new_total else 0
        rate_reduction = old_rate - new_rate

        old_interest = total_debt * old_rate
        new_interest = new_total * new_rate
        annual_savings = old_interest - new_interest

        ws.cell(row=row, column=1, value="Current Interest Expense")
        ws.cell(row=row, column=2, value=old_interest)
        ws.cell(row=row, column=2).number_format = '#,##0.0'
        row += 1

        ws.cell(row=row, column=1, value="New Interest Expense")
        ws.cell(row=row, column=2, value=new_interest)
        ws.cell(row=row, column=2).number_format = '#,##0.0'
        row += 1

        ws.cell(row=row, column=1, value="Annual Interest Savings")
        ws.cell(row=row, column=2, value=annual_savings)
        ws.cell(row=row, column=2).number_format = '#,##0.0'
        ws.cell(row=row, column=2).font = Font(bold=True)
        ws.cell(row=row, column=2).fill = PatternFill(start_color="90EE90", end_color="90EE90", fill_type="solid")
        row += 1

        ws.cell(row=row, column=1, value="Rate Reduction")
        ws.cell(row=row, column=2, value=rate_reduction * 10000)  # Convert to bps
        ws.cell(row=row, column=2).number_format = '0" bps"'
        row += 3

        # Transaction Costs
        self._add_section_header(ws, "TRANSACTION COSTS", row, 1)
        row += 1

        call_premium = data.get('call_premium', total_debt * 0.01)
        arrangement_fee = new_total * 0.01
        legal_fees = 0.5
        total_costs = call_premium + arrangement_fee + legal_fees

        ws.cell(row=row, column=1, value="Call Premium / Make-Whole")
        ws.cell(row=row, column=2, value=call_premium)
        ws.cell(row=row, column=2).number_format = '#,##0.0'
        row += 1

        ws.cell(row=row, column=1, value="Arrangement Fee (1%)")
        ws.cell(row=row, column=2, value=arrangement_fee)
        ws.cell(row=row, column=2).number_format = '#,##0.0'
        row += 1

        ws.cell(row=row, column=1, value="Legal & Advisory")
        ws.cell(row=row, column=2, value=legal_fees)
        ws.cell(row=row, column=2).number_format = '#,##0.0'
        row += 1

        ws.cell(row=row, column=1, value="Total Transaction Costs")
        ws.cell(row=row, column=2, value=total_costs)
        ws.cell(row=row, column=2).number_format = '#,##0.0'
        ws.cell(row=row, column=2).font = Font(bold=True)
        row += 2

        # Payback
        payback = total_costs / annual_savings if annual_savings > 0 else 999
        ws.cell(row=row, column=1, value="Payback Period (years)")
        ws.cell(row=row, column=2, value=payback)
        ws.cell(row=row, column=2).number_format = '0.0'
        ws.cell(row=row, column=2).font = Font(bold=True)
        if payback <= 2:
            ws.cell(row=row, column=3, value="✓ Attractive")
            ws.cell(row=row, column=3).font = Font(color="008000")
        elif payback <= 3:
            ws.cell(row=row, column=3, value="⚠ Marginal")
            ws.cell(row=row, column=3).font = Font(color="FFA500")
        else:
            ws.cell(row=row, column=3, value="✗ Not recommended")
            ws.cell(row=row, column=3).font = Font(color="FF0000")

        # Column widths
        ws.column_dimensions['A'].width = 30
        for col in ['B', 'C', 'D', 'E']:
            ws.column_dimensions[col].width = 15

        return self

    # ============================================================
    # MODULE: CAP TABLE / WATERFALL
    # ============================================================

    def add_cap_table_waterfall(self, data: Dict = None) -> 'ExcelModelGenerator':
        """
        Add Cap Table / Waterfall analysis sheet.
        Detailed equity waterfall with preferred returns, participation, catch-ups.
        """
        ws = self.wb.create_sheet("Cap Table Waterfall")
        self.sheets_created.append("Cap Table Waterfall")

        a = self.assumptions
        data = data or {}

        # Title
        self._add_title(ws, f"{self.company_name} - Equity Waterfall Analysis", 1, 1)

        # Cap Table
        self._add_section_header(ws, "CAPITALIZATION TABLE", 3, 1)

        cap_table = data.get('cap_table', [
            {'investor': 'Sponsor Fund', 'invested': 150.0, 'ownership': 0.80, 'type': 'Common'},
            {'investor': 'Co-Investors', 'invested': 25.0, 'ownership': 0.13, 'type': 'Common'},
            {'investor': 'Management', 'invested': 5.0, 'ownership': 0.05, 'type': 'Common'},
            {'investor': 'Rollover Equity', 'invested': 4.0, 'ownership': 0.02, 'type': 'Common'},
        ])

        headers = ["Investor", "Invested ($M)", "Ownership %", "Security Type"]
        row = 4
        for i, h in enumerate(headers):
            ws.cell(row=row, column=1 + i, value=h)
        self._format_header_row(ws, row, 1, 4)
        row += 1

        total_invested = 0
        for investor in cap_table:
            ws.cell(row=row, column=1, value=investor['investor'])
            ws.cell(row=row, column=2, value=investor['invested'])
            ws.cell(row=row, column=2).number_format = '#,##0.0'
            ws.cell(row=row, column=3, value=investor['ownership'])
            ws.cell(row=row, column=3).number_format = '0.0%'
            ws.cell(row=row, column=4, value=investor['type'])
            total_invested += investor['invested']
            row += 1

        row += 1
        ws.cell(row=row, column=1, value="Total")
        ws.cell(row=row, column=2, value=total_invested)
        ws.cell(row=row, column=2).number_format = '#,##0.0'
        ws.cell(row=row, column=2).font = Font(bold=True)
        ws.cell(row=row, column=3, value=1.0)
        ws.cell(row=row, column=3).number_format = '0.0%'
        ws.cell(row=row, column=3).font = Font(bold=True)
        row += 3

        # Waterfall Terms
        self._add_section_header(ws, "WATERFALL STRUCTURE", row, 1)
        row += 1

        waterfall_terms = data.get('waterfall_terms', {
            'preferred_return': 0.08,
            'catch_up_pct': 1.00,
            'catch_up_split': 0.20,
            'carried_interest': 0.20,
            'gp_commitment': 0.02,
        })

        ws.cell(row=row, column=1, value="Preferred Return (Hurdle)")
        ws.cell(row=row, column=2, value=waterfall_terms['preferred_return'])
        ws.cell(row=row, column=2).number_format = '0.0%'
        self._format_input_cell(ws, row, 2)
        row += 1

        ws.cell(row=row, column=1, value="GP Catch-Up")
        ws.cell(row=row, column=2, value=waterfall_terms['catch_up_pct'])
        ws.cell(row=row, column=2).number_format = '0%'
        row += 1

        ws.cell(row=row, column=1, value="Carried Interest")
        ws.cell(row=row, column=2, value=waterfall_terms['carried_interest'])
        ws.cell(row=row, column=2).number_format = '0.0%'
        self._format_input_cell(ws, row, 2)
        row += 1

        ws.cell(row=row, column=1, value="GP Commitment")
        ws.cell(row=row, column=2, value=waterfall_terms['gp_commitment'])
        ws.cell(row=row, column=2).number_format = '0.0%'
        row += 3

        # Exit Scenarios Waterfall
        self._add_section_header(ws, "WATERFALL BY EXIT VALUE", row, 1)
        row += 1

        headers = ["Exit Equity Value ($M)", "200", "300", "400", "500", "600"]
        for i, h in enumerate(headers):
            ws.cell(row=row, column=1 + i, value=h)
        self._format_header_row(ws, row, 1, 6)
        row += 1

        exit_values = [200, 300, 400, 500, 600]
        pref_rate = waterfall_terms['preferred_return']
        carry = waterfall_terms['carried_interest']
        hold = 5  # years

        # Calculate preferred return threshold
        pref_threshold = total_invested * ((1 + pref_rate) ** hold)

        waterfall_rows = [
            "Return of Capital",
            "Preferred Return (to hurdle)",
            "GP Catch-Up",
            "Remaining (80/20 split)",
            "Total to LPs",
            "Total to GP (Carry)",
            "LP MOIC",
            "GP Carry ($M)",
        ]

        for row_name in waterfall_rows:
            ws.cell(row=row, column=1, value=row_name)

            for i, ev in enumerate(exit_values):
                col = 2 + i

                if row_name == "Return of Capital":
                    value = min(ev, total_invested)
                elif row_name == "Preferred Return (to hurdle)":
                    pref_amount = pref_threshold - total_invested
                    value = min(max(0, ev - total_invested), pref_amount)
                elif row_name == "GP Catch-Up":
                    remaining_after_pref = ev - pref_threshold
                    if remaining_after_pref > 0:
                        # Catch-up until GP has 20% of total profits
                        total_profit = ev - total_invested
                        catch_up_target = total_profit * carry / (1 - carry)
                        pref_to_lp = pref_threshold - total_invested
                        value = min(remaining_after_pref, max(0, catch_up_target - 0))
                    else:
                        value = 0
                elif row_name == "Remaining (80/20 split)":
                    # Simplified - remaining after catch-up split 80/20
                    catch_up_complete = ev - total_invested - (pref_threshold - total_invested)
                    if catch_up_complete > 0:
                        value = catch_up_complete * 0.80
                    else:
                        value = 0
                elif row_name == "Total to LPs":
                    # Simplified LP total
                    if ev <= total_invested:
                        value = ev
                    elif ev <= pref_threshold:
                        value = ev
                    else:
                        profit = ev - total_invested
                        gp_share = profit * carry
                        value = ev - gp_share
                elif row_name == "Total to GP (Carry)":
                    if ev <= pref_threshold:
                        value = 0
                    else:
                        profit = ev - total_invested
                        value = profit * carry
                elif row_name == "LP MOIC":
                    lp_total = ev if ev <= pref_threshold else ev - (ev - total_invested) * carry
                    value = lp_total / total_invested
                elif row_name == "GP Carry ($M)":
                    if ev <= pref_threshold:
                        value = 0
                    else:
                        profit = ev - total_invested
                        value = profit * carry

                ws.cell(row=row, column=col, value=value)
                if "MOIC" in row_name:
                    ws.cell(row=row, column=col).number_format = '0.00x'
                else:
                    ws.cell(row=row, column=col).number_format = '#,##0.0'

            if "Total to LPs" in row_name or "LP MOIC" in row_name:
                ws.cell(row=row, column=1).font = Font(bold=True)
                for col in range(2, 7):
                    ws.cell(row=row, column=col).font = Font(bold=True)
                    if "Total to LPs" in row_name:
                        ws.cell(row=row, column=col).fill = PatternFill(start_color="90EE90", end_color="90EE90", fill_type="solid")

            row += 1

        # Column widths
        ws.column_dimensions['A'].width = 25
        for col in ['B', 'C', 'D', 'E', 'F']:
            ws.column_dimensions[col].width = 12

        return self

    # ============================================================
    # MODULE: SPONSOR ECONOMICS
    # ============================================================

    def add_sponsor_economics(self, data: Dict = None) -> 'ExcelModelGenerator':
        """
        Add Sponsor Economics sheet.
        GP carry, management fees, fund-level vs deal-level IRR.
        """
        ws = self.wb.create_sheet("Sponsor Economics")
        self.sheets_created.append("Sponsor Economics")

        a = self.assumptions
        data = data or {}

        # Title
        self._add_title(ws, f"{self.company_name} - Sponsor Economics Analysis", 1, 1)

        # Fund Parameters
        self._add_section_header(ws, "FUND PARAMETERS", 3, 1)

        fund_params = data.get('fund_params', {
            'fund_size': 500.0,
            'gp_commitment': 0.02,
            'management_fee': 0.02,
            'carried_interest': 0.20,
            'hurdle_rate': 0.08,
            'fund_life': 10,
            'investment_period': 5,
        })

        row = 4
        params = [
            ("Fund Size ($M)", fund_params['fund_size'], '#,##0'),
            ("GP Commitment", fund_params['gp_commitment'], '0.0%'),
            ("Management Fee", fund_params['management_fee'], '0.0%'),
            ("Carried Interest", fund_params['carried_interest'], '0.0%'),
            ("Hurdle Rate", fund_params['hurdle_rate'], '0.0%'),
            ("Fund Life (years)", fund_params['fund_life'], '0'),
            ("Investment Period (years)", fund_params['investment_period'], '0'),
        ]

        for name, value, fmt in params:
            ws.cell(row=row, column=1, value=name)
            ws.cell(row=row, column=2, value=value)
            ws.cell(row=row, column=2).number_format = fmt
            self._format_input_cell(ws, row, 2)
            row += 1

        row += 2

        # Deal Parameters
        self._add_section_header(ws, "DEAL PARAMETERS", row, 1)
        row += 1

        deal_params = data.get('deal_params', {
            'deal_equity': 150.0,
            'deal_pct_of_fund': 0.30,
            'entry_moic': 2.5,
            'hold_period': 5,
        })

        ws.cell(row=row, column=1, value="Deal Equity Investment ($M)")
        ws.cell(row=row, column=2, value=deal_params['deal_equity'])
        ws.cell(row=row, column=2).number_format = '#,##0.0'
        self._format_input_cell(ws, row, 2)
        row += 1

        ws.cell(row=row, column=1, value="% of Fund")
        ws.cell(row=row, column=2, value=deal_params['deal_pct_of_fund'])
        ws.cell(row=row, column=2).number_format = '0.0%'
        row += 1

        ws.cell(row=row, column=1, value="Expected MOIC")
        ws.cell(row=row, column=2, value=deal_params['entry_moic'])
        ws.cell(row=row, column=2).number_format = '0.0x'
        self._format_input_cell(ws, row, 2)
        row += 1

        ws.cell(row=row, column=1, value="Hold Period (years)")
        ws.cell(row=row, column=2, value=deal_params['hold_period'])
        self._format_input_cell(ws, row, 2)
        row += 3

        # GP Economics from this Deal
        self._add_section_header(ws, "GP ECONOMICS FROM THIS DEAL", row, 1)
        row += 1

        fund_size = fund_params['fund_size']
        mgmt_fee = fund_params['management_fee']
        carry = fund_params['carried_interest']
        hurdle = fund_params['hurdle_rate']
        gp_commit = fund_params['gp_commitment']
        inv_period = fund_params['investment_period']
        fund_life = fund_params['fund_life']

        deal_equity = deal_params['deal_equity']
        moic = deal_params['entry_moic']
        hold = deal_params['hold_period']

        # Management fees (simplified)
        mgmt_fee_total = fund_size * mgmt_fee * inv_period + fund_size * 0.5 * mgmt_fee * (fund_life - inv_period)

        # Deal-level returns
        deal_proceeds = deal_equity * moic
        deal_profit = deal_proceeds - deal_equity
        deal_irr = (moic ** (1 / hold)) - 1

        # GP share of this deal's profit (simplified - assumes hurdle met at fund level)
        gp_carry_from_deal = deal_profit * carry

        # GP co-invest return
        gp_coinvest = deal_equity * gp_commit
        gp_coinvest_return = gp_coinvest * moic - gp_coinvest

        ws.cell(row=row, column=1, value="Deal Investment")
        ws.cell(row=row, column=2, value=deal_equity)
        ws.cell(row=row, column=2).number_format = '#,##0.0'
        row += 1

        ws.cell(row=row, column=1, value="Deal Proceeds")
        ws.cell(row=row, column=2, value=deal_proceeds)
        ws.cell(row=row, column=2).number_format = '#,##0.0'
        row += 1

        ws.cell(row=row, column=1, value="Deal Profit")
        ws.cell(row=row, column=2, value=deal_profit)
        ws.cell(row=row, column=2).number_format = '#,##0.0'
        row += 1

        ws.cell(row=row, column=1, value="Deal IRR")
        ws.cell(row=row, column=2, value=deal_irr)
        ws.cell(row=row, column=2).number_format = '0.0%'
        ws.cell(row=row, column=2).font = Font(bold=True)
        row += 2

        ws.cell(row=row, column=1, value="GP Carried Interest (20% of profit)")
        ws.cell(row=row, column=2, value=gp_carry_from_deal)
        ws.cell(row=row, column=2).number_format = '#,##0.0'
        ws.cell(row=row, column=2).fill = PatternFill(start_color="90EE90", end_color="90EE90", fill_type="solid")
        row += 1

        ws.cell(row=row, column=1, value="GP Co-Invest Profit")
        ws.cell(row=row, column=2, value=gp_coinvest_return)
        ws.cell(row=row, column=2).number_format = '#,##0.0'
        row += 1

        ws.cell(row=row, column=1, value="Total GP Economics (this deal)")
        ws.cell(row=row, column=2, value=gp_carry_from_deal + gp_coinvest_return)
        ws.cell(row=row, column=2).number_format = '#,##0.0'
        ws.cell(row=row, column=2).font = Font(bold=True)
        row += 3

        # Fund-Level Economics (Simplified)
        self._add_section_header(ws, "FUND-LEVEL ECONOMICS (ILLUSTRATIVE)", row, 1)
        row += 1

        # Assume fund returns 2.0x gross
        fund_gross_moic = data.get('fund_gross_moic', 2.0)
        fund_proceeds = fund_size * fund_gross_moic
        fund_profit = fund_proceeds - fund_size

        # Hurdle calculation
        hurdle_threshold = fund_size * ((1 + hurdle) ** fund_life)
        hurdle_met = fund_proceeds > hurdle_threshold

        total_carry = fund_profit * carry if hurdle_met else 0
        total_mgmt_fees = mgmt_fee_total
        gp_coinvest_total = fund_size * gp_commit * (fund_gross_moic - 1)

        headers = ["", "Amount ($M)", "% of Fund"]
        for i, h in enumerate(headers):
            ws.cell(row=row, column=1 + i, value=h)
        self._format_header_row(ws, row, 1, 3)
        row += 1

        fund_economics = [
            ("Fund Size (Committed)", fund_size, 1.0),
            ("Gross Proceeds", fund_proceeds, fund_gross_moic),
            ("Gross Profit", fund_profit, fund_profit / fund_size),
            ("", None, None),
            ("Management Fees (total)", total_mgmt_fees, total_mgmt_fees / fund_size),
            ("Carried Interest (20%)", total_carry, total_carry / fund_size),
            ("GP Co-Invest Profit", gp_coinvest_total, gp_coinvest_total / fund_size),
            ("", None, None),
            ("Total GP Revenue", total_mgmt_fees + total_carry + gp_coinvest_total, None),
        ]

        for name, amount, pct in fund_economics:
            ws.cell(row=row, column=1, value=name)
            if amount is not None:
                ws.cell(row=row, column=2, value=amount)
                ws.cell(row=row, column=2).number_format = '#,##0.0'
            if pct is not None:
                ws.cell(row=row, column=3, value=pct)
                ws.cell(row=row, column=3).number_format = '0.0%' if pct < 5 else '0.0x'

            if "Total GP" in name:
                ws.cell(row=row, column=1).font = Font(bold=True)
                ws.cell(row=row, column=2).font = Font(bold=True)
                ws.cell(row=row, column=2).fill = PatternFill(start_color="FFFF99", end_color="FFFF99", fill_type="solid")
            row += 1

        # Column widths
        ws.column_dimensions['A'].width = 35
        ws.column_dimensions['B'].width = 15
        ws.column_dimensions['C'].width = 15

        return self

    # ============================================================
    # TRANSACTION STRUCTURE & EXECUTION MODULES
    # ============================================================

    def add_addon_analysis(self, data: Dict = None) -> 'ExcelModelGenerator':
        """Add Add-on/Bolt-on Acquisition analysis sheet."""
        ws = self.wb.create_sheet("Add-on Analysis")
        self.sheets_created.append("Add-on Analysis")
        a = self.assumptions
        data = data or {}

        self._add_title(ws, f"{self.company_name} - Add-on Acquisition Analysis", 1, 1)

        # Platform
        self._add_section_header(ws, "PLATFORM COMPANY", 3, 1)
        platform_ebitda = data.get('platform_ebitda', a.ltm_ebitda)
        platform_ev = platform_ebitda * a.entry_multiple
        row = 4
        ws.cell(row=row, column=1, value="Platform EBITDA")
        ws.cell(row=row, column=2, value=platform_ebitda)
        ws.cell(row=row, column=2).number_format = '#,##0.0'
        row += 1
        ws.cell(row=row, column=1, value="Entry Multiple")
        ws.cell(row=row, column=2, value=a.entry_multiple)
        ws.cell(row=row, column=2).number_format = '0.0x'
        row += 3

        # Add-ons
        self._add_section_header(ws, "ADD-ON TARGETS", row, 1)
        row += 1
        headers = ["Target", "EBITDA", "Multiple", "EV", "Synergies"]
        for i, h in enumerate(headers):
            ws.cell(row=row, column=1+i, value=h)
        self._format_header_row(ws, row, 1, 5)
        row += 1

        addons = data.get('addons', [
            {'name': 'Target A', 'ebitda': 5.0, 'multiple': 5.5, 'synergies': 0.8},
            {'name': 'Target B', 'ebitda': 3.0, 'multiple': 5.0, 'synergies': 0.5},
        ])
        total_ebitda, total_ev, total_syn = 0, 0, 0
        for addon in addons:
            ev = addon['ebitda'] * addon['multiple']
            ws.cell(row=row, column=1, value=addon['name'])
            ws.cell(row=row, column=2, value=addon['ebitda'])
            ws.cell(row=row, column=3, value=addon['multiple'])
            ws.cell(row=row, column=4, value=ev)
            ws.cell(row=row, column=5, value=addon['synergies'])
            for col in [2,4,5]: ws.cell(row=row, column=col).number_format = '#,##0.0'
            ws.cell(row=row, column=3).number_format = '0.0x'
            total_ebitda += addon['ebitda']
            total_ev += ev
            total_syn += addon['synergies']
            row += 1

        row += 1
        combined_ebitda = platform_ebitda + total_ebitda + total_syn
        ws.cell(row=row, column=1, value="Pro Forma EBITDA")
        ws.cell(row=row, column=2, value=combined_ebitda)
        ws.cell(row=row, column=2).number_format = '#,##0.0'
        ws.cell(row=row, column=2).font = Font(bold=True)
        ws.cell(row=row, column=2).fill = PatternFill(start_color="90EE90", end_color="90EE90", fill_type="solid")
        row += 1
        ws.cell(row=row, column=1, value="Multiple Arbitrage")
        ws.cell(row=row, column=2, value=a.entry_multiple - (total_ev/total_ebitda if total_ebitda else 0))
        ws.cell(row=row, column=2).number_format = '0.0x'
        ws.cell(row=row, column=2).font = Font(bold=True, color="008000")

        ws.column_dimensions['A'].width = 25
        for c in ['B','C','D','E']: ws.column_dimensions[c].width = 12
        return self

    def add_synergy_model(self, data: Dict = None) -> 'ExcelModelGenerator':
        """Add Synergy Model sheet with cost/revenue synergies."""
        ws = self.wb.create_sheet("Synergy Model")
        self.sheets_created.append("Synergy Model")
        data = data or {}

        self._add_title(ws, f"{self.company_name} - Synergy Analysis", 1, 1)
        self._add_section_header(ws, "COST SYNERGIES", 3, 1)

        headers = ["Category", "Yr 1", "Yr 2", "Yr 3", "Run-Rate", "Prob."]
        row = 4
        for i, h in enumerate(headers):
            ws.cell(row=row, column=1+i, value=h)
        self._format_header_row(ws, row, 1, 6)
        row += 1

        synergies = data.get('cost_synergies', [
            {'name': 'Headcount', 'y1': 2.0, 'y2': 4.0, 'y3': 5.0, 'prob': 0.90},
            {'name': 'Procurement', 'y1': 1.0, 'y2': 2.0, 'y3': 2.5, 'prob': 0.85},
            {'name': 'Facilities', 'y1': 0.5, 'y2': 1.5, 'y3': 2.0, 'prob': 0.75},
        ])
        total = {'y1': 0, 'y2': 0, 'y3': 0, 'run': 0}
        for syn in synergies:
            ws.cell(row=row, column=1, value=syn['name'])
            ws.cell(row=row, column=2, value=syn['y1'])
            ws.cell(row=row, column=3, value=syn['y2'])
            ws.cell(row=row, column=4, value=syn['y3'])
            ws.cell(row=row, column=5, value=syn['y3'])
            ws.cell(row=row, column=6, value=syn['prob'])
            ws.cell(row=row, column=6).number_format = '0%'
            for c in [2,3,4,5]: ws.cell(row=row, column=c).number_format = '#,##0.0'
            total['y1'] += syn['y1']
            total['y2'] += syn['y2']
            total['y3'] += syn['y3']
            total['run'] += syn['y3']
            row += 1

        row += 1
        ws.cell(row=row, column=1, value="Total Cost Synergies")
        ws.cell(row=row, column=5, value=total['run'])
        ws.cell(row=row, column=5).number_format = '#,##0.0'
        ws.cell(row=row, column=5).font = Font(bold=True)
        ws.cell(row=row, column=5).fill = PatternFill(start_color="90EE90", end_color="90EE90", fill_type="solid")

        ws.column_dimensions['A'].width = 25
        for c in ['B','C','D','E','F']: ws.column_dimensions[c].width = 12
        return self

    def add_carveout_analysis(self, data: Dict = None) -> 'ExcelModelGenerator':
        """Add Carve-out Analysis sheet."""
        ws = self.wb.create_sheet("Carve-out")
        self.sheets_created.append("Carve-out")
        a = self.assumptions
        data = data or {}

        self._add_title(ws, f"{self.company_name} - Carve-out Analysis", 1, 1)
        self._add_section_header(ws, "STANDALONE COST ANALYSIS", 3, 1)

        headers = ["Category", "Allocated", "Standalone", "Variance"]
        row = 4
        for i, h in enumerate(headers):
            ws.cell(row=row, column=1+i, value=h)
        self._format_header_row(ws, row, 1, 4)
        row += 1

        costs = data.get('costs', [
            {'name': 'Corporate overhead', 'allocated': 5.0, 'standalone': 3.5},
            {'name': 'IT infrastructure', 'allocated': 3.0, 'standalone': 4.0},
            {'name': 'Finance/Accounting', 'allocated': 2.0, 'standalone': 2.5},
        ])
        total_alloc, total_stand = 0, 0
        for cost in costs:
            ws.cell(row=row, column=1, value=cost['name'])
            ws.cell(row=row, column=2, value=cost['allocated'])
            ws.cell(row=row, column=3, value=cost['standalone'])
            ws.cell(row=row, column=4, value=cost['standalone'] - cost['allocated'])
            for c in [2,3,4]: ws.cell(row=row, column=c).number_format = '#,##0.0'
            total_alloc += cost['allocated']
            total_stand += cost['standalone']
            row += 1

        row += 1
        ws.cell(row=row, column=1, value="Dis-synergies")
        ws.cell(row=row, column=4, value=total_stand - total_alloc)
        ws.cell(row=row, column=4).number_format = '#,##0.0'
        ws.cell(row=row, column=4).font = Font(bold=True, color="FF0000" if total_stand > total_alloc else "008000")

        ws.column_dimensions['A'].width = 25
        for c in ['B','C','D']: ws.column_dimensions[c].width = 15
        return self

    def add_earnout_model(self, data: Dict = None) -> 'ExcelModelGenerator':
        """Add Earnout/Contingent Consideration modeling sheet."""
        ws = self.wb.create_sheet("Earnout Model")
        self.sheets_created.append("Earnout Model")
        data = data or {}

        self._add_title(ws, f"{self.company_name} - Earnout Analysis", 1, 1)
        self._add_section_header(ws, "EARNOUT STRUCTURE", 3, 1)

        row = 4
        upfront = data.get('upfront', 150.0)
        max_earnout = data.get('max_earnout', 50.0)
        ws.cell(row=row, column=1, value="Upfront Consideration")
        ws.cell(row=row, column=2, value=upfront)
        ws.cell(row=row, column=2).number_format = '#,##0.0'
        row += 1
        ws.cell(row=row, column=1, value="Maximum Earnout")
        ws.cell(row=row, column=2, value=max_earnout)
        ws.cell(row=row, column=2).number_format = '#,##0.0'
        row += 3

        self._add_section_header(ws, "SCENARIO ANALYSIS", row, 1)
        row += 1
        headers = ["Scenario", "Prob.", "Payout", "Weighted"]
        for i, h in enumerate(headers):
            ws.cell(row=row, column=1+i, value=h)
        self._format_header_row(ws, row, 1, 4)
        row += 1

        scenarios = data.get('scenarios', [
            {'name': 'Exceed', 'prob': 0.20, 'payout': 50.0},
            {'name': 'Meet', 'prob': 0.45, 'payout': 35.0},
            {'name': 'Partial', 'prob': 0.25, 'payout': 15.0},
            {'name': 'Miss', 'prob': 0.10, 'payout': 0.0},
        ])
        expected = 0
        for sc in scenarios:
            ws.cell(row=row, column=1, value=sc['name'])
            ws.cell(row=row, column=2, value=sc['prob'])
            ws.cell(row=row, column=2).number_format = '0%'
            ws.cell(row=row, column=3, value=sc['payout'])
            ws.cell(row=row, column=3).number_format = '#,##0.0'
            ws.cell(row=row, column=4, value=sc['prob'] * sc['payout'])
            ws.cell(row=row, column=4).number_format = '#,##0.0'
            expected += sc['prob'] * sc['payout']
            row += 1

        row += 1
        ws.cell(row=row, column=1, value="Expected Earnout")
        ws.cell(row=row, column=4, value=expected)
        ws.cell(row=row, column=4).number_format = '#,##0.0'
        ws.cell(row=row, column=4).font = Font(bold=True)
        row += 1
        ws.cell(row=row, column=1, value="Effective Purchase Price")
        ws.cell(row=row, column=4, value=upfront + expected)
        ws.cell(row=row, column=4).number_format = '#,##0.0'
        ws.cell(row=row, column=4).font = Font(bold=True)
        ws.cell(row=row, column=4).fill = PatternFill(start_color="90EE90", end_color="90EE90", fill_type="solid")

        ws.column_dimensions['A'].width = 25
        for c in ['B','C','D']: ws.column_dimensions[c].width = 12
        return self

    def add_purchase_price_allocation(self, data: Dict = None) -> 'ExcelModelGenerator':
        """Add Purchase Price Allocation (PPA) sheet."""
        ws = self.wb.create_sheet("PPA")
        self.sheets_created.append("PPA")
        a = self.assumptions
        data = data or {}

        self._add_title(ws, f"{self.company_name} - Purchase Price Allocation", 1, 1)
        purchase_price = data.get('purchase_price', a.ltm_ebitda * a.entry_multiple)

        self._add_section_header(ws, "ASSETS ACQUIRED AT FAIR VALUE", 3, 1)
        headers = ["Asset", "Book", "Step-Up", "Fair Value"]
        row = 4
        for i, h in enumerate(headers):
            ws.cell(row=row, column=1+i, value=h)
        self._format_header_row(ws, row, 1, 4)
        row += 1

        assets = data.get('assets', [
            {'name': 'Tangible assets', 'book': 50.0, 'stepup': 10.0},
            {'name': 'Customer relationships', 'book': 0.0, 'stepup': 60.0},
            {'name': 'Technology/IP', 'book': 5.0, 'stepup': 30.0},
            {'name': 'Trade name', 'book': 0.0, 'stepup': 15.0},
        ])
        total_fv = 0
        for asset in assets:
            fv = asset['book'] + asset['stepup']
            ws.cell(row=row, column=1, value=asset['name'])
            ws.cell(row=row, column=2, value=asset['book'])
            ws.cell(row=row, column=3, value=asset['stepup'])
            ws.cell(row=row, column=4, value=fv)
            for c in [2,3,4]: ws.cell(row=row, column=c).number_format = '#,##0.0'
            total_fv += fv
            row += 1

        row += 1
        liabilities = data.get('liabilities', 30.0)
        net_assets = total_fv - liabilities
        goodwill = purchase_price - net_assets

        ws.cell(row=row, column=1, value="Total Identifiable Assets")
        ws.cell(row=row, column=4, value=total_fv)
        ws.cell(row=row, column=4).number_format = '#,##0.0'
        row += 1
        ws.cell(row=row, column=1, value="Less: Liabilities")
        ws.cell(row=row, column=4, value=-liabilities)
        ws.cell(row=row, column=4).number_format = '(#,##0.0)'
        row += 1
        ws.cell(row=row, column=1, value="Net Identifiable Assets")
        ws.cell(row=row, column=4, value=net_assets)
        ws.cell(row=row, column=4).number_format = '#,##0.0'
        row += 2
        ws.cell(row=row, column=1, value="Purchase Price")
        ws.cell(row=row, column=4, value=purchase_price)
        ws.cell(row=row, column=4).number_format = '#,##0.0'
        row += 1
        ws.cell(row=row, column=1, value="Goodwill")
        ws.cell(row=row, column=4, value=goodwill)
        ws.cell(row=row, column=4).number_format = '#,##0.0'
        ws.cell(row=row, column=4).font = Font(bold=True)
        ws.cell(row=row, column=4).fill = PatternFill(start_color="FFFF99", end_color="FFFF99", fill_type="solid")

        ws.column_dimensions['A'].width = 25
        for c in ['B','C','D']: ws.column_dimensions[c].width = 15
        return self

    # ============================================================
    # VALUE CREATION & OPERATIONS MODULES
    # ============================================================

    def add_value_creation_bridge(self, data: Dict = None) -> 'ExcelModelGenerator':
        """Add detailed Value Creation Bridge sheet."""
        ws = self.wb.create_sheet("Value Creation")
        self.sheets_created.append("Value Creation")
        a = self.assumptions
        data = data or {}

        self._add_title(ws, f"{self.company_name} - Value Creation Bridge", 1, 1)

        entry_equity = data.get('entry_equity', a.ltm_ebitda * a.entry_multiple * 0.55)
        exit_equity = data.get('exit_equity', entry_equity * 2.5)
        value_created = exit_equity - entry_equity

        self._add_section_header(ws, "VALUE CREATION ATTRIBUTION", 3, 1)
        row = 4
        ws.cell(row=row, column=1, value="Entry Equity Value")
        ws.cell(row=row, column=2, value=entry_equity)
        ws.cell(row=row, column=2).number_format = '#,##0.0'
        row += 2

        attribution = data.get('attribution', [
            {'name': 'Revenue Growth', 'value': value_created * 0.35},
            {'name': 'Margin Improvement', 'value': value_created * 0.25},
            {'name': 'Multiple Expansion', 'value': value_created * 0.15},
            {'name': 'Debt Paydown', 'value': value_created * 0.20},
            {'name': 'Add-on M&A', 'value': value_created * 0.05},
        ])
        for attr in attribution:
            ws.cell(row=row, column=1, value=attr['name'])
            ws.cell(row=row, column=2, value=attr['value'])
            ws.cell(row=row, column=2).number_format = '#,##0.0'
            ws.cell(row=row, column=3, value=attr['value'] / value_created if value_created else 0)
            ws.cell(row=row, column=3).number_format = '0%'
            row += 1

        row += 1
        ws.cell(row=row, column=1, value="Exit Equity Value")
        ws.cell(row=row, column=2, value=exit_equity)
        ws.cell(row=row, column=2).number_format = '#,##0.0'
        ws.cell(row=row, column=2).font = Font(bold=True)
        ws.cell(row=row, column=2).fill = PatternFill(start_color="90EE90", end_color="90EE90", fill_type="solid")

        ws.column_dimensions['A'].width = 25
        ws.column_dimensions['B'].width = 15
        ws.column_dimensions['C'].width = 10
        return self

    def add_hundred_day_plan(self, data: Dict = None) -> 'ExcelModelGenerator':
        """Add 100-Day Plan Tracker sheet."""
        ws = self.wb.create_sheet("100-Day Plan")
        self.sheets_created.append("100-Day Plan")
        data = data or {}

        self._add_title(ws, f"{self.company_name} - 100-Day Plan", 1, 1)
        self._add_section_header(ws, "KEY INITIATIVES", 3, 1)

        headers = ["Initiative", "Owner", "Timeline", "Status", "Value ($M)"]
        row = 4
        for i, h in enumerate(headers):
            ws.cell(row=row, column=1+i, value=h)
        self._format_header_row(ws, row, 1, 5)
        row += 1

        initiatives = data.get('initiatives', [
            {'name': 'Management assessment', 'owner': 'CEO', 'timeline': 'Days 1-30', 'status': 'Complete', 'value': 0},
            {'name': 'Procurement RFP', 'owner': 'CFO', 'timeline': 'Days 30-90', 'status': 'In Progress', 'value': 3.0},
            {'name': 'Sales effectiveness', 'owner': 'CRO', 'timeline': 'Days 30-100', 'status': 'Planning', 'value': 5.0},
            {'name': 'Working capital optimization', 'owner': 'CFO', 'timeline': 'Days 15-75', 'status': 'In Progress', 'value': 1.5},
        ])
        total_value = 0
        for init in initiatives:
            ws.cell(row=row, column=1, value=init['name'])
            ws.cell(row=row, column=2, value=init['owner'])
            ws.cell(row=row, column=3, value=init['timeline'])
            ws.cell(row=row, column=4, value=init['status'])
            ws.cell(row=row, column=5, value=init['value'] if init['value'] > 0 else "—")
            status_colors = {'Complete': "90EE90", 'In Progress': "FFFF99", 'Planning': "FFE4B5"}
            if init['status'] in status_colors:
                ws.cell(row=row, column=4).fill = PatternFill(start_color=status_colors[init['status']], end_color=status_colors[init['status']], fill_type="solid")
            if init['value'] > 0: ws.cell(row=row, column=5).number_format = '#,##0.0'
            total_value += init['value']
            row += 1

        row += 1
        ws.cell(row=row, column=1, value="Total Value at Stake")
        ws.cell(row=row, column=5, value=total_value)
        ws.cell(row=row, column=5).number_format = '#,##0.0'
        ws.cell(row=row, column=5).font = Font(bold=True)
        ws.cell(row=row, column=5).fill = PatternFill(start_color="90EE90", end_color="90EE90", fill_type="solid")

        ws.column_dimensions['A'].width = 30
        for c in ['B','C','D','E']: ws.column_dimensions[c].width = 12
        return self

    def add_exit_readiness(self, data: Dict = None) -> 'ExcelModelGenerator':
        """Add Exit Readiness Assessment sheet."""
        ws = self.wb.create_sheet("Exit Readiness")
        self.sheets_created.append("Exit Readiness")
        data = data or {}

        self._add_title(ws, f"{self.company_name} - Exit Readiness", 1, 1)
        self._add_section_header(ws, "READINESS SCORECARD", 3, 1)

        headers = ["Category", "Score", "Weight", "Weighted"]
        row = 4
        for i, h in enumerate(headers):
            ws.cell(row=row, column=1+i, value=h)
        self._format_header_row(ws, row, 1, 4)
        row += 1

        categories = data.get('categories', [
            {'name': 'Financial Performance', 'score': 4, 'weight': 0.25},
            {'name': 'Management Team', 'score': 4, 'weight': 0.20},
            {'name': 'Growth Profile', 'score': 4, 'weight': 0.20},
            {'name': 'Market Position', 'score': 3, 'weight': 0.15},
            {'name': 'Financial Reporting', 'score': 3, 'weight': 0.10},
            {'name': 'Legal/Compliance', 'score': 4, 'weight': 0.10},
        ])
        total = 0
        for cat in categories:
            ws.cell(row=row, column=1, value=cat['name'])
            ws.cell(row=row, column=2, value=cat['score'])
            ws.cell(row=row, column=3, value=cat['weight'])
            ws.cell(row=row, column=3).number_format = '0%'
            ws.cell(row=row, column=4, value=cat['score'] * cat['weight'])
            ws.cell(row=row, column=4).number_format = '0.0'
            color = "90EE90" if cat['score'] >= 4 else "FFFF99" if cat['score'] >= 3 else "FFB6C1"
            ws.cell(row=row, column=2).fill = PatternFill(start_color=color, end_color=color, fill_type="solid")
            total += cat['score'] * cat['weight']
            row += 1

        row += 1
        ws.cell(row=row, column=1, value="Overall Score")
        ws.cell(row=row, column=4, value=total)
        ws.cell(row=row, column=4).number_format = '0.0'
        ws.cell(row=row, column=4).font = Font(bold=True)
        ws.cell(row=row, column=4).fill = PatternFill(start_color="90EE90", end_color="90EE90", fill_type="solid")

        ws.column_dimensions['A'].width = 25
        for c in ['B','C','D']: ws.column_dimensions[c].width = 12
        return self

    def add_management_incentive_plan(self, data: Dict = None) -> 'ExcelModelGenerator':
        """Add Management Incentive Plan (MIP) sheet."""
        ws = self.wb.create_sheet("Management MIP")
        self.sheets_created.append("Management MIP")
        a = self.assumptions
        data = data or {}

        self._add_title(ws, f"{self.company_name} - Management Incentive Plan", 1, 1)

        mip_pool = data.get('mip_pool_pct', 0.10)
        entry_equity = a.ltm_ebitda * a.entry_multiple * 0.55

        self._add_section_header(ws, "MIP STRUCTURE", 3, 1)
        row = 4
        ws.cell(row=row, column=1, value="MIP Pool (% of equity)")
        ws.cell(row=row, column=2, value=mip_pool)
        ws.cell(row=row, column=2).number_format = '0.0%'
        row += 1
        ws.cell(row=row, column=1, value="MIP Pool Value ($M)")
        ws.cell(row=row, column=2, value=entry_equity * mip_pool)
        ws.cell(row=row, column=2).number_format = '#,##0.0'
        row += 3

        self._add_section_header(ws, "PAYOUT BY EXIT MOIC", row, 1)
        row += 1
        headers = ["Exit MOIC", "Exit Equity", "MIP Value", "CEO (35%)"]
        for i, h in enumerate(headers):
            ws.cell(row=row, column=1+i, value=h)
        self._format_header_row(ws, row, 1, 4)
        row += 1

        for moic in [1.5, 2.0, 2.5, 3.0]:
            exit_equity = entry_equity * moic
            mip_value = exit_equity * mip_pool
            ceo_payout = mip_value * 0.35
            ws.cell(row=row, column=1, value=moic)
            ws.cell(row=row, column=1).number_format = '0.0x'
            ws.cell(row=row, column=2, value=exit_equity)
            ws.cell(row=row, column=3, value=mip_value)
            ws.cell(row=row, column=4, value=ceo_payout)
            for c in [2,3,4]: ws.cell(row=row, column=c).number_format = '#,##0.0'
            row += 1

        ws.column_dimensions['A'].width = 20
        for c in ['B','C','D']: ws.column_dimensions[c].width = 15
        return self

    # ============================================================
    # SPECIALIZED SITUATIONS MODULES
    # ============================================================

    def add_rollup_model(self, data: Dict = None) -> 'ExcelModelGenerator':
        """Add Roll-up/Consolidation Model sheet."""
        ws = self.wb.create_sheet("Roll-up Model")
        self.sheets_created.append("Roll-up Model")
        a = self.assumptions
        data = data or {}

        self._add_title(ws, f"{self.company_name} - Roll-up Strategy", 1, 1)

        platform_ebitda = data.get('platform_ebitda', a.ltm_ebitda)
        self._add_section_header(ws, "ACQUISITION SCHEDULE", 3, 1)

        headers = ["Year", "Target", "EBITDA", "Multiple", "EV"]
        row = 4
        for i, h in enumerate(headers):
            ws.cell(row=row, column=1+i, value=h)
        self._format_header_row(ws, row, 1, 5)
        row += 1

        acquisitions = data.get('acquisitions', [
            {'year': 1, 'name': 'Tuck-in A', 'ebitda': 3.0, 'multiple': 5.0},
            {'year': 2, 'name': 'Regional B', 'ebitda': 5.0, 'multiple': 5.5},
            {'year': 3, 'name': 'Strategic C', 'ebitda': 8.0, 'multiple': 6.0},
        ])
        total_ebitda, total_ev = 0, 0
        for acq in acquisitions:
            ev = acq['ebitda'] * acq['multiple']
            ws.cell(row=row, column=1, value=acq['year'])
            ws.cell(row=row, column=2, value=acq['name'])
            ws.cell(row=row, column=3, value=acq['ebitda'])
            ws.cell(row=row, column=4, value=acq['multiple'])
            ws.cell(row=row, column=5, value=ev)
            ws.cell(row=row, column=3).number_format = '#,##0.0'
            ws.cell(row=row, column=4).number_format = '0.0x'
            ws.cell(row=row, column=5).number_format = '#,##0.0'
            total_ebitda += acq['ebitda']
            total_ev += ev
            row += 1

        row += 1
        combined = platform_ebitda + total_ebitda
        ws.cell(row=row, column=1, value="Pro Forma EBITDA")
        ws.cell(row=row, column=3, value=combined)
        ws.cell(row=row, column=3).number_format = '#,##0.0'
        ws.cell(row=row, column=3).font = Font(bold=True)
        ws.cell(row=row, column=3).fill = PatternFill(start_color="90EE90", end_color="90EE90", fill_type="solid")
        row += 1
        ws.cell(row=row, column=1, value="Blended Acquisition Multiple")
        ws.cell(row=row, column=4, value=total_ev / total_ebitda if total_ebitda else 0)
        ws.cell(row=row, column=4).number_format = '0.0x'
        ws.cell(row=row, column=4).font = Font(bold=True)

        ws.column_dimensions['A'].width = 15
        for c in ['B','C','D','E']: ws.column_dimensions[c].width = 12
        return self

    def add_tax_analysis(self, data: Dict = None) -> 'ExcelModelGenerator':
        """Add Tax Analysis sheet (338(h)(10), step-up, NOLs)."""
        ws = self.wb.create_sheet("Tax Analysis")
        self.sheets_created.append("Tax Analysis")
        a = self.assumptions
        data = data or {}

        self._add_title(ws, f"{self.company_name} - Tax Structure Analysis", 1, 1)

        purchase_price = data.get('purchase_price', a.ltm_ebitda * a.entry_multiple)
        tax_basis = data.get('tax_basis', purchase_price * 0.30)
        step_up = purchase_price - tax_basis

        self._add_section_header(ws, "STEP-UP BENEFIT (338(h)(10))", 3, 1)
        row = 4
        ws.cell(row=row, column=1, value="Purchase Price")
        ws.cell(row=row, column=2, value=purchase_price)
        ws.cell(row=row, column=2).number_format = '#,##0.0'
        row += 1
        ws.cell(row=row, column=1, value="Existing Tax Basis")
        ws.cell(row=row, column=2, value=tax_basis)
        ws.cell(row=row, column=2).number_format = '#,##0.0'
        row += 1
        ws.cell(row=row, column=1, value="Step-Up Amount")
        ws.cell(row=row, column=2, value=step_up)
        ws.cell(row=row, column=2).number_format = '#,##0.0'
        ws.cell(row=row, column=2).font = Font(bold=True)
        row += 2

        # Tax shield calculation
        annual_amort = step_up / 15
        annual_shield = annual_amort * a.tax_rate
        npv_shield = sum(annual_shield / ((1.10) ** i) for i in range(1, 16))

        ws.cell(row=row, column=1, value="Annual Amortization (15 yr)")
        ws.cell(row=row, column=2, value=annual_amort)
        ws.cell(row=row, column=2).number_format = '#,##0.0'
        row += 1
        ws.cell(row=row, column=1, value="Annual Tax Shield")
        ws.cell(row=row, column=2, value=annual_shield)
        ws.cell(row=row, column=2).number_format = '#,##0.0'
        row += 1
        ws.cell(row=row, column=1, value="NPV of Tax Benefit (@10%)")
        ws.cell(row=row, column=2, value=npv_shield)
        ws.cell(row=row, column=2).number_format = '#,##0.0'
        ws.cell(row=row, column=2).font = Font(bold=True)
        ws.cell(row=row, column=2).fill = PatternFill(start_color="90EE90", end_color="90EE90", fill_type="solid")

        ws.column_dimensions['A'].width = 30
        ws.column_dimensions['B'].width = 15
        return self

    def add_control_premium_analysis(self, data: Dict = None) -> 'ExcelModelGenerator':
        """Add Control Premium Analysis sheet."""
        ws = self.wb.create_sheet("Control Premium")
        self.sheets_created.append("Control Premium")
        data = data or {}

        self._add_title(ws, f"{self.company_name} - Control Premium Analysis", 1, 1)

        self._add_section_header(ws, "PRECEDENT TRANSACTION PREMIA", 3, 1)
        headers = ["Target", "1-Day", "30-Day"]
        row = 4
        for i, h in enumerate(headers):
            ws.cell(row=row, column=1+i, value=h)
        self._format_header_row(ws, row, 1, 3)
        row += 1

        transactions = data.get('transactions', [
            {'name': 'Comp A', '1day': 0.25, '30day': 0.35},
            {'name': 'Comp B', '1day': 0.30, '30day': 0.40},
            {'name': 'Comp C', '1day': 0.22, '30day': 0.32},
            {'name': 'Comp D', '1day': 0.28, '30day': 0.38},
        ])
        premia_1d, premia_30d = [], []
        for txn in transactions:
            ws.cell(row=row, column=1, value=txn['name'])
            ws.cell(row=row, column=2, value=txn['1day'])
            ws.cell(row=row, column=2).number_format = '0.0%'
            ws.cell(row=row, column=3, value=txn['30day'])
            ws.cell(row=row, column=3).number_format = '0.0%'
            premia_1d.append(txn['1day'])
            premia_30d.append(txn['30day'])
            row += 1

        row += 1
        mean_30d = sum(premia_30d) / len(premia_30d)
        ws.cell(row=row, column=1, value="Mean Premium")
        ws.cell(row=row, column=2, value=sum(premia_1d)/len(premia_1d))
        ws.cell(row=row, column=2).number_format = '0.0%'
        ws.cell(row=row, column=2).font = Font(bold=True)
        ws.cell(row=row, column=3, value=mean_30d)
        ws.cell(row=row, column=3).number_format = '0.0%'
        ws.cell(row=row, column=3).font = Font(bold=True)
        row += 3

        unaffected = data.get('unaffected_price', 50.0)
        self._add_section_header(ws, "IMPLIED OFFER PRICE", row, 1)
        row += 1
        ws.cell(row=row, column=1, value="Unaffected Share Price")
        ws.cell(row=row, column=2, value=unaffected)
        ws.cell(row=row, column=2).number_format = '$#,##0.00'
        row += 1
        ws.cell(row=row, column=1, value="Selected Premium (30-day)")
        ws.cell(row=row, column=2, value=mean_30d)
        ws.cell(row=row, column=2).number_format = '0.0%'
        row += 1
        ws.cell(row=row, column=1, value="Implied Offer Price")
        ws.cell(row=row, column=2, value=unaffected * (1 + mean_30d))
        ws.cell(row=row, column=2).number_format = '$#,##0.00'
        ws.cell(row=row, column=2).font = Font(bold=True)
        ws.cell(row=row, column=2).fill = PatternFill(start_color="90EE90", end_color="90EE90", fill_type="solid")

        ws.column_dimensions['A'].width = 25
        ws.column_dimensions['B'].width = 12
        ws.column_dimensions['C'].width = 12
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
    """Generate a comprehensive 7+ day LBO model with full institutional modules."""
    a = ModelAssumptions(company_name=company_name)
    if assumptions:
        for key, value in assumptions.items():
            if hasattr(a, key):
                setattr(a, key, value)

    gen = ExcelModelGenerator(company_name, ModelDepth.COMPREHENSIVE, a)

    # Core modules
    gen.add_sources_uses()
    gen.add_revenue_build()
    gen.add_expense_build()
    gen.add_operating_model()
    gen.add_debt_schedule()
    gen.add_working_capital()
    gen.add_wacc_calculation()
    gen.add_returns_analysis()
    gen.add_sensitivity_tables()

    # Institutional modules (7+ day case)
    gen.add_scenario_analysis()
    gen.add_management_vs_buyer()
    gen.add_dcf_valuation()
    gen.add_covenant_analysis()

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
