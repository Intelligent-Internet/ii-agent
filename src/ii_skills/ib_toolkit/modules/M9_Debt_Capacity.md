# Module M9: Debt Capacity & Financing
## Middle Market Transaction Analysis

*Time: 15-20 minutes | Prerequisite: M6 (Working Capital), M8 (Deal Structure)*

---

## Objective

Assess the company's debt capacity, evaluate financing options, and stress test the capital structure under various scenarios.

---

## Debt Capacity Analysis

### Step 1: Cash Flow Available for Debt Service (5 min)

#### Free Cash Flow for Debt Service

| Item | LTM | Year 1 | Year 2 | Year 3 | Year 4 | Year 5 |
|------|-----|--------|--------|--------|--------|--------|
| EBITDA | $__M | $__M | $__M | $__M | $__M | $__M |
| - Cash Taxes | ($__M) | ($__M) | ($__M) | ($__M) | ($__M) | ($__M) |
| - Maintenance Capex | ($__M) | ($__M) | ($__M) | ($__M) | ($__M) | ($__M) |
| - Working Capital | ($__M) | ($__M) | ($__M) | ($__M) | ($__M) | ($__M) |
| = **Cash for Debt Service** | **$__M** | **$__M** | **$__M** | **$__M** | **$__M** | **$__M** |

#### Debt Service Capacity

```
Minimum Cash for Debt Service (Year 1):    $__M

At 2.0x coverage, max debt service:        $__M
At 1.5x coverage, max debt service:        $__M
At 1.25x coverage, max debt service:       $__M

Interest expense at SOFR + 400 (say 9%):
- Max debt at 2.0x coverage:               $__M
- Max debt at 1.5x coverage:               $__M
```

---

### Step 2: Leverage Capacity (5 min)

#### Multiple-Based Debt Capacity

| Approach | Multiple | EBITDA | Max Debt |
|----------|----------|--------|----------|
| **Conservative** | 3.5x | $__M | $__M |
| **Market** | 4.5x | $__M | $__M |
| **Aggressive** | 5.5x | $__M | $__M |

#### Coverage-Based Debt Capacity

| Coverage Metric | Minimum | Available CF | Implied Max Interest | Max Debt (@ 9%) |
|-----------------|---------|--------------|---------------------|-----------------|
| Interest Coverage | 2.5x | $__M EBITDA | $__M | $__M |
| Fixed Charge | 1.25x | $__M CF | $__M | $__M |
| Debt Service | 1.1x | $__M CF | $__M | $__M |

#### Constraining Factor

```
Multiple-based capacity:     $__M (__x)
Coverage-based capacity:     $__M
Asset-based capacity:        $__M (if applicable)
─────────────────────────────────────────
BINDING CONSTRAINT:          $__M
Recommended debt level:      $__M (__x) with cushion
```

---

### Step 3: Asset-Based Lending Consideration (5 min)

*Applicable for asset-heavy businesses or companies with inventory/receivables*

#### ABL Borrowing Base

| Asset | Book Value | Advance Rate | Borrowing Base |
|-------|------------|--------------|----------------|
| Eligible A/R (<90 days) | $__M | 85% | $__M |
| Eligible Inventory | $__M | 50-65% | $__M |
| PP&E (appraised) | $__M | 50-75% | $__M |
| **Total Borrowing Base** | | | **$__M** |
| Less: Reserves | | | ($__M) |
| **Net Availability** | | | **$__M** |

#### ABL vs. Cash Flow Comparison

| Factor | ABL | Cash Flow |
|--------|-----|-----------|
| Max availability | $__M | $__M |
| Interest rate | SOFR + 150-250 | SOFR + 400-600 |
| Covenants | Springing | Maintenance |
| Flexibility | Lower (reporting) | Higher |
| Best for | Asset-heavy, volatile | Stable CF, asset-light |

---

### Step 4: Debt Schedule Construction (5 min)

#### Amortization Schedule

| Year | Opening Debt | Mandatory Amort | Cash Sweep | Ending Debt | Interest |
|------|--------------|-----------------|------------|-------------|----------|
| 0 | $__M | — | — | $__M | — |
| 1 | $__M | ($__M) | ($__M) | $__M | $__M |
| 2 | $__M | ($__M) | ($__M) | $__M | $__M |
| 3 | $__M | ($__M) | ($__M) | $__M | $__M |
| 4 | $__M | ($__M) | ($__M) | $__M | $__M |
| 5 | $__M | ($__M) | ($__M) | $__M | $__M |

#### Cash Sweep Mechanics

```
Excess Cash Flow Calculation:
EBITDA                         $__M
- Cash Interest               ($__M)
- Cash Taxes                  ($__M)
- Capex                       ($__M)
- Working Capital Change      ($__M)
- Mandatory Amortization      ($__M)
= Excess Cash Flow             $__M
× Sweep Percentage             __%
= Cash Sweep                   $__M
```

---

### Step 5: Stress Testing (5 min)

#### Downside Scenarios

| Scenario | EBITDA Impact | Interest Coverage | Leverage | Covenant Status |
|----------|---------------|-------------------|----------|-----------------|
| Base Case | — | __x | __x | Pass |
| Revenue -10% | -__% | __x | __x | Pass/Breach |
| Revenue -20% | -__% | __x | __x | Pass/Breach |
| Margin -200bps | -__% | __x | __x | Pass/Breach |
| Rev -10%, Margin -100bps | -__% | __x | __x | Pass/Breach |

#### Covenant Headroom Analysis

| Covenant | Limit | Base Case | Cushion | Break-even EBITDA |
|----------|-------|-----------|---------|-------------------|
| Max Leverage | __x | __x | __x | $__M (−__%) |
| Min Coverage | __x | __x | __x | $__M (−__%) |

```
EBITDA required to avoid covenant breach:
- Leverage covenant: $__M minimum EBITDA
- Coverage covenant: $__M minimum EBITDA

Current EBITDA:               $__M
Cushion to breach:            __% downside
```

---

## Output Template

```markdown
## Debt Capacity Analysis: [Company Name]

### Debt Capacity Summary
| Approach | Capacity | Constraint |
|----------|----------|------------|
| Multiple-based (4.5x) | $__M | Market leverage |
| Coverage-based (2.5x) | $__M | Min interest coverage |
| Asset-based | $__M | Borrowing base |
| **Recommended** | **$__M** | **With __ cushion** |

### Proposed Structure
| Tranche | Amount | Rate | Maturity |
|---------|--------|------|----------|
| Revolver | $__M | SOFR + __ | __ yrs |
| Term Loan | $__M | SOFR + __ | __ yrs |
| Mezz (if needed) | $__M | __% | __ yrs |
| **Total** | **$__M** (**__x**) | | |

### Debt Paydown Trajectory
| Year | Debt | Leverage |
|------|------|----------|
| Entry | $__M | __x |
| Year 3 | $__M | __x |
| Exit | $__M | __x |

### Stress Test Results
- Break-even EBITDA for covenants: $__M (−__% from current)
- Cushion to covenant breach: ___%
- Assessment: [Comfortable / Tight / Risky]

### Key Observations
1. [Observation on capacity]
2. [Observation on structure]
```

---

## Middle Market Lender Landscape

| Lender Type | Typical Size | Leverage | Characteristics |
|-------------|--------------|----------|-----------------|
| **Banks** | $10-50M | 2-3.5x | Cheapest, most covenants |
| **BDCs** | $20-100M | 3-5x | Flexible, relationship-driven |
| **Direct Lenders** | $25-250M | 4-6x | One-stop, higher rate |
| **Mezzanine** | $10-50M | +1-2x stretch | Expensive, equity kicker |

---

*Module Version: 1.0.0*
*Estimated Time: 15-20 minutes*
