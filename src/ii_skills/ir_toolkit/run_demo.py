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


async def main():
    """Run all demos."""
    print("\n" + "#" * 60)
    print("# INFRASTRUCTURE IR TOOLKIT - DEMO")
    print("#" * 60)

    # Run LP update
    await run_lp_update_demo()

    # Run fundraising (more modules)
    # await run_fundraising_demo()

    # Run DDQ (focused subset)
    # await run_ddq_demo()

    print("\n" + "#" * 60)
    print("# DEMO COMPLETE")
    print("#" * 60)


if __name__ == "__main__":
    asyncio.run(main())
