# PE/IB Slide Module Reference

## Quick Reference - Prompt to Module Mapping

| User Request | Module | Function |
|--------------|--------|----------|
| "industry analysis", "market overview", "TAM", "five forces" | `industry_analysis` | `generate_industry_analysis()` |
| "competitive analysis", "SWOT", "competitors", "market position" | `competitive_analysis` | `generate_competitive_analysis()` |
| "financial analysis", "financials", "P&L", "projections" | `financial_analysis` | `generate_financial_analysis()` |
| "debt analysis", "capital structure", "leverage", "covenants" | `debt_analysis` | `generate_debt_analysis()` |
| "LBO", "returns analysis", "sources and uses", "transaction" | `lbo_analysis` | `generate_lbo_analysis()` |
| "management analysis", "leadership", "team", "executives" | `management_analysis` | `generate_management_analysis()` |
| "valuation", "comps", "multiples", "trading comps" | `valuation` | `generate_valuation_analysis()` |
| "investment thesis", "recommendation", "risks", "decision" | `investment_thesis` | `generate_investment_thesis()` |
| "company overview", "business description", "customers" | `company_overview` | via SlideGenerator class |
| "full deck", "complete analysis", "investment memo" | all modules | `generate_full_deck()` |

### Institutional Modules (7+ Day Case)

| User Request | Module | Function |
|--------------|--------|----------|
| "scenario analysis", "bull/bear/base", "probability weighted" | `scenario_analysis` | `generate_scenario_analysis()` |
| "management vs buyer", "case comparison", "haircut" | `management_vs_buyer` | `generate_management_vs_buyer()` |
| "DCF", "discounted cash flow", "terminal value" | `dcf_valuation` | `generate_dcf_slides()` |
| "covenant analysis", "covenant compliance", "leverage ratio" | `covenant_analysis` | `generate_covenant_slides()` |
| "institutional deck", "full institutional", "7-day case" | all + institutional | `generate_institutional_deck()` |

## Module Details

### 1. Industry Analysis (`industry_analysis`)
**Slides generated:** 3
- Market Overview (TAM/SAM/SOM, growth drivers, headwinds)
- Porter's Five Forces diagram
- Industry Value Chain

**Best for:** Understanding market dynamics, sizing opportunities

### 2. Competitive Analysis (`competitive_analysis`)
**Slides generated:** 3
- Competitive Landscape table
- SWOT Analysis (2x2 framework)
- Competitive Moat Assessment

**Best for:** Positioning vs. competitors, strategic assessment

### 3. Financial Analysis (`financial_analysis`)
**Slides generated:** 3
- Historical Financial Summary table
- Projected Financial Summary table
- Key Operating Metrics comparison

**Best for:** Historical performance, projections, peer benchmarking

### 4. Debt Analysis (`debt_analysis`)
**Slides generated:** 3
- Current Capital Structure table
- Debt Capacity Analysis table
- Coverage Ratio Analysis

**Best for:** Leverage analysis, refinancing, covenant assessment

### 5. LBO Analysis (`lbo_analysis`)
**Slides generated:** 3
- Sources and Uses of Funds
- LBO Returns Analysis table
- Returns Sensitivity Analysis

**Best for:** Transaction structuring, returns modeling

### 6. Management Analysis (`management_analysis`)
**Slides generated:** 2
- Leadership Team Overview table
- Management Assessment (strengths, risks, incentives)

**Best for:** Due diligence on key personnel, succession planning

### 7. Valuation (`valuation`)
**Slides generated:** 3
- Public Comparable Companies table
- Precedent Transactions table
- Valuation Summary (football field)

**Best for:** Determining fair value range, negotiation support

### 8. Investment Thesis (`investment_thesis`)
**Slides generated:** 3
- Investment Thesis pillars
- Risk Assessment Matrix (2x2)
- Investment Recommendation

**Best for:** IC memo, final recommendation

---

## Institutional Modules (7+ Day Case)

These modules are designed for comprehensive institutional-quality analysis, typically used in 7+ day case studies or IC presentations.

### 9. Scenario Analysis (`scenario_analysis`)
**Slides generated:** 4
- Scenario Comparison Summary (Bull/Bear/Base table)
- Scenario Key Drivers (assumptions breakdown)
- Probability-Weighted Returns
- Downside Protection Analysis

**Best for:** IC presentations, risk assessment, return attribution

### 10. Management vs Buyer Case (`management_vs_buyer`)
**Slides generated:** 3
- Projection Case Comparison table
- Key Variance Drivers
- Returns Comparison

**Best for:** Explaining haircuts to management plan, underwriting rationale

### 11. DCF Valuation (`dcf_valuation`)
**Slides generated:** 3
- DCF Valuation Summary
- Free Cash Flow Build table
- DCF Sensitivity Analysis (WACC vs Exit Multiple)

**Best for:** Standalone valuation support, triangulation with comps

### 12. Covenant Analysis (`covenant_analysis`)
**Slides generated:** 4
- Covenant Package Overview
- Leverage Ratio Trajectory
- Interest Coverage Trajectory
- Covenant Stress Test

**Best for:** Credit analysis, lender presentations, downside protection

## Usage Examples

### Python - Single Module
```python
from slide_modules import generate_competitive_analysis

generate_competitive_analysis(
    company_name="Acme Corp",
    output_path="C:/Users/user/Downloads/acme_competitive.pptx"
)
```

### Python - Multiple Modules (Composable)
```python
from slide_modules import SlideGenerator

gen = SlideGenerator(company_name="Acme Corp")
gen.add_industry_analysis()
gen.add_competitive_analysis()
gen.add_financial_analysis()
gen.save("C:/Users/user/Downloads/acme_analysis.pptx")
```

### Python - Full Deck with Data
```python
from slide_modules import generate_full_deck

generate_full_deck(
    company_name="Acme Corp",
    output_path="C:/Users/user/Downloads/acme_full.pptx",
    data={
        'company': {'segments': [...]},
        'financial': {'historical': [...]},
    }
)
```

### Python - Institutional Modules
```python
from slide_modules import SlideGenerator

# Add specific institutional modules
gen = SlideGenerator(company_name="Acme Corp")
gen.add_scenario_analysis()
gen.add_management_vs_buyer()
gen.add_covenant_analysis()
gen.save("C:/Users/user/Downloads/acme_institutional.pptx")
```

### Python - Full Institutional Deck
```python
from slide_modules import generate_institutional_deck

generate_institutional_deck(
    company_name="Acme Corp",
    output_path="C:/Users/user/Downloads/acme_institutional_full.pptx"
)
```

## Template Location

The master template is stored at:
```
C:\Users\user\ii-agent\src\ii_skills\ib_toolkit\templates\case_study\
├── slide_modules.py           # Modular generator (USE THIS)
├── analysis_slides_template.py # Legacy full-deck generator
├── SLIDE_REFERENCE.md          # This reference document
├── lbo_model_template.py       # Excel LBO model generator
├── quick_case_template.py      # Excel quick case generator
└── CASE_STUDY_SKILL.md         # Overall skill documentation
```

## Output Styling

All slides match Roberto's BCI/Northleaf case study style:
- **Dimensions:** 13.333" x 7.5" (16:9 widescreen)
- **Font:** Arial throughout
- **Primary Color:** #00A651 (TD Green) or #00365B (dark navy)
- **Title:** 28pt bold at top
- **Header Bar:** Gray (#4A4A4A) with white text
- **Key Takeaway:** Green bar at bottom with italic white text
- **Source:** Bottom left (8pt gray)
- **Slide Number:** Bottom right

---

## Professional Slide Templates

For comprehensive design guidance, see:
**[docs/skills/SLIDE_DESIGN_GUIDE.md](../../../../docs/skills/SLIDE_DESIGN_GUIDE.md)**

This guide includes 14 professional slide templates extracted from TD Securities presentations:

| Template | Use For |
|----------|---------|
| Executive Summary | Opening slides, recommendations |
| Numbered Key Points | Investment highlights, thesis pillars |
| Peer Benchmarking | Valuation multiples, metrics comparison |
| Comps Table | Trading comps, peer analysis |
| Time Series | Historical performance, trends |
| Before/After | Value creation, renovations |
| Sources & Uses | Transaction structure, IPO analysis |
| Scenario Analysis | Disposition analysis, strategic alternatives |
| Horizontal Bar + Pie | Rankings, geographic exposure |
| Gantt Chart | Transaction timeline, project phases |
| Heat Map | Performance matrix, scoring |
| Portfolio Valuations | Fund investments, exit forecasts |
| Geographic Map | Property locations, market presence |
| Debt Benchmarking | Capital structure comparison |

### Key Design Patterns

1. **Key Takeaway Bar**: Green bar at bottom with italic text summarizing the slide's insight
2. **Subject Highlighting**: Subject company/fund always in green, peers in gray
3. **Header Bars**: Gray with white text to separate sections
4. **Data Tables**: Low/Mid/High scenarios in columns, color-coded headers
5. **Source Citations**: Always include source and footnotes at bottom
