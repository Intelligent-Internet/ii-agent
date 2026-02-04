# LBO Case Study Approach Guide

A structured decision tree for approaching PE/LBO modeling cases based on available time and required depth.

---

## Quick Reference: What to Build by Timeframe

```
                           LBO CASE TIMEFRAME
                                  |
        ┌─────────────┬──────────┴──────────┬─────────────┐
        ▼             ▼                     ▼             ▼
    24-HOUR       48-HOUR               5-DAY          7+ DAY
   (Screening)   (First Round)      (Final Round)  (Institutional)
        |             |                     |             |
   4 Sheets      9 Sheets             17 Sheets     30 Sheets
   ~25 Slides    ~25 Slides           60+ Slides    80+ Slides
```

---

## Phase 1: Immediate Assessment (First 30 Minutes)

Before building anything, gather and confirm:

### Information Checklist
- [ ] **Target financials**: Revenue, EBITDA, margins (historical + projections)
- [ ] **Transaction terms**: Purchase price, EV/EBITDA multiple, debt/equity split
- [ ] **Debt structure**: Tranches, rates, amortization, covenants
- [ ] **Exit assumptions**: Holding period, exit multiple range
- [ ] **Key value drivers**: Growth levers, margin improvement, synergies

### Quick Sanity Checks
```
Entry EV = EBITDA × Entry Multiple
Equity Check = EV - Total Debt
Debt/EBITDA = Total Debt ÷ EBITDA (should be 4-6x typically)
```

---

## 24-Hour Case (Screening / Quick Turn)

**Objective:** Determine if deal meets return thresholds. Go/no-go decision.

### What to Build

| Priority | Module | Purpose | Time |
|----------|--------|---------|------|
| 1 | Sources & Uses | Transaction structure | 15 min |
| 2 | Operating Model | P&L projections | 30 min |
| 3 | Returns Analysis | MOIC/IRR calculation | 20 min |
| 4 | Sensitivity Table | Key variable ranges | 15 min |

**Total Model Time:** ~1.5 hours
**Total Deck Time:** ~1.5 hours
**Buffer for Review:** ~1 hour

### Key Outputs to Deliver
- Entry valuation and transaction structure
- 5-year P&L with EBITDA growth
- Base case IRR and MOIC
- Sensitivity to entry multiple, exit multiple, and EBITDA growth
- Go/no-go recommendation

### Generate With
```python
# Excel
gen = ExcelModelGenerator(company)
gen.generate_quick_lbo()  # 4 sheets

# Slides
generate_full_deck(company, path)  # ~25 slides
```

### What to Skip (Save for Later)
- Detailed debt schedule (use simple assumptions)
- Working capital granularity
- Scenario analysis
- Due diligence modules

---

## 48-Hour Case (First Round / IOI Support)

**Objective:** Support indicative bid with defensible model and thesis.

### What to Build

| Priority | Module | Purpose | Time |
|----------|--------|---------|------|
| 1 | Sources & Uses | Transaction structure | 20 min |
| 2 | Revenue Build | Segment-level projections | 45 min |
| 3 | Expense Build | Margin assumptions | 30 min |
| 4 | Operating Model | Integrated P&L | 30 min |
| 5 | Debt Schedule | Multi-tranche with amortization | 45 min |
| 6 | Working Capital | NWC assumptions | 20 min |
| 7 | Returns Analysis | Detailed returns | 30 min |
| 8 | Sensitivity Tables | Multiple matrices | 30 min |
| 9 | WACC (optional) | Cost of capital | 20 min |

**Total Model Time:** ~5 hours
**Total Deck Time:** ~3 hours
**Buffer for Review:** ~2 hours

### Key Outputs to Deliver
- Detailed transaction structure with debt tranches
- Bottom-up revenue build by segment/product
- Expense breakdown showing margin expansion path
- Cash flow available for debt paydown
- Returns at multiple exit scenarios
- Preliminary investment thesis

### Generate With
```python
# Excel
gen = ExcelModelGenerator(company)
gen.generate_standard_lbo()  # 9 sheets

# Slides
generate_full_deck(company, path)  # ~25 slides
```

### Additional Modules to Consider
- Quality of Earnings (if data available)
- Customer concentration analysis
- Preliminary synergy estimates (if add-on or strategic)

---

## 5-Day Case (Final Round / Binding Bid)

**Objective:** Full underwriting to support binding offer with IC approval.

### What to Build

| Day | Focus Area | Modules |
|-----|------------|---------|
| **Day 1** | Core Model | S&U, Revenue, Expense, Operating Model |
| **Day 2** | Debt & Returns | Debt Schedule, Working Capital, Returns, Sensitivity |
| **Day 3** | Institutional | WACC, DCF, Scenario Analysis, Mgmt vs Buyer |
| **Day 4** | Due Diligence | QoE, NWC Normalization, Customer Quality, Credit |
| **Day 5** | Deck & Review | Full deck build, model audit, presentation prep |

### Full Module List (17 Sheets)

**Core LBO (9 sheets)**
- Sources & Uses
- Revenue Build
- Expense Build
- Operating Model
- Debt Schedule
- Working Capital
- WACC
- Returns Analysis
- Sensitivity

**Institutional (4 sheets)**
- Scenario Analysis (Bull/Bear/Base)
- Management vs Buyer Case
- DCF Valuation
- Covenant Analysis

**Due Diligence (4 sheets)**
- Quality of Earnings
- NWC Normalization
- Customer/Revenue Quality
- Credit Analysis

### Generate With
```python
# Excel
gen = ExcelModelGenerator(company)
gen.generate_comprehensive_lbo()  # 17 sheets

# Slides
generate_institutional_deck(company, path)  # 60+ slides
```

### Key Outputs to Deliver
- Fully integrated 3-statement model
- Multiple scenarios with probability weighting
- Management case vs buyer underwriting comparison
- DCF cross-check valuation
- Covenant compliance analysis
- Due diligence findings summary
- Complete IC memo deck

---

## 7+ Day Case (Institutional / Full DD)

**Objective:** Complete deal package for IC/Board approval with full diligence.

### Additional Modules Beyond 5-Day

**Transaction Structure (5 sheets)**
- Add-on Analysis (if platform + bolt-on)
- Synergy Model
- Carve-out Analysis (if corporate divestiture)
- Earnout Model (if contingent consideration)
- Purchase Price Allocation

**Value Creation (4 sheets)**
- Value Creation Bridge
- 100-Day Plan
- Exit Readiness Assessment
- Management Incentive Plan (MIP)

**Specialized (3 sheets)**
- Rollup Model (if buy-and-build)
- Tax Analysis
- Control Premium (if public target)

### Full 30-Sheet Model Structure

```
COMPREHENSIVE LBO MODEL (30 Sheets)
│
├── CORE LBO (9)
│   ├── Sources & Uses
│   ├── Revenue Build
│   ├── Expense Build
│   ├── Operating Model
│   ├── Debt Schedule
│   ├── Working Capital
│   ├── WACC
│   ├── Returns Analysis
│   └── Sensitivity
│
├── INSTITUTIONAL (4)
│   ├── Scenario Analysis
│   ├── Mgmt vs Buyer
│   ├── DCF Valuation
│   └── Covenant Analysis
│
├── DUE DILIGENCE (4)
│   ├── Quality of Earnings
│   ├── NWC Normalization
│   ├── Revenue Quality
│   └── Credit Analysis
│
├── CAPITAL STRUCTURE (4)
│   ├── Dividend Recap
│   ├── Refinancing Analysis
│   ├── Cap Table Waterfall
│   └── Sponsor Economics
│
├── TRANSACTION STRUCTURE (5)
│   ├── Add-on Analysis
│   ├── Synergy Model
│   ├── Carve-out Analysis
│   ├── Earnout Model
│   └── Purchase Price Allocation
│
├── VALUE CREATION (4)
│   ├── Value Creation Bridge
│   ├── 100-Day Plan
│   ├── Exit Readiness
│   └── Management Incentive Plan
│
└── SPECIALIZED (as needed)
    ├── Rollup Model
    ├── Tax Analysis
    └── Control Premium
```

---

## Decision Tree: Which Modules Do I Need?

### Transaction Type
```
Is this a...
│
├── Platform acquisition?
│   └── Core LBO + Institutional + DD modules
│
├── Add-on to existing platform?
│   └── Add: Add-on Analysis, Synergy Model
│
├── Corporate carve-out?
│   └── Add: Carve-out Analysis, standalone adjustments
│
├── Public company take-private?
│   └── Add: Control Premium, Tax Analysis (338h)
│
├── Rollup / consolidation play?
│   └── Add: Rollup Model, multiple add-on tracking
│
└── Growth equity (minority)?
    └── Simplify: Focus on DCF, skip debt schedule
```

### Deal Complexity
```
Does the deal have...
│
├── Contingent consideration?
│   └── Add: Earnout Model
│
├── Management rollover?
│   └── Add: MIP, Cap Table Waterfall
│
├── Significant synergies?
│   └── Add: Synergy Model (revenue + cost)
│
├── Complex debt structure?
│   └── Add: Covenant Analysis, Refinancing scenarios
│
├── Tax attributes (NOLs, step-up)?
│   └── Add: Tax Analysis
│
└── Near-term exit planning?
    └── Add: Exit Readiness, Value Creation Bridge
```

---

## Model Quality Checklist

### Before Submitting Any Model

**Mechanical Checks**
- [ ] Balance sheet balances (A = L + E)
- [ ] Cash flow ties to balance sheet cash change
- [ ] Debt schedule ties to balance sheet debt
- [ ] Sources = Uses in transaction
- [ ] No circular references or hard-coded overrides

**Reasonableness Checks**
- [ ] Revenue growth in realistic range for industry
- [ ] Margin expansion supported by identifiable initiatives
- [ ] Debt paydown consistent with cash generation
- [ ] Exit multiple justified by comparable transactions
- [ ] Returns in investable range (typically 20%+ IRR)

**Sensitivity Checks**
- [ ] Model doesn't break at reasonable stress levels
- [ ] Downside case still services debt
- [ ] Identified break-even assumptions

---

## Quick Commands by Scenario

### "I need a quick screening model"
```python
gen = ExcelModelGenerator(company)
gen.add_sources_uses()
gen.add_operating_model()
gen.add_returns_analysis()
gen.add_sensitivity_tables()
gen.save("screening_model.xlsx")
```

### "I need to analyze an add-on"
```python
gen = ExcelModelGenerator(company)
gen.add_addon_analysis()
gen.add_synergy_model()
gen.add_returns_analysis()
gen.save("addon_analysis.xlsx")

generate_addon_slides(company, "addon_deck.pptx")
generate_synergy_slides(company, "synergy_deck.pptx")
```

### "I need a full IC package"
```python
gen = ExcelModelGenerator(company)
gen.generate_comprehensive_lbo()  # 17 sheets
gen.add_quality_of_earnings()
gen.add_value_creation_bridge()
gen.add_hundred_day_plan()
gen.save("ic_model.xlsx")

generate_institutional_deck(company, "ic_deck.pptx")
```

### "I need to prep for exit"
```python
gen = ExcelModelGenerator(company)
gen.add_exit_readiness()
gen.add_value_creation_bridge()
gen.add_returns_analysis()
gen.save("exit_analysis.xlsx")

generate_exit_readiness_slides(company, "exit_deck.pptx")
generate_value_creation_slides(company, "value_deck.pptx")
```

---

## Common Mistakes to Avoid

| Mistake | Why It Matters | Fix |
|---------|----------------|-----|
| Over-engineering 24-hour case | Wastes time on detail that won't change decision | Focus on returns drivers only |
| Under-building 5-day case | Missing key analysis for IC | Use comprehensive template |
| Ignoring working capital | NWC can swing cash flows significantly | Always model NWC |
| Single-point estimates | Hides risk in assumptions | Always include sensitivity |
| Forgetting covenant headroom | Deal can fail at closing | Check covenants under stress |
| Mixing management vs buyer case | Unclear what you're underwriting | Keep cases clearly separated |

---

## File Locations

| Resource | Path |
|----------|------|
| Excel Generator | `templates/excel_models/excel_modules.py` |
| Slide Generator | `templates/case_study/slide_modules.py` |
| Quick Reference | `QUICK_REFERENCE.md` |
| Module Index | `templates/reference_outputs/MODULE_INDEX.md` |
| Reference Templates | `templates/reference_outputs/` |
| This Guide | `LBO_CASE_GUIDE.md` |
