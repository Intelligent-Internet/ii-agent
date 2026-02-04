# IB Toolkit Quick Reference

## Reference Templates Location
```
src/ii_skills/ib_toolkit/templates/reference_outputs/
├── Institutional_LBO_Template.xlsx   # 17-sheet comprehensive model
└── Institutional_Deck_Template.pptx  # 60+ slide institutional deck
```

## Request → Output Mapping

When the user asks for analysis, generate BOTH the Excel sheet AND corresponding slides.

### Core Modules

| User Request | Excel Module | Excel Sheet | Slide Module | Slides |
|--------------|--------------|-------------|--------------|--------|
| "scenario analysis", "bull/bear/base" | `add_scenario_analysis()` | Scenario Analysis | `add_scenario_analysis()` | 4 |
| "management vs buyer", "case comparison" | `add_management_vs_buyer()` | Mgmt vs Buyer | `add_management_vs_buyer()` | 3 |
| "DCF", "discounted cash flow" | `add_dcf_valuation()` | DCF Valuation | `add_dcf_valuation()` | 3 |
| "covenant analysis", "leverage covenant" | `add_covenant_analysis()` | Covenant Analysis | `add_covenant_analysis()` | 4 |
| "debt schedule", "amortization" | `add_debt_schedule()` | Debt Schedule | `add_debt_analysis()` | 3 |
| "revenue build", "segment analysis" | `add_revenue_build()` | Revenue Build | `add_financial_analysis()` | 3 |
| "expense build", "SG&A" | `add_expense_build()` | Expense Build | `add_financial_analysis()` | 3 |
| "WACC", "cost of capital" | `add_wacc_calculation()` | WACC | `add_dcf_valuation()` | 3 |
| "sources and uses", "S&U" | `add_sources_uses()` | Sources & Uses | `add_lbo_analysis()` | 3 |
| "returns analysis", "MOIC/IRR" | `add_returns_analysis()` | Returns Analysis | `add_lbo_analysis()` | 3 |
| "sensitivity", "matrix" | `add_sensitivity_tables()` | Sensitivity | `add_lbo_analysis()` | 3 |
| "working capital", "NWC" | `add_working_capital()` | Working Capital | `add_financial_analysis()` | 3 |
| "operating model", "P&L" | `add_operating_model()` | Operating Model | `add_financial_analysis()` | 3 |

### Due Diligence & Quality Modules

| User Request | Excel Module | Excel Sheet | Slide Module | Slides |
|--------------|--------------|-------------|--------------|--------|
| "quality of earnings", "QoE", "EBITDA adjustments" | `add_quality_of_earnings()` | Quality of Earnings | `add_quality_of_earnings()` | 3 |
| "working capital normalization", "NWC peg" | `add_working_capital_normalization()` | NWC Normalization | `add_working_capital_analysis()` | 2 |
| "customer quality", "concentration", "churn" | `add_customer_revenue_quality()` | Revenue Quality | `add_customer_quality_analysis()` | 3 |
| "credit analysis", "debt sizing", "stress test" | `add_credit_debt_sizing()` | Credit Analysis | `add_credit_analysis_slides()` | 3 |

### Returns & Capital Structure Modules

| User Request | Excel Module | Excel Sheet | Slide Module | Slides |
|--------------|--------------|-------------|--------------|--------|
| "dividend recap", "recapitalization" | `add_dividend_recap()` | Dividend Recap | `add_dividend_recap_slides()` | 2 |
| "refinancing", "rate savings" | `add_refinancing_analysis()` | Refinancing | `add_refinancing_slides()` | 2 |
| "waterfall", "cap table", "LP/GP split" | `add_cap_table_waterfall()` | Cap Table Waterfall | `add_waterfall_slides()` | 2 |
| "sponsor economics", "GP carry", "fund returns" | `add_sponsor_economics()` | Sponsor Economics | `add_sponsor_economics_slides()` | 2 |

### Slides Only (No Excel)

| User Request | Slide Module | Slides |
|--------------|--------------|--------|
| "industry analysis", "TAM/SAM" | `add_industry_analysis()` | 3 |
| "competitive analysis", "SWOT" | `add_competitive_analysis()` | 3 |
| "valuation", "comps" | `add_valuation()` | 3 |
| "investment thesis", "recommendation" | `add_investment_thesis()` | 3 |
| "management team", "leadership" | `add_management_analysis()` | 2 |

## Time-Based Model Generation

| Timeframe | Excel Function | Sheets | Slide Function | Slides |
|-----------|----------------|--------|----------------|--------|
| 24-hour | `generate_quick_lbo()` | 4 | `generate_full_deck()` | ~25 |
| 48-hour | `generate_standard_lbo()` | 9 | `generate_full_deck()` | ~25 |
| 7+ day | `generate_comprehensive_lbo()` | 17 | `generate_institutional_deck()` | 60+ |

## Excel Sheet Details (Full Model)

### Core LBO Sheets
| Sheet Name | Contents | Key Outputs |
|------------|----------|-------------|
| Sources & Uses | Transaction funding | Total EV, Equity check, Debt amounts |
| Revenue Build | Segment-level projections | 5-year revenue by segment |
| Expense Build | COGS + SG&A breakdown | Gross margin, EBITDA margin |
| Operating Model | Full P&L | EBITDA, Net income by year |
| Debt Schedule | Multi-tranche amortization | Ending debt, Interest expense |
| Working Capital | AR/AP/Inventory days | NWC change, Cash conversion |
| WACC | Cost of capital calculation | Blended WACC rate |
| Returns Analysis | MOIC/IRR by exit year | Value creation bridge |
| Sensitivity | Entry/exit/growth matrices | IRR ranges |
| Scenario Analysis | Bull/Bear/Base | Probability-weighted returns |
| Mgmt vs Buyer | Case comparison | Variance analysis, Returns gap |
| DCF Valuation | UFCF → Terminal → PV | Implied EV/EBITDA |
| Covenant Analysis | Leverage + Coverage tracking | Compliance status |

### Due Diligence Sheets
| Sheet Name | Contents | Key Outputs |
|------------|----------|-------------|
| Quality of Earnings | EBITDA adjustments | Adjusted EBITDA, Run-rate |
| NWC Normalization | Historical NWC, Days | Target NWC, Peg variance |
| Revenue Quality | Customer concentration, Churn | LTV/CAC, Quality score |
| Credit Analysis | Leverage, Coverage ratios | Max debt capacity, Implied rating |

### Capital Structure Sheets
| Sheet Name | Contents | Key Outputs |
|------------|----------|-------------|
| Dividend Recap | Mid-hold dividend | Returns with/without recap |
| Refinancing | Rate comparison | Annual savings, Payback |
| Cap Table Waterfall | LP/GP splits | Distribution by exit value |
| Sponsor Economics | GP carry, Fund returns | Total GP economics |

## Quick Access Functions

### Excel
```python
# Due Diligence
gen.add_quality_of_earnings()
gen.add_working_capital_normalization()
gen.add_customer_revenue_quality()
gen.add_credit_debt_sizing()

# Capital Structure
gen.add_dividend_recap()
gen.add_refinancing_analysis()
gen.add_cap_table_waterfall()
gen.add_sponsor_economics()
```

### Slides
```python
# Due Diligence
generate_qoe_slides(company, path)
generate_nwc_slides(company, path)
generate_customer_quality_slides(company, path)
generate_credit_slides(company, path)

# Capital Structure
generate_dividend_recap_slides(company, path)
generate_refinancing_slides(company, path)
generate_waterfall_slides(company, path)
generate_sponsor_economics_slides(company, path)
```

## File Locations

| Type | Location |
|------|----------|
| Excel Generator | `templates/excel_models/excel_modules.py` |
| Slide Generator | `templates/case_study/slide_modules.py` |
| Excel Reference | `templates/excel_models/MODEL_REFERENCE.md` |
| Slide Reference | `templates/case_study/SLIDE_REFERENCE.md` |
| Reference Templates | `templates/reference_outputs/` |
| This Quick Reference | `QUICK_REFERENCE.md` |
