# PE/IB Case Study Skill

## Overview

Institutional-grade case study support for Private Equity and Investment Banking interviews. This skill provides templates, frameworks, and automated analysis for live case work.

## Templates Available

### 1. LBO Model Template (`LBO_Model_Template_YYYYMMDD.xlsx`)
**Full institutional model for comprehensive cases (60-120 minutes)**

Sheets:
- **Cover** - Deal summary, key metrics
- **Assumptions** - All inputs consolidated (blue = input, black = formula)
- **Sources & Uses** - Transaction funding structure
- **Operating Model** - 5-year income statement and FCF projections
- **Debt Schedule** - Multi-tranche (TLB, Second Lien, Mezz) with cash sweep
- **Returns Analysis** - MOIC, IRR, sensitivity tables, value creation bridge

Key Features:
- Goldman Sachs formatting standards
- Fully linked formulas
- Scenario toggles
- Print-ready layout

### 2. Quick Case Template (`Quick_Case_Template_YYYYMMDD.xlsx`)
**Streamlined single-sheet model for timed cases (30-60 minutes)**

Sections (all on one sheet):
1. Transaction Inputs (10 key assumptions)
2. Sources & Uses (instant calculation)
3. 5-Year Operating Projections
4. Returns Calculator (MOIC/IRR)
5. Exit Multiple Sensitivity Table

Key Features:
- All inputs at top for fast data entry
- Instant results as you type
- Fits on 1-2 printed pages

## How to Use

### Receiving a New Case

1. **Open Template**: Choose based on time available:
   - 60+ minutes → `LBO_Model_Template`
   - 30-60 minutes → `Quick_Case_Template`

2. **Input Data from CIM/Materials**:
   - LTM Revenue and EBITDA
   - Entry multiple (from transaction terms or comparable transactions)
   - Capital structure (leverage level, debt tranches)
   - Operating assumptions (growth, margins)
   - Exit assumptions

3. **Validate Returns**:
   - Target MOIC: 2.0-3.0x (buyout), 3.0-4.0x (growth)
   - Target IRR: 20-25% (buyout), 25-30%+ (growth)

4. **Run Sensitivities**:
   - Entry/Exit multiple matrix
   - Revenue growth scenarios
   - Margin improvement cases

### Key Formulas Reference

**MOIC (Multiple on Invested Capital)**
```
MOIC = Exit Equity Value / Entry Equity Investment
```

**IRR (Internal Rate of Return)**
```
IRR = (Exit Equity / Entry Equity)^(1/n) - 1
where n = holding period in years
```

**Unlevered Free Cash Flow**
```
UFCF = EBITDA - Taxes - CapEx - Δ NWC
```

**Free Cash Flow for Debt Paydown**
```
FCFDP = UFCF - Cash Interest - Mandatory Amortization
```

## Interview Tips

### First 5 Minutes
- Read the prompt carefully
- Note the time limit
- Identify: deal type, key metrics given, what they're asking

### Model Building Order
1. Sources & Uses (anchor the deal size)
2. Operating projections (revenue → EBITDA → FCF)
3. Debt schedule (if time permits)
4. Returns calculation
5. Sensitivities

### Common Pitfalls
- Forgetting to subtract fees from equity check
- Not accounting for cash interest in FCF
- Using wrong EBITDA year for entry (usually LTM) vs exit (projected)
- Circular reference in debt/interest (use average balance)

### Presentation Structure
1. Transaction Overview (30 seconds)
2. Investment Thesis (1 minute)
3. Key Assumptions (1 minute)
4. Returns Summary (30 seconds)
5. Risks & Mitigants (1 minute)
6. Recommendation (30 seconds)

## Quick Reference Tables

### Target Returns by Strategy
| Strategy | MOIC | IRR | Hold Period |
|----------|------|-----|-------------|
| Large Cap Buyout | 2.0-2.5x | 18-22% | 4-6 years |
| Mid-Market Buyout | 2.5-3.0x | 20-25% | 4-5 years |
| Growth Equity | 3.0-4.0x | 25-35% | 4-6 years |
| Lower Mid-Market | 3.0-3.5x | 25-30% | 4-5 years |

### Leverage Benchmarks (Debt / EBITDA)
| Industry | Conservative | Moderate | Aggressive |
|----------|--------------|----------|------------|
| Healthcare | 3.0x | 4.5x | 6.0x |
| Software | 3.0x | 4.5x | 6.0x |
| Business Services | 3.5x | 5.0x | 6.5x |
| Industrials | 2.5x | 4.0x | 5.5x |
| Consumer | 3.0x | 4.5x | 6.0x |

### Debt Tranches Reference
| Tranche | Typical Spread | Amortization | Term |
|---------|----------------|--------------|------|
| Term Loan B | L+300-400bp | 1% p.a. | 7 years |
| Second Lien | L+600-750bp | None | 8 years |
| Mezzanine | 12-15% total | None | 8-10 years |
| HY Bonds | 7-10% coupon | None | 7-10 years |

## File Structure

```
templates/case_study/
├── CASE_STUDY_SKILL.md           # This documentation
├── lbo_model_template.py          # Full LBO template generator
├── quick_case_template.py         # Quick case template generator
├── LBO_Model_Template_YYYYMMDD.xlsx   # Generated full model
└── Quick_Case_Template_YYYYMMDD.xlsx  # Generated quick model
```

## Regenerating Templates

If you need fresh templates:

```bash
cd ii-agent/src/ii_skills/ib_toolkit/templates/case_study
python lbo_model_template.py    # Full model
python quick_case_template.py   # Quick model
```

---

*Based on: Private Equity textbook frameworks (Pignataro, Zeisberger)*
*Formatting: Goldman Sachs / KKR institutional standards*
*Version: 1.0.0*
