# IB Toolkit Quick Reference

## Reference Templates Location
```
src/ii_skills/ib_toolkit/templates/reference_outputs/
├── Institutional_LBO_Template.xlsx   # 13-sheet comprehensive model
└── Institutional_Deck_Template.pptx  # 47-slide institutional deck
```

## Request → Output Mapping

When the user asks for analysis, generate BOTH the Excel sheet AND corresponding slides.

| User Request | Excel Module | Excel Sheet | Slide Module | Slides |
|--------------|--------------|-------------|--------------|--------|
| "scenario analysis", "bull/bear/base" | `add_scenario_analysis()` | Scenario Analysis | `add_scenario_analysis()` | 4 slides |
| "management vs buyer", "case comparison" | `add_management_vs_buyer()` | Mgmt vs Buyer | `add_management_vs_buyer()` | 3 slides |
| "DCF", "discounted cash flow" | `add_dcf_valuation()` | DCF Valuation | `add_dcf_valuation()` | 3 slides |
| "covenant analysis", "leverage covenant" | `add_covenant_analysis()` | Covenant Analysis | `add_covenant_analysis()` | 4 slides |
| "debt schedule", "amortization" | `add_debt_schedule()` | Debt Schedule | `add_debt_analysis()` | 3 slides |
| "revenue build", "segment analysis" | `add_revenue_build()` | Revenue Build | `add_financial_analysis()` | 3 slides |
| "expense build", "SG&A" | `add_expense_build()` | Expense Build | `add_financial_analysis()` | 3 slides |
| "WACC", "cost of capital" | `add_wacc_calculation()` | WACC | `add_dcf_valuation()` | 3 slides |
| "sources and uses", "S&U" | `add_sources_uses()` | Sources & Uses | `add_lbo_analysis()` | 3 slides |
| "returns analysis", "MOIC/IRR" | `add_returns_analysis()` | Returns Analysis | `add_lbo_analysis()` | 3 slides |
| "sensitivity", "matrix" | `add_sensitivity_tables()` | Sensitivity | `add_lbo_analysis()` | 3 slides |
| "working capital", "NWC" | `add_working_capital()` | Working Capital | `add_financial_analysis()` | 3 slides |
| "operating model", "P&L" | `add_operating_model()` | Operating Model | `add_financial_analysis()` | 3 slides |
| "industry analysis", "TAM/SAM" | — | — | `add_industry_analysis()` | 3 slides |
| "competitive analysis", "SWOT" | — | — | `add_competitive_analysis()` | 3 slides |
| "valuation", "comps" | — | — | `add_valuation()` | 3 slides |
| "investment thesis", "recommendation" | — | — | `add_investment_thesis()` | 3 slides |
| "management team", "leadership" | — | — | `add_management_analysis()` | 2 slides |

## Time-Based Model Generation

| Timeframe | Excel Function | Sheets | Slide Function | Slides |
|-----------|----------------|--------|----------------|--------|
| 24-hour | `generate_quick_lbo()` | 4 | `generate_full_deck()` | ~25 |
| 48-hour | `generate_standard_lbo()` | 9 | `generate_full_deck()` | ~25 |
| 7+ day | `generate_comprehensive_lbo()` | 13 | `generate_institutional_deck()` | 47 |

## Excel Sheet Details (Institutional Model)

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

## Slide Sections (Institutional Deck)

| Section | Slides | Key Content |
|---------|--------|-------------|
| Company Overview | 3 | Business description, segments, customers |
| Industry Analysis | 3 | TAM/SAM, Porter's forces, value chain |
| Competitive Analysis | 3 | Landscape, SWOT, competitive moat |
| Financial Analysis | 3 | Historical, projected, metrics |
| Valuation | 3 | Trading comps, transaction comps, football field |
| LBO Analysis | 3 | S&U, returns, sensitivity |
| Scenario Analysis | 4 | Bull/Bear/Base, drivers, weighted returns, downside |
| Management vs Buyer | 3 | Case comparison, variance, returns bridge |
| DCF Valuation | 3 | Summary, FCF build, sensitivity |
| Covenant Analysis | 4 | Package, leverage, coverage, stress test |
| Investment Thesis | 3 | Thesis pillars, risks, recommendation |

## Quick Generation Examples

### Generate specific module pair (Excel + Slides)
```python
# Excel
from excel_modules import ExcelModelGenerator, ModelDepth, ModelAssumptions
gen = ExcelModelGenerator("Company", ModelDepth.COMPREHENSIVE)
gen.add_scenario_analysis()
gen.save("scenario_analysis.xlsx")

# Slides
from slide_modules import SlideGenerator
slides = SlideGenerator("Company")
slides.add_scenario_analysis()
slides.save("scenario_analysis.pptx")
```

### Generate full institutional package
```python
from excel_modules import generate_comprehensive_lbo
from slide_modules import generate_institutional_deck

generate_comprehensive_lbo("Company", "model.xlsx")
generate_institutional_deck("Company", "deck.pptx")
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
