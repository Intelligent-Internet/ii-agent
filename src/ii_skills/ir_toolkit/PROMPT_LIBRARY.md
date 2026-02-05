# Prompt Library — Infrastructure IR

Ready-to-use prompts for common IR analysis requests.

## 1. LP Quarterly Update

**Prompt:**
```
Create an infrastructure LP quarterly update. Use Excel tables for fund
performance, cash flows, and asset KPIs, and produce matching slides.
Highlight contracted revenue %, inflation linkage, and regulatory exposure.

Inputs needed:
- Fund name and vintage
- Reporting period
- Performance metrics (IRR, DPI, RVPI, TVPI)
- Cash flow data (calls, distributions)
- Top 3 asset KPIs
```

**Sample Output:**
- Excel: Fund Performance Table (IRR/DPI/RVPI/TVPI by fund)
- Slide: "Fund returns remain in top-quartile driven by stable cash yield"

---

## 2. Fundraising Narrative

**Prompt:**
```
Build a fundraising deck outline for a global infrastructure strategy.
Provide Excel analysis for track record and portfolio mix and pair each
table with a slide. Include term sheet summary and ESG framework.

Inputs needed:
- Fund strategy and target size
- Historical track record
- Current portfolio composition
- Proposed terms (fees, carry, hurdle)
```

**Sample Output:**
- Excel: Portfolio mix by sector/region
- Slide: "Diversified portfolio reduces regulatory concentration risk"

---

## 3. Asset Performance Deep Dive

**Prompt:**
```
Generate an asset KPI dashboard (availability, utilization, contracted
coverage) and a slide summarizing top 3 KPIs for our largest asset.

Inputs needed:
- Asset name and type
- Quarterly KPI data (8 quarters)
- Contract details (tenor, counterparty)
- Safety metrics
```

**Sample Output:**
- Excel: KPI table with YoY deltas
- Slide: "Availability improved to 98.4% post-maintenance"

---

## 4. Downside Case Stress Test

**Prompt:**
```
Model a downside case with a 100 bps discount rate increase and a 10%
merchant price decline. Provide Excel sensitivity and a paired slide.

Inputs needed:
- Current NAV and discount rate
- Revenue split (contracted vs. merchant)
- Sensitivity parameters
```

**Sample Output:**
- Excel: Sensitivity grid for NAV
- Slide: "NAV remains resilient with <5% downside under stress"

---

## 5. DDQ Response Pack

**Prompt:**
```
Prepare DDQ tracker Excel outputs and a summary slide showing open
items, owners, and dates.

Inputs needed:
- DDQ question list
- Current status by question
- Owners and target dates
```

**Sample Output:**
- Excel: DDQ tracker table
- Slide: "85% of DDQ items closed; 3 high-priority pending"

---

## 6. NAV Roll-Forward

**Prompt:**
```
Build a NAV roll-forward with prior NAV, contributions, distributions,
valuation changes, and FX impact. Provide slide headline and waterfall chart.

Inputs needed:
- Prior period NAV
- Capital activity (calls, distributions)
- Valuation changes by driver
- FX impact
```

**Sample Output:**
- Excel: NAV driver breakdown table
- Slide: "NAV growth driven by cash yield and FX tailwinds"

---

## 7. Regulatory Reset View

**Prompt:**
```
Build a regulatory reset calendar for our regulated assets with upcoming
reset dates and mitigation actions. Output the table and a timeline slide.

Inputs needed:
- Asset list (regulated only)
- Reset dates and regulatory body
- Current rate base
- Mitigation actions
```

**Sample Output:**
- Excel: Reset schedule by asset and year
- Slide: "Regulatory resets are back-weighted with mitigants in place"

---

## 8. Distribution Coverage Analysis

**Prompt:**
```
Create a distribution coverage analysis by quarter (cash generated vs.
distributions) and pair it with a coverage slide.

Inputs needed:
- Quarterly cash generation (8 quarters)
- Quarterly distributions
- Target coverage ratio
```

**Sample Output:**
- Excel: Coverage ratio table with 8-quarter trend
- Slide: "Coverage remains >1.2x through the period"

---

## 9. Leverage & Coverage Profile

**Prompt:**
```
Build a leverage profile showing Debt/EBITDA, DSCR, and debt maturity
ladder with covenant headroom. Provide Excel and paired slide.

Inputs needed:
- Current debt by facility
- EBITDA (trailing 12 months)
- Debt service schedule
- Covenant thresholds
```

**Sample Output:**
- Excel: Leverage metrics + maturity ladder
- Slide: "Leverage remains conservative with strong coverage ratios"

---

## 10. Term Sheet Summary

**Prompt:**
```
Draft a term sheet summary table (fees, carry, hurdle, governance) and
provide a paired slide headline.

Inputs needed:
- Management fee structure
- Carry and hurdle
- Key LP protections
- Governance provisions
```

**Sample Output:**
- Excel: Term sheet table with key terms
- Slide: "Terms provide strong governance and alignment"

---

## 11. Peer Benchmarking

**Prompt:**
```
Create a peer benchmark analysis comparing fund performance to quartiles.
Include infra-specific adjustments for cash yield profile.

Inputs needed:
- Fund performance metrics
- Peer universe data
- Vintage adjustment factors
```

**Sample Output:**
- Excel: Performance vs. quartile table
- Slide: "Top-quartile performance vs. infrastructure peer group"

---

## 12. ESG Impact Summary

**Prompt:**
```
Build an ESG metrics dashboard with emissions, safety, and community
impact. Include infra-specific KPIs like grid reliability.

Inputs needed:
- Emissions data (Scope 1, 2, 3)
- Safety metrics (TRIR, LTIR)
- Community/social metrics
- Environmental certifications
```

**Sample Output:**
- Excel: ESG scorecard table
- Slide: "Strong ESG performance across safety and emissions"

---

## Prompt Structure Template

For any IR analysis, use this structure:

```
[Action]: Create/Build/Generate/Analyze
[Module]: [specific module from capabilities]
[Data requirements]: [list specific inputs]
[Output format]: Excel table + paired slide
[Infra nuance]: [specific infra elements to highlight]
```
