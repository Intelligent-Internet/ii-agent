# Module M6: Working Capital & Cash Conversion
## Middle Market Transaction Analysis

*Time: 15-20 minutes | Prerequisite: Historical financials*

---

## Objective

Analyze working capital dynamics, seasonality, and cash conversion to understand true cash generation and debt capacity. Critical for LBO debt sizing and understanding business quality.

---

## Working Capital Analysis

### Step 1: NWC Components (5 min)

#### Working Capital Build

| Component | Year 1 | Year 2 | Year 3 | LTM | As % of Rev |
|-----------|--------|--------|--------|-----|-------------|
| **Current Assets** | | | | | |
| Accounts Receivable | $__M | $__M | $__M | $__M | __% |
| Inventory | $__M | $__M | $__M | $__M | __% |
| Prepaid Expenses | $__M | $__M | $__M | $__M | __% |
| Other Current Assets | $__M | $__M | $__M | $__M | __% |
| **Current Liabilities** | | | | | |
| Accounts Payable | ($__M) | ($__M) | ($__M) | ($__M) | __% |
| Accrued Expenses | ($__M) | ($__M) | ($__M) | ($__M) | __% |
| Deferred Revenue | ($__M) | ($__M) | ($__M) | ($__M) | __% |
| Other Current Liabilities | ($__M) | ($__M) | ($__M) | ($__M) | __% |
| **Net Working Capital** | **$__M** | **$__M** | **$__M** | **$__M** | **__%** |

#### Exclude from Operating NWC
- Cash and equivalents
- Short-term debt
- Current portion of long-term debt
- Accrued interest

---

### Step 2: Cash Conversion Cycle (5 min)

#### Efficiency Metrics

| Metric | Formula | Year 1 | Year 2 | Year 3 | LTM | Trend |
|--------|---------|--------|--------|--------|-----|-------|
| **DSO** | (A/R ÷ Revenue) × 365 | __ | __ | __ | __ | ↑/↓/→ |
| **DIO** | (Inventory ÷ COGS) × 365 | __ | __ | __ | __ | ↑/↓/→ |
| **DPO** | (A/P ÷ COGS) × 365 | __ | __ | __ | __ | ↑/↓/→ |
| **CCC** | DSO + DIO - DPO | __ | __ | __ | __ | ↑/↓/→ |

#### Cash Conversion Cycle Interpretation

| CCC | Interpretation | Business Type |
|-----|----------------|---------------|
| Negative | Collects before paying suppliers | SaaS, prepaid models |
| 0-30 days | Efficient cash management | Services, low inventory |
| 30-60 days | Normal for most industries | Distribution, light mfg |
| 60-90 days | Working capital intensive | Manufacturing, wholesale |
| >90 days | Cash trap potential | Heavy manufacturing, construction |

**Company CCC: __ days** → [Interpretation]

---

### Step 3: Seasonality Analysis (5 min)

#### Monthly/Quarterly Pattern

If monthly data available:

| Month | Revenue Index | NWC Index | Cash Build/Drain |
|-------|---------------|-----------|------------------|
| Jan | __ | __ | $__M |
| Feb | __ | __ | $__M |
| Mar | __ | __ | $__M |
| Apr | __ | __ | $__M |
| May | __ | __ | $__M |
| Jun | __ | __ | $__M |
| Jul | __ | __ | $__M |
| Aug | __ | __ | $__M |
| Sep | __ | __ | $__M |
| Oct | __ | __ | $__M |
| Nov | __ | __ | $__M |
| Dec | __ | __ | $__M |

#### Peak Working Capital Need

```
Average NWC:                    $__M
Peak NWC (Month: _____):        $__M
Trough NWC (Month: _____):      $__M
Seasonal Swing:                 $__M
Revolver sizing implication:    $__M minimum availability
```

---

### Step 4: Cash Conversion Analysis (5 min)

#### EBITDA to Cash Bridge

| Item | Amount | % of EBITDA |
|------|--------|-------------|
| EBITDA | $__M | 100% |
| - Cash Interest | ($__M) | (__%) |
| - Cash Taxes | ($__M) | (__%) |
| - Maintenance Capex | ($__M) | (__%) |
| - Working Capital Change | ($__M) | (__%) |
| = **Free Cash Flow** | **$__M** | **__%** |

#### Cash Conversion Quality

| Metric | Value | Benchmark | Assessment |
|--------|-------|-----------|------------|
| FCF / EBITDA | __% | 60-80% | ✓/⚠/✗ |
| FCF / Net Income | __% | 80-120% | ✓/⚠/✗ |
| Capex / D&A | __x | 0.8-1.2x | ✓/⚠/✗ |
| NWC / Revenue trend | ↑/↓/→ | Stable/declining | ✓/⚠/✗ |

---

### Step 5: Working Capital Adjustments (5 min)

#### Transaction Adjustments

| Adjustment | Amount | Rationale |
|------------|--------|-----------|
| **Minimum cash** | $__M | Operating needs (__ days of opex) |
| **Excess cash** | $__M | Above minimum, reduces purchase price |
| **NWC target** | $__M | Normalized level for purchase agreement |
| **NWC true-up** | +/- $__M | Estimated adjustment at close |

#### Working Capital Peg

```
Trailing 12-month average NWC:  $__M
Adjustments:
  + Seasonality normalization:  $__M
  - Non-operating items:       ($__M)
  + Growth adjustment:          $__M
= NWC Target (Peg):            $__M
```

**Peg as % of LTM Revenue: __%**

---

## Output Template

```markdown
## Working Capital Analysis: [Company Name]

### Summary Metrics
| Metric | LTM Value | Trend | Assessment |
|--------|-----------|-------|------------|
| NWC | $__M | ↑/↓/→ | |
| NWC % of Revenue | __% | ↑/↓/→ | |
| Cash Conversion Cycle | __ days | ↑/↓/→ | |
| FCF Conversion | __% | ↑/↓/→ | |

### Cash Conversion Cycle
- DSO: __ days [Good/Concerning]
- DIO: __ days [Good/Concerning]
- DPO: __ days [Good/Concerning]
- CCC: __ days [Efficient/Normal/Cash intensive]

### Seasonality
- Peak month: [Month] - NWC = $__M
- Trough month: [Month] - NWC = $__M
- Seasonal swing: $__M
- Revolver need: $__M

### Transaction Implications
- NWC target (peg): $__M
- Minimum cash: $__M
- Expected true-up: $__M [Source/Use]

### Key Observations
1. [Observation about cash conversion]
2. [Observation about seasonality]
3. [Observation about trends]

### Diligence Questions
1. [Question about DSO/collections]
2. [Question about inventory/DIO]
3. [Question about payment terms/DPO]
```

---

## Red Flags

| Red Flag | What It Signals | Action |
|----------|-----------------|--------|
| DSO increasing | Collection issues, revenue quality | Aging analysis, customer concentration |
| DIO increasing | Slow sales, obsolete inventory | Inventory aging, write-off history |
| DPO decreasing | Supplier pressure, terms tightening | Supplier concentration, payment terms |
| NWC % increasing | Cash trap as business grows | Model NWC investment in projections |
| Large seasonal swings | Need higher revolver | Size revolver for peak need |

---

*Module Version: 1.0.0*
*Estimated Time: 15-20 minutes*
