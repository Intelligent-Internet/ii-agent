# Module M7: Valuation (Comps / DCF / LBO)
## Middle Market Transaction Analysis

*Time: 30-45 minutes | Prerequisite: M4-M6 (Financials)*

---

## Objective

Develop a supportable valuation range using multiple methodologies. In middle market, comps and LBO-implied value are most relevant; DCF is supportive.

---

## Valuation Framework

### Step 1: Comparable Company Analysis (15 min)

#### Select Comparables

| Criteria | Weight | Notes |
|----------|--------|-------|
| Business model similarity | HIGH | Same revenue model (recurring vs. transactional) |
| End market | HIGH | Same customers, use cases |
| Size (revenue) | MEDIUM | Within 0.5x-2x of target |
| Growth profile | MEDIUM | Similar growth rates |
| Margin profile | MEDIUM | Similar profitability |
| Geography | LOW | Unless regulatory differences |

#### Comparable Company Data

| Company | Ticker | EV ($M) | Revenue | Growth | EBITDA | Margin | EV/Rev | EV/EBITDA |
|---------|--------|---------|---------|--------|--------|--------|--------|-----------|
| [Comp 1] | | $__M | $__M | __% | $__M | __% | __x | __x |
| [Comp 2] | | $__M | $__M | __% | $__M | __% | __x | __x |
| [Comp 3] | | $__M | $__M | __% | $__M | __% | __x | __x |
| [Comp 4] | | $__M | $__M | __% | $__M | __% | __x | __x |
| [Comp 5] | | $__M | $__M | __% | $__M | __% | __x | __x |
| **Mean** | | | | __% | | __% | __x | __x |
| **Median** | | | | __% | | __% | __x | __x |

#### Comp Adjustments

| Factor | Target vs. Comps | Multiple Adjustment |
|--------|------------------|---------------------|
| Size | Smaller / Similar / Larger | -__x / — / +__x |
| Growth | Slower / Similar / Faster | -__x / — / +__x |
| Margins | Lower / Similar / Higher | -__x / — / +__x |
| Market position | Weaker / Similar / Stronger | -__x / — / +__x |
| **Net Adjustment** | | **+/- __x** |

#### Implied Valuation from Comps

| Metric | Target Value | Multiple Range | Implied EV |
|--------|--------------|----------------|------------|
| LTM Revenue | $__M | __x - __x | $__M - $__M |
| LTM EBITDA | $__M | __x - __x | $__M - $__M |
| NTM Revenue | $__M | __x - __x | $__M - $__M |
| NTM EBITDA | $__M | __x - __x | $__M - $__M |

---

### Step 2: Precedent Transactions (10 min)

#### Transaction Selection

| Date | Target | Acquirer | EV ($M) | Revenue | EBITDA | EV/Rev | EV/EBITDA |
|------|--------|----------|---------|---------|--------|--------|-----------|
| [Date] | [Target] | [Buyer] | $__M | $__M | $__M | __x | __x |
| [Date] | [Target] | [Buyer] | $__M | $__M | $__M | __x | __x |
| [Date] | [Target] | [Buyer] | $__M | $__M | $__M | __x | __x |
| [Date] | [Target] | [Buyer] | $__M | $__M | $__M | __x | __x |
| **Mean** | | | | | | __x | __x |
| **Median** | | | | | | __x | __x |

#### Control Premium Consideration

```
Trading comp median:           __x EBITDA
Transaction comp median:       __x EBITDA
Implied control premium:       __%
Typical range:                 20-40%
```

---

### Step 3: DCF Valuation (10 min)

#### DCF Assumptions

| Assumption | Value | Rationale |
|------------|-------|-----------|
| Projection period | __ years | [Standard 5 years] |
| WACC | __% | [Build-up or comparable] |
| Terminal growth | __% | [GDP or industry growth] |
| Exit multiple (alternative) | __x | [Based on comps] |

#### WACC Build-Up (Middle Market)

```
Risk-free rate (10Y Treasury):     __%
+ Equity risk premium:             __%
+ Size premium:                    __%  (small cap adjustment)
+ Company-specific risk:           __%  (judgment)
= Cost of Equity:                  __%

Cost of Debt (after-tax):          __%
Target D/E ratio:                  __%

WACC = (E% × Ke) + (D% × Kd × (1-T))
WACC =                             __%
```

#### DCF Model Summary

| Year | UFCF | Discount Factor | PV |
|------|------|-----------------|-----|
| 1 | $__M | __.__ | $__M |
| 2 | $__M | __.__ | $__M |
| 3 | $__M | __.__ | $__M |
| 4 | $__M | __.__ | $__M |
| 5 | $__M | __.__ | $__M |
| **PV of FCF** | | | **$__M** |

```
Terminal Value Calculation:
- Exit Year EBITDA:                $__M
- Exit Multiple:                   __x
- Terminal Value:                  $__M
- PV of Terminal Value:            $__M

OR (Gordon Growth):
- Terminal FCF:                    $__M
- Terminal Growth:                 __%
- Terminal Value:                  $__M  [FCF × (1+g) / (WACC-g)]
- PV of Terminal Value:            $__M

Enterprise Value:
- PV of FCF:                       $__M
- PV of Terminal:                  $__M
- Enterprise Value:                $__M
- TV as % of EV:                   __% (should be <70%)
```

---

### Step 4: LBO Floor Valuation (10 min)

#### LBO Returns Analysis

What price can a financial buyer pay and achieve target returns?

| Assumption | Value |
|------------|-------|
| Target IRR | __% |
| Hold period | __ years |
| Entry leverage | __x EBITDA |
| Exit multiple | __x EBITDA |

#### LBO Implied Valuation

```
Exit Year EBITDA:              $__M
× Exit Multiple:               __x
= Exit Enterprise Value:       $__M
- Exit Debt:                   $__M
= Exit Equity Value:           $__M

Required Entry Equity for __% IRR:
= Exit Equity ÷ (1 + IRR)^n
= $__M ÷ (1 + __%)^__
= $__M

Entry Sources & Uses:
Entry Equity:                  $__M
+ Entry Debt (__x EBITDA):     $__M
= Entry Enterprise Value:      $__M

Implied Entry Multiple:        __x LTM EBITDA
```

---

### Step 5: Valuation Summary (5 min)

#### Football Field

```
                          Low        Mid        High
                           |          |          |
Trading Comps         ├────|──────────|──────────|────┤  $__M - $__M
                           |          |          |
Transaction Comps     ├────|──────────|──────────|────┤  $__M - $__M
                           |          |          |
DCF                   ├────|──────────|──────────|────┤  $__M - $__M
                           |          |          |
LBO (@ __% IRR)       ├────|──────────|──────────|────┤  $__M - $__M
                           |          |          |
                      $____M     $____M     $____M
```

#### Valuation Summary Table

| Methodology | Low | Mid | High | Weight |
|-------------|-----|-----|------|--------|
| Trading Comps | $__M | $__M | $__M | __% |
| Transaction Comps | $__M | $__M | $__M | __% |
| DCF | $__M | $__M | $__M | __% |
| LBO Floor | $__M | $__M | $__M | __% |
| **Weighted Value** | **$__M** | **$__M** | **$__M** | 100% |

#### Implied Multiples at Valuation Range

| Valuation | EV/Revenue | EV/EBITDA |
|-----------|------------|-----------|
| Low: $__M | __x | __x |
| Mid: $__M | __x | __x |
| High: $__M | __x | __x |

---

## Output Template

```markdown
## Valuation Summary: [Company Name]

### Valuation Range
| Method | Range | Implied EV/EBITDA |
|--------|-------|-------------------|
| Trading Comps | $__M - $__M | __x - __x |
| Transaction Comps | $__M - $__M | __x - __x |
| DCF | $__M - $__M | __x - __x |
| LBO Floor | $__M - $__M | __x - __x |
| **Conclusion** | **$__M - $__M** | **__x - __x** |

### Key Assumptions
- LTM EBITDA: $__M
- NTM EBITDA: $__M
- WACC: __%
- Terminal growth/multiple: __% / __x
- LBO target IRR: __%

### Valuation Drivers
1. [What drives value higher]
2. [What limits value]

### Entry Multiple Context
- Asking price: $__M (__x EBITDA)
- vs. Comps median: [Premium/Discount] of __%
- vs. Transactions: [Premium/Discount] of __%
```

---

## Middle Market Valuation Considerations

| Factor | Impact | Notes |
|--------|--------|-------|
| **Size discount** | -1-2x EBITDA | Smaller = less liquid, higher risk |
| **Customer concentration** | -0.5-1x | >20% in single customer |
| **Key person risk** | -0.5-1x | Founder-dependent |
| **Growth premium** | +1-2x | Above-market growth |
| **Recurring revenue** | +1-3x | Predictable cash flows |
| **Strategic premium** | +2-4x | If strategic buyer |

---

*Module Version: 1.0.0*
*Estimated Time: 30-45 minutes*
