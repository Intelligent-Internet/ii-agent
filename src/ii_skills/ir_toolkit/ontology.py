"""
Infrastructure Ontology — Python-native encoding

Encodes references/infra_ontology.yml as pure Python dicts (no PyYAML dependency).
Provides lookup, tagging, and QA gate functions.

Usage:
    from ii_skills.ir_toolkit.ontology import (
        InfraOntology, OntologyTagger, SemanticTag, TaggedElement,
        check_jargon_consistency, check_metric_definitions,
    )

    ontology = InfraOntology()
    tagger = OntologyTagger(ontology)
    tags = tagger.tag_text("The wind farm achieved 96% availability with a DSCR of 1.8x")
"""

from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any, Tuple


# =============================================================================
# ONTOLOGY CONSTANTS
# =============================================================================

ASSET_CLASSES: Dict[str, Dict[str, Any]] = {
    "transport": {
        "label": "Transportation",
        "subcategories": [
            "toll_roads", "airports", "ports_and_terminals",
            "rail_freight", "mass_transit",
        ],
        "typical_revenue_profile": ["contracted", "regulated", "availability_based"],
        "typical_contract_life_years": [15, 30],
        "key_kpis": ["traffic_volume", "availability", "toll_rate", "capex_per_lane_km"],
    },
    "midstream": {
        "label": "Midstream Energy",
        "subcategories": [
            "gas_pipelines", "ngl_processing", "lng_terminals",
            "storage_facilities", "gathering_systems",
        ],
        "typical_revenue_profile": ["contracted", "take_or_pay"],
        "typical_contract_life_years": [10, 25],
        "key_kpis": [
            "throughput", "contracted_capacity_pct",
            "counterparty_credit_rating", "recontracting_spread",
        ],
    },
    "utilities": {
        "label": "Regulated Utilities",
        "subcategories": [
            "electric_distribution", "electric_transmission",
            "gas_distribution", "water_and_wastewater", "district_energy",
        ],
        "typical_revenue_profile": ["regulated"],
        "typical_contract_life_years": ["perpetual"],
        "key_kpis": [
            "rate_base", "allowed_roe", "regulatory_lag_months",
            "capex_to_rate_base_pct",
        ],
    },
    "data_infrastructure": {
        "label": "Digital / Data Infrastructure",
        "subcategories": [
            "data_centers", "fiber_networks", "telecom_towers",
            "small_cells", "subsea_cables",
        ],
        "typical_revenue_profile": ["contracted", "cpi_indexed"],
        "typical_contract_life_years": [5, 15],
        "key_kpis": [
            "utilization_pct", "churn_rate",
            "power_usage_effectiveness", "arpu",
        ],
    },
    "contracted_power": {
        "label": "Contracted Power Generation",
        "subcategories": [
            "onshore_wind", "offshore_wind", "solar_pv",
            "hydro", "biomass", "battery_storage",
        ],
        "typical_revenue_profile": ["contracted", "merchant", "cpi_indexed"],
        "typical_contract_life_years": [10, 25],
        "key_kpis": [
            "capacity_factor", "availability", "ppa_price",
            "curtailment_pct", "merchant_exposure_pct",
        ],
    },
    "regulated_networks": {
        "label": "Regulated Networks",
        "subcategories": [
            "electricity_transmission", "gas_transmission", "water_networks",
        ],
        "typical_revenue_profile": ["regulated"],
        "typical_contract_life_years": ["perpetual"],
        "key_kpis": [
            "rab_growth_pct", "totex_efficiency",
            "outage_minutes", "leakage_rate",
        ],
    },
}

REVENUE_PROFILES: Dict[str, Dict[str, Any]] = {
    "contracted": {
        "definition": "Revenue secured under long-term offtake, capacity, or service agreements",
        "risk_level": "low",
        "inflation_linkage": "varies",
        "typical_tenor_years": [10, 30],
        "counterparty_dependency": "high",
    },
    "regulated": {
        "definition": "Revenue determined by a regulatory body (tariff, rate base, allowed return)",
        "risk_level": "low_to_medium",
        "inflation_linkage": "typically_partial",
        "reset_frequency": [1, 5],
        "political_risk": "medium",
    },
    "merchant": {
        "definition": "Revenue exposed to market pricing (spot or short-term contracts)",
        "risk_level": "high",
        "inflation_linkage": "indirect",
        "typical_tenor_years": [0, 2],
        "price_volatility": "high",
    },
    "take_or_pay": {
        "definition": "Counterparty pays regardless of actual usage up to contracted volumes",
        "risk_level": "low",
        "inflation_linkage": "typically_cpi_indexed",
        "volume_risk": "minimal",
        "counterparty_dependency": "high",
    },
    "cpi_indexed": {
        "definition": "Revenue or tariff escalates with a consumer price index",
        "risk_level": "low",
        "pass_through_lag_months": [0, 12],
        "floor": "often_zero",
        "cap": "varies",
    },
    "availability_based": {
        "definition": "Revenue paid for asset availability, not actual throughput",
        "risk_level": "low",
        "volume_risk": "minimal",
        "performance_penalty": "deductions_for_downtime",
        "typical_sectors": ["transport", "contracted_power"],
    },
}

FINANCING_TERMS: Dict[str, Dict[str, Any]] = {
    "dscr": {
        "label": "Debt Service Coverage Ratio",
        "definition": "Cash available for debt service / debt service obligation",
        "healthy_range": [1.3, 2.5],
        "covenant_typical": 1.2,
        "stress_floor": 1.0,
    },
    "llcr": {
        "label": "Loan Life Coverage Ratio",
        "definition": "NPV of future cash flows over loan life / outstanding debt",
        "healthy_range": [1.3, 2.0],
        "used_in": "project_finance",
    },
    "sculpted_amortization": {
        "label": "Sculpted Amortization",
        "definition": "Debt repayment schedule shaped to match projected cash flow profile",
        "advantage": "optimizes_dscr_stability",
        "typical_sectors": ["transport", "contracted_power"],
    },
    "bullet_maturity": {
        "label": "Bullet Maturity",
        "definition": "Full principal repayment at maturity (no interim amortization)",
        "refinancing_risk": "high",
        "typical_tenor_years": [5, 7],
    },
    "covenant_holiday": {
        "label": "Covenant Holiday",
        "definition": "Period during construction or ramp-up where covenants are waived",
        "typical_duration_months": [12, 36],
        "risk": "delayed_visibility_of_stress",
    },
    "cash_sweep": {
        "label": "Cash Sweep",
        "definition": "Mandatory excess cash flow applied to debt prepayment",
        "trigger": "typically_dscr_based",
        "sweep_pct_range": [50, 100],
    },
    "reserve_accounts": {
        "label": "Reserve Accounts",
        "definition": "Restricted cash balances (debt service, maintenance, distribution lock-up)",
        "types": ["debt_service_reserve", "maintenance_reserve", "distribution_reserve"],
        "sizing": "typically_6_months_debt_service",
    },
}

OPERATIONS_TERMS: Dict[str, Dict[str, Any]] = {
    "forced_outage_factor": {
        "label": "Forced Outage Factor",
        "definition": "Unplanned downtime as a percentage of total hours",
        "target": "<5%",
        "impact": "availability_based_revenue_deductions",
    },
    "availability_factor": {
        "label": "Availability Factor",
        "definition": "Hours available for operation / total hours",
        "target": ">95%",
        "sectors": ["contracted_power", "transport", "data_infrastructure"],
    },
    "throughput": {
        "label": "Throughput",
        "definition": "Volume processed or transported (units vary by asset)",
        "units": ["bcf_per_day", "mtpa", "vehicles_per_day", "mwh"],
        "relevance": "revenue_driver_for_volume_based_contracts",
    },
    "load_factor": {
        "label": "Load Factor",
        "definition": "Actual output / maximum possible output",
        "range": [0.25, 0.95],
        "context": "generation_assets_and_transport",
    },
    "heat_rate": {
        "label": "Heat Rate",
        "definition": "Energy input per unit of electricity output (thermal plants)",
        "units": "btu_per_kwh",
        "lower_is_better": True,
    },
    "opex_per_unit": {
        "label": "Operating Cost per Unit",
        "definition": "Total operating cost divided by capacity or output measure",
        "benchmarking": "peer_comparison_metric",
        "trend": "should_decline_or_stay_flat",
    },
}

SEMANTIC_TAG_DEFINITIONS: Dict[str, List[str]] = {
    "asset_class": list(ASSET_CLASSES.keys()),
    "cash_flow_type": list(REVENUE_PROFILES.keys()),
    "regulatory_exposure": ["none", "low", "medium", "high"],
    "counterparty_risk": [
        "investment_grade", "sub_investment_grade", "government", "unrated",
    ],
    "inflation_linkage": ["none", "partial", "full", "capped"],
    "contract_tenor": ["short", "medium", "long", "perpetual"],
    "leverage_profile": ["conservative", "moderate", "aggressive"],
    "operational_risk": ["low", "medium", "high"],
}


# =============================================================================
# ONTOLOGY CLASSES
# =============================================================================

@dataclass
class InfraOntology:
    """Lookup interface for the infrastructure ontology."""

    asset_classes: Dict[str, Dict] = field(default_factory=lambda: ASSET_CLASSES)
    revenue_profiles: Dict[str, Dict] = field(default_factory=lambda: REVENUE_PROFILES)
    financing_terms: Dict[str, Dict] = field(default_factory=lambda: FINANCING_TERMS)
    operations_terms: Dict[str, Dict] = field(default_factory=lambda: OPERATIONS_TERMS)
    tag_definitions: Dict[str, List[str]] = field(default_factory=lambda: SEMANTIC_TAG_DEFINITIONS)

    def get_asset_class(self, key: str) -> Optional[Dict]:
        """Look up an asset class by key."""
        return self.asset_classes.get(key)

    def get_revenue_profile(self, key: str) -> Optional[Dict]:
        """Look up a revenue profile by key."""
        return self.revenue_profiles.get(key)

    def get_financing_term(self, key: str) -> Optional[Dict]:
        """Look up a financing term by key."""
        return self.financing_terms.get(key)

    def get_operations_term(self, key: str) -> Optional[Dict]:
        """Look up an operations term by key."""
        return self.operations_terms.get(key)

    def is_valid_tag(self, tag_name: str, tag_value: str) -> bool:
        """Check if a tag name/value pair is valid."""
        valid_values = self.tag_definitions.get(tag_name)
        if valid_values is None:
            return False
        return tag_value in valid_values

    def get_healthy_range(self, term_key: str) -> Optional[List[float]]:
        """Get the healthy range for a financing or operations metric."""
        term = self.financing_terms.get(term_key)
        if term and "healthy_range" in term:
            return term["healthy_range"]
        term = self.operations_terms.get(term_key)
        if term and "range" in term:
            return term["range"]
        return None


@dataclass
class SemanticTag:
    """A single semantic tag applied to an element."""
    tag_name: str
    tag_value: str
    confidence: float = 1.0
    source: str = "rule_based"


@dataclass
class TaggedElement:
    """An element (text, KPI, data field) with semantic tags."""
    element_id: str
    element_type: str  # "text", "kpi", "data_field"
    content: str
    tags: List[SemanticTag] = field(default_factory=list)

    def has_tag(self, tag_name: str) -> bool:
        """Check if this element has a tag with the given name."""
        return any(t.tag_name == tag_name for t in self.tags)

    def get_tag_value(self, tag_name: str) -> Optional[str]:
        """Get the value of a tag by name (first match)."""
        for t in self.tags:
            if t.tag_name == tag_name:
                return t.tag_value
        return None

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "element_id": self.element_id,
            "element_type": self.element_type,
            "content": self.content,
            "tags": [asdict(t) for t in self.tags],
        }


# =============================================================================
# ONTOLOGY TAGGER
# =============================================================================

class OntologyTagger:
    """
    Rule-based keyword tagger using the ontology.

    Builds a keyword index from ontology constants at init.
    Scans text for keyword matches and produces SemanticTags.
    """

    def __init__(self, ontology: Optional[InfraOntology] = None):
        self.ontology = ontology or InfraOntology()
        self._keyword_index: Dict[str, List[Tuple[str, str]]] = {}
        self._build_keyword_index()

    def _build_keyword_index(self):
        """Build keyword -> (tag_name, tag_value) index from ontology."""
        # Asset class keywords
        for key, data in self.ontology.asset_classes.items():
            label = data["label"].lower()
            self._add_keyword(label, "asset_class", key)
            self._add_keyword(key.replace("_", " "), "asset_class", key)
            for sub in data.get("subcategories", []):
                self._add_keyword(sub.replace("_", " "), "asset_class", key)

        # Revenue profile keywords (key name only, not definition words)
        for key, data in self.ontology.revenue_profiles.items():
            self._add_keyword(key.replace("_", " "), "cash_flow_type", key)
        # Explicit aliases for common terms
        self._add_keyword("regulated", "cash_flow_type", "regulated")
        self._add_keyword("merchant", "cash_flow_type", "merchant")
        self._add_keyword("take or pay", "cash_flow_type", "take_or_pay")

        # Financing term keywords
        for key, data in self.ontology.financing_terms.items():
            label = data["label"].lower()
            self._add_keyword(label, "financing_term", key)
            self._add_keyword(key.replace("_", " "), "financing_term", key)
            # Common abbreviations
            if key == "dscr":
                self._add_keyword("dscr", "financing_term", "dscr")
                self._add_keyword("debt service coverage", "financing_term", "dscr")
            elif key == "llcr":
                self._add_keyword("llcr", "financing_term", "llcr")
                self._add_keyword("loan life coverage", "financing_term", "llcr")

        # Operations term keywords
        for key, data in self.ontology.operations_terms.items():
            label = data["label"].lower()
            self._add_keyword(label, "operations_term", key)
            self._add_keyword(key.replace("_", " "), "operations_term", key)

    def _add_keyword(self, keyword: str, tag_name: str, tag_value: str):
        """Add a keyword -> tag mapping."""
        kw = keyword.lower().strip()
        if kw and len(kw) > 2:
            if kw not in self._keyword_index:
                self._keyword_index[kw] = []
            mapping = (tag_name, tag_value)
            if mapping not in self._keyword_index[kw]:
                self._keyword_index[kw].append(mapping)

    def tag_text(self, text: str, element_id: str = "auto") -> TaggedElement:
        """Tag a text string with semantic tags from the ontology."""
        text_lower = text.lower()
        tags: List[SemanticTag] = []
        seen: set = set()

        for keyword, mappings in self._keyword_index.items():
            if keyword in text_lower:
                for tag_name, tag_value in mappings:
                    tag_key = (tag_name, tag_value)
                    if tag_key not in seen:
                        seen.add(tag_key)
                        tags.append(SemanticTag(
                            tag_name=tag_name,
                            tag_value=tag_value,
                            confidence=0.8,
                            source="keyword_match",
                        ))

        return TaggedElement(
            element_id=element_id,
            element_type="text",
            content=text[:200],
            tags=tags,
        )

    def tag_kpi(
        self,
        metric_name: str,
        value: Any,
        element_id: str = "auto",
    ) -> TaggedElement:
        """Tag a KPI metric with ontology context."""
        tags: List[SemanticTag] = []

        # Check financing terms
        term = self.ontology.financing_terms.get(metric_name)
        if term:
            tags.append(SemanticTag(
                tag_name="financing_term",
                tag_value=metric_name,
                confidence=1.0,
                source="exact_match",
            ))
            # Check healthy range
            healthy = term.get("healthy_range")
            if healthy and value is not None:
                try:
                    v = float(value)
                    if v < healthy[0]:
                        tags.append(SemanticTag(
                            tag_name="range_status",
                            tag_value="below_healthy",
                            confidence=1.0,
                            source="range_check",
                        ))
                    elif v > healthy[1]:
                        tags.append(SemanticTag(
                            tag_name="range_status",
                            tag_value="above_healthy",
                            confidence=1.0,
                            source="range_check",
                        ))
                    else:
                        tags.append(SemanticTag(
                            tag_name="range_status",
                            tag_value="within_healthy",
                            confidence=1.0,
                            source="range_check",
                        ))
                except (ValueError, TypeError):
                    pass

        # Check operations terms
        ops_term = self.ontology.operations_terms.get(metric_name)
        if ops_term:
            tags.append(SemanticTag(
                tag_name="operations_term",
                tag_value=metric_name,
                confidence=1.0,
                source="exact_match",
            ))

        return TaggedElement(
            element_id=element_id,
            element_type="kpi",
            content=f"{metric_name}={value}",
            tags=tags,
        )

    def tag_data_dict(
        self,
        data: Dict[str, Any],
        prefix: str = "",
    ) -> List[TaggedElement]:
        """Tag all fields in a data dictionary."""
        elements: List[TaggedElement] = []
        for key, value in data.items():
            eid = f"{prefix}.{key}" if prefix else key
            if isinstance(value, str):
                elem = self.tag_text(value, element_id=eid)
                if elem.tags:
                    elements.append(elem)
            elif isinstance(value, (int, float)):
                elem = self.tag_kpi(key, value, element_id=eid)
                if elem.tags:
                    elements.append(elem)
            elif isinstance(value, dict):
                elements.extend(self.tag_data_dict(value, prefix=eid))
        return elements

    def get_tags_summary(self, elements: List[TaggedElement]) -> Dict[str, int]:
        """Summarize tag counts across multiple tagged elements."""
        counts: Dict[str, int] = {}
        for elem in elements:
            for tag in elem.tags:
                key = f"{tag.tag_name}:{tag.tag_value}"
                counts[key] = counts.get(key, 0) + 1
        return counts


# =============================================================================
# QA GATE FUNCTIONS
# =============================================================================

@dataclass
class JargonQAResult:
    """Result of jargon consistency QA check."""
    passed: bool
    undefined_jargon_count: int = 0
    inconsistent_usage_count: int = 0
    metric_definition_mismatches: int = 0
    details: List[str] = field(default_factory=list)


def check_jargon_consistency(
    tagged_elements: List[TaggedElement],
    ontology: Optional[InfraOntology] = None,
) -> JargonQAResult:
    """
    Validate tagging consistency across tagged elements.

    Checks:
    - All tag values are valid per ontology definitions
    - No conflicting tags on the same element
    - Consistent usage of terms across elements
    """
    ontology = ontology or InfraOntology()
    details: List[str] = []
    undefined_count = 0
    inconsistent_count = 0

    # Track tag usage for consistency
    tag_usage: Dict[str, set] = {}  # tag_name -> set of tag_values seen

    for elem in tagged_elements:
        for tag in elem.tags:
            # Check validity
            if tag.tag_name in ontology.tag_definitions:
                if not ontology.is_valid_tag(tag.tag_name, tag.tag_value):
                    undefined_count += 1
                    details.append(
                        f"Undefined tag value: {tag.tag_name}={tag.tag_value} "
                        f"on element {elem.element_id}"
                    )

            # Track usage
            if tag.tag_name not in tag_usage:
                tag_usage[tag.tag_name] = set()
            tag_usage[tag.tag_name].add(tag.tag_value)

        # Check for conflicting tags on same element
        tag_names_on_elem = [t.tag_name for t in elem.tags]
        for tn in set(tag_names_on_elem):
            values = [t.tag_value for t in elem.tags if t.tag_name == tn]
            if len(set(values)) > 1 and tn in ("asset_class", "cash_flow_type"):
                # Multiple different values for a single-value tag is acceptable
                # for text that mentions multiple concepts, but flag it
                inconsistent_count += 1
                details.append(
                    f"Multiple values for {tn} on element {elem.element_id}: "
                    f"{', '.join(set(values))}"
                )

    passed = undefined_count == 0 and inconsistent_count == 0
    return JargonQAResult(
        passed=passed,
        undefined_jargon_count=undefined_count,
        inconsistent_usage_count=inconsistent_count,
        details=details,
    )


def check_metric_definitions(
    metrics: Dict[str, float],
    ontology: Optional[InfraOntology] = None,
) -> JargonQAResult:
    """
    Validate metric values against healthy ranges in the ontology.

    Args:
        metrics: Dict of metric_key -> numeric value
        ontology: InfraOntology instance (creates default if None)

    Returns:
        JargonQAResult with any out-of-range findings
    """
    ontology = ontology or InfraOntology()
    details: List[str] = []
    mismatch_count = 0

    for metric_key, value in metrics.items():
        healthy = ontology.get_healthy_range(metric_key)
        if healthy is not None:
            try:
                v = float(value)
                lo, hi = healthy
                if v < lo:
                    mismatch_count += 1
                    details.append(
                        f"{metric_key}={v:.2f} is below healthy range "
                        f"[{lo}, {hi}]"
                    )
                elif v > hi:
                    mismatch_count += 1
                    details.append(
                        f"{metric_key}={v:.2f} is above healthy range "
                        f"[{lo}, {hi}]"
                    )
            except (ValueError, TypeError):
                pass

    passed = mismatch_count == 0
    return JargonQAResult(
        passed=passed,
        metric_definition_mismatches=mismatch_count,
        details=details,
    )
