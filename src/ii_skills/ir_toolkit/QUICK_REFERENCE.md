# Quick Reference — IR Toolkit

## Key Documentation

| Document | Purpose |
|----------|---------|
| `CAPABILITIES.md` | Complete module reference (33 Excel ↔ Slide pairs) |
| `CASE_GUIDE.md` | Phased workflow, quality gates, common mistakes, IC vs LP guide |
| `PROMPT_LIBRARY.md` | 24 ready-to-use prompts (core + interview prep + Anki) |
| `SLIDE_LAYOUTS.md` | Visual slide templates with ASCII diagrams |
| `references/infra_jargon_metrics.md` | Infrastructure terminology guide |
| `references/infra_ontology.yml` | Machine-readable infra taxonomy (asset classes, revenue profiles, financing, ops) |
| `references/claim_evidence_schema.yml` | Schema for evidence-linked synthesis |
| `references/ir_event_schemas.yml` | Typed event payloads for workflow telemetry |
| `modules/terms_analyzer.md` | LP/GP deal-term analyzer spec (extraction, scoring, red flags) |
| `modules/company_profiles/bip.yml` | Brookfield Infrastructure Partners profile skeleton |
| `ROADMAP_II_AGENT_IR_TOOLKIT.md` | Expansion game plan (ontology, term analytics, BIP, benchmarking) |

---

## Request → Module Mapping

| Request / Keyword | Primary Excel Modules | Paired Slides |
|-------------------|----------------------|---------------|
| "LP update" | Performance Summary, Cash Flow Waterfall, Asset KPI Dashboard | Fund Performance, Distributions & Calls, Asset KPI |
| "fundraising deck" | Fund Snapshot, Portfolio Mix, Track Record | Fund Overview, Portfolio Mix, Track Record |
| "DDQ" | DDQ Tracker, Risk Register | DDQ Progress, Risks |
| "NAV drivers" | NAV Roll-forward, Valuation Sensitivity | NAV Driver, Sensitivity |
| "risk review" | Risk Register, Scenario Stress | Risk & Mitigants, Downside Case |
| "ESG" | ESG Metrics | ESG Impact |
| "co-invest" | Co-Invest Allocation | Co-Invest Summary |
| "coverage" | Distribution Coverage, Leverage & Coverage | Coverage Ratio, Leverage Profile |
| "regulatory reset" | Regulatory Reset Calendar | Regulatory Timeline |
| "contract roll-off" | Contract Roll-Off | Contract Tenor |
| "data room" | Data Room Checklist | Data Room Status |
| "term sheet" | Term Sheet | Term Sheet Summary |
| "performance" | Performance Summary, IRR/MOIC Bridge | Performance At-a-Glance, Returns Bridge |
| "cash flow" | Cash Flow Waterfall, Distribution Coverage | Distributions & Calls, Coverage Ratio |
| "asset KPI" | Asset KPI Dashboard, Revenue Quality | Asset KPI, Revenue Quality |
| "valuation" | NAV Build, Valuation Sensitivity | NAV Roll-forward, Sensitivity |
| "leverage" | Leverage & Coverage | Leverage Profile |
| "pipeline" | Fundraising Pipeline | Pipeline Slide |
| "benchmark" | Peer Benchmark | Benchmark Slide |
| "term analysis" | Term Extraction, LP-Friendliness Scorecard | Term Sheet Overview, Terms Quality Summary |
| "red flags" | Red-Flag Register | Negotiation Priorities |
| "negotiation" | Negotiation Priorities Summary | Negotiation Priorities |
| "term comparison" | Term Comparison (Fund-over-Fund) | Terms Evolution |
| "BIP" / "Brookfield" | BIP Profile Pack | BIP Monitoring Views |
| "claim evidence" | Claim-Evidence Graph | Evidence Trail (footnotes) |

## Case Type → Module Set

### LP Quarterly Update (30-60 min)
```
Excel: Performance Summary + Cash Flow Waterfall + Asset KPI Dashboard
Slides: 6-8 slides (Exec Summary, Performance, Cash Flow, Asset KPIs, Risks, Outlook)
```

### Fundraising Deck (2-4 hours)
```
Excel: Full suite + Track Record + Term Sheet
Slides: 10-14 slides (Strategy, Track Record, Portfolio, Case Studies, Pipeline, Terms, Risk/ESG)
```

### DDQ Response (1-2 hours)
```
Excel: DDQ Tracker + Risk Register + ESG Metrics
Slides: 4-6 slides (DDQ Progress, Risk Summary, ESG Impact)
```

### Annual Meeting (4-8 hours)
```
Excel: Full suite + Scenario Stress + Peer Benchmark
Slides: 12-16 slides (Full LP Update + Outlook + Strategic Discussion)
```

## Infra-Specific Keywords

| Keyword | Triggers | Nuance to Include |
|---------|----------|-------------------|
| "contracted" | Revenue Quality, Contract Roll-Off | % contracted, average contract life |
| "regulated" | Regulatory Reset Calendar | Rate base, reset timing, mitigants |
| "inflation" | Revenue Quality, Macro Sensitivity | CPI linkage %, pass-through mechanism |
| "availability" | Asset KPI Dashboard | Uptime %, penalties, targets |
| "DSCR" | Leverage & Coverage | Coverage by asset, covenant headroom |
| "merchant" | Revenue Quality, Scenario Stress | Merchant % exposure, price risk |

## Output Format Quick Reference

| Request | Excel Output | Slide Output |
|---------|--------------|--------------|
| "table" | Formatted table with headers | Table on slide |
| "chart" | Data table for charting | Chart + data callout |
| "waterfall" | Driver breakdown table | Waterfall chart |
| "sensitivity" | Grid of scenarios | Heat map or matrix |
| "timeline" | Date-based schedule | Gantt or timeline |

## Interview Prep Quick Reference

| Need | Use Prompt # | Output |
|------|--------------|--------|
| Q&A preparation | 19 | 50-question prep document |
| Cheat sheet | 20 | 1-page memorization sheet |
| Mock interview | 21 | Interactive 15-question session |
| 60-second pitch | 22 | Scripted verbal pitch |
| IR fundamentals flashcards | 23 | 80-card Anki TSV |
| Case-specific flashcards | 24 | 50-card Anki TSV |
| Term sheet red-flag scan | 25 | Red-flag register + negotiation priorities |
| Negotiation priorities memo | 26 | 1-page negotiation summary |
| Term comparison (fund vs peers) | 27 | Side-by-side term comparison |
| LP-friendliness scorecard | 28 | Scored term quality assessment |

## Phased Workflow Summary

| Phase | Focus | Key Outputs |
|-------|-------|-------------|
| 0 | Triage & Intake | Execution plan |
| 1 | Data Foundation | Excel + Key Metrics Table |
| 2 | Research & Narrative | DDQ drafts, LP comms |
| 3 | LP Presentation | .pptx file |
| 4 | Polish & Supporting | Final formatting, Q&A prep |
| 5 | Final QA | Consistency audit, interview readiness |

See `CASE_GUIDE.md` for full workflow details.

---

*Version: 2.0 | Last Updated: February 2026*
