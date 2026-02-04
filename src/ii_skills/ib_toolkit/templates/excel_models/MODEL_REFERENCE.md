# Excel Financial Model Reference Guide

## Time-Based Model Selection

### 24-Hour Sprint Case
**Focus:** Essentials only - get to a decision fast

| Module | Include? | Depth |
|--------|----------|-------|
| Sources & Uses | ✅ Required | Simple table |
| Operating Model | ✅ Required | Revenue → EBITDA (5 lines) |
| Debt Schedule | ❌ Skip | Use single debt assumption |
| Returns Analysis | ✅ Required | MOIC + IRR only |
| Sensitivity | ⚡ If time | Entry/exit matrix only |

**Tips:**
- Use management projections directly
- Single debt tranche, flat paydown
- Don't build detailed schedules
- One sensitivity table maximum

**Generate:**
```python
generate_quick_lbo("Company", "output.xlsx")
```

---

### 48-Hour Standard Case
**Focus:** Solid analysis with key supporting detail

| Module | Include? | Depth |
|--------|----------|-------|
| Sources & Uses | ✅ Required | With fees breakdown |
| Operating Model | ✅ Required | Full P&L through EBITDA |
| Revenue Build | ⚡ If time | Segment breakdown |
| Debt Schedule | ✅ Required | Multi-tranche |
| Working Capital | ⚡ If time | % of revenue |
| Returns Analysis | ✅ Required | By exit year + bridge |
| Sensitivity | ✅ Required | 2-3 matrices |

**Tips:**
- Challenge 1-2 management assumptions
- Build debt schedule with amortization
- Simple value creation bridge
- Base/upside/downside scenarios

**Generate:**
```python
gen = ExcelModelGenerator("Company", ModelDepth.STANDARD)
gen.add_sources_uses()
gen.add_operating_model()
gen.add_debt_schedule()
gen.add_returns_analysis()
gen.add_sensitivity_tables()
gen.save("output.xlsx")
```

---

### 5-Day Detailed Case
**Focus:** Comprehensive analysis with full supporting detail

| Module | Include? | Depth |
|--------|----------|-------|
| Sources & Uses | ✅ Required | Full breakdown |
| Revenue Build | ✅ Required | Segment drivers |
| Expense Build | ✅ Required | COGS + SG&A breakdown |
| Operating Model | ✅ Required | Segment-level P&L |
| Debt Schedule | ✅ Required | Cash sweep, multi-tranche |
| Working Capital | ✅ Required | Days-based calculation |
| WACC | ⚡ If DCF | Full CAPM build |
| Returns Analysis | ✅ Required | Full attribution |
| Sensitivity | ✅ Required | Multiple matrices |
| Covenant Analysis | ⚡ If relevant | Leverage + coverage |

**Tips:**
- Build revenue from segment drivers
- Detailed SG&A with categories
- Cash sweep mechanics in debt schedule
- Full value creation attribution
- Management vs. buyer case comparison

**Generate:**
```python
generate_standard_lbo("Company", "output.xlsx")
```

---

### 7+ Day Institutional Case
**Focus:** Full institutional-quality model

| Module | Include? | Depth |
|--------|----------|-------|
| All Standard modules | ✅ Required | Comprehensive |
| Revenue Build | ✅ Required | Unit economics, cohorts |
| Expense Build | ✅ Required | Headcount model |
| Debt Schedule | ✅ Required | Revolver, PIK, covenants |
| WACC | ✅ Required | Unlevering/relevering |
| DCF Model | ✅ Required | Multiple terminal methods |
| Trading Comps | ✅ Required | Full analysis |
| Transaction Comps | ✅ Required | Control premium |
| Covenant Analysis | ✅ Required | Full package |
| Synergy Model | ⚡ If M&A | Bottom-up build |
| 3-Statement | ⚡ If requested | Fully circular |

**Generate:**
```python
generate_comprehensive_lbo("Company", "output.xlsx")
```

---

## Module Quick Reference

### Sources & Uses (`add_sources_uses`)
```
Sources              Uses
────────────────     ────────────────
Senior Debt          Purchase Price
Sub Debt             Refinance Debt
Rollover Equity      Transaction Fees
Sponsor Equity       Financing Fees
```

### Revenue Build (`add_revenue_build`)
- **Quick:** Total revenue with growth rate
- **Standard:** Segment breakdown with individual growth
- **Comprehensive:** Unit economics, customer cohorts, pricing

### Expense Build (`add_expense_build`)
- **Quick:** COGS and SG&A as % of revenue
- **Standard:** Line-item breakdown (materials, labor, S&M, G&A, R&D)
- **Comprehensive:** Headcount model, vendor analysis

### Debt Schedule (`add_debt_schedule`)
- **Quick:** Single tranche, flat annual paydown
- **Standard:** Multi-tranche (Senior + Sub), mandatory amortization
- **Comprehensive:** Cash sweep, revolver, PIK toggle, covenant tracking

### WACC Calculation (`add_wacc_calculation`)
- **Quick:** Simple assumption (e.g., 10%)
- **Standard:** Full CAPM: Rf + β(ERP) + Size Premium
- **Comprehensive:** Unlevered beta, relevering, country risk

### Working Capital (`add_working_capital`)
- **Quick:** NWC as % of revenue
- **Standard:** AR/AP/Inventory days calculation
- **Comprehensive:** Seasonal patterns, normalization, CCC analysis

### Returns Analysis (`add_returns_analysis`)
- **Quick:** MOIC and IRR by exit year
- **Standard:** Value creation bridge (EBITDA growth, multiple, debt paydown)
- **Comprehensive:** Full attribution, management vs. buyer case

### Sensitivity Tables (`add_sensitivity_tables`)
- **Quick:** Entry vs. Exit multiple matrix
- **Standard:** Multiple matrices (growth, margin, leverage)
- **Comprehensive:** Monte Carlo inputs, tornado chart data

---

## Prompt-to-Module Mapping

| User Request | Module | Quick Function |
|--------------|--------|----------------|
| "debt schedule", "debt paydown", "amortization" | `debt_schedule` | `generate_debt_schedule()` |
| "WACC", "cost of capital", "discount rate" | `wacc_calculation` | `generate_wacc_model()` |
| "revenue build", "segment analysis", "top line" | `revenue_build` | `generate_revenue_build()` |
| "SG&A", "expense build", "cost structure" | `expense_build` | `generate_expense_build()` |
| "working capital", "NWC", "AR/AP" | `working_capital` | via ExcelModelGenerator |
| "sources and uses", "S&U", "funding" | `sources_uses` | via ExcelModelGenerator |
| "returns", "MOIC", "IRR" | `returns_analysis` | via ExcelModelGenerator |
| "sensitivity", "matrix", "scenarios" | `sensitivity_tables` | via ExcelModelGenerator |
| "quick LBO", "24-hour model" | all essentials | `generate_quick_lbo()` |
| "full LBO model", "detailed model" | all modules | `generate_comprehensive_lbo()` |

---

## Usage Examples

### Single Module
```python
from excel_modules import generate_debt_schedule

generate_debt_schedule(
    company_name="Acme Corp",
    output_path="debt_schedule.xlsx",
    assumptions={
        "ltm_ebitda": 50,
        "senior_debt_multiple": 4.0,
        "sub_debt_multiple": 1.5,
    }
)
```

### Composable Model
```python
from excel_modules import ExcelModelGenerator, ModelDepth, ModelAssumptions

# Custom assumptions
assumptions = ModelAssumptions(
    company_name="Target Co",
    ltm_revenue=200,
    ltm_ebitda=40,
    entry_multiple=9.0,
    exit_multiple=8.5,
)

# Build custom model
gen = ExcelModelGenerator("Target Co", ModelDepth.STANDARD, assumptions)
gen.add_sources_uses()
gen.add_revenue_build()
gen.add_debt_schedule()
gen.add_returns_analysis()
gen.save("custom_model.xlsx")
```

### Time-Based Generation
```python
from excel_modules import get_framework_recommendation

# Get recommendation based on hours
framework = get_framework_recommendation(hours_available=36)
print(f"Recommended: {framework['name']}")
print(f"Required modules: {framework['required_modules']}")
print(f"Tips: {framework['tips']}")
```

---

## Key PE Textbook Principles Applied

### From Rosenbaum & Pearl
- Sources & Uses always balances
- Entry multiple = EV / LTM EBITDA
- Senior debt sized on coverage and leverage

### From Pignataro
- EBITDA adjustments clearly separated
- Working capital = operating items only
- Capex = maintenance + growth

### From Zeisberger
- Value creation attribution: EBITDA growth, multiple expansion, debt paydown
- IRR sensitive to timing of cash flows
- MOIC more stable than IRR for comparison

---

## File Locations

```
ii-agent/src/ii_skills/ib_toolkit/templates/excel_models/
├── excel_modules.py       # Modular generator (USE THIS)
├── MODEL_REFERENCE.md     # This reference document
└── [generated models]     # Output files
```
