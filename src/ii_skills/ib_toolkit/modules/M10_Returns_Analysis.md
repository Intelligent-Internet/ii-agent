# Module M10: Returns Analysis & Sensitivity
## Middle Market Transaction Analysis

*Time: 20-30 minutes | Prerequisite: M5 (Projections), M8 (Deal Structure)*

---

## Objective

Calculate investment returns (MOIC/IRR), build sensitivity tables, and stress test returns under various scenarios to assess risk-adjusted attractiveness.

---

## Returns Framework

### Step 1: Base Case Returns (10 min)

#### Entry Assumptions

| Parameter | Value | Source |
|-----------|-------|--------|
| Entry Date | [Date] | Assumed |
| Entry Enterprise Value | $__M | Purchase price |
| Entry Multiple | __x LTM EBITDA | Calculated |
| Entry Equity | $__M | S&U |
| Entry Debt | $__M | S&U |

#### Exit Assumptions

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| Exit Date | [Date] | __ year hold |
| Exit EBITDA | $__M | From projections |
| Exit Multiple | __x | [Comps / Entry / Premium] |
| Exit Enterprise Value | $__M | EBITDA × Multiple |
| Exit Debt | $__M | From debt schedule |
| Exit Equity Value | $__M | EV - Debt |

#### Returns Calculation

```
Entry Equity Investment:       $__M
Exit Equity Proceeds:          $__M

MOIC = Exit Equity / Entry Equity
MOIC = $__M / $__M
MOIC = __.__ x

IRR = (Exit / Entry)^(1/n) - 1
IRR = ($__M / $__M)^(1/__) - 1
IRR = __.__%
```

#### Returns by Year

| Exit Year | Exit EBITDA | Exit EV | Exit Debt | Exit Equity | MOIC | IRR |
|-----------|-------------|---------|-----------|-------------|------|-----|
| Year 3 | $__M | $__M | $__M | $__M | __x | __% |
| Year 4 | $__M | $__M | $__M | $__M | __x | __% |
| **Year 5** | **$__M** | **$__M** | **$__M** | **$__M** | **__x** | **__%** |
| Year 6 | $__M | $__M | $__M | $__M | __x | __% |
| Year 7 | $__M | $__M | $__M | $__M | __x | __% |

---

### Step 2: Sensitivity Analysis (10 min)

#### MOIC Sensitivity: Entry Multiple vs. Exit Multiple

|Entry \ Exit| 5.0x | 6.0x | 7.0x | 8.0x | 9.0x | 10.0x |
|------------|------|------|------|------|------|-------|
| **5.0x** | __x | __x | __x | __x | __x | __x |
| **6.0x** | __x | __x | __x | __x | __x | __x |
| **7.0x** | __x | __x | **[__x]** | __x | __x | __x |
| **8.0x** | __x | __x | __x | __x | __x | __x |
| **9.0x** | __x | __x | __x | __x | __x | __x |

*Base case highlighted in brackets*

#### IRR Sensitivity: Revenue Growth vs. Exit Multiple

|Growth \ Exit| 6.0x | 7.0x | 8.0x | 9.0x |
|-------------|------|------|------|------|
| **5%** | __% | __% | __% | __% |
| **10%** | __% | **[__%]** | __% | __% |
| **15%** | __% | __% | __% | __% |
| **20%** | __% | __% | __% | __% |

#### IRR Sensitivity: EBITDA Margin vs. Exit Multiple

|Margin \ Exit| 6.0x | 7.0x | 8.0x | 9.0x |
|-------------|------|------|------|------|
| **15%** | __% | __% | __% | __% |
| **18%** | __% | **[__%]** | __% | __% |
| **21%** | __% | __% | __% | __% |
| **24%** | __% | __% | __% | __% |

---

### Step 3: Scenario Analysis (10 min)

#### Scenario Definition

| Scenario | Probability | Revenue CAGR | Exit Margin | Exit Multiple | Key Assumptions |
|----------|-------------|--------------|-------------|---------------|-----------------|
| **Upside** | 15% | __% | __% | __x | [What goes right] |
| **Bull** | 20% | __% | __% | __x | [Above plan] |
| **Base** | 40% | __% | __% | __x | [Plan achieved] |
| **Bear** | 20% | __% | __% | __x | [Below plan] |
| **Downside** | 5% | __% | __% | __x | [What goes wrong] |

#### Scenario Returns

| Scenario | Exit EBITDA | Exit EV | Exit Equity | MOIC | IRR |
|----------|-------------|---------|-------------|------|-----|
| Upside | $__M | $__M | $__M | __x | __% |
| Bull | $__M | $__M | $__M | __x | __% |
| **Base** | **$__M** | **$__M** | **$__M** | **__x** | **__%** |
| Bear | $__M | $__M | $__M | __x | __% |
| Downside | $__M | $__M | $__M | __x | __% |

#### Probability-Weighted Returns

```
Expected MOIC = Σ (Probability × MOIC)
             = (15% × __) + (20% × __) + (40% × __) + (20% × __) + (5% × __)
             = __.__x

Expected IRR = Σ (Probability × IRR)
            = (15% × __%) + (20% × __%) + (40% × __%) + (20% × __%) + (5% × __%)
            = __.__%
```

---

### Step 4: Breakeven Analysis (5 min)

#### Multiple Breakeven

```
Entry Equity:                  $__M
Entry Debt:                    $__M
Entry Enterprise Value:        $__M
Entry EBITDA:                  $__M

For 1.0x MOIC (return of capital):
- Required Exit Equity:        $__M
- Plus Exit Debt:              $__M (assume)
- Required Exit EV:            $__M
- Exit EBITDA (base):          $__M
- Breakeven Exit Multiple:     __.__ x

Cushion below entry multiple:  __.__x
```

#### Operational Breakeven

| Metric | Base Case | Breakeven (1.0x) | Cushion |
|--------|-----------|------------------|---------|
| Exit Revenue | $__M | $__M | −__% |
| Exit EBITDA | $__M | $__M | −__% |
| Exit Margin | __% | __% | −__ bps |
| Exit Multiple | __x | __x | −__x |

---

### Step 5: Returns Attribution (5 min)

#### Value Creation Bridge

```
Entry Equity Value:            $__M

+ EBITDA Growth:              +$__M  (__% of value creation)
  [Entry to exit EBITDA × Entry multiple]

+ Multiple Expansion:         +$__M  (__% of value creation)
  [Exit EBITDA × (Exit mult - Entry mult)]

+ Debt Paydown:               +$__M  (__% of value creation)
  [Entry debt - Exit debt]

- Cash Used for Growth:       -$__M
  [If negative FCF years]

= Exit Equity Value:           $__M
─────────────────────────────────────
MOIC:                          __.__x
IRR:                           __.__%
```

#### Value Creation Mix

| Driver | $ Contribution | % of Gain |
|--------|----------------|-----------|
| EBITDA Growth | $__M | __% |
| Multiple Expansion | $__M | __% |
| Debt Paydown | $__M | __% |
| FCF (if distributed) | $__M | __% |
| **Total Gain** | **$__M** | **100%** |

---

## Output Template

```markdown
## Returns Analysis: [Company Name]

### Base Case Returns
| Metric | Value |
|--------|-------|
| Hold Period | __ years |
| Entry Multiple | __x |
| Exit Multiple | __x |
| **MOIC** | **__x** |
| **IRR** | **__%** |

### Scenario Summary
| Scenario | Prob | MOIC | IRR |
|----------|------|------|-----|
| Bull | __% | __x | __% |
| Base | __% | __x | __% |
| Bear | __% | __x | __% |
| **Weighted** | 100% | **__x** | **__%** |

### Key Sensitivities
- Most sensitive to: [Factor]
- Entry multiple ±1x: MOIC [range]
- Exit multiple ±1x: MOIC [range]
- EBITDA ±10%: MOIC [range]

### Breakeven Analysis
- Breakeven exit multiple: __x (vs. __x entry)
- Cushion: __x below entry

### Value Creation Attribution
- EBITDA Growth: __% of gain
- Multiple Expansion: __% of gain
- Deleveraging: __% of gain

### Assessment
[Strong / Adequate / Marginal] returns with [high / moderate / low] downside protection.
```

---

## Target Returns by Strategy

| Strategy | Target MOIC | Target IRR | Typical Hold |
|----------|-------------|------------|--------------|
| Growth Equity | 2.5-4.0x | 25-35% | 4-6 years |
| Buyout (MM) | 2.0-3.0x | 20-25% | 4-6 years |
| Buyout (LMM) | 2.5-3.5x | 25-30% | 4-5 years |
| Platform + Add-ons | 3.0-4.0x | 25-35% | 5-7 years |

---

*Module Version: 1.0.0*
*Estimated Time: 20-30 minutes*
