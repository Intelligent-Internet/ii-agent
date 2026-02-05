# II Agent × IR Toolkit Expansion Game Plan

## Objective

Build the IR toolkit into a **domain-specialized infrastructure IR copilot** that:
1. Speaks infrastructure LP/GP language with precision.
2. Produces evidence-linked synthesis across filings, decks, transcripts, and benchmark sources.
3. Analyzes economic and governance terms in fund-level and co-invest deal documents.
4. Uses II Agent core infrastructure (task graphs, telemetry, run budgets, schemas) for repeatable and auditable workflows.

---

## 1) Current-State Assessment (vs. Requested Direction)

The current toolkit is strong on **moduleized output structure** (Excel ↔ slide pairing, KPI scaffolds, case types), but limited in:

- **Deep infrastructure ontology**: jargon is present, but not normalized into a machine-usable taxonomy.
- **Research synthesis rigor**: no explicit claim-evidence chain across documents.
- **Term-sheet/legal depth**: no parser/scorer for LP/GP economics + governance terms.
- **Issuer-specific intelligence loops**: no dedicated profile pack for major infrastructure names (e.g., Brookfield Infrastructure Partners).

### Gap Scorecard (0-5)

| Capability | Current | Target | Gap |
|---|---:|---:|---:|
| Infra jargon coverage | 2.5 | 4.5 | 2.0 |
| Source-grounded synthesis | 2.0 | 4.5 | 2.5 |
| LP/GP term analytics | 1.5 | 4.5 | 3.0 |
| Company-specific playbooks | 1.5 | 4.0 | 2.5 |
| Workflow observability | 3.5 | 4.5 | 1.0 |

---

## 2) Integration Plan: Merge II Agent Core Capabilities with IR Toolkit

## 2.1 Task-Graph Pipeline (from request → output)

Implement IR runs as an explicit DAG:

1. **Ingest** (filings, quarterly letters, transcript text, investor deck extracts)
2. **Normalize** (entity mapping, unit harmonization, period alignment)
3. **Extract** (KPI and terms extraction)
4. **Synthesize** (thesis + risks + delta vs prior quarter)
5. **Generate** (Excel tables + paired slides)
6. **QA** (rubric scoring + citation completeness)

Use existing orchestration hooks (`IRPhase`, telemetry callback, budget enforcement) as the backbone for these nodes.

## 2.2 Event Telemetry for Trust and Auditability

Expand telemetry payloads with IR-specific metrics:
- `evidence_coverage_ratio`
- `uncited_claim_count`
- `term_sheet_fields_extracted`
- `benchmark_confidence_score`

Outcome: PM/IR leads can audit what changed and why each conclusion was produced.

## 2.3 Run Budgets for Faster Iteration Modes

Add profile presets tailored to IR workflows:
- `triage`: fast readout in <10 min (limited extraction scope)
- `committee`: full synthesis + term analysis + benchmark comparison
- `ddq_deadline`: prioritize unresolved LP questions and artifact generation speed

## 2.4 Shared Event Schema Extensions

Define typed payloads for:
- `doc_extracted` (document class + period + entities)
- `kpi_reconciled` (old/new value, source provenance)
- `term_risk_flagged` (clause id, risk type, severity)

This turns IR output into trackable data products rather than one-off decks.

---

## 3) Technical Depth Plan: Infrastructure Ontology + Terminology Engine

## 3.1 Build an Infra Ontology Layer

Create `references/infra_ontology.yml` with normalized dictionaries:
- **Asset classes**: transport, midstream, utilities, data infrastructure, contracted power, regulated networks.
- **Revenue profile terms**: contracted, regulated, merchant, take-or-pay, CPI-indexed, availability-based.
- **Financing terms**: DSCR, LLCR, sculpted amortization, bullet maturity, covenant holiday.
- **Operations terms**: forced outage factor, availability factor, throughput, load factor.

## 3.2 Add Semantic Tagging in Extraction

Each extracted statement gets tags:
- `asset_class`
- `cash_flow_type`
- `regulatory_exposure`
- `counterparty_risk`
- `inflation_linkage`

This supports richer comparative analysis (e.g., regulated utility vs merchant midstream).

## 3.3 Jargon Quality Gates

Before output generation, run terminology QA:
- undefined jargon count
- inconsistent term usage (e.g., "contracted" vs "regulated" conflation)
- metric-definition mismatches across tabs/slides

---

## 4) Research Synthesis Upgrade: Evidence-Linked Intelligence

## 4.1 Claim-Evidence Graph

Introduce a simple graph object:
- **Claim** (text + confidence)
- **Evidence nodes** (source doc, section, period)
- **Contradictory evidence** (if any)
- **Resulting recommendation**

Every executive-summary bullet should map to at least one evidence node.

## 4.2 Delta Engine (Quarter-over-Quarter + Guidance vs Actual)

Add automated deltas for:
- Funds from operations / cash available for distribution trends
- Segment performance changes (price, volume, FX, utilization drivers)
- Leverage/coverage movement and covenant headroom changes

## 4.3 Benchmark Synthesis

Build comparable cohorts by infrastructure subtype and capital structure.
Output:
- percentile bands
- "within/above/below peer range" labels
- explanatory notes for apples-to-oranges adjustments

---

## 5) LP/GP Deal-Term Analyzer (High-Priority Capability)

Create a new module family:

## 5.1 Term Extraction

Parse and structure:
- management fee basis and step-down mechanics
- preferred return/hurdle terms
- carry waterfall (European/American nuances)
- catch-up structure
- GP commitment
- key-person and no-fault divorce clauses
- removal for cause / supermajority thresholds
- co-invest rights and fee/carry offsets
- recycling, recallable distributions, extension options

## 5.2 Term Quality Scoring

Produce LP-friendliness and GP-flexibility scores with explainable subscores:
- economics
- governance
- transparency/reporting
- liquidity/transfer

## 5.3 Red-Flag Detection

Rules-based triggers (e.g.):
- broad valuation discretion with weak LP oversight
- asymmetric information rights
- aggressive fee-on-committed-capital duration
- weak conflict-management provisions

Outputs should include a one-page "Negotiation Priorities" summary.

---

## 6) Brookfield Infrastructure Partners (BIP) Focus Pack

> Note: direct retrieval from `bip.brookfield.com` may be blocked in some execution environments; use redundant public-source ingestion from SEC filings, earnings transcripts, and investor presentations when direct site access fails.

## 6.1 Company Profile Template

Create a prebuilt profile object for BIP:
- segment taxonomy mapping
- historical KPI dictionary
- capital allocation framework summary
- payout/distribution framing
- leverage and refinancing watchlist

## 6.2 BIP-Specific Monitoring Views

- **Distribution sustainability dashboard**
- **Maturity wall + refinancing risk view**
- **FX/rates sensitivity overlay**
- **Regulatory/contract renewal calendar**

## 6.3 Q&A Simulator for LP Conversations

Generate likely LP questions and draft responses tied to sources:
- why distribution growth is sustainable/not
- sensitivity to rate environment and funding costs
- organic vs acquisition-driven growth quality
- asset rotation discipline and valuation realization risk

---

## 7) Implementation Phasing

## Phase 1 (2-3 weeks): Foundation
- Add ontology file + tagging interface.
- Add claim-evidence schema and citation tracking.
- Add telemetry fields for evidence quality.

## Phase 2 (3-5 weeks): Term Analytics
- Build LP/GP term extractor + scorer.
- Add red-flag rules and "Negotiation Priorities" output.
- Integrate into DDQ/fundraising case flows.

## Phase 3 (3-4 weeks): BIP Playbook + Benchmarking
- Build BIP profile template and monitoring dashboard modules.
- Add comparable peer synthesis and range labeling.
- Ship scenario prompts for infrastructure risk narratives.

## Phase 4 (2-3 weeks): Production Hardening
- QA rubric expansion for evidence completeness and term accuracy.
- Gold-test corpus for infra jargon and term parsing.
- Runbook documentation for analysts.

---

## 8) Success Metrics (How We Know It Worked)

- **Terminology precision**: >90% correct tagging on infra jargon validation set.
- **Evidence integrity**: <5% uncited summary claims in QA checks.
- **Term extraction recall**: >85% of critical LP/GP terms captured from sample agreements.
- **Analyst speed**: 30-40% reduction in time to first draft LP update.
- **Decision usefulness**: positive reviewer rating on negotiation-priority memos.

---

## 9) Immediate Next Actions

1. Add ontology + claim-evidence scaffolding files.
2. Add new module spec: `terms_analyzer`.
3. Add BIP profile skeleton and source ingestion checklist.
4. Update prompt library with "LP/GP term negotiation" prompt patterns.
5. Run pilot on one recent infra issuer package and score with QA rubric.
