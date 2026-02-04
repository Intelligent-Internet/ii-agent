#!/usr/bin/env python3
"""
Capital Structure Analyzer Module

Evaluates optimal debt capacity and financing recommendations based on
Private Equity textbook frameworks.

Key concepts:
- Debt capacity constrained by coverage ratios (interest, fixed charge)
- Industry benchmarks for leverage by sector
- Senior vs subordinated debt allocation
- Mezzanine and PIK financing analysis
"""

from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum


class Industry(Enum):
    """Industry sectors with typical leverage ranges."""
    TECHNOLOGY = "technology"
    HEALTHCARE = "healthcare"
    INDUSTRIALS = "industrials"
    CONSUMER = "consumer"
    BUSINESS_SERVICES = "business_services"
    FINANCIAL_SERVICES = "financial_services"
    REAL_ESTATE = "real_estate"
    ENERGY = "energy"
    RETAIL = "retail"
    MEDIA = "media"


# Industry leverage benchmarks (Debt/EBITDA ranges)
INDUSTRY_LEVERAGE = {
    Industry.TECHNOLOGY: {"low": 2.0, "mid": 3.5, "high": 5.0},
    Industry.HEALTHCARE: {"low": 3.0, "mid": 4.5, "high": 6.0},
    Industry.INDUSTRIALS: {"low": 2.5, "mid": 4.0, "high": 5.5},
    Industry.CONSUMER: {"low": 3.0, "mid": 4.5, "high": 6.0},
    Industry.BUSINESS_SERVICES: {"low": 3.5, "mid": 5.0, "high": 6.5},
    Industry.FINANCIAL_SERVICES: {"low": 2.0, "mid": 3.0, "high": 4.0},
    Industry.REAL_ESTATE: {"low": 4.0, "mid": 6.0, "high": 8.0},
    Industry.ENERGY: {"low": 2.0, "mid": 3.5, "high": 5.0},
    Industry.RETAIL: {"low": 2.5, "mid": 4.0, "high": 5.5},
    Industry.MEDIA: {"low": 3.0, "mid": 4.5, "high": 6.0},
}

# Debt instrument characteristics
DEBT_INSTRUMENTS = {
    "term_loan_a": {
        "name": "Term Loan A",
        "spread": 0.025,  # L + 250bp
        "typical_amort": 0.10,
        "secured": True,
        "max_leverage": 3.0,
    },
    "term_loan_b": {
        "name": "Term Loan B",
        "spread": 0.035,  # L + 350bp
        "typical_amort": 0.01,
        "secured": True,
        "max_leverage": 4.5,
    },
    "senior_notes": {
        "name": "Senior Unsecured Notes",
        "spread": 0.055,  # ~7-8% yield
        "typical_amort": 0.0,
        "secured": False,
        "max_leverage": 5.5,
    },
    "mezzanine": {
        "name": "Mezzanine / Sub Debt",
        "spread": 0.10,  # ~12-14% all-in
        "typical_amort": 0.0,
        "secured": False,
        "max_leverage": 6.5,
        "pik_component": 0.04,
    },
    "second_lien": {
        "name": "Second Lien Term Loan",
        "spread": 0.065,
        "typical_amort": 0.0,
        "secured": True,
        "max_leverage": 5.5,
    },
}


@dataclass
class CompanyFinancials:
    """Company financial data for debt capacity analysis."""
    ebitda: float
    revenue: float
    capex: float
    interest_expense: float = 0
    existing_debt: float = 0
    cash: float = 0
    working_capital_needs: float = 0

    # Qualitative factors
    revenue_volatility: str = "moderate"  # low, moderate, high
    customer_concentration: str = "moderate"  # low, moderate, high
    industry: Industry = Industry.INDUSTRIALS
    asset_light: bool = False


@dataclass
class DebtCapacityResult:
    """Results of debt capacity analysis."""
    max_total_debt: float
    max_senior_secured: float
    max_senior_unsecured: float
    max_subordinated: float

    # Coverage metrics
    interest_coverage: float
    fixed_charge_coverage: float
    debt_to_ebitda: float

    # Recommended structure
    recommended_structure: Dict[str, float]
    total_interest_expense: float

    # Analysis
    capacity_constraints: List[str]
    risk_assessment: str


def calculate_debt_capacity(
    financials: CompanyFinancials,
    min_interest_coverage: float = 2.0,
    min_fixed_charge_coverage: float = 1.2,
    base_rate: float = 0.055
) -> DebtCapacityResult:
    """
    Calculate maximum debt capacity based on coverage ratios.

    Args:
        financials: Company financial data
        min_interest_coverage: Minimum interest coverage ratio
        min_fixed_charge_coverage: Minimum fixed charge coverage ratio
        base_rate: Base interest rate (SOFR/LIBOR)

    Returns:
        DebtCapacityResult with capacity analysis
    """
    f = financials

    # Get industry benchmarks
    industry_bench = INDUSTRY_LEVERAGE.get(
        f.industry,
        INDUSTRY_LEVERAGE[Industry.INDUSTRIALS]
    )

    # Adjust for company-specific factors
    leverage_adj = 0
    constraints = []

    if f.revenue_volatility == "high":
        leverage_adj -= 0.5
        constraints.append("High revenue volatility reduces capacity by 0.5x")
    elif f.revenue_volatility == "low":
        leverage_adj += 0.5

    if f.customer_concentration == "high":
        leverage_adj -= 0.5
        constraints.append("High customer concentration reduces capacity by 0.5x")

    if f.asset_light:
        leverage_adj -= 0.5
        constraints.append("Asset-light model limits secured debt capacity")

    # Maximum leverage based on industry + adjustments
    max_leverage = industry_bench["high"] + leverage_adj
    max_debt_from_leverage = f.ebitda * max_leverage

    # Calculate coverage-constrained debt capacity
    # Interest coverage: EBITDA / Interest >= min_interest_coverage
    # Max Interest = EBITDA / min_interest_coverage
    max_interest = f.ebitda / min_interest_coverage

    # Weighted average cost of debt assumption
    avg_debt_cost = base_rate + 0.04  # ~9% blended
    max_debt_from_coverage = max_interest / avg_debt_cost

    if max_debt_from_coverage < max_debt_from_leverage:
        constraints.append(f"Interest coverage ({min_interest_coverage:.1f}x min) limits total debt")

    # Fixed charge coverage: (EBITDA - CapEx) / (Interest + Debt Service)
    cash_available = f.ebitda - f.capex

    # Binding constraint
    max_total_debt = min(max_debt_from_leverage, max_debt_from_coverage)

    # Allocate across tranches
    # Senior secured: up to 3.5x for most credits
    senior_secured_cap = f.ebitda * min(3.5, max_leverage)
    max_senior_secured = min(senior_secured_cap, max_total_debt)

    # Senior unsecured: additional 1.0-1.5x
    remaining_after_secured = max_total_debt - max_senior_secured
    max_senior_unsecured = min(f.ebitda * 1.5, max(0, remaining_after_secured))

    # Subordinated: stretch to max
    remaining_after_unsecured = remaining_after_secured - max_senior_unsecured
    max_subordinated = max(0, remaining_after_unsecured)

    # Build recommended structure
    recommended = build_optimal_structure(
        f.ebitda,
        max_total_debt,
        base_rate,
        f.asset_light
    )

    # Calculate coverage with recommended structure
    total_interest = sum(
        amt * (base_rate + DEBT_INSTRUMENTS[inst]["spread"])
        for inst, amt in recommended.items()
        if amt > 0
    )

    interest_coverage = f.ebitda / total_interest if total_interest > 0 else float('inf')

    # Fixed charge coverage
    mandatory_amort = sum(
        amt * DEBT_INSTRUMENTS[inst].get("typical_amort", 0)
        for inst, amt in recommended.items()
    )
    total_fixed_charges = total_interest + mandatory_amort
    fixed_charge_coverage = cash_available / total_fixed_charges if total_fixed_charges > 0 else float('inf')

    # Risk assessment
    debt_to_ebitda = max_total_debt / f.ebitda

    if debt_to_ebitda <= industry_bench["low"]:
        risk = "Low - Conservative leverage within industry norms"
    elif debt_to_ebitda <= industry_bench["mid"]:
        risk = "Moderate - Average leverage for the sector"
    elif debt_to_ebitda <= industry_bench["high"]:
        risk = "Elevated - Above-average leverage, limited cushion"
    else:
        risk = "High - Leverage exceeds typical market levels"

    return DebtCapacityResult(
        max_total_debt=max_total_debt,
        max_senior_secured=max_senior_secured,
        max_senior_unsecured=max_senior_unsecured,
        max_subordinated=max_subordinated,
        interest_coverage=interest_coverage,
        fixed_charge_coverage=fixed_charge_coverage,
        debt_to_ebitda=debt_to_ebitda,
        recommended_structure=recommended,
        total_interest_expense=total_interest,
        capacity_constraints=constraints,
        risk_assessment=risk,
    )


def build_optimal_structure(
    ebitda: float,
    target_debt: float,
    base_rate: float,
    asset_light: bool = False
) -> Dict[str, float]:
    """
    Build optimal debt structure given target debt amount.

    Prioritizes cheaper senior debt, then layers in junior capital.

    Args:
        ebitda: Company EBITDA
        target_debt: Total debt target
        base_rate: Base interest rate
        asset_light: Whether company is asset-light

    Returns:
        Dict mapping instrument to amount
    """
    structure = {k: 0.0 for k in DEBT_INSTRUMENTS.keys()}
    remaining = target_debt

    # Layer 1: Term Loan B (most common in sponsor deals)
    if not asset_light:
        tlb_max = ebitda * DEBT_INSTRUMENTS["term_loan_b"]["max_leverage"]
        tlb_amount = min(remaining, tlb_max)
        structure["term_loan_b"] = tlb_amount
        remaining -= tlb_amount
    else:
        # Asset-light uses more unsecured
        tla_max = ebitda * 2.0
        structure["term_loan_a"] = min(remaining, tla_max)
        remaining -= structure["term_loan_a"]

    if remaining <= 0:
        return structure

    # Layer 2: Second lien or senior notes
    second_lien_max = ebitda * 1.5
    structure["second_lien"] = min(remaining, second_lien_max)
    remaining -= structure["second_lien"]

    if remaining <= 0:
        return structure

    # Layer 3: Mezzanine for remaining
    structure["mezzanine"] = remaining

    return structure


def analyze_refinancing_options(
    current_debt: float,
    current_rate: float,
    ebitda: float,
    years_remaining: int = 5
) -> List[Dict]:
    """
    Analyze refinancing options and savings.

    Args:
        current_debt: Current debt balance
        current_rate: Current blended interest rate
        ebitda: Current EBITDA
        years_remaining: Years remaining on current debt

    Returns:
        List of refinancing options with analysis
    """
    options = []
    current_interest = current_debt * current_rate

    # Option 1: Term Loan B refinancing
    tlb_rate = 0.055 + DEBT_INSTRUMENTS["term_loan_b"]["spread"]
    tlb_interest = current_debt * tlb_rate
    tlb_savings = (current_interest - tlb_interest) * years_remaining

    options.append({
        "option": "Term Loan B Refinancing",
        "new_rate": tlb_rate,
        "annual_savings": current_interest - tlb_interest,
        "total_savings": tlb_savings,
        "recommendation": "Recommended" if tlb_savings > 0 else "Not advantageous",
    })

    # Option 2: High-yield bond
    hy_rate = 0.075
    hy_interest = current_debt * hy_rate
    hy_savings = (current_interest - hy_interest) * years_remaining

    options.append({
        "option": "High-Yield Bond Issuance",
        "new_rate": hy_rate,
        "annual_savings": current_interest - hy_interest,
        "total_savings": hy_savings,
        "recommendation": "Consider if seeking covenant flexibility",
    })

    # Option 3: Add-on equity and delever
    delever_target = ebitda * 3.5
    equity_needed = current_debt - delever_target

    if equity_needed > 0:
        new_interest = delever_target * 0.08
        options.append({
            "option": f"Deleverage with ${equity_needed:.0f}M equity",
            "new_rate": 0.08,
            "annual_savings": current_interest - new_interest,
            "equity_required": equity_needed,
            "recommendation": "Consider if targeting credit upgrade",
        })

    return options


def generate_structure_report(financials: CompanyFinancials) -> str:
    """
    Generate formatted capital structure analysis report.

    Args:
        financials: Company financial data

    Returns:
        Markdown formatted report
    """
    result = calculate_debt_capacity(financials)
    industry_bench = INDUSTRY_LEVERAGE.get(
        financials.industry,
        INDUSTRY_LEVERAGE[Industry.INDUSTRIALS]
    )

    report = f"""## Capital Structure Analysis

### Company Overview
| Metric | Value |
|--------|-------|
| EBITDA | ${financials.ebitda:,.0f}M |
| Revenue | ${financials.revenue:,.0f}M |
| Industry | {financials.industry.value.title()} |
| Existing Debt | ${financials.existing_debt:,.0f}M |

### Debt Capacity Summary
| Metric | Amount | Multiple |
|--------|--------|----------|
| **Max Total Debt** | **${result.max_total_debt:,.0f}M** | **{result.debt_to_ebitda:.1f}x** |
| Max Senior Secured | ${result.max_senior_secured:,.0f}M | {result.max_senior_secured/financials.ebitda:.1f}x |
| Max Senior Unsecured | ${result.max_senior_unsecured:,.0f}M | {result.max_senior_unsecured/financials.ebitda:.1f}x |
| Max Subordinated | ${result.max_subordinated:,.0f}M | {result.max_subordinated/financials.ebitda:.1f}x |

### Industry Benchmarks ({financials.industry.value.title()})
| Leverage Level | Debt/EBITDA |
|----------------|-------------|
| Conservative | {industry_bench['low']:.1f}x |
| Moderate | {industry_bench['mid']:.1f}x |
| Aggressive | {industry_bench['high']:.1f}x |

### Recommended Structure
| Instrument | Amount | Rate | Annual Interest |
|------------|--------|------|-----------------|
"""

    total_debt = 0
    for inst, amount in result.recommended_structure.items():
        if amount > 0:
            rate = 0.055 + DEBT_INSTRUMENTS[inst]["spread"]
            interest = amount * rate
            report += f"| {DEBT_INSTRUMENTS[inst]['name']} | ${amount:,.0f}M | {rate*100:.1f}% | ${interest:,.1f}M |\n"
            total_debt += amount

    report += f"| **Total** | **${total_debt:,.0f}M** | - | **${result.total_interest_expense:,.1f}M** |\n"

    report += f"""
### Coverage Ratios
| Ratio | Value | Minimum |
|-------|-------|---------|
| Interest Coverage | {result.interest_coverage:.1f}x | 2.0x |
| Fixed Charge Coverage | {result.fixed_charge_coverage:.1f}x | 1.2x |
| Debt / EBITDA | {result.debt_to_ebitda:.1f}x | - |

### Risk Assessment
**{result.risk_assessment}**

### Capacity Constraints
"""

    if result.capacity_constraints:
        for constraint in result.capacity_constraints:
            report += f"- {constraint}\n"
    else:
        report += "- No binding constraints identified\n"

    return report


if __name__ == "__main__":
    # Example usage
    print("=" * 60)
    print("Capital Structure Analyzer - Example Analysis")
    print("=" * 60)

    # Sample company
    company = CompanyFinancials(
        ebitda=75.0,
        revenue=500.0,
        capex=25.0,
        existing_debt=150.0,
        cash=20.0,
        industry=Industry.BUSINESS_SERVICES,
        revenue_volatility="moderate",
        customer_concentration="low",
    )

    print(generate_structure_report(company))
