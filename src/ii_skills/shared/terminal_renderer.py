"""
Terminal Model Renderer — display LBO model outputs directly in the terminal.

Reads generated Excel workbooks (openpyxl) and renders key financial metrics
as formatted ASCII tables using the `rich` library.

No Tier 1/Tier 2 files are modified — this is a pure read-only renderer.

Usage:
    from ii_skills.shared.terminal_renderer import TerminalModelRenderer

    renderer = TerminalModelRenderer()
    # Render full model summary to terminal
    renderer.print_model(path_to_xlsx)
    # Or get as string
    text = renderer.render_model(path_to_xlsx)
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.text import Text
    from rich.columns import Columns
    HAS_RICH = True
except ImportError:
    HAS_RICH = False

try:
    from openpyxl import load_workbook
    HAS_OPENPYXL = True
except ImportError:
    HAS_OPENPYXL = False


# ---------------------------------------------------------------------------
# ModelMetrics — all computed values in one place
# ---------------------------------------------------------------------------

@dataclass
class ModelMetrics:
    """Computed metrics extracted from an LBO model workbook."""

    # Identification
    company_name: str = "Target Company"
    sheets_found: List[str] = field(default_factory=list)

    # Assumptions (read from Assumptions sheet)
    ltm_revenue: float = 0.0
    ltm_ebitda: float = 0.0
    entry_multiple: float = 0.0
    exit_multiple: float = 0.0
    hold_period: int = 5

    # Debt structure
    senior_debt_multiple: float = 0.0
    senior_interest_rate: float = 0.0
    senior_amortization: float = 0.0
    sub_debt_multiple: float = 0.0
    sub_interest_rate: float = 0.0

    # Fees & rates
    transaction_fee_pct: float = 0.0
    financing_fee_pct: float = 0.0
    capex_pct_revenue: float = 0.0
    nwc_pct_revenue: float = 0.0
    tax_rate: float = 0.0

    # Projection drivers
    revenue_growth: List[float] = field(default_factory=list)
    ebitda_margin: List[float] = field(default_factory=list)

    # Computed: Sources & Uses
    entry_ev: float = 0.0
    total_senior_debt: float = 0.0
    total_sub_debt: float = 0.0
    total_debt: float = 0.0
    transaction_fees: float = 0.0
    financing_fees: float = 0.0
    equity_invested: float = 0.0

    # Computed: Projections
    projected_revenue: List[float] = field(default_factory=list)
    projected_ebitda: List[float] = field(default_factory=list)
    projected_ebitda_margin: List[float] = field(default_factory=list)

    # Computed: Debt schedule (simplified — no amort for terminal display)
    senior_debt_by_year: List[float] = field(default_factory=list)
    sub_debt_by_year: List[float] = field(default_factory=list)
    total_debt_by_year: List[float] = field(default_factory=list)
    senior_interest_by_year: List[float] = field(default_factory=list)
    sub_interest_by_year: List[float] = field(default_factory=list)
    total_interest_by_year: List[float] = field(default_factory=list)
    leverage_by_year: List[float] = field(default_factory=list)

    # Computed: Returns
    exit_ebitda: float = 0.0
    exit_ev: float = 0.0
    exit_equity: float = 0.0
    moic: float = 0.0
    irr: float = 0.0

    # Sensitivity grid: list of (entry_mult, exit_mult, moic, irr)
    sensitivity_rows: List[Tuple[float, float, float, float]] = field(
        default_factory=list
    )
    sensitivity_entry_range: List[float] = field(default_factory=list)
    sensitivity_exit_range: List[float] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Helper: safe float extraction
# ---------------------------------------------------------------------------

def _safe_float(val: Any) -> float:
    """Extract a float from a cell value, ignoring formulas."""
    if val is None:
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, str):
        # Skip formula strings
        if val.startswith("="):
            return 0.0
        try:
            return float(val.replace(",", "").replace("$", "").strip())
        except (ValueError, TypeError):
            return 0.0
    return 0.0


def _fmt_dollar(v: float) -> str:
    """Format as dollar amount: $123.4M or $1.2B."""
    if abs(v) >= 1000:
        return f"${v / 1000:,.1f}B"
    return f"${v:,.1f}M"


def _fmt_pct(v: float) -> str:
    """Format as percentage from decimal: 0.25 -> 25.0%."""
    return f"{v * 100:.1f}%"


def _fmt_mult(v: float) -> str:
    """Format as multiple: 8.0 -> 8.0x."""
    return f"{v:.1f}x"


# ---------------------------------------------------------------------------
# Extraction: read workbook → ModelMetrics
# ---------------------------------------------------------------------------

def extract_metrics(wb_path: str) -> ModelMetrics:
    """
    Extract model metrics from an Excel workbook's Assumptions sheet.

    Reads the Assumptions sheet cell layout per excel_modules.py:
    - Row 5: LTM Revenue (B5), Row 6: LTM EBITDA (B6)
    - Row 7: Entry Multiple (B7), Row 8: Exit Multiple (B8)
    - Row 9: Hold Period (B9)
    - Row 12-16: Debt structure, Row 19-24: Fees & rates
    - Row 28-29: Projection drivers (cols C-G)

    Then computes all derived values in Python.
    """
    if not HAS_OPENPYXL:
        raise ImportError("openpyxl is required: pip install openpyxl")

    wb = load_workbook(str(wb_path), data_only=False, read_only=True)
    m = ModelMetrics(sheets_found=wb.sheetnames)

    if "Assumptions" not in wb.sheetnames:
        wb.close()
        raise ValueError(
            f"No 'Assumptions' sheet in {wb_path}. "
            f"Found: {wb.sheetnames}"
        )

    ws = wb["Assumptions"]

    # --- Read cell values from known positions ---
    m.company_name = ws.cell(1, 2).value or ws.cell(1, 1).value or "Target Company"
    # Strip title prefix if present
    if isinstance(m.company_name, str) and " - " in m.company_name:
        m.company_name = m.company_name.split(" - ")[0].strip()

    m.ltm_revenue = _safe_float(ws.cell(5, 2).value)
    m.ltm_ebitda = _safe_float(ws.cell(6, 2).value)
    m.entry_multiple = _safe_float(ws.cell(7, 2).value)
    m.exit_multiple = _safe_float(ws.cell(8, 2).value)
    m.hold_period = max(1, int(_safe_float(ws.cell(9, 2).value)))

    m.senior_debt_multiple = _safe_float(ws.cell(12, 2).value)
    m.senior_interest_rate = _safe_float(ws.cell(13, 2).value)
    m.senior_amortization = _safe_float(ws.cell(14, 2).value)
    m.sub_debt_multiple = _safe_float(ws.cell(15, 2).value)
    m.sub_interest_rate = _safe_float(ws.cell(16, 2).value)

    m.transaction_fee_pct = _safe_float(ws.cell(19, 2).value)
    m.financing_fee_pct = _safe_float(ws.cell(20, 2).value)
    m.capex_pct_revenue = _safe_float(ws.cell(22, 2).value)
    m.nwc_pct_revenue = _safe_float(ws.cell(23, 2).value)
    m.tax_rate = _safe_float(ws.cell(24, 2).value)

    # Projection drivers (row 28 = revenue growth, row 29 = EBITDA margin)
    for yr in range(m.hold_period):
        col = 3 + yr  # C=3, D=4, E=5, F=6, G=7
        m.revenue_growth.append(_safe_float(ws.cell(28, col).value))
        m.ebitda_margin.append(_safe_float(ws.cell(29, col).value))

    wb.close()

    # --- Compute derived metrics ---
    _compute_sources_uses(m)
    _compute_projections(m)
    _compute_debt_schedule(m)
    _compute_returns(m)
    _compute_sensitivity(m)

    return m


def _compute_sources_uses(m: ModelMetrics) -> None:
    m.entry_ev = m.ltm_ebitda * m.entry_multiple
    m.total_senior_debt = m.ltm_ebitda * m.senior_debt_multiple
    m.total_sub_debt = m.ltm_ebitda * m.sub_debt_multiple
    m.total_debt = m.total_senior_debt + m.total_sub_debt
    m.transaction_fees = m.entry_ev * m.transaction_fee_pct
    m.financing_fees = m.total_debt * m.financing_fee_pct
    m.equity_invested = m.entry_ev - m.total_debt + m.transaction_fees + m.financing_fees


def _compute_projections(m: ModelMetrics) -> None:
    rev = m.ltm_revenue
    for yr in range(m.hold_period):
        g = m.revenue_growth[yr] if yr < len(m.revenue_growth) else 0.05
        margin = m.ebitda_margin[yr] if yr < len(m.ebitda_margin) else 0.20
        rev = rev * (1 + g)
        ebitda = rev * margin
        m.projected_revenue.append(round(rev, 2))
        m.projected_ebitda.append(round(ebitda, 2))
        m.projected_ebitda_margin.append(margin)


def _compute_debt_schedule(m: ModelMetrics) -> None:
    senior = m.total_senior_debt
    sub = m.total_sub_debt

    for yr in range(m.hold_period):
        # Senior amortization
        amort = senior * m.senior_amortization
        senior = max(0, senior - amort)
        sr_interest = senior * m.senior_interest_rate
        sb_interest = sub * m.sub_interest_rate

        m.senior_debt_by_year.append(round(senior, 2))
        m.sub_debt_by_year.append(round(sub, 2))
        m.total_debt_by_year.append(round(senior + sub, 2))
        m.senior_interest_by_year.append(round(sr_interest, 2))
        m.sub_interest_by_year.append(round(sb_interest, 2))
        m.total_interest_by_year.append(round(sr_interest + sb_interest, 2))

        ebitda = m.projected_ebitda[yr] if yr < len(m.projected_ebitda) else m.ltm_ebitda
        leverage = (senior + sub) / ebitda if ebitda > 0 else 0
        m.leverage_by_year.append(round(leverage, 2))


def _compute_returns(m: ModelMetrics) -> None:
    m.exit_ebitda = m.projected_ebitda[-1] if m.projected_ebitda else m.ltm_ebitda
    m.exit_ev = m.exit_ebitda * m.exit_multiple

    exit_debt = m.total_debt_by_year[-1] if m.total_debt_by_year else m.total_debt
    m.exit_equity = m.exit_ev - exit_debt

    if m.equity_invested > 0:
        m.moic = m.exit_equity / m.equity_invested
    if m.moic > 0 and m.hold_period > 0:
        m.irr = m.moic ** (1.0 / m.hold_period) - 1


def _compute_sensitivity(m: ModelMetrics) -> None:
    """Compute MOIC/IRR grid for entry x exit multiple ranges."""
    m.sensitivity_entry_range = [
        m.entry_multiple - 1.0,
        m.entry_multiple - 0.5,
        m.entry_multiple,
        m.entry_multiple + 0.5,
        m.entry_multiple + 1.0,
    ]
    m.sensitivity_exit_range = [
        m.exit_multiple - 1.0,
        m.exit_multiple - 0.5,
        m.exit_multiple,
        m.exit_multiple + 0.5,
        m.exit_multiple + 1.0,
    ]

    exit_debt = m.total_debt_by_year[-1] if m.total_debt_by_year else m.total_debt

    for entry_m in m.sensitivity_entry_range:
        if entry_m <= 0:
            continue
        ev = m.ltm_ebitda * entry_m
        debt = m.total_debt  # Uses same debt structure
        fees = ev * m.transaction_fee_pct + debt * m.financing_fee_pct
        eq_in = ev - debt + fees
        if eq_in <= 0:
            continue

        for exit_m in m.sensitivity_exit_range:
            if exit_m <= 0:
                continue
            x_ev = m.exit_ebitda * exit_m
            x_eq = x_ev - exit_debt
            moic = x_eq / eq_in if eq_in > 0 else 0
            irr = (moic ** (1.0 / m.hold_period) - 1) if moic > 0 else -1.0
            m.sensitivity_rows.append((entry_m, exit_m, round(moic, 2), round(irr * 100, 1)))


# ---------------------------------------------------------------------------
# Rendering: ModelMetrics → formatted strings
# ---------------------------------------------------------------------------

class TerminalModelRenderer:
    """
    Renders LBO model outputs as rich terminal tables.

    All methods return strings suitable for terminal display.
    Use print_model() for direct console output with color.
    """

    def __init__(self, use_color: bool = True):
        self._use_color = use_color and HAS_RICH

    # --- Public API ---

    def render_model(self, wb_path: str) -> str:
        """Render complete model summary as formatted string."""
        metrics = extract_metrics(wb_path)
        sections = [
            self.render_deal_summary(metrics),
            self.render_sources_uses(metrics),
            self.render_operating_model(metrics),
            self.render_debt_summary(metrics),
            self.render_returns(metrics),
            self.render_sensitivity(metrics),
        ]
        return "\n\n".join(sections)

    def print_model(self, wb_path: str) -> None:
        """Print model summary directly to console with rich formatting."""
        metrics = extract_metrics(wb_path)
        console = Console() if HAS_RICH else None

        sections = [
            ("Deal Summary", self._deal_summary_table(metrics)),
            ("Sources & Uses", self._sources_uses_table(metrics)),
            ("Operating Model", self._operating_model_table(metrics)),
            ("Debt Schedule", self._debt_summary_table(metrics)),
            ("Returns Analysis", self._returns_table(metrics)),
            ("Sensitivity Analysis", self._sensitivity_table(metrics)),
        ]

        if console and self._use_color:
            for title, table in sections:
                console.print()
                console.print(Panel(table, title=title, border_style="blue"))
        else:
            print(self.render_model(wb_path))

    def render_deal_summary(self, m: ModelMetrics) -> str:
        """One-box deal overview."""
        lines = [
            f"  {m.company_name} - LBO Summary",
            f"  {'=' * 50}",
            f"  Entry EV:       {_fmt_dollar(m.entry_ev):>12}  ({_fmt_mult(m.entry_multiple)} EBITDA)",
            f"  LTM Revenue:    {_fmt_dollar(m.ltm_revenue):>12}",
            f"  LTM EBITDA:     {_fmt_dollar(m.ltm_ebitda):>12}  ({_fmt_pct(m.ltm_ebitda / m.ltm_revenue if m.ltm_revenue else 0)} margin)",
            f"  Hold Period:    {m.hold_period:>9} yrs",
            f"  Exit Multiple:  {_fmt_mult(m.exit_multiple):>12}",
            f"  {'─' * 50}",
            f"  MOIC: {m.moic:.2f}x   IRR: {_fmt_pct(m.irr)}",
            f"  Sheets: {', '.join(m.sheets_found)}",
        ]
        return "\n".join(lines)

    def render_sources_uses(self, m: ModelMetrics) -> str:
        """Sources & Uses summary."""
        lines = [
            "  Sources & Uses",
            f"  {'─' * 40}",
            f"  SOURCES",
            f"    Senior Debt:     {_fmt_dollar(m.total_senior_debt):>10}  ({_fmt_mult(m.senior_debt_multiple)})",
            f"    Sub Debt:        {_fmt_dollar(m.total_sub_debt):>10}  ({_fmt_mult(m.sub_debt_multiple)})",
            f"    Sponsor Equity:  {_fmt_dollar(m.equity_invested):>10}",
            f"    Total Sources:   {_fmt_dollar(m.total_debt + m.equity_invested):>10}",
            f"  {'─' * 40}",
            f"  USES",
            f"    Enterprise Value:{_fmt_dollar(m.entry_ev):>10}",
            f"    Transaction Fees:{_fmt_dollar(m.transaction_fees):>10}  ({_fmt_pct(m.transaction_fee_pct)})",
            f"    Financing Fees:  {_fmt_dollar(m.financing_fees):>10}  ({_fmt_pct(m.financing_fee_pct)})",
            f"    Total Uses:      {_fmt_dollar(m.entry_ev + m.transaction_fees + m.financing_fees):>10}",
        ]
        return "\n".join(lines)

    def render_operating_model(self, m: ModelMetrics) -> str:
        """Projection table: Revenue, EBITDA, margins by year."""
        # Header row
        header = f"  {'':>20}"
        for yr in range(m.hold_period):
            header += f"  {'Year ' + str(yr + 1):>10}"
        lines = [
            "  Operating Model Projections",
            f"  {'─' * (22 + 12 * m.hold_period)}",
            header,
            f"  {'─' * (22 + 12 * m.hold_period)}",
        ]

        # Revenue
        row = f"  {'Revenue ($M)':>20}"
        for v in m.projected_revenue:
            row += f"  {v:>10,.1f}"
        lines.append(row)

        # Revenue growth
        row = f"  {'  Growth %':>20}"
        for g in m.revenue_growth:
            row += f"  {g * 100:>9.1f}%"
        lines.append(row)

        # EBITDA
        row = f"  {'EBITDA ($M)':>20}"
        for v in m.projected_ebitda:
            row += f"  {v:>10,.1f}"
        lines.append(row)

        # Margin
        row = f"  {'  Margin %':>20}"
        for mg in m.projected_ebitda_margin:
            row += f"  {mg * 100:>9.1f}%"
        lines.append(row)

        return "\n".join(lines)

    def render_debt_summary(self, m: ModelMetrics) -> str:
        """Debt schedule summary with leverage ratios."""
        header = f"  {'':>20}"
        for yr in range(m.hold_period):
            header += f"  {'Year ' + str(yr + 1):>10}"
        lines = [
            "  Debt Schedule Summary",
            f"  {'─' * (22 + 12 * m.hold_period)}",
            header,
            f"  {'─' * (22 + 12 * m.hold_period)}",
        ]

        # Total debt
        row = f"  {'Total Debt ($M)':>20}"
        for v in m.total_debt_by_year:
            row += f"  {v:>10,.1f}"
        lines.append(row)

        # Interest
        row = f"  {'Total Interest ($M)':>20}"
        for v in m.total_interest_by_year:
            row += f"  {v:>10,.1f}"
        lines.append(row)

        # Leverage
        row = f"  {'Leverage (x EBITDA)':>20}"
        for v in m.leverage_by_year:
            row += f"  {v:>9.1f}x"
        lines.append(row)

        return "\n".join(lines)

    def render_returns(self, m: ModelMetrics) -> str:
        """Returns analysis summary."""
        lines = [
            "  Returns Analysis",
            f"  {'─' * 45}",
            f"  Equity Invested:   {_fmt_dollar(m.equity_invested):>12}",
            f"  Exit EBITDA:       {_fmt_dollar(m.exit_ebitda):>12}",
            f"  Exit EV:           {_fmt_dollar(m.exit_ev):>12}  ({_fmt_mult(m.exit_multiple)})",
            f"  Exit Equity:       {_fmt_dollar(m.exit_equity):>12}",
            f"  {'─' * 45}",
            f"  MOIC:              {m.moic:>11.2f}x",
            f"  IRR:               {_fmt_pct(m.irr):>12}",
        ]
        return "\n".join(lines)

    def render_sensitivity(self, m: ModelMetrics) -> str:
        """Sensitivity matrix: entry x exit multiples → MOIC / IRR."""
        if not m.sensitivity_rows:
            return "  Sensitivity: No data"

        # Build grid: entry_mult → exit_mult → (moic, irr)
        grid: Dict[float, Dict[float, Tuple[float, float]]] = {}
        for entry_m, exit_m, moic, irr in m.sensitivity_rows:
            grid.setdefault(entry_m, {})[exit_m] = (moic, irr)

        exit_range = m.sensitivity_exit_range
        entry_range = m.sensitivity_entry_range

        # Header
        header = f"  {'Entry \\ Exit':>14}"
        for xm in exit_range:
            header += f"  {_fmt_mult(xm):>10}"

        lines = [
            "  MOIC Sensitivity (Entry x Exit Multiple)",
            f"  {'─' * (16 + 12 * len(exit_range))}",
            header,
            f"  {'─' * (16 + 12 * len(exit_range))}",
        ]

        for em in entry_range:
            if em not in grid:
                continue
            row = f"  {_fmt_mult(em):>14}"
            for xm in exit_range:
                pair = grid[em].get(xm, (0, 0))
                row += f"  {pair[0]:>9.2f}x"
            lines.append(row)

        lines.append("")
        lines.append("  IRR Sensitivity (Entry x Exit Multiple)")
        lines.append(f"  {'─' * (16 + 12 * len(exit_range))}")
        lines.append(header)
        lines.append(f"  {'─' * (16 + 12 * len(exit_range))}")

        for em in entry_range:
            if em not in grid:
                continue
            row = f"  {_fmt_mult(em):>14}"
            for xm in exit_range:
                pair = grid[em].get(xm, (0, 0))
                row += f"  {pair[1]:>9.1f}%"
            lines.append(row)

        return "\n".join(lines)

    # --- Rich table builders (for print_model color output) ---

    def _deal_summary_table(self, m: ModelMetrics) -> Table:
        """Rich table for deal summary."""
        if not HAS_RICH:
            return self.render_deal_summary(m)

        table = Table(show_header=False, box=None, padding=(0, 2))
        table.add_column("Metric", style="bold")
        table.add_column("Value", justify="right")
        table.add_column("Detail", style="dim")

        table.add_row("Entry EV", _fmt_dollar(m.entry_ev), f"{_fmt_mult(m.entry_multiple)} EBITDA")
        table.add_row("LTM Revenue", _fmt_dollar(m.ltm_revenue), "")
        table.add_row("LTM EBITDA", _fmt_dollar(m.ltm_ebitda),
                       f"{_fmt_pct(m.ltm_ebitda / m.ltm_revenue if m.ltm_revenue else 0)} margin")
        table.add_row("Hold Period", f"{m.hold_period} yrs", "")
        table.add_row("Exit Multiple", _fmt_mult(m.exit_multiple), "")
        table.add_row("", "", "")
        table.add_row("MOIC", f"[bold green]{m.moic:.2f}x[/bold green]" if m.moic >= 2.0
                       else f"[bold yellow]{m.moic:.2f}x[/bold yellow]" if m.moic >= 1.5
                       else f"[bold red]{m.moic:.2f}x[/bold red]", "")
        table.add_row("IRR", f"[bold green]{_fmt_pct(m.irr)}[/bold green]" if m.irr >= 0.20
                       else f"[bold yellow]{_fmt_pct(m.irr)}[/bold yellow]" if m.irr >= 0.15
                       else f"[bold red]{_fmt_pct(m.irr)}[/bold red]", "")
        return table

    def _sources_uses_table(self, m: ModelMetrics) -> Table:
        if not HAS_RICH:
            return self.render_sources_uses(m)

        table = Table(show_header=True, box=None, padding=(0, 2))
        table.add_column("", style="bold")
        table.add_column("Amount", justify="right")
        table.add_column("Detail", style="dim")

        table.add_row("[bold]SOURCES[/bold]", "", "")
        table.add_row("  Senior Debt", _fmt_dollar(m.total_senior_debt), _fmt_mult(m.senior_debt_multiple))
        table.add_row("  Sub Debt", _fmt_dollar(m.total_sub_debt), _fmt_mult(m.sub_debt_multiple))
        table.add_row("  Sponsor Equity", _fmt_dollar(m.equity_invested), "")
        table.add_row("", "", "")
        table.add_row("[bold]USES[/bold]", "", "")
        table.add_row("  Enterprise Value", _fmt_dollar(m.entry_ev), "")
        table.add_row("  Transaction Fees", _fmt_dollar(m.transaction_fees), _fmt_pct(m.transaction_fee_pct))
        table.add_row("  Financing Fees", _fmt_dollar(m.financing_fees), _fmt_pct(m.financing_fee_pct))
        return table

    def _operating_model_table(self, m: ModelMetrics) -> Table:
        if not HAS_RICH:
            return self.render_operating_model(m)

        table = Table(show_header=True, box=None, padding=(0, 1))
        table.add_column("", style="bold", min_width=18)
        for yr in range(m.hold_period):
            table.add_column(f"Year {yr + 1}", justify="right", min_width=10)

        table.add_row("Revenue ($M)", *[f"{v:,.1f}" for v in m.projected_revenue])
        table.add_row("  Growth %", *[f"{g * 100:.1f}%" for g in m.revenue_growth])
        table.add_row("EBITDA ($M)", *[f"{v:,.1f}" for v in m.projected_ebitda])
        table.add_row("  Margin %", *[f"{mg * 100:.1f}%" for mg in m.projected_ebitda_margin])
        return table

    def _debt_summary_table(self, m: ModelMetrics) -> Table:
        if not HAS_RICH:
            return self.render_debt_summary(m)

        table = Table(show_header=True, box=None, padding=(0, 1))
        table.add_column("", style="bold", min_width=18)
        for yr in range(m.hold_period):
            table.add_column(f"Year {yr + 1}", justify="right", min_width=10)

        table.add_row("Total Debt ($M)", *[f"{v:,.1f}" for v in m.total_debt_by_year])
        table.add_row("Total Interest ($M)", *[f"{v:,.1f}" for v in m.total_interest_by_year])
        table.add_row("Leverage", *[f"{v:.1f}x" for v in m.leverage_by_year])
        return table

    def _returns_table(self, m: ModelMetrics) -> Table:
        if not HAS_RICH:
            return self.render_returns(m)

        table = Table(show_header=False, box=None, padding=(0, 2))
        table.add_column("Metric", style="bold")
        table.add_column("Value", justify="right")

        table.add_row("Equity Invested", _fmt_dollar(m.equity_invested))
        table.add_row("Exit EBITDA", _fmt_dollar(m.exit_ebitda))
        table.add_row("Exit EV", _fmt_dollar(m.exit_ev))
        table.add_row("Exit Equity", _fmt_dollar(m.exit_equity))
        table.add_row("", "")

        moic_style = "bold green" if m.moic >= 2.0 else "bold yellow" if m.moic >= 1.5 else "bold red"
        irr_style = "bold green" if m.irr >= 0.20 else "bold yellow" if m.irr >= 0.15 else "bold red"
        table.add_row("MOIC", f"[{moic_style}]{m.moic:.2f}x[/{moic_style}]")
        table.add_row("IRR", f"[{irr_style}]{_fmt_pct(m.irr)}[/{irr_style}]")
        return table

    def _sensitivity_table(self, m: ModelMetrics) -> Table:
        if not HAS_RICH or not m.sensitivity_rows:
            return self.render_sensitivity(m) if not HAS_RICH else Table()

        # Build grid
        grid: Dict[float, Dict[float, Tuple[float, float]]] = {}
        for entry_m, exit_m, moic, irr in m.sensitivity_rows:
            grid.setdefault(entry_m, {})[exit_m] = (moic, irr)

        table = Table(title="MOIC / IRR", show_header=True, box=None, padding=(0, 1))
        table.add_column("Entry \\ Exit", style="bold")
        for xm in m.sensitivity_exit_range:
            table.add_column(_fmt_mult(xm), justify="right")

        for em in m.sensitivity_entry_range:
            if em not in grid:
                continue
            cells = []
            for xm in m.sensitivity_exit_range:
                pair = grid[em].get(xm, (0, 0))
                moic, irr = pair
                style = "green" if irr >= 20 else "yellow" if irr >= 15 else "red"
                cells.append(f"[{style}]{moic:.2f}x / {irr:.1f}%[/{style}]")
            table.add_row(_fmt_mult(em), *cells)

        return table


# ---------------------------------------------------------------------------
# Convenience: render from assumptions dict (no workbook needed)
# ---------------------------------------------------------------------------

def render_from_assumptions(assumptions: Dict[str, Any]) -> str:
    """
    Render a terminal model summary from a dict of assumptions.

    Useful when you have assumptions but haven't generated the Excel yet.

    Keys: ltm_revenue, ltm_ebitda, entry_multiple, exit_multiple,
          hold_period, senior_debt_multiple, sub_debt_multiple,
          revenue_growth (list), ebitda_margin (list), etc.
    """
    m = ModelMetrics()
    m.company_name = assumptions.get("company_name", "Target Company")
    m.ltm_revenue = assumptions.get("ltm_revenue", 100.0)
    m.ltm_ebitda = assumptions.get("ltm_ebitda", 20.0)
    m.entry_multiple = assumptions.get("entry_multiple", 8.0)
    m.exit_multiple = assumptions.get("exit_multiple", 8.0)
    m.hold_period = assumptions.get("hold_period", 5)

    m.senior_debt_multiple = assumptions.get("senior_debt_multiple", 4.0)
    m.senior_interest_rate = assumptions.get("senior_interest_rate", 0.08)
    m.senior_amortization = assumptions.get("senior_amortization", 0.01)
    m.sub_debt_multiple = assumptions.get("sub_debt_multiple", 1.5)
    m.sub_interest_rate = assumptions.get("sub_interest_rate", 0.12)

    m.transaction_fee_pct = assumptions.get("transaction_fee_pct", 0.015)
    m.financing_fee_pct = assumptions.get("financing_fee_pct", 0.025)
    m.capex_pct_revenue = assumptions.get("capex_pct_revenue", 0.05)
    m.nwc_pct_revenue = assumptions.get("nwc_pct_revenue", 0.10)
    m.tax_rate = assumptions.get("tax_rate", 0.25)

    m.revenue_growth = assumptions.get("revenue_growth", [0.08, 0.07, 0.06, 0.05, 0.05])
    m.ebitda_margin = assumptions.get("ebitda_margin", [0.20, 0.21, 0.22, 0.22, 0.22])

    _compute_sources_uses(m)
    _compute_projections(m)
    _compute_debt_schedule(m)
    _compute_returns(m)
    _compute_sensitivity(m)

    renderer = TerminalModelRenderer(use_color=False)
    sections = [
        renderer.render_deal_summary(m),
        renderer.render_sources_uses(m),
        renderer.render_operating_model(m),
        renderer.render_debt_summary(m),
        renderer.render_returns(m),
        renderer.render_sensitivity(m),
    ]
    return "\n\n".join(sections)
