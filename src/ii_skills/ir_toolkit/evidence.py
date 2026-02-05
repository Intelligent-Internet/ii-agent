"""
Claim-Evidence Tracking

Implements references/claim_evidence_schema.yml as Python dataclasses
with a tracker class for managing the claim-evidence graph.

Usage:
    from ii_skills.ir_toolkit.evidence import (
        ClaimEvidenceTracker, EvidenceNode, Claim, Recommendation,
    )

    tracker = ClaimEvidenceTracker()
    ev = tracker.add_evidence(
        source_document="BIP Q3 2025 Supplemental",
        source_type="sec_filing",
        extracted_text="Cash yield 8.2%",
    )
    claim = tracker.add_claim(
        text="Fund IV cash yield remains above 8%",
        confidence=0.9,
        category="cash_flow",
        evidence_ids=[ev.evidence_id],
    )
    report = tracker.validate()
"""

from dataclasses import dataclass, field, asdict
from datetime import date, datetime
from enum import Enum
from typing import Dict, List, Optional, Any


# =============================================================================
# ENUMS
# =============================================================================

class ClaimCategory(Enum):
    PERFORMANCE = "performance"
    CASH_FLOW = "cash_flow"
    VALUATION = "valuation"
    RISK = "risk"
    OPERATIONAL = "operational"
    MARKET = "market"
    TERMS = "terms"
    OUTLOOK = "outlook"


class SourceType(Enum):
    SEC_FILING = "sec_filing"
    EARNINGS_TRANSCRIPT = "earnings_transcript"
    INVESTOR_PRESENTATION = "investor_presentation"
    QUARTERLY_LETTER = "quarterly_letter"
    LPA_DOCUMENT = "lpa_document"
    SIDE_LETTER = "side_letter"
    DATA_ROOM_DOCUMENT = "data_room_document"
    BENCHMARK_REPORT = "benchmark_report"
    THIRD_PARTY_RESEARCH = "third_party_research"
    INTERNAL_MODEL = "internal_model"


class ConflictType(Enum):
    DIRECT_CONTRADICTION = "direct_contradiction"
    MAGNITUDE_DISAGREEMENT = "magnitude_disagreement"
    TEMPORAL_MISMATCH = "temporal_mismatch"
    METHODOLOGICAL = "methodological"


class RecommendationPriority(Enum):
    CRITICAL = "critical"
    IMPORTANT = "important"
    INFORMATIONAL = "informational"


# =============================================================================
# DATACLASSES
# =============================================================================

@dataclass
class ExtractedValue:
    """Structured numeric data extracted from a source."""
    metric: str
    value: float
    unit: str
    period: str


@dataclass
class EvidenceNode:
    """A discrete piece of supporting data from a source document."""
    evidence_id: str
    source_document: str
    source_type: str
    section: str = ""
    period: str = ""
    extracted_text: str = ""
    extracted_value: Optional[ExtractedValue] = None
    retrieval_date: str = field(default_factory=lambda: date.today().isoformat())

    @classmethod
    def create(
        cls,
        evidence_id: str,
        source_document: str,
        source_type: str,
        **kwargs,
    ) -> "EvidenceNode":
        """Factory method for creating EvidenceNode."""
        return cls(
            evidence_id=evidence_id,
            source_document=source_document,
            source_type=source_type,
            **kwargs,
        )

    def to_dict(self) -> Dict[str, Any]:
        result = asdict(self)
        return result


@dataclass
class ContradictoryEvidence:
    """Evidence that conflicts with or weakens a claim."""
    evidence_id: str
    conflict_type: str
    severity: str = "medium"
    resolution_note: Optional[str] = None


@dataclass
class Claim:
    """An assertion made in an executive summary, slide headline, or narrative."""
    claim_id: str
    text: str
    confidence: float
    category: str
    output_location: str = ""
    evidence_ids: List[str] = field(default_factory=list)
    contradictory_evidence: List[ContradictoryEvidence] = field(default_factory=list)
    semantic_tags: List[Dict[str, str]] = field(default_factory=list)

    @property
    def confidence_level(self) -> str:
        if self.confidence >= 0.8:
            return "high"
        elif self.confidence >= 0.5:
            return "medium"
        return "low"

    @property
    def is_cited(self) -> bool:
        return len(self.evidence_ids) > 0

    @property
    def has_contradictions(self) -> bool:
        return len(self.contradictory_evidence) > 0

    @classmethod
    def create(
        cls,
        claim_id: str,
        text: str,
        confidence: float,
        category: str,
        **kwargs,
    ) -> "Claim":
        """Factory method for creating Claim."""
        return cls(
            claim_id=claim_id,
            text=text,
            confidence=confidence,
            category=category,
            **kwargs,
        )

    def to_dict(self) -> Dict[str, Any]:
        result = asdict(self)
        result["confidence_level"] = self.confidence_level
        result["is_cited"] = self.is_cited
        result["has_contradictions"] = self.has_contradictions
        return result


@dataclass
class Recommendation:
    """An actionable recommendation derived from claims and evidence."""
    recommendation_id: str
    text: str
    priority: str
    supporting_claim_ids: List[str] = field(default_factory=list)
    action_owner: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# =============================================================================
# QUALITY REPORT
# =============================================================================

@dataclass
class QualityRuleResult:
    """Result of a single quality rule check."""
    rule: str
    enforcement: str  # "hard_fail" or "warning"
    passed: bool
    metric_name: str
    metric_value: Any
    details: str = ""


@dataclass
class EvidenceQualityReport:
    """Aggregate quality report from evidence validation."""
    total_claims: int = 0
    cited_claims: int = 0
    uncited_claims: int = 0
    evidence_coverage_ratio: float = 0.0
    low_confidence_claim_count: int = 0
    stale_evidence_count: int = 0
    rule_results: List[QualityRuleResult] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        """All hard-fail rules must pass."""
        return all(
            r.passed for r in self.rule_results
            if r.enforcement == "hard_fail"
        )


# =============================================================================
# TRACKER
# =============================================================================

class ClaimEvidenceTracker:
    """
    Manages the claim-evidence graph.

    Tracks claims, evidence nodes, contradictions, and recommendations
    with auto-incrementing IDs.
    """

    def __init__(self):
        self._claims: Dict[str, Claim] = {}
        self._evidence: Dict[str, EvidenceNode] = {}
        self._recommendations: Dict[str, Recommendation] = {}
        self._claim_counter: int = 0
        self._evidence_counter: int = 0
        self._recommendation_counter: int = 0

    # ── Add methods ──────────────────────────────────────────────

    def add_evidence(
        self,
        source_document: str,
        source_type: str,
        extracted_text: str = "",
        section: str = "",
        period: str = "",
        extracted_value: Optional[ExtractedValue] = None,
        **kwargs,
    ) -> EvidenceNode:
        """Add an evidence node. Returns the created node with auto-ID."""
        self._evidence_counter += 1
        eid = f"EV-{self._evidence_counter:03d}"
        node = EvidenceNode.create(
            evidence_id=eid,
            source_document=source_document,
            source_type=source_type,
            extracted_text=extracted_text,
            section=section,
            period=period,
            extracted_value=extracted_value,
            **kwargs,
        )
        self._evidence[eid] = node
        return node

    def add_claim(
        self,
        text: str,
        confidence: float,
        category: str,
        evidence_ids: Optional[List[str]] = None,
        output_location: str = "",
        semantic_tags: Optional[List[Dict[str, str]]] = None,
        **kwargs,
    ) -> Claim:
        """Add a claim. Returns the created claim with auto-ID."""
        self._claim_counter += 1
        cid = f"CLM-{self._claim_counter:03d}"
        claim = Claim.create(
            claim_id=cid,
            text=text,
            confidence=confidence,
            category=category,
            evidence_ids=evidence_ids or [],
            output_location=output_location,
            semantic_tags=semantic_tags or [],
            **kwargs,
        )
        self._claims[cid] = claim
        return claim

    def add_contradiction(
        self,
        claim_id: str,
        evidence_id: str,
        conflict_type: str,
        severity: str = "medium",
        resolution_note: Optional[str] = None,
    ) -> Optional[ContradictoryEvidence]:
        """Add contradictory evidence to a claim."""
        claim = self._claims.get(claim_id)
        if not claim:
            return None
        contradiction = ContradictoryEvidence(
            evidence_id=evidence_id,
            conflict_type=conflict_type,
            severity=severity,
            resolution_note=resolution_note,
        )
        claim.contradictory_evidence.append(contradiction)
        return contradiction

    def add_recommendation(
        self,
        text: str,
        priority: str,
        supporting_claim_ids: Optional[List[str]] = None,
        action_owner: Optional[str] = None,
    ) -> Recommendation:
        """Add a recommendation. Returns the created recommendation with auto-ID."""
        self._recommendation_counter += 1
        rid = f"REC-{self._recommendation_counter:03d}"
        rec = Recommendation(
            recommendation_id=rid,
            text=text,
            priority=priority,
            supporting_claim_ids=supporting_claim_ids or [],
            action_owner=action_owner,
        )
        self._recommendations[rid] = rec
        return rec

    def link_claim_to_evidence(self, claim_id: str, evidence_id: str) -> bool:
        """Link an existing claim to an existing evidence node."""
        claim = self._claims.get(claim_id)
        if not claim:
            return False
        if evidence_id not in self._evidence:
            return False
        if evidence_id not in claim.evidence_ids:
            claim.evidence_ids.append(evidence_id)
        return True

    # ── Query methods ────────────────────────────────────────────

    def get_claim(self, claim_id: str) -> Optional[Claim]:
        return self._claims.get(claim_id)

    def get_evidence(self, evidence_id: str) -> Optional[EvidenceNode]:
        return self._evidence.get(evidence_id)

    def get_uncited_claims(self) -> List[Claim]:
        return [c for c in self._claims.values() if not c.is_cited]

    def get_low_confidence_claims(self, threshold: float = 0.5) -> List[Claim]:
        return [c for c in self._claims.values() if c.confidence < threshold]

    def get_claims_with_contradictions(self) -> List[Claim]:
        return [c for c in self._claims.values() if c.has_contradictions]

    def get_evidence_coverage_ratio(self) -> float:
        total = len(self._claims)
        if total == 0:
            return 1.0
        cited = sum(1 for c in self._claims.values() if c.is_cited)
        return cited / total

    def get_quality_score(self) -> float:
        """
        Composite quality score (0-1).
        Weights: coverage 40%, confidence 30%, contradiction disclosure 30%.
        """
        if not self._claims:
            return 1.0

        # Coverage
        coverage = self.get_evidence_coverage_ratio()

        # Average confidence
        avg_conf = sum(c.confidence for c in self._claims.values()) / len(self._claims)

        # Contradiction disclosure
        with_contradictions = self.get_claims_with_contradictions()
        if with_contradictions:
            disclosed = sum(
                1 for c in with_contradictions
                if any(ce.resolution_note for ce in c.contradictory_evidence)
            )
            disclosure_ratio = disclosed / len(with_contradictions)
        else:
            disclosure_ratio = 1.0

        return 0.4 * coverage + 0.3 * avg_conf + 0.3 * disclosure_ratio

    # ── Validation ───────────────────────────────────────────────

    def validate(self, current_period: Optional[str] = None) -> EvidenceQualityReport:
        """
        Run all 5 quality rules and return a report.

        Rules:
        1. Every claim must have at least one evidence_id (hard_fail)
        2. Claims with confidence < 0.5 must be flagged (warning)
        3. Contradictory evidence must be disclosed (hard_fail)
        4. All numeric claims should trace to extracted_value (warning)
        5. Evidence older than 2 quarters should be flagged stale (warning)
        """
        total = len(self._claims)
        cited = sum(1 for c in self._claims.values() if c.is_cited)
        uncited = total - cited
        coverage = cited / total if total > 0 else 1.0
        low_conf = len(self.get_low_confidence_claims())

        rules: List[QualityRuleResult] = []

        # Rule 1: Evidence coverage (hard_fail)
        uncited_claims = self.get_uncited_claims()
        rules.append(QualityRuleResult(
            rule="Every claim must have at least one evidence_id",
            enforcement="hard_fail",
            passed=len(uncited_claims) == 0,
            metric_name="evidence_coverage_ratio",
            metric_value=coverage,
            details=f"{len(uncited_claims)} uncited claims" if uncited_claims else "",
        ))

        # Rule 2: Low confidence flagging (warning)
        low_conf_claims = self.get_low_confidence_claims()
        rules.append(QualityRuleResult(
            rule="Claims with confidence < 0.5 must be flagged for review",
            enforcement="warning",
            passed=len(low_conf_claims) == 0,
            metric_name="low_confidence_claim_count",
            metric_value=len(low_conf_claims),
            details=f"{len(low_conf_claims)} low-confidence claims" if low_conf_claims else "",
        ))

        # Rule 3: Contradiction disclosure (hard_fail)
        contradicted = self.get_claims_with_contradictions()
        undisclosed = [
            c for c in contradicted
            if not all(ce.resolution_note for ce in c.contradictory_evidence)
        ]
        rules.append(QualityRuleResult(
            rule="Contradictory evidence must be disclosed in output footnotes",
            enforcement="hard_fail",
            passed=len(undisclosed) == 0,
            metric_name="undisclosed_contradiction_count",
            metric_value=len(undisclosed),
            details=f"{len(undisclosed)} claims with undisclosed contradictions" if undisclosed else "",
        ))

        # Rule 4: Numeric claims must trace to extracted_value (warning)
        # Check if evidence for each claim has extracted_value
        uncited_numeric = 0
        for claim in self._claims.values():
            if claim.is_cited:
                has_extracted = any(
                    self._evidence.get(eid) and self._evidence[eid].extracted_value
                    for eid in claim.evidence_ids
                    if eid in self._evidence
                )
                # Only flag if no evidence has extracted_value
                if not has_extracted:
                    uncited_numeric += 1
        rules.append(QualityRuleResult(
            rule="All numeric claims must trace to an extracted_value",
            enforcement="warning",
            passed=uncited_numeric == 0,
            metric_name="uncited_numeric_count",
            metric_value=uncited_numeric,
            details=f"{uncited_numeric} claims without extracted values" if uncited_numeric else "",
        ))

        # Rule 5: Stale evidence (warning)
        stale_count = 0
        if current_period:
            # Simple staleness check: compare year/quarter
            for ev in self._evidence.values():
                if ev.period and current_period:
                    if _is_stale(ev.period, current_period):
                        stale_count += 1
        rules.append(QualityRuleResult(
            rule="Evidence older than 2 quarters should be flagged as stale",
            enforcement="warning",
            passed=stale_count == 0,
            metric_name="stale_evidence_count",
            metric_value=stale_count,
            details=f"{stale_count} stale evidence nodes" if stale_count else "",
        ))

        return EvidenceQualityReport(
            total_claims=total,
            cited_claims=cited,
            uncited_claims=uncited,
            evidence_coverage_ratio=coverage,
            low_confidence_claim_count=low_conf,
            stale_evidence_count=stale_count,
            rule_results=rules,
        )

    # ── Serialization ────────────────────────────────────────────

    def to_dict(self) -> Dict[str, Any]:
        return {
            "claims": {k: v.to_dict() for k, v in self._claims.items()},
            "evidence": {k: v.to_dict() for k, v in self._evidence.items()},
            "recommendations": {k: v.to_dict() for k, v in self._recommendations.items()},
            "counters": {
                "claim": self._claim_counter,
                "evidence": self._evidence_counter,
                "recommendation": self._recommendation_counter,
            },
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ClaimEvidenceTracker":
        """Reconstruct tracker from serialized dict."""
        tracker = cls()

        # Restore counters
        counters = data.get("counters", {})
        tracker._claim_counter = counters.get("claim", 0)
        tracker._evidence_counter = counters.get("evidence", 0)
        tracker._recommendation_counter = counters.get("recommendation", 0)

        # Restore evidence
        for eid, ev_data in data.get("evidence", {}).items():
            extracted_value = ev_data.pop("extracted_value", None)
            if extracted_value:
                extracted_value = ExtractedValue(**extracted_value)
            tracker._evidence[eid] = EvidenceNode(**{**ev_data, "extracted_value": extracted_value})

        # Restore claims
        for cid, cl_data in data.get("claims", {}).items():
            # Remove computed properties that to_dict() adds
            cl_data.pop("confidence_level", None)
            cl_data.pop("is_cited", None)
            cl_data.pop("has_contradictions", None)
            contradictory = cl_data.pop("contradictory_evidence", [])
            cl_data["contradictory_evidence"] = [
                ContradictoryEvidence(**ce) for ce in contradictory
            ]
            tracker._claims[cid] = Claim(**cl_data)

        # Restore recommendations
        for rid, rec_data in data.get("recommendations", {}).items():
            tracker._recommendations[rid] = Recommendation(**rec_data)

        return tracker


# =============================================================================
# HELPERS
# =============================================================================

def _parse_quarter(period: str) -> Optional[tuple]:
    """Parse 'Q3 2025' -> (2025, 3). Returns None if unparsable."""
    period = period.strip().upper()
    parts = period.split()
    if len(parts) != 2:
        return None
    try:
        q = int(parts[0].replace("Q", ""))
        y = int(parts[1])
        return (y, q)
    except (ValueError, IndexError):
        return None


def _is_stale(evidence_period: str, current_period: str, threshold_quarters: int = 2) -> bool:
    """Check if evidence period is more than threshold_quarters behind current."""
    ev = _parse_quarter(evidence_period)
    cur = _parse_quarter(current_period)
    if not ev or not cur:
        return False
    ev_total = ev[0] * 4 + ev[1]
    cur_total = cur[0] * 4 + cur[1]
    return (cur_total - ev_total) > threshold_quarters
