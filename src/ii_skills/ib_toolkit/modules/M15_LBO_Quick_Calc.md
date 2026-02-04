# Module M15: LBO Quick Calculator
## Rapid LBO Returns Analysis

*Time: 10-15 minutes | Prerequisite: Basic deal parameters*

---

## Objective

Quickly calculate LBO returns (IRR/MOIC) and understand value creation drivers without building a full model. Essential for:
- Initial deal screening
- IC discussion preparation
- Interview case studies
- Sensitivity testing

---

## Quick LBO Framework

### Step 1: Entry Economics (3 min)

#### Transaction Setup

| Input | Value | Notes |
|-------|-------|-------|
| LTM EBITDA | $__M | Trailing 12 months |
| Entry Multiple | __x | EV / EBITDA |
| **Entry EV** | **$__M** | EBITDA × Multiple |

#### Sources & Uses (Simplified)

| Sources | Amount | Multiple |
|---------|--------|----------|
| Senior Debt (TLB) | $__M | __x |
| Subordinated Debt | $__M | __x |
| **Total Debt** | **$__M** | **__x** |
| Sponsor Equity | $__M | - |
| **Total Sources** | **$__M** | - |

```
Entry Equity = Entry EV - Total Debt
Entry Equity = $__M - $__M = $__M
```

---

### Step 2: Exit Economics (3 min)

#### EBITDA Projection

```
Exit EBITDA = Entry EBITDA × (1 + Growth Rate)^Hold Period
Exit EBITDA = $__M × (1 + __%)^__ years
Exit EBITDA = $__M
```

| Year | EBITDA | Growth |
|------|--------|--------|
| Entry | $__M | - |
| Year 1 | $__M | __% |
| Year 2 | $__M | __% |
| Year 3 | $__M | __% |
| Year 4 | $__M | __% |
| Year 5 | $__M | __% |

#### Exit Valuation

| Metric | Value | Notes |
|--------|-------|-------|
| Exit EBITDA | $__M | Year __ projection |
| Exit Multiple | __x | [Same / Expansion / Contraction] |
| **Exit EV** | **$__M** | EBITDA × Multiple |
| Exit Debt | $__M | Remaining after paydown |
| **Exit Equity** | **$__M** | EV - Debt |

---

### Step 3: Returns Calculation (2 min)

#### MOIC (Multiple on Invested Capital)

```
MOIC = Exit Equity / Entry Equity
MOIC = $__M / $__M
MOIC = __.__ x
```

#### IRR (Internal Rate of Return)

```
IRR = (Exit Equity / Entry Equity)^(1/Hold Period) - 1
IRR = ($__M / $__M)^(1/__) - 1
IRR = __.__%
```

#### Quick IRR Reference Table

| MOIC | 3 Years | 4 Years | 5 Years | 6 Years | 7 Years |
|------|---------|---------|---------|---------|---------|
| 1.5x | 14% | 11% | 8% | 7% | 6% |
| 2.0x | 26% | 19% | 15% | 12% | 10% |
| 2.5x | 36% | 26% | 20% | 16% | 14% |
| 3.0x | 44% | 32% | 25% | 20% | 17% |
| 3.5x | 52% | 37% | 28% | 23% | 20% |
| 4.0x | 59% | 41% | 32% | 26% | 22% |

---

### Step 4: Value Creation Attribution (2 min)

Three drivers of LBO returns:

#### 1. EBITDA Growth
```
EBITDA Growth Value = (Exit EBITDA - Entry EBITDA) × Entry Multiple
= ($__M - $__M) × __x
= $__M
```

#### 2. Multiple Expansion
```
Multiple Expansion Value = Exit EBITDA × (Exit Multiple - Entry Multiple)
= $__M × (__x - __x)
= $__M
```

#### 3. Deleveraging
```
Deleveraging Value = Entry Debt - Exit Debt
= $__M - $__M
= $__M
```

#### Attribution Summary

| Driver | $ Value | % of Gain |
|--------|---------|-----------|
| EBITDA Growth | $__M | __% |
| Multiple Expansion | $__M | __% |
| Deleveraging | $__M | __% |
| **Total Equity Gain** | **$__M** | **100%** |

---

### Step 5: Sensitivity Analysis (3 min)

#### Entry vs Exit Multiple

|Entry \ Exit| 6.0x | 7.0x | 8.0x | 9.0x | 10.0x |
|------------|------|------|------|------|-------|
| **6.0x** | __x | __x | __x | __x | __x |
| **7.0x** | __x | __x | __x | __x | __x |
| **8.0x** | __x | __x | [__x] | __x | __x |
| **9.0x** | __x | __x | __x | __x | __x |
| **10.0x** | __x | __x | __x | __x | __x |

*Base case in brackets*

#### Breakeven Analysis

```
For 1.0x MOIC (return of capital):

Entry Equity: $__M
Required Exit Equity: $__M
Plus Exit Debt: $__M
Required Exit EV: $__M
Exit EBITDA: $__M

Breakeven Multiple = Required EV / Exit EBITDA
Breakeven Multiple = $__M / $__M
Breakeven Multiple = __.__ x

Cushion = Entry Multiple - Breakeven Multiple
Cushion = __x - __x = __.__ x
```

---

## Output Template

```markdown
## LBO Quick Calc: [Company Name]

### Transaction Summary
| Metric | Entry | Exit |
|--------|-------|------|
| EBITDA | $__M | $__M |
| Multiple | __x | __x |
| EV | $__M | $__M |
| Debt | $__M | $__M |
| Equity | $__M | $__M |

### Returns
| Metric | Value |
|--------|-------|
| **MOIC** | **__x** |
| **IRR** | **__%** |
| Hold Period | __ years |

### Value Creation
- EBITDA Growth: __% of gain
- Multiple Expansion: __% of gain
- Deleveraging: __% of gain

### Downside Protection
- Breakeven exit multiple: __x
- Cushion vs entry: __x
```

---

## Quick Rules of Thumb

### Leverage Guidelines
- **Conservative**: 3-4x total debt
- **Moderate**: 4-5x total debt
- **Aggressive**: 5-6x+ total debt

### Target Returns by Fund Type
| Strategy | Target MOIC | Target IRR |
|----------|-------------|------------|
| Large Cap Buyout | 2.0-2.5x | 18-22% |
| Mid-Market Buyout | 2.5-3.0x | 20-25% |
| Lower Mid-Market | 3.0-4.0x | 25-30% |
| Growth Equity | 3.0-5.0x | 25-35% |

### Multiple Expansion Reality Check
- 1x expansion rare in current market
- Most deals underwrite flat or slight compression
- Expansion typically requires strategic value add

---

## Python Implementation

```python
from ii_skills.ib_toolkit.lbo_calculator import quick_lbo, generate_lbo_summary, LBOAssumptions

# Quick calculation
result = quick_lbo(
    ebitda=50,           # $50M EBITDA
    entry_multiple=8.0,  # 8x entry
    exit_multiple=8.5,   # 8.5x exit
    leverage=4.5,        # 4.5x debt
    hold_years=5,        # 5 year hold
    ebitda_growth=0.08   # 8% annual growth
)

print(f"MOIC: {result['moic']}x")
print(f"IRR: {result['irr']}%")

# Full report
assumptions = LBOAssumptions(
    entry_ebitda=50,
    entry_multiple=8.0,
    exit_multiple=8.5,
    hold_period=5
)
print(generate_lbo_summary(assumptions))
```

---

*Module Version: 1.0.0*
*Estimated Time: 10-15 minutes*
