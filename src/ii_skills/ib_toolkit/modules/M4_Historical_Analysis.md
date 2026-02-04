# Module M4: Historical Financial Analysis
## Middle Market Transaction Analysis

*Time: 20-30 minutes | Prerequisite: Historical financials (3-5 years)*

---

## Objective

Analyze historical financials to understand the business trajectory, identify trends, and assess quality of earnings. This module informs your projection assumptions and surfaces diligence questions.

---

## Historical Analysis Framework

### Step 1: Data Extraction (5 min)

Pull these metrics from the financials provided:

| Metric | Year 1 | Year 2 | Year 3 | LTM | Source |
|--------|--------|--------|--------|-----|--------|
| **Revenue** | | | | | |
| Revenue Growth % | | | | | Calc |
| **Gross Profit** | | | | | |
| Gross Margin % | | | | | Calc |
| **EBITDA** | | | | | |
| EBITDA Margin % | | | | | Calc |
| **Capex** | | | | | |
| Capex % of Revenue | | | | | Calc |
| **Working Capital** | | | | | |
| NWC % of Revenue | | | | | Calc |

### Step 2: Trend Analysis (10 min)

#### Revenue Trends
```
Revenue Bridge (Year 1 → LTM)
├── Starting Revenue:     $___M
├── Volume Growth:        $___M  (___%)
├── Price Increases:      $___M  (___%)
├── New Products/Markets: $___M  (___%)
├── Acquisitions:         $___M  (___%)
├── Lost Customers:      ($___M) (___%)
└── Ending Revenue:       $___M
    CAGR: ____%
```

**Key Questions:**
- Is growth organic or acquired?
- Is growth accelerating or decelerating?
- What's driving growth - volume, price, or mix?

#### Margin Trends
```
EBITDA Margin Bridge (Year 1 → LTM)
├── Starting Margin:      ____%
├── Gross Margin Change:  ____%  [Why: ____________]
├── S&M Leverage:         ____%  [Why: ____________]
├── G&A Leverage:         ____%  [Why: ____________]
├── Other:                ____%  [Why: ____________]
└── Ending Margin:        ____%
```

**Key Questions:**
- Are margins expanding or compressing?
- Is gross margin stable? (Input cost risk)
- Are operating expenses scaling?

---

## Step 3: Quality of Earnings Analysis (10 min)

### Common Middle Market Adjustments

Review any EBITDA add-backs in the CIM. Assess reasonableness:

| Adjustment | Amount | Recurring? | Appropriate? | Notes |
|------------|--------|------------|--------------|-------|
| Owner Compensation | $___M | No | Usually yes | Market comp for replacement? |
| One-time Legal/Prof | $___M | No | Verify | Was it truly one-time? |
| Non-recurring Revenue | $___M | No | Maybe | Why won't it recur? |
| Related Party Rent | $___M | Depends | Verify | At market rate? |
| Pro Forma Savings | $___M | Future | Skeptical | Achievable? Timeline? |
| COVID Impact | $___M | No | Historical | Normalize both ways |
| **Total Adjustments** | **$___M** | | | |

### Adjusted vs Reported EBITDA

| Year | Reported EBITDA | Adjustments | Adjusted EBITDA | Difference |
|------|-----------------|-------------|-----------------|------------|
| Year 1 | $___M | $___M | $___M | ___% |
| Year 2 | $___M | $___M | $___M | ___% |
| Year 3 | $___M | $___M | $___M | ___% |
| LTM | $___M | $___M | $___M | ___% |

**Red Flag:** If adjustments >20% of EBITDA, scrutinize heavily.

### Cash Conversion Check

```
Adjusted EBITDA:           $___M
- Cash Interest:          ($___M)
- Cash Taxes:             ($___M)
- Maintenance Capex:      ($___M)
- Working Capital Change: ($___M)
= Unlevered Free Cash Flow $___M
  Cash Conversion: ___% of EBITDA
```

**Benchmark:** Healthy business converts 60-80% of EBITDA to FCF.

---

## Step 4: Working Capital Analysis (5 min)

### NWC Components

| Component | Year 1 | Year 2 | Year 3 | LTM | Days |
|-----------|--------|--------|--------|-----|------|
| A/R | $___M | $___M | $___M | $___M | ___ |
| Inventory | $___M | $___M | $___M | $___M | ___ |
| A/P | ($___M) | ($___M) | ($___M) | ($___M) | ___ |
| Accrued Exp | ($___M) | ($___M) | ($___M) | ($___M) | ___ |
| **Net WC** | **$___M** | **$___M** | **$___M** | **$___M** | |
| NWC % of Rev | ___% | ___% | ___% | ___% | |

### Cash Conversion Cycle

```
Days Sales Outstanding (DSO):      ___ days
+ Days Inventory Outstanding (DIO): ___ days
- Days Payables Outstanding (DPO): ___ days
= Cash Conversion Cycle:           ___ days
```

**What to Watch:**
- DSO increasing = collection issues or revenue quality
- DIO increasing = inventory build or slow sales
- DPO decreasing = supplier pressure

---

## Step 5: Capex Analysis (5 min)

### Maintenance vs Growth Capex

| Year | Total Capex | Maintenance | Growth | % of Revenue |
|------|-------------|-------------|--------|--------------|
| Year 1 | $___M | $___M | $___M | ___% |
| Year 2 | $___M | $___M | $___M | ___% |
| Year 3 | $___M | $___M | $___M | ___% |
| LTM | $___M | $___M | $___M | ___% |

**Rules of Thumb:**
- Maintenance capex ≈ D&A for mature business
- Growth capex should correlate with revenue growth
- If capex << D&A historically, deferred maintenance risk

### D&A vs Capex Check

| Year | D&A | Capex | Ratio | Signal |
|------|-----|-------|-------|--------|
| Year 1 | $___M | $___M | ___x | |
| Year 2 | $___M | $___M | ___x | |
| Year 3 | $___M | $___M | ___x | |
| LTM | $___M | $___M | ___x | |

**Interpretation:**
- Ratio >1.0x = Investing for growth
- Ratio ~1.0x = Maintaining assets
- Ratio <0.7x = Potential underinvestment

---

## Output Template

```markdown
## Historical Financial Analysis: [Company Name]

### Summary Metrics (LTM)
| Metric | Value | 3-Year Trend |
|--------|-------|--------------|
| Revenue | $___M | [↑/↓/→] ___% CAGR |
| Gross Margin | ___% | [↑/↓/→] |
| EBITDA | $___M | [↑/↓/→] ___% CAGR |
| EBITDA Margin | ___% | [↑/↓/→] |
| FCF Conversion | ___% | [↑/↓/→] |

### Key Observations
1. **Revenue:** [Observation on growth trajectory]
2. **Margins:** [Observation on profitability trend]
3. **Cash Flow:** [Observation on cash generation]

### Quality of Earnings Concerns
1. [Concern 1 - e.g., large add-backs]
2. [Concern 2 - e.g., margin compression]

### Assumptions for Projections
Based on historical analysis, use:
- Revenue growth: ___% (rationale: ___)
- EBITDA margin: ___% (rationale: ___)
- NWC % of revenue: ___% (rationale: ___)
- Capex % of revenue: ___% (rationale: ___)

### Diligence Questions
1. [Question from analysis]
2. [Question from analysis]
```

---

## Quick Checks: Common Middle Market Issues

| Issue | What to Look For | Impact |
|-------|------------------|--------|
| **Revenue Concentration** | Top customer trends | Exit risk |
| **Margin Sustainability** | One-time benefits in margins | Overstated EBITDA |
| **Working Capital Seasonality** | Monthly/quarterly swings | Debt sizing |
| **Capex Deferrals** | Capex << D&A | Hidden liability |
| **Related Party Transactions** | Rent, services to owners | Normalization needed |
| **Accounting Changes** | Revenue recognition, estimates | Comparability |

---

*Module Version: 1.0.0*
*Estimated Time: 20-30 minutes*
