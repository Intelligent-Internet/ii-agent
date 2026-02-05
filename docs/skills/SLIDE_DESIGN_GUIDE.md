# Professional Slide Design Guide

Best practices for IB/PE/IR slide generation extracted from institutional-quality presentations.

---

## Design Principles

### 1. Visual Hierarchy
- **Title**: Large, prominent, green text (28-32pt)
- **Subtitle/Header Bar**: Gray background with white text
- **Body**: Clean 11-12pt for tables, 14pt for bullet text
- **Key Takeaway**: Green bar at bottom with italic text

### 2. Color Palette

| Element | Color | Hex |
|---------|-------|-----|
| Primary (Subject) | Green | `#00A651` |
| Secondary (Comparison) | Dark Green | `#006341` |
| Neutral (Peers) | Gray | `#808080` |
| Headers | Dark Gray | `#4A4A4A` |
| Negative Values | Red | `#C00000` |
| Positive Values | Green | `#00A651` |
| Highlight Box | Dashed Red | `#FF0000` |

### 3. Branding
- Logo in top-right corner (consistent placement)
- Slide numbers in bottom-right
- Source citations in bottom-left (8pt gray)
- Footnotes numbered with superscript

---

## Slide Layout Templates

### Template 1: Executive Summary / Introduction

**Use for:** Opening slides, key recommendations, thesis summaries

```
┌─────────────────────────────────────────────────────────────┐
│  Title (Green)                                    [LOGO]    │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ■ Main point 1 with supporting detail                      │
│    - Sub-bullet with additional context                     │
│    - Sub-bullet with data point                             │
│                                                             │
│  ■ Main point 2 with supporting detail                      │
│    - Sub-bullet                                             │
│                                                             │
│  ■ Main point 3                                             │
│    - Sub-bullet                                             │
│    - Sub-bullet                                             │
│                                                             │
│  ■ Main point 4 (recommendation or conclusion)              │
│                                                             │
├─────────────────────────────────────────────────────────────┤
│  Key takeaway message in italic on green background         │
└─────────────────────────────────────────────────────────────┘
```

**Pattern:** IPO Introduction Slide

---

### Template 2: Numbered Key Points with Detail

**Use for:** Investment highlights, strategic rationale, thesis pillars

```
┌─────────────────────────────────────────────────────────────┐
│ [1] Title: Key Point Description                  [LOGO]    │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ■ Supporting narrative text explaining the key point       │
│    with sufficient detail for standalone comprehension      │
│                                                             │
│  ■ Second supporting point with sub-bullets:                │
│    - Detail item 1                                          │
│    - Detail item 2                                          │
│    - Detail item 3                                          │
│                                                             │
│  ■ Third supporting point                                   │
│                                                             │
│ ┌─────────────────┐  ┌─────────────────┐  ┌───────────────┐ │
│ │   Chart 1       │  │   Chart 2       │  │   Chart 3     │ │
│ │   (Bar/Pie)     │  │   (Bar/Pie)     │  │   (Bar/Pie)   │ │
│ └─────────────────┘  └─────────────────┘  └───────────────┘ │
│                                                             │
├─────────────────────────────────────────────────────────────┤
│  Key takeaway reinforcing the numbered point                │
└─────────────────────────────────────────────────────────────┘
```

**Pattern:** Strategic Rationale Slide

---

### Template 3: Peer Benchmarking Bar Chart

**Use for:** Valuation multiples, financial metrics, competitive positioning

```
┌─────────────────────────────────────────────────────────────┐
│  Metric Name Benchmarking                         [LOGO]    │
├─────────────────────────────────────────────────────────────┤
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ Metric | Date Range                         (Header)    │ │
│ ├─────────────────────────────────────────────────────────┤ │
│ │                                                         │ │
│ │  23.8x  22.4x  20.2x  18.7x  18.2x  16.7x  13.8x  10.1x │ │
│ │   ▓▓▓    ▓▓▓    ▓▓▓    ▓▓▓    ▓▓▓    ▓▓▓    ▓▓▓    ███  │ │
│ │   ▓▓▓    ▓▓▓    ▓▓▓    ▓▓▓    ▓▓▓    ▓▓▓    ▓▓▓    ███  │ │
│ │   ▓▓▓    ▓▓▓    ▓▓▓    ▓▓▓    ▓▓▓    ▓▓▓    ▓▓▓    ███  │ │
│ │  ─────────────────────────────────────────────────────  │ │
│ │  Peer1  Peer2  Peer3  Peer4  Peer5  Peer6  Peer7 SUBJECT│ │
│ │  [logo] [logo] [logo] [logo] [logo] [logo] [logo] [logo]│ │
│ └─────────────────────────────────────────────────────────┘ │
│                                                             │
│  ▓▓▓ = Gray (peers)    ███ = Green (subject company)        │
│                                                             │
│  Source: Company filings, market data as of [date]          │
└─────────────────────────────────────────────────────────────┘
```

**Key Rules:**
- Sort bars by value (descending typically)
- Subject company ALWAYS in green
- Peers in gray
- Company logos below bars
- Values above bars

**Pattern:** REIT Benchmarking Slide

---

### Template 4: Comprehensive Comps Table

**Use for:** Trading comps, transaction comps, peer analysis

```
┌─────────────────────────────────────────────────────────────┐
│  Peer Comparison Title                            [LOGO]    │
├─────────────────────────────────────────────────────────────┤
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ Header Row (Gray Background)                            │ │
│ ├───────┬────────┬────────┬────────┬────────┬────────────┤ │
│ │Company│ Price  │Mkt Cap │  EV    │P/E 25E │ EV/EBITDA  │ │
│ ├───────┼────────┼────────┼────────┼────────┼────────────┤ │
│ │ Peer1 │ $XX.XX │ $X,XXX │ $X,XXX │  XX.Xx │    XX.Xx   │ │
│ │ Peer2 │ $XX.XX │ $X,XXX │ $X,XXX │  XX.Xx │    XX.Xx   │ │
│ │ Peer3 │ $XX.XX │ $X,XXX │ $X,XXX │  XX.Xx │    XX.Xx   │ │
│ ├───────┼────────┼────────┼────────┼────────┼────────────┤ │
│ │SUBJECT│ $XX.XX │ $X,XXX │ $X,XXX │  XX.Xx │    XX.Xx   │ │ ← Green row
│ ├───────┼────────┼────────┼────────┼────────┼────────────┤ │
│ │ Peer4 │ $XX.XX │ $X,XXX │ $X,XXX │  XX.Xx │    XX.Xx   │ │
│ ├───────┼────────┼────────┼────────┼────────┼────────────┤ │
│ │Average│   -    │   -    │   -    │  XX.Xx │    XX.Xx   │ │ ← Bold row
│ └───────┴────────┴────────┴────────┴────────┴────────────┘ │
│                                                             │
│  Source: Company filings as of [date]                       │
└─────────────────────────────────────────────────────────────┘
```

**Key Rules:**
- Company logos in first column
- Subject row highlighted with green background
- Peer average/median at bottom
- Negative values in parentheses and red
- Consistent decimal places per column

**Pattern:** Multi-Residential Comps Slide

---

### Template 5: Time Series Line Chart

**Use for:** Historical performance, price trends, multiple comparison

```
┌─────────────────────────────────────────────────────────────┐
│  Performance Comparison Title                     [LOGO]    │
├─────────────────────────────────────────────────────────────┤
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ Metric | Date Range                         (Header)    │ │
│ ├─────────────────────────────────────────────────────────┤ │
│ │                                              ┌────────┐ │ │
│ │  60%                                    ╱╲   │Summary │ │ │
│ │                                        ╱  ╲  │Table   │ │ │
│ │  40%                              ╱╲  ╱    ╲ │        │ │ │
│ │                               ╱╲ ╱  ╲╱      │        │ │ │
│ │  20%           ╱╲            ╱  ╲           └────────┘ │ │
│ │          ╱╲   ╱  ╲   ╱╲    ╱                           │ │
│ │    ─────╱  ╲─╱    ╲─╱  ╲──╱                            │ │
│ │   0%                                                    │ │
│ │  ─────────────────────────────────────────────────────  │ │
│ │   2020    2021    2022    2023    2024    2025          │ │
│ ├─────────────────────────────────────────────────────────┤ │
│ │  ─── Subject (Green): XX%  ─── Peer (Gray): XX%         │ │
│ └─────────────────────────────────────────────────────────┘ │
│                                                             │
├─────────────────────────────────────────────────────────────┤
│  Key insight about the trend                                │
└─────────────────────────────────────────────────────────────┘
```

**Key Rules:**
- Subject line in green, thicker weight
- Peers/comparisons in gray
- Optional: Small summary table overlay
- Event annotations with callout boxes
- Legend at bottom with cumulative returns

**Pattern:** Price Performance / Multiple Expansion Slide

---

### Template 6: Before/After Comparison

**Use for:** Value creation, renovations, pro forma analysis

```
┌─────────────────────────────────────────────────────────────┐
│  Value-Add / Transformation Title                 [LOGO]    │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ■ Narrative explaining the transformation strategy         │
│                                                             │
│  ┌──────────────────┐    ┌──────────────────────────────┐   │
│  │  KPI Grid        │    │  Metric 1  │  Metric 2      │   │
│  │  ┌──────┬──────┐ │    │  $X,XXX    │  +$XXX         │   │
│  │  │Cost  │Uplift│ │    ├────────────┼────────────────┤   │
│  │  │$5K   │+$400 │ │    │  Payback   │  Value Added   │   │
│  │  ├──────┼──────┤ │    │  1-Year    │  +$68,500      │   │
│  │  │Pybck │ROI   │ │    └────────────┴────────────────┘   │
│  │  │1 Yr  │96%   │ │                                       │
│  │  └──────┴──────┘ │                                       │
│  └──────────────────┘                                       │
│                                                             │
│  ┌─────────────────────────────────────────────────────────┐│
│  │ Case Study: [Property Name]                             ││
│  ├─────────────────────────────────────────────────────────┤│
│  │  ┌─────────┐  ┌─────────┐  │ Metric    │Before│After│Δ ││
│  │  │ Before  │  │ After   │  │ Revenue   │$2,780│$5,087│83%│
│  │  │ [Photo] │  │ [Photo] │  │ Rent      │$2,780│$3,395│22%│
│  │  └─────────┘  └─────────┘  │ Care Rev  │  -   │$1,692│n/a│
│  └─────────────────────────────────────────────────────────┘│
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

**Key Rules:**
- Photos side-by-side for visual proof
- Data table quantifying the improvement
- KPI summary boxes with key metrics
- Green for positive changes

**Pattern:** Value-Add Strategy Slide

---

### Template 7: Sources & Uses / Transaction Summary

**Use for:** Deal structure, IPO analysis, M&A transactions

```
┌─────────────────────────────────────────────────────────────┐
│  Transaction Analysis Title                       [LOGO]    │
├─────────────────────────────────────────────────────────────┤
│ ┌─────────────────────────┐  ┌────────────────────────────┐ │
│ │ Valuation Summary       │  │ Sources & Uses             │ │
│ ├─────────────────────────┤  ├────────────────────────────┤ │
│ │            Low Mid High │  │ Sources        Low Mid High│ │
│ │ AFFO      $22  $22  $22 │  │ Equity Issue  $125 $138 $150│
│ │ Multiple  13.5x14.5x15.5│  │ Retained Int  $142 $150 $157│
│ │ Eq Value  $297 $319 $341│  │ Portfolio Debt$282 $282 $282│
│ │ + Net Debt$234 $234 $234│  │ Total Sources $549 $569 $589│
│ │ = EV      $502 $521 $541│  ├────────────────────────────┤ │
│ ├─────────────────────────┤  │ Uses          Low Mid High │
│ │ Implied Metrics:        │  │ Purchase Price$488 $507 $526│
│ │ P/FFO    10.9x11.7x12.5x│  │ Transaction   $14  $14  $15 │
│ │ P/AFFO   12.2x13.1x14.0x│  │ Debt Repay    $47  $47  $47 │
│ │ Cap Rate  8.1% 7.8% 7.5%│  │ Total Uses    $549 $569 $589│
│ └─────────────────────────┘  └────────────────────────────┘ │
│                                                             │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ Cash Flow Summary                             2026E     │ │
│ ├─────────────────────────────────────────────────────────┤ │
│ │ NOI                                           $45.9     │ │
│ │ Less: Management Fee                          ($5.4)    │ │
│ │ Less: G&A                                     ($3.6)    │ │
│ │ EBITDA                                        $35.4     │ │
│ │ Less: Interest                               ($10.9)    │ │
│ │ FFO                                           $24.5     │ │
│ └─────────────────────────────────────────────────────────┘ │
│                                                             │
│  Source: Management, SNL                                    │
└─────────────────────────────────────────────────────────────┘
```

**Key Rules:**
- Multiple tables arranged in logical flow
- Low/Mid/High scenarios in columns
- Color-coded headers (gray, green, tan)
- Totals rows highlighted
- Clear separation between sections

**Pattern:** IPO Analysis Slide

---

### Template 8: Scenario Analysis (Data-Dense)

**Use for:** Disposition analysis, strategic alternatives, complex transactions

```
┌─────────────────────────────────────────────────────────────┐
│  Scenario X: Transaction Description              [LOGO]    │
├─────────────────────────────────────────────────────────────┤
│  ■ Key assumption 1 with quantified detail                  │
│  ■ Key assumption 2 with implications                       │
│                                                             │
│ ┌──────────────────┐ ┌────────────────────────────────────┐ │
│ │ Before   After   │ │ Capitalization                     │ │
│ │   ┌───┐   ┌───┐  │ │                 Current  Adj   PF  │ │
│ │   │20%│   │15%│  │ │ Unit Price      $17.04  -    $17.04│ │
│ │   │   │   │   │  │ │ Market Cap      $614.5  -    $611.1│ │
│ │   │31%│   │29%│  │ │ + Net Debt     $1,686  ($724) $962 │ │
│ │   │   │ ╱╲│   │  │ │ = EV          $2,301  ($724)$1,574│ │
│ │   │39%│╱  ╲56%│  │ │ Debt/GBV        63.9%   -    51.3% │ │
│ │   └───┘    └───┘ │ │ Implied Cap     7.19%   -    6.43% │ │
│ │ $161M     $97M   │ └────────────────────────────────────┘ │
│ │  NOI       NOI   │                                        │
│ └──────────────────┘ ┌────────────────────────────────────┐ │
│                      │ Accretion / Dilution               │ │
│ ┌──────────────────┐ │ In-Place NOI            ($64.1)    │ │
│ │ Sources & Uses   │ │ + Mgmt Fee Income         -        │ │
│ │ Sources:   $756  │ │ + G&A Savings            $1.4      │ │
│ │ Uses:      $756  │ │ + Interest Savings      $35.4      │ │
│ │                  │ │ = Incr. FFO            ($27.3)     │ │
│ │ - Debt     $388  │ │ + Capex Savings          $4.8      │ │
│ │ - Credit   $248  │ │ = Incr. AFFO           ($22.5)     │ │
│ │ - Other     $88  │ │                                    │ │
│ │ - Buyback   $4   │ │ AFFO/Unit: $1.69 → $1.07 (-36.7%)  │ │
│ │ - Costs     $28  │ └────────────────────────────────────┘ │
│ └──────────────────┘                                        │
│                                                             │
│  Source: Company, Market data                               │
└─────────────────────────────────────────────────────────────┘
```

**Key Rules:**
- Multiple coordinated data tables
- Donut charts for composition changes
- Clear before/after narrative
- Accretion/dilution analysis
- Color-coded positive (green) / negative (red) impacts

**Pattern:** Scenario Analysis Slide

---

### Template 9: Horizontal Bar Chart with Annotations

**Use for:** Rankings, market exposure, geographic distribution

```
┌─────────────────────────────────────────────────────────────┐
│  Ranking / Exposure Title                         [LOGO]    │
├─────────────────────────────────────────────────────────────┤
│  ■ Context statement about the ranking                      │
│                                                             │
│ ┌────────────────────────────────────┐  ┌─────────────────┐ │
│ │ Metric by Category | Period        │  │ Exposure Chart  │ │
│ ├────────────────────────────────────┤  │    ┌─────┐      │ │
│ │ City 1         ████████████  23.7% │  │    │ 12% │ Top  │ │
│ │ City 2 [#1 in Region] ██████ 21.3% │  │    ├─────┤      │ │
│ │ City 3         ████████       19.5% │  │    │ 88% │Other│ │
│ │ City 4 [#1 in Province] ████ 18.3% │  │    └─────┘      │ │
│ │ City 5         █████████     18.3% │  │                 │ │
│ │ City 6         ███████       17.3% │  │    ┌─────┐      │ │
│ │ City 7         ██████        16.9% │  │    │ 15% │ Top  │ │
│ │ City 8         ██████        16.9% │  │    ├─────┤      │ │
│ │ City 9 [#4 in Ontario] ████  16.9% │  │    │ 85% │Other│ │
│ │ City 10        █████         16.5% │  │    └─────┘      │ │
│ └────────────────────────────────────┘  └─────────────────┘ │
│                                                             │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ Key takeaway about portfolio exposure                   │ │
│ └─────────────────────────────────────────────────────────┘ │
│                                                             │
│  ███ = Subject Portfolio Exposure                           │
│  Source: Statistics Canada                                  │
└─────────────────────────────────────────────────────────────┘
```

**Key Rules:**
- Horizontal bars sorted by value
- Annotation callouts for notable items
- Companion pie/donut charts for context
- Green bars for subject company metrics
- Clear legend and source

**Pattern:** Market Exposure / Growth Cities Slide

---

### Template 10: Gantt Chart / Timeline

**Use for:** Transaction timeline, IPO process, project phases

```
┌─────────────────────────────────────────────────────────────┐
│  Process Timeline Title                           [LOGO]    │
├─────────────────────────────────────────────────────────────┤
│  ■ Context about timing rationale                           │
│  ■ Key milestone or deadline                                │
│                                                             │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ Illustrative Timeline                                   │ │
│ ├───────────────────────────────────────────────────────┬─┤ │
│ │           │ Q1  │ Q2  │ Q3  │ Q4  │ Q1  │ Milestone   │ │
│ ├───────────┼─────┼─────┼─────┼─────┼─────┼─────────────┤ │
│ │ Planning  │████ │     │     │     │     │             │ │
│ │ Appraisals│████ │████ │     │     │     │             │ │
│ │ Diligence │     │████ │████ │████ │     │             │ │
│ │ Structure │     │     │████ │████ │     │             │ │
│ │ Prospectus│     │     │     │████ │████ │             │ │
│ │ Marketing │     │     │     │     │████ │             │ │
│ │ Filing    │     │     │     │     │████ │ ┌─────────┐ │ │
│ │ TTW Mtgs  │     │     │     │     │████ │ │ Launch: │ │ │
│ │           │     │     │     │     │     │ │  Q4/25  │ │ │
│ │           │     │     │     │     │     │ └─────────┘ │ │
│ └───────────┴─────┴─────┴─────┴─────┴─────┴─────────────┘ │
│                                                             │
│  Source: Management estimates                               │
└─────────────────────────────────────────────────────────────┘
```

**Key Rules:**
- Green bars for work phases
- Tan/beige highlight for key milestones
- Milestone callout box
- Clear time axis (months or quarters)
- Workstreams listed vertically

**Pattern:** IPO Timeline Slide

---

### Template 11: Heat Map / Performance Matrix

**Use for:** Annual returns by strategy, risk ratings, scoring matrices

```
┌─────────────────────────────────────────────────────────────┐
│  Performance Matrix Title                         [LOGO]    │
├─────────────────────────────────────────────────────────────┤
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ Metric by Year                                    Avg   │ │
│ ├──────────┬──────┬──────┬──────┬──────┬──────┬──────────┤ │
│ │          │ 2020 │ 2021 │ 2022 │ 2023 │ 2024 │ 5-Yr IRR │ │
│ ├──────────┼──────┼──────┼──────┼──────┼──────┼──────────┤ │
│ │Strategy 1│ 17.1%│ 21.3%│ 31.4%│ 13.0%│ 12.4%│   15.8%  │ │
│ │          │  ██  │  ██  │  ██  │  ▓▓  │  ▓▓  │    ██    │ │
│ ├──────────┼──────┼──────┼──────┼──────┼──────┼──────────┤ │
│ │Strategy 2│ 14.9%│ 18.8%│ 20.3%│ 12.5%│ 10.8%│   15.4%  │ │
│ │          │  ▓▓  │  ██  │  ██  │  ▓▓  │  ░░  │    ██    │ │
│ ├──────────┼──────┼──────┼──────┼──────┼──────┼──────────┤ │
│ │Strategy 3│  7.1%│ (2.8)│ 12.1%│  8.0%│ (8.2)│    7.9%  │ │
│ │          │  ░░  │  ▒▒  │  ▓▓  │  ░░  │  ▒▒  │    ░░    │ │
│ └──────────┴──────┴──────┴──────┴──────┴──────┴──────────┘ │
│                                                             │
│  Color Scale: ██ Dark Green (>20%) → ▓▓ Green (10-20%)     │
│               ░░ Light Green (0-10%) → ▒▒ Red (<0%)        │
│                                                             │
├─────────────────────────────────────────────────────────────┤
│  Key insight about performance trends                       │
└─────────────────────────────────────────────────────────────┘
```

**Key Rules:**
- Conditional formatting by value
- Dark green = best, red = worst
- Strategy labels in first column
- Summary metric (avg/IRR) in final column
- Clear color scale legend

**Pattern:** Annual Returns Heat Map Slide

---

### Template 12: Portfolio Valuations Table

**Use for:** Portfolio company summary, fund investments, exit forecasts

```
┌─────────────────────────────────────────────────────────────┐
│  Portfolio Summary Title                          [LOGO]    │
├─────────────────────────────────────────────────────────────┤
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ Portfolio │ Current Valuation  │ Expected Exit Values  │ │
│ │ Company   ├──────┬──────┬──────┼──────┬──────┬─────────┤ │
│ │           │Invest│ MOIC │ IRR  │ Date │ MOIC │   IRR   │ │
│ ├───────────┼──────┼──────┼──────┼──────┼──────┼─────────┤ │
│ │ [Logo] A  │$28.6m│ 2.00x│ 39.7%│H1'27 │┌────┐│ 28-34%  │ │
│ │           │      │      │      │      ││2.5-││         │ │
│ │           │      │      │      │      ││3.0x││         │ │
│ │           │      │      │      │      │└────┘│         │ │
│ ├───────────┼──────┼──────┼──────┼──────┼──────┼─────────┤ │
│ │ [Logo] B  │$27.2m│ 1.60x│ 87.5%│ 2028 │┌────┐│ 26-32%  │ │
│ │           │      │      │      │      ││2.5-││         │ │
│ │           │      │      │      │      ││3.0x││         │ │
│ │           │      │      │      │      │└────┘│         │ │
│ └───────────┴──────┴──────┴──────┴──────┴──────┴─────────┘ │
│                                                             │
│  ┌────┐ = Dashed red box highlighting forecast range        │
│  └────┘                                                     │
│                                                             │
├─────────────────────────────────────────────────────────────┤
│  Key takeaway about portfolio positioning                   │
└─────────────────────────────────────────────────────────────┘
```

**Key Rules:**
- Company logos in first column
- Current metrics vs. expected exit
- Dashed red boxes for forecast ranges
- Clean column headers with sections
- Key takeaway at bottom

**Pattern:** Portfolio Valuations Slide

---

### Template 13: Geographic Map

**Use for:** Property locations, market presence, regional concentration

```
┌─────────────────────────────────────────────────────────────┐
│  Geographic Title                                 [LOGO]    │
├─────────────────────────────────────────────────────────────┤
│ ┌──────────────────┐                                        │
│ │ Summary Stats    │         ┌─────────────────────────┐    │
│ │ ┌──────┬───────┐ │         │                         │    │
│ │ │Props │ SF    │ │         │    [MAP WITH MARKERS]   │    │
│ │ │  49  │ 2.6M  │ │         │                         │    │
│ │ │  78  │ 6.4M  │ │         │   ● ●  ●                │    │
│ │ └──────┴───────┘ │         │     ●●   ●              │    │
│ │  Gray   Green    │         │  ●    ●●●●●             │    │
│ │  Peer  Subject   │         │           ●●●           │    │
│ └──────────────────┘         │                         │    │
│                              └─────────────────────────┘    │
│                                                             │
│  Legend:                                                    │
│  ● Subject (Green)    Size: ● Small  ● Medium  ● Large     │
│  ● Comparison (Gray)                                        │
│  ─ Transit Lines                                            │
│                                                             │
│  Source: Company data                                       │
└─────────────────────────────────────────────────────────────┘
```

**Key Rules:**
- Size-coded markers for scale
- Color-coded for ownership/type
- Small comparison chart in corner
- Clear legend
- Infrastructure/context overlay (transit, highways)

**Pattern:** Geographic Market Map Slide

---

### Template 14: Debt Structure Benchmarking

**Use for:** Capital structure comparison, credit profile, leverage analysis

```
┌─────────────────────────────────────────────────────────────┐
│  Debt Structure Comparison Title                  [LOGO]    │
├─────────────────────────────────────────────────────────────┤
│  ■ Key observation about debt structure                     │
│  ■ Implication for subject company                          │
│                                                             │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ Debt Benchmarking ($M)                                  │ │
│ ├───────────────────┬─────────────┬─────────────┬─────────┤ │
│ │                   │  [Logo] A   │  [Logo] B   │ [Logo]C │ │
│ │                   │ Val │ % Tot │ Val │ % Tot │Val│%Tot │ │
│ ├───────────────────┼─────┼───────┼─────┼───────┼───┼─────┤ │
│ │ CMHC Insured      │$1,631│ 49.6%│ $598│ 47.1% │$30│12.7%│ │
│ │ Non-CMHC Insured  │ $358│ 10.9%│ $189│ 14.9% │$205│87.3%│ │
│ │ Unsecured Deb     │ $950│ 28.9%│ $450│ 35.4% │ - │  -  │ │
│ │ Term Loan         │ $149│  4.5%│   - │   -   │ - │  -  │ │
│ │ Credit Facility   │ $190│  5.8%│  $30│  2.4% │ - │  -  │ │
│ ├───────────────────┼─────┼───────┼─────┼───────┼───┼─────┤ │
│ │ Total Debt        │$3,286│100.0%│$1,270│100.0%│$234│100%│ │
│ ├───────────────────┼─────┼───────┼─────┼───────┼───┼─────┤ │
│ │ Credit Capacity   │ $400│ 12.2%│ $309│ 24.3% │$65│27.7%│ │
│ │ Undrawn Capacity  │ $210│  6.4%│ $309│ 24.3% │$65│27.7%│ │
│ └───────────────────┴─────┴───────┴─────┴───────┴───┴─────┘ │
│                                                             │
│  Source: Company filings as of [date]                       │
└─────────────────────────────────────────────────────────────┘
```

**Key Rules:**
- Company logos as column headers
- Value and % of Total for each
- Totals row highlighted
- Additional metrics section below
- Consistent decimal formatting

**Pattern:** Debt Benchmarking Slide

---

## Formatting Standards

### Numbers and Currency

| Type | Format | Example |
|------|--------|---------|
| Currency (M) | $X,XXX.X | $1,234.5 |
| Currency (K) | $XXX | $850 |
| Multiples | X.Xx | 12.5x |
| Percentages | X.X% | 8.5% |
| Negative | (X.X) or -X.X | (2.3%) |
| Large numbers | X.XB / X.XM | $2.3B |

### Text Styles

| Element | Font Size | Weight | Color |
|---------|-----------|--------|-------|
| Slide Title | 28-32pt | Bold | Green |
| Section Header | 14-16pt | Bold | Dark Gray |
| Body Text | 11-12pt | Regular | Black |
| Table Text | 10-11pt | Regular | Black |
| Footnotes | 8pt | Regular | Gray |
| Key Takeaway | 12-14pt | Italic | White on Green |

### Table Formatting

- **Header rows**: Gray or green background, white text
- **Data rows**: Alternating white/light gray
- **Subject row**: Green background highlight
- **Totals row**: Bold, light gray background
- **Column alignment**: Right-align numbers, left-align text
- **Decimal consistency**: Same decimal places within column

---

## Chart Best Practices

### Bar Charts

1. **Subject highlighting**: Always green for subject company
2. **Sorting**: By value (descending) or logical order
3. **Data labels**: Above bars for clarity
4. **Company logos**: Below bars when space permits
5. **Value axis**: Start at zero unless log scale needed

### Line Charts

1. **Subject line**: Green, thicker weight (2-3pt)
2. **Comparison lines**: Gray, thinner weight (1pt)
3. **Annotations**: Callout boxes for key events
4. **Legend**: Below chart with cumulative returns
5. **Time axis**: Clear date labels

### Pie/Donut Charts

1. **Segments**: Maximum 5-6 for clarity
2. **Labels**: Inside or adjacent with leader lines
3. **Color scheme**: Green gradient for subject, gray for others
4. **Emphasis**: "Exploded" segment for key item

---

## Source Citations

### Standard Format

```
Source: [Primary Source], [Secondary Source] as of [Date]
Note: [Specific assumptions or clarifications]
1. [Numbered footnote for specific data point]
```

### Common Sources

- Company Filings / Company Disclosure
- Market data as of [Date]
- Management provided forecasts
- SNL (for real estate data)
- Statistics Canada / StatCan
- Capital IQ
- Bloomberg

---

## Key Takeaway Guidelines

The green bar at the bottom should:

1. **Summarize** the slide's main insight in one sentence
2. **Use italics** for emphasis
3. **Be actionable** or conclusive
4. **Reference** specific data when possible

**Examples:**
- "Senior Housing has seen the strongest share price appreciation since 2021, driven by rapidly improving fundamentals"
- "We have strategically deployed more capital into our best investments"
- "Pro forma, the combined entity has superior scale and financial flexibility"

---

## Infrastructure Investor Day Templates

*Additional patterns extracted from institutional infrastructure investor day presentations.*

### Template 15: Mission Statement / Strategic Focus

**Use for:** Opening thesis, fund strategy, investment philosophy

```
┌─────────────────────────────────────────────────────────────┐
│                                                   [LOGO]    │
│                                                             │
│                                                             │
│                                                             │
│          Our mission is to own highly                       │
│          contracted and regulated businesses                │
│          that generate long-term, consistent                │
│          growth with minimal variability                    │
│                                                             │
│          If executed well, this will lead to                │
│          annual FFO per unit growth of 10%+                 │
│                                                             │
│                                                             │
│                                                             │
│                                                     PAGE #  │
└─────────────────────────────────────────────────────────────┘
```

**Key Rules:**
- Centered, large text (24-28pt)
- Minimal design, maximum impact
- Key metric highlighted
- Clean white space

**Pattern:** Mission Statement Slide

---

### Template 16: 4-Quadrant Achievement Summary

**Use for:** Year in review, strategic accomplishments, quarterly highlights

```
┌─────────────────────────────────────────────────────────────┐
│  2025 has been an excellent year for [Company]    [LOGO]    │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────────┐      ┌─────────────────┐               │
│  │    Executed     │      │    Delivered    │               │
│  │    strategic    │      │     record      │               │
│  │   priorities    │      │financial results│               │
│  └─────────────────┘      └─────────────────┘               │
│                                                             │
│  ┌─────────────────┐      ┌─────────────────┐               │
│  │  Maintained a   │      │    Advanced     │               │
│  │ strong balance  │      │  several ESG    │               │
│  │     sheet       │      │   priorities    │               │
│  └─────────────────┘      └─────────────────┘               │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

**Key Rules:**
- Four boxes in 2x2 grid
- Brief, punchy text (3-5 words each)
- Consistent box sizing
- No data overload

**Pattern:** Year in Review Slide

---

### Template 17: Track Record Line Chart with CAGR

**Use for:** Historical FFO growth, distribution history, performance trends

```
┌─────────────────────────────────────────────────────────────┐
│  Long-term track record for cash flow growth      [LOGO]    │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│                                          14%        $3.32   │
│                                                    ╱        │
│                                         FFO per   ╱         │
│                                          unit   ╱           │
│                                          CAGR ╱             │
│                                              ╱              │
│                                            ╱                │
│                                          ╱                  │
│                                        ╱                    │
│                              ╱────────╱                     │
│                    ╱────────╱                               │
│  $0.42  ──────────╱                                         │
│  ─────────────────────────────────────────────────────────  │
│  2009   2011   2013   2015   2017   2019   2021   2023  2025│
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

**Key Rules:**
- CAGR annotation prominently displayed
- Start and end values labeled
- Clean timeline axis
- Single metric focus per chart

**Pattern:** FFO Track Record Slide

---

### Template 18: 3-Pillar Strategy Flow

**Use for:** Business strategy, investment approach, value creation framework

```
┌─────────────────────────────────────────────────────────────┐
│  Our full-cycle business strategy entails:        [LOGO]    │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────────┐  ┌─────────────────┐  ┌──────────────┐ │
│  │                 │  │                 │  │              │ │
│  │   Deploy        │  │  Crystalize     │  │  Maintain a  │ │
│  │   capital at    │→→│  value through  │→→│    strong    │ │
│  │   or above      │  │    capital      │  │  financial   │ │
│  │   12-15%        │  │   recycling     │  │   position   │ │
│  │   target        │  │                 │  │              │ │
│  │   returns       │  │                 │  │              │ │
│  │                 │  │                 │  │              │ │
│  └─────────────────┘  └─────────────────┘  └──────────────┘ │
│                                                             │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

**Key Rules:**
- Three equal-width boxes
- Arrow connectors showing flow
- Brief descriptive text
- Consistent visual weight

**Pattern:** Strategy Framework Slide

---

### Template 19: Exit Strategy Summary Grid

**Use for:** Asset sales recap, capital recycling summary, realized returns

```
┌─────────────────────────────────────────────────────────────┐
│  This year's exits generated strong results       [LOGO]    │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────────────────────────────────────────────────┐│
│  │ Transaction   │Exit Strategy│Proceeds│ IRR  │   MoC    ││
│  ├───────────────┼─────────────┼────────┼──────┼──────────┤│
│  │ [Logo] Deal A │ Full exit   │  $480M │  17% │   3.6x   ││
│  │ [Logo] Deal B │ Partial sale│  $430M │  19% │   7.5x   ││
│  │ [Logo] Deal C │ Partial sale│  $390M │  18% │   2.9x   ││
│  │ [Logo] Deal D │Staged exit  │  $580M │  22% │   3.8x   ││
│  │ [Logo] Deal E │Public market│  $620M │  25% │   1.6x   ││
│  ├───────────────┼─────────────┼────────┼──────┼──────────┤│
│  │ TOTAL         │   Various   │ ~$2.8B │ ~20% │   4.0x   ││
│  └───────────────┴─────────────┴────────┴──────┴──────────┘│
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

**Key Rules:**
- Company/deal logos in first column
- Exit strategy type indicated
- IRR and MoC for each exit
- Total/average row at bottom

**Pattern:** Capital Recycling Summary Slide

---

### Template 20: Investment Checklist / Rules Alignment

**Use for:** Investment criteria validation, deal screening, due diligence summary

```
┌─────────────────────────────────────────────────────────────┐
│  Checks all the boxes for a value-based investment [LOGO]   │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Attractive entry point           ~10x run-rate EBITDA      │
│  ──────────────────────────────────────────────────────     │
│  Quick payback period             Less than eight years     │
│  ──────────────────────────────────────────────────────     │
│  Robust cash yield                13% going-in FFO yield    │
│                                   16%+ run-rate FFO yield   │
│  ──────────────────────────────────────────────────────     │
│  Conservative capital structure   Investment-grade balance  │
│  ──────────────────────────────────────────────────────     │
│  Large-scale transaction          ~$2.5 billion investment  │
│  ──────────────────────────────────────────────────────     │
│  Customer quality                 97% from IG customers     │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

**Key Rules:**
- Criteria on left, validation on right
- Horizontal dividers between rows
- Quantified evidence for each criterion
- Clean two-column layout

**Pattern:** Investment Criteria Checklist Slide

---

### Template 21: Macro Themes / Super Cycle Drivers

**Use for:** Market tailwinds, sector thesis, thematic overview

```
┌─────────────────────────────────────────────────────────────┐
│  The infrastructure super-cycle is playing out    [LOGO]    │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌───────────┐  ┌───────────┐  ┌───────────┐  ┌───────────┐│
│  │  [Icon]   │  │  [Icon]   │  │  [Icon]   │  │  [Icon]   ││
│  │           │  │           │  │           │  │           ││
│  │Sovereign &│  │   Data    │  │ Midstream │  │ Transport ││
│  │ corporate │  │ infra in  │  │  sector   │  │  assets   ││
│  │   debt    │  │ need of   │  │ requires  │  │ critically││
│  │  rising   │  │ upgrade   │  │  capital  │  │bottleneck ││
│  │           │  │           │  │           │  │           ││
│  │• Govt debt│  │• 30% data │  │• Scarcity │  │• Minimal  ││
│  │  rising   │  │  growth   │  │  value    │  │  capacity ││
│  │• $1.2T US │  │• 100-year │  │• Net zero │  │• Travel   ││
│  │  infra    │  │  upgrade  │  │  support  │  │  hindered ││
│  │  plan     │  │  cycle    │  │           │  │           ││
│  └───────────┘  └───────────┘  └───────────┘  └───────────┘│
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

**Key Rules:**
- 4 equal columns with icons
- Theme title in bold
- 2-3 supporting bullet points each
- Consistent visual treatment

**Pattern:** Macro Themes / Super Cycle Slide

---

### Template 22: Debt Maturity Profile

**Use for:** Refinancing schedule, maturity wall, credit analysis

```
┌─────────────────────────────────────────────────────────────┐
│  Strong Financial Position                        [LOGO]    │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Recourse Debt Summary                                      │
│  Outstanding:        ~$4.2 billion                          │
│  Average Rate:       5.0%                                   │
│  Average Term:       14 Years                               │
│                                                             │
│                               ┌───┐                         │
│                               │   │                         │
│                               │   │ $2.5B                   │
│                               │   │                         │
│  ┌───┐ ┌───┐ ┌───┐ ┌───┐     │   │                         │
│  │$0.3│ │$0.5│ │$0.5│ │$0.4│     │   │                         │
│  └───┘ └───┘ └───┘ └───┘     └───┘                         │
│  2026  2027  2028  2029  2030  Beyond                       │
│                                                             │
│  ~$3B           90%              90%                        │
│  Corporate   Non-recourse     Fixed-rate                    │
│  liquidity       debt            debt                       │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

**Key Rules:**
- Bar chart showing maturities by year
- Key metrics summarized above
- "Beyond" bucket for long-dated debt
- Supporting metrics in boxes below

**Pattern:** Financial Position / Debt Maturity Slide

---

### Template 23: Value Creation Bridge / FFO Growth Drivers

**Use for:** Organic growth attribution, return decomposition, performance drivers

```
┌─────────────────────────────────────────────────────────────┐
│  Illustrative Organic Value Creation: FFO Growth  [LOGO]    │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌───────┐   ┌───────┐   ┌───────┐       ┌───────────────┐ │
│  │       │   │       │   │       │       │               │ │
│  │ 3-4%  │ + │ 1-2%  │ + │ 2-3%  │   =   │     6-9%      │ │
│  │       │   │       │   │       │       │               │ │
│  │       │   │       │   │       │       │ Organic Growth│ │
│  └───────┘   └───────┘   └───────┘       └───────────────┘ │
│  Inflation      GDP      Reinvested                         │
│                          Capital                            │
│                                                             │
│                                                             │
│  ┌─────────────────────────────────────────────────────────┐│
│  │                 10%+                                    ││
│  │            FFO per unit                                 ││
│  │           growth target                                 ││
│  └─────────────────────────────────────────────────────────┘│
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

**Key Rules:**
- Additive components with + signs
- Result box larger/highlighted
- Labels below each component
- Target metric prominently displayed

**Pattern:** Organic Growth Attribution Slide

---

### Template 24: Platform / Business Unit Overview

**Use for:** Segment overview, business unit summary, portfolio composition

```
┌─────────────────────────────────────────────────────────────┐
│  Essential Infrastructure Diversified Across Sectors [LOGO] │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│    Utilities         Transport        Midstream      Data   │
│   ┌─────────┐       ┌─────────┐      ┌─────────┐  ┌───────┐│
│   │   25%   │       │   37%   │      │   22%   │  │  16%  ││
│   │   FFO   │       │   FFO   │      │   FFO   │  │  FFO  ││
│   └─────────┘       └─────────┘      └─────────┘  └───────┘│
│                                                             │
│   8%  17%            12% 19%           [pie]       6%  10% │
│   [pie chart]        6%  [pie]                     [pie]   │
│                                                             │
│  ───────────────────────────────────────────────────────── │
│  Regulated           Rail              Energy      Data    │
│  Transmission        Diversified       Transport   Transmit│
│  Commercial &        Terminals         Storage &   Data    │
│  Residential         Toll Roads        Processing  Storage │
│  Distribution                                              │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

**Key Rules:**
- 4 sectors with % of FFO
- Mini pie charts showing sub-segment mix
- Sector labels and descriptions below
- Consistent visual hierarchy

**Pattern:** Asset Class / Segment Overview Slide

---

### Template 25: Deal Showcase Grid

**Use for:** Recent transactions, deployment summary, acquisition highlights

```
┌─────────────────────────────────────────────────────────────┐
│  Over $22 billion of marquee transactions this year [LOGO]  │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Sector:    Midstream      Data        Transport   Utilities│
│  Type:      Value-based    Platform    Partnership Carve-out│
│                                                             │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────────────┐ │
│  │ [Logo]  │  │ [Logo]  │  │ [Logo]  │  │     [Logo]      │ │
│  │         │  │         │  │         │  │                 │ │
│  │ Deal A  │  │ Deal B  │  │ Deal C  │  │     Deal D      │ │
│  │         │  │         │  │         │  │                 │ │
│  │EV: $9.1B│  │EV: $6.9B│  │EV: $5.3B│  │   EV: $1.0B     │ │
│  │Jul 2025 │  │Sep 2025 │  │Q1 2026  │  │   Q4 2025       │ │
│  └─────────┘  └─────────┘  └─────────┘  └─────────────────┘ │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

**Key Rules:**
- Sector and deal type labels above
- Company logos prominently displayed
- Enterprise value for each
- Closing date/status

**Pattern:** Marquee Transactions Showcase Slide

---

### Template 26: Investment Perimeter Evolution

**Use for:** Capability expansion, opportunity set growth, strategy evolution

```
┌─────────────────────────────────────────────────────────────┐
│  Evolution of our investment opportunity set      [LOGO]    │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│         10 Years Ago        5 Years Ago         Today       │
│  ┌───────────────────┬───────────────────┬─────────────────┐│
│  │Transport          │Transport          │Transport        ││
│  │ • Ports           │ • Ports           │ • Ports         ││
│  │ • Toll roads      │ • Toll roads      │ • Toll roads    ││
│  │ • Rail            │ • Rail            │ • Rail          ││
│  │                   │                   │ • Container     ││
│  │                   │                   │ • Railcar       ││
│  ├───────────────────┼───────────────────┼─────────────────┤│
│  │Midstream          │Midstream          │Midstream        ││
│  │ • Gas pipelines   │ • Gas pipelines   │ • Gas pipelines ││
│  │                   │ • LNG             │ • LNG           ││
│  │                   │ • Liquids         │ • Liquids       ││
│  │                   │                   │ • Industrial gas││
│  ├───────────────────┼───────────────────┼─────────────────┤│
│  │Data               │Data               │Data             ││
│  │ • Towers          │ • Towers          │ • Towers        ││
│  │                   │ • Colocation DCs  │ • AI/Hyperscale ││
│  │                   │ • FTTH            │ • Semiconductor ││
│  │                   │                   │ • Bulk fiber    ││
│  └───────────────────┴───────────────────┴─────────────────┘│
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

**Key Rules:**
- Three time periods as columns
- Sectors as rows
- Show capability additions over time
- New items highlighted or in different color

**Pattern:** Investment Perimeter Evolution Slide

---

### Template 27: Cost of Capital Spectrum

**Use for:** Funding strategy, capital sources comparison, financing options

```
┌─────────────────────────────────────────────────────────────┐
│  Asset sales provide an accretive source of capital [LOGO]  │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│                          9-11%                              │
│                     Target cost of                          │
│                       asset sales                           │
│                           │                                 │
│  Lowest                   ▼                        Highest  │
│   Cost ─────────────────────────────────────────────  Cost  │
│                                                             │
│    ~4%           ~6%                          12-15%+       │
│  Corporate    Preferred                       Common        │
│    debt        equity                         equity        │
│                                                             │
│  Limited by                                                 │
│  BBB+ ratings                                               │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

**Key Rules:**
- Horizontal spectrum from low to high cost
- Asset sale cost positioned on spectrum
- Labels for each funding type
- Constraints noted (e.g., rating limits)

**Pattern:** Cost of Capital Spectrum Slide

---

## Implementation Notes

### For python-pptx Code

```python
# Standard slide dimensions
SLIDE_WIDTH = Inches(13.333)  # 16:9 aspect ratio
SLIDE_HEIGHT = Inches(7.5)

# Standard positions
TITLE_TOP = Inches(0.4)
LOGO_RIGHT = SLIDE_WIDTH - Inches(0.5)
CONTENT_TOP = Inches(1.2)
TAKEAWAY_BOTTOM = SLIDE_HEIGHT - Inches(0.8)
FOOTER_BOTTOM = SLIDE_HEIGHT - Inches(0.3)

# Colors (RGB tuples)
TD_GREEN = RGBColor(0, 166, 81)      # #00A651
DARK_GREEN = RGBColor(0, 99, 65)     # #006341
HEADER_GRAY = RGBColor(74, 74, 74)   # #4A4A4A
LIGHT_GRAY = RGBColor(240, 240, 240) # #F0F0F0
```

---

## Related Documentation

- **[EXCEL_BACKUP_REFERENCE.md](./EXCEL_BACKUP_REFERENCE.md)** - Excel data structures for 18 of these 27 templates, including column definitions, sample data, and chart generation code.

---

*Extracted from institutional-quality IB/PE/IR presentations including IPO mandates, strategic rationales, investor day materials, and corporate profiles.*

*Last Updated: 2026-02-04*
