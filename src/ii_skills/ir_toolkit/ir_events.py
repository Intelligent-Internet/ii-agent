"""
IR-Specific Event Payloads and Telemetry Extensions

Extends shared EventPayload with IR-specific events for document extraction,
KPI reconciliation, and term risk flagging. Graceful degradation if shared
schema is unavailable.

Usage:
    from ii_skills.ir_toolkit.ir_events import (
        DocExtractedPayload, KPIReconciledPayload, TermRiskFlaggedPayload,
        register_ir_events, compute_ir_telemetry, IRTelemetryExtensions,
    )

    register_ir_events()  # extend shared PAYLOAD_REGISTRY (idempotent)

    payload = DocExtractedPayload(
        run_id="abc123",
        document_class="sec_filing",
        document_name="BIP_Q3_2025.pdf",
        period="Q3 2025",
    )
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional, Any, Type

# Try to import shared EventPayload; fall back to standalone base
try:
    from ii_skills.shared.event_schema import EventPayload, PAYLOAD_REGISTRY
    _SHARED_AVAILABLE = True
except ImportError:
    _SHARED_AVAILABLE = False
    PAYLOAD_REGISTRY = {}

    @dataclass
    class EventPayload:
        """Standalone base when shared schema unavailable."""
        event_type: str = ""
        timestamp: str = field(
            default_factory=lambda: datetime.now(timezone.utc).isoformat()
        )

        def to_dict(self) -> Dict[str, Any]:
            return asdict(self)


# =============================================================================
# ENUMS
# =============================================================================

class DocumentClass(Enum):
    SEC_FILING = "sec_filing"
    EARNINGS_TRANSCRIPT = "earnings_transcript"
    INVESTOR_PRESENTATION = "investor_presentation"
    QUARTERLY_LETTER = "quarterly_letter"
    LPA_DOCUMENT = "lpa_document"
    SIDE_LETTER = "side_letter"
    BENCHMARK_REPORT = "benchmark_report"
    THIRD_PARTY_RESEARCH = "third_party_research"
    INTERNAL_MODEL = "internal_model"


class ReconciliationStatus(Enum):
    CONFIRMED = "confirmed"
    UPDATED = "updated"
    DISCREPANCY = "discrepancy"
    NEW_METRIC = "new_metric"


class TermRiskType(Enum):
    ECONOMICS_RISK = "economics_risk"
    GOVERNANCE_RISK = "governance_risk"
    TRANSPARENCY_RISK = "transparency_risk"
    LIQUIDITY_RISK = "liquidity_risk"
    CONFLICT_RISK = "conflict_risk"
    STRUCTURAL_RISK = "structural_risk"


class NegotiationPriority(Enum):
    MUST_NEGOTIATE = "must_negotiate"
    SHOULD_NEGOTIATE = "should_negotiate"
    NICE_TO_HAVE = "nice_to_have"
    ACCEPTABLE = "acceptable"


# =============================================================================
# EVENT PAYLOADS
# =============================================================================

@dataclass
class DocExtractedPayload(EventPayload):
    """Emitted when a source document is ingested and parsed."""
    event_type: str = "doc_extracted"
    run_id: str = ""
    document_class: str = ""
    document_name: str = ""
    period: str = ""
    entities_extracted: List[str] = field(default_factory=list)
    page_count: int = 0
    sections_parsed: int = 0
    extraction_confidence: float = 0.0
    warnings: List[str] = field(default_factory=list)


@dataclass
class SourceProvenance:
    """Provenance data for a KPI reconciliation."""
    document: str = ""
    page_or_section: str = ""
    extraction_method: str = ""  # table_parse, text_regex, manual_input, model_calculation


@dataclass
class KPIReconciledPayload(EventPayload):
    """Emitted when a KPI value is updated or confirmed vs. prior period."""
    event_type: str = "kpi_reconciled"
    run_id: str = ""
    metric_name: str = ""
    asset_or_fund: str = ""
    old_value: Optional[float] = None
    new_value: float = 0.0
    unit: str = ""
    delta: Optional[float] = None
    delta_pct: Optional[float] = None
    source_provenance: Optional[Dict[str, str]] = None
    reconciliation_status: str = ""
    flags: List[str] = field(default_factory=list)


@dataclass
class TermRiskFlaggedPayload(EventPayload):
    """Emitted when a deal-term red flag or notable provision is detected."""
    event_type: str = "term_risk_flagged"
    run_id: str = ""
    clause_id: str = ""
    clause_text: str = ""
    risk_type: str = ""
    severity: str = "medium"
    description: str = ""
    lp_friendliness_impact: float = 0.0
    gp_flexibility_impact: float = 0.0
    benchmark_comparison: Optional[str] = None
    negotiation_priority: str = ""
    suggested_revision: Optional[str] = None


# =============================================================================
# TELEMETRY HELPERS
# =============================================================================

# Maps event type strings to payload classes
IR_PAYLOAD_REGISTRY: Dict[str, Type[EventPayload]] = {
    "doc_extracted": DocExtractedPayload,
    "kpi_reconciled": KPIReconciledPayload,
    "term_risk_flagged": TermRiskFlaggedPayload,
}

_IR_EVENTS_REGISTERED = False


def register_ir_events():
    """
    Extend shared PAYLOAD_REGISTRY with IR-specific event types.
    Idempotent — safe to call multiple times. No-op if shared schema unavailable.
    """
    global _IR_EVENTS_REGISTERED
    if _IR_EVENTS_REGISTERED:
        return
    _IR_EVENTS_REGISTERED = True

    if _SHARED_AVAILABLE:
        PAYLOAD_REGISTRY.update(IR_PAYLOAD_REGISTRY)


@dataclass
class IRTelemetryExtensions:
    """
    IR-specific aggregate telemetry fields added to run-level summaries.
    """
    evidence_coverage_ratio: float = 0.0
    uncited_claim_count: int = 0
    term_sheet_fields_extracted: int = 0
    term_red_flags_count: int = 0
    benchmark_confidence_score: float = 0.0
    kpi_discrepancy_count: int = 0
    documents_ingested: int = 0
    total_evidence_nodes: int = 0

    def inject_into_custom_metrics(self, metrics: Dict[str, Any]):
        """Inject IR telemetry fields into a custom metrics dict."""
        metrics["ir_evidence_coverage_ratio"] = self.evidence_coverage_ratio
        metrics["ir_uncited_claim_count"] = self.uncited_claim_count
        metrics["ir_term_sheet_fields_extracted"] = self.term_sheet_fields_extracted
        metrics["ir_term_red_flags_count"] = self.term_red_flags_count
        metrics["ir_benchmark_confidence_score"] = self.benchmark_confidence_score
        metrics["ir_kpi_discrepancy_count"] = self.kpi_discrepancy_count
        metrics["ir_documents_ingested"] = self.documents_ingested
        metrics["ir_total_evidence_nodes"] = self.total_evidence_nodes


def compute_ir_telemetry(
    tracker: Optional[Any] = None,
    doc_events: Optional[List[DocExtractedPayload]] = None,
    kpi_events: Optional[List[KPIReconciledPayload]] = None,
    term_events: Optional[List[TermRiskFlaggedPayload]] = None,
) -> IRTelemetryExtensions:
    """
    Compute IR telemetry extensions from tracker and event lists.

    Args:
        tracker: ClaimEvidenceTracker instance (optional, avoids circular import)
        doc_events: List of doc_extracted events
        kpi_events: List of kpi_reconciled events
        term_events: List of term_risk_flagged events

    Returns:
        IRTelemetryExtensions with computed values
    """
    ext = IRTelemetryExtensions()

    # From tracker
    if tracker is not None:
        ext.evidence_coverage_ratio = tracker.get_evidence_coverage_ratio()
        ext.uncited_claim_count = len(tracker.get_uncited_claims())
        ext.total_evidence_nodes = len(tracker._evidence)

    # From doc events
    if doc_events:
        ext.documents_ingested = len(doc_events)
        confidences = [e.extraction_confidence for e in doc_events if e.extraction_confidence > 0]
        if confidences:
            ext.benchmark_confidence_score = sum(confidences) / len(confidences)

    # From KPI events
    if kpi_events:
        ext.kpi_discrepancy_count = sum(
            1 for e in kpi_events
            if e.reconciliation_status == ReconciliationStatus.DISCREPANCY.value
        )

    # From term events
    if term_events:
        ext.term_red_flags_count = sum(
            1 for e in term_events
            if e.severity in ("medium", "high", "critical")
        )
        ext.term_sheet_fields_extracted = len(term_events)

    return ext
