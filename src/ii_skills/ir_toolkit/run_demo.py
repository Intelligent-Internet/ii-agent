"""
IR Toolkit Demo Runner

Demonstrates the IR toolkit capabilities with sample data.

Usage:
    python -m ii_skills.ir_toolkit.run_demo

    # Or from src directory:
    python ii_skills/ir_toolkit/run_demo.py
"""

import asyncio
import sys
from pathlib import Path

# Add src to path for imports
src_dir = Path(__file__).parent.parent.parent
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

from ii_skills.ir_toolkit import (
    IRToolkit,
    IRCaseType,
    ConsoleIRProgressCallback,
)


# Sample fund data for demo
SAMPLE_FUND_DATA = {
    "fund_name": "Global Infrastructure Fund IV",
    "vintage": 2022,
    "fund_size": 2500000000,  # $2.5B
    "strategy": "Core/Core+ Infrastructure",
    "geography": "Global (Americas 40%, Europe 35%, APAC 25%)",
    "sectors": ["Energy Transition", "Digital Infrastructure", "Transportation", "Utilities"],

    # Performance metrics
    "net_irr": 0.142,  # 14.2%
    "gross_irr": 0.168,  # 16.8%
    "dpi": 0.35,
    "rvpi": 1.28,
    "tvpi": 1.63,

    # Capital metrics
    "committed_capital": 2500000000,
    "called_capital": 1875000000,  # 75% called
    "distributed": 656250000,  # 35% DPI
    "nav": 2400000000,

    # Cash flows
    "cash_flows": [
        {"period": "Q1 2023", "calls": 250000000, "distributions": 50000000},
        {"period": "Q2 2023", "calls": 200000000, "distributions": 75000000},
        {"period": "Q3 2023", "calls": 175000000, "distributions": 100000000},
        {"period": "Q4 2023", "calls": 150000000, "distributions": 125000000},
        {"period": "Q1 2024", "calls": 100000000, "distributions": 80000000},
        {"period": "Q2 2024", "calls": 75000000, "distributions": 90000000},
        {"period": "Q3 2024", "calls": 50000000, "distributions": 70000000},
        {"period": "Q4 2024", "calls": 25000000, "distributions": 66250000},
    ],
}

SAMPLE_ASSET_DATA = {
    "assets": [
        {
            "name": "Nordic Wind Portfolio",
            "sector": "Energy Transition",
            "region": "Europe",
            "investment_date": "2022-06-15",
            "investment_amount": 450000000,
            "current_nav": 580000000,
            "availability": 0.968,
            "capacity_factor": 0.42,
            "contracted_revenue_pct": 0.85,
            "wacl": 12.5,  # Weighted avg contract life
        },
        {
            "name": "US Data Center Platform",
            "sector": "Digital Infrastructure",
            "region": "Americas",
            "investment_date": "2022-09-01",
            "investment_amount": 600000000,
            "current_nav": 780000000,
            "availability": 0.9995,
            "utilization": 0.78,
            "contracted_revenue_pct": 0.92,
            "wacl": 8.2,
        },
        {
            "name": "Australia Toll Roads",
            "sector": "Transportation",
            "region": "APAC",
            "investment_date": "2023-01-15",
            "investment_amount": 350000000,
            "current_nav": 410000000,
            "traffic_growth": 0.045,
            "inflation_linkage": 0.75,
            "concession_remaining": 28,  # years
        },
        {
            "name": "UK Water Utility",
            "sector": "Utilities",
            "region": "Europe",
            "investment_date": "2023-06-01",
            "investment_amount": 400000000,
            "current_nav": 520000000,
            "rab_growth": 0.062,
            "allowed_roe": 0.095,
            "regulatory_reset": 2029,
        },
    ],
}


async def run_lp_update_demo():
    """Run LP quarterly update demo."""
    print("\n" + "=" * 60)
    print("IR TOOLKIT DEMO: LP Quarterly Update")
    print("=" * 60)

    output_dir = Path(__file__).parent / "outputs" / "demo_lp_update"

    toolkit = IRToolkit(
        user_id="demo_user",
        output_dir=str(output_dir),
        progress_callback=ConsoleIRProgressCallback(),
    )

    result = await toolkit.generate_lp_update(
        fund_name="Global Infrastructure Fund IV",
        reporting_period="Q4 2024",
        fund_data=SAMPLE_FUND_DATA,
        asset_data=SAMPLE_ASSET_DATA,
    )

    print("\n" + "-" * 60)
    print("RESULTS")
    print("-" * 60)
    print(f"Case ID: {result.case_id}")
    print(f"Fund: {result.fund_name}")
    print(f"Period: {result.reporting_period}")
    print(f"Excel outputs: {len(result.excel_outputs)}")
    print(f"Slide outputs: {len(result.slide_outputs)}")
    print(f"Output directory: {output_dir}")

    return result


async def run_fundraising_demo():
    """Run fundraising deck demo."""
    print("\n" + "=" * 60)
    print("IR TOOLKIT DEMO: Fundraising Deck")
    print("=" * 60)

    output_dir = Path(__file__).parent / "outputs" / "demo_fundraising"

    toolkit = IRToolkit(
        user_id="demo_user",
        output_dir=str(output_dir),
        progress_callback=ConsoleIRProgressCallback(),
    )

    result = await toolkit.generate_fundraising_deck(
        fund_name="Global Infrastructure Fund V",
        fund_data={
            **SAMPLE_FUND_DATA,
            "fund_name": "Global Infrastructure Fund V",
            "target_size": 3500000000,  # $3.5B target
            "vintage": 2025,
        },
        asset_data=SAMPLE_ASSET_DATA,
    )

    print("\n" + "-" * 60)
    print("RESULTS")
    print("-" * 60)
    print(f"Case ID: {result.case_id}")
    print(f"Excel outputs: {len(result.excel_outputs)}")
    print(f"Slide outputs: {len(result.slide_outputs)}")

    return result


async def run_ddq_demo():
    """Run DDQ response demo."""
    print("\n" + "=" * 60)
    print("IR TOOLKIT DEMO: DDQ Response")
    print("=" * 60)

    output_dir = Path(__file__).parent / "outputs" / "demo_ddq"

    toolkit = IRToolkit(
        user_id="demo_user",
        output_dir=str(output_dir),
        progress_callback=ConsoleIRProgressCallback(),
    )

    result = await toolkit.generate_ddq_response(
        fund_name="Global Infrastructure Fund IV",
        fund_data=SAMPLE_FUND_DATA,
    )

    print("\n" + "-" * 60)
    print("RESULTS")
    print("-" * 60)
    print(f"Case ID: {result.case_id}")
    print(f"Excel outputs: {len(result.excel_outputs)}")
    print(f"Slide outputs: {len(result.slide_outputs)}")

    return result


async def run_phase1_demo():
    """
    Demonstrate Phase 1 features: Ontology tagging, Evidence tracking, IR telemetry.
    """
    print("\n" + "=" * 60)
    print("PHASE 1 DEMO: Ontology + Evidence + Telemetry")
    print("=" * 60)

    # ── Part A: Ontology-enabled LP update ──────────────────────
    print("\n--- Part A: LP Update with Ontology Tagging ---")
    output_dir = Path(__file__).parent / "outputs" / "demo_phase1"

    toolkit = IRToolkit(
        user_id="demo_user",
        output_dir=str(output_dir),
        progress_callback=ConsoleIRProgressCallback(),
        enable_ontology=True,
        enable_evidence=True,
    )

    result = await toolkit.generate_lp_update(
        fund_name="Global Infrastructure Fund IV",
        reporting_period="Q4 2025",
        fund_data=SAMPLE_FUND_DATA,
        asset_data=SAMPLE_ASSET_DATA,
    )

    # Print ontology tag counts per module
    print("\n--- Ontology Tags per Module ---")
    for module_id, tags in result.ontology_tags.items():
        total_tags = sum(len(t.get("tags", [])) for t in tags)
        print(f"  {module_id}: {len(tags)} elements, {total_tags} tags")

    # ── Part B: ClaimEvidenceTracker demo ───────────────────────
    print("\n--- Part B: Claim-Evidence Tracker ---")
    from ii_skills.ir_toolkit.evidence import ClaimEvidenceTracker, ExtractedValue

    tracker = ClaimEvidenceTracker()

    # Add evidence
    ev1 = tracker.add_evidence(
        source_document="BIP Q3 2025 Supplemental Information",
        source_type="sec_filing",
        section="p.12, Segment Overview — Utilities",
        period="Q3 2025",
        extracted_text="Cash yield of 8.2% across utilities segment",
        extracted_value=ExtractedValue(
            metric="cash_yield", value=8.2, unit="%", period="Q3 2025",
        ),
    )
    ev2 = tracker.add_evidence(
        source_document="Fund IV Quarterly Letter Q3 2025",
        source_type="quarterly_letter",
        section="Performance Highlights",
        period="Q3 2025",
        extracted_text="Net IRR of 14.2% since inception",
        extracted_value=ExtractedValue(
            metric="net_irr", value=14.2, unit="%", period="Q3 2025",
        ),
    )
    ev3 = tracker.add_evidence(
        source_document="Cambridge Benchmark Q2 2025",
        source_type="benchmark_report",
        period="Q2 2025",
        extracted_text="Median infra fund IRR of 11.5%",
    )

    print(f"  Added {ev1.evidence_id}, {ev2.evidence_id}, {ev3.evidence_id}")

    # Add claims (including one uncited to demonstrate validation)
    c1 = tracker.add_claim(
        text="Fund IV cash yield remains above 8% supported by contracted revenue",
        confidence=0.9,
        category="cash_flow",
        evidence_ids=[ev1.evidence_id],
        output_location="Executive Summary Slide, bullet 2",
    )
    c2 = tracker.add_claim(
        text="Net IRR of 14.2% exceeds benchmark median by 270bps",
        confidence=0.85,
        category="performance",
        evidence_ids=[ev2.evidence_id, ev3.evidence_id],
        output_location="Performance Slide, headline",
    )
    c3 = tracker.add_claim(
        text="Portfolio resilience driven by regulatory protections",
        confidence=0.4,
        category="outlook",
        evidence_ids=[],  # Intentionally uncited
        output_location="Outlook Slide, bullet 1",
    )
    print(f"  Added {c1.claim_id} (cited, high conf)")
    print(f"  Added {c2.claim_id} (cited, high conf)")
    print(f"  Added {c3.claim_id} (UNCITED, low conf)")

    # Add a recommendation
    rec = tracker.add_recommendation(
        text="Highlight cash yield resilience in LP letter; flag benchmark comparison",
        priority="important",
        supporting_claim_ids=[c1.claim_id, c2.claim_id],
        action_owner="IR Team Lead",
    )
    print(f"  Added {rec.recommendation_id}")

    # Validate
    report = tracker.validate(current_period="Q4 2025")
    print("\n--- Evidence Quality Report ---")
    print(f"  Total claims:        {report.total_claims}")
    print(f"  Cited claims:        {report.cited_claims}")
    print(f"  Uncited claims:      {report.uncited_claims}")
    print(f"  Coverage ratio:      {report.evidence_coverage_ratio:.1%}")
    print(f"  Low-conf claims:     {report.low_confidence_claim_count}")
    print(f"  Stale evidence:      {report.stale_evidence_count}")
    print(f"  Overall passed:      {report.passed}")
    print(f"  Quality score:       {tracker.get_quality_score():.2f}")

    print("\n  Rule results:")
    for r in report.rule_results:
        status = "PASS" if r.passed else "FAIL"
        print(f"    [{r.enforcement.upper():9s}] [{status}] {r.metric_name}={r.metric_value}")

    # ── Part C: Serialization round-trip ────────────────────────
    print("\n--- Part C: Serialization Round-Trip ---")
    serialized = tracker.to_dict()
    restored = ClaimEvidenceTracker.from_dict(serialized)
    print(f"  Claims preserved: {len(restored._claims)}")
    print(f"  Evidence preserved: {len(restored._evidence)}")
    print(f"  Recommendations preserved: {len(restored._recommendations)}")

    print("\n" + "=" * 60)
    print("PHASE 1 DEMO COMPLETE")
    print("=" * 60)


async def main():
    """Run all demos."""
    print("\n" + "#" * 60)
    print("# INFRASTRUCTURE IR TOOLKIT - DEMO")
    print("#" * 60)

    # Run LP update
    await run_lp_update_demo()

    # Run Phase 1 demo (ontology + evidence)
    await run_phase1_demo()

    # Run fundraising (more modules)
    # await run_fundraising_demo()

    # Run DDQ (focused subset)
    # await run_ddq_demo()

    print("\n" + "#" * 60)
    print("# DEMO COMPLETE")
    print("#" * 60)


if __name__ == "__main__":
    asyncio.run(main())
