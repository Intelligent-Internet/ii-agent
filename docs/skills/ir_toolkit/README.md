# IR Toolkit Documentation

Infrastructure Investor Relations Toolkit for LP communications, fundraising, and DDQ responses.

## Core Principle

**Every Excel analysis has a corresponding PowerPoint slide.**

## Quick Start

```python
from ii_skills.ir_toolkit import IRToolkit, IRCaseType

toolkit = IRToolkit(user_id="user")

# Generate LP quarterly update
result = await toolkit.generate_lp_update(
    fund_name="Global Infrastructure Fund IV",
    reporting_period="Q4 2025",
)

# Generate fundraising deck
result = await toolkit.generate_fundraising_deck(
    fund_name="Global Infrastructure Fund V",
)

# Generate DDQ response
result = await toolkit.generate_ddq_response(
    fund_name="Global Infrastructure Fund IV",
)
```

## Documentation Files

| Document | Description |
|----------|-------------|
| [CAPABILITIES.md](../../../src/ii_skills/ir_toolkit/CAPABILITIES.md) | Complete reference of all 33 Excel ↔ Slide modules |
| [CASE_GUIDE.md](../../../src/ii_skills/ir_toolkit/CASE_GUIDE.md) | How to approach IR deliverables by timeframe |
| [PROMPT_LIBRARY.md](../../../src/ii_skills/ir_toolkit/PROMPT_LIBRARY.md) | 12 ready-to-use prompts for common tasks |
| [QUICK_REFERENCE.md](../../../src/ii_skills/ir_toolkit/QUICK_REFERENCE.md) | Request keywords → Module mapping |
| [BEST_PRACTICES.md](../../../src/ii_skills/ir_toolkit/BEST_PRACTICES.md) | Deck structure and Excel model architecture |
| [SCENARIO_LIBRARY.md](../../../src/ii_skills/ir_toolkit/SCENARIO_LIBRARY.md) | 8 stress test scenarios |
| [DATA_ROOM_CHECKLIST.md](../../../src/ii_skills/ir_toolkit/DATA_ROOM_CHECKLIST.md) | Fundraising data room preparation |
| [QA_RUBRIC.md](../../../src/ii_skills/ir_toolkit/QA_RUBRIC.md) | Quality assurance scoring (1-5 scale) |
| [infra_jargon_metrics.md](../../../src/ii_skills/ir_toolkit/references/infra_jargon_metrics.md) | Infrastructure terminology guide |

## Case Types

| Case Type | Modules | Use Case |
|-----------|---------|----------|
| LP Update | 6 | Quarterly LP communications |
| Fundraising | 12 | New fund marketing materials |
| DDQ Response | 3 | Due diligence questionnaire packs |
| Annual Meeting | 12 | AGM presentations |
| Crisis Comms | 4 | Rapid response materials |

## Module Categories

### Fund Overview (4 modules)
- Fund Snapshot - strategy, size, vintage
- Performance Summary - IRR, DPI, RVPI, TVPI
- Portfolio Composition - sector, geography
- Track Record - historical returns

### Cash Flows (3 modules)
- Cash Flow Waterfall - calls, distributions
- Distribution Coverage - coverage ratios
- IRR Bridge - return attribution

### Asset Performance (4 modules)
- Asset KPI Dashboard - availability, utilization
- Revenue Quality - contracted vs merchant
- Capex Tracker - maintenance, growth
- Contract Summary - WACL, counterparty

### Valuation (3 modules)
- NAV Roll-forward - drivers, FX
- Sensitivity Analysis - discount rate
- Macro Exposure - inflation, rates

### Risk (2 modules)
- Risk Register - top risks, mitigation
- Regulatory Calendar - reset dates

### ESG (1 module)
- ESG Metrics - emissions, safety

### Fundraising (4 modules)
- LP Pipeline - prospects, funnel
- DDQ Tracker - questions, status
- Term Sheet - fees, carry, hurdle
- Data Room Checklist - documents

## Infrastructure-Specific Metrics

| Metric | Definition | Target |
|--------|------------|--------|
| **Contracted Revenue %** | Revenue under long-term contracts | 70-95% |
| **WACL** | Weighted Average Contract Life | 8-15 years |
| **Availability** | Uptime percentage | >95% |
| **DSCR** | Debt Service Coverage Ratio | >1.3x |
| **CPI Linkage** | Revenue indexed to inflation | Higher = better |
| **Rate Base** | Regulated asset value | Growing = positive |

## Example Prompts

### LP Quarterly Update
```
Create an infrastructure LP quarterly update. Use Excel tables for fund
performance, cash flows, and asset KPIs, and produce matching slides.
Highlight contracted revenue %, inflation linkage, and regulatory exposure.

Inputs:
- Fund: Global Infrastructure Fund IV
- Period: Q4 2025
- Metrics: IRR 14.2%, DPI 0.35, TVPI 1.63
```

### Fundraising Deck
```
Build a fundraising deck for a global infrastructure strategy.
Provide Excel analysis for track record and portfolio mix.
Include term sheet summary and ESG framework.

Inputs:
- Fund: Global Infrastructure Fund V
- Target size: $3.5B
- Strategy: Core/Core+ infrastructure
```

### NAV Roll-Forward
```
Build a NAV roll-forward with prior NAV, contributions, distributions,
valuation changes, and FX impact. Provide slide headline and waterfall chart.

Inputs:
- Prior NAV: $2.2B
- Contributions: $150M
- Distributions: $80M
- FX impact: +$45M
```

## Differences from IB Toolkit

| Aspect | IB Toolkit | IR Toolkit |
|--------|------------|------------|
| **Focus** | PE/IB deal analysis | Infrastructure fund IR |
| **Audience** | Investment committee | Limited partners |
| **Output** | LBO models, IC decks | LP updates, fundraising |
| **Metrics** | IRR, MOIC, leverage | DSCR, availability, WACL |
| **Timeframe** | Deal lifecycle | Reporting periods |

The IR Toolkit is **orthogonal** to the IB Toolkit - they serve different use cases and can be used independently.

---

*Source: ii-agent skills system*
