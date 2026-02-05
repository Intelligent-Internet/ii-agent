# IR Best Practices (Infrastructure, Private IR)

*Infra-first with general IR fallback.*

## 1. Deck Structure Guidelines

### LP Update (6-8 Slides)
1. **Executive Summary** — Performance snapshot, key wins/risks
2. **Fund Performance** — IRR/DPI/RVPI/TVPI and drivers
3. **Cash Flows** — Calls/distributions, net cash flow
4. **Asset Highlights** — 2-3 asset KPI spotlights
5. **Valuation & Sensitivity** — NAV drivers + discount rate sensitivity
6. **Leverage & Coverage** — Debt profile and DSCR
7. **Risks & Mitigations** — Regulatory, inflation, counterparty
8. **Near-Term Outlook** — Catalysts, refinancing, capex

### Fundraising Deck (10-14 Slides)
- Strategy + edge in infrastructure
- Track record & realized cash yield
- Portfolio construction philosophy
- Asset case studies (1-2)
- Pipeline & sourcing advantages
- Term sheet summary (fees, governance, protections)
- Risk management + ESG framework

## 2. Excel Model Architecture

### Tab Order (IR Model)
1. Cover / Inputs
2. Portfolio Summary
3. Asset KPIs
4. Cash Flows (Calls/Distributions)
5. Returns (IRR/MOIC/DPI/RVPI/TVPI)
6. NAV Roll-forward
7. Valuation Sensitivity
8. Risk Register
9. ESG Metrics
10. Scenario Stress

### Formatting Standards
- **Inputs**: Blue font
- **Assumptions**: Light blue background
- **Formulas**: Black font
- **Links**: Green font (to other tabs)
- **Hardcodes**: Blue font (clearly labeled)

### Layout Rules
- History vs. projection clearly separated (vertical line)
- Currency + date conventions consistent with fund reporting
- All assumptions documented in dedicated section
- Version control in footer (date, initials)

## 3. Infra-Specific Storytelling

### Contracted vs. Merchant
- Always show % contracted and average contract life
- Highlight counterparty credit quality
- Note re-contracting risk timing

### Inflation Linkage
- Quantify escalators (CPI + spread)
- Explain pass-through mechanisms
- Show lag between inflation and revenue impact

### Regulatory Exposure
- Explain rate-base framework
- Show reset schedule and exposure windows
- Document mitigants and hedges

### Cash Yield Stability
- Highlight distribution coverage ratio trends
- Show payout volatility vs. peers
- Emphasize recurring vs. one-time distributions

## 4. Risk Framework

### Top Infra Risks to Address
1. **Regulatory Reset** — Tariff/rate changes at review
2. **Counterparty Credit** — Deterioration of offtakers
3. **Capex Overrun** — Lifecycle cost spikes
4. **Merchant Volatility** — Price exposure on uncontracted capacity
5. **Operational Availability** — Downtime penalties
6. **FX/Rates** — Cross-border currency and rate exposure

### Risk Slide Best Practices
- Use probability × impact matrix
- Show mitigation action for each risk
- Include timeline for risk events (regulatory resets)

## 5. Excel → Slide Discipline

### Pairing Rules
Every Excel analysis must produce a slide:

| Excel Output | Slide Type |
|--------------|------------|
| KPI table | KPI dashboard slide |
| NAV roll-forward | NAV driver slide (waterfall) |
| Cash flow waterfall | Distribution slide |
| Scenario sensitivity | Stress-case slide (heat map) |
| Coverage ratios | Coverage trend slide (line chart) |
| Risk register | Risk matrix slide |

### Headline Guidelines
- Use action-titles (insight first, not description)
- Good: "Cash yield remains stable despite capex uptick"
- Bad: "Q4 2025 Cash Flow Summary"

## 6. Chart Selection Guide

| Data Type | Recommended Chart |
|-----------|-------------------|
| Period comparison | Clustered bar |
| Trend over time | Line chart |
| Component breakdown | Stacked bar |
| Driver attribution | Waterfall |
| Two-variable sensitivity | Heat map / matrix |
| Timeline / schedule | Gantt chart |
| Composition | Pie or treemap |

## 7. Quality Assurance Checklist

Before finalizing:
- [ ] All Excel numbers match slide numbers
- [ ] KPI definitions consistent throughout
- [ ] Assumptions documented and reasonable
- [ ] Coverage ratios reconcile to cash flow tables
- [ ] Infra nuance explicit (contracted, regulated, etc.)
- [ ] Action-title headlines on all slides
- [ ] Footnotes explain any non-standard calculations
- [ ] Version/date in footer

## 8. Common Pitfalls to Avoid

1. **Mismatched numbers** — Excel and slide don't agree
2. **Missing infra context** — Generic IR without infrastructure nuance
3. **Description headlines** — "Performance Summary" instead of insight
4. **Undefined acronyms** — DSCR, TRIR without explanation
5. **Inconsistent units** — $M vs. $B, % vs. bps
6. **Stale benchmarks** — Using outdated peer data
7. **Missing assumptions** — Sensitivity without base case
