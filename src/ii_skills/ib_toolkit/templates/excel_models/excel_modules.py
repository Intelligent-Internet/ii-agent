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
from .formula_builder import FormulaBuilder as FB
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

    # Fees
    transaction_fee_pct: float = 0.015  # 1.5% of EV
    financing_fee_pct: float = 0.025    # 2.5% of debt

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

        # Track key cell locations across sheets for cross-references
        self.cell_map = {}  # e.g., {"assumptions": {"ltm_ebitda": "B6", ...}}

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
    # MODULE: ASSUMPTIONS (Central Input Sheet)
    # ============================================================

    def add_assumptions_sheet(self) -> 'ExcelModelGenerator':
        """Add central Assumptions sheet — all model inputs in one place.
        Every other formula-driven sheet references this sheet."""
        ws = self.wb.create_sheet("Assumptions")
        self.sheets_created.append("Assumptions")

        a = self.assumptions

        self._add_title(ws, f"{self.company_name} - Model Assumptions", 1, 1)

        # --- Company / Transaction ---
        self._add_section_header(ws, "Transaction Assumptions", 3, 1)
        self._format_header_row(ws, 3, 1, 2)

        inputs = [
            (5,  "LTM Revenue ($M)",        a.ltm_revenue,            '#,##0.0'),
            (6,  "LTM EBITDA ($M)",         a.ltm_ebitda,             '#,##0.0'),
            (7,  "Entry Multiple",          a.entry_multiple,         '0.0"x"'),
            (8,  "Exit Multiple",           a.exit_multiple,          '0.0"x"'),
            (9,  "Hold Period (Years)",     a.hold_period,            '#,##0'),
        ]

        for row, label, value, fmt in inputs:
            ws.cell(row=row, column=1, value=label)
            cell = ws.cell(row=row, column=2, value=value)
            cell.number_format = fmt
            self._format_input_cell(ws, row, 2)

        # --- Debt Structure ---
        self._add_section_header(ws, "Debt Structure", 11, 1)

        debt_inputs = [
            (12, "Senior Debt Multiple",    a.senior_debt_multiple,   '0.0"x"'),
            (13, "Senior Interest Rate",    a.senior_interest_rate,   '0.0%'),
            (14, "Senior Amortization %",   a.senior_amortization,    '0.0%'),
            (15, "Sub Debt Multiple",       a.sub_debt_multiple,      '0.0"x"'),
            (16, "Sub Interest Rate",       a.sub_interest_rate,      '0.0%'),
        ]

        for row, label, value, fmt in debt_inputs:
            ws.cell(row=row, column=1, value=label)
            cell = ws.cell(row=row, column=2, value=value)
            cell.number_format = fmt
            self._format_input_cell(ws, row, 2)

        # --- Fees & Rates ---
        self._add_section_header(ws, "Fees & Rates", 18, 1)

        fee_inputs = [
            (19, "Transaction Fee %",       a.transaction_fee_pct,    '0.0%'),
            (20, "Financing Fee %",         a.financing_fee_pct,      '0.0%'),
            (22, "CapEx % Revenue",         a.capex_pct_revenue,      '0.0%'),
            (23, "NWC % Revenue",           a.nwc_pct_revenue,        '0.0%'),
            (24, "Tax Rate",                a.tax_rate,               '0.0%'),
        ]

        for row, label, value, fmt in fee_inputs:
            ws.cell(row=row, column=1, value=label)
            cell = ws.cell(row=row, column=2, value=value)
            cell.number_format = fmt
            self._format_input_cell(ws, row, 2)

        # --- Projection Drivers (Year 1–5 across columns C–G) ---
        self._add_section_header(ws, "Projection Drivers", 26, 1)

        # Column headers
        for i in range(self.projection_years):
            ws.cell(row=27, column=3 + i, value=f"Year {i + 1}")
            ws.cell(row=27, column=3 + i).font = Font(bold=True)
            ws.cell(row=27, column=3 + i).alignment = Alignment(horizontal='center')

        # Revenue Growth (row 28, cols C–G)
        ws.cell(row=28, column=1, value="Revenue Growth %")
        for i, g in enumerate(a.revenue_growth[:self.projection_years]):
            cell = ws.cell(row=28, column=3 + i, value=g)
            cell.number_format = '0.0%'
            self._format_input_cell(ws, 28, 3 + i)

        # EBITDA Margin (row 29, cols C–G)
        ws.cell(row=29, column=1, value="EBITDA Margin %")
        for i, m in enumerate(a.ebitda_margin[:self.projection_years]):
            cell = ws.cell(row=29, column=3 + i, value=m)
            cell.number_format = '0.0%'
            self._format_input_cell(ws, 29, 3 + i)

        # Column widths
        ws.column_dimensions['A'].width = 25
        ws.column_dimensions['B'].width = 15
        for i in range(self.projection_years):
            ws.column_dimensions[get_column_letter(3 + i)].width = 12

        # Store cell locations for cross-references
        self.cell_map['assumptions'] = {
            'ltm_revenue': 'B5',
            'ltm_ebitda': 'B6',
            'entry_multiple': 'B7',
            'exit_multiple': 'B8',
            'hold_period': 'B9',
            'senior_debt_mult': 'B12',
            'senior_rate': 'B13',
            'senior_amort': 'B14',
            'sub_debt_mult': 'B15',
            'sub_rate': 'B16',
            'txn_fee_pct': 'B19',
            'fin_fee_pct': 'B20',
            'capex_pct': 'B22',
            'nwc_pct': 'B23',
            'tax_rate': 'B24',
            'rev_growth_row': 28,       # row number, cols C onward
            'ebitda_margin_row': 29,    # row number, cols C onward
        }

        return self

    # ============================================================
    # MODULE: SOURCES & USES
    # ============================================================

    def add_sources_uses(self, data: Dict = None) -> 'ExcelModelGenerator':
        """Add Sources & Uses sheet with real Excel formulas referencing Assumptions."""
        ws = self.wb.create_sheet("Sources & Uses")
        self.sheets_created.append("Sources & Uses")

        A = "Assumptions"  # sheet name for cross-refs

        # Title
        self._add_title(ws, f"{self.company_name} - Sources & Uses", 1, 1)

        # Sources section
        self._add_section_header(ws, "Sources", 3, 1)
        ws.cell(row=3, column=2, value="$M")
        ws.cell(row=3, column=3, value="% of Total")
        self._format_header_row(ws, 3, 1, 3)

        # Row 4: Senior Debt = LTM EBITDA × Senior Debt Multiple
        ws.cell(row=4, column=1, value="Senior Secured Debt")
        ws.cell(row=4, column=2, value=f"='{A}'!B6*'{A}'!B12")
        ws.cell(row=4, column=2).number_format = '#,##0.0'
        ws.cell(row=4, column=3, value="=B4/$B$7")
        ws.cell(row=4, column=3).number_format = '0.0%'
        self._format_input_cell(ws, 4, 2)

        # Row 5: Sub Debt = LTM EBITDA × Sub Debt Multiple
        ws.cell(row=5, column=1, value="Subordinated Debt")
        ws.cell(row=5, column=2, value=f"='{A}'!B6*'{A}'!B15")
        ws.cell(row=5, column=2).number_format = '#,##0.0'
        ws.cell(row=5, column=3, value="=B5/$B$7")
        ws.cell(row=5, column=3).number_format = '0.0%'
        self._format_input_cell(ws, 5, 2)

        # Row 6: Sponsor Equity = Total Uses - Senior - Sub
        ws.cell(row=6, column=1, value="Sponsor Equity")
        ws.cell(row=6, column=2, value="=B12-B4-B5")
        ws.cell(row=6, column=2).number_format = '#,##0.0'
        ws.cell(row=6, column=3, value="=B6/$B$7")
        ws.cell(row=6, column=3).number_format = '0.0%'

        # Row 7: Total Sources
        ws.cell(row=7, column=1, value="Total Sources")
        ws.cell(row=7, column=2, value="=SUM(B4:B6)")
        ws.cell(row=7, column=2).number_format = '#,##0.0'
        ws.cell(row=7, column=3, value="=1")
        ws.cell(row=7, column=3).number_format = '0.0%'
        for col in range(1, 4):
            ws.cell(row=7, column=col).font = Font(bold=True)
            ws.cell(row=7, column=col).border = DOUBLE_BORDER

        # Uses section (row 9)
        self._add_section_header(ws, "Uses", 9, 1)
        ws.cell(row=9, column=2, value="$M")
        ws.cell(row=9, column=3, value="% of Total")
        self._format_header_row(ws, 9, 1, 3)

        # Row 10: Purchase EV = LTM EBITDA × Entry Multiple
        ws.cell(row=10, column=1, value="Purchase Enterprise Value")
        ws.cell(row=10, column=2, value=f"='{A}'!B6*'{A}'!B7")
        ws.cell(row=10, column=2).number_format = '#,##0.0'
        ws.cell(row=10, column=3, value="=B10/$B$12")
        ws.cell(row=10, column=3).number_format = '0.0%'

        # Row 11: Transaction Fees = EV × Fee %
        ws.cell(row=11, column=1, value="Transaction Fees")
        ws.cell(row=11, column=2, value=f"=B10*'{A}'!B19")
        ws.cell(row=11, column=2).number_format = '#,##0.0'
        ws.cell(row=11, column=3, value="=B11/$B$12")
        ws.cell(row=11, column=3).number_format = '0.0%'

        # Row 12 (was Financing Fees, move to 12 for Fin Fees): Financing Fees = Total Debt × Fin Fee %
        # Actually let's put Fin Fees at 12 and Total at 13
        ws.cell(row=12, column=1, value="Financing Fees")
        ws.cell(row=12, column=2, value=f"=(B4+B5)*'{A}'!B20")
        ws.cell(row=12, column=2).number_format = '#,##0.0'
        ws.cell(row=12, column=3, value="=B12/$B$13")
        ws.cell(row=12, column=3).number_format = '0.0%'

        # Fix % of total references to point to row 13 (total uses)
        ws.cell(row=10, column=3, value="=B10/$B$13")
        ws.cell(row=11, column=3, value="=B11/$B$13")
        ws.cell(row=12, column=3, value="=B12/$B$13")

        # Row 13: Total Uses
        ws.cell(row=13, column=1, value="Total Uses")
        ws.cell(row=13, column=2, value="=SUM(B10:B12)")
        ws.cell(row=13, column=2).number_format = '#,##0.0'
        ws.cell(row=13, column=3, value="=1")
        ws.cell(row=13, column=3).number_format = '0.0%'
        for col in range(1, 4):
            ws.cell(row=13, column=col).font = Font(bold=True)
            ws.cell(row=13, column=col).border = DOUBLE_BORDER

        # Key metrics (row 15)
        self._add_section_header(ws, "Key Metrics", 15, 1)

        ws.cell(row=16, column=1, value="Entry EV / EBITDA")
        ws.cell(row=16, column=2, value=f"='{A}'!B7")
        ws.cell(row=16, column=2).number_format = '0.0"x"'

        ws.cell(row=17, column=1, value="Total Debt / EBITDA")
        ws.cell(row=17, column=2, value=f"=(B4+B5)/'{A}'!B6")
        ws.cell(row=17, column=2).number_format = '0.0"x"'

        ws.cell(row=18, column=1, value="Senior Debt / EBITDA")
        ws.cell(row=18, column=2, value=f"=B4/'{A}'!B6")
        ws.cell(row=18, column=2).number_format = '0.0"x"'

        ws.cell(row=19, column=1, value="Equity Check ($M)")
        ws.cell(row=19, column=2, value="=B6")
        ws.cell(row=19, column=2).number_format = '#,##0.0'

        ws.cell(row=20, column=1, value="Equity / EV")
        ws.cell(row=20, column=2, value="=B6/B10")
        ws.cell(row=20, column=2).number_format = '0.0%'

        # Set column widths
        ws.column_dimensions['A'].width = 25
        ws.column_dimensions['B'].width = 15
        ws.column_dimensions['C'].width = 12

        # Store cell map
        self.cell_map['sources_uses'] = {
            'senior_debt': 'B4',
            'sub_debt': 'B5',
            'equity': 'B6',
            'total_sources': 'B7',
            'purchase_ev': 'B10',
            'total_uses': 'B13',
        }

        return self

    # ============================================================
    # MODULE: OPERATING MODEL
    # ============================================================

    def add_operating_model(self, data: Dict = None) -> 'ExcelModelGenerator':
        """Add Operating Model sheet with real Excel formulas referencing Assumptions."""
        ws = self.wb.create_sheet("Operating Model")
        self.sheets_created.append("Operating Model")

        A = "Assumptions"
        n = self.projection_years  # typically 5
        # Column layout: B=LTM, C=Year1, D=Year2, ...
        ltm_col = 2        # column B
        y1_col = 3          # column C

        # Title
        self._add_title(ws, f"{self.company_name} - Operating Model", 1, 1)

        # Year headers
        self._year_headers(ws, 3, 2)

        # --- Assumptions section (rows 4-7) ---
        self._add_section_header(ws, "Assumptions", 4, 1)

        # Row 5: Revenue Growth % — LTM is "—", Y1+ reference Assumptions row 28
        ws.cell(row=5, column=1, value="Revenue Growth %")
        ws.cell(row=5, column=ltm_col, value="—")
        for i in range(n):
            col = y1_col + i
            # Reference Assumptions!C28, D28, etc.
            ws.cell(row=5, column=col, value=f"='{A}'!{get_column_letter(3 + i)}28")
            ws.cell(row=5, column=col).number_format = '0.0%'
            self._format_input_cell(ws, 5, col)

        # Row 6: EBITDA Margin % — LTM = EBITDA/Revenue, Y1+ reference Assumptions row 29
        ws.cell(row=6, column=1, value="EBITDA Margin %")
        ws.cell(row=6, column=ltm_col, value=f"='{A}'!B6/'{A}'!B5")
        ws.cell(row=6, column=ltm_col).number_format = '0.0%'
        for i in range(n):
            col = y1_col + i
            ws.cell(row=6, column=col, value=f"='{A}'!{get_column_letter(3 + i)}29")
            ws.cell(row=6, column=col).number_format = '0.0%'
            self._format_input_cell(ws, 6, col)

        # Row 7: CapEx % Revenue — all periods reference Assumptions!B22
        ws.cell(row=7, column=1, value="CapEx % Revenue")
        for i in range(n + 1):
            col = ltm_col + i
            ws.cell(row=7, column=col, value=f"='{A}'!B22")
            ws.cell(row=7, column=col).number_format = '0.0%'
            self._format_input_cell(ws, 7, col)

        # --- Operating Model section (rows 9+) ---
        self._add_section_header(ws, "Operating Model ($M)", 9, 1)

        # Row 10: Revenue — LTM from Assumptions, Y1+ = prior × (1 + growth)
        ws.cell(row=10, column=1, value="Revenue")
        ws.cell(row=10, column=ltm_col, value=f"='{A}'!B5")
        ws.cell(row=10, column=ltm_col).number_format = '#,##0.0'
        for i in range(n):
            col = y1_col + i
            prev = get_column_letter(col - 1)
            this = get_column_letter(col)
            ws.cell(row=10, column=col, value=f"={prev}10*(1+{this}5)")
            ws.cell(row=10, column=col).number_format = '#,##0.0'

        # Row 11: % Growth — LTM is "—", Y1+ = (this/prior)-1
        ws.cell(row=11, column=1, value="  % Growth")
        ws.cell(row=11, column=ltm_col, value="—")
        for i in range(n):
            col = y1_col + i
            prev = get_column_letter(col - 1)
            this = get_column_letter(col)
            ws.cell(row=11, column=col, value=f"={this}10/{prev}10-1")
            ws.cell(row=11, column=col).number_format = '0.0%'
            ws.cell(row=11, column=col).font = Font(italic=True, color="666666")

        # Row 13: EBITDA — LTM from Assumptions, Y1+ = Revenue × Margin
        ws.cell(row=13, column=1, value="EBITDA")
        ws.cell(row=13, column=ltm_col, value=f"='{A}'!B6")
        ws.cell(row=13, column=ltm_col).number_format = '#,##0.0'
        for i in range(n):
            col = y1_col + i
            this = get_column_letter(col)
            ws.cell(row=13, column=col, value=f"={this}10*{this}6")
            ws.cell(row=13, column=col).number_format = '#,##0.0'

        # Row 14: % Margin = EBITDA / Revenue
        ws.cell(row=14, column=1, value="  % Margin")
        for i in range(n + 1):
            col = ltm_col + i
            this = get_column_letter(col)
            ws.cell(row=14, column=col, value=f"={this}13/{this}10")
            ws.cell(row=14, column=col).number_format = '0.0%'
            ws.cell(row=14, column=col).font = Font(italic=True, color="666666")

        # Row 16: CapEx = -Revenue × CapEx%
        ws.cell(row=16, column=1, value="CapEx")
        for i in range(n + 1):
            col = ltm_col + i
            this = get_column_letter(col)
            ws.cell(row=16, column=col, value=f"=-{this}10*{this}7")
            ws.cell(row=16, column=col).number_format = '(#,##0.0)'

        # Row 17: D&A = -CapEx (same magnitude, positive)
        ws.cell(row=17, column=1, value="D&A")
        for i in range(n + 1):
            col = ltm_col + i
            this = get_column_letter(col)
            ws.cell(row=17, column=col, value=f"=-{this}16")
            ws.cell(row=17, column=col).number_format = '#,##0.0'

        # Row 19: EBITDA - CapEx
        ws.cell(row=19, column=1, value="EBITDA - CapEx")
        for i in range(n + 1):
            col = ltm_col + i
            this = get_column_letter(col)
            ws.cell(row=19, column=col, value=f"={this}13+{this}16")
            ws.cell(row=19, column=col).number_format = '#,##0.0'
            ws.cell(row=19, column=col).font = Font(bold=True)

        # Set column widths
        ws.column_dimensions['A'].width = 20
        for i in range(n + 2):
            ws.column_dimensions[get_column_letter(2 + i)].width = 12

        # Store cell map
        self.cell_map['operating_model'] = {
            'revenue_row': 10,
            'ebitda_row': 13,
            'capex_row': 16,
            'ebitda_minus_capex_row': 19,
            'ltm_col': ltm_col,
            'y1_col': y1_col,
        }

        return self

    # ============================================================
    # MODULE: REVENUE BUILD
    # ============================================================

    def add_revenue_build(self, data: Dict = None) -> 'ExcelModelGenerator':
        """Add detailed Revenue Build sheet with real Excel formulas."""
        ws = self.wb.create_sheet("Revenue Build")
        self.sheets_created.append("Revenue Build")

        A = "Assumptions"
        a = self.assumptions
        n = self.projection_years

        # Title
        self._add_title(ws, f"{self.company_name} - Revenue Build", 1, 1)

        # Year headers
        self._year_headers(ws, 3, 2)

        if self.depth == ModelDepth.QUICK:
            # Simple: total revenue with formulas referencing Assumptions
            self._add_section_header(ws, "Revenue Projections ($M)", 4, 1)

            # Row 5: Total Revenue — LTM from Assumptions, projections via growth formula
            ws.cell(row=5, column=1, value="Total Revenue")
            ws.cell(row=5, column=2, value=f"='{A}'!B5")  # LTM Revenue
            ws.cell(row=5, column=2).number_format = '#,##0.0'
            for i in range(n):
                prev_col = get_column_letter(2 + i)
                growth_col = get_column_letter(3 + i)
                ws.cell(row=5, column=3 + i,
                        value=f"={prev_col}5*(1+'{A}'!{growth_col}28)")
                ws.cell(row=5, column=3 + i).number_format = '#,##0.0'

            # Row 6: Growth % — references from Assumptions row 28
            ws.cell(row=6, column=1, value="  % Growth")
            ws.cell(row=6, column=2, value="—")
            for i in range(n):
                growth_col = get_column_letter(3 + i)
                ws.cell(row=6, column=3 + i, value=f"='{A}'!{growth_col}28")
                ws.cell(row=6, column=3 + i).number_format = '0.0%'
                self._format_input_cell(ws, 6, 3 + i)

            self.cell_map['revenue_build'] = {
                'total_revenue_row': 5,
                'growth_row': 6,
                'ltm_col': 2,
                'y1_col': 3,
            }

        else:
            # Standard/Comprehensive: Segment breakdown with formulas
            data = data or {}
            segments = data.get('segments', [
                {"name": "Segment A", "pct": 0.50, "growth": [0.10, 0.09, 0.08, 0.07, 0.06]},
                {"name": "Segment B", "pct": 0.30, "growth": [0.06, 0.05, 0.05, 0.04, 0.04]},
                {"name": "Segment C", "pct": 0.20, "growth": [0.04, 0.03, 0.03, 0.02, 0.02]},
            ])

            # Segment assumptions (input cells — stay as values)
            self._add_section_header(ws, "Segment Assumptions", 4, 1)
            ws.cell(row=5, column=1, value="Segment")
            ws.cell(row=5, column=2, value="LTM %")
            for i in range(n):
                ws.cell(row=5, column=3 + i, value=f"Y{i+1} Growth")
            self._format_header_row(ws, 5, 1, 2 + n)

            for j, seg in enumerate(segments):
                row = 6 + j
                ws.cell(row=row, column=1, value=seg["name"])
                ws.cell(row=row, column=2, value=seg["pct"])
                ws.cell(row=row, column=2).number_format = '0.0%'
                self._format_input_cell(ws, row, 2)

                for i, g in enumerate(seg["growth"][:n]):
                    cell = ws.cell(row=row, column=3 + i, value=g)
                    cell.number_format = '0.0%'
                    self._format_input_cell(ws, row, 3 + i)

            # Revenue by segment — formulas referencing Assumptions + segment inputs
            seg_start = 6 + len(segments) + 1
            self._add_section_header(ws, "Revenue by Segment ($M)", seg_start, 1)

            for j, seg in enumerate(segments):
                row = seg_start + 1 + j
                seg_input_row = 6 + j  # Row with this segment's pct and growth
                ws.cell(row=row, column=1, value=seg["name"])

                # LTM: =Assumptions!B5 * segment_pct
                pct_cell = f"B{seg_input_row}"
                ws.cell(row=row, column=2, value=f"='{A}'!B5*{pct_cell}")
                ws.cell(row=row, column=2).number_format = '#,##0.0'

                # Projected: =prev_revenue * (1 + segment_growth)
                for i in range(n):
                    prev_col = get_column_letter(2 + i)
                    growth_col = get_column_letter(3 + i)
                    ws.cell(row=row, column=3 + i,
                            value=f"={prev_col}{row}*(1+{growth_col}{seg_input_row})")
                    ws.cell(row=row, column=3 + i).number_format = '#,##0.0'

            # Total revenue — SUM formula
            total_row = seg_start + 1 + len(segments)
            ws.cell(row=total_row, column=1, value="Total Revenue")

            for i in range(n + 1):
                start_row = seg_start + 1
                end_row = total_row - 1
                col_letter = get_column_letter(2 + i)
                ws.cell(row=total_row, column=2 + i,
                       value=f"=SUM({col_letter}{start_row}:{col_letter}{end_row})")
                ws.cell(row=total_row, column=2 + i).number_format = '#,##0.0'
                ws.cell(row=total_row, column=2 + i).font = Font(bold=True)
                ws.cell(row=total_row, column=2 + i).border = DOUBLE_BORDER

            self.cell_map['revenue_build'] = {
                'total_revenue_row': total_row,
                'seg_start_row': seg_start + 1,
                'seg_count': len(segments),
                'ltm_col': 2,
                'y1_col': 3,
            }

        # Set column widths
        ws.column_dimensions['A'].width = 20
        for i in range(n + 2):
            ws.column_dimensions[get_column_letter(2 + i)].width = 12

        return self

    # ============================================================
    # MODULE: EXPENSE BUILD (SG&A BREAKOUT)
    # ============================================================

    def add_expense_build(self, data: Dict = None) -> 'ExcelModelGenerator':
        """Add Expense / SG&A Build sheet with real Excel formulas."""
        ws = self.wb.create_sheet("Expense Build")
        self.sheets_created.append("Expense Build")

        A = "Assumptions"
        OM = "Operating Model"
        a = self.assumptions
        n = self.projection_years

        # Title
        self._add_title(ws, f"{self.company_name} - Expense Build", 1, 1)

        # Year headers
        self._year_headers(ws, 3, 2)

        # Revenue reference row — pull from Operating Model row 10
        om_rev_row = self.cell_map.get('operating_model', {}).get('revenue_row', 10)

        if self.depth == ModelDepth.QUICK:
            # Simple: COGS and SG&A as % of revenue (input cells stay as values)
            self._add_section_header(ws, "Cost Assumptions (% Revenue)", 4, 1)

            cogs_pct = 0.60
            sga_pct = 0.20

            ws.cell(row=5, column=1, value="COGS %")
            for i in range(n + 1):
                cell = ws.cell(row=5, column=2 + i, value=cogs_pct)
                cell.number_format = '0.0%'
                self._format_input_cell(ws, 5, 2 + i)

            ws.cell(row=6, column=1, value="SG&A %")
            for i in range(n + 1):
                cell = ws.cell(row=6, column=2 + i, value=sga_pct)
                cell.number_format = '0.0%'
                self._format_input_cell(ws, 6, 2 + i)

            # Calculated values — formulas referencing OM revenue × local %
            self._add_section_header(ws, "Expense Summary ($M)", 8, 1)

            ws.cell(row=9, column=1, value="COGS")
            for i in range(n + 1):
                col = get_column_letter(2 + i)
                ws.cell(row=9, column=2 + i,
                        value=f"='{OM}'!{col}{om_rev_row}*{col}5")
                ws.cell(row=9, column=2 + i).number_format = '#,##0.0'

            ws.cell(row=10, column=1, value="Gross Profit")
            for i in range(n + 1):
                col = get_column_letter(2 + i)
                ws.cell(row=10, column=2 + i,
                        value=f"='{OM}'!{col}{om_rev_row}-{col}9")
                ws.cell(row=10, column=2 + i).number_format = '#,##0.0'
                ws.cell(row=10, column=2 + i).font = Font(bold=True)

            ws.cell(row=12, column=1, value="SG&A")
            for i in range(n + 1):
                col = get_column_letter(2 + i)
                ws.cell(row=12, column=2 + i,
                        value=f"='{OM}'!{col}{om_rev_row}*{col}6")
                ws.cell(row=12, column=2 + i).number_format = '#,##0.0'

            self.cell_map['expense_build'] = {
                'cogs_pct_row': 5,
                'sga_pct_row': 6,
                'cogs_row': 9,
                'gross_profit_row': 10,
                'sga_row': 12,
            }

        else:
            # Standard/Comprehensive: Detailed breakdown with formulas
            data = data or {}
            self._add_section_header(ws, "COGS Breakdown ($M)", 4, 1)

            cogs_items = data.get('cogs_items', [
                {"name": "Materials", "pct": 0.35},
                {"name": "Direct Labor", "pct": 0.15},
                {"name": "Manufacturing OH", "pct": 0.10},
            ])

            # COGS line items: formula = OM Revenue × item_pct (input in adjacent row)
            # First write pct input rows, then formula rows
            # Layout: Row 5+ = item name + pct input | formula = OM_rev * pct
            for j, item in enumerate(cogs_items):
                row = 5 + j
                ws.cell(row=row, column=1, value=item["name"])
                for i in range(n + 1):
                    col = get_column_letter(2 + i)
                    # Write pct as input value (these are the driver assumptions)
                    ws.cell(row=row, column=2 + i, value=item["pct"])
                    ws.cell(row=row, column=2 + i).number_format = '0.0%'
                    self._format_input_cell(ws, row, 2 + i)

            # COGS $ rows (formulas)
            cogs_dollar_start = 5 + len(cogs_items) + 1
            self._add_section_header(ws, "COGS ($M)", cogs_dollar_start - 1, 1)

            for j, item in enumerate(cogs_items):
                row = cogs_dollar_start + j
                pct_row = 5 + j
                ws.cell(row=row, column=1, value=f"{item['name']} $")
                for i in range(n + 1):
                    col = get_column_letter(2 + i)
                    ws.cell(row=row, column=2 + i,
                            value=f"='{OM}'!{col}{om_rev_row}*{col}{pct_row}")
                    ws.cell(row=row, column=2 + i).number_format = '#,##0.0'

            cogs_total_row = cogs_dollar_start + len(cogs_items)
            ws.cell(row=cogs_total_row, column=1, value="Total COGS")
            for i in range(n + 1):
                col = get_column_letter(2 + i)
                ws.cell(row=cogs_total_row, column=2 + i,
                        value=f"=SUM({col}{cogs_dollar_start}:{col}{cogs_total_row - 1})")
                ws.cell(row=cogs_total_row, column=2 + i).number_format = '#,##0.0'
                ws.cell(row=cogs_total_row, column=2 + i).font = Font(bold=True)
                ws.cell(row=cogs_total_row, column=2 + i).border = BOTTOM_BORDER

            # SG&A breakdown
            sga_pct_start = cogs_total_row + 2
            self._add_section_header(ws, "SG&A Assumptions (% Revenue)", sga_pct_start, 1)

            sga_items = data.get('sga_items', [
                {"name": "Sales & Marketing", "pct": 0.08},
                {"name": "General & Admin", "pct": 0.05},
                {"name": "R&D", "pct": 0.04},
                {"name": "Other", "pct": 0.03},
            ])

            for j, item in enumerate(sga_items):
                row = sga_pct_start + 1 + j
                ws.cell(row=row, column=1, value=item["name"])
                for i in range(n + 1):
                    ws.cell(row=row, column=2 + i, value=item["pct"])
                    ws.cell(row=row, column=2 + i).number_format = '0.0%'
                    self._format_input_cell(ws, row, 2 + i)

            # SG&A $ rows (formulas)
            sga_dollar_start = sga_pct_start + 1 + len(sga_items) + 1
            self._add_section_header(ws, "SG&A ($M)", sga_dollar_start - 1, 1)

            for j, item in enumerate(sga_items):
                row = sga_dollar_start + j
                pct_row = sga_pct_start + 1 + j
                ws.cell(row=row, column=1, value=f"{item['name']} $")
                for i in range(n + 1):
                    col = get_column_letter(2 + i)
                    ws.cell(row=row, column=2 + i,
                            value=f"='{OM}'!{col}{om_rev_row}*{col}{pct_row}")
                    ws.cell(row=row, column=2 + i).number_format = '#,##0.0'

            sga_total_row = sga_dollar_start + len(sga_items)
            ws.cell(row=sga_total_row, column=1, value="Total SG&A")
            for i in range(n + 1):
                col = get_column_letter(2 + i)
                ws.cell(row=sga_total_row, column=2 + i,
                        value=f"=SUM({col}{sga_dollar_start}:{col}{sga_total_row - 1})")
                ws.cell(row=sga_total_row, column=2 + i).number_format = '#,##0.0'
                ws.cell(row=sga_total_row, column=2 + i).font = Font(bold=True)
                ws.cell(row=sga_total_row, column=2 + i).border = BOTTOM_BORDER

            # P&L Summary — all formulas
            summary_start = sga_total_row + 2
            self._add_section_header(ws, "P&L Summary ($M)", summary_start, 1)

            ws.cell(row=summary_start + 1, column=1, value="Revenue")
            for i in range(n + 1):
                col = get_column_letter(2 + i)
                ws.cell(row=summary_start + 1, column=2 + i,
                        value=f"='{OM}'!{col}{om_rev_row}")
                ws.cell(row=summary_start + 1, column=2 + i).number_format = '#,##0.0'

            ws.cell(row=summary_start + 2, column=1, value="Gross Profit")
            for i in range(n + 1):
                col = get_column_letter(2 + i)
                ws.cell(row=summary_start + 2, column=2 + i,
                        value=f"={col}{summary_start + 1}-{col}{cogs_total_row}")
                ws.cell(row=summary_start + 2, column=2 + i).number_format = '#,##0.0'

            ws.cell(row=summary_start + 3, column=1, value="  Gross Margin %")
            for i in range(n + 1):
                col = get_column_letter(2 + i)
                ws.cell(row=summary_start + 3, column=2 + i,
                        value=f"=IFERROR({col}{summary_start + 2}/{col}{summary_start + 1},0)")
                ws.cell(row=summary_start + 3, column=2 + i).number_format = '0.0%'
                ws.cell(row=summary_start + 3, column=2 + i).font = Font(italic=True, color="666666")

            ws.cell(row=summary_start + 5, column=1, value="EBITDA")
            for i in range(n + 1):
                col = get_column_letter(2 + i)
                ws.cell(row=summary_start + 5, column=2 + i,
                        value=f"={col}{summary_start + 2}-{col}{sga_total_row}")
                ws.cell(row=summary_start + 5, column=2 + i).number_format = '#,##0.0'
                ws.cell(row=summary_start + 5, column=2 + i).font = Font(bold=True)

            ws.cell(row=summary_start + 6, column=1, value="  EBITDA Margin %")
            for i in range(n + 1):
                col = get_column_letter(2 + i)
                ws.cell(row=summary_start + 6, column=2 + i,
                        value=f"=IFERROR({col}{summary_start + 5}/{col}{summary_start + 1},0)")
                ws.cell(row=summary_start + 6, column=2 + i).number_format = '0.0%'
                ws.cell(row=summary_start + 6, column=2 + i).font = Font(italic=True, color="666666")

            self.cell_map['expense_build'] = {
                'cogs_pct_start': 5,
                'cogs_dollar_start': cogs_dollar_start,
                'cogs_total_row': cogs_total_row,
                'sga_pct_start': sga_pct_start + 1,
                'sga_dollar_start': sga_dollar_start,
                'sga_total_row': sga_total_row,
                'summary_revenue_row': summary_start + 1,
                'summary_ebitda_row': summary_start + 5,
            }

        # Set column widths
        ws.column_dimensions['A'].width = 20
        for i in range(self.projection_years + 2):
            ws.column_dimensions[get_column_letter(2 + i)].width = 12

        return self

    # ============================================================
    # MODULE: DEBT SCHEDULE
    # ============================================================

    def add_debt_schedule(self, data: Dict = None) -> 'ExcelModelGenerator':
        """Add Debt Schedule sheet with real Excel formulas."""
        ws = self.wb.create_sheet("Debt Schedule")
        self.sheets_created.append("Debt Schedule")

        A = "Assumptions"
        OM = "Operating Model"
        n = self.projection_years
        # Column layout: B=Entry, C=Year1, D=Year2, ...
        entry_col = 2
        y1_col = 3

        # Title
        self._add_title(ws, f"{self.company_name} - Debt Schedule", 1, 1)

        # Year headers
        ws.cell(row=3, column=1, value="")
        ws.cell(row=3, column=2, value="Entry")
        for i in range(n):
            ws.cell(row=3, column=y1_col + i, value=f"Year {i + 1}")
        self._format_header_row(ws, 3, 1, entry_col + n)

        if self.depth == ModelDepth.QUICK:
            # --- QUICK: Single tranche with flat paydown ---
            self._add_section_header(ws, "Debt Assumptions", 4, 1)

            # Row 5: Initial Debt = EBITDA × (Senior + Sub multiples)
            ws.cell(row=5, column=1, value="Initial Debt ($M)")
            ws.cell(row=5, column=2, value=f"='{A}'!B6*('{A}'!B12+'{A}'!B15)")
            ws.cell(row=5, column=2).number_format = '#,##0.0'
            self._format_input_cell(ws, 5, 2)

            # Row 6: Blended Interest Rate = average of senior and sub
            ws.cell(row=6, column=1, value="Interest Rate")
            ws.cell(row=6, column=2, value=f"=('{A}'!B13+'{A}'!B16)/2")
            ws.cell(row=6, column=2).number_format = '0.0%'
            self._format_input_cell(ws, 6, 2)

            # Row 7: Annual Paydown = 10% of initial debt
            ws.cell(row=7, column=1, value="Annual Paydown ($M)")
            ws.cell(row=7, column=2, value="=B5*0.1")
            ws.cell(row=7, column=2).number_format = '#,##0.0'
            self._format_input_cell(ws, 7, 2)

            # Debt schedule
            self._add_section_header(ws, "Debt Schedule ($M)", 9, 1)

            # Row 10: Beginning Balance — Entry=Initial, Y1+=prior ending
            ws.cell(row=10, column=1, value="Beginning Balance")
            ws.cell(row=10, column=entry_col, value="=B5")
            ws.cell(row=10, column=entry_col).number_format = '#,##0.0'
            for i in range(n):
                col = y1_col + i
                prev = get_column_letter(col - 1)
                this = get_column_letter(col)
                if i == 0:
                    ws.cell(row=10, column=col, value="=B5")  # Entry = initial
                else:
                    ws.cell(row=10, column=col, value=f"={prev}12")  # prior ending
                ws.cell(row=10, column=col).number_format = '#,##0.0'

            # Row 11: Paydown
            ws.cell(row=11, column=1, value="Paydown")
            for i in range(n):
                col = y1_col + i
                ws.cell(row=11, column=col, value="=-$B$7")
                ws.cell(row=11, column=col).number_format = '(#,##0.0)'

            # Row 12: Ending Balance = MAX(0, Beg + Paydown)
            ws.cell(row=12, column=1, value="Ending Balance")
            for i in range(n):
                col = y1_col + i
                this = get_column_letter(col)
                ws.cell(row=12, column=col, value=f"=MAX(0,{this}10+{this}11)")
                ws.cell(row=12, column=col).number_format = '#,##0.0'
                ws.cell(row=12, column=col).font = Font(bold=True)

            # Row 14: Interest = avg(beg, end) × rate
            ws.cell(row=14, column=1, value="Interest Expense")
            for i in range(n):
                col = y1_col + i
                this = get_column_letter(col)
                ws.cell(row=14, column=col, value=f"=({this}10+{this}12)/2*$B$6")
                ws.cell(row=14, column=col).number_format = '#,##0.0'

            # Cell map for QUICK mode
            self.cell_map['debt_schedule'] = {
                'mode': 'quick',
                'ending_balance_row': 12,
                'interest_row': 14,
                'total_debt_row': 12,  # same as ending in quick mode
            }

        else:
            # --- STANDARD/COMPREHENSIVE: Multi-tranche with cash sweep ---

            # Senior Debt section
            self._add_section_header(ws, "Senior Secured Debt ($M)", 4, 1)

            # Row 5: Senior Beg Balance — Entry col = EBITDA × Senior mult
            ws.cell(row=5, column=1, value="Beginning Balance")
            ws.cell(row=5, column=entry_col, value=f"='{A}'!B6*'{A}'!B12")
            ws.cell(row=5, column=entry_col).number_format = '#,##0.0'
            for i in range(n):
                col = y1_col + i
                prev = get_column_letter(col - 1)
                if i == 0:
                    ws.cell(row=5, column=col, value=f"=B5")  # Entry initial
                else:
                    ws.cell(row=5, column=col, value=f"={prev}8")  # prior ending
                ws.cell(row=5, column=col).number_format = '#,##0.0'

            # Row 6: Mandatory Amortization = -Initial × amort%
            ws.cell(row=6, column=1, value="Mandatory Amortization")
            for i in range(n):
                col = y1_col + i
                ws.cell(row=6, column=col, value=f"=-$B$5*'{A}'!B14")
                ws.cell(row=6, column=col).number_format = '(#,##0.0)'

            # Row 7: Cash Sweep = -MAX(0, (EBITDA - CapEx - Interest - Amort) × 50%)
            ws.cell(row=7, column=1, value="Cash Sweep")
            for i in range(n):
                col = y1_col + i
                this = get_column_letter(col)
                om_ebitda = f"'{OM}'!{this}13"
                om_capex = f"'{OM}'!{this}16"
                sr_interest = f"{this}10"
                sr_amort = f"{this}6"
                ws.cell(row=7, column=col,
                        value=f"=-MAX(0,({om_ebitda}+{om_capex}-{sr_interest}+{sr_amort})*0.5)")
                ws.cell(row=7, column=col).number_format = '(#,##0.0)'

            # Row 8: Senior Ending Balance = MAX(0, Beg + Amort + Sweep)
            ws.cell(row=8, column=1, value="Ending Balance")
            for i in range(n):
                col = y1_col + i
                this = get_column_letter(col)
                ws.cell(row=8, column=col, value=f"=MAX(0,{this}5+{this}6+{this}7)")
                ws.cell(row=8, column=col).number_format = '#,##0.0'
                ws.cell(row=8, column=col).font = Font(bold=True)

            # Row 9: Senior Interest Rate (input reference)
            ws.cell(row=9, column=1, value="Interest Rate")
            ws.cell(row=9, column=2, value=f"='{A}'!B13")
            ws.cell(row=9, column=2).number_format = '0.0%'
            self._format_input_cell(ws, 9, 2)

            # Row 10: Senior Interest Expense = avg(beg, end) × rate
            ws.cell(row=10, column=1, value="Interest Expense")
            for i in range(n):
                col = y1_col + i
                this = get_column_letter(col)
                ws.cell(row=10, column=col, value=f"=({this}5+{this}8)/2*$B$9")
                ws.cell(row=10, column=col).number_format = '#,##0.0'

            # --- Subordinated Debt section (row 12) ---
            sub_start = 12
            self._add_section_header(ws, "Subordinated Debt ($M)", sub_start, 1)

            # Row 13: Sub Balance = constant = EBITDA × Sub mult
            ws.cell(row=sub_start + 1, column=1, value="Beginning Balance")
            ws.cell(row=sub_start + 1, column=entry_col, value=f"='{A}'!B6*'{A}'!B15")
            ws.cell(row=sub_start + 1, column=entry_col).number_format = '#,##0.0'
            for i in range(n):
                col = y1_col + i
                ws.cell(row=sub_start + 1, column=col, value=f"=$B${sub_start + 1}")
                ws.cell(row=sub_start + 1, column=col).number_format = '#,##0.0'

            # Row 14: Sub Ending = same (no amort)
            ws.cell(row=sub_start + 2, column=1, value="Ending Balance")
            for i in range(n):
                col = y1_col + i
                this = get_column_letter(col)
                ws.cell(row=sub_start + 2, column=col, value=f"={this}{sub_start + 1}")
                ws.cell(row=sub_start + 2, column=col).number_format = '#,##0.0'
                ws.cell(row=sub_start + 2, column=col).font = Font(bold=True)

            # Row 15: Sub Interest Rate
            ws.cell(row=sub_start + 3, column=1, value="Interest Rate")
            ws.cell(row=sub_start + 3, column=2, value=f"='{A}'!B16")
            ws.cell(row=sub_start + 3, column=2).number_format = '0.0%'
            self._format_input_cell(ws, sub_start + 3, 2)

            # Row 16: Sub Interest = Balance × Rate
            ws.cell(row=sub_start + 4, column=1, value="Interest Expense")
            for i in range(n):
                col = y1_col + i
                this = get_column_letter(col)
                ws.cell(row=sub_start + 4, column=col,
                        value=f"={this}{sub_start + 1}*$B${sub_start + 3}")
                ws.cell(row=sub_start + 4, column=col).number_format = '#,##0.0'

            # --- Debt Summary (row 18) ---
            summary_start = sub_start + 6  # row 18
            self._add_section_header(ws, "Debt Summary", summary_start, 1)

            # Row 19: Total Debt = Senior Ending + Sub Ending
            td_row = summary_start + 1
            ws.cell(row=td_row, column=1, value="Total Debt")
            # Entry column: initial senior + sub
            ws.cell(row=td_row, column=entry_col, value=f"=B5+B{sub_start + 1}")
            ws.cell(row=td_row, column=entry_col).number_format = '#,##0.0'
            ws.cell(row=td_row, column=entry_col).font = Font(bold=True)
            for i in range(n):
                col = y1_col + i
                this = get_column_letter(col)
                ws.cell(row=td_row, column=col, value=f"={this}8+{this}{sub_start + 2}")
                ws.cell(row=td_row, column=col).number_format = '#,##0.0'
                ws.cell(row=td_row, column=col).font = Font(bold=True)

            # Row 20: Total Interest = Senior Interest + Sub Interest
            ti_row = summary_start + 2
            ws.cell(row=ti_row, column=1, value="Total Interest")
            for i in range(n):
                col = y1_col + i
                this = get_column_letter(col)
                ws.cell(row=ti_row, column=col, value=f"={this}10+{this}{sub_start + 4}")
                ws.cell(row=ti_row, column=col).number_format = '#,##0.0'

            # Row 22: Debt / EBITDA
            lever_row = summary_start + 4
            ws.cell(row=lever_row, column=1, value="Debt / EBITDA")
            # Entry
            ws.cell(row=lever_row, column=entry_col,
                    value=f"=IFERROR(B{td_row}/'{OM}'!B13,0)")
            ws.cell(row=lever_row, column=entry_col).number_format = '0.0"x"'
            for i in range(n):
                col = y1_col + i
                this = get_column_letter(col)
                ws.cell(row=lever_row, column=col,
                        value=f"=IFERROR({this}{td_row}/'{OM}'!{this}13,0)")
                ws.cell(row=lever_row, column=col).number_format = '0.0"x"'

            # Cell map for STANDARD mode
            self.cell_map['debt_schedule'] = {
                'mode': 'standard',
                'senior_ending_row': 8,
                'sub_ending_row': sub_start + 2,
                'total_debt_row': td_row,
                'total_interest_row': ti_row,
                'leverage_row': lever_row,
            }

        # Set column widths
        ws.column_dimensions['A'].width = 22
        for i in range(n + 2):
            ws.column_dimensions[get_column_letter(2 + i)].width = 12

        return self

    # ============================================================
    # MODULE: WACC CALCULATION
    # ============================================================

    def add_wacc_calculation(self, data: Dict = None) -> 'ExcelModelGenerator':
        """Add WACC Calculation sheet with live Excel formulas."""
        ws = self.wb.create_sheet("WACC")
        self.sheets_created.append("WACC")

        a = self.assumptions

        # Title
        self._add_title(ws, f"{self.company_name} - WACC Calculation", 1, 1)

        if self.depth == ModelDepth.QUICK:
            # Simple: Just show WACC assumption
            self._add_section_header(ws, "WACC Assumption", 3, 1)

            ws.cell(row=4, column=1, value="WACC")
            ws.cell(row=4, column=2, value=0.10)
            ws.cell(row=4, column=2).number_format = '0.0%'
            self._format_input_cell(ws, 4, 2)

            self.cell_map['wacc'] = {'wacc': 'B4'}

        else:
            # Standard/Comprehensive: Full CAPM with live formulas

            # Cost of Equity section
            self._add_section_header(ws, "Cost of Equity (CAPM)", 3, 1)

            # Row 4-7: CAPM inputs (blue font = editable)
            capm_inputs = [
                (4, "Risk-Free Rate (10Y Treasury)", a.risk_free_rate, '0.00%'),
                (5, "Equity Risk Premium", a.equity_risk_premium, '0.00%'),
                (6, "Beta (Levered)", a.beta, '0.00'),
                (7, "Size Premium", a.size_premium, '0.00%'),
            ]
            for row, name, value, fmt in capm_inputs:
                ws.cell(row=row, column=1, value=name)
                ws.cell(row=row, column=2, value=value)
                ws.cell(row=row, column=2).number_format = fmt
                self._format_input_cell(ws, row, 2)

            # Row 9: Cost of Equity = Rf + (Beta × ERP) + Size Premium
            ws.cell(row=9, column=1, value="Cost of Equity")
            ws.cell(row=9, column=2, value="=B4+(B6*B5)+B7")
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

            # Row 14: After-Tax Cost of Debt = Rate × (1 - Tax)
            ws.cell(row=14, column=1, value="After-Tax Cost of Debt")
            ws.cell(row=14, column=2, value="=B12*(1-B13)")
            ws.cell(row=14, column=2).number_format = '0.0%'
            ws.cell(row=14, column=2).font = Font(bold=True)
            ws.cell(row=14, column=2).border = DOUBLE_BORDER

            # Capital Structure
            self._add_section_header(ws, "Capital Structure", 16, 1)

            ws.cell(row=17, column=1, value="Target Debt / Equity")
            ws.cell(row=17, column=2, value=a.target_debt_equity)
            ws.cell(row=17, column=2).number_format = '0.0%'
            self._format_input_cell(ws, 17, 2)

            # Row 18-19: Weights as formulas
            ws.cell(row=18, column=1, value="Debt Weight")
            ws.cell(row=18, column=2, value="=B17/(1+B17)")
            ws.cell(row=18, column=2).number_format = '0.0%'

            ws.cell(row=19, column=1, value="Equity Weight")
            ws.cell(row=19, column=2, value="=1-B18")
            ws.cell(row=19, column=2).number_format = '0.0%'

            # WACC Calculation
            self._add_section_header(ws, "WACC Calculation", 21, 1)

            # Row 22: WACC = (E/V × Re) + (D/V × Rd×(1-T))
            ws.cell(row=22, column=1, value="WACC")
            ws.cell(row=22, column=2, value="=(B19*B9)+(B18*B14)")
            ws.cell(row=22, column=2).number_format = '0.0%'
            ws.cell(row=22, column=2).font = Font(bold=True, size=14)
            ws.cell(row=22, column=2).fill = PatternFill(start_color="90EE90", end_color="90EE90", fill_type="solid")

            # Formula reference
            ws.cell(row=24, column=1, value="Formula: (E/V × Re) + (D/V × Rd × (1-T))")

            self.cell_map['wacc'] = {
                'risk_free_rate': 'B4',
                'erp': 'B5',
                'beta': 'B6',
                'size_premium': 'B7',
                'cost_of_equity': 'B9',
                'cost_of_debt': 'B12',
                'tax_rate': 'B13',
                'after_tax_debt': 'B14',
                'de_ratio': 'B17',
                'debt_weight': 'B18',
                'equity_weight': 'B19',
                'wacc': 'B22',
            }

        # Set column widths
        ws.column_dimensions['A'].width = 30
        ws.column_dimensions['B'].width = 15

        return self

    # ============================================================
    # MODULE: WORKING CAPITAL
    # ============================================================

    def add_working_capital(self, data: Dict = None) -> 'ExcelModelGenerator':
        """Add Working Capital Analysis sheet with real Excel formulas."""
        ws = self.wb.create_sheet("Working Capital")
        self.sheets_created.append("Working Capital")

        A = "Assumptions"
        OM = "Operating Model"
        n = self.projection_years
        ltm_col = 2
        y1_col = 3

        # Title
        self._add_title(ws, f"{self.company_name} - Working Capital Analysis", 1, 1)

        # Year headers
        self._year_headers(ws, 3, 2)

        if self.depth == ModelDepth.QUICK:
            # Simple: NWC as % of revenue, referencing Assumptions + Operating Model
            self._add_section_header(ws, "Working Capital Assumptions", 4, 1)

            # Row 5: NWC % Revenue — reference Assumptions!B23
            ws.cell(row=5, column=1, value="NWC % of Revenue")
            for i in range(n + 1):
                col = ltm_col + i
                ws.cell(row=5, column=col, value=f"='{A}'!B23")
                ws.cell(row=5, column=col).number_format = '0.0%'
                self._format_input_cell(ws, 5, col)

            self._add_section_header(ws, "Working Capital ($M)", 7, 1)

            # Row 8: NWC = Revenue × NWC%
            ws.cell(row=8, column=1, value="Net Working Capital")
            for i in range(n + 1):
                col = ltm_col + i
                this = get_column_letter(col)
                ws.cell(row=8, column=col, value=f"='{OM}'!{this}10*{this}5")
                ws.cell(row=8, column=col).number_format = '#,##0.0'

            # Row 9: Change in NWC
            ws.cell(row=9, column=1, value="Change in NWC")
            ws.cell(row=9, column=ltm_col, value="—")
            for i in range(n):
                col = y1_col + i
                prev = get_column_letter(col - 1)
                this = get_column_letter(col)
                ws.cell(row=9, column=col, value=f"={this}8-{prev}8")
                ws.cell(row=9, column=col).number_format = '#,##0.0'

            self.cell_map['working_capital'] = {
                'nwc_row': 8,
                'change_nwc_row': 9,
            }

        else:
            # Standard/Comprehensive: Days-based calculation with formulas
            data = data or {}
            self._add_section_header(ws, "Working Capital Assumptions (Days)", 4, 1)

            days = data.get('days', {
                'ar_days': 45, 'inventory_days': 60, 'ap_days': 30,
                'other_ca_pct': 0.02, 'other_cl_pct': 0.03,
            })

            # Row 5-7: Input assumptions (still hardcoded input values, not formula refs)
            ws.cell(row=5, column=1, value="Accounts Receivable Days")
            for i in range(n + 1):
                ws.cell(row=5, column=ltm_col + i, value=days['ar_days'])
                self._format_input_cell(ws, 5, ltm_col + i)

            ws.cell(row=6, column=1, value="Inventory Days")
            for i in range(n + 1):
                ws.cell(row=6, column=ltm_col + i, value=days['inventory_days'])
                self._format_input_cell(ws, 6, ltm_col + i)

            ws.cell(row=7, column=1, value="Accounts Payable Days")
            for i in range(n + 1):
                ws.cell(row=7, column=ltm_col + i, value=days['ap_days'])
                self._format_input_cell(ws, 7, ltm_col + i)

            # Current Assets (formulas referencing Operating Model revenue)
            self._add_section_header(ws, "Current Assets ($M)", 9, 1)

            # Row 10: AR = Revenue × AR Days / 365
            ws.cell(row=10, column=1, value="Accounts Receivable")
            for i in range(n + 1):
                col = ltm_col + i
                this = get_column_letter(col)
                ws.cell(row=10, column=col, value=f"='{OM}'!{this}10*{this}5/365")
                ws.cell(row=10, column=col).number_format = '#,##0.0'

            # Row 11: Inventory = Revenue × 0.60 × Inv Days / 365
            ws.cell(row=11, column=1, value="Inventory")
            for i in range(n + 1):
                col = ltm_col + i
                this = get_column_letter(col)
                ws.cell(row=11, column=col, value=f"='{OM}'!{this}10*0.6*{this}6/365")
                ws.cell(row=11, column=col).number_format = '#,##0.0'

            # Row 12: Other CA = Revenue × other_ca_pct
            ws.cell(row=12, column=1, value="Other Current Assets")
            for i in range(n + 1):
                col = ltm_col + i
                this = get_column_letter(col)
                ws.cell(row=12, column=col, value=f"='{OM}'!{this}10*{days['other_ca_pct']}")
                ws.cell(row=12, column=col).number_format = '#,##0.0'

            # Row 13: Total CA
            ws.cell(row=13, column=1, value="Total Current Assets")
            for i in range(n + 1):
                col = ltm_col + i
                this = get_column_letter(col)
                ws.cell(row=13, column=col, value=f"=SUM({this}10:{this}12)")
                ws.cell(row=13, column=col).number_format = '#,##0.0'
                ws.cell(row=13, column=col).font = Font(bold=True)

            # Current Liabilities
            self._add_section_header(ws, "Current Liabilities ($M)", 15, 1)

            # Row 16: AP = Revenue × 0.60 × AP Days / 365
            ws.cell(row=16, column=1, value="Accounts Payable")
            for i in range(n + 1):
                col = ltm_col + i
                this = get_column_letter(col)
                ws.cell(row=16, column=col, value=f"='{OM}'!{this}10*0.6*{this}7/365")
                ws.cell(row=16, column=col).number_format = '#,##0.0'

            # Row 17: Other CL = Revenue × other_cl_pct
            ws.cell(row=17, column=1, value="Other Current Liabilities")
            for i in range(n + 1):
                col = ltm_col + i
                this = get_column_letter(col)
                ws.cell(row=17, column=col, value=f"='{OM}'!{this}10*{days['other_cl_pct']}")
                ws.cell(row=17, column=col).number_format = '#,##0.0'

            # Row 18: Total CL
            ws.cell(row=18, column=1, value="Total Current Liabilities")
            for i in range(n + 1):
                col = ltm_col + i
                this = get_column_letter(col)
                ws.cell(row=18, column=col, value=f"=SUM({this}16:{this}17)")
                ws.cell(row=18, column=col).number_format = '#,##0.0'
                ws.cell(row=18, column=col).font = Font(bold=True)

            # Net Working Capital
            self._add_section_header(ws, "Net Working Capital ($M)", 20, 1)

            # Row 21: NWC = Total CA - Total CL
            ws.cell(row=21, column=1, value="Net Working Capital")
            for i in range(n + 1):
                col = ltm_col + i
                this = get_column_letter(col)
                ws.cell(row=21, column=col, value=f"={this}13-{this}18")
                ws.cell(row=21, column=col).number_format = '#,##0.0'
                ws.cell(row=21, column=col).font = Font(bold=True)

            # Row 22: NWC % Revenue
            ws.cell(row=22, column=1, value="NWC % of Revenue")
            for i in range(n + 1):
                col = ltm_col + i
                this = get_column_letter(col)
                ws.cell(row=22, column=col, value=f"={this}21/'{OM}'!{this}10")
                ws.cell(row=22, column=col).number_format = '0.0%'

            # Row 23: Change in NWC
            ws.cell(row=23, column=1, value="Change in NWC")
            ws.cell(row=23, column=ltm_col, value="—")
            for i in range(n):
                col = y1_col + i
                prev = get_column_letter(col - 1)
                this = get_column_letter(col)
                ws.cell(row=23, column=col, value=f"={this}21-{prev}21")
                ws.cell(row=23, column=col).number_format = '#,##0.0'

            # Cash Conversion Cycle (formulas referencing local day inputs)
            self._add_section_header(ws, "Cash Conversion Cycle", 25, 1)

            ws.cell(row=26, column=1, value="DSO (Days Sales Outstanding)")
            ws.cell(row=26, column=2, value="=B5")

            ws.cell(row=27, column=1, value="DIO (Days Inventory Outstanding)")
            ws.cell(row=27, column=2, value="=B6")

            ws.cell(row=28, column=1, value="DPO (Days Payable Outstanding)")
            ws.cell(row=28, column=2, value="=B7")

            ws.cell(row=29, column=1, value="Cash Conversion Cycle")
            ws.cell(row=29, column=2, value="=B26+B27-B28")
            ws.cell(row=29, column=2).font = Font(bold=True)

            self.cell_map['working_capital'] = {
                'nwc_row': 21,
                'change_nwc_row': 23,
            }

        # Set column widths
        ws.column_dimensions['A'].width = 28
        for i in range(n + 2):
            ws.column_dimensions[get_column_letter(2 + i)].width = 12

        return self

    # ============================================================
    # MODULE: RETURNS ANALYSIS
    # ============================================================

    def add_returns_analysis(self, data: Dict = None) -> 'ExcelModelGenerator':
        """Add Returns Analysis sheet with real Excel formulas referencing other sheets."""
        ws = self.wb.create_sheet("Returns Analysis")
        self.sheets_created.append("Returns Analysis")

        A = "Assumptions"
        SU = "Sources & Uses"
        OM = "Operating Model"
        DS = "Debt Schedule"
        n = self.projection_years

        # Determine debt schedule total debt row based on mode
        ds_info = self.cell_map.get('debt_schedule', {})
        ds_mode = ds_info.get('mode', 'quick')
        td_row = ds_info.get('total_debt_row', 12)

        # Title
        self._add_title(ws, f"{self.company_name} - Returns Analysis", 1, 1)

        # --- Entry Assumptions (rows 3-8) — formulas referencing S&U ---
        self._add_section_header(ws, "Entry Assumptions", 3, 1)

        ws.cell(row=4, column=1, value="LTM EBITDA ($M)")
        ws.cell(row=4, column=2, value=f"='{A}'!B6")
        ws.cell(row=4, column=2).number_format = '#,##0.0'

        ws.cell(row=5, column=1, value="Entry Multiple")
        ws.cell(row=5, column=2, value=f"='{A}'!B7")
        ws.cell(row=5, column=2).number_format = '0.0"x"'

        ws.cell(row=6, column=1, value="Enterprise Value ($M)")
        ws.cell(row=6, column=2, value=f"='{SU}'!B10")
        ws.cell(row=6, column=2).number_format = '#,##0.0'

        ws.cell(row=7, column=1, value="Total Debt ($M)")
        ws.cell(row=7, column=2, value=f"='{SU}'!B4+'{SU}'!B5")
        ws.cell(row=7, column=2).number_format = '#,##0.0'

        ws.cell(row=8, column=1, value="Equity Investment ($M)")
        ws.cell(row=8, column=2, value=f"='{SU}'!B6")
        ws.cell(row=8, column=2).number_format = '#,##0.0'

        # --- Exit Assumptions (rows 10-12) ---
        self._add_section_header(ws, "Exit Assumptions", 10, 1)

        ws.cell(row=11, column=1, value="Exit Multiple")
        ws.cell(row=11, column=2, value=f"='{A}'!B8")
        ws.cell(row=11, column=2).number_format = '0.0"x"'
        self._format_input_cell(ws, 11, 2)

        ws.cell(row=12, column=1, value="Hold Period (Years)")
        ws.cell(row=12, column=2, value=f"='{A}'!B9")
        self._format_input_cell(ws, 12, 2)

        # --- Returns by Exit Year (rows 14+) ---
        self._add_section_header(ws, "Returns by Exit Year", 14, 1)

        headers = ["Exit Year", "EBITDA", "Exit EV", "Net Debt", "Equity Value", "MOIC", "IRR"]
        for i, header in enumerate(headers):
            ws.cell(row=15, column=1 + i, value=header)
        self._format_header_row(ws, 15, 1, len(headers))

        for year in range(3, n + 1):
            row = 16 + (year - 3)
            # Column in Operating Model / Debt Schedule for this year
            # Year 3 = column E (col 5), Year 4 = F, Year 5 = G
            yr_col = get_column_letter(2 + year)  # B=LTM, C=Y1, D=Y2, E=Y3...

            ws.cell(row=row, column=1, value=f"Year {year}")

            # Col B: Exit EBITDA from Operating Model
            ws.cell(row=row, column=2, value=f"='{OM}'!{yr_col}13")
            ws.cell(row=row, column=2).number_format = '#,##0.0'

            # Col C: Exit EV = Exit EBITDA × Exit Multiple
            ws.cell(row=row, column=3, value=f"=B{row}*$B$11")
            ws.cell(row=row, column=3).number_format = '#,##0.0'

            # Col D: Net Debt at exit from Debt Schedule
            ws.cell(row=row, column=4, value=f"='{DS}'!{yr_col}{td_row}")
            ws.cell(row=row, column=4).number_format = '#,##0.0'

            # Col E: Equity Value = Exit EV - Net Debt
            ws.cell(row=row, column=5, value=f"=C{row}-D{row}")
            ws.cell(row=row, column=5).number_format = '#,##0.0'

            # Col F: MOIC = Equity Value / Entry Equity
            ws.cell(row=row, column=6, value=f"=IFERROR(E{row}/$B$8,0)")
            ws.cell(row=row, column=6).number_format = '0.00"x"'

            # Col G: IRR = (MOIC^(1/year)) - 1
            ws.cell(row=row, column=7, value=f"=IFERROR((F{row}^(1/{year}))-1,0)")
            ws.cell(row=row, column=7).number_format = '0.0%'

        # Highlight base case (Year 5)
        if n >= 5:
            base_row = 16 + (5 - 3)
            for col in range(1, 8):
                ws.cell(row=base_row, column=col).fill = PatternFill(
                    start_color="90EE90", end_color="90EE90", fill_type="solid")

        # --- Value Creation Bridge (Standard/Comprehensive only) ---
        if self.depth != ModelDepth.QUICK:
            bridge_start = 16 + (n - 2) + 2
            self._add_section_header(ws, "Value Creation Bridge (Base Case)", bridge_start, 1)

            # Use last exit year row for base case references
            base_data_row = 16 + (n - 3)  # row for Year n (the last one)
            exit_yr_col = get_column_letter(2 + n)  # column for exit year in OM/DS

            br = bridge_start + 1
            # Entry Equity
            ws.cell(row=br, column=1, value="Entry Equity")
            ws.cell(row=br, column=2, value="=$B$8")
            ws.cell(row=br, column=2).number_format = '#,##0.0'

            # EBITDA Growth value = (Exit EBITDA - LTM EBITDA) × Exit Multiple
            ws.cell(row=br + 1, column=1, value="(+) EBITDA Growth")
            ws.cell(row=br + 1, column=2,
                    value=f"=('{OM}'!{exit_yr_col}13-'{A}'!B6)*$B$11")
            ws.cell(row=br + 1, column=2).number_format = '#,##0.0'

            # Multiple Expansion = Exit EBITDA × (Exit Mult - Entry Mult)
            ws.cell(row=br + 2, column=1, value="(+) Multiple Expansion")
            ws.cell(row=br + 2, column=2,
                    value=f"='{OM}'!{exit_yr_col}13*('{A}'!B8-'{A}'!B7)")
            ws.cell(row=br + 2, column=2).number_format = '#,##0.0'

            # Debt Paydown = Entry Debt - Exit Debt
            ws.cell(row=br + 3, column=1, value="(+) Debt Paydown")
            ws.cell(row=br + 3, column=2,
                    value=f"=$B$7-'{DS}'!{exit_yr_col}{td_row}")
            ws.cell(row=br + 3, column=2).number_format = '#,##0.0'

            # Exit Equity = sum of bridge
            ws.cell(row=br + 4, column=1, value="(=) Exit Equity")
            ws.cell(row=br + 4, column=2,
                    value=f"=SUM(B{br}:B{br + 3})")
            ws.cell(row=br + 4, column=2).number_format = '#,##0.0'
            ws.cell(row=br + 4, column=1).font = Font(bold=True)
            ws.cell(row=br + 4, column=2).font = Font(bold=True)
            ws.cell(row=br + 4, column=2).border = DOUBLE_BORDER

        # Set column widths
        ws.column_dimensions['A'].width = 22
        for i in range(7):
            ws.column_dimensions[get_column_letter(2 + i)].width = 12

        return self

    # ============================================================
    # MODULE: SENSITIVITY TABLES
    # ============================================================

    def add_sensitivity_tables(self, data: Dict = None) -> 'ExcelModelGenerator':
        """Add Sensitivity Analysis sheet with formula grids referencing other sheets."""
        ws = self.wb.create_sheet("Sensitivity")
        self.sheets_created.append("Sensitivity")

        A = "Assumptions"
        OM = "Operating Model"
        DS = "Debt Schedule"
        n = self.projection_years

        # Exit year column in Operating Model (Year n)
        exit_col = get_column_letter(2 + n)  # e.g. G for year 5

        # Debt schedule total debt row
        ds_info = self.cell_map.get('debt_schedule', {})
        td_row = ds_info.get('total_debt_row', 12)

        # We store reference cells in hidden rows for the formula grid
        # Row 2: helper cells
        # H2 = Exit EBITDA, H3 = Total Debt at exit, H4 = Fees, H5 = Hold period
        ws.cell(row=2, column=8, value=f"='{OM}'!{exit_col}13")    # Exit EBITDA
        ws.cell(row=2, column=9, value=f"='{DS}'!{exit_col}{td_row}")  # Debt at exit
        ws.cell(row=2, column=10, value=f"='{A}'!B6*('{A}'!B12+'{A}'!B15)")  # Total entry debt
        ws.cell(row=2, column=11, value=f"='{A}'!B9")  # Hold period
        ws.cell(row=2, column=12, value=f"='{A}'!B19")  # Txn fee %
        ws.cell(row=2, column=13, value=f"='{A}'!B20")  # Fin fee %
        ws.cell(row=2, column=14, value=f"='{A}'!B6")   # LTM EBITDA
        # Labels for reference
        for c, label in [(8, "Exit EBITDA"), (9, "Debt@Exit"), (10, "Entry Debt"),
                         (11, "Hold Yrs"), (12, "Txn%"), (13, "Fin%"), (14, "LTM EBITDA")]:
            ws.cell(row=1, column=c, value=label)
            ws.cell(row=1, column=c).font = Font(color="999999", size=8)

        entry_multiples = [7.0, 7.5, 8.0, 8.5, 9.0]
        exit_multiples = [7.0, 7.5, 8.0, 8.5, 9.0]

        # Title
        self._add_title(ws, f"{self.company_name} - Sensitivity Analysis", 3, 1)

        # --- IRR Matrix (rows 5-10) ---
        self._add_section_header(ws, "IRR Sensitivity: Entry Multiple vs Exit Multiple", 5, 1)

        ws.cell(row=6, column=1, value="Entry \\ Exit")
        for i, em in enumerate(exit_multiples):
            ws.cell(row=6, column=2 + i, value=em)
            ws.cell(row=6, column=2 + i).number_format = '0.0"x"'
        self._format_header_row(ws, 6, 1, 1 + len(exit_multiples))

        for j, entry_mult in enumerate(entry_multiples):
            row = 7 + j
            ws.cell(row=row, column=1, value=entry_mult)
            ws.cell(row=row, column=1).number_format = '0.0"x"'
            ws.cell(row=row, column=1).font = HEADER_FONT
            ws.cell(row=row, column=1).fill = HEADER_FILL

            for i, exit_mult in enumerate(exit_multiples):
                # MOIC = (exit_ebitda * exit_mult - debt_at_exit) /
                #        (entry_mult * ltm_ebitda + fees - entry_debt)
                # fees = entry_mult*ltm_ebitda*txn_fee_pct + entry_debt*fin_fee_pct
                # IRR = (MOIC^(1/hold))-1
                exit_mult_ref = f"${get_column_letter(2 + i)}$6"  # exit mult from header
                entry_mult_ref = f"$A${row}"  # entry mult from row header
                # Build MOIC formula inline
                moic_f = (
                    f"(($H$2*{exit_mult_ref}-$I$2)"
                    f"/({entry_mult_ref}*$N$2"
                    f"+{entry_mult_ref}*$N$2*$L$2+$J$2*$M$2"
                    f"-$J$2))"
                )
                irr_f = f"=IFERROR(({moic_f}^(1/$K$2))-1,0)"

                cell = ws.cell(row=row, column=2 + i, value=irr_f)
                cell.number_format = '0.0%'

        # --- MOIC Matrix ---
        moic_start = 7 + len(entry_multiples) + 2  # row 14
        self._add_section_header(ws, "MOIC Sensitivity: Entry Multiple vs Exit Multiple", moic_start, 1)

        ws.cell(row=moic_start + 1, column=1, value="Entry \\ Exit")
        for i, em in enumerate(exit_multiples):
            ws.cell(row=moic_start + 1, column=2 + i, value=em)
            ws.cell(row=moic_start + 1, column=2 + i).number_format = '0.0"x"'
        self._format_header_row(ws, moic_start + 1, 1, 1 + len(exit_multiples))

        for j, entry_mult in enumerate(entry_multiples):
            row = moic_start + 2 + j
            ws.cell(row=row, column=1, value=entry_mult)
            ws.cell(row=row, column=1).number_format = '0.0"x"'
            ws.cell(row=row, column=1).font = HEADER_FONT
            ws.cell(row=row, column=1).fill = HEADER_FILL

            for i, exit_mult in enumerate(exit_multiples):
                exit_mult_ref = f"${get_column_letter(2 + i)}${moic_start + 1}"
                entry_mult_ref = f"$A${row}"
                moic_f = (
                    f"=IFERROR(($H$2*{exit_mult_ref}-$I$2)"
                    f"/({entry_mult_ref}*$N$2"
                    f"+{entry_mult_ref}*$N$2*$L$2+$J$2*$M$2"
                    f"-$J$2),0)"
                )

                cell = ws.cell(row=row, column=2 + i, value=moic_f)
                cell.number_format = '0.00"x"'

        # Legend
        legend_start = moic_start + 2 + len(entry_multiples) + 2
        ws.cell(row=legend_start, column=1, value="Legend:")
        ws.cell(row=legend_start + 1, column=1, value="Note: Values update automatically when Assumptions change")
        ws.cell(row=legend_start + 1, column=1).font = Font(italic=True, color="666666")

        # Set column widths
        ws.column_dimensions['A'].width = 15
        for i in range(6):
            ws.column_dimensions[get_column_letter(2 + i)].width = 10

        return self

    # ============================================================
    # MODULE: SCENARIO ANALYSIS (Bull/Bear/Base)
    # ============================================================

    def add_scenario_analysis(self, data: Dict = None) -> 'ExcelModelGenerator':
        """Add Bull/Bear/Base scenario comparison sheet with live formulas."""
        ws = self.wb.create_sheet("Scenario Analysis")
        self.sheets_created.append("Scenario Analysis")

        A = "Assumptions"
        a = self.assumptions
        data = data or {}
        n = self.projection_years

        # Define scenarios (input assumptions — written as editable values)
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

        # Title
        self._add_title(ws, f"{self.company_name} - Scenario Analysis", 1, 1)

        # ── SECTION 1: Scenario Input Assumptions (values, user-editable) ──
        self._add_section_header(ws, "Scenario Assumptions", 3, 1)

        headers = ["Assumption", "Bear Case", "Base Case", "Bull Case"]
        for i, h in enumerate(headers):
            ws.cell(row=4, column=1 + i, value=h)
        self._format_header_row(ws, 4, 1, 4)

        # Row 5: Revenue Growth (Y1)
        ws.cell(row=5, column=1, value="Revenue Growth (Y1)")
        ws.cell(row=5, column=2, value=scenarios['bear']['revenue_growth'][0])
        ws.cell(row=5, column=3, value=scenarios['base']['revenue_growth'][0])
        ws.cell(row=5, column=4, value=scenarios['bull']['revenue_growth'][0])
        for col in range(2, 5):
            ws.cell(row=5, column=col).number_format = '0.0%'
            self._format_input_cell(ws, 5, col)

        # Row 6: Exit EBITDA Margin
        ws.cell(row=6, column=1, value="Exit EBITDA Margin")
        ws.cell(row=6, column=2, value=scenarios['bear']['ebitda_margin'][-1])
        ws.cell(row=6, column=3, value=scenarios['base']['ebitda_margin'][-1])
        ws.cell(row=6, column=4, value=scenarios['bull']['ebitda_margin'][-1])
        for col in range(2, 5):
            ws.cell(row=6, column=col).number_format = '0.0%'
            self._format_input_cell(ws, 6, col)

        # Row 7: Exit Multiple
        ws.cell(row=7, column=1, value="Exit Multiple")
        ws.cell(row=7, column=2, value=scenarios['bear']['exit_multiple'])
        ws.cell(row=7, column=3, value=scenarios['base']['exit_multiple'])
        ws.cell(row=7, column=4, value=scenarios['bull']['exit_multiple'])
        for col in range(2, 5):
            ws.cell(row=7, column=col).number_format = '0.0x'
            self._format_input_cell(ws, 7, col)

        # Row 8: Probability Weight
        ws.cell(row=8, column=1, value="Probability Weight")
        ws.cell(row=8, column=2, value=scenarios['bear']['probability'])
        ws.cell(row=8, column=3, value=scenarios['base']['probability'])
        ws.cell(row=8, column=4, value=scenarios['bull']['probability'])
        for col in range(2, 5):
            ws.cell(row=8, column=col).number_format = '0%'
            self._format_input_cell(ws, 8, col)

        # ── SECTION 2: Shared entry-level assumptions (formulas from Assumptions) ──
        # Row 9: blank separator
        self._add_section_header(ws, "Entry Assumptions (from Assumptions sheet)", 9, 1)

        # B10: LTM Revenue, B11: LTM EBITDA, B12: Entry Multiple
        # B13: Total Debt, B14: Fees (4% of EV), B15: Equity Check
        ws.cell(row=10, column=1, value="LTM Revenue ($M)")
        ws.cell(row=10, column=2, value=f"='{A}'!B5")
        ws.cell(row=10, column=2).number_format = '#,##0.0'

        ws.cell(row=11, column=1, value="LTM EBITDA ($M)")
        ws.cell(row=11, column=2, value=f"='{A}'!B6")
        ws.cell(row=11, column=2).number_format = '#,##0.0'

        ws.cell(row=12, column=1, value="Entry Multiple")
        ws.cell(row=12, column=2, value=f"='{A}'!B7")
        ws.cell(row=12, column=2).number_format = '0.0"x"'

        ws.cell(row=13, column=1, value="Total Debt ($M)")
        ws.cell(row=13, column=2, value=f"=B11*('{A}'!B12+'{A}'!B15)")
        ws.cell(row=13, column=2).number_format = '#,##0.0'

        ws.cell(row=14, column=1, value="Fees ($M, 4% EV)")
        ws.cell(row=14, column=2, value="=B11*B12*0.04")
        ws.cell(row=14, column=2).number_format = '#,##0.0'

        ws.cell(row=15, column=1, value="Equity Check ($M)")
        ws.cell(row=15, column=2, value="=B11*B12+B14-B13")
        ws.cell(row=15, column=2).number_format = '#,##0.0'
        ws.cell(row=15, column=2).font = Font(bold=True)

        ws.cell(row=16, column=1, value="Hold Period (yrs)")
        ws.cell(row=16, column=2, value=f"='{A}'!B9")

        # ── SECTION 3: Scenario Outputs (ALL formulas) ──
        self._add_section_header(ws, "Scenario Outputs ($M)", 18, 1)

        output_headers = ["Metric", "Bear Case", "Base Case", "Bull Case"]
        for i, h in enumerate(output_headers):
            ws.cell(row=19, column=1 + i, value=h)
        self._format_header_row(ws, 19, 1, 4)

        # Row 20: Exit Revenue = LTM_Rev * (1+growth)^hold_period (simplified)
        ws.cell(row=20, column=1, value="Exit Revenue")
        for col_idx in range(2, 5):
            c = get_column_letter(col_idx)
            ws.cell(row=20, column=col_idx,
                    value=f"=$B$10*(1+{c}5)^$B$16")
            ws.cell(row=20, column=col_idx).number_format = '#,##0.0'

        # Row 21: Exit EBITDA = Exit Revenue × Exit EBITDA Margin
        ws.cell(row=21, column=1, value="Exit EBITDA")
        for col_idx in range(2, 5):
            c = get_column_letter(col_idx)
            ws.cell(row=21, column=col_idx,
                    value=f"={c}20*{c}6")
            ws.cell(row=21, column=col_idx).number_format = '#,##0.0'

        # Row 22: Exit EV = Exit EBITDA × Exit Multiple
        ws.cell(row=22, column=1, value="Exit EV")
        for col_idx in range(2, 5):
            c = get_column_letter(col_idx)
            ws.cell(row=22, column=col_idx,
                    value=f"={c}21*{c}7")
            ws.cell(row=22, column=col_idx).number_format = '#,##0.0'

        # Row 23: Exit Equity = Exit EV - Debt at Exit (50% paydown simplified)
        ws.cell(row=23, column=1, value="Exit Equity Value")
        for col_idx in range(2, 5):
            c = get_column_letter(col_idx)
            ws.cell(row=23, column=col_idx,
                    value=f"={c}22-$B$13*0.5")
            ws.cell(row=23, column=col_idx).number_format = '#,##0.0'

        # Row 24: MOIC = Exit Equity / Equity Check
        ws.cell(row=24, column=1, value="MOIC")
        for col_idx in range(2, 5):
            c = get_column_letter(col_idx)
            ws.cell(row=24, column=col_idx,
                    value=f"=IFERROR({c}23/$B$15,0)")
            ws.cell(row=24, column=col_idx).number_format = '0.00"x"'
            ws.cell(row=24, column=col_idx).font = Font(bold=True)

        # Row 25: IRR = MOIC^(1/hold) - 1
        ws.cell(row=25, column=1, value="IRR")
        for col_idx in range(2, 5):
            c = get_column_letter(col_idx)
            ws.cell(row=25, column=col_idx,
                    value=f"=IFERROR({c}24^(1/$B$16)-1,0)")
            ws.cell(row=25, column=col_idx).number_format = '0.0%'
            ws.cell(row=25, column=col_idx).font = Font(bold=True)

        # ── SECTION 4: Probability-Weighted Returns (formulas) ──
        self._add_section_header(ws, "Probability-Weighted Returns", 27, 1)

        # Row 28: Expected MOIC = SUMPRODUCT(MOIC row, Probability row)
        ws.cell(row=28, column=1, value="Expected MOIC")
        ws.cell(row=28, column=2, value="=SUMPRODUCT(B24:D24,B8:D8)")
        ws.cell(row=28, column=2).number_format = '0.00"x"'
        ws.cell(row=28, column=2).font = Font(bold=True, size=14)
        ws.cell(row=28, column=2).fill = PatternFill(start_color="90EE90", end_color="90EE90", fill_type="solid")

        # Row 29: Expected IRR = SUMPRODUCT(IRR row, Probability row)
        ws.cell(row=29, column=1, value="Expected IRR")
        ws.cell(row=29, column=2, value="=SUMPRODUCT(B25:D25,B8:D8)")
        ws.cell(row=29, column=2).number_format = '0.0%'
        ws.cell(row=29, column=2).font = Font(bold=True, size=14)
        ws.cell(row=29, column=2).fill = PatternFill(start_color="90EE90", end_color="90EE90", fill_type="solid")

        # ── SECTION 5: Downside Protection (formulas) ──
        self._add_section_header(ws, "Downside Protection", 31, 1)

        ws.cell(row=32, column=1, value="Bear Case MOIC")
        ws.cell(row=32, column=2, value="=B24")
        ws.cell(row=32, column=2).number_format = '0.00"x"'

        ws.cell(row=33, column=1, value="Capital Protected?")
        ws.cell(row=33, column=2, value='=IF(B32>=1,"Yes","No")')

        # Note about live formulas
        ws.cell(row=35, column=1, value="Note: All outputs update automatically when scenario assumptions change")
        ws.cell(row=35, column=1).font = Font(italic=True, color="666666")

        self.cell_map['scenario_analysis'] = {
            'rev_growth_row': 5,
            'ebitda_margin_row': 6,
            'exit_multiple_row': 7,
            'probability_row': 8,
            'moic_row': 24,
            'irr_row': 25,
            'expected_moic_cell': 'B28',
            'expected_irr_cell': 'B29',
        }

        # Set column widths
        ws.column_dimensions['A'].width = 28
        for col in ['B', 'C', 'D']:
            ws.column_dimensions[col].width = 14

        return self

    # ============================================================
    # MODULE: MANAGEMENT VS BUYER CASE
    # ============================================================

    def add_management_vs_buyer(self, data: Dict = None) -> 'ExcelModelGenerator':
        """Add Management Case vs Buyer Case comparison with live Excel formulas."""
        ws = self.wb.create_sheet("Mgmt vs Buyer Case")
        self.sheets_created.append("Mgmt vs Buyer Case")

        a = self.assumptions
        data = data or {}
        n = self.projection_years

        # Define case assumptions (inputs)
        mgmt_case = data.get('management', {
            'revenue_growth': [0.12, 0.10, 0.09, 0.08, 0.07],
            'ebitda_margin': [0.22, 0.24, 0.25, 0.26, 0.27],
        })
        buyer_case = data.get('buyer', {
            'revenue_growth': [0.08, 0.07, 0.06, 0.05, 0.05],
            'ebitda_margin': [0.20, 0.21, 0.22, 0.22, 0.22],
        })

        # Title
        self._add_title(ws, f"{self.company_name} - Management vs Buyer Case", 1, 1)

        # Year headers (row 3)
        ws.cell(row=3, column=1, value="")
        ws.cell(row=3, column=2, value="LTM")
        for i in range(n):
            ws.cell(row=3, column=3 + i, value=f"Year {i + 1}")
        self._format_header_row(ws, 3, 1, 2 + n)

        # ── MANAGEMENT CASE (rows 4-8) ──
        self._add_section_header(ws, "MANAGEMENT CASE", 4, 1)

        # Row 5: Revenue — LTM from Assumptions, projections as formulas
        ws.cell(row=5, column=1, value="Revenue")
        ws.cell(row=5, column=2, value=f"='Assumptions'!B5")
        ws.cell(row=5, column=2).number_format = '#,##0.0'
        for i in range(n):
            col = get_column_letter(3 + i)
            prev = get_column_letter(2 + i)
            ws.cell(row=5, column=3 + i, value=f"={prev}5*(1+{col}6)")
            ws.cell(row=5, column=3 + i).number_format = '#,##0.0'

        # Row 6: Growth % (inputs)
        ws.cell(row=6, column=1, value="  % Growth")
        ws.cell(row=6, column=2, value="—")
        for i in range(n):
            g = mgmt_case['revenue_growth'][i] if i < len(mgmt_case['revenue_growth']) else 0.05
            ws.cell(row=6, column=3 + i, value=g)
            ws.cell(row=6, column=3 + i).number_format = '0.0%'
            self._format_input_cell(ws, 6, 3 + i)

        # Row 7: EBITDA = Revenue × Margin
        ws.cell(row=7, column=1, value="EBITDA")
        ws.cell(row=7, column=2, value=f"='Assumptions'!B6")
        ws.cell(row=7, column=2).number_format = '#,##0.0'
        ws.cell(row=7, column=2).font = Font(bold=True)
        for i in range(n):
            col = get_column_letter(3 + i)
            ws.cell(row=7, column=3 + i, value=f"={col}5*{col}8")
            ws.cell(row=7, column=3 + i).number_format = '#,##0.0'
            ws.cell(row=7, column=3 + i).font = Font(bold=True)

        # Row 8: Margin % (inputs)
        ws.cell(row=8, column=1, value="  % Margin")
        ws.cell(row=8, column=2, value="=B7/B5")
        ws.cell(row=8, column=2).number_format = '0.0%'
        for i in range(n):
            m = mgmt_case['ebitda_margin'][i] if i < len(mgmt_case['ebitda_margin']) else 0.22
            ws.cell(row=8, column=3 + i, value=m)
            ws.cell(row=8, column=3 + i).number_format = '0.0%'
            self._format_input_cell(ws, 8, 3 + i)

        # ── BUYER CASE (rows 10-14) ──
        self._add_section_header(ws, "BUYER CASE (HAIRCUT)", 10, 1)

        # Row 11: Revenue
        ws.cell(row=11, column=1, value="Revenue")
        ws.cell(row=11, column=2, value="=B5")  # Same LTM
        ws.cell(row=11, column=2).number_format = '#,##0.0'
        for i in range(n):
            col = get_column_letter(3 + i)
            prev = get_column_letter(2 + i)
            ws.cell(row=11, column=3 + i, value=f"={prev}11*(1+{col}12)")
            ws.cell(row=11, column=3 + i).number_format = '#,##0.0'

        # Row 12: Growth % (inputs)
        ws.cell(row=12, column=1, value="  % Growth")
        ws.cell(row=12, column=2, value="—")
        for i in range(n):
            g = buyer_case['revenue_growth'][i] if i < len(buyer_case['revenue_growth']) else 0.05
            ws.cell(row=12, column=3 + i, value=g)
            ws.cell(row=12, column=3 + i).number_format = '0.0%'
            self._format_input_cell(ws, 12, 3 + i)

        # Row 13: EBITDA = Revenue × Margin
        ws.cell(row=13, column=1, value="EBITDA")
        ws.cell(row=13, column=2, value="=B11*B14")
        ws.cell(row=13, column=2).number_format = '#,##0.0'
        ws.cell(row=13, column=2).font = Font(bold=True)
        for i in range(n):
            col = get_column_letter(3 + i)
            ws.cell(row=13, column=3 + i, value=f"={col}11*{col}14")
            ws.cell(row=13, column=3 + i).number_format = '#,##0.0'
            ws.cell(row=13, column=3 + i).font = Font(bold=True)

        # Row 14: Margin % (inputs)
        ws.cell(row=14, column=1, value="  % Margin")
        ws.cell(row=14, column=2, value="=B7/B5")
        ws.cell(row=14, column=2).number_format = '0.0%'
        for i in range(n):
            m = buyer_case['ebitda_margin'][i] if i < len(buyer_case['ebitda_margin']) else 0.20
            ws.cell(row=14, column=3 + i, value=m)
            ws.cell(row=14, column=3 + i).number_format = '0.0%'
            self._format_input_cell(ws, 14, 3 + i)

        # ── VARIANCE ANALYSIS (rows 16-21) ──
        self._add_section_header(ws, "VARIANCE ANALYSIS", 16, 1)

        # Row 17: Revenue Variance = Buyer - Mgmt
        ws.cell(row=17, column=1, value="Revenue Variance")
        for i in range(n + 1):
            col = get_column_letter(2 + i)
            ws.cell(row=17, column=2 + i, value=f"={col}11-{col}5")
            ws.cell(row=17, column=2 + i).number_format = '#,##0.0'

        # Row 18: % Variance
        ws.cell(row=18, column=1, value="  % Variance")
        for i in range(n + 1):
            col = get_column_letter(2 + i)
            ws.cell(row=18, column=2 + i, value=f"=IFERROR({col}17/{col}5,0)")
            ws.cell(row=18, column=2 + i).number_format = '0.0%'

        # Row 20: EBITDA Variance
        ws.cell(row=20, column=1, value="EBITDA Variance")
        for i in range(n + 1):
            col = get_column_letter(2 + i)
            ws.cell(row=20, column=2 + i, value=f"={col}13-{col}7")
            ws.cell(row=20, column=2 + i).number_format = '#,##0.0'

        # Row 21: % Variance
        ws.cell(row=21, column=1, value="  % Variance")
        for i in range(n + 1):
            col = get_column_letter(2 + i)
            ws.cell(row=21, column=2 + i, value=f"=IFERROR({col}20/{col}7,0)")
            ws.cell(row=21, column=2 + i).number_format = '0.0%'

        # ── RETURNS COMPARISON (rows 23-28) ──
        self._add_section_header(ws, "RETURNS COMPARISON", 23, 1)

        ws.cell(row=24, column=1, value="")
        ws.cell(row=24, column=2, value="Management")
        ws.cell(row=24, column=3, value="Buyer")
        ws.cell(row=24, column=4, value="Difference")
        self._format_header_row(ws, 24, 1, 4)

        # Exit year column (last projection year)
        exit_col = get_column_letter(2 + n)

        # Row 25: Exit EBITDA — reference last year of each case
        ws.cell(row=25, column=1, value="Exit EBITDA")
        ws.cell(row=25, column=2, value=f"={exit_col}7")
        ws.cell(row=25, column=3, value=f"={exit_col}13")
        ws.cell(row=25, column=4, value="=C25-B25")
        for col in range(2, 5):
            ws.cell(row=25, column=col).number_format = '#,##0.0'

        # Row 26: Exit EV = Exit EBITDA × Exit Multiple
        ws.cell(row=26, column=1, value="Exit EV")
        ws.cell(row=26, column=2, value=f"=B25*'Assumptions'!B8")
        ws.cell(row=26, column=3, value=f"=C25*'Assumptions'!B8")
        ws.cell(row=26, column=4, value="=C26-B26")
        for col in range(2, 5):
            ws.cell(row=26, column=col).number_format = '#,##0.0'

        # Row 27: Exit Equity = Exit EV - Debt at exit (50% paydown)
        su = self.cell_map.get('sources_uses', {})
        su_debt = su.get('total_debt', 'B8')  # fallback
        ws.cell(row=27, column=1, value="Exit Equity")
        ws.cell(row=27, column=2, value=f"=B26-'Sources & Uses'!{su_debt}*0.5")
        ws.cell(row=27, column=3, value=f"=C26-'Sources & Uses'!{su_debt}*0.5")
        ws.cell(row=27, column=4, value="=C27-B27")
        for col in range(2, 5):
            ws.cell(row=27, column=col).number_format = '#,##0.0'

        # Row 28: MOIC = Exit Equity / Initial Equity
        su_equity = su.get('sponsor_equity', 'B13')
        ws.cell(row=28, column=1, value="MOIC")
        ws.cell(row=28, column=2, value=f"=IFERROR(B27/'Sources & Uses'!{su_equity},0)")
        ws.cell(row=28, column=3, value=f"=IFERROR(C27/'Sources & Uses'!{su_equity},0)")
        ws.cell(row=28, column=4, value="=C28-B28")
        for col in range(2, 5):
            ws.cell(row=28, column=col).number_format = '0.00x'
            ws.cell(row=28, column=col).font = Font(bold=True)

        # Row 29: IRR = MOIC^(1/hold) - 1
        ws.cell(row=29, column=1, value="IRR")
        ws.cell(row=29, column=2, value=f"=IFERROR(B28^(1/'Assumptions'!B9)-1,0)")
        ws.cell(row=29, column=3, value=f"=IFERROR(C28^(1/'Assumptions'!B9)-1,0)")
        ws.cell(row=29, column=4, value="=C29-B29")
        for col in range(2, 5):
            ws.cell(row=29, column=col).number_format = '0.0%'
            ws.cell(row=29, column=col).font = Font(bold=True)

        # Highlight buyer case column
        for row in range(25, 30):
            ws.cell(row=row, column=3).fill = PatternFill(start_color="90EE90", end_color="90EE90", fill_type="solid")

        # Set column widths
        ws.column_dimensions['A'].width = 20
        for i in range(n + 3):
            ws.column_dimensions[get_column_letter(2 + i)].width = 12

        self.cell_map['mgmt_vs_buyer'] = {
            'mgmt_revenue_row': 5,
            'mgmt_growth_row': 6,
            'mgmt_ebitda_row': 7,
            'mgmt_margin_row': 8,
            'buyer_revenue_row': 11,
            'buyer_growth_row': 12,
            'buyer_ebitda_row': 13,
            'buyer_margin_row': 14,
            'moic_row': 28,
            'irr_row': 29,
        }

        return self

    # ============================================================
    # MODULE: DCF VALUATION
    # ============================================================

    def add_dcf_valuation(self, data: Dict = None) -> 'ExcelModelGenerator':
        """Add DCF Valuation sheet with real Excel formulas."""
        ws = self.wb.create_sheet("DCF Valuation")
        self.sheets_created.append("DCF Valuation")

        A = "Assumptions"
        OM = "Operating Model"
        n = self.projection_years
        data = data or {}

        # WACC and terminal growth are local DCF inputs (not on Assumptions sheet)
        wacc = data.get('wacc', 0.10)
        terminal_growth = data.get('terminal_growth', 0.025)

        # Title
        self._add_title(ws, f"{self.company_name} - DCF Valuation", 1, 1)

        # DCF Assumptions (rows 3-6)
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
        ws.cell(row=6, column=2, value=f"='{A}'!B24")
        ws.cell(row=6, column=2).number_format = '0.0%'
        self._format_input_cell(ws, 6, 2)

        # Year headers (row 8)
        ws.cell(row=8, column=1, value="")
        for i in range(n):
            ws.cell(row=8, column=2 + i, value=f"Year {i + 1}")
        ws.cell(row=8, column=2 + n, value="Terminal")
        self._format_header_row(ws, 8, 1, 2 + n)

        # DCF column layout: B=Year1, C=Year2, ... last_col+1=Terminal
        # Year i (1-indexed) is in column (1+i) = col 2+i-1... actually col 2+i-1
        # Wait: Year 1 = col B (2), Year 2 = col C (3), ... Year n = col 1+n
        # But Operating Model has: B=LTM, C=Y1, D=Y2, ... so Y(i) = col 2+i
        # DCF has: B=Y1, C=Y2, ... so Y(i) = col 1+i
        # We need to map: DCF col for year i = 1+i, OM col for year i = 2+i

        # --- Unlevered Free Cash Flow Build (rows 9-18) ---
        self._add_section_header(ws, "Unlevered Free Cash Flow ($M)", 9, 1)

        # Row 10: EBITDA — from Operating Model
        ws.cell(row=10, column=1, value="EBITDA")
        for i in range(n):
            dcf_col = 2 + i  # B, C, D, ...
            om_col_letter = get_column_letter(3 + i)  # C, D, E, ... (Y1+ in OM)
            ws.cell(row=10, column=dcf_col, value=f"='{OM}'!{om_col_letter}13")
            ws.cell(row=10, column=dcf_col).number_format = '#,##0.0'

        # Row 11: Less: D&A = CapEx from Operating Model (negative)
        ws.cell(row=11, column=1, value="Less: D&A")
        for i in range(n):
            dcf_col = 2 + i
            om_col_letter = get_column_letter(3 + i)
            ws.cell(row=11, column=dcf_col, value=f"='{OM}'!{om_col_letter}16")  # CapEx is already negative
            ws.cell(row=11, column=dcf_col).number_format = '(#,##0.0)'

        # Row 12: EBIT = EBITDA + D&A (D&A is negative)
        ws.cell(row=12, column=1, value="EBIT")
        for i in range(n):
            dcf_col = 2 + i
            c = get_column_letter(dcf_col)
            ws.cell(row=12, column=dcf_col, value=f"={c}10+{c}11")
            ws.cell(row=12, column=dcf_col).number_format = '#,##0.0'

        # Row 13: Less: Taxes = -EBIT × Tax Rate
        ws.cell(row=13, column=1, value="Less: Taxes")
        for i in range(n):
            dcf_col = 2 + i
            c = get_column_letter(dcf_col)
            ws.cell(row=13, column=dcf_col, value=f"=-{c}12*$B$6")
            ws.cell(row=13, column=dcf_col).number_format = '(#,##0.0)'

        # Row 14: NOPAT = EBIT × (1 - Tax Rate)
        ws.cell(row=14, column=1, value="NOPAT")
        for i in range(n):
            dcf_col = 2 + i
            c = get_column_letter(dcf_col)
            ws.cell(row=14, column=dcf_col, value=f"={c}12*(1-$B$6)")
            ws.cell(row=14, column=dcf_col).number_format = '#,##0.0'

        # Row 15: Plus: D&A = -Row 11 (add back)
        ws.cell(row=15, column=1, value="Plus: D&A")
        for i in range(n):
            dcf_col = 2 + i
            c = get_column_letter(dcf_col)
            ws.cell(row=15, column=dcf_col, value=f"=-{c}11")
            ws.cell(row=15, column=dcf_col).number_format = '#,##0.0'

        # Row 16: Less: CapEx (same as D&A, negative)
        ws.cell(row=16, column=1, value="Less: CapEx")
        for i in range(n):
            dcf_col = 2 + i
            c = get_column_letter(dcf_col)
            ws.cell(row=16, column=dcf_col, value=f"={c}11")  # same as D&A (already negative)
            ws.cell(row=16, column=dcf_col).number_format = '(#,##0.0)'

        # Row 17: Less: Change in NWC
        # NWC = Revenue × NWC%, Change = -(this_NWC - prev_NWC)
        ws.cell(row=17, column=1, value="Less: Change in NWC")
        for i in range(n):
            dcf_col = 2 + i
            om_this = get_column_letter(3 + i)   # Y(i+1) in OM
            om_prev = get_column_letter(2 + i)   # Y(i) in OM (or LTM for i=0)
            ws.cell(row=17, column=dcf_col,
                    value=f"=-('{OM}'!{om_this}10*'{A}'!B23-'{OM}'!{om_prev}10*'{A}'!B23)")
            ws.cell(row=17, column=dcf_col).number_format = '(#,##0.0)'

        # Row 18: Unlevered FCF = NOPAT + D&A + CapEx + Change in NWC
        # Since D&A and CapEx cancel, UFCF = NOPAT + Change_NWC(row 17)
        ws.cell(row=18, column=1, value="Unlevered FCF")
        for i in range(n):
            dcf_col = 2 + i
            c = get_column_letter(dcf_col)
            ws.cell(row=18, column=dcf_col, value=f"={c}14+{c}15+{c}16+{c}17")
            ws.cell(row=18, column=dcf_col).number_format = '#,##0.0'
            ws.cell(row=18, column=dcf_col).font = Font(bold=True)
            ws.cell(row=18, column=dcf_col).border = DOUBLE_BORDER

        # Terminal Value = Last UFCF × (1+g) / (WACC - g)
        term_col = 2 + n  # Terminal column
        last_fcf_col = get_column_letter(1 + n)  # last year UFCF column
        ws.cell(row=18, column=term_col,
                value=f"={last_fcf_col}18*(1+$B$5)/($B$4-$B$5)")
        ws.cell(row=18, column=term_col).number_format = '#,##0.0'
        ws.cell(row=18, column=term_col).font = Font(bold=True)

        # --- Present Value Calculation (rows 20-22) ---
        self._add_section_header(ws, "Present Value Calculation", 20, 1)

        # Row 21: Discount Factor = 1/(1+WACC)^year
        ws.cell(row=21, column=1, value="Discount Factor")
        for i in range(n):
            dcf_col = 2 + i
            ws.cell(row=21, column=dcf_col, value=f"=1/(1+$B$4)^{i + 1}")
            ws.cell(row=21, column=dcf_col).number_format = '0.000'

        # Terminal discount factor (same as last year)
        ws.cell(row=21, column=term_col, value=f"=1/(1+$B$4)^{n}")
        ws.cell(row=21, column=term_col).number_format = '0.000'

        # Row 22: Present Value = UFCF × Discount Factor
        ws.cell(row=22, column=1, value="Present Value")
        for i in range(n):
            dcf_col = 2 + i
            c = get_column_letter(dcf_col)
            ws.cell(row=22, column=dcf_col, value=f"={c}18*{c}21")
            ws.cell(row=22, column=dcf_col).number_format = '#,##0.0'

        # PV of Terminal Value
        tc = get_column_letter(term_col)
        ws.cell(row=22, column=term_col, value=f"={tc}18*{tc}21")
        ws.cell(row=22, column=term_col).number_format = '#,##0.0'

        # --- Valuation Summary (rows 24-31) ---
        self._add_section_header(ws, "Valuation Summary ($M)", 24, 1)

        # PV of Projection FCF = SUM of PV row (excluding terminal)
        first_pv = get_column_letter(2)
        last_pv = get_column_letter(1 + n)
        ws.cell(row=25, column=1, value="PV of Projection Period FCF")
        ws.cell(row=25, column=2, value=f"=SUM({first_pv}22:{last_pv}22)")
        ws.cell(row=25, column=2).number_format = '#,##0.0'

        # PV of Terminal Value
        ws.cell(row=26, column=1, value="PV of Terminal Value")
        ws.cell(row=26, column=2, value=f"={tc}22")
        ws.cell(row=26, column=2).number_format = '#,##0.0'

        # Enterprise Value = sum
        ws.cell(row=27, column=1, value="Enterprise Value")
        ws.cell(row=27, column=2, value="=B25+B26")
        ws.cell(row=27, column=2).number_format = '#,##0.0'
        ws.cell(row=27, column=2).font = Font(bold=True, size=14)
        ws.cell(row=27, column=2).fill = PatternFill(
            start_color="90EE90", end_color="90EE90", fill_type="solid")

        # Implied multiples
        ws.cell(row=29, column=1, value="Implied EV / LTM EBITDA")
        ws.cell(row=29, column=2, value=f"=IFERROR(B27/'{A}'!B6,0)")
        ws.cell(row=29, column=2).number_format = '0.0"x"'

        # Exit EBITDA = last year in OM
        exit_om_col = get_column_letter(2 + n)
        ws.cell(row=30, column=1, value="Implied EV / Exit EBITDA")
        ws.cell(row=30, column=2, value=f"=IFERROR(B27/'{OM}'!{exit_om_col}13,0)")
        ws.cell(row=30, column=2).number_format = '0.0"x"'

        # Terminal Value % of EV
        ws.cell(row=31, column=1, value="Terminal Value % of EV")
        ws.cell(row=31, column=2, value="=IFERROR(B26/B27,0)")
        ws.cell(row=31, column=2).number_format = '0.0%'

        # Set column widths
        ws.column_dimensions['A'].width = 25
        for i in range(n + 2):
            ws.column_dimensions[get_column_letter(2 + i)].width = 12

        return self

    # ============================================================
    # MODULE: COVENANT ANALYSIS
    # ============================================================

    def add_covenant_analysis(self, data: Dict = None) -> 'ExcelModelGenerator':
        """Add Covenant Analysis sheet with live formulas referencing OM and Debt Schedule."""
        ws = self.wb.create_sheet("Covenant Analysis")
        self.sheets_created.append("Covenant Analysis")

        A = "Assumptions"
        OM = "Operating Model"
        DS = "Debt Schedule"
        a = self.assumptions
        n = self.projection_years
        data = data or {}

        # Resolve Debt Schedule cell_map (quick vs standard mode)
        ds_map = self.cell_map.get('debt_schedule', {})
        ds_mode = ds_map.get('mode', 'quick')
        om_map = self.cell_map.get('operating_model', {})
        om_ebitda_row = om_map.get('ebitda_row', 13)

        # Debt ending-balance row in DS sheet
        if ds_mode == 'standard':
            # Standard mode: total debt row = senior_ending + sub_ending via a total row
            ds_total_debt_row = ds_map.get('total_debt_row', 20)
            ds_interest_row = ds_map.get('total_interest_row', 22)
        else:
            # Quick mode
            ds_total_debt_row = ds_map.get('ending_balance_row', 12)
            ds_interest_row = ds_map.get('interest_row', 14)

        # Covenant thresholds (input cells — user-editable)
        covenants = data.get('covenants', {
            'max_leverage': 6.0,
            'min_interest_coverage': 2.0,
            'min_fixed_charge': 1.1,
        })

        # Title
        self._add_title(ws, f"{self.company_name} - Covenant Analysis", 1, 1)

        # ── Covenant Thresholds (input values) ──
        self._add_section_header(ws, "Covenant Thresholds", 3, 1)

        ws.cell(row=4, column=1, value="Maximum Leverage (Debt/EBITDA)")
        ws.cell(row=4, column=2, value=covenants['max_leverage'])
        ws.cell(row=4, column=2).number_format = '0.0"x"'
        self._format_input_cell(ws, 4, 2)

        ws.cell(row=5, column=1, value="Minimum Interest Coverage")
        ws.cell(row=5, column=2, value=covenants['min_interest_coverage'])
        ws.cell(row=5, column=2).number_format = '0.0"x"'
        self._format_input_cell(ws, 5, 2)

        ws.cell(row=6, column=1, value="Minimum Fixed Charge Coverage")
        ws.cell(row=6, column=2, value=covenants['min_fixed_charge'])
        ws.cell(row=6, column=2).number_format = '0.0"x"'
        self._format_input_cell(ws, 6, 2)

        # ── Year headers ──
        ws.cell(row=8, column=1, value="")
        ws.cell(row=8, column=2, value="Entry")
        for i in range(n):
            ws.cell(row=8, column=3 + i, value=f"Year {i + 1}")
        self._format_header_row(ws, 8, 1, 2 + n)

        # ── Leverage Ratio (formulas referencing DS and OM) ──
        self._add_section_header(ws, "Leverage Ratio (Debt / EBITDA)", 9, 1)

        # Row 10: Total Debt — pull from Debt Schedule ending balance
        ws.cell(row=10, column=1, value="Total Debt")
        for i in range(n + 1):
            col = get_column_letter(2 + i)
            ws.cell(row=10, column=2 + i,
                    value=f"='{DS}'!{col}{ds_total_debt_row}")
            ws.cell(row=10, column=2 + i).number_format = '#,##0.0'

        # Row 11: EBITDA — pull from Operating Model
        ws.cell(row=11, column=1, value="EBITDA")
        for i in range(n + 1):
            col = get_column_letter(2 + i)
            ws.cell(row=11, column=2 + i,
                    value=f"='{OM}'!{col}{om_ebitda_row}")
            ws.cell(row=11, column=2 + i).number_format = '#,##0.0'

        # Row 12: Leverage Ratio = Debt / EBITDA
        ws.cell(row=12, column=1, value="Leverage Ratio")
        for i in range(n + 1):
            col = get_column_letter(2 + i)
            ws.cell(row=12, column=2 + i,
                    value=f"=IFERROR({col}10/{col}11,0)")
            ws.cell(row=12, column=2 + i).number_format = '0.0"x"'
            ws.cell(row=12, column=2 + i).font = Font(bold=True)

        # Row 13: Covenant threshold (repeated for comparison)
        ws.cell(row=13, column=1, value="Covenant")
        for i in range(n + 1):
            ws.cell(row=13, column=2 + i, value="=$B$4")
            ws.cell(row=13, column=2 + i).number_format = '0.0"x"'
            ws.cell(row=13, column=2 + i).font = Font(italic=True, color="666666")

        # Row 14: Headroom = Covenant - Leverage
        ws.cell(row=14, column=1, value="Headroom")
        for i in range(n + 1):
            col = get_column_letter(2 + i)
            ws.cell(row=14, column=2 + i,
                    value=f"=$B$4-{col}12")
            ws.cell(row=14, column=2 + i).number_format = '0.0"x"'

        # ── Interest Coverage (formulas) ──
        self._add_section_header(ws, "Interest Coverage (EBITDA / Interest)", 16, 1)

        # Row 17: EBITDA (projected years only, cols C+)
        ws.cell(row=17, column=1, value="EBITDA")
        for i in range(n):
            col = get_column_letter(3 + i)
            ws.cell(row=17, column=3 + i,
                    value=f"='{OM}'!{col}{om_ebitda_row}")
            ws.cell(row=17, column=3 + i).number_format = '#,##0.0'

        # Row 18: Interest Expense — pull from Debt Schedule interest row
        ws.cell(row=18, column=1, value="Interest Expense")
        for i in range(n):
            col = get_column_letter(3 + i)
            ws.cell(row=18, column=3 + i,
                    value=f"='{DS}'!{col}{ds_interest_row}")
            ws.cell(row=18, column=3 + i).number_format = '#,##0.0'

        # Row 19: Interest Coverage = EBITDA / Interest
        ws.cell(row=19, column=1, value="Interest Coverage")
        for i in range(n):
            col = get_column_letter(3 + i)
            ws.cell(row=19, column=3 + i,
                    value=f"=IFERROR({col}17/{col}18,99)")
            ws.cell(row=19, column=3 + i).number_format = '0.0"x"'
            ws.cell(row=19, column=3 + i).font = Font(bold=True)

        # Row 20: Covenant threshold
        ws.cell(row=20, column=1, value="Covenant")
        for i in range(n):
            ws.cell(row=20, column=3 + i, value="=$B$5")
            ws.cell(row=20, column=3 + i).number_format = '0.0"x"'
            ws.cell(row=20, column=3 + i).font = Font(italic=True, color="666666")

        # ── Compliance Summary (formulas) ──
        self._add_section_header(ws, "Compliance Summary", 22, 1)

        # Row 23: Overall Compliance — AND of all leverage <= max AND coverage >= min
        # Build formula: check last year leverage and first year coverage as proxy
        last_yr_col = get_column_letter(2 + n)
        first_yr_col = get_column_letter(3)
        ws.cell(row=23, column=1, value="Overall Compliance")
        ws.cell(row=23, column=2,
                value=f'=IF(AND({last_yr_col}12<=$B$4,{first_yr_col}19>=$B$5),"PASS","FAIL")')
        ws.cell(row=23, column=2).font = Font(bold=True, size=14)

        # Note
        ws.cell(row=25, column=1,
                value="Note: Ratios update automatically from Operating Model and Debt Schedule")
        ws.cell(row=25, column=1).font = Font(italic=True, color="666666")

        self.cell_map['covenant_analysis'] = {
            'max_leverage_cell': 'B4',
            'min_coverage_cell': 'B5',
            'leverage_row': 12,
            'coverage_row': 19,
            'compliance_cell': 'B23',
        }

        # Set column widths
        ws.column_dimensions['A'].width = 28
        for i in range(n + 2):
            ws.column_dimensions[get_column_letter(2 + i)].width = 12

        return self

    # ============================================================
    # DUE DILIGENCE & QUALITY MODULES
    # ============================================================

    # ============================================================
    # MODULE: QUALITY OF EARNINGS (QoE)
    # ============================================================

    def add_quality_of_earnings(self, data: Dict = None) -> 'ExcelModelGenerator':
        """Add Quality of Earnings analysis with live Excel formulas for totals."""
        ws = self.wb.create_sheet("Quality of Earnings")
        self.sheets_created.append("Quality of Earnings")

        a = self.assumptions
        data = data or {}

        # Title
        self._add_title(ws, f"{self.company_name} - Quality of Earnings Analysis", 1, 1)

        # Reported EBITDA Section
        self._add_section_header(ws, "REPORTED EBITDA ($M)", 3, 1)

        ws.cell(row=4, column=1, value="")
        ws.cell(row=4, column=2, value="LTM")
        ws.cell(row=4, column=3, value="FY-1")
        ws.cell(row=4, column=4, value="FY-2")
        self._format_header_row(ws, 4, 1, 4)

        # Row 5: Reported figures (inputs)
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
            self._format_input_cell(ws, 5, col)

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

        # Rows 8+: Adjustment line items (inputs)
        adj_start_row = 8
        for i, adj in enumerate(adjustments):
            row = adj_start_row + i
            ws.cell(row=row, column=1, value=f"  {adj['name']}")
            ws.cell(row=row, column=2, value=adj['ltm'])
            ws.cell(row=row, column=3, value=adj['fy1'])
            ws.cell(row=row, column=4, value=adj['fy2'])
            for col in range(2, 5):
                ws.cell(row=row, column=col).number_format = '#,##0.0'
                ws.cell(row=row, column=col).font = Font(color="0066CC")
        adj_end_row = adj_start_row + len(adjustments) - 1

        # Total Adjustments row (SUM formula)
        total_row = adj_end_row + 2
        ws.cell(row=total_row, column=1, value="Total Adjustments")
        for col in range(2, 5):
            col_letter = get_column_letter(col)
            ws.cell(row=total_row, column=col,
                    value=f"=SUM({col_letter}{adj_start_row}:{col_letter}{adj_end_row})")
            ws.cell(row=total_row, column=col).number_format = '#,##0.0'
            ws.cell(row=total_row, column=col).font = Font(bold=True)
            ws.cell(row=total_row, column=col).border = Border(top=Side(style='thin'))

        # Adjusted EBITDA section
        adj_header_row = total_row + 2
        self._add_section_header(ws, "ADJUSTED EBITDA", adj_header_row, 1)
        adj_ebitda_row = adj_header_row + 1

        ws.cell(row=adj_ebitda_row, column=1, value="Adjusted EBITDA")
        for col in range(2, 5):
            col_letter = get_column_letter(col)
            ws.cell(row=adj_ebitda_row, column=col,
                    value=f"={col_letter}5+{col_letter}{total_row}")
            ws.cell(row=adj_ebitda_row, column=col).number_format = '#,##0.0'
            ws.cell(row=adj_ebitda_row, column=col).font = Font(bold=True)
            ws.cell(row=adj_ebitda_row, column=col).fill = PatternFill(
                start_color="90EE90", end_color="90EE90", fill_type="solid")

        # % Adjustment
        pct_row = adj_ebitda_row + 1
        ws.cell(row=pct_row, column=1, value="  % Adjustment")
        for col in range(2, 5):
            col_letter = get_column_letter(col)
            ws.cell(row=pct_row, column=col,
                    value=f"=IFERROR({col_letter}{total_row}/{col_letter}5,0)")
            ws.cell(row=pct_row, column=col).number_format = '0.0%'
            ws.cell(row=pct_row, column=col).font = Font(italic=True, color="666666")

        # Run-Rate Analysis
        rr_header_row = pct_row + 2
        self._add_section_header(ws, "RUN-RATE EBITDA ANALYSIS", rr_header_row, 1)
        rr_start = rr_header_row + 1

        # Base = Adjusted LTM EBITDA (formula reference)
        ws.cell(row=rr_start, column=1, value="Adjusted LTM EBITDA")
        ws.cell(row=rr_start, column=2, value=f"=B{adj_ebitda_row}")
        ws.cell(row=rr_start, column=2).number_format = '#,##0.0'

        run_rate_adds = data.get('run_rate_adds', [
            {'name': 'Full-year impact of price increase', 'value': 1.5},
            {'name': 'Annualized new customer wins', 'value': 2.0},
            {'name': 'Full-year cost savings', 'value': 1.0},
            {'name': 'Lost customer annualization', 'value': -0.5},
        ])

        for i, item in enumerate(run_rate_adds):
            row = rr_start + 1 + i
            ws.cell(row=row, column=1, value=f"  {item['name']}")
            ws.cell(row=row, column=2, value=item['value'])
            ws.cell(row=row, column=2).number_format = '#,##0.0'
            self._format_input_cell(ws, row, 2)
        rr_end = rr_start + len(run_rate_adds)

        # Run-Rate EBITDA total (SUM formula)
        rr_total_row = rr_end + 2
        ws.cell(row=rr_total_row, column=1, value="Run-Rate EBITDA")
        ws.cell(row=rr_total_row, column=2,
                value=f"=SUM(B{rr_start}:B{rr_end})")
        ws.cell(row=rr_total_row, column=2).number_format = '#,##0.0'
        ws.cell(row=rr_total_row, column=2).font = Font(bold=True)
        ws.cell(row=rr_total_row, column=2).fill = PatternFill(
            start_color="FFFF99", end_color="FFFF99", fill_type="solid")

        # QoE Summary
        sum_header = rr_total_row + 3
        self._add_section_header(ws, "QoE SUMMARY", sum_header, 1)
        sr = sum_header + 1

        ws.cell(row=sr, column=1, value="Reported LTM EBITDA")
        ws.cell(row=sr, column=2, value="=B5")
        ws.cell(row=sr, column=2).number_format = '#,##0.0'

        ws.cell(row=sr + 1, column=1, value="Adjusted LTM EBITDA")
        ws.cell(row=sr + 1, column=2, value=f"=B{adj_ebitda_row}")
        ws.cell(row=sr + 1, column=2).number_format = '#,##0.0'

        ws.cell(row=sr + 2, column=1, value="Run-Rate EBITDA")
        ws.cell(row=sr + 2, column=2, value=f"=B{rr_total_row}")
        ws.cell(row=sr + 2, column=2).number_format = '#,##0.0'

        ws.cell(row=sr + 3, column=1, value="Implied Adjustment %")
        ws.cell(row=sr + 3, column=2, value=f"=IFERROR((B{rr_total_row}-B5)/B5,0)")
        ws.cell(row=sr + 3, column=2).number_format = '0.0%'
        ws.cell(row=sr + 3, column=2).font = Font(bold=True)

        # Column widths
        ws.column_dimensions['A'].width = 35
        ws.column_dimensions['B'].width = 15
        ws.column_dimensions['C'].width = 15
        ws.column_dimensions['D'].width = 15

        self.cell_map['quality_of_earnings'] = {
            'reported_ebitda_row': 5,
            'adj_start_row': adj_start_row,
            'adj_end_row': adj_end_row,
            'total_adj_row': total_row,
            'adjusted_ebitda_row': adj_ebitda_row,
            'run_rate_row': rr_total_row,
        }

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

        ca_start = row
        for item_name, values in [
            ("  Accounts Receivable", historical['accounts_receivable']),
            ("  Inventory", historical['inventory']),
            ("  Prepaid Expenses", historical['prepaid_expenses']),
        ]:
            ws.cell(row=row, column=1, value=item_name)
            for i, v in enumerate(values):
                ws.cell(row=row, column=2 + i, value=v)
                ws.cell(row=row, column=2 + i).number_format = '#,##0.0'
                self._format_input_cell(ws, row, 2 + i)
            ws.cell(row=row, column=6, value=f"=AVERAGE(B{row}:E{row})")
            ws.cell(row=row, column=6).number_format = '#,##0.0'
            row += 1
        ca_end = row - 1

        # Total Current Assets
        ca_total_row = row
        ws.cell(row=row, column=1, value="Total Current Assets")
        for i in range(4):
            c = get_column_letter(2 + i)
            ws.cell(row=row, column=2 + i, value=f"=SUM({c}{ca_start}:{c}{ca_end})")
            ws.cell(row=row, column=2 + i).number_format = '#,##0.0'
        ws.cell(row=row, column=6, value=f"=AVERAGE(B{row}:E{row})")
        ws.cell(row=row, column=6).number_format = '#,##0.0'
        ws.cell(row=row, column=1).font = Font(bold=True)
        row += 2

        # Current Liabilities
        ws.cell(row=row, column=1, value="Current Liabilities")
        ws.cell(row=row, column=1).font = Font(bold=True, italic=True)
        row += 1

        cl_item_start = row
        for item_name, values in [
            ("  Accounts Payable", historical['accounts_payable']),
            ("  Accrued Expenses", historical['accrued_expenses']),
            ("  Deferred Revenue", historical['deferred_revenue']),
        ]:
            ws.cell(row=row, column=1, value=item_name)
            for i, v in enumerate(values):
                ws.cell(row=row, column=2 + i, value=v)
                ws.cell(row=row, column=2 + i).number_format = '#,##0.0'
                self._format_input_cell(ws, row, 2 + i)
            ws.cell(row=row, column=6, value=f"=AVERAGE(B{row}:E{row})")
            ws.cell(row=row, column=6).number_format = '#,##0.0'
            row += 1
        cl_item_end = row - 1

        # Total Current Liabilities
        cl_total_row = row
        ws.cell(row=row, column=1, value="Total Current Liabilities")
        for i in range(4):
            c = get_column_letter(2 + i)
            ws.cell(row=row, column=2 + i, value=f"=SUM({c}{cl_item_start}:{c}{cl_item_end})")
            ws.cell(row=row, column=2 + i).number_format = '#,##0.0'
        ws.cell(row=row, column=6, value=f"=AVERAGE(B{row}:E{row})")
        ws.cell(row=row, column=6).number_format = '#,##0.0'
        ws.cell(row=row, column=1).font = Font(bold=True)
        row += 2

        # Net Working Capital
        nwc_row = row
        ws.cell(row=row, column=1, value="Net Working Capital")
        for i in range(4):
            c = get_column_letter(2 + i)
            ws.cell(row=row, column=2 + i, value=f"={c}{ca_total_row}-{c}{cl_total_row}")
            ws.cell(row=row, column=2 + i).number_format = '#,##0.0'
            ws.cell(row=row, column=2 + i).font = Font(bold=True)
        ws.cell(row=row, column=6, value=f"=AVERAGE(B{row}:E{row})")
        ws.cell(row=row, column=6).number_format = '#,##0.0'
        ws.cell(row=row, column=6).font = Font(bold=True)
        ws.cell(row=row, column=6).fill = PatternFill(start_color="FFFF99", end_color="FFFF99", fill_type="solid")
        row += 2

        # Revenue reference row (needed for NWC % and Days calculations)
        revenues = historical['revenue']
        rev_row = row
        ws.cell(row=row, column=1, value="Revenue")
        for i, v in enumerate(revenues):
            ws.cell(row=row, column=2 + i, value=v)
            ws.cell(row=row, column=2 + i).number_format = '#,##0.0'
            self._format_input_cell(ws, row, 2 + i)
        ws.cell(row=row, column=6, value=f"=AVERAGE(B{row}:E{row})")
        ws.cell(row=row, column=6).number_format = '#,##0.0'
        row += 1

        # NWC as % of Revenue
        nwc_pct_row = row
        ws.cell(row=row, column=1, value="NWC as % of Revenue")
        for i in range(4):
            c = get_column_letter(2 + i)
            ws.cell(row=row, column=2 + i, value=f"=IFERROR({c}{nwc_row}/{c}{rev_row},0)")
            ws.cell(row=row, column=2 + i).number_format = '0.0%'
        ws.cell(row=row, column=6, value=f"=AVERAGE(B{row}:E{row})")
        ws.cell(row=row, column=6).number_format = '0.0%'
        ws.cell(row=row, column=6).font = Font(bold=True)
        row += 3

        # Target NWC / Peg Analysis
        self._add_section_header(ws, "NWC PEG MECHANISM", row, 1)
        row += 1

        target_row_num = row
        ws.cell(row=row, column=1, value="Target NWC (Peg)")
        if 'target_nwc' in data:
            ws.cell(row=row, column=2, value=data['target_nwc'])
        else:
            ws.cell(row=row, column=2, value=f"=F{nwc_row}")  # Default = average NWC
        ws.cell(row=row, column=2).number_format = '#,##0.0'
        self._format_input_cell(ws, row, 2)
        row += 1

        closing_row_num = row
        ws.cell(row=row, column=1, value="Estimated Closing NWC")
        if 'actual_nwc' in data:
            ws.cell(row=row, column=2, value=data['actual_nwc'])
        else:
            ws.cell(row=row, column=2, value=f"=B{nwc_row}")  # Default = LTM NWC
        ws.cell(row=row, column=2).number_format = '#,##0.0'
        self._format_input_cell(ws, row, 2)
        row += 2

        ws.cell(row=row, column=1, value="NWC Variance")
        ws.cell(row=row, column=2, value=f"=B{closing_row_num}-B{target_row_num}")
        ws.cell(row=row, column=2).number_format = '#,##0.0'
        ws.cell(row=row, column=2).font = Font(bold=True)
        ws.cell(row=row, column=3, value=f'=IF(B{row}<0,"← Buyer receives adjustment","← Seller receives adjustment")')
        ws.cell(row=row, column=3).font = Font(italic=True)
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

        # AR = ca_start, Inventory = ca_start+1, AP = cl_item_start
        ar_row = ca_start
        inv_row_num = ca_start + 1
        ap_row = cl_item_start

        dso_row = row
        ws.cell(row=row, column=1, value="Days Sales Outstanding (DSO)")
        ws.cell(row=row, column=2, value=f"=IFERROR(B{ar_row}/B{rev_row}*365,0)")
        ws.cell(row=row, column=3, value=data.get('target_dso', 40))
        ws.cell(row=row, column=4, value=data.get('benchmark_dso', 45))
        for col in range(2, 5):
            ws.cell(row=row, column=col).number_format = '0'
        self._format_input_cell(ws, row, 3)
        self._format_input_cell(ws, row, 4)
        row += 1

        dio_row = row
        ws.cell(row=row, column=1, value="Days Inventory Outstanding (DIO)")
        ws.cell(row=row, column=2, value=f"=IFERROR(B{inv_row_num}/(B{rev_row}*0.6)*365,0)")
        ws.cell(row=row, column=3, value=data.get('target_dio', 35))
        ws.cell(row=row, column=4, value=data.get('benchmark_dio', 40))
        for col in range(2, 5):
            ws.cell(row=row, column=col).number_format = '0'
        self._format_input_cell(ws, row, 3)
        self._format_input_cell(ws, row, 4)
        row += 1

        dpo_row = row
        ws.cell(row=row, column=1, value="Days Payable Outstanding (DPO)")
        ws.cell(row=row, column=2, value=f"=IFERROR(B{ap_row}/(B{rev_row}*0.6)*365,0)")
        ws.cell(row=row, column=3, value=data.get('target_dpo', 45))
        ws.cell(row=row, column=4, value=data.get('benchmark_dpo', 40))
        for col in range(2, 5):
            ws.cell(row=row, column=col).number_format = '0'
        self._format_input_cell(ws, row, 3)
        self._format_input_cell(ws, row, 4)
        row += 1

        # Cash Conversion Cycle
        row += 1
        ws.cell(row=row, column=1, value="Cash Conversion Cycle")
        ws.cell(row=row, column=2, value=f"=B{dso_row}+B{dio_row}-B{dpo_row}")
        ws.cell(row=row, column=2).number_format = '0'
        ws.cell(row=row, column=2).font = Font(bold=True)

        # Column widths
        ws.column_dimensions['A'].width = 30
        for col in ['B', 'C', 'D', 'E', 'F']:
            ws.column_dimensions[col].width = 12

        self.cell_map['nwc_normalization'] = {
            'ca_start': ca_start,
            'ca_end': ca_end,
            'ca_total_row': ca_total_row,
            'cl_start': cl_item_start,
            'cl_end': cl_item_end,
            'cl_total_row': cl_total_row,
            'nwc_row': nwc_row,
            'rev_row': rev_row,
            'nwc_pct_row': nwc_pct_row,
            'target_row': target_row_num,
            'closing_row': closing_row_num,
            'dso_row': dso_row,
            'dio_row': dio_row,
            'dpo_row': dpo_row,
        }

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

        cust_start = 5
        row = 5
        for cust in customers:
            ws.cell(row=row, column=1, value=cust['name'])
            ws.cell(row=row, column=2, value=cust['revenue'])
            ws.cell(row=row, column=2).number_format = '#,##0.0'
            self._format_input_cell(ws, row, 2)
            ws.cell(row=row, column=4, value=cust['tenure'] if cust['tenure'] else "—")
            ws.cell(row=row, column=5, value=cust['contract'])
            row += 1
        cust_end = row - 1

        # Concentration summary
        row += 1
        total_rev_row = row
        ws.cell(row=row, column=1, value="Total Revenue")
        ws.cell(row=row, column=2, value=f"=SUM(B{cust_start}:B{cust_end})")
        ws.cell(row=row, column=2).number_format = '#,##0.0'
        ws.cell(row=row, column=2).font = Font(bold=True)

        # Fill % of Total (col C) referencing total row
        for r in range(cust_start, cust_end + 1):
            ws.cell(row=r, column=3, value=f"=IFERROR(B{r}/B${total_rev_row},0)")
            ws.cell(row=r, column=3).number_format = '0.0%'
        row += 1

        top5_end = min(cust_start + 4, cust_end)
        ws.cell(row=row, column=1, value="Top 5 Concentration")
        ws.cell(row=row, column=2, value=f"=IFERROR(SUM(B{cust_start}:B{top5_end})/B{total_rev_row},0)")
        ws.cell(row=row, column=2).number_format = '0.0%'
        ws.cell(row=row, column=2).font = Font(bold=True)
        ws.cell(row=row, column=3, value=f'=IF(B{row}>0.5,"⚠ High concentration risk","")')
        ws.cell(row=row, column=3).font = Font(color="FF0000")
        row += 1

        ws.cell(row=row, column=1, value="Top 1 Concentration")
        ws.cell(row=row, column=2, value=f"=IFERROR(B{cust_start}/B{total_rev_row},0)")
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

        # Input rows (fixed positions for formulas)
        arpu_row = row
        ws.cell(row=row, column=1, value="Average Revenue Per User (ARPU)")
        ws.cell(row=row, column=2, value=unit_econ['arpu'])
        ws.cell(row=row, column=2).number_format = '#,##0'
        self._format_input_cell(ws, row, 2)
        row += 1

        cac_row = row
        ws.cell(row=row, column=1, value="Customer Acquisition Cost (CAC)")
        ws.cell(row=row, column=2, value=unit_econ['cac'])
        ws.cell(row=row, column=2).number_format = '#,##0'
        self._format_input_cell(ws, row, 2)
        row += 1

        margin_row = row
        ws.cell(row=row, column=1, value="Gross Margin")
        ws.cell(row=row, column=2, value=unit_econ['gross_margin'])
        ws.cell(row=row, column=2).number_format = '0.0%'
        self._format_input_cell(ws, row, 2)
        row += 1

        churn_row = row
        ws.cell(row=row, column=1, value="Annual Churn Rate")
        ws.cell(row=row, column=2, value=unit_econ['churn_rate'])
        ws.cell(row=row, column=2).number_format = '0.0%'
        self._format_input_cell(ws, row, 2)
        row += 1

        ltv_row = row
        ws.cell(row=row, column=1, value="Customer Lifetime Value (LTV)")
        ws.cell(row=row, column=2, value=f"=IFERROR(B{arpu_row}*B{margin_row}/B{churn_row},0)")
        ws.cell(row=row, column=2).number_format = '#,##0'
        row += 1

        ltv_cac_row = row
        ws.cell(row=row, column=1, value="LTV/CAC Ratio")
        ws.cell(row=row, column=2, value=f"=IFERROR(B{ltv_row}/B{cac_row},0)")
        ws.cell(row=row, column=2).number_format = '0.0x'
        ws.cell(row=row, column=2).font = Font(bold=True)
        ws.cell(row=row, column=3, value=f'=IF(B{row}>=3,"✓ Healthy (>3x)",IF(B{row}>=1,"⚠ Marginal (1-3x)","✗ Unhealthy (<1x)"))')
        row += 1

        ws.cell(row=row, column=1, value="CAC Payback (months)")
        ws.cell(row=row, column=2, value=f"=IFERROR(B{cac_row}/(B{arpu_row}*B{margin_row}/12),0)")
        ws.cell(row=row, column=2).number_format = '0.0'
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

        qf_start = row
        for factor in quality_factors:
            ws.cell(row=row, column=1, value=factor['factor'])
            ws.cell(row=row, column=2, value=factor['score'])
            self._format_input_cell(ws, row, 2)
            ws.cell(row=row, column=3, value=factor['notes'])
            row += 1
        qf_end = row - 1

        row += 1
        ws.cell(row=row, column=1, value="Overall Quality Score")
        ws.cell(row=row, column=2, value=f"=AVERAGE(B{qf_start}:B{qf_end})")
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
        """Add Credit/Debt Sizing analysis with live Excel formulas."""
        ws = self.wb.create_sheet("Credit Analysis")
        self.sheets_created.append("Credit Analysis")

        a = self.assumptions
        data = data or {}

        # Title
        self._add_title(ws, f"{self.company_name} - Credit & Debt Sizing Analysis", 1, 1)

        # ── CREDIT PROFILE (rows 3-10) ──
        self._add_section_header(ws, "CREDIT PROFILE", 3, 1)

        # Inputs (rows 4-10)
        ws.cell(row=4, column=1, value="LTM EBITDA")
        ws.cell(row=4, column=2, value=f"='Assumptions'!B6")
        ws.cell(row=4, column=2).number_format = '#,##0.0'

        ws.cell(row=5, column=1, value="LTM Revenue")
        ws.cell(row=5, column=2, value=f"='Assumptions'!B5")
        ws.cell(row=5, column=2).number_format = '#,##0.0'

        # Total debt from S&U if available
        su = self.cell_map.get('sources_uses', {})
        su_debt = su.get('total_debt', None)
        if su_debt:
            ws.cell(row=6, column=2, value=f"='Sources & Uses'!{su_debt}")
        else:
            ws.cell(row=6, column=2, value=a.ltm_ebitda * (a.senior_debt_multiple + a.sub_debt_multiple))
        ws.cell(row=6, column=1, value="Total Debt")
        ws.cell(row=6, column=2).number_format = '#,##0.0'

        ws.cell(row=7, column=1, value="Cash & Equivalents")
        ws.cell(row=7, column=2, value=data.get('cash', 10.0))
        ws.cell(row=7, column=2).number_format = '#,##0.0'
        self._format_input_cell(ws, 7, 2)

        ws.cell(row=8, column=1, value="Net Debt")
        ws.cell(row=8, column=2, value="=B6-B7")
        ws.cell(row=8, column=2).number_format = '#,##0.0'

        ws.cell(row=9, column=1, value="Interest Expense")
        ws.cell(row=9, column=2, value=a.ltm_ebitda * a.senior_debt_multiple * 0.08)
        ws.cell(row=9, column=2).number_format = '#,##0.0'
        self._format_input_cell(ws, 9, 2)

        ws.cell(row=10, column=1, value="CapEx")
        ws.cell(row=10, column=2, value=f"=B5*'Assumptions'!B22")
        ws.cell(row=10, column=2).number_format = '#,##0.0'

        # ── KEY CREDIT RATIOS (rows 12-18) ──
        self._add_section_header(ws, "KEY CREDIT RATIOS", 12, 1)

        ws.cell(row=13, column=1, value="Ratio")
        ws.cell(row=13, column=2, value="Current")
        ws.cell(row=13, column=3, value="Threshold")
        ws.cell(row=13, column=4, value="Status")
        self._format_header_row(ws, 13, 1, 4)

        # All ratios as formulas
        ratio_rows = [
            (14, "Total Debt / EBITDA", "=IFERROR(B6/B4,0)", 5.5, "max"),
            (15, "Net Debt / EBITDA", "=IFERROR(B8/B4,0)", 5.0, "max"),
            (16, "EBITDA / Interest", "=IFERROR(B4/B9,0)", 2.0, "min"),
            (17, "(EBITDA - CapEx) / Interest", "=IFERROR((B4-B10)/B9,0)", 1.5, "min"),
            (18, "Debt / Revenue", "=IFERROR(B6/B5,0)", 0.5, "max"),
        ]

        for row, name, formula, threshold, direction in ratio_rows:
            ws.cell(row=row, column=1, value=name)
            ws.cell(row=row, column=2, value=formula)
            ws.cell(row=row, column=2).number_format = '0.00x'
            ws.cell(row=row, column=3, value=threshold)
            ws.cell(row=row, column=3).number_format = '0.00x'
            # Status with IF formula
            if direction == "max":
                ws.cell(row=row, column=4, value=f'=IF(B{row}<=C{row},"Pass","Fail")')
            else:
                ws.cell(row=row, column=4, value=f'=IF(B{row}>=C{row},"Pass","Fail")')

        # ── DEBT CAPACITY (rows 20-28) ──
        self._add_section_header(ws, "DEBT CAPACITY ANALYSIS", 20, 1)

        ws.cell(row=21, column=1, value="Constraint")
        ws.cell(row=21, column=2, value="Multiple")
        ws.cell(row=21, column=3, value="Max Debt ($M)")
        self._format_header_row(ws, 21, 1, 3)

        constraints = [
            (22, 'Leverage Ratio (5.5x EBITDA)', 5.5),
            (23, 'Interest Coverage (2.0x floor)', 4.5),
            (24, 'Fixed Charge Coverage (1.5x)', 4.0),
            (25, 'Senior Secured (4.0x)', 4.0),
        ]

        for row, name, mult in constraints:
            ws.cell(row=row, column=1, value=name)
            ws.cell(row=row, column=2, value=mult)
            ws.cell(row=row, column=2).number_format = '0.0x'
            self._format_input_cell(ws, row, 2)
            ws.cell(row=row, column=3, value=f"=B4*B{row}")
            ws.cell(row=row, column=3).number_format = '#,##0.0'

        ws.cell(row=27, column=1, value="Binding Constraint (Max Debt)")
        ws.cell(row=27, column=2, value="=MIN(C22:C25)")
        ws.cell(row=27, column=2).number_format = '#,##0.0'
        ws.cell(row=27, column=2).font = Font(bold=True)
        ws.cell(row=27, column=2).fill = PatternFill(start_color="90EE90", end_color="90EE90", fill_type="solid")
        ws.cell(row=27, column=3, value="=IFERROR(B27/B4,0)")
        ws.cell(row=27, column=3).number_format = '0.0x'
        ws.cell(row=27, column=3).font = Font(bold=True)

        # ── STRESS TEST (rows 29-36) ──
        self._add_section_header(ws, "EBITDA STRESS TEST", 29, 1)

        ws.cell(row=30, column=1, value="EBITDA Decline")
        ws.cell(row=30, column=2, value="Stressed EBITDA")
        ws.cell(row=30, column=3, value="Leverage")
        ws.cell(row=30, column=4, value="Coverage")
        ws.cell(row=30, column=5, value="Status")
        self._format_header_row(ws, 30, 1, 5)

        stress_levels = [0.0, -0.10, -0.20, -0.30, -0.40]
        for i, decline in enumerate(stress_levels):
            row = 31 + i
            ws.cell(row=row, column=1, value=decline)
            ws.cell(row=row, column=1).number_format = '0%'
            # Stressed EBITDA = LTM × (1 + decline)
            ws.cell(row=row, column=2, value=f"=$B$4*(1+A{row})")
            ws.cell(row=row, column=2).number_format = '#,##0.0'
            # Leverage = Debt / Stressed EBITDA
            ws.cell(row=row, column=3, value=f"=IFERROR($B$6/B{row},999)")
            ws.cell(row=row, column=3).number_format = '0.0x'
            # Coverage = Stressed EBITDA / Interest
            ws.cell(row=row, column=4, value=f"=IFERROR(B{row}/$B$9,0)")
            ws.cell(row=row, column=4).number_format = '0.0x'
            # Status formula
            ws.cell(row=row, column=5,
                    value=f'=IF(AND(C{row}<=6,D{row}>=1.5),"Serviceable",'
                          f'IF(AND(C{row}<=7,D{row}>=1),"Tight","Distressed"))')

        # ── IMPLIED RATING (row 38) ──
        self._add_section_header(ws, "IMPLIED CREDIT RATING", 38, 1)
        ws.cell(row=39, column=1, value="Implied Rating")
        ws.cell(row=39, column=2,
                value='=IF(AND(B14<2,B16>8),"BBB / Baa2",'
                      'IF(AND(B14<3.5,B16>4),"BB / Ba2",'
                      'IF(AND(B14<5,B16>2.5),"B+ / B1",'
                      'IF(AND(B14<6,B16>2),"B / B2","B- / B3 or lower"))))')
        ws.cell(row=39, column=2).font = Font(bold=True)

        # Column widths
        ws.column_dimensions['A'].width = 30
        for col in ['B', 'C', 'D', 'E']:
            ws.column_dimensions[col].width = 15

        self.cell_map['credit_analysis'] = {
            'ebitda': 'B4',
            'revenue': 'B5',
            'total_debt': 'B6',
            'cash': 'B7',
            'net_debt': 'B8',
            'interest': 'B9',
            'capex': 'B10',
            'leverage_ratio': 'B14',
            'coverage_ratio': 'B16',
            'max_debt': 'B27',
            'implied_rating': 'B39',
        }

        return self

    # ============================================================
    # RETURNS & CAPITAL STRUCTURE MODULES
    # ============================================================

    # ============================================================
    # MODULE: DIVIDEND RECAPITALIZATION
    # ============================================================

    def add_dividend_recap(self, data: Dict = None) -> 'ExcelModelGenerator':
        """Add Dividend Recapitalization analysis with live Excel formulas."""
        ws = self.wb.create_sheet("Dividend Recap")
        self.sheets_created.append("Dividend Recap")

        a = self.assumptions
        data = data or {}

        # Title
        self._add_title(ws, f"{self.company_name} - Dividend Recapitalization Analysis", 1, 1)

        # ── CURRENT CAPITAL STRUCTURE (rows 3-7) ──
        self._add_section_header(ws, "CURRENT CAPITAL STRUCTURE ($M)", 3, 1)

        ws.cell(row=4, column=1, value="Enterprise Value")
        ws.cell(row=4, column=2, value="='Assumptions'!B6*'Assumptions'!B7")
        ws.cell(row=4, column=2).number_format = '#,##0.0'

        su = self.cell_map.get('sources_uses', {})
        su_debt = su.get('total_debt', None)
        ws.cell(row=5, column=1, value="Less: Existing Debt")
        if su_debt:
            ws.cell(row=5, column=2, value=f"=-'Sources & Uses'!{su_debt}")
        else:
            ws.cell(row=5, column=2, value=f"=-'Assumptions'!B6*('Assumptions'!B12+'Assumptions'!B15)")
        ws.cell(row=5, column=2).number_format = '(#,##0.0)'

        ws.cell(row=6, column=1, value="Equity Value")
        ws.cell(row=6, column=2, value="=B4+B5")
        ws.cell(row=6, column=2).number_format = '#,##0.0'
        ws.cell(row=6, column=2).font = Font(bold=True)

        ws.cell(row=7, column=1, value="Current Leverage")
        ws.cell(row=7, column=2, value="=IFERROR(-B5/'Assumptions'!B6,0)")
        ws.cell(row=7, column=2).number_format = '0.0x'

        # ── RECAP PARAMETERS (rows 9-16) ──
        self._add_section_header(ws, "DIVIDEND RECAP PARAMETERS", 9, 1)

        recap_year = data.get('recap_year', 2)
        new_debt_amount = data.get('new_debt_amount', a.ltm_ebitda * 1.5)
        recap_rate = data.get('recap_debt_rate', 0.09)

        ws.cell(row=10, column=1, value="Recap Timing (Year)")
        ws.cell(row=10, column=2, value=recap_year)
        self._format_input_cell(ws, 10, 2)

        ws.cell(row=11, column=1, value="EBITDA at Recap")
        # Grow LTM EBITDA by avg growth for recap_year periods
        ws.cell(row=11, column=2, value=f"='Assumptions'!B6*(1+'Assumptions'!C{self.cell_map['assumptions']['rev_growth_row']})^B10")
        ws.cell(row=11, column=2).number_format = '#,##0.0'

        ws.cell(row=12, column=1, value="New Debt Amount")
        ws.cell(row=12, column=2, value=new_debt_amount)
        ws.cell(row=12, column=2).number_format = '#,##0.0'
        self._format_input_cell(ws, 12, 2)

        ws.cell(row=13, column=1, value="New Debt Rate")
        ws.cell(row=13, column=2, value=recap_rate)
        ws.cell(row=13, column=2).number_format = '0.0%'
        self._format_input_cell(ws, 13, 2)

        # Existing debt at recap (20% paydown/year)
        ws.cell(row=14, column=1, value="Existing Debt at Recap")
        ws.cell(row=14, column=2, value="=-B5*0.8^B10")
        ws.cell(row=14, column=2).number_format = '#,##0.0'

        ws.cell(row=15, column=1, value="Total Debt Post-Recap")
        ws.cell(row=15, column=2, value="=B14+B12")
        ws.cell(row=15, column=2).number_format = '#,##0.0'
        ws.cell(row=15, column=2).font = Font(bold=True)

        ws.cell(row=16, column=1, value="Post-Recap Leverage")
        ws.cell(row=16, column=2, value="=IFERROR(B15/B11,0)")
        ws.cell(row=16, column=2).number_format = '0.0x'
        ws.cell(row=16, column=2).font = Font(bold=True)

        # ── DIVIDEND DISTRIBUTION (rows 18-22) ──
        self._add_section_header(ws, "DIVIDEND DISTRIBUTION", 18, 1)

        ws.cell(row=19, column=1, value="Gross Proceeds")
        ws.cell(row=19, column=2, value="=B12")
        ws.cell(row=19, column=2).number_format = '#,##0.0'

        ws.cell(row=20, column=1, value="Less: Financing Fees (2%)")
        ws.cell(row=20, column=2, value="=-B12*0.02")
        ws.cell(row=20, column=2).number_format = '(#,##0.0)'

        ws.cell(row=21, column=1, value="Net Dividend to Equity")
        ws.cell(row=21, column=2, value="=B19+B20")
        ws.cell(row=21, column=2).number_format = '#,##0.0'
        ws.cell(row=21, column=2).font = Font(bold=True)
        ws.cell(row=21, column=2).fill = PatternFill(start_color="90EE90", end_color="90EE90", fill_type="solid")

        # ── RETURNS IMPACT (rows 23-32) ──
        self._add_section_header(ws, "RETURNS IMPACT ANALYSIS", 23, 1)

        ws.cell(row=24, column=1, value="Metric")
        ws.cell(row=24, column=2, value="Without Recap")
        ws.cell(row=24, column=3, value="With Recap")
        ws.cell(row=24, column=4, value="Impact")
        self._format_header_row(ws, 24, 1, 4)

        # Row 25: Initial Equity = from S&U or calculated
        su_equity = su.get('sponsor_equity', None)
        ws.cell(row=25, column=1, value="Initial Equity Investment")
        if su_equity:
            ws.cell(row=25, column=2, value=f"='Sources & Uses'!{su_equity}")
        else:
            ws.cell(row=25, column=2, value="=B4*(1+'Assumptions'!B19)-(-B5)")
        ws.cell(row=25, column=3, value="=B25")
        ws.cell(row=25, column=4, value="=C25-B25")
        for col in range(2, 5):
            ws.cell(row=25, column=col).number_format = '#,##0.0'

        # Row 26: Dividend Proceeds
        ws.cell(row=26, column=1, value="Dividend Proceeds")
        ws.cell(row=26, column=2, value=0)
        ws.cell(row=26, column=3, value="=B21")
        ws.cell(row=26, column=4, value="=C26-B26")
        for col in range(2, 5):
            ws.cell(row=26, column=col).number_format = '#,##0.0'

        # Row 27: Exit EV = exit EBITDA × exit multiple
        ws.cell(row=27, column=1, value="Exit EV")
        # Exit EBITDA = LTM × (1+growth)^hold
        ws.cell(row=27, column=2, value=f"='Assumptions'!B6*(1+'Assumptions'!C{self.cell_map['assumptions']['rev_growth_row']})^'Assumptions'!B9*'Assumptions'!B8")
        ws.cell(row=27, column=3, value="=B27")
        ws.cell(row=27, column=4, value=0)
        for col in range(2, 5):
            ws.cell(row=27, column=col).number_format = '#,##0.0'

        # Row 28: Exit Equity (without recap: 50% debt paydown; with recap: 60% paydown)
        ws.cell(row=28, column=1, value="Exit Equity Proceeds")
        ws.cell(row=28, column=2, value="=B27-(-B5)*0.5")
        ws.cell(row=28, column=3, value="=C27-B15*0.6")
        ws.cell(row=28, column=4, value="=C28-B28")
        for col in range(2, 5):
            ws.cell(row=28, column=col).number_format = '#,##0.0'

        # Row 29: Total Proceeds
        ws.cell(row=29, column=1, value="Total Proceeds")
        ws.cell(row=29, column=2, value="=B28")
        ws.cell(row=29, column=3, value="=C26+C28")
        ws.cell(row=29, column=4, value="=C29-B29")
        for col in range(2, 5):
            ws.cell(row=29, column=col).number_format = '#,##0.0'

        # Row 30: MOIC
        ws.cell(row=30, column=1, value="MOIC")
        ws.cell(row=30, column=2, value="=IFERROR(B29/B25,0)")
        ws.cell(row=30, column=3, value="=IFERROR(C29/C25,0)")
        ws.cell(row=30, column=4, value="=C30-B30")
        for col in range(2, 5):
            ws.cell(row=30, column=col).number_format = '0.00x'
            ws.cell(row=30, column=col).font = Font(bold=True)

        # Row 31: IRR
        ws.cell(row=31, column=1, value="IRR (approx)")
        ws.cell(row=31, column=2, value="=IFERROR(B30^(1/'Assumptions'!B9)-1,0)")
        ws.cell(row=31, column=3, value="=IFERROR(C30^(1/'Assumptions'!B9)-1,0)")
        ws.cell(row=31, column=4, value="=C31-B31")
        for col in range(2, 5):
            ws.cell(row=31, column=col).number_format = '0.0%'
            ws.cell(row=31, column=col).font = Font(bold=True)

        # Column widths
        ws.column_dimensions['A'].width = 30
        for col in ['B', 'C', 'D']:
            ws.column_dimensions[col].width = 15

        self.cell_map['dividend_recap'] = {
            'ev': 'B4',
            'existing_debt': 'B5',
            'equity_value': 'B6',
            'recap_year': 'B10',
            'new_debt': 'B12',
            'total_debt_post': 'B15',
            'net_dividend': 'B21',
            'moic_without': 'B30',
            'moic_with': 'C30',
            'irr_without': 'B31',
            'irr_with': 'C31',
        }

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

        old_start = row
        for debt in current_debt:
            ws.cell(row=row, column=1, value=debt['tranche'])
            ws.cell(row=row, column=2, value=debt['amount'])
            ws.cell(row=row, column=2).number_format = '#,##0.0'
            self._format_input_cell(ws, row, 2)
            ws.cell(row=row, column=3, value=debt['rate'])
            ws.cell(row=row, column=3).number_format = '0.00%'
            self._format_input_cell(ws, row, 3)
            ws.cell(row=row, column=4, value=debt['maturity'])
            ws.cell(row=row, column=5, value=debt['callable'])
            row += 1
        old_end = row - 1

        row += 1
        old_total_row = row
        ws.cell(row=row, column=1, value="Total / Weighted Average")
        ws.cell(row=row, column=2, value=f"=SUM(B{old_start}:B{old_end})")
        ws.cell(row=row, column=2).number_format = '#,##0.0'
        ws.cell(row=row, column=2).font = Font(bold=True)
        ws.cell(row=row, column=3, value=f"=IFERROR(SUMPRODUCT(B{old_start}:B{old_end},C{old_start}:C{old_end})/B{row},0)")
        ws.cell(row=row, column=3).number_format = '0.00%'
        ws.cell(row=row, column=3).font = Font(bold=True)
        total_debt = sum(d['amount'] for d in current_debt)  # keep for default new_structure
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

        new_start = row
        for debt in new_structure:
            ws.cell(row=row, column=1, value=debt['tranche'])
            ws.cell(row=row, column=2, value=debt['amount'])
            ws.cell(row=row, column=2).number_format = '#,##0.0'
            self._format_input_cell(ws, row, 2)
            ws.cell(row=row, column=3, value=debt['rate'])
            ws.cell(row=row, column=3).number_format = '0.00%'
            self._format_input_cell(ws, row, 3)
            ws.cell(row=row, column=4, value=debt['maturity'])
            row += 1
        new_end = row - 1

        row += 1
        new_total_row = row
        ws.cell(row=row, column=1, value="Total / Weighted Average")
        ws.cell(row=row, column=2, value=f"=SUM(B{new_start}:B{new_end})")
        ws.cell(row=row, column=2).number_format = '#,##0.0'
        ws.cell(row=row, column=2).font = Font(bold=True)
        ws.cell(row=row, column=3, value=f"=IFERROR(SUMPRODUCT(B{new_start}:B{new_end},C{new_start}:C{new_end})/B{row},0)")
        ws.cell(row=row, column=3).number_format = '0.00%'
        ws.cell(row=row, column=3).font = Font(bold=True)
        row += 3

        # Savings Analysis
        self._add_section_header(ws, "ANNUAL SAVINGS ANALYSIS", row, 1)
        row += 1

        old_int_row = row
        ws.cell(row=row, column=1, value="Current Interest Expense")
        ws.cell(row=row, column=2, value=f"=SUMPRODUCT(B{old_start}:B{old_end},C{old_start}:C{old_end})")
        ws.cell(row=row, column=2).number_format = '#,##0.0'
        row += 1

        new_int_row = row
        ws.cell(row=row, column=1, value="New Interest Expense")
        ws.cell(row=row, column=2, value=f"=SUMPRODUCT(B{new_start}:B{new_end},C{new_start}:C{new_end})")
        ws.cell(row=row, column=2).number_format = '#,##0.0'
        row += 1

        savings_row = row
        ws.cell(row=row, column=1, value="Annual Interest Savings")
        ws.cell(row=row, column=2, value=f"=B{old_int_row}-B{new_int_row}")
        ws.cell(row=row, column=2).number_format = '#,##0.0'
        ws.cell(row=row, column=2).font = Font(bold=True)
        ws.cell(row=row, column=2).fill = PatternFill(start_color="90EE90", end_color="90EE90", fill_type="solid")
        row += 1

        ws.cell(row=row, column=1, value="Rate Reduction")
        ws.cell(row=row, column=2, value=f"=(C{old_total_row}-C{new_total_row})*10000")
        ws.cell(row=row, column=2).number_format = '0" bps"'
        row += 3

        # Transaction Costs
        self._add_section_header(ws, "TRANSACTION COSTS", row, 1)
        row += 1

        call_row = row
        ws.cell(row=row, column=1, value="Call Premium / Make-Whole")
        ws.cell(row=row, column=2, value=f"=B{old_total_row}*0.01")
        ws.cell(row=row, column=2).number_format = '#,##0.0'
        self._format_input_cell(ws, row, 2)
        row += 1

        arr_row = row
        ws.cell(row=row, column=1, value="Arrangement Fee (1%)")
        ws.cell(row=row, column=2, value=f"=B{new_total_row}*0.01")
        ws.cell(row=row, column=2).number_format = '#,##0.0'
        row += 1

        legal_row = row
        ws.cell(row=row, column=1, value="Legal & Advisory")
        ws.cell(row=row, column=2, value=0.5)
        ws.cell(row=row, column=2).number_format = '#,##0.0'
        self._format_input_cell(ws, row, 2)
        row += 1

        total_costs_row = row
        ws.cell(row=row, column=1, value="Total Transaction Costs")
        ws.cell(row=row, column=2, value=f"=B{call_row}+B{arr_row}+B{legal_row}")
        ws.cell(row=row, column=2).number_format = '#,##0.0'
        ws.cell(row=row, column=2).font = Font(bold=True)
        row += 2

        # Payback
        ws.cell(row=row, column=1, value="Payback Period (years)")
        ws.cell(row=row, column=2, value=f"=IFERROR(B{total_costs_row}/B{savings_row},999)")
        ws.cell(row=row, column=2).number_format = '0.0'
        ws.cell(row=row, column=2).font = Font(bold=True)
        ws.cell(row=row, column=3, value=f'=IF(B{row}<=2,"✓ Attractive",IF(B{row}<=3,"⚠ Marginal","✗ Not recommended"))')
        ws.cell(row=row, column=3).font = Font(italic=True)

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

        cap_start = row
        for investor in cap_table:
            ws.cell(row=row, column=1, value=investor['investor'])
            ws.cell(row=row, column=2, value=investor['invested'])
            ws.cell(row=row, column=2).number_format = '#,##0.0'
            self._format_input_cell(ws, row, 2)
            ws.cell(row=row, column=3, value=investor['ownership'])
            ws.cell(row=row, column=3).number_format = '0.0%'
            ws.cell(row=row, column=4, value=investor['type'])
            row += 1
        cap_end = row - 1

        row += 1
        ti_row = row  # Total Invested row
        ws.cell(row=row, column=1, value="Total")
        ws.cell(row=row, column=2, value=f"=SUM(B{cap_start}:B{cap_end})")
        ws.cell(row=row, column=2).number_format = '#,##0.0'
        ws.cell(row=row, column=2).font = Font(bold=True)
        ws.cell(row=row, column=3, value=f"=SUM(C{cap_start}:C{cap_end})")
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

        pref_row = row
        ws.cell(row=row, column=1, value="Preferred Return (Hurdle)")
        ws.cell(row=row, column=2, value=waterfall_terms['preferred_return'])
        ws.cell(row=row, column=2).number_format = '0.0%'
        self._format_input_cell(ws, row, 2)
        row += 1

        ws.cell(row=row, column=1, value="GP Catch-Up")
        ws.cell(row=row, column=2, value=waterfall_terms['catch_up_pct'])
        ws.cell(row=row, column=2).number_format = '0%'
        row += 1

        carry_row = row
        ws.cell(row=row, column=1, value="Carried Interest")
        ws.cell(row=row, column=2, value=waterfall_terms['carried_interest'])
        ws.cell(row=row, column=2).number_format = '0.0%'
        self._format_input_cell(ws, row, 2)
        row += 1

        ws.cell(row=row, column=1, value="GP Commitment")
        ws.cell(row=row, column=2, value=waterfall_terms['gp_commitment'])
        ws.cell(row=row, column=2).number_format = '0.0%'
        row += 1

        hold_row = row
        ws.cell(row=row, column=1, value="Hold Period (years)")
        ws.cell(row=row, column=2, value=5)
        self._format_input_cell(ws, row, 2)
        row += 1

        # Preferred Return Threshold = Invested × (1+hurdle)^hold
        pt_row = row
        ws.cell(row=row, column=1, value="Pref Return Threshold")
        ws.cell(row=row, column=2, value=f"=B{ti_row}*((1+B{pref_row})^B{hold_row})")
        ws.cell(row=row, column=2).number_format = '#,##0.0'
        row += 2

        # Exit Scenarios Waterfall
        self._add_section_header(ws, "WATERFALL BY EXIT VALUE", row, 1)
        row += 1

        # Exit values as numbers for formula references
        ev_row = row
        ws.cell(row=row, column=1, value="Exit Equity Value ($M)")
        exit_values = [200, 300, 400, 500, 600]
        for i, ev in enumerate(exit_values):
            ws.cell(row=row, column=2 + i, value=ev)
            ws.cell(row=row, column=2 + i).number_format = '#,##0'
            self._format_input_cell(ws, row, 2 + i)
        self._format_header_row(ws, row, 1, 6)
        row += 1

        # Reference shortcuts for formulas
        ti = f"$B${ti_row}"    # Total Invested
        pt = f"$B${pt_row}"    # Pref Threshold
        cr = f"$B${carry_row}" # Carry %

        # Return of Capital
        ws.cell(row=row, column=1, value="Return of Capital")
        for i in range(5):
            c = get_column_letter(2 + i)
            ws.cell(row=row, column=2 + i, value=f"=MIN({c}${ev_row},{ti})")
            ws.cell(row=row, column=2 + i).number_format = '#,##0.0'
        row += 1

        # Preferred Return (to hurdle)
        ws.cell(row=row, column=1, value="Preferred Return (to hurdle)")
        for i in range(5):
            c = get_column_letter(2 + i)
            ws.cell(row=row, column=2 + i, value=f"=MIN(MAX(0,{c}${ev_row}-{ti}),{pt}-{ti})")
            ws.cell(row=row, column=2 + i).number_format = '#,##0.0'
        row += 1

        # GP Catch-Up
        ws.cell(row=row, column=1, value="GP Catch-Up")
        for i in range(5):
            c = get_column_letter(2 + i)
            ws.cell(row=row, column=2 + i,
                    value=f"=IF({c}${ev_row}>{pt},({c}${ev_row}-{ti})*{cr},0)")
            ws.cell(row=row, column=2 + i).number_format = '#,##0.0'
        row += 1

        # Remaining (80/20 split)
        ws.cell(row=row, column=1, value="Remaining (80/20 split)")
        for i in range(5):
            c = get_column_letter(2 + i)
            ws.cell(row=row, column=2 + i,
                    value=f"=IF({c}${ev_row}>{pt},MAX(0,{c}${ev_row}-{pt})*0.8,0)")
            ws.cell(row=row, column=2 + i).number_format = '#,##0.0'
        row += 1

        # Total to LPs
        lp_row = row
        ws.cell(row=row, column=1, value="Total to LPs")
        ws.cell(row=row, column=1).font = Font(bold=True)
        for i in range(5):
            c = get_column_letter(2 + i)
            ws.cell(row=row, column=2 + i,
                    value=f"=IF({c}${ev_row}<={pt},{c}${ev_row},{c}${ev_row}-({c}${ev_row}-{ti})*{cr})")
            ws.cell(row=row, column=2 + i).number_format = '#,##0.0'
            ws.cell(row=row, column=2 + i).font = Font(bold=True)
            ws.cell(row=row, column=2 + i).fill = PatternFill(start_color="90EE90", end_color="90EE90", fill_type="solid")
        row += 1

        # Total to GP (Carry)
        gp_row = row
        ws.cell(row=row, column=1, value="Total to GP (Carry)")
        for i in range(5):
            c = get_column_letter(2 + i)
            ws.cell(row=row, column=2 + i,
                    value=f"=IF({c}${ev_row}<={pt},0,({c}${ev_row}-{ti})*{cr})")
            ws.cell(row=row, column=2 + i).number_format = '#,##0.0'
        row += 1

        # LP MOIC
        ws.cell(row=row, column=1, value="LP MOIC")
        ws.cell(row=row, column=1).font = Font(bold=True)
        for i in range(5):
            c = get_column_letter(2 + i)
            ws.cell(row=row, column=2 + i, value=f"=IFERROR({c}{lp_row}/{ti},0)")
            ws.cell(row=row, column=2 + i).number_format = '0.00x'
            ws.cell(row=row, column=2 + i).font = Font(bold=True)
        row += 1

        # GP Carry ($M)
        ws.cell(row=row, column=1, value="GP Carry ($M)")
        for i in range(5):
            c = get_column_letter(2 + i)
            ws.cell(row=row, column=2 + i, value=f"={c}{gp_row}")
            ws.cell(row=row, column=2 + i).number_format = '#,##0.0'

        # Column widths
        ws.column_dimensions['A'].width = 25
        for col_letter in ['B', 'C', 'D', 'E', 'F']:
            ws.column_dimensions[col_letter].width = 12

        self.cell_map['cap_table_waterfall'] = {
            'total_invested_row': ti_row,
            'pref_return_row': pref_row,
            'carry_row': carry_row,
            'pref_threshold_row': pt_row,
            'lp_total_row': lp_row,
            'gp_total_row': gp_row,
        }

        return self

    # ============================================================
    # MODULE: SPONSOR ECONOMICS
    # ============================================================

    def add_sponsor_economics(self, data: Dict = None) -> 'ExcelModelGenerator':
        """Add Sponsor Economics with live Excel formulas."""
        ws = self.wb.create_sheet("Sponsor Economics")
        self.sheets_created.append("Sponsor Economics")

        a = self.assumptions
        data = data or {}

        # Title
        self._add_title(ws, f"{self.company_name} - Sponsor Economics Analysis", 1, 1)

        # ── FUND PARAMETERS (rows 3-10) — all inputs ──
        self._add_section_header(ws, "FUND PARAMETERS", 3, 1)

        fund_params = data.get('fund_params', {
            'fund_size': 500.0, 'gp_commitment': 0.02, 'management_fee': 0.02,
            'carried_interest': 0.20, 'hurdle_rate': 0.08,
            'fund_life': 10, 'investment_period': 5,
        })

        fund_inputs = [
            (4, "Fund Size ($M)", fund_params['fund_size'], '#,##0'),
            (5, "GP Commitment", fund_params['gp_commitment'], '0.0%'),
            (6, "Management Fee", fund_params['management_fee'], '0.0%'),
            (7, "Carried Interest", fund_params['carried_interest'], '0.0%'),
            (8, "Hurdle Rate", fund_params['hurdle_rate'], '0.0%'),
            (9, "Fund Life (years)", fund_params['fund_life'], '0'),
            (10, "Investment Period (years)", fund_params['investment_period'], '0'),
        ]
        for row, name, value, fmt in fund_inputs:
            ws.cell(row=row, column=1, value=name)
            ws.cell(row=row, column=2, value=value)
            ws.cell(row=row, column=2).number_format = fmt
            self._format_input_cell(ws, row, 2)

        # ── DEAL PARAMETERS (rows 12-16) — inputs ──
        self._add_section_header(ws, "DEAL PARAMETERS", 12, 1)

        deal_params = data.get('deal_params', {
            'deal_equity': 150.0, 'deal_pct_of_fund': 0.30,
            'entry_moic': 2.5, 'hold_period': 5,
        })

        ws.cell(row=13, column=1, value="Deal Equity Investment ($M)")
        ws.cell(row=13, column=2, value=deal_params['deal_equity'])
        ws.cell(row=13, column=2).number_format = '#,##0.0'
        self._format_input_cell(ws, 13, 2)

        ws.cell(row=14, column=1, value="% of Fund")
        ws.cell(row=14, column=2, value="=IFERROR(B13/B4,0)")
        ws.cell(row=14, column=2).number_format = '0.0%'

        ws.cell(row=15, column=1, value="Expected MOIC")
        ws.cell(row=15, column=2, value=deal_params['entry_moic'])
        ws.cell(row=15, column=2).number_format = '0.0x'
        self._format_input_cell(ws, 15, 2)

        ws.cell(row=16, column=1, value="Hold Period (years)")
        ws.cell(row=16, column=2, value=deal_params['hold_period'])
        self._format_input_cell(ws, 16, 2)

        # ── GP ECONOMICS FROM THIS DEAL (rows 18-28) — formulas ──
        self._add_section_header(ws, "GP ECONOMICS FROM THIS DEAL", 18, 1)

        ws.cell(row=19, column=1, value="Deal Investment")
        ws.cell(row=19, column=2, value="=B13")
        ws.cell(row=19, column=2).number_format = '#,##0.0'

        ws.cell(row=20, column=1, value="Deal Proceeds")
        ws.cell(row=20, column=2, value="=B13*B15")
        ws.cell(row=20, column=2).number_format = '#,##0.0'

        ws.cell(row=21, column=1, value="Deal Profit")
        ws.cell(row=21, column=2, value="=B20-B19")
        ws.cell(row=21, column=2).number_format = '#,##0.0'

        ws.cell(row=22, column=1, value="Deal IRR")
        ws.cell(row=22, column=2, value="=IFERROR(B15^(1/B16)-1,0)")
        ws.cell(row=22, column=2).number_format = '0.0%'
        ws.cell(row=22, column=2).font = Font(bold=True)

        ws.cell(row=24, column=1, value="GP Carried Interest")
        ws.cell(row=24, column=2, value="=B21*B7")
        ws.cell(row=24, column=2).number_format = '#,##0.0'
        ws.cell(row=24, column=2).fill = PatternFill(start_color="90EE90", end_color="90EE90", fill_type="solid")

        ws.cell(row=25, column=1, value="GP Co-Invest Profit")
        ws.cell(row=25, column=2, value="=B13*B5*(B15-1)")
        ws.cell(row=25, column=2).number_format = '#,##0.0'

        ws.cell(row=26, column=1, value="Total GP Economics (this deal)")
        ws.cell(row=26, column=2, value="=B24+B25")
        ws.cell(row=26, column=2).number_format = '#,##0.0'
        ws.cell(row=26, column=2).font = Font(bold=True)

        # ── FUND-LEVEL ECONOMICS (rows 28-40) — formulas ──
        self._add_section_header(ws, "FUND-LEVEL ECONOMICS (ILLUSTRATIVE)", 28, 1)

        ws.cell(row=29, column=1, value="Fund Gross MOIC (assumed)")
        ws.cell(row=29, column=2, value=data.get('fund_gross_moic', 2.0))
        ws.cell(row=29, column=2).number_format = '0.0x'
        self._format_input_cell(ws, 29, 2)

        ws.cell(row=31, column=1, value="")
        ws.cell(row=31, column=2, value="Amount ($M)")
        ws.cell(row=31, column=3, value="% of Fund")
        self._format_header_row(ws, 31, 1, 3)

        ws.cell(row=32, column=1, value="Fund Size (Committed)")
        ws.cell(row=32, column=2, value="=B4")
        ws.cell(row=32, column=2).number_format = '#,##0.0'

        ws.cell(row=33, column=1, value="Gross Proceeds")
        ws.cell(row=33, column=2, value="=B4*B29")
        ws.cell(row=33, column=2).number_format = '#,##0.0'

        ws.cell(row=34, column=1, value="Gross Profit")
        ws.cell(row=34, column=2, value="=B33-B32")
        ws.cell(row=34, column=2).number_format = '#,##0.0'
        ws.cell(row=34, column=3, value="=IFERROR(B34/B32,0)")
        ws.cell(row=34, column=3).number_format = '0.0%'

        # Management Fees = Fund × Fee% × InvPeriod + Fund × 0.5 × Fee% × (Life-InvPeriod)
        ws.cell(row=36, column=1, value="Management Fees (total)")
        ws.cell(row=36, column=2, value="=B4*B6*B10+B4*0.5*B6*(B9-B10)")
        ws.cell(row=36, column=2).number_format = '#,##0.0'
        ws.cell(row=36, column=3, value="=IFERROR(B36/B32,0)")
        ws.cell(row=36, column=3).number_format = '0.0%'

        # Carry = Profit × Carry% (if hurdle met)
        ws.cell(row=37, column=1, value="Carried Interest")
        ws.cell(row=37, column=2, value="=IF(B33>B4*(1+B8)^B9,B34*B7,0)")
        ws.cell(row=37, column=2).number_format = '#,##0.0'
        ws.cell(row=37, column=3, value="=IFERROR(B37/B32,0)")
        ws.cell(row=37, column=3).number_format = '0.0%'

        ws.cell(row=38, column=1, value="GP Co-Invest Profit")
        ws.cell(row=38, column=2, value="=B4*B5*(B29-1)")
        ws.cell(row=38, column=2).number_format = '#,##0.0'
        ws.cell(row=38, column=3, value="=IFERROR(B38/B32,0)")
        ws.cell(row=38, column=3).number_format = '0.0%'

        ws.cell(row=40, column=1, value="Total GP Revenue")
        ws.cell(row=40, column=2, value="=B36+B37+B38")
        ws.cell(row=40, column=2).number_format = '#,##0.0'
        ws.cell(row=40, column=2).font = Font(bold=True)
        ws.cell(row=40, column=2).fill = PatternFill(start_color="FFFF99", end_color="FFFF99", fill_type="solid")

        # Column widths
        ws.column_dimensions['A'].width = 35
        ws.column_dimensions['B'].width = 15
        ws.column_dimensions['C'].width = 15

        self.cell_map['sponsor_economics'] = {
            'fund_size': 'B4',
            'carry_pct': 'B7',
            'deal_equity': 'B13',
            'deal_moic': 'B15',
            'deal_irr': 'B22',
            'gp_carry': 'B24',
            'total_gp_deal': 'B26',
            'total_gp_fund': 'B40',
        }

        return self

    # ============================================================
    # TRANSACTION STRUCTURE & EXECUTION MODULES
    # ============================================================

    def add_addon_analysis(self, data: Dict = None) -> 'ExcelModelGenerator':
        """Add Add-on/Bolt-on Acquisition analysis with formulas."""
        ws = self.wb.create_sheet("Add-on Analysis")
        self.sheets_created.append("Add-on Analysis")
        a = self.assumptions
        data = data or {}

        self._add_title(ws, f"{self.company_name} - Add-on Acquisition Analysis", 1, 1)

        # Platform (rows 3-5)
        self._add_section_header(ws, "PLATFORM COMPANY", 3, 1)
        ws.cell(row=4, column=1, value="Platform EBITDA")
        ws.cell(row=4, column=2, value=f"='Assumptions'!B6")
        ws.cell(row=4, column=2).number_format = '#,##0.0'
        ws.cell(row=5, column=1, value="Entry Multiple")
        ws.cell(row=5, column=2, value=f"='Assumptions'!B7")
        ws.cell(row=5, column=2).number_format = '0.0x'

        # Add-ons (rows 7+)
        self._add_section_header(ws, "ADD-ON TARGETS", 7, 1)
        headers = ["Target", "EBITDA", "Multiple", "EV", "Synergies"]
        for i, h in enumerate(headers):
            ws.cell(row=8, column=1+i, value=h)
        self._format_header_row(ws, 8, 1, 5)

        addons = data.get('addons', [
            {'name': 'Target A', 'ebitda': 5.0, 'multiple': 5.5, 'synergies': 0.8},
            {'name': 'Target B', 'ebitda': 3.0, 'multiple': 5.0, 'synergies': 0.5},
        ])
        addon_start = 9
        for i, addon in enumerate(addons):
            row = addon_start + i
            ws.cell(row=row, column=1, value=addon['name'])
            ws.cell(row=row, column=2, value=addon['ebitda'])
            ws.cell(row=row, column=2).number_format = '#,##0.0'
            self._format_input_cell(ws, row, 2)
            ws.cell(row=row, column=3, value=addon['multiple'])
            ws.cell(row=row, column=3).number_format = '0.0x'
            self._format_input_cell(ws, row, 3)
            ws.cell(row=row, column=4, value=f"=B{row}*C{row}")
            ws.cell(row=row, column=4).number_format = '#,##0.0'
            ws.cell(row=row, column=5, value=addon['synergies'])
            ws.cell(row=row, column=5).number_format = '#,##0.0'
            self._format_input_cell(ws, row, 5)
        addon_end = addon_start + len(addons) - 1

        pf_row = addon_end + 2
        ws.cell(row=pf_row, column=1, value="Pro Forma EBITDA")
        ws.cell(row=pf_row, column=2,
                value=f"=B4+SUM(B{addon_start}:B{addon_end})+SUM(E{addon_start}:E{addon_end})")
        ws.cell(row=pf_row, column=2).number_format = '#,##0.0'
        ws.cell(row=pf_row, column=2).font = Font(bold=True)
        ws.cell(row=pf_row, column=2).fill = PatternFill(start_color="90EE90", end_color="90EE90", fill_type="solid")

        ws.cell(row=pf_row + 1, column=1, value="Multiple Arbitrage")
        ws.cell(row=pf_row + 1, column=2,
                value=f"=B5-IFERROR(SUM(D{addon_start}:D{addon_end})/SUM(B{addon_start}:B{addon_end}),0)")
        ws.cell(row=pf_row + 1, column=2).number_format = '0.0x'
        ws.cell(row=pf_row + 1, column=2).font = Font(bold=True, color="008000")

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
        syn_start = row
        for syn in synergies:
            ws.cell(row=row, column=1, value=syn['name'])
            ws.cell(row=row, column=2, value=syn['y1'])
            ws.cell(row=row, column=3, value=syn['y2'])
            ws.cell(row=row, column=4, value=syn['y3'])
            ws.cell(row=row, column=5, value=f"=D{row}")  # Run-rate = Year 3
            ws.cell(row=row, column=6, value=syn['prob'])
            ws.cell(row=row, column=6).number_format = '0%'
            for c in [2,3,4]: self._format_input_cell(ws, row, c)
            for c in [2,3,4,5]: ws.cell(row=row, column=c).number_format = '#,##0.0'
            row += 1
        syn_end = row - 1

        row += 1
        ws.cell(row=row, column=1, value="Total Cost Synergies")
        for c in [2, 3, 4, 5]:
            cl = get_column_letter(c)
            ws.cell(row=row, column=c, value=f"=SUM({cl}{syn_start}:{cl}{syn_end})")
            ws.cell(row=row, column=c).number_format = '#,##0.0'
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
        cost_start = row
        for cost in costs:
            ws.cell(row=row, column=1, value=cost['name'])
            ws.cell(row=row, column=2, value=cost['allocated'])
            ws.cell(row=row, column=3, value=cost['standalone'])
            ws.cell(row=row, column=4, value=f"=C{row}-B{row}")  # Variance formula
            for c in [2,3]: self._format_input_cell(ws, row, c)
            for c in [2,3,4]: ws.cell(row=row, column=c).number_format = '#,##0.0'
            row += 1
        cost_end = row - 1

        row += 1
        ws.cell(row=row, column=1, value="Dis-synergies")
        ws.cell(row=row, column=4, value=f"=SUM(D{cost_start}:D{cost_end})")
        ws.cell(row=row, column=4).number_format = '#,##0.0'
        ws.cell(row=row, column=4).font = Font(bold=True)

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

        # Inputs (rows 4-5)
        ws.cell(row=4, column=1, value="Upfront Consideration")
        ws.cell(row=4, column=2, value=data.get('upfront', 150.0))
        ws.cell(row=4, column=2).number_format = '#,##0.0'
        self._format_input_cell(ws, 4, 2)
        ws.cell(row=5, column=1, value="Maximum Earnout")
        ws.cell(row=5, column=2, value=data.get('max_earnout', 50.0))
        ws.cell(row=5, column=2).number_format = '#,##0.0'
        self._format_input_cell(ws, 5, 2)

        self._add_section_header(ws, "SCENARIO ANALYSIS", 7, 1)
        headers = ["Scenario", "Prob.", "Payout", "Weighted"]
        for i, h in enumerate(headers):
            ws.cell(row=8, column=1+i, value=h)
        self._format_header_row(ws, 8, 1, 4)

        scenarios = data.get('scenarios', [
            {'name': 'Exceed', 'prob': 0.20, 'payout': 50.0},
            {'name': 'Meet', 'prob': 0.45, 'payout': 35.0},
            {'name': 'Partial', 'prob': 0.25, 'payout': 15.0},
            {'name': 'Miss', 'prob': 0.10, 'payout': 0.0},
        ])
        sc_start = 9
        for i, sc in enumerate(scenarios):
            row = sc_start + i
            ws.cell(row=row, column=1, value=sc['name'])
            ws.cell(row=row, column=2, value=sc['prob'])
            ws.cell(row=row, column=2).number_format = '0%'
            self._format_input_cell(ws, row, 2)
            ws.cell(row=row, column=3, value=sc['payout'])
            ws.cell(row=row, column=3).number_format = '#,##0.0'
            self._format_input_cell(ws, row, 3)
            ws.cell(row=row, column=4, value=f"=B{row}*C{row}")  # Weighted formula
            ws.cell(row=row, column=4).number_format = '#,##0.0'
        sc_end = sc_start + len(scenarios) - 1

        exp_row = sc_end + 2
        ws.cell(row=exp_row, column=1, value="Expected Earnout")
        ws.cell(row=exp_row, column=4, value=f"=SUM(D{sc_start}:D{sc_end})")
        ws.cell(row=exp_row, column=4).number_format = '#,##0.0'
        ws.cell(row=exp_row, column=4).font = Font(bold=True)

        ws.cell(row=exp_row + 1, column=1, value="Effective Purchase Price")
        ws.cell(row=exp_row + 1, column=4, value=f"=B4+D{exp_row}")
        ws.cell(row=exp_row + 1, column=4).number_format = '#,##0.0'
        ws.cell(row=exp_row + 1, column=4).font = Font(bold=True)
        ws.cell(row=exp_row + 1, column=4).fill = PatternFill(start_color="90EE90", end_color="90EE90", fill_type="solid")

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

        self._add_section_header(ws, "ASSETS ACQUIRED AT FAIR VALUE", 3, 1)
        headers = ["Asset", "Book", "Step-Up", "Fair Value"]
        row = 4
        for i, h in enumerate(headers):
            ws.cell(row=row, column=1+i, value=h)
        self._format_header_row(ws, row, 1, 4)

        assets = data.get('assets', [
            {'name': 'Tangible assets', 'book': 50.0, 'stepup': 10.0},
            {'name': 'Customer relationships', 'book': 0.0, 'stepup': 60.0},
            {'name': 'Technology/IP', 'book': 5.0, 'stepup': 30.0},
            {'name': 'Trade name', 'book': 0.0, 'stepup': 15.0},
        ])
        asset_start = 5
        for i, asset in enumerate(assets):
            row = asset_start + i
            ws.cell(row=row, column=1, value=asset['name'])
            ws.cell(row=row, column=2, value=asset['book'])
            ws.cell(row=row, column=3, value=asset['stepup'])
            ws.cell(row=row, column=4, value=f"=B{row}+C{row}")  # FV formula
            for c in [2,3]: self._format_input_cell(ws, row, c)
            for c in [2,3,4]: ws.cell(row=row, column=c).number_format = '#,##0.0'
        asset_end = asset_start + len(assets) - 1

        liabilities = data.get('liabilities', 30.0)
        t_row = asset_end + 2
        ws.cell(row=t_row, column=1, value="Total Identifiable Assets")
        ws.cell(row=t_row, column=4, value=f"=SUM(D{asset_start}:D{asset_end})")
        ws.cell(row=t_row, column=4).number_format = '#,##0.0'

        ws.cell(row=t_row + 1, column=1, value="Less: Liabilities")
        ws.cell(row=t_row + 1, column=4, value=-liabilities)
        ws.cell(row=t_row + 1, column=4).number_format = '(#,##0.0)'
        self._format_input_cell(ws, t_row + 1, 4)

        ws.cell(row=t_row + 2, column=1, value="Net Identifiable Assets")
        ws.cell(row=t_row + 2, column=4, value=f"=D{t_row}+D{t_row+1}")
        ws.cell(row=t_row + 2, column=4).number_format = '#,##0.0'

        pp_row = t_row + 4
        ws.cell(row=pp_row, column=1, value="Purchase Price")
        ws.cell(row=pp_row, column=4, value=f"='Assumptions'!B6*'Assumptions'!B7")
        ws.cell(row=pp_row, column=4).number_format = '#,##0.0'

        ws.cell(row=pp_row + 1, column=1, value="Goodwill")
        ws.cell(row=pp_row + 1, column=4, value=f"=D{pp_row}-D{t_row+2}")
        ws.cell(row=pp_row + 1, column=4).number_format = '#,##0.0'
        ws.cell(row=pp_row + 1, column=4).font = Font(bold=True)
        ws.cell(row=pp_row + 1, column=4).fill = PatternFill(start_color="FFFF99", end_color="FFFF99", fill_type="solid")

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
        su = self.cell_map.get('sources_uses', {})
        su_equity = su.get('sponsor_equity', None)
        if su_equity:
            ws.cell(row=row, column=2, value=f"='Sources & Uses'!{su_equity}")
        else:
            ws.cell(row=row, column=2, value=entry_equity)
        ws.cell(row=row, column=2).number_format = '#,##0.0'
        self._format_input_cell(ws, row, 2)
        row += 2

        attribution = data.get('attribution', [
            {'name': 'Revenue Growth', 'value': value_created * 0.35},
            {'name': 'Margin Improvement', 'value': value_created * 0.25},
            {'name': 'Multiple Expansion', 'value': value_created * 0.15},
            {'name': 'Debt Paydown', 'value': value_created * 0.20},
            {'name': 'Add-on M&A', 'value': value_created * 0.05},
        ])
        attr_start = row
        attr_end = row + len(attribution) - 1
        for attr in attribution:
            ws.cell(row=row, column=1, value=attr['name'])
            ws.cell(row=row, column=2, value=attr['value'])
            ws.cell(row=row, column=2).number_format = '#,##0.0'
            self._format_input_cell(ws, row, 2)
            ws.cell(row=row, column=3, value=f"=IFERROR(B{row}/SUM(B${attr_start}:B${attr_end}),0)")
            ws.cell(row=row, column=3).number_format = '0%'
            row += 1

        row += 1
        ws.cell(row=row, column=1, value="Exit Equity Value")
        ws.cell(row=row, column=2, value=f"=B4+SUM(B{attr_start}:B{attr_end})")
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
        init_start = row
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
            row += 1
        init_end = row - 1

        row += 1
        ws.cell(row=row, column=1, value="Total Value at Stake")
        ws.cell(row=row, column=5, value=f"=SUM(E{init_start}:E{init_end})")
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
        cat_start = row
        for cat in categories:
            ws.cell(row=row, column=1, value=cat['name'])
            ws.cell(row=row, column=2, value=cat['score'])
            self._format_input_cell(ws, row, 2)
            ws.cell(row=row, column=3, value=cat['weight'])
            ws.cell(row=row, column=3).number_format = '0%'
            self._format_input_cell(ws, row, 3)
            ws.cell(row=row, column=4, value=f"=B{row}*C{row}")
            ws.cell(row=row, column=4).number_format = '0.0'
            color = "90EE90" if cat['score'] >= 4 else "FFFF99" if cat['score'] >= 3 else "FFB6C1"
            ws.cell(row=row, column=2).fill = PatternFill(start_color=color, end_color=color, fill_type="solid")
            row += 1
        cat_end = row - 1

        row += 1
        ws.cell(row=row, column=1, value="Overall Score")
        ws.cell(row=row, column=4, value=f"=SUM(D{cat_start}:D{cat_end})")
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

        self._add_section_header(ws, "MIP STRUCTURE", 3, 1)
        ws.cell(row=4, column=1, value="MIP Pool (% of equity)")
        ws.cell(row=4, column=2, value=mip_pool)
        ws.cell(row=4, column=2).number_format = '0.0%'
        self._format_input_cell(ws, 4, 2)

        # Entry Equity from Assumptions
        ws.cell(row=5, column=1, value="Entry Equity ($M)")
        su = self.cell_map.get('sources_uses', {})
        su_equity = su.get('sponsor_equity', None)
        if su_equity:
            ws.cell(row=5, column=2, value=f"='Sources & Uses'!{su_equity}")
        else:
            ws.cell(row=5, column=2, value="='Assumptions'!B6*'Assumptions'!B7*0.55")
        ws.cell(row=5, column=2).number_format = '#,##0.0'

        ws.cell(row=6, column=1, value="MIP Pool Value ($M)")
        ws.cell(row=6, column=2, value="=B5*B4")
        ws.cell(row=6, column=2).number_format = '#,##0.0'

        self._add_section_header(ws, "PAYOUT BY EXIT MOIC", 8, 1)
        headers = ["Exit MOIC", "Exit Equity", "MIP Value", "CEO (35%)"]
        for i, h in enumerate(headers):
            ws.cell(row=9, column=1+i, value=h)
        self._format_header_row(ws, 9, 1, 4)

        row = 10
        for moic in [1.5, 2.0, 2.5, 3.0]:
            ws.cell(row=row, column=1, value=moic)
            ws.cell(row=row, column=1).number_format = '0.0x'
            ws.cell(row=row, column=2, value=f"=$B$5*A{row}")     # Exit Equity
            ws.cell(row=row, column=3, value=f"=B{row}*$B$4")     # MIP Value
            ws.cell(row=row, column=4, value=f"=C{row}*0.35")     # CEO share
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

        ws.cell(row=3, column=1, value="Platform EBITDA")
        ws.cell(row=3, column=3, value=f"='Assumptions'!B6")
        ws.cell(row=3, column=3).number_format = '#,##0.0'

        self._add_section_header(ws, "ACQUISITION SCHEDULE", 4, 1)
        headers = ["Year", "Target", "EBITDA", "Multiple", "EV"]
        for i, h in enumerate(headers):
            ws.cell(row=5, column=1+i, value=h)
        self._format_header_row(ws, 5, 1, 5)

        acquisitions = data.get('acquisitions', [
            {'year': 1, 'name': 'Tuck-in A', 'ebitda': 3.0, 'multiple': 5.0},
            {'year': 2, 'name': 'Regional B', 'ebitda': 5.0, 'multiple': 5.5},
            {'year': 3, 'name': 'Strategic C', 'ebitda': 8.0, 'multiple': 6.0},
        ])
        acq_start = 6
        for i, acq in enumerate(acquisitions):
            row = acq_start + i
            ws.cell(row=row, column=1, value=acq['year'])
            ws.cell(row=row, column=2, value=acq['name'])
            ws.cell(row=row, column=3, value=acq['ebitda'])
            ws.cell(row=row, column=3).number_format = '#,##0.0'
            self._format_input_cell(ws, row, 3)
            ws.cell(row=row, column=4, value=acq['multiple'])
            ws.cell(row=row, column=4).number_format = '0.0x'
            self._format_input_cell(ws, row, 4)
            ws.cell(row=row, column=5, value=f"=C{row}*D{row}")
            ws.cell(row=row, column=5).number_format = '#,##0.0'
        acq_end = acq_start + len(acquisitions) - 1

        pf_row = acq_end + 2
        ws.cell(row=pf_row, column=1, value="Pro Forma EBITDA")
        ws.cell(row=pf_row, column=3, value=f"=C3+SUM(C{acq_start}:C{acq_end})")
        ws.cell(row=pf_row, column=3).number_format = '#,##0.0'
        ws.cell(row=pf_row, column=3).font = Font(bold=True)
        ws.cell(row=pf_row, column=3).fill = PatternFill(start_color="90EE90", end_color="90EE90", fill_type="solid")

        ws.cell(row=pf_row + 1, column=1, value="Blended Acquisition Multiple")
        ws.cell(row=pf_row + 1, column=4,
                value=f"=IFERROR(SUM(E{acq_start}:E{acq_end})/SUM(C{acq_start}:C{acq_end}),0)")
        ws.cell(row=pf_row + 1, column=4).number_format = '0.0x'
        ws.cell(row=pf_row + 1, column=4).font = Font(bold=True)

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

        self._add_section_header(ws, "STEP-UP BENEFIT (338(h)(10))", 3, 1)

        ws.cell(row=4, column=1, value="Purchase Price")
        ws.cell(row=4, column=2, value=f"='Assumptions'!B6*'Assumptions'!B7")
        ws.cell(row=4, column=2).number_format = '#,##0.0'

        ws.cell(row=5, column=1, value="Existing Tax Basis")
        ws.cell(row=5, column=2, value=data.get('tax_basis', a.ltm_ebitda * a.entry_multiple * 0.30))
        ws.cell(row=5, column=2).number_format = '#,##0.0'
        self._format_input_cell(ws, 5, 2)

        ws.cell(row=6, column=1, value="Step-Up Amount")
        ws.cell(row=6, column=2, value="=B4-B5")
        ws.cell(row=6, column=2).number_format = '#,##0.0'
        ws.cell(row=6, column=2).font = Font(bold=True)

        ws.cell(row=8, column=1, value="Amortization Period (years)")
        ws.cell(row=8, column=2, value=15)
        self._format_input_cell(ws, 8, 2)

        ws.cell(row=9, column=1, value="Discount Rate")
        ws.cell(row=9, column=2, value=0.10)
        ws.cell(row=9, column=2).number_format = '0.0%'
        self._format_input_cell(ws, 9, 2)

        ws.cell(row=10, column=1, value="Tax Rate")
        ws.cell(row=10, column=2, value=f"='Assumptions'!B24")
        ws.cell(row=10, column=2).number_format = '0.0%'

        ws.cell(row=12, column=1, value="Annual Amortization")
        ws.cell(row=12, column=2, value="=B6/B8")
        ws.cell(row=12, column=2).number_format = '#,##0.0'

        ws.cell(row=13, column=1, value="Annual Tax Shield")
        ws.cell(row=13, column=2, value="=B12*B10")
        ws.cell(row=13, column=2).number_format = '#,##0.0'

        # NPV using PV annuity formula: Shield × (1 - (1+r)^-n) / r
        ws.cell(row=14, column=1, value="NPV of Tax Benefit")
        ws.cell(row=14, column=2, value="=B13*(1-(1+B9)^(-B8))/B9")
        ws.cell(row=14, column=2).number_format = '#,##0.0'
        ws.cell(row=14, column=2).font = Font(bold=True)
        ws.cell(row=14, column=2).fill = PatternFill(start_color="90EE90", end_color="90EE90", fill_type="solid")

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
        txn_start = row
        for txn in transactions:
            ws.cell(row=row, column=1, value=txn['name'])
            ws.cell(row=row, column=2, value=txn['1day'])
            ws.cell(row=row, column=2).number_format = '0.0%'
            self._format_input_cell(ws, row, 2)
            ws.cell(row=row, column=3, value=txn['30day'])
            ws.cell(row=row, column=3).number_format = '0.0%'
            self._format_input_cell(ws, row, 3)
            row += 1
        txn_end = row - 1

        row += 1
        ws.cell(row=row, column=1, value="Mean Premium")
        ws.cell(row=row, column=2, value=f"=AVERAGE(B{txn_start}:B{txn_end})")
        ws.cell(row=row, column=2).number_format = '0.0%'
        ws.cell(row=row, column=2).font = Font(bold=True)
        ws.cell(row=row, column=3, value=f"=AVERAGE(C{txn_start}:C{txn_end})")
        ws.cell(row=row, column=3).number_format = '0.0%'
        ws.cell(row=row, column=3).font = Font(bold=True)
        mean_row = row
        row += 3

        unaffected = data.get('unaffected_price', 50.0)
        self._add_section_header(ws, "IMPLIED OFFER PRICE", row, 1)
        row += 1
        ws.cell(row=row, column=1, value="Unaffected Share Price")
        ws.cell(row=row, column=2, value=unaffected)
        ws.cell(row=row, column=2).number_format = '$#,##0.00'
        self._format_input_cell(ws, row, 2)
        price_row = row
        row += 1
        ws.cell(row=row, column=1, value="Selected Premium (30-day)")
        ws.cell(row=row, column=2, value=f"=C{mean_row}")
        ws.cell(row=row, column=2).number_format = '0.0%'
        prem_row = row
        row += 1
        ws.cell(row=row, column=1, value="Implied Offer Price")
        ws.cell(row=row, column=2, value=f"=B{price_row}*(1+B{prem_row})")
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

        # Always add Assumptions sheet first (central input sheet for formulas)
        self.add_assumptions_sheet()

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
    gen.add_assumptions_sheet()
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
    gen.add_assumptions_sheet()
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

    # Assumptions first (central input sheet)
    gen.add_assumptions_sheet()

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
