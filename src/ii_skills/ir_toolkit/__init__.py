"""
Infrastructure Investor Relations Toolkit

A comprehensive toolkit for infrastructure fund investor relations,
including LP updates, fundraising decks, and DDQ responses.

Core Principle: Every Excel analysis has a corresponding PowerPoint slide.

Usage:
    from ii_skills.ir_toolkit import IRToolkit, IRCaseType

    toolkit = IRToolkit(user_id="user123")
    result = await toolkit.generate_lp_update(
        fund_name="Global Infrastructure Fund IV",
        reporting_period="Q4 2025",
    )

Module Categories:
    - Fund Overview (snapshot, performance, composition, leverage)
    - Cash Flows (waterfall, IRR bridge, coverage)
    - Asset Performance (KPIs, revenue quality, capex, contracts)
    - Valuation (NAV, sensitivity, macro)
    - Risk (register, regulatory calendar)
    - ESG (impact metrics)
    - Fundraising (pipeline, LP coverage, DDQ, terms)
"""

from ii_skills.ir_toolkit.ir_orchestrator import (
    IRToolkit,
    IRCaseType,
    IRPhase,
    IRTaskStatus,
    IRState,
    IRModule,
    IRProgressCallback,
    ConsoleIRProgressCallback,
    LP_UPDATE_MODULES,
    FUNDRAISING_MODULES,
    DDQ_MODULES,
)

from ii_skills.ir_toolkit.excel_generator import (
    IRExcelGenerator,
    TableSpec,
)

from ii_skills.ir_toolkit.pptx_generator import (
    IRSlideGenerator,
    SLIDE_SPECS,
    generate_ir_deck,
)

__all__ = [
    # Orchestrator
    "IRToolkit",
    "IRCaseType",
    "IRPhase",
    "IRTaskStatus",
    "IRState",
    "IRModule",
    "IRProgressCallback",
    "ConsoleIRProgressCallback",
    # Module definitions
    "LP_UPDATE_MODULES",
    "FUNDRAISING_MODULES",
    "DDQ_MODULES",
    # Generators
    "IRExcelGenerator",
    "IRSlideGenerator",
    "TableSpec",
    "SLIDE_SPECS",
    "generate_ir_deck",
]

__version__ = "1.0.0"
