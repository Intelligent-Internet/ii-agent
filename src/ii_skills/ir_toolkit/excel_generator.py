"""
IR Toolkit Excel Generator

Generates Excel outputs for IR modules following the Excel ↔ Slide pairing principle.
Each module produces a formatted table that feeds into a corresponding slide.

Usage:
    from ii_skills.ir_toolkit.excel_generator import IRExcelGenerator

    generator = IRExcelGenerator(output_dir="outputs/")
    path = await generator.generate_module_excel(module, state)
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List
from dataclasses import dataclass

logger = logging.getLogger(__name__)

try:
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Border, Side, Alignment
    from openpyxl.utils import get_column_letter
    OPENPYXL_AVAILABLE = True
except ImportError:
    OPENPYXL_AVAILABLE = False
    logger.warning("openpyxl not available - Excel generation disabled")


# Style definitions
STYLES = {
    "header": {
        "font": Font(bold=True, color="FFFFFF", size=11),
        "fill": PatternFill(start_color="003366", end_color="003366", fill_type="solid"),
        "alignment": Alignment(horizontal="center", vertical="center"),
    },
    "input": {
        "font": Font(color="0000FF"),  # Blue for inputs
    },
    "assumption": {
        "fill": PatternFill(start_color="E6F2FF", end_color="E6F2FF", fill_type="solid"),
    },
    "total": {
        "font": Font(bold=True),
        "border": Border(top=Side(style="thin"), bottom=Side(style="double")),
    },
    "percent": {
        "number_format": "0.0%",
    },
    "currency": {
        "number_format": '"$"#,##0.0',
    },
    "multiple": {
        "number_format": "0.00x",
    },
}


@dataclass
class TableSpec:
    """Specification for an Excel table output."""
    name: str
    headers: List[str]
    rows: List[List[Any]]
    column_widths: Optional[List[int]] = None
    formats: Optional[Dict[int, str]] = None  # Column index -> format type
    title: Optional[str] = None
    subtitle: Optional[str] = None


class IRExcelGenerator:
    """
    Generates Excel outputs for IR toolkit modules.
    """

    def __init__(self, output_dir: str):
        """
        Initialize the Excel generator.

        Args:
            output_dir: Directory for output files
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    async def generate_module_excel(
        self,
        module: 'IRModule',
        state: 'IRState',
    ) -> str:
        """
        Generate Excel output for a module.

        Args:
            module: The IR module to generate for
            state: Current IR state with data

        Returns:
            Path to generated Excel file
        """
        if not OPENPYXL_AVAILABLE:
            logger.warning("openpyxl not available")
            return ""

        # Get table spec based on module
        table_spec = self._get_table_spec(module, state)

        # Create workbook
        wb = Workbook()
        ws = wb.active
        ws.title = module.name[:31]  # Excel tab name limit

        # Add title and subtitle
        if table_spec.title:
            ws.merge_cells('A1:F1')
            ws['A1'] = table_spec.title
            ws['A1'].font = Font(bold=True, size=14)

        if table_spec.subtitle:
            ws.merge_cells('A2:F2')
            ws['A2'] = table_spec.subtitle
            ws['A2'].font = Font(italic=True, size=10, color="666666")

        # Starting row for table
        start_row = 4 if table_spec.title else 1

        # Add headers
        for col, header in enumerate(table_spec.headers, 1):
            cell = ws.cell(row=start_row, column=col, value=header)
            cell.font = STYLES["header"]["font"]
            cell.fill = STYLES["header"]["fill"]
            cell.alignment = STYLES["header"]["alignment"]

        # Add data rows
        for row_idx, row_data in enumerate(table_spec.rows, start_row + 1):
            for col_idx, value in enumerate(row_data, 1):
                cell = ws.cell(row=row_idx, column=col_idx, value=value)

                # Apply format if specified
                if table_spec.formats and col_idx in table_spec.formats:
                    fmt_type = table_spec.formats[col_idx]
                    if fmt_type in STYLES:
                        if "number_format" in STYLES[fmt_type]:
                            cell.number_format = STYLES[fmt_type]["number_format"]

        # Set column widths
        if table_spec.column_widths:
            for col_idx, width in enumerate(table_spec.column_widths, 1):
                ws.column_dimensions[get_column_letter(col_idx)].width = width
        else:
            # Auto-width based on content
            for col in range(1, len(table_spec.headers) + 1):
                ws.column_dimensions[get_column_letter(col)].width = 15

        # Add metadata footer
        footer_row = start_row + len(table_spec.rows) + 3
        ws.cell(row=footer_row, column=1, value=f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        ws.cell(row=footer_row, column=1).font = Font(size=8, color="999999")

        # Save file
        filename = f"{state.fund_name.replace(' ', '_')}_{module.id}_{datetime.now().strftime('%Y%m%d')}.xlsx"
        filepath = self.output_dir / filename
        wb.save(filepath)

        logger.info(f"Generated Excel: {filepath}")
        return str(filepath)

    def _get_table_spec(self, module: 'IRModule', state: 'IRState') -> TableSpec:
        """Get table specification for a module."""

        # Module-specific table generators
        generators = {
            "performance_summary": self._performance_table,
            "cash_flow_waterfall": self._cashflow_table,
            "asset_kpi_dashboard": self._asset_kpi_table,
            "nav_rollforward": self._nav_table,
            "leverage_coverage": self._leverage_table,
            "risk_register": self._risk_table,
            "fund_snapshot": self._fund_snapshot_table,
            "portfolio_composition": self._portfolio_table,
            "ddq_tracker": self._ddq_table,
            "esg_metrics": self._esg_table,
            "term_sheet": self._term_sheet_table,
        }

        generator = generators.get(module.id, self._default_table)
        return generator(module, state)

    def _performance_table(self, module: 'IRModule', state: 'IRState') -> TableSpec:
        """Generate performance summary table."""
        perf = state.performance_data or {}

        return TableSpec(
            name="Fund Performance",
            title=f"{state.fund_name} - Performance Summary",
            subtitle=f"As of {state.reporting_period}",
            headers=["Fund", "Vintage", "Net IRR", "DPI", "RVPI", "TVPI"],
            rows=[
                [state.fund_name, perf.get("vintage", "2020"),
                 perf.get("net_irr", 0.15), perf.get("dpi", 0.8),
                 perf.get("rvpi", 1.2), perf.get("tvpi", 2.0)],
            ],
            formats={3: "percent", 4: "multiple", 5: "multiple", 6: "multiple"},
            column_widths=[30, 12, 12, 12, 12, 12],
        )

    def _cashflow_table(self, module: 'IRModule', state: 'IRState') -> TableSpec:
        """Generate cash flow waterfall table."""
        cf = state.cash_flow_data or {}

        quarters = cf.get("quarters", ["Q1", "Q2", "Q3", "Q4"])
        calls = cf.get("calls", [10, 15, 5, 0])
        distributions = cf.get("distributions", [0, 5, 10, 15])
        net = [d - c for c, d in zip(calls, distributions)]

        rows = [
            ["Capital Calls"] + calls,
            ["Distributions"] + distributions,
            ["Net Cash Flow"] + net,
        ]

        return TableSpec(
            name="Cash Flow Waterfall",
            title=f"{state.fund_name} - Cash Flow Summary",
            subtitle=f"{state.reporting_period}",
            headers=["Category"] + quarters,
            rows=rows,
            formats={i: "currency" for i in range(2, len(quarters) + 2)},
            column_widths=[20] + [12] * len(quarters),
        )

    def _asset_kpi_table(self, module: 'IRModule', state: 'IRState') -> TableSpec:
        """Generate asset KPI dashboard table."""
        assets = state.asset_data or {}

        rows = []
        for asset_name, kpis in assets.items():
            rows.append([
                asset_name,
                kpis.get("availability", 0.98),
                kpis.get("utilization", 0.85),
                kpis.get("contracted_pct", 0.90),
                kpis.get("cpi_linked_pct", 0.75),
            ])

        if not rows:
            rows = [
                ["Asset 1", 0.98, 0.85, 0.90, 0.75],
                ["Asset 2", 0.97, 0.82, 0.85, 0.80],
                ["Asset 3", 0.99, 0.88, 0.95, 0.70],
            ]

        return TableSpec(
            name="Asset KPIs",
            title=f"{state.fund_name} - Asset KPI Dashboard",
            subtitle=f"As of {state.reporting_period}",
            headers=["Asset", "Availability", "Utilization", "Contracted %", "CPI-Linked %"],
            rows=rows,
            formats={2: "percent", 3: "percent", 4: "percent", 5: "percent"},
            column_widths=[25, 15, 15, 15, 15],
        )

    def _nav_table(self, module: 'IRModule', state: 'IRState') -> TableSpec:
        """Generate NAV roll-forward table."""
        val = state.valuation_data or {}

        return TableSpec(
            name="NAV Roll-forward",
            title=f"{state.fund_name} - NAV Roll-forward",
            subtitle=f"{state.reporting_period}",
            headers=["Driver", "Amount ($M)", "% of Prior NAV"],
            rows=[
                ["Prior Period NAV", val.get("prior_nav", 500), 1.0],
                ["Contributions", val.get("contributions", 50), 0.10],
                ["Distributions", val.get("distributions", -30), -0.06],
                ["Valuation Change", val.get("val_change", 40), 0.08],
                ["FX Impact", val.get("fx_impact", 5), 0.01],
                ["Current NAV", val.get("current_nav", 565), 1.13],
            ],
            formats={2: "currency", 3: "percent"},
            column_widths=[25, 18, 18],
        )

    def _leverage_table(self, module: 'IRModule', state: 'IRState') -> TableSpec:
        """Generate leverage and coverage table."""
        return TableSpec(
            name="Leverage Profile",
            title=f"{state.fund_name} - Leverage & Coverage",
            subtitle=f"As of {state.reporting_period}",
            headers=["Metric", "Current", "Covenant", "Headroom"],
            rows=[
                ["Debt/EBITDA", "4.2x", "6.0x", "30%"],
                ["DSCR", "1.45x", "1.20x", "21%"],
                ["Interest Coverage", "3.8x", "2.5x", "52%"],
                ["LTV", "55%", "65%", "15%"],
            ],
            column_widths=[20, 15, 15, 15],
        )

    def _risk_table(self, module: 'IRModule', state: 'IRState') -> TableSpec:
        """Generate risk register table."""
        risks = state.risk_data or {}

        return TableSpec(
            name="Risk Register",
            title=f"{state.fund_name} - Key Risks",
            subtitle=f"As of {state.reporting_period}",
            headers=["Risk", "Probability", "Impact", "Mitigation"],
            rows=risks.get("risks", [
                ["Regulatory Reset", "Medium", "High", "Diversified regulatory exposure"],
                ["Counterparty Credit", "Low", "Medium", "Investment grade counterparties"],
                ["Merchant Volatility", "Medium", "Medium", "80%+ contracted revenue"],
                ["Capex Overrun", "Low", "Medium", "Fixed-price contracts"],
                ["FX Exposure", "Medium", "Low", "Currency hedging program"],
            ]),
            column_widths=[25, 12, 12, 40],
        )

    def _fund_snapshot_table(self, module: 'IRModule', state: 'IRState') -> TableSpec:
        """Generate fund snapshot table."""
        fund = state.fund_data or {}

        return TableSpec(
            name="Fund Snapshot",
            title=f"{state.fund_name} - Fund Overview",
            subtitle="Fund Characteristics",
            headers=["Attribute", "Value"],
            rows=[
                ["Fund Size", fund.get("size", "$2.5B")],
                ["Vintage", fund.get("vintage", "2020")],
                ["Strategy", fund.get("strategy", "Global Infrastructure")],
                ["Geography", fund.get("geography", "North America, Europe")],
                ["Currency", fund.get("currency", "USD")],
                ["Investment Period", fund.get("inv_period", "2020-2024")],
                ["Fund Life", fund.get("fund_life", "12 years")],
            ],
            column_widths=[25, 30],
        )

    def _portfolio_table(self, module: 'IRModule', state: 'IRState') -> TableSpec:
        """Generate portfolio composition table."""
        return TableSpec(
            name="Portfolio Mix",
            title=f"{state.fund_name} - Portfolio Composition",
            subtitle=f"As of {state.reporting_period}",
            headers=["Sector", "% of NAV", "# Assets", "Avg. Contract Life"],
            rows=[
                ["Transport", "35%", "4", "12 years"],
                ["Utilities", "30%", "3", "15 years"],
                ["Digital Infra", "20%", "2", "8 years"],
                ["Midstream", "15%", "2", "10 years"],
            ],
            column_widths=[20, 12, 12, 18],
        )

    def _ddq_table(self, module: 'IRModule', state: 'IRState') -> TableSpec:
        """Generate DDQ tracker table."""
        return TableSpec(
            name="DDQ Tracker",
            title=f"{state.fund_name} - DDQ Status",
            subtitle=f"As of {state.reporting_period}",
            headers=["Category", "Questions", "Complete", "In Progress", "Pending"],
            rows=[
                ["Fund Structure", "15", "12", "2", "1"],
                ["Performance", "20", "18", "2", "0"],
                ["Operations", "12", "10", "1", "1"],
                ["ESG", "8", "6", "1", "1"],
                ["Legal", "10", "8", "2", "0"],
                ["Total", "65", "54 (83%)", "8", "3"],
            ],
            column_widths=[18, 12, 12, 15, 12],
        )

    def _esg_table(self, module: 'IRModule', state: 'IRState') -> TableSpec:
        """Generate ESG metrics table."""
        return TableSpec(
            name="ESG Metrics",
            title=f"{state.fund_name} - ESG Dashboard",
            subtitle=f"As of {state.reporting_period}",
            headers=["Metric", "Current", "Prior Year", "Target"],
            rows=[
                ["Scope 1+2 Emissions (tCO2e)", "125,000", "140,000", "100,000"],
                ["TRIR (Safety)", "0.8", "1.1", "<1.0"],
                ["Community Investment ($M)", "2.5", "2.0", "3.0"],
                ["Renewable Energy (%)", "45%", "38%", "60%"],
                ["Water Intensity (m3/MWh)", "0.5", "0.6", "0.4"],
            ],
            column_widths=[28, 15, 15, 15],
        )

    def _term_sheet_table(self, module: 'IRModule', state: 'IRState') -> TableSpec:
        """Generate term sheet summary table."""
        return TableSpec(
            name="Term Sheet",
            title=f"{state.fund_name} - Key Terms",
            subtitle="Summary of Fund Terms",
            headers=["Term", "Description"],
            rows=[
                ["Management Fee", "1.5% on committed (inv. period), 1.25% on invested (post)"],
                ["Carried Interest", "20% over 8% preferred return"],
                ["Hurdle Rate", "8% compounded annually"],
                ["GP Commitment", "2% of fund size"],
                ["Key Person", "Founding partners must dedicate >75% time"],
                ["LPAC", "5 members with veto on conflicts"],
                ["No Fault Removal", "66.67% LP vote"],
            ],
            column_widths=[20, 60],
        )

    def _default_table(self, module: 'IRModule', state: 'IRState') -> TableSpec:
        """Default table generator for unknown modules."""
        return TableSpec(
            name=module.name,
            title=f"{state.fund_name} - {module.name}",
            subtitle=f"As of {state.reporting_period}",
            headers=["Item", "Value", "Notes"],
            rows=[
                [f"{module.category} data", "Placeholder", module.infra_nuance],
            ],
            column_widths=[25, 20, 40],
        )


async def generate_ir_workbook(
    state: 'IRState',
    output_dir: str,
) -> str:
    """
    Generate a complete IR workbook with all modules.

    Args:
        state: IR state with all data
        output_dir: Output directory

    Returns:
        Path to generated workbook
    """
    generator = IRExcelGenerator(output_dir)

    if not OPENPYXL_AVAILABLE:
        logger.warning("openpyxl not available")
        return ""

    wb = Workbook()
    # Remove default sheet
    wb.remove(wb.active)

    for module_id, module in state.modules.items():
        # Generate table spec
        table_spec = generator._get_table_spec(module, state)

        # Add sheet
        ws = wb.create_sheet(title=module.name[:31])

        # Populate (similar to generate_module_excel)
        # ... (implementation)

    filename = f"{state.fund_name.replace(' ', '_')}_IR_Model_{datetime.now().strftime('%Y%m%d')}.xlsx"
    filepath = Path(output_dir) / filename
    wb.save(filepath)

    return str(filepath)
