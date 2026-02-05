# Excel Model Conventions & Architecture
## Formatting Standards, Model Architecture, and Template Specifications

*Version: 1.0.0 | Last Updated: February 2026*

---

## Color Coding Standards

Consistent color coding is the single most important convention for model readability. Every cell in the model should follow this system.

### Font Colors

| Color | Hex | Use | Example |
|-------|-----|-----|---------|
| **Blue** | `#0000FF` | Hardcoded inputs / assumptions | Entry multiple: `8.0x` |
| **Black** | `#000000` | Formulas (calculated values) | `=Revenue*Margin` |
| **Green** | `#008000` | Cross-tab links (references to other sheets) | `='P&L'!B15` |
| **Purple** | `#800080` | Same-sheet references to distant cells | `=B5*$H$3` |
| **Red** | `#FF0000` | Errors, warnings, balance checks | `=IF(Check=0,"OK","ERROR")` |

### Cell Background Colors

| Color | Hex | Use |
|-------|-----|-----|
| **Light Yellow** | `#FFFDE7` | Input cells (assumptions area) |
| **Light Gray** | `#F5F5F5` | Section headers / subtotals |
| **White** | `#FFFFFF` | Formula cells (default) |
| **Light Green** | `#E8F5E9` | Check cells that pass |
| **Light Red** | `#FFEBEE` | Check cells that fail |

### Header Formatting

| Element | Style |
|---------|-------|
| Tab section headers | Bold, navy background (`#01395D`), white text |
| Row group headers | Bold, gray background (`#D9D9D9`) |
| Subtotals | Bold, light gray background, top border |
| Grand totals | Bold, double underline, dark border top and bottom |
| Historical vs. Projected divider | Thick vertical border between last actual and first projected year |

---

## Number Formatting Standards

### Primary Formats

| Data Type | Format Code | Example | Notes |
|-----------|-------------|---------|-------|
| Currency (millions) | `$#,##0.0` | $125.3 | Use for all dollar amounts unless noted |
| Currency (large, rounded) | `$#,##0` | $1,234 | Use for TEV, fund sizes |
| Percentages | `0.0%` | 12.5% | One decimal standard |
| Multiples | `0.0x` | 8.5x | Entry/exit multiples, leverage |
| Counts | `#,##0` | 1,250 | Employees, customers |
| Basis points | `#,##0 "bps"` | 350 bps | Spreads, margins |
| Dates | `MMM-YY` or `FYE Dec-25` | Dec-25 | Fiscal year-end |

### Negative Number Convention

**Always use parentheses, never minus signs:**

| Correct | Incorrect |
|---------|-----------|
| ($5.0) | -$5.0 |
| (12.5%) | -12.5% |
| ($0.3x) | -0.3x |

### Sign Convention

| Item | Sign | Rationale |
|------|------|-----------|
| Revenue | Positive | Inflow |
| Expenses (COGS, SG&A) | Negative | Use parentheses on P&L |
| EBITDA | Positive | Profit metric |
| CapEx | Negative on CF | Cash outflow |
| Debt repayment | Negative on CF | Cash outflow |
| Distributions | Negative on CF | Cash outflow |

---

## Dynamic Linking Architecture

### Master Architecture Diagram

```
┌──────────────────────────────────────────────────────────────────────┐
│                        ASSUMPTIONS TAB                                │
│    (Central input repository — ALL blue-font inputs live here)       │
└──────────┬────────────┬────────────┬────────────┬───────────────────┘
           │            │            │            │
           ▼            ▼            ▼            ▼
    ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌──────────┐
    │ Revenue │  │  Debt   │  │ Returns │  │Sensitivity│
    │  Build  │  │Schedule │  │Analysis │  │  Tables   │
    └────┬────┘  └────┬────┘  └────┬────┘  └──────────┘
         │            │            │              ▲
         ▼            │            │              │
    ┌─────────┐       │            │              │
    │   P&L   │◄──────┘            │              │
    │  (OpMod)│────────────────────┘              │
    └────┬────┘                                   │
         │                                        │
         ▼                                        │
    ┌─────────┐                                   │
    │ Balance │                                   │
    │  Sheet  │                                   │
    └────┬────┘                                   │
         │                                        │
         ▼                                        │
    ┌─────────┐                                   │
    │  Cash   │───────────────────────────────────┘
    │  Flow   │
    └─────────┘
```

### Key Link Paths

| From | To | What Links |
|------|----|------------|
| Assumptions → Revenue Build | Growth rates, pricing, customer counts |
| Assumptions → Debt Schedule | Interest rates, amort schedules, covenants |
| Assumptions → Returns | Exit multiple, hold period |
| Revenue Build → P&L | Top-line revenue by segment |
| P&L → Balance Sheet | Net income → Retained earnings |
| P&L → Debt Schedule | Interest expense confirmation |
| Balance Sheet → Cash Flow | All balance sheet changes |
| Cash Flow → Debt Schedule | Cash available for debt paydown |
| Debt Schedule → Returns | Exit net debt |
| P&L + Returns → Sensitivity | Key outputs to sensitize |

### Link Naming Convention

Use named ranges for critical cross-tab references:

| Named Range | Cell | Purpose |
|-------------|------|---------|
| `Entry_EBITDA` | Assumptions!B10 | LTM EBITDA at entry |
| `Entry_Multiple` | Assumptions!B11 | EV/EBITDA entry multiple |
| `Exit_Multiple` | Assumptions!B12 | EV/EBITDA exit multiple |
| `Hold_Period` | Assumptions!B13 | Years to exit |
| `Scenario_Toggle` | Assumptions!B5 | Bull/Base/Bear selector |
| `Total_Sources` | S&U!B20 | Sum of all funding sources |
| `Total_Uses` | S&U!B30 | Sum of all uses |
| `Exit_Equity` | Returns!B15 | Equity value at exit |
| `Base_MOIC` | Returns!B18 | Base case MOIC |
| `Base_IRR` | Returns!B19 | Base case IRR |

---

## Assumptions Tab Architecture

The Assumptions tab is the **single source of truth** for all model inputs. No other tab should contain blue-font hardcoded inputs.

### Standard Layout

```
┌─────────────────────────────────────────────────────────────────┐
│ ASSUMPTIONS                                                      │
├──────────────────────────────────────────┬──────────────────────┤
│ TRANSACTION ASSUMPTIONS                  │ SCENARIO TOGGLE       │
│ Entry Date:             [Mar-26]         │ [Base ▼]             │
│ Entry EBITDA:           [$50.0M]         │                      │
│ Entry Multiple:         [8.0x]           │ SCENARIO MATRIX      │
│ Enterprise Value:       $400.0M  ← calc  │       Bull Base Bear │
│ Hold Period:            [5 years]        │ Rev Gw  12%   8%  4% │
│ Exit Multiple:          [8.0x]           │ Margin  +300 +150  +0│
│ Management Rollover:    [10%]            │ Exit Mx 9.0x 8.0x 7.0│
├──────────────────────────────────────────┤                      │
│ CAPITAL STRUCTURE                        │                      │
│ Senior Debt (TLB):      [4.0x]           │                      │
│ Subordinated:           [1.0x]           │                      │
│ Total Leverage:         5.0x     ← calc  │                      │
│ Equity Check:           $150.0M  ← calc  │                      │
├──────────────────────────────────────────┼──────────────────────┤
│ OPERATING ASSUMPTIONS                    │ DEBT TERMS            │
│ Revenue Growth (Y1-Y5): [8%]             │ TLB Rate:    [L+350] │
│ Gross Margin:           [65%]            │ TLB Amort:   [1%]    │
│ EBITDA Margin (exit):   [28%]            │ TLB Maturity:[7 yrs] │
│ CapEx (% Rev):          [3%]             │ Sub Rate:    [10%]   │
│ NWC (% Rev Δ):          [10%]            │ Sub Maturity:[8 yrs] │
│ Tax Rate:               [25%]            │ Cash Sweep:  [75%]   │
├──────────────────────────────────────────┼──────────────────────┤
│ TRANSACTION FEES                         │ COVENANT THRESHOLDS   │
│ Advisory Fee:           [1.5%]           │ Max Leverage: [6.0x] │
│ Financing Fee:          [2.0%]           │ Min Coverage: [2.0x] │
│ Legal & Other:          [$2.0M]          │                      │
└──────────────────────────────────────────┴──────────────────────┘

[Blue] = Hardcoded input    Black = Calculated    [Green] = Cross-tab link
```

### Design Principles

1. **All inputs in one place** — An analyst should be able to change any assumption without leaving this tab
2. **Scenario toggle at top** — Single dropdown that switches between Bull/Base/Bear
3. **Calculations visible** — Show key derived values (TEV, equity check) so errors are immediately apparent
4. **Grouped logically** — Transaction, capital structure, operating, fees, debt terms, covenants
5. **Documentation column** — Column to the right of each input explaining the source/rationale

---

## Cover Page Template

Every model should have a professional cover page as the first tab.

### Standard Layout

```
┌─────────────────────────────────────────────────────────────────┐
│                                                                   │
│                        [FIRM LOGO]                                │
│                                                                   │
│              ─────────────────────────────────                   │
│                                                                   │
│                    [COMPANY NAME]                                 │
│                                                                   │
│                 LBO Financial Model                               │
│                                                                   │
│              ─────────────────────────────────                   │
│                                                                   │
│  Prepared by:     [Analyst Name]                                 │
│  Date:            [Date]                                         │
│  Status:          [Draft / Final]                                │
│  Version:         [1.0 / 2.0]                                   │
│                                                                   │
│  ─────────────────────────────────────────────────────           │
│                                                                   │
│  TABLE OF CONTENTS                                               │
│  1. Assumptions .............. Key inputs & scenarios             │
│  2. Sources & Uses ........... Transaction structure              │
│  3. Operating Model .......... 5-year P&L projections            │
│  4. Balance Sheet ............ Assets, liabilities, equity       │
│  5. Cash Flow Statement ...... CFO, CFI, CFF                    │
│  6. Debt Schedule ............ Tranches, amort, covenants        │
│  7. Returns Analysis ......... MOIC, IRR, value bridge           │
│  8. Sensitivity .............. Entry/exit, growth, margins       │
│  9. Scenario Analysis ........ Bull / Base / Bear                │
│                                                                   │
│  ─────────────────────────────────────────────────────           │
│                                                                   │
│  COLOR CODING LEGEND                                             │
│  ■ Blue text    = Hardcoded inputs (change these)                │
│  ■ Black text   = Formulas (do not overwrite)                    │
│  ■ Green text   = Links to other tabs                            │
│  ■ Red text     = Error / warning flags                          │
│                                                                   │
│  ─────────────────────────────────────────────────────           │
│  CONFIDENTIAL — For internal use only                            │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
```

---

## Tab Naming & Ordering Convention

### Standard Tab Order

| Order | Tab Name | Short Name | Color |
|-------|----------|------------|-------|
| 1 | Cover | Cover | Navy |
| 2 | Assumptions | Assumptions | Yellow |
| 3 | Sources & Uses | S&U | Blue |
| 4 | Revenue Build | RevBuild | Green |
| 5 | Expense Build | ExpBuild | Green |
| 6 | Operating Model | OpModel | Green |
| 7 | Balance Sheet | BS | Green |
| 8 | Cash Flow | CF | Green |
| 9 | Working Capital | NWC | Green |
| 10 | Debt Schedule | Debt | Orange |
| 11 | Returns Analysis | Returns | Purple |
| 12 | Sensitivity | Sensitivity | Purple |
| 13 | Scenario Analysis | Scenarios | Purple |
| 14+ | Due Diligence / Other | QoE, etc. | Gray |

### Tab Color Convention

| Color | Purpose |
|-------|---------|
| **Navy** | Cover / documentation |
| **Yellow** | Inputs / assumptions |
| **Blue** | Transaction structure |
| **Green** | Financial statements |
| **Orange** | Debt-related |
| **Purple** | Returns / analysis |
| **Gray** | Supporting / appendix |

---

## Row & Column Layout Standards

### Time Axis (Columns)

```
Col A    Col B     Col C     Col D     Col E     Col F     Col G
Label    2023A     2024A     2025E     2026E     2027E     2028E
                      ↑
              Historical|Projected divider (thick border)
```

- **Column A**: Row labels (left-aligned, descriptive)
- **Columns B+**: Time periods (years or quarters)
- **"A" suffix**: Actual (historical) years
- **"E" suffix**: Estimated (projected) years
- **Thick vertical border** between last actual and first projected year

### Row Layout Pattern

```
Section Header (bold, gray background)
  Line item 1
  Line item 2
  Line item 3
──────────────────── (top border)
  Subtotal (bold)

  % margin row (italic, lighter font)

[blank row separator]

Next Section Header
  ...
```

---

## Print Setup Standards

| Setting | Value |
|---------|-------|
| Orientation | Landscape |
| Paper size | Letter (8.5" × 11") |
| Margins | 0.5" all sides |
| Scale | Fit to 1 page wide, variable pages tall |
| Header | Left: [Company Name] — Center: [Tab Name] — Right: Page X of Y |
| Footer | Left: [Draft/Final] — Center: CONFIDENTIAL — Right: [Date] |
| Gridlines | Off (use borders instead) |
| Row/column headings | Off |
| Repeat rows at top | Freeze the header row(s) |

---

## Formula Best Practices

### Do

- Use `IFERROR()` around lookups and divisions
- Use `INDEX(MATCH())` instead of `VLOOKUP()` for flexibility
- Use named ranges for key assumptions
- Use `CHOOSE()` or `INDEX()` for scenario switching
- Keep formulas readable — break complex calculations across helper rows
- Use `ROUND()` for displayed values when precision matters

### Don't

- Don't nest more than 3 levels of `IF()` — use a lookup table instead
- Don't use `INDIRECT()` — it's volatile and breaks easily
- Don't merge cells — they break copy/paste and sorting
- Don't hide rows/columns with data — use grouping instead
- Don't use array formulas (Ctrl+Shift+Enter) unless necessary

### Circular Reference Resolution

For the debt ↔ interest circularity:

**Method 1: Average Balance (Recommended)**
```
Interest_Expense = (Opening_Debt + Closing_Debt) / 2 × Rate
```
Enable iterative calculations: File → Options → Formulas → Enable iterative calculation (100 iterations, 0.001 tolerance).

**Method 2: Prior Period Balance (Simple)**
```
Interest_Expense = Opening_Debt × Rate
```
No circularity. Slightly less precise but fully acceptable.

---

*See also: `MODEL_AUDIT_CHECKLIST.md` for validation, `BEST_PRACTICES.md` for slide formatting*

*Version: 1.0.0 | Last Updated: February 2026*
