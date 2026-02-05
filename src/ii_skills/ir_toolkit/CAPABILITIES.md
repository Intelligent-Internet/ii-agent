# IR Toolkit Capabilities (Infrastructure)

*Infra-first with general IR fallback; every Excel module has a paired slide output.*

## Module Map (Excel ↔ PowerPoint)

| Category | Excel Module | Paired Slide | Purpose | Infra Nuance |
|----------|--------------|--------------|---------|--------------|
| **Fund Overview** | | | | |
| | Fund Snapshot | Fund Overview Slide | Fund size, strategy, vintage, region mix | Regulatory regimes, contracted vs. merchant |
| | Performance Summary | Performance At-a-Glance | Net/GP/LP returns, DPI/RVPI/TVPI | Inflation linkage + cash yield stability |
| | Portfolio Composition | Portfolio Mix Slide | Sector, region, stage, currency, duration | Regulated vs. contracted assets split |
| | Leverage & Coverage | Leverage Profile Slide | Debt/EBITDA, DSCR, debt ladder | Amortization and covenants by asset |
| **Cash Flows** | | | | |
| | Cash Flow Waterfall | Distributions & Calls | Capital calls, distributions, net cash flow | Infra-specific yield stability |
| | IRR / MOIC Bridge | Returns Bridge Slide | Drivers of return changes | Valuation vs. cash yield drivers |
| | Distribution Coverage | Coverage Ratio Slide | Distributions vs. cash generation | Payout stability by quarter |
| **Asset Performance** | | | | |
| | Asset KPI Dashboard | Asset KPI Slide | Utilization, availability, uptime | Contracted capacity and penalties |
| | Revenue Quality | Revenue Quality Slide | Contract coverage, inflation escalators | Fixed/variable mix + CPI escalators |
| | Capex & Maintenance | Capex Plan Slide | Maintenance vs. growth capex | Lifecycle cost stress-tests |
| | Contract Roll-Off | Contract Tenor Slide | Expiry schedule by asset | Re-contracting risk timing |
| **Valuation** | | | | |
| | NAV Build | NAV Roll-forward Slide | Period NAV + key deltas | Discount rate + market spreads |
| | Valuation Sensitivity | Sensitivity Slide | Discount rate, exit multiples | Infra-specific yield spreads |
| | FX & Rates Impact | Macro Sensitivity Slide | FX, rates, inflation shocks | Base currency and hedging |
| **Risk** | | | | |
| | Risk Register | Risk & Mitigants Slide | Top risks with mitigation | Regulatory, inflation, counterparty |
| | Regulatory Reset Calendar | Regulatory Timeline Slide | Upcoming reset dates | Exposure windows and mitigants |
| **ESG** | | | | |
| | ESG / Impact Metrics | ESG Impact Slide | Emissions, safety, community | Grid reliability, safety KPIs |
| **Fundraising** | | | | |
| | Fundraising Pipeline | Pipeline Slide | LP funnel, stage, probability | Region + LP type segmentation |
| **LP Engagement** | | | | |
| | LP Coverage Map | Coverage & Cadence Slide | LP touchpoints by quarter | Private IR cadence |
| | DDQ Tracker | DDQ Progress Slide | Outstanding questions + owners | Time-to-response emphasis |
| **Benchmarking** | | | | |
| | Peer Benchmark | Benchmark Slide | Returns vs. peer quartiles | Infra cash yield profile adjustment |
| **Co-Invest** | | | | |
| | Co-Invest Allocation | Co-Invest Summary Slide | Ticket size, exposure, timeline | Asset-level risk sharing |
| **Terms** | | | | |
| | Fee & Carry Model | Economics Slide | Mgmt fee, carry, hurdle | Infra fee step-downs |
| | Term Sheet | Term Sheet Slide | Key terms (fees, governance) | Infra-specific protections |
| **Liquidity** | | | | |
| | Liquidity Profile | Liquidity & Exit Slide | Exit routes, timing, market | Long duration + optionality |
| **Scenario** | | | | |
| | Scenario Stress | Downside Case Slide | Revenue/capex/regulatory shocks | Regulatory reset stress |

## Core Outputs

### 1. LP Update (6-8 slides)
- Executive Summary
- Fund Performance (IRR/DPI/RVPI/TVPI)
- Cash Flows (calls/distributions)
- Asset KPI Highlights
- Valuation & Sensitivity
- Leverage & Coverage
- Risks & Mitigations
- Near-Term Outlook

### 2. Fundraising Deck (10-14 slides)
- Fund Overview & Strategy
- Track Record & Cash Yield
- Portfolio Construction
- Asset Case Studies (1-2)
- Pipeline & Sourcing
- Term Sheet Summary
- Risk & ESG Framework

### 3. DDQ Response Pack
- DDQ Tracker with owners/dates
- KPI Dashboards
- Disclosure summaries

## Infra-Specific KPI Set

| KPI | Description | Typical Range |
|-----|-------------|---------------|
| Contracted Revenue % | Revenue under long-term contracts | 70-95% |
| Inflation-Linked % | Revenue indexed to CPI | 40-80% |
| Availability / Uptime | Operational reliability | 95-99% |
| Regulated vs. Merchant | Revenue mix by type | Varies |
| TRIR | Safety incident rate | <1.0 |
| Maintenance Capex/Unit | Per-unit lifecycle cost | Varies |
| Counterparty Concentration | Top 5 counterparty % | <50% |
| DSCR | Debt service coverage | >1.3x |
| Contract Expiry (24-36mo) | Near-term rolloff % | <25% |

## Excel ↔ Slide Pairing Rules

1. **One table → one slide**: Every Excel output must appear in a slide table or chart
2. **Shared naming**: Excel tab name = slide title prefix (e.g., `NAV Roll-forward — Slide`)
3. **Same metric definitions**: KPI formulas must match in both Excel and slide footnotes

## Module Output Schema

Each analysis module produces:

```
- Inputs: [list of required fields]
- Assumptions: [explicit fallback logic]
- Excel Output Table: [row/column definitions]
- Slide Headline: [action-title, insight first]
- Chart Spec: [chart type + series]
```

## General IR Fallback (Non-Infra)

When infrastructure-specific data is missing, default to:
- Revenue stability indicators (recurring %)
- Customer concentration + retention
- Operating margin + cash conversion
- Contract length / renewal rate
