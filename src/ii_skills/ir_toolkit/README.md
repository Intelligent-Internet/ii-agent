# Infrastructure Investor Relations Toolkit

An infrastructure-first investor relations (IR) case framework for LP updates, fundraising decks, and DDQ responses. Designed for private infrastructure fund IR work.

## Core Principle

**Every Excel analysis has a corresponding PowerPoint slide output.** The Excel ↔ Slide pairing ensures consistency between data and presentation.

## Key Differences from IB/PE Toolkit

| Aspect | IB/PE Toolkit | IR Toolkit |
|--------|---------------|------------|
| **Focus** | Deal execution (LBO, M&A) | Fund reporting & LP communication |
| **Audience** | Investment committee, buyers | LPs, prospective investors |
| **Key Metrics** | IRR, MOIC, entry/exit multiples | DPI, RVPI, TVPI, NAV, cash yield |
| **Time Horizon** | Transaction-based | Quarterly/annual reporting cycles |
| **Infra Nuance** | Deal structure, debt capacity | Contracted revenue, regulatory reset, availability |

## Quick Start

```python
from ii_skills.ir_toolkit import IRToolkit

# Create LP quarterly update
toolkit = IRToolkit(user_id="user123")
result = await toolkit.generate_lp_update(
    fund_name="Global Infrastructure Fund IV",
    reporting_period="Q4 2025",
    case_type="lp_update",
)
```

## Module Categories

### Fund Overview
- Fund Snapshot → Fund Overview Slide
- Performance Summary → Performance At-a-Glance Slide
- Portfolio Composition → Portfolio Mix Slide
- Leverage & Coverage → Leverage Profile Slide

### Cash Flows
- Cash Flow Waterfall → Distributions & Calls Slide
- IRR/MOIC Bridge → Returns Bridge Slide
- Distribution Coverage → Coverage Ratio Slide

### Asset Performance
- Asset KPI Dashboard → Asset KPI Slide
- Revenue Quality → Revenue Quality Slide
- Capex & Maintenance → Capex Plan Slide
- Contract Roll-Off → Contract Tenor Slide

### Valuation
- NAV Build → NAV Roll-forward Slide
- Valuation Sensitivity → Sensitivity Slide
- FX & Rates Impact → Macro Sensitivity Slide

### Risk & ESG
- Risk Register → Risk & Mitigants Slide
- Regulatory Reset Calendar → Regulatory Timeline Slide
- ESG/Impact Metrics → ESG Impact Slide

### Fundraising & LP Engagement
- Fundraising Pipeline → Pipeline Slide
- LP Coverage Map → Coverage & Cadence Slide
- DDQ Tracker → DDQ Progress Slide
- Term Sheet → Term Sheet Slide

## Case Types

| Case Type | Slides | Excel Modules | Timeframe |
|-----------|--------|---------------|-----------|
| LP Update | 6-8 | Performance, Cash Flow, Asset KPIs | 30-60 min |
| Fundraising Deck | 10-14 | Full suite + track record | 2-4 hours |
| DDQ Response | 4-6 | DDQ Tracker, Risk, ESG | 1-2 hours |
| Annual Meeting | 12-16 | Full suite + outlook | 4-8 hours |

## Infra-Specific KPIs

- Contracted revenue % (by asset)
- Inflation-linked revenue %
- Availability / uptime
- Regulated vs. merchant exposure
- Safety incidents (TRIR)
- Maintenance capex per unit capacity
- Counterparty concentration
- DSCR / coverage ratios
- Contract expiry concentration

## Templates & References

- `templates/excel/` - Excel model templates
- `templates/slides/` - PowerPoint slide templates
- `references/` - Jargon, metrics, ontology, schemas
- `benchmark_library/` - Peer benchmarking data
- `modules/` - Analysis module specifications (terms analyzer, company profiles)

## Documentation

- `CAPABILITIES.md` - Full module map
- `QUICK_REFERENCE.md` - Request → Module lookup
- `CASE_GUIDE.md` - Timeboxed approach guide
- `BEST_PRACTICES.md` - Deck structure and formatting
- `SCENARIO_LIBRARY.md` - Stress test scenarios
- `DATA_ROOM_CHECKLIST.md` - Fundraising data room prep
- `QA_RUBRIC.md` - Quality assurance scoring
- `ROADMAP_II_AGENT_IR_TOOLKIT.md` - Expansion strategy for II Agent integration, infra terminology depth, and LP/GP term analytics
