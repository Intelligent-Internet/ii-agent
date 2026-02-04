# Module M5: Projection Build / Validation
## Middle Market Transaction Analysis

*Time: 30-45 minutes | Prerequisite: M4 (Historical Analysis)*

---

## Objective

Build or validate financial projections that form the basis for valuation and returns analysis. This module ensures projections are grounded in reality and internally consistent.

---

## Projection Framework

### Step 1: Projection Approach Selection (5 min)

#### Choose Your Approach

| Scenario | Approach | Time Required |
|----------|----------|---------------|
| No projections provided | Build from scratch | 45 min |
| Management projections provided | Validate and adjust | 30 min |
| Model with projections provided | Sensitivity analysis | 20 min |

#### Key Projection Principles

1. **Anchor to historical**: Projections should connect logically to historical performance
2. **Growth deceleration**: High-growth companies naturally slow down
3. **Margin realism**: Operating leverage has limits
4. **Cash awareness**: Profitable ≠ cash-generative

---

### Step 2: Revenue Projection (15-20 min)

#### Revenue Driver Identification

| Business Model | Primary Drivers | Build Method |
|----------------|-----------------|--------------|
| **SaaS/Subscription** | Customers × ARPU × Retention | Cohort model |
| **Transaction/GMV** | Volume × Take rate | Volume growth model |
| **Services** | Headcount × Utilization × Rate | Capacity model |
| **Product** | Units × Price | Volume/price model |
| **Recurring + One-time** | Base × Retention + New wins | Hybrid model |

#### SaaS Revenue Build

```
Beginning ARR                    $___M
+ New Logo ARR                   $___M  (Logos × Starting ARPU)
+ Expansion ARR                  $___M  (Base × Expansion Rate)
- Churned ARR                   ($___M) (Base × Churn Rate)
= Ending ARR                     $___M

Revenue Recognition Adjustment:
- Ending ARR                     $___M
- Beginning ARR                  $___M
- Avg ARR                        $___M
- Recognized Revenue             $___M  (≈ Avg ARR)
```

#### Revenue Projection Template

| Line Item | 2024A | 2025E | 2026E | 2027E | 2028E | 2029E |
|-----------|-------|-------|-------|-------|-------|-------|
| **Volume Driver** | | | | | | |
| Beginning customers | __ | __ | __ | __ | __ | __ |
| + Gross adds | __ | __ | __ | __ | __ | __ |
| - Churn | (__) | (__) | (__) | (__) | (__) | (__) |
| = Ending customers | __ | __ | __ | __ | __ | __ |
| **Price Driver** | | | | | | |
| ARPU ($K) | __ | __ | __ | __ | __ | __ |
| ARPU growth | __% | __% | __% | __% | __% | __% |
| **Revenue** | | | | | | |
| Revenue ($M) | __ | __ | __ | __ | __ | __ |
| Growth % | __% | __% | __% | __% | __% | __% |

#### Assumption Justification

| Assumption | Value | Historical | Rationale |
|------------|-------|------------|-----------|
| Customer growth | __% → __% | __% avg | [Why this trajectory] |
| ARPU growth | __% | __% avg | [Pricing power, mix shift] |
| Gross churn | __% | __% avg | [Why this level] |
| Net retention | ___% | ___% avg | [Expansion drivers] |

---

### Step 3: Expense & Margin Projection (10-15 min)

#### Cost Structure Analysis

| Cost Type | Driver | Projection Method |
|-----------|--------|-------------------|
| **COGS** | % of revenue | Scale with revenue, slight improvement |
| **S&M** | % of revenue or headcount | Investment phase vs. efficiency phase |
| **R&D** | % of revenue or headcount | Investment level decision |
| **G&A** | Fixed + % of revenue | Operating leverage |

#### Margin Projection Template

| Line Item | 2024A | 2025E | 2026E | 2027E | 2028E | 2029E |
|-----------|-------|-------|-------|-------|-------|-------|
| **Revenue** | $__M | $__M | $__M | $__M | $__M | $__M |
| **Gross Profit** | | | | | | |
| COGS | $__M | $__M | $__M | $__M | $__M | $__M |
| % of revenue | __% | __% | __% | __% | __% | __% |
| Gross Profit | $__M | $__M | $__M | $__M | $__M | $__M |
| Gross Margin | __% | __% | __% | __% | __% | __% |
| **Operating Expenses** | | | | | | |
| S&M | $__M | $__M | $__M | $__M | $__M | $__M |
| % of revenue | __% | __% | __% | __% | __% | __% |
| R&D | $__M | $__M | $__M | $__M | $__M | $__M |
| % of revenue | __% | __% | __% | __% | __% | __% |
| G&A | $__M | $__M | $__M | $__M | $__M | $__M |
| % of revenue | __% | __% | __% | __% | __% | __% |
| **EBITDA** | $__M | $__M | $__M | $__M | $__M | $__M |
| EBITDA Margin | __% | __% | __% | __% | __% | __% |

#### Margin Bridge

```
LTM EBITDA Margin:              ___%
+ Gross margin expansion:       +___%  [Why: ___________]
+ S&M leverage:                 +___%  [Why: ___________]
+ R&D leverage:                 +___%  [Why: ___________]
+ G&A leverage:                 +___%  [Why: ___________]
= Exit Year EBITDA Margin:      ___%
```

---

### Step 4: Cash Flow Projection (5-10 min)

#### Working Capital Assumptions

| Component | % of Revenue | Days | Rationale |
|-----------|--------------|------|-----------|
| A/R | __% | __ DSO | [Payment terms] |
| Inventory | __% | __ DIO | [Turnover] |
| A/P | __% | __ DPO | [Supplier terms] |
| Accrued expenses | __% | — | [Timing] |
| **Net WC** | **__%** | — | [Trend] |

#### Capex Assumptions

| Type | % of Revenue | $ Amount | Rationale |
|------|--------------|----------|-----------|
| Maintenance capex | __% | $__M | [≈ D&A] |
| Growth capex | __% | $__M | [Investments] |
| **Total Capex** | **__%** | **$__M** | |

#### Free Cash Flow Projection

| Line Item | 2024A | 2025E | 2026E | 2027E | 2028E | 2029E |
|-----------|-------|-------|-------|-------|-------|-------|
| EBITDA | $__M | $__M | $__M | $__M | $__M | $__M |
| - D&A | ($__M) | ($__M) | ($__M) | ($__M) | ($__M) | ($__M) |
| EBIT | $__M | $__M | $__M | $__M | $__M | $__M |
| - Taxes (@ __%) | ($__M) | ($__M) | ($__M) | ($__M) | ($__M) | ($__M) |
| EBIAT | $__M | $__M | $__M | $__M | $__M | $__M |
| + D&A | $__M | $__M | $__M | $__M | $__M | $__M |
| - Capex | ($__M) | ($__M) | ($__M) | ($__M) | ($__M) | ($__M) |
| - Δ NWC | ($__M) | ($__M) | ($__M) | ($__M) | ($__M) | ($__M) |
| **Unlevered FCF** | **$__M** | **$__M** | **$__M** | **$__M** | **$__M** | **$__M** |
| FCF Conversion | __% | __% | __% | __% | __% | __% |

---

### Step 5: Projection Validation (5 min)

#### Sanity Checks

| Check | Calculation | Result | Pass? |
|-------|-------------|--------|-------|
| Revenue CAGR reasonable | [Entry] → [Exit] | __% | ✓/✗ |
| Growth deceleration | Year 1 vs Year 5 | __% → __% | ✓/✗ |
| Margin expansion realistic | [Entry] → [Exit] | __% → __% | ✓/✗ |
| FCF conversion improving | [Entry] → [Exit] | __% → __% | ✓/✗ |
| Implied productivity | Rev/employee | $__K → $__K | ✓/✗ |

#### Comparison to Management Case

| Metric | Your Projection | Mgmt Projection | Delta | Why Different |
|--------|-----------------|-----------------|-------|---------------|
| Exit Revenue | $__M | $__M | __% | [Reason] |
| Exit EBITDA | $__M | $__M | __% | [Reason] |
| Exit Margin | __% | __% | __ bps | [Reason] |
| Revenue CAGR | __% | __% | __ bps | [Reason] |

#### Rule of 40 Check (SaaS)

| Year | Growth % | EBITDA Margin % | Rule of 40 |
|------|----------|-----------------|------------|
| 2024A | __% | __% | __ |
| 2025E | __% | __% | __ |
| 2026E | __% | __% | __ |
| 2027E | __% | __% | __ |
| 2028E | __% | __% | __ |
| 2029E | __% | __% | __ |

---

## Output Template

```markdown
## Projection Summary: [Company Name]

### Key Metrics
| Metric | LTM | Year 5 | CAGR |
|--------|-----|--------|------|
| Revenue | $__M | $__M | __% |
| EBITDA | $__M | $__M | __% |
| EBITDA Margin | __% | __% | +__ bps |
| FCF | $__M | $__M | __% |

### Key Assumptions
| Driver | Assumption | Rationale |
|--------|------------|-----------|
| Revenue growth | __% → __% | [Why] |
| Gross margin | __% → __% | [Why] |
| EBITDA margin | __% → __% | [Why] |
| Capex % rev | __% | [Why] |
| NWC % rev | __% | [Why] |

### Projection vs Management
- Revenue: [Higher/Lower/In-line] by __% - [Why]
- EBITDA: [Higher/Lower/In-line] by __% - [Why]

### Sensitivity Drivers
1. [Most sensitive assumption]
2. [Second most sensitive]
3. [Third most sensitive]

### Risks to Projections
1. [Downside risk 1]
2. [Downside risk 2]
```

---

## Common Projection Mistakes

| Mistake | Problem | Fix |
|---------|---------|-----|
| Hockey stick revenue | Unrealistic acceleration | Anchor to historical growth rates |
| Linear margin expansion | Ignores investment needs | Model investment phases |
| No growth deceleration | Math doesn't work at scale | Use decay function |
| Ignoring working capital | Cash trap | Model NWC as % of revenue |
| Capex = D&A forever | Under-invests for growth | Split maintenance vs. growth |

---

*Module Version: 1.0.0*
*Estimated Time: 30-45 minutes*
