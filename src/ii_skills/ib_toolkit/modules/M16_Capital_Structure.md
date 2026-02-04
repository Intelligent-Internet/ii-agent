# Module M16: Capital Structure Analysis
## Debt Capacity & Optimal Financing

*Time: 15-20 minutes | Prerequisite: M4 (Historical Analysis)*

---

## Objective

Analyze debt capacity and recommend optimal capital structure based on company fundamentals, industry benchmarks, and coverage constraints.

---

## Capital Structure Framework

### Step 1: Assess Debt Capacity (5 min)

#### Company Fundamentals

| Metric | Value | Source |
|--------|-------|--------|
| LTM EBITDA | $__M | Financials |
| LTM Revenue | $__M | Financials |
| CapEx | $__M | Financials |
| Working Capital Needs | $__M | Estimated |
| Existing Debt | $__M | Balance sheet |
| Cash | $__M | Balance sheet |

#### Qualitative Factors

| Factor | Assessment | Impact on Capacity |
|--------|------------|-------------------|
| Revenue Volatility | Low / Moderate / High | +0.5x / 0 / -0.5x |
| Customer Concentration | Low / Moderate / High | +0.5x / 0 / -0.5x |
| Asset Base | Asset-Heavy / Light | +0.5x / -0.5x |
| Market Position | Leader / Challenger | +0.5x / 0 |
| Cash Flow Predictability | High / Moderate / Low | +0.5x / 0 / -0.5x |

**Adjusted Capacity Modifier**: __x

---

### Step 2: Industry Benchmarks (3 min)

#### Leverage by Sector (Debt / EBITDA)

| Industry | Conservative | Moderate | Aggressive |
|----------|--------------|----------|------------|
| Technology | 2.0x | 3.5x | 5.0x |
| Healthcare | 3.0x | 4.5x | 6.0x |
| Industrials | 2.5x | 4.0x | 5.5x |
| Consumer | 3.0x | 4.5x | 6.0x |
| Business Services | 3.5x | 5.0x | 6.5x |
| Financial Services | 2.0x | 3.0x | 4.0x |
| Real Estate | 4.0x | 6.0x | 8.0x |
| Retail | 2.5x | 4.0x | 5.5x |

**Target Industry**: _____________
**Benchmark Range**: __x - __x

---

### Step 3: Coverage Constraints (5 min)

#### Interest Coverage Test

```
Minimum Interest Coverage = 2.0x (typical covenant)

Max Interest = EBITDA / Min Coverage
Max Interest = $__M / 2.0
Max Interest = $__M

At blended rate of __%, Max Debt = $__M / __%
Max Debt (Coverage) = $__M
```

#### Fixed Charge Coverage Test

```
Minimum Fixed Charge Coverage = 1.2x

Cash Available = EBITDA - CapEx
Cash Available = $__M - $__M = $__M

Max Fixed Charges = Cash Available / 1.2
Max Fixed Charges = $__M / 1.2 = $__M

If mandatory amort = 5% of senior debt:
Interest + Amort <= $__M
```

#### Leverage Constraint

```
Max Leverage (industry) = __x EBITDA
Max Debt (Leverage) = $__M × __x
Max Debt (Leverage) = $__M
```

#### Binding Constraint

| Constraint | Max Debt |
|------------|----------|
| Interest Coverage | $__M |
| Fixed Charge Coverage | $__M |
| Industry Leverage | $__M |
| **Binding Constraint** | **$__M** |

---

### Step 4: Debt Tranches (5 min)

#### Debt Instrument Comparison

| Instrument | Typical Spread | Amort | Security | Max Leverage |
|------------|----------------|-------|----------|--------------|
| Term Loan A | L + 200-300bp | 10%/yr | Senior Secured | 3.0x |
| Term Loan B | L + 300-400bp | 1%/yr | Senior Secured | 4.5x |
| Second Lien | L + 600-700bp | None | Secured | 5.5x |
| Senior Notes | 7-9% fixed | None | Unsecured | 5.5x |
| Mezzanine | 12-15% (cash + PIK) | None | Unsecured | 6.5x |

#### Recommended Structure

| Tranche | Amount | Rate | Annual Interest |
|---------|--------|------|-----------------|
| Term Loan B | $__M | __% | $__M |
| Second Lien | $__M | __% | $__M |
| Mezzanine | $__M | __% | $__M |
| **Total Debt** | **$__M** | - | **$__M** |

```
Debt / EBITDA = $__M / $__M = __x
Interest Coverage = $__M / $__M = __x
```

---

### Step 5: Structure Optimization (3 min)

#### Option A: Conservative Structure
- **Total Debt**: __x EBITDA
- **Composition**: 100% senior secured
- **Interest Rate**: ~__% blended
- **Pros**: Lower cost, covenant flexibility
- **Cons**: More equity required

#### Option B: Moderate Structure
- **Total Debt**: __x EBITDA
- **Composition**: __% senior + __% junior
- **Interest Rate**: ~__% blended
- **Pros**: Balance of cost and leverage
- **Cons**: Standard covenant package

#### Option C: Aggressive Structure
- **Total Debt**: __x EBITDA
- **Composition**: __% senior + __% mezz
- **Interest Rate**: ~__% blended
- **Pros**: Minimize equity check
- **Cons**: Tight cushion, restrictive covenants

**Recommended**: Option __ because _____________

---

## Output Template

```markdown
## Capital Structure Analysis: [Company Name]

### Debt Capacity
| Metric | Value |
|--------|-------|
| EBITDA | $__M |
| **Max Total Debt** | **$__M** |
| Max Senior Secured | $__M |
| Max Junior/Sub | $__M |

### Binding Constraints
- Primary constraint: [Coverage / Leverage]
- Interest coverage: __x (min 2.0x)
- Fixed charge coverage: __x (min 1.2x)

### Recommended Structure
| Tranche | Amount | Multiple | Rate |
|---------|--------|----------|------|
| Senior Secured | $__M | __x | __% |
| Junior Debt | $__M | __x | __% |
| **Total** | **$__M** | **__x** | **__%** |

### Coverage Pro Forma
| Ratio | Pro Forma | Covenant |
|-------|-----------|----------|
| Total Leverage | __x | < __x |
| Senior Leverage | __x | < __x |
| Interest Coverage | __x | > 2.0x |
| Fixed Charge | __x | > 1.2x |

### Risk Assessment
[Low / Moderate / Elevated / High]
[Key risk factors and mitigants]
```

---

## Debt Market Benchmarks (2024-2025)

### Current Market Terms

| Metric | First Lien | Second Lien | Mezzanine |
|--------|------------|-------------|-----------|
| Spread | L+325-425 | L+625-725 | 11-14% |
| OID | 99.0-99.5 | 97.0-98.0 | 96.0-98.0 |
| Max Leverage | 4.5-5.5x | 5.5-6.5x | 6.0-7.0x |
| Typical Size | $50M-$500M | $25M-$200M | $10M-$100M |

### Covenant Levels (Middle Market)

| Covenant | First Lien | Second Lien |
|----------|------------|-------------|
| Total Leverage | 5.5-6.5x | 6.5-7.5x |
| Senior Leverage | 4.5-5.0x | N/A |
| Interest Coverage | 1.75-2.0x | N/A |
| CapEx Limit | 110-125% of D&A | N/A |

---

## Python Implementation

```python
from ii_skills.ib_toolkit.capital_structure import (
    CompanyFinancials, Industry, calculate_debt_capacity,
    generate_structure_report
)

# Define company
company = CompanyFinancials(
    ebitda=75.0,
    revenue=500.0,
    capex=25.0,
    existing_debt=150.0,
    cash=20.0,
    industry=Industry.BUSINESS_SERVICES,
    revenue_volatility="moderate",
    customer_concentration="low",
)

# Get analysis
result = calculate_debt_capacity(company)
print(f"Max Debt Capacity: ${result.max_total_debt:.0f}M")
print(f"Leverage: {result.debt_to_ebitda:.1f}x")

# Full report
print(generate_structure_report(company))
```

---

*Module Version: 1.0.0*
*Estimated Time: 15-20 minutes*
