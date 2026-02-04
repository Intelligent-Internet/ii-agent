# Investment Banking Toolkit Skill

Professional-grade investment banking tools for creating presentations and financial models.

## Version
1.3.0

## Capabilities

### 1. PowerPoint Generation
- **Industry Research Decks** - Market overview, trends, competitive landscape
- **Company Profile Decks** - Auto-populated with live financial data from Yahoo Finance
- **M&A Pitch Books** - Transaction overviews, CIMs, deal materials
- **IC Presentations** - 17-slide Investment Committee format

### 2. Excel Financial Models
- **DCF Model** - Discounted cash flow valuation with sensitivity analysis
- **LBO Model** - Leveraged buyout with sources/uses, debt schedule, returns
- **Comps Model** - Trading comps, transaction comps, football field
- **3-Statement Model** - Integrated P&L, balance sheet, cash flow

### 3. Analysis Frameworks
- **Orchestrated Deal Analysis** - 52-prompt system for structured deal execution
- **Middle Market Case Studies** - Modular analysis blocks for interview prep
- **Investment Thesis Builder** - 3-pillar thesis construction

### 4. PE-Informed Quick Analysis (NEW in v1.3)
- **LBO Quick Calculator** - Rapid IRR/MOIC analysis with sensitivity matrices and value creation attribution
- **Capital Structure Analyzer** - Debt capacity assessment, optimal financing recommendations, industry benchmarks
- **Quality of Earnings Analyzer** - EBITDA normalization framework, adjustment risk-tiering, DD question generation

### 4. Data Fetching
- Live company financials from Yahoo Finance
- Comparable company metrics
- Key ratios and valuation multiples

## Usage

### As ii-agent Skill

```python
from ii_skills.ib_toolkit import get_toolkit

# Initialize the toolkit
toolkit = get_toolkit()

# Create a company profile deck
result = toolkit.execute(
    "create_company_deck",
    ticker="AAPL",
    comp_tickers=["MSFT", "GOOGL", "META"]
)
print(f"Deck created: {result['output_path']}")

# Create an LBO model
result = toolkit.execute(
    "create_lbo_model",
    company_name="Target Corp",
    entry_multiple=8.0,
    exit_multiple=9.0,
    hold_period=5
)
print(f"Model created: {result['output_path']}")

# Fetch company data
result = toolkit.execute("fetch_company_data", ticker="NVDA")
print(result['data'])
```

### Middle Market Case Analysis

```python
# Initialize case intake
result = toolkit.execute(
    "run_case_intake",
    company_name="Target Co",
    deal_type="lbo",
    materials_summary="CIM (45 pages), Management Deck, 3Y Financials"
)

# Execute specific analysis module
result = toolkit.execute(
    "execute_analysis_module",
    module_id="M4",  # Historical Financial Analysis
    company_data=financials
)
```

### LBO Quick Calculator (NEW)

```python
# Quick LBO returns analysis
result = toolkit.execute(
    "quick_lbo_analysis",
    ebitda=50,           # $50M EBITDA
    entry_multiple=8.0,
    exit_multiple=8.5,
    leverage=4.5,
    hold_years=5,
    ebitda_growth=0.08
)
print(f"MOIC: {result['moic']}x | IRR: {result['irr']}%")
print(result['summary_report'])
```

### Capital Structure Analysis (NEW)

```python
# Analyze debt capacity
result = toolkit.execute(
    "analyze_capital_structure",
    ebitda=75,
    revenue=500,
    capex=25,
    industry="business_services",
    revenue_volatility="moderate"
)
print(f"Max Debt: ${result['max_debt_capacity']}M ({result['max_leverage']:.1f}x)")
print(result['report'])
```

### Quality of Earnings Analysis (NEW)

```python
# Analyze EBITDA adjustments
result = toolkit.execute(
    "analyze_quality_of_earnings",
    revenue=250,
    reported_ebitda=35,
    adjustments=[
        {"description": "Restructuring", "amount": 2.5, "category": "one_time", "risk": "low"},
        {"description": "Stock comp", "amount": 3.2, "category": "accounting", "risk": "moderate"},
        {"description": "New customer run-rate", "amount": 2.0, "category": "run_rate", "risk": "moderate"},
    ],
    company_name="Target Corp"
)
print(f"Adjusted EBITDA: ${result['adjusted_ebitda']}M")
print(result['report'])
```

## Documentation

Full documentation available in `docs/skills/ib_toolkit/`:

| Document | Description |
|----------|-------------|
| `BEST_PRACTICES.md` | Slide structure, model architecture, financial metrics, risk frameworks |
| `SLIDE_TEMPLATES.md` | ASCII templates for IC presentations (Growth Equity, PE/LBO) |
| `ORCHESTRATION_FRAMEWORK.md` | 52-prompt system with dependency tracking and state management |
| `PROMPT_LIBRARY.md` | Executable prompts for structured deal execution |
| `CASE_INTAKE_PROTOCOL.md` | Middle market interview case study approach |
| `CLAUDE_FOR_EXCEL_PROMPTS.md` | Excel modeling prompts |

## Analysis Modules

Modular analysis blocks for case studies:

| ID | Module | Phase | Time |
|----|--------|-------|------|
| M1 | Business Quality Assessment | Foundation | 15-20 min |
| M2 | Market & Competitive Position | Foundation | 20-30 min |
| M3 | Management & Operational Assessment | Foundation | 15-20 min |
| M4 | Historical Financial Analysis | Financial | 20-30 min |
| M5 | Projection Build / Validation | Financial | 30-45 min |
| M6 | Working Capital & Cash Conversion | Financial | 15-20 min |
| M7 | Valuation (Comps / DCF / LBO) | Financial | 30-45 min |
| M8 | Deal Structure & Sources/Uses | Deal | 20-30 min |
| M9 | Debt Capacity & Financing | Deal | 15-20 min |
| M10 | Returns Analysis & Sensitivity | Deal | 20-30 min |
| M11 | Value Creation Levers | Deal | 15-20 min |
| M12 | Investment Recommendation | Output | 15-20 min |
| M13 | Risk Assessment & Mitigants | Output | 15-20 min |
| M14 | Due Diligence Questions | Output | 20-30 min |
| **M15** | **LBO Quick Calculator** | **Quick Analysis** | **10-15 min** |
| **M16** | **Capital Structure Analysis** | **Quick Analysis** | **15-20 min** |
| **M17** | **Quality of Earnings Analysis** | **Due Diligence** | **20-30 min** |

## Dependencies

```
python-pptx>=0.6.21
openpyxl>=3.1.0
yfinance>=0.2.0
requests>=2.28.0
```

## Configuration

Most features work without API keys (Yahoo Finance is free). Optional:

| Config | Description | Required |
|--------|-------------|----------|
| `FMP_API_KEY` | Financial Modeling Prep API | No |
| `ALPHA_VANTAGE_KEY` | Alpha Vantage API | No |

## Output

Generated files are saved to `output/`:
```
output/
├── [Company]_Company_Profile_[DATE].pptx
├── DCF_Model_[Company]_[DATE].xlsx
├── LBO_Model_[Company]_[DATE].xlsx
├── Comps_Model_[Company]_[DATE].xlsx
└── Three_Statement_Model_[Company]_[DATE].xlsx
```

---

*Source: II-Agent System*
*Best Practices: BCI Growth Equity (2026), Northleaf PE (2025)*
*Orchestration: Buyside Agent Resources (52-Prompt PE System)*
*PE Frameworks: Based on Pignataro LBO Analysis, Mastering Private Equity, PE Operational DD*
