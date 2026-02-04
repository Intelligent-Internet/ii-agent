#!/usr/bin/env python3
"""
Quality of Earnings (QoE) Analyzer Module

EBITDA normalization and quality of earnings analysis framework based on
Private Equity due diligence best practices.

Key concepts:
- One-time vs recurring adjustments
- Run-rate adjustments for recent changes
- Pro forma adjustments for acquisitions/divestitures
- Management adjustment scrutiny
"""

from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime


class AdjustmentCategory(Enum):
    """Categories of EBITDA adjustments."""
    ONE_TIME = "one_time"              # Non-recurring items
    RUN_RATE = "run_rate"              # Annualize partial-year items
    PRO_FORMA = "pro_forma"            # M&A related
    ACCOUNTING = "accounting"          # Accounting policy changes
    RELATED_PARTY = "related_party"    # Related party transactions
    OWNER_BENEFIT = "owner_benefit"    # Owner/sponsor add-backs
    SYNERGY = "synergy"                # Expected synergies (buyer)


class AdjustmentRisk(Enum):
    """Risk level of adjustment acceptance."""
    LOW = "low"           # Well-documented, verifiable
    MODERATE = "moderate" # Reasonable but requires validation
    HIGH = "high"         # Aggressive, may not be accepted


@dataclass
class EBITDAAdjustment:
    """Individual EBITDA adjustment."""
    description: str
    amount: float
    category: AdjustmentCategory
    risk: AdjustmentRisk = AdjustmentRisk.MODERATE
    supporting_docs: List[str] = field(default_factory=list)
    buyer_likely_accepts: bool = True
    notes: str = ""


@dataclass
class QoEAnalysis:
    """Complete Quality of Earnings analysis."""
    # Reported figures
    reported_revenue: float
    reported_ebitda: float

    # Adjustments
    adjustments: List[EBITDAAdjustment]

    # Analysis period
    period: str  # e.g., "LTM Q3 2025"

    # Company info
    company_name: str = "Target"

    def adjusted_ebitda(self) -> float:
        """Calculate fully adjusted EBITDA."""
        return self.reported_ebitda + sum(adj.amount for adj in self.adjustments)

    def buyer_adjusted_ebitda(self) -> float:
        """Calculate EBITDA with only buyer-accepted adjustments."""
        accepted = [adj for adj in self.adjustments if adj.buyer_likely_accepts]
        return self.reported_ebitda + sum(adj.amount for adj in accepted)

    def adjustments_by_category(self) -> Dict[AdjustmentCategory, float]:
        """Sum adjustments by category."""
        by_cat = {}
        for adj in self.adjustments:
            by_cat[adj.category] = by_cat.get(adj.category, 0) + adj.amount
        return by_cat

    def low_risk_adjustments(self) -> float:
        """Sum of low-risk adjustments."""
        return sum(adj.amount for adj in self.adjustments if adj.risk == AdjustmentRisk.LOW)

    def high_risk_adjustments(self) -> float:
        """Sum of high-risk adjustments."""
        return sum(adj.amount for adj in self.adjustments if adj.risk == AdjustmentRisk.HIGH)


# Common adjustment templates
COMMON_ADJUSTMENTS = {
    "restructuring": {
        "description": "Restructuring charges",
        "category": AdjustmentCategory.ONE_TIME,
        "risk": AdjustmentRisk.LOW,
        "notes": "Severance, facility closure costs - typically accepted if documented",
    },
    "litigation": {
        "description": "Litigation settlement/legal fees",
        "category": AdjustmentCategory.ONE_TIME,
        "risk": AdjustmentRisk.MODERATE,
        "notes": "Accepted if truly one-time; recurring legal costs should not be added back",
    },
    "transaction_costs": {
        "description": "M&A transaction costs",
        "category": AdjustmentCategory.ONE_TIME,
        "risk": AdjustmentRisk.LOW,
        "notes": "Investment banking, legal, accounting fees for the transaction",
    },
    "stock_comp": {
        "description": "Stock-based compensation",
        "category": AdjustmentCategory.ACCOUNTING,
        "risk": AdjustmentRisk.MODERATE,
        "notes": "Standard add-back but some buyers view as real expense",
    },
    "management_fees": {
        "description": "Sponsor management fees",
        "category": AdjustmentCategory.OWNER_BENEFIT,
        "risk": AdjustmentRisk.LOW,
        "notes": "Fees paid to PE sponsor - will not continue post-transaction",
    },
    "owner_comp": {
        "description": "Above-market owner compensation",
        "category": AdjustmentCategory.OWNER_BENEFIT,
        "risk": AdjustmentRisk.MODERATE,
        "notes": "Excess compensation to owner/family - normalized to market rate",
    },
    "public_company_costs": {
        "description": "Public company costs (going private)",
        "category": AdjustmentCategory.RUN_RATE,
        "risk": AdjustmentRisk.LOW,
        "notes": "Board fees, D&O insurance, SEC reporting costs",
    },
    "acquisition_synergies": {
        "description": "Expected acquisition synergies",
        "category": AdjustmentCategory.SYNERGY,
        "risk": AdjustmentRisk.HIGH,
        "notes": "Buyer-specific; typically haircut 50-75%",
    },
    "new_contract": {
        "description": "Run-rate of new contract/customer",
        "category": AdjustmentCategory.RUN_RATE,
        "risk": AdjustmentRisk.MODERATE,
        "notes": "Annualize partial-year impact of new business won",
    },
    "cost_savings": {
        "description": "Implemented cost savings run-rate",
        "category": AdjustmentCategory.RUN_RATE,
        "risk": AdjustmentRisk.MODERATE,
        "notes": "Must be verifiable with bank statements/payroll",
    },
    "covid_impact": {
        "description": "COVID-19 related costs/impacts",
        "category": AdjustmentCategory.ONE_TIME,
        "risk": AdjustmentRisk.HIGH,
        "notes": "Increasingly scrutinized; must demonstrate truly one-time",
    },
    "facility_move": {
        "description": "Facility relocation costs",
        "category": AdjustmentCategory.ONE_TIME,
        "risk": AdjustmentRisk.LOW,
        "notes": "Moving costs, duplicate rent - typically accepted",
    },
    "erp_implementation": {
        "description": "ERP/system implementation costs",
        "category": AdjustmentCategory.ONE_TIME,
        "risk": AdjustmentRisk.MODERATE,
        "notes": "Implementation consulting; ongoing maintenance not added back",
    },
}


def create_adjustment(
    template_name: str,
    amount: float,
    custom_description: str = None,
    **kwargs
) -> EBITDAAdjustment:
    """
    Create an adjustment from a template.

    Args:
        template_name: Key from COMMON_ADJUSTMENTS
        amount: Adjustment amount (positive = add-back)
        custom_description: Override default description
        **kwargs: Override other template values

    Returns:
        EBITDAAdjustment instance
    """
    template = COMMON_ADJUSTMENTS.get(template_name, {})

    return EBITDAAdjustment(
        description=custom_description or template.get("description", template_name),
        amount=amount,
        category=kwargs.get("category", template.get("category", AdjustmentCategory.ONE_TIME)),
        risk=kwargs.get("risk", template.get("risk", AdjustmentRisk.MODERATE)),
        notes=kwargs.get("notes", template.get("notes", "")),
        buyer_likely_accepts=kwargs.get("buyer_likely_accepts", True),
    )


def analyze_management_adjustments(
    management_ebitda: float,
    reported_ebitda: float,
    adjustments: List[EBITDAAdjustment]
) -> Dict:
    """
    Analyze gap between management's adjusted EBITDA and QoE findings.

    Args:
        management_ebitda: Management's claimed adjusted EBITDA
        reported_ebitda: GAAP/IFRS reported EBITDA
        adjustments: List of validated adjustments

    Returns:
        Analysis of the "EBITDA gap"
    """
    validated_ebitda = reported_ebitda + sum(adj.amount for adj in adjustments)
    gap = management_ebitda - validated_ebitda

    # Categorize risk
    gap_pct = abs(gap) / reported_ebitda if reported_ebitda else 0

    if gap_pct < 0.05:
        risk_level = "Low"
        recommendation = "Minor gap - reasonable alignment"
    elif gap_pct < 0.15:
        risk_level = "Moderate"
        recommendation = "Material gap - requires negotiation on specific items"
    else:
        risk_level = "High"
        recommendation = "Significant gap - major valuation risk"

    return {
        "management_ebitda": management_ebitda,
        "validated_ebitda": validated_ebitda,
        "gap": gap,
        "gap_percentage": gap_pct,
        "risk_level": risk_level,
        "recommendation": recommendation,
        "high_risk_items": [adj for adj in adjustments if adj.risk == AdjustmentRisk.HIGH],
    }


def generate_due_diligence_questions(adjustments: List[EBITDAAdjustment]) -> List[str]:
    """
    Generate due diligence questions based on adjustments.

    Args:
        adjustments: List of proposed adjustments

    Returns:
        List of DD questions to ask
    """
    questions = []

    # Standard questions
    questions.append("Please provide a detailed EBITDA bridge from reported to adjusted figures")
    questions.append("What is the source documentation for each adjustment?")

    # Category-specific questions
    for adj in adjustments:
        if adj.category == AdjustmentCategory.ONE_TIME:
            questions.append(f"For '{adj.description}': Please confirm this cost did not recur in prior periods and is not expected going forward")

        elif adj.category == AdjustmentCategory.RUN_RATE:
            questions.append(f"For '{adj.description}': Please provide monthly detail to support annualization")

        elif adj.category == AdjustmentCategory.PRO_FORMA:
            questions.append(f"For '{adj.description}': Please provide standalone financials for the acquired entity")

        elif adj.category == AdjustmentCategory.SYNERGY:
            questions.append(f"For '{adj.description}': What is the implementation timeline and cost to achieve?")

        if adj.risk == AdjustmentRisk.HIGH:
            questions.append(f"HIGH RISK - '{adj.description}': Please provide third-party verification or bank statements")

    return questions


def generate_qoe_report(analysis: QoEAnalysis) -> str:
    """
    Generate formatted Quality of Earnings report.

    Args:
        analysis: QoEAnalysis instance

    Returns:
        Markdown formatted report
    """
    by_category = analysis.adjustments_by_category()
    total_adjustments = sum(adj.amount for adj in analysis.adjustments)

    report = f"""## Quality of Earnings Analysis: {analysis.company_name}

### Period: {analysis.period}

### EBITDA Bridge
| Line Item | Amount |
|-----------|--------|
| Reported EBITDA | ${analysis.reported_ebitda:,.0f}M |
"""

    # Add adjustments by category
    for cat in AdjustmentCategory:
        if cat in by_category:
            report += f"| {cat.value.replace('_', ' ').title()} Adjustments | ${by_category[cat]:,.0f}M |\n"

    report += f"""| **Total Adjustments** | **${total_adjustments:,.0f}M** |
| **Adjusted EBITDA** | **${analysis.adjusted_ebitda():,.0f}M** |
| Buyer-Accepted EBITDA | ${analysis.buyer_adjusted_ebitda():,.0f}M |

### Adjustment Summary
| Metric | Value |
|--------|-------|
| Reported EBITDA Margin | {analysis.reported_ebitda/analysis.reported_revenue*100:.1f}% |
| Adjusted EBITDA Margin | {analysis.adjusted_ebitda()/analysis.reported_revenue*100:.1f}% |
| Total Adjustments | ${total_adjustments:,.0f}M ({total_adjustments/analysis.reported_ebitda*100:.1f}% of reported) |
| Low Risk Adjustments | ${analysis.low_risk_adjustments():,.0f}M |
| High Risk Adjustments | ${analysis.high_risk_adjustments():,.0f}M |

### Detailed Adjustments
| Description | Amount | Category | Risk | Notes |
|-------------|--------|----------|------|-------|
"""

    for adj in sorted(analysis.adjustments, key=lambda x: -abs(x.amount)):
        risk_emoji = {"low": "LOW", "moderate": "MOD", "high": "HIGH"}[adj.risk.value]
        report += f"| {adj.description} | ${adj.amount:,.1f}M | {adj.category.value} | {risk_emoji} | {adj.notes[:50]} |\n"

    # Risk assessment
    high_risk_total = analysis.high_risk_adjustments()
    high_risk_pct = high_risk_total / total_adjustments if total_adjustments else 0

    if high_risk_pct > 0.3:
        risk_assessment = "HIGH RISK: Over 30% of adjustments are high-risk items requiring significant validation"
    elif high_risk_pct > 0.15:
        risk_assessment = "MODERATE RISK: Material high-risk adjustments present; focused DD recommended"
    else:
        risk_assessment = "LOW RISK: Adjustments are well-supported with limited high-risk items"

    report += f"""
### Risk Assessment
**{risk_assessment}**

### Key Due Diligence Questions
"""

    questions = generate_due_diligence_questions(analysis.adjustments)
    for i, q in enumerate(questions[:10], 1):
        report += f"{i}. {q}\n"

    return report


def quick_qoe(
    revenue: float,
    reported_ebitda: float,
    adjustments: List[Tuple[str, float, str]] = None
) -> Dict:
    """
    Quick QoE analysis.

    Args:
        revenue: Reported revenue
        reported_ebitda: Reported EBITDA
        adjustments: List of (description, amount, risk) tuples

    Returns:
        Quick QoE summary dict
    """
    adj_list = []
    for desc, amt, risk in (adjustments or []):
        adj_list.append(EBITDAAdjustment(
            description=desc,
            amount=amt,
            category=AdjustmentCategory.ONE_TIME,
            risk=AdjustmentRisk[risk.upper()],
        ))

    analysis = QoEAnalysis(
        reported_revenue=revenue,
        reported_ebitda=reported_ebitda,
        adjustments=adj_list,
        period="LTM",
    )

    return {
        "reported_ebitda": reported_ebitda,
        "adjusted_ebitda": analysis.adjusted_ebitda(),
        "total_adjustments": sum(a.amount for a in adj_list),
        "adjustment_pct": sum(a.amount for a in adj_list) / reported_ebitda if reported_ebitda else 0,
        "reported_margin": reported_ebitda / revenue if revenue else 0,
        "adjusted_margin": analysis.adjusted_ebitda() / revenue if revenue else 0,
    }


if __name__ == "__main__":
    # Example usage
    print("=" * 60)
    print("Quality of Earnings Analyzer - Example Analysis")
    print("=" * 60)

    # Create sample analysis
    adjustments = [
        create_adjustment("restructuring", 2.5, "Q2 restructuring - plant consolidation"),
        create_adjustment("transaction_costs", 1.8, "Sell-side M&A advisory fees"),
        create_adjustment("stock_comp", 3.2, "Employee stock compensation"),
        create_adjustment("management_fees", 1.5, "Annual sponsor monitoring fee"),
        create_adjustment("owner_comp", 0.8, "Excess owner compensation above market"),
        create_adjustment("new_contract", 2.0, "New Fortune 500 customer - partial year"),
        create_adjustment("covid_impact", 1.5, "COVID-related supply chain costs"),
    ]

    # Mark some as potentially not accepted
    adjustments[-1].buyer_likely_accepts = False  # COVID impacts increasingly scrutinized
    adjustments[-2].risk = AdjustmentRisk.MODERATE

    analysis = QoEAnalysis(
        company_name="Sample Manufacturing Co",
        period="LTM Q3 2025",
        reported_revenue=250.0,
        reported_ebitda=35.0,
        adjustments=adjustments,
    )

    print(generate_qoe_report(analysis))
