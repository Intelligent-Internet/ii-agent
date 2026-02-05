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

# Phase 1: Ontology, Evidence, IR Events (guarded imports)
try:
    from ii_skills.ir_toolkit.ontology import (
        InfraOntology,
        OntologyTagger,
        SemanticTag,
        TaggedElement,
        check_jargon_consistency,
        check_metric_definitions,
        ASSET_CLASSES,
        REVENUE_PROFILES,
        FINANCING_TERMS,
        OPERATIONS_TERMS,
    )
    __all__.extend([
        "InfraOntology", "OntologyTagger", "SemanticTag", "TaggedElement",
        "check_jargon_consistency", "check_metric_definitions",
        "ASSET_CLASSES", "REVENUE_PROFILES", "FINANCING_TERMS", "OPERATIONS_TERMS",
    ])
except ImportError:
    pass

try:
    from ii_skills.ir_toolkit.evidence import (
        ClaimEvidenceTracker,
        EvidenceNode,
        Claim,
        Recommendation,
        EvidenceQualityReport,
        ClaimCategory,
        SourceType,
        ConflictType,
        RecommendationPriority,
    )
    __all__.extend([
        "ClaimEvidenceTracker", "EvidenceNode", "Claim", "Recommendation",
        "EvidenceQualityReport", "ClaimCategory", "SourceType",
        "ConflictType", "RecommendationPriority",
    ])
except ImportError:
    pass

try:
    from ii_skills.ir_toolkit.ir_events import (
        DocExtractedPayload,
        KPIReconciledPayload,
        TermRiskFlaggedPayload,
        IRTelemetryExtensions,
        register_ir_events,
        compute_ir_telemetry,
        DocumentClass,
        ReconciliationStatus,
        TermRiskType,
        NegotiationPriority,
    )
    __all__.extend([
        "DocExtractedPayload", "KPIReconciledPayload", "TermRiskFlaggedPayload",
        "IRTelemetryExtensions", "register_ir_events", "compute_ir_telemetry",
        "DocumentClass", "ReconciliationStatus", "TermRiskType", "NegotiationPriority",
    ])
except ImportError:
    pass

__version__ = "1.0.0"
