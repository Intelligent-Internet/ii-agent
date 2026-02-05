# Scenario Library — Infrastructure IR

Standard stress test scenarios for infrastructure fund analysis.

## 1. Regulatory Reset Shock

**Scenario**: Adverse regulatory review outcome

| Parameter | Assumption |
|-----------|------------|
| Tariff Change | -5% on regulated assets |
| Timing | Next review period |
| Duration | Until next reset (3-5 years) |

**Impact Areas:**
- Revenue decline
- NAV reduction
- Distribution coverage pressure

**Output Requirements:**
- Sensitivity table showing NAV impact
- Regulatory timeline slide with reset dates
- Mitigation actions documented

---

## 2. Inflation Spike + CPI Pass-Through Lag

**Scenario**: Inflation accelerates but pass-through is delayed

| Parameter | Assumption |
|-----------|------------|
| CPI Increase | +400 bps above base |
| Pass-Through Delay | 12 months |
| Duration | 8 quarters |

**Impact Areas:**
- Margin compression during lag period
- Coverage ratio pressure
- Operating cost increases

**Output Requirements:**
- Margin bridge showing impact
- Coverage ratio trend under stress
- Inflation-linked revenue % callout

---

## 3. Merchant Price Decline

**Scenario**: Spot market prices decline for uncontracted capacity

| Parameter | Assumption |
|-----------|------------|
| Price Decline | -10% merchant prices |
| Duration | 4 quarters |
| Recovery | Gradual (8 quarters to baseline) |

**Impact Areas:**
- Cash flow volatility
- Distribution coverage
- NAV (for merchant-heavy assets)

**Output Requirements:**
- Cash flow stress comparison
- IRR sensitivity to merchant exposure
- Contracted vs. merchant revenue split

---

## 4. Availability Outage Event

**Scenario**: Operational disruption affects availability

| Parameter | Assumption |
|-----------|------------|
| Availability Drop | -2% (e.g., 98% → 96%) |
| Duration | 2 quarters |
| Penalty Exposure | Per contract terms |

**Impact Areas:**
- Penalty payments
- Revenue shortfall
- Counterparty relationship

**Output Requirements:**
- KPI dashboard with outage callout
- Penalty calculation
- Remediation timeline

---

## 5. FX & Rates Shock

**Scenario**: Macro environment deteriorates

| Parameter | Assumption |
|-----------|------------|
| Interest Rates | +100 bps |
| FX Impact | -5% on non-base currency assets |
| Duration | Sustained |

**Impact Areas:**
- NAV (discount rate effect)
- Coverage ratios (debt service)
- Translation impact on returns

**Output Requirements:**
- Macro sensitivity slide
- NAV bridge showing rate/FX drivers
- Hedging position summary

---

## 6. Counterparty Credit Deterioration

**Scenario**: Key offtaker downgrade or distress

| Parameter | Assumption |
|-----------|------------|
| Counterparty | Top 3 by revenue |
| Credit Event | Rating downgrade (2 notches) |
| Revenue at Risk | Per concentration |

**Impact Areas:**
- Receivables risk
- Contract enforcement
- Re-marketing risk

**Output Requirements:**
- Counterparty concentration table
- Credit quality summary
- Mitigation actions (guarantees, etc.)

---

## 7. Capex Overrun

**Scenario**: Construction or maintenance costs exceed budget

| Parameter | Assumption |
|-----------|------------|
| Cost Overrun | +20% on active projects |
| Funding Source | Debt or equity call |
| Impact on Returns | IRR dilution |

**Impact Areas:**
- Cash flow timing
- Leverage metrics
- IRR/MOIC

**Output Requirements:**
- Capex bridge (budget vs. actual)
- Returns sensitivity to overrun
- Funding plan

---

## 8. Combined Downside (Severe Stress)

**Scenario**: Multiple adverse events simultaneously

| Parameter | Assumption |
|-----------|------------|
| Regulatory | -3% tariff |
| Merchant | -5% prices |
| Rates | +50 bps |
| Availability | -1% |

**Impact Areas:**
- All metrics stressed
- Floor valuation test
- Capital adequacy

**Output Requirements:**
- Full sensitivity matrix
- Downside NAV vs. entry
- Covenant headroom under stress

---

## Using Scenarios

### In Excel
1. Create separate scenario tabs or toggles
2. Show base case vs. stress in parallel columns
3. Calculate delta and % impact

### In Slides
1. Use "Downside Case" slide template
2. Show key metrics under stress
3. Emphasize mitigants and protections
4. Include management response plan

### Narrative Framing
- "Even under severe stress, NAV remains above X"
- "Coverage ratio stays above 1.0x in all scenarios"
- "Downside protection from contracted revenue base"
