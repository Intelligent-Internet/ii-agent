#!/usr/bin/env python3
"""
LBO Quick Calculator Module

Rapid LBO returns analysis based on Private Equity textbook best practices.
Calculates IRR, MOIC, sensitivity matrices, and value creation attribution.

Key concepts from PE textbooks:
- Three value creation drivers: EBITDA growth, multiple expansion, deleveraging
- IRR sensitivity to entry/exit multiples and leverage
- Breakeven analysis for downside protection assessment
"""

from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
import math


@dataclass
class LBOAssumptions:
    """LBO transaction assumptions."""
    # Transaction
    entry_ebitda: float
    entry_multiple: float

    # Capital Structure
    senior_debt_multiple: float = 3.0  # x EBITDA
    sub_debt_multiple: float = 1.0     # x EBITDA

    # Operating
    ebitda_growth_rate: float = 0.08   # Annual EBITDA growth
    capex_pct_revenue: float = 0.05
    nwc_pct_revenue: float = 0.10
    revenue_to_ebitda: float = 5.0     # Revenue / EBITDA ratio

    # Debt Terms
    senior_interest_rate: float = 0.065
    sub_debt_interest_rate: float = 0.12
    mandatory_amort_pct: float = 0.05   # % of senior debt annually

    # Exit
    exit_multiple: float = 8.0
    hold_period: int = 5

    # Tax
    tax_rate: float = 0.25


@dataclass
class LBOResults:
    """LBO analysis results."""
    # Entry
    entry_ev: float
    entry_equity: float
    entry_debt: float

    # Exit
    exit_ebitda: float
    exit_ev: float
    exit_debt: float
    exit_equity: float

    # Returns
    moic: float
    irr: float

    # Value Creation Attribution
    ebitda_growth_contribution: float
    multiple_expansion_contribution: float
    deleveraging_contribution: float

    # Annual Projections
    projections: List[Dict]


def calculate_irr(cash_flows: List[float], max_iterations: int = 1000, tolerance: float = 0.0001) -> float:
    """
    Calculate IRR using Newton-Raphson method.

    Args:
        cash_flows: List of cash flows, starting with negative initial investment
        max_iterations: Maximum iterations for convergence
        tolerance: Convergence tolerance

    Returns:
        IRR as decimal (e.g., 0.25 for 25%)
    """
    if not cash_flows or all(cf == 0 for cf in cash_flows):
        return 0.0

    # Initial guess
    rate = 0.10

    for _ in range(max_iterations):
        # Calculate NPV and its derivative
        npv = sum(cf / (1 + rate) ** i for i, cf in enumerate(cash_flows))
        npv_derivative = sum(-i * cf / (1 + rate) ** (i + 1) for i, cf in enumerate(cash_flows))

        if abs(npv_derivative) < 1e-10:
            break

        # Newton-Raphson update
        new_rate = rate - npv / npv_derivative

        if abs(new_rate - rate) < tolerance:
            return new_rate

        rate = new_rate

        # Keep rate in reasonable bounds
        rate = max(-0.99, min(rate, 10.0))

    return rate


def run_lbo_analysis(assumptions: LBOAssumptions) -> LBOResults:
    """
    Run complete LBO analysis.

    Args:
        assumptions: LBO transaction assumptions

    Returns:
        LBOResults with full analysis
    """
    a = assumptions

    # Entry calculations
    entry_ev = a.entry_ebitda * a.entry_multiple
    senior_debt = a.entry_ebitda * a.senior_debt_multiple
    sub_debt = a.entry_ebitda * a.sub_debt_multiple
    entry_debt = senior_debt + sub_debt
    entry_equity = entry_ev - entry_debt

    # Build projections
    projections = []
    current_senior = senior_debt
    current_sub = sub_debt

    for year in range(a.hold_period + 1):
        if year == 0:
            # Entry year
            ebitda = a.entry_ebitda
            revenue = ebitda * a.revenue_to_ebitda
            senior = senior_debt
            sub = sub_debt
            fcf = 0
        else:
            # Projection years
            prev = projections[-1]

            # EBITDA growth
            ebitda = prev['ebitda'] * (1 + a.ebitda_growth_rate)
            revenue = ebitda * a.revenue_to_ebitda

            # Interest expense
            senior_interest = prev['senior_debt'] * a.senior_interest_rate
            sub_interest = prev['sub_debt'] * a.sub_debt_interest_rate
            total_interest = senior_interest + sub_interest

            # Simplified FCF calculation
            capex = revenue * a.capex_pct_revenue
            nwc_change = (revenue - prev['revenue']) * a.nwc_pct_revenue

            ebt = ebitda - total_interest
            taxes = max(0, ebt * a.tax_rate)

            fcf = ebitda - total_interest - taxes - capex - nwc_change

            # Debt paydown
            mandatory_amort = senior_debt * a.mandatory_amort_pct
            optional_prepay = max(0, fcf - mandatory_amort)

            senior = max(0, prev['senior_debt'] - mandatory_amort - optional_prepay)
            sub = prev['sub_debt']  # Sub debt typically stays until exit

        projections.append({
            'year': year,
            'revenue': revenue,
            'ebitda': ebitda,
            'senior_debt': senior,
            'sub_debt': sub,
            'total_debt': senior + sub,
            'fcf': fcf,
        })

    # Exit calculations
    final = projections[-1]
    exit_ebitda = final['ebitda']
    exit_ev = exit_ebitda * a.exit_multiple
    exit_debt = final['total_debt']
    exit_equity = exit_ev - exit_debt

    # Returns
    moic = exit_equity / entry_equity if entry_equity > 0 else 0

    # IRR calculation
    cash_flows = [-entry_equity] + [0] * (a.hold_period - 1) + [exit_equity]
    irr = calculate_irr(cash_flows)

    # Value creation attribution
    # 1. EBITDA growth at entry multiple
    ebitda_growth_value = (exit_ebitda - a.entry_ebitda) * a.entry_multiple

    # 2. Multiple expansion on exit EBITDA
    multiple_expansion_value = exit_ebitda * (a.exit_multiple - a.entry_multiple)

    # 3. Deleveraging (debt paid down)
    deleveraging_value = entry_debt - exit_debt

    total_gain = exit_equity - entry_equity

    if total_gain > 0:
        ebitda_pct = ebitda_growth_value / total_gain
        multiple_pct = multiple_expansion_value / total_gain
        delever_pct = deleveraging_value / total_gain
    else:
        ebitda_pct = multiple_pct = delever_pct = 0

    return LBOResults(
        entry_ev=entry_ev,
        entry_equity=entry_equity,
        entry_debt=entry_debt,
        exit_ebitda=exit_ebitda,
        exit_ev=exit_ev,
        exit_debt=exit_debt,
        exit_equity=exit_equity,
        moic=moic,
        irr=irr,
        ebitda_growth_contribution=ebitda_pct,
        multiple_expansion_contribution=multiple_pct,
        deleveraging_contribution=delever_pct,
        projections=projections,
    )


def build_sensitivity_matrix(
    base_assumptions: LBOAssumptions,
    row_param: str,
    row_values: List[float],
    col_param: str,
    col_values: List[float],
    output_metric: str = 'irr'
) -> Dict:
    """
    Build 2D sensitivity matrix.

    Args:
        base_assumptions: Base case assumptions
        row_param: Parameter name for rows (e.g., 'entry_multiple')
        row_values: List of values for row parameter
        col_param: Parameter name for columns (e.g., 'exit_multiple')
        col_values: List of values for column parameter
        output_metric: 'irr' or 'moic'

    Returns:
        Dict with matrix data and labels
    """
    matrix = []

    for row_val in row_values:
        row_results = []
        for col_val in col_values:
            # Create modified assumptions
            modified = LBOAssumptions(
                entry_ebitda=base_assumptions.entry_ebitda,
                entry_multiple=base_assumptions.entry_multiple,
                senior_debt_multiple=base_assumptions.senior_debt_multiple,
                sub_debt_multiple=base_assumptions.sub_debt_multiple,
                ebitda_growth_rate=base_assumptions.ebitda_growth_rate,
                exit_multiple=base_assumptions.exit_multiple,
                hold_period=base_assumptions.hold_period,
            )

            # Apply parameter changes
            setattr(modified, row_param, row_val)
            setattr(modified, col_param, col_val)

            # Run analysis
            result = run_lbo_analysis(modified)

            if output_metric == 'irr':
                row_results.append(result.irr)
            else:
                row_results.append(result.moic)

        matrix.append(row_results)

    return {
        'matrix': matrix,
        'row_param': row_param,
        'row_values': row_values,
        'col_param': col_param,
        'col_values': col_values,
        'metric': output_metric,
    }


def calculate_breakeven_multiple(assumptions: LBOAssumptions, target_moic: float = 1.0) -> float:
    """
    Calculate breakeven exit multiple for target MOIC.

    Args:
        assumptions: LBO assumptions
        target_moic: Target MOIC (default 1.0 = return of capital)

    Returns:
        Breakeven exit multiple
    """
    # Binary search for breakeven multiple
    low, high = 1.0, 20.0

    for _ in range(50):
        mid = (low + high) / 2
        test_assumptions = LBOAssumptions(
            entry_ebitda=assumptions.entry_ebitda,
            entry_multiple=assumptions.entry_multiple,
            senior_debt_multiple=assumptions.senior_debt_multiple,
            sub_debt_multiple=assumptions.sub_debt_multiple,
            ebitda_growth_rate=assumptions.ebitda_growth_rate,
            exit_multiple=mid,
            hold_period=assumptions.hold_period,
        )
        result = run_lbo_analysis(test_assumptions)

        if abs(result.moic - target_moic) < 0.01:
            return mid
        elif result.moic < target_moic:
            low = mid
        else:
            high = mid

    return mid


def generate_lbo_summary(assumptions: LBOAssumptions) -> str:
    """
    Generate formatted LBO analysis summary.

    Args:
        assumptions: LBO transaction assumptions

    Returns:
        Formatted markdown summary
    """
    result = run_lbo_analysis(assumptions)
    breakeven = calculate_breakeven_multiple(assumptions)

    # Build sensitivity matrices
    entry_exit_sens = build_sensitivity_matrix(
        assumptions,
        'entry_multiple', [assumptions.entry_multiple - 1, assumptions.entry_multiple, assumptions.entry_multiple + 1],
        'exit_multiple', [assumptions.exit_multiple - 1, assumptions.exit_multiple, assumptions.exit_multiple + 1],
        'moic'
    )

    summary = f"""## LBO Quick Analysis Summary

### Transaction Overview
| Metric | Value |
|--------|-------|
| Entry EBITDA | ${result.entry_ev / assumptions.entry_multiple:,.0f}M |
| Entry Multiple | {assumptions.entry_multiple:.1f}x |
| Entry Enterprise Value | ${result.entry_ev:,.0f}M |
| Entry Debt | ${result.entry_debt:,.0f}M ({result.entry_debt/result.entry_ev*100:.0f}% of EV) |
| Entry Equity | ${result.entry_equity:,.0f}M ({result.entry_equity/result.entry_ev*100:.0f}% of EV) |

### Exit Analysis (Year {assumptions.hold_period})
| Metric | Value |
|--------|-------|
| Exit EBITDA | ${result.exit_ebitda:,.0f}M |
| Exit Multiple | {assumptions.exit_multiple:.1f}x |
| Exit Enterprise Value | ${result.exit_ev:,.0f}M |
| Exit Debt | ${result.exit_debt:,.0f}M |
| Exit Equity | ${result.exit_equity:,.0f}M |

### Returns
| Metric | Value |
|--------|-------|
| **MOIC** | **{result.moic:.2f}x** |
| **IRR** | **{result.irr*100:.1f}%** |
| Breakeven Exit Multiple | {breakeven:.1f}x |
| Cushion vs Entry | {assumptions.entry_multiple - breakeven:.1f}x |

### Value Creation Attribution
| Driver | Contribution |
|--------|--------------|
| EBITDA Growth | {result.ebitda_growth_contribution*100:.0f}% |
| Multiple Expansion | {result.multiple_expansion_contribution*100:.0f}% |
| Deleveraging | {result.deleveraging_contribution*100:.0f}% |

### MOIC Sensitivity (Entry vs Exit Multiple)
"""

    # Add sensitivity table
    summary += f"|Entry \\ Exit| {' | '.join(f'{v:.1f}x' for v in entry_exit_sens['col_values'])} |\n"
    summary += f"|------------|{'|'.join(['------'] * len(entry_exit_sens['col_values']))}|\n"

    for i, row_val in enumerate(entry_exit_sens['row_values']):
        cells = [f"{v:.2f}x" for v in entry_exit_sens['matrix'][i]]
        summary += f"| **{row_val:.1f}x** | {' | '.join(cells)} |\n"

    return summary


def quick_lbo(
    ebitda: float,
    entry_multiple: float = 8.0,
    exit_multiple: float = 8.0,
    leverage: float = 4.0,
    hold_years: int = 5,
    ebitda_growth: float = 0.08
) -> Dict:
    """
    Quick LBO returns calculation.

    Args:
        ebitda: Entry LTM EBITDA
        entry_multiple: Entry EV/EBITDA multiple
        exit_multiple: Exit EV/EBITDA multiple
        leverage: Total debt / EBITDA
        hold_years: Investment holding period
        ebitda_growth: Annual EBITDA growth rate

    Returns:
        Dict with key returns metrics
    """
    assumptions = LBOAssumptions(
        entry_ebitda=ebitda,
        entry_multiple=entry_multiple,
        senior_debt_multiple=min(leverage * 0.75, 4.0),
        sub_debt_multiple=max(0, leverage - min(leverage * 0.75, 4.0)),
        ebitda_growth_rate=ebitda_growth,
        exit_multiple=exit_multiple,
        hold_period=hold_years,
    )

    result = run_lbo_analysis(assumptions)

    return {
        'entry_equity': result.entry_equity,
        'exit_equity': result.exit_equity,
        'moic': round(result.moic, 2),
        'irr': round(result.irr * 100, 1),
        'value_creation': {
            'ebitda_growth': round(result.ebitda_growth_contribution * 100, 0),
            'multiple_expansion': round(result.multiple_expansion_contribution * 100, 0),
            'deleveraging': round(result.deleveraging_contribution * 100, 0),
        }
    }


if __name__ == "__main__":
    # Example usage
    print("=" * 60)
    print("LBO Quick Calculator - Example Analysis")
    print("=" * 60)

    # Create sample assumptions
    assumptions = LBOAssumptions(
        entry_ebitda=50.0,      # $50M EBITDA
        entry_multiple=8.0,     # 8x entry
        senior_debt_multiple=3.5,
        sub_debt_multiple=1.0,
        ebitda_growth_rate=0.10,  # 10% annual growth
        exit_multiple=8.5,      # 8.5x exit
        hold_period=5,
    )

    # Run analysis
    result = run_lbo_analysis(assumptions)

    print(f"\nEntry: ${result.entry_ev:.0f}M EV at {assumptions.entry_multiple:.1f}x")
    print(f"Equity: ${result.entry_equity:.0f}M | Debt: ${result.entry_debt:.0f}M")
    print(f"\nExit: ${result.exit_ev:.0f}M EV at {assumptions.exit_multiple:.1f}x")
    print(f"Exit Equity: ${result.exit_equity:.0f}M")
    print(f"\nMOIC: {result.moic:.2f}x | IRR: {result.irr*100:.1f}%")

    print("\n" + "=" * 60)
    print("Full Summary Report:")
    print("=" * 60)
    print(generate_lbo_summary(assumptions))
