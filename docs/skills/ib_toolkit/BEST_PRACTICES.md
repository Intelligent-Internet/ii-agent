# Investment Banking Best Practices Guide
## Extracted from Real Case Studies: BCI Growth Equity & Northleaf PE

*Last Updated: February 4, 2026*
*Source: BCI Venture & Growth Case Study (2026), Northleaf PE LBO Case (2025)*

---

## Table of Contents
1. [PowerPoint Presentation Structure](#1-powerpoint-presentation-structure)
2. [Slide Content Best Practices](#2-slide-content-best-practices)
3. [Excel Model Architecture](#3-excel-model-architecture)
4. [Key Financial Metrics & Frameworks](#4-key-financial-metrics--frameworks)
5. [Investment Thesis Construction](#5-investment-thesis-construction)
6. [Competitive Analysis Frameworks](#6-competitive-analysis-frameworks)
7. [Returns Analysis Standards](#7-returns-analysis-standards)
8. [Risk Framework Templates](#8-risk-framework-templates)

---

## 1. PowerPoint Presentation Structure

### Standard IC Deck Flow (15-20 minutes)

| Slide # | Section | Duration | Purpose |
|---------|---------|----------|---------|
| 1 | Title Slide | 30 sec | Company name, deal type, recommendation, date |
| 2 | Executive Summary | 2 min | Investment thesis, key metrics, returns summary |
| 3 | Company Overview | 1.5 min | Founding story, product, traction, funding history |
| 4 | Investment Thesis | 2 min | 3 pillars supporting the recommendation |
| 5 | Market Opportunity | 1.5 min | TAM/SAM/SOM, market growth, "why now" |
| 6 | Competitive Landscape | 2 min | Positioning matrix, win/loss analysis |
| 7 | Unit Economics / GTM | 1.5 min | CAC, LTV, LTV:CAC by channel |
| 8 | Financial Overview | 2 min | Revenue trajectory, profitability path |
| 9 | Management Team | 1 min | Key executives, gaps, governance |
| 10-12 | Returns Analysis | 2.5 min | MOIC/IRR sensitivity, scenario analysis |
| 13-14 | Risk Analysis | 1.5 min | Key risks with probability/severity/mitigation |
| 15 | "What Must Be True" | 1 min | Critical assumptions for base case |
| 16 | Valuation Scenarios | 1 min | Stretch valuation impact on returns |
| 17 | Recommendation | 1 min | Final verdict, terms, diligence gates |

### Slide Design Principles

1. **One Key Message Per Slide**: Each slide should answer ONE question
2. **Action Titles**: Titles should be conclusions, not topics
   - BAD: "Financial Overview"
   - GOOD: "Revenue CAGR of 38% Driven by NDR Expansion and Logo Growth"
3. **Visual Hierarchy**: Key number → Supporting data → Context
4. **White Space**: 30-40% of slide should be empty
5. **Consistent Formatting**: Same fonts, colors, table styles throughout

---

## 2. Slide Content Best Practices

### Executive Summary Slide

**Required Elements:**
```
┌─────────────────────────────────────────────────────────────┐
│ EXECUTIVE SUMMARY                                           │
├─────────────────────────────────────────────────────────────┤
│ Company: [Name] | Sector: [Sector] | Deal Type: [Type]     │
├─────────────────────────────────────────────────────────────┤
│ RECOMMENDATION: [BUY / QUALIFIED BUY / PASS]               │
├─────────────────────────────────────────────────────────────┤
│ KEY METRICS:                                                │
│ • Entry Valuation: $XXM pre-money (X.Xx LTM Revenue)       │
│ • Investment Size: $XXM for X.X% ownership                 │
│ • LTM Revenue: $XXM | Growth: XX% YoY                      │
│ • Key SaaS Metric: XXX% NDR / XX% Gross Margin             │
├─────────────────────────────────────────────────────────────┤
│ BASE CASE RETURNS:                                          │
│ • MOIC: X.XXx | IRR: XX.X%                                 │
│ • Exit Year: 20XX | Exit Multiple: X.Xx                    │
├─────────────────────────────────────────────────────────────┤
│ INVESTMENT THESIS (3 Pillars):                             │
│ 1. [First pillar - market/competitive advantage]           │
│ 2. [Second pillar - distribution/growth driver]            │
│ 3. [Third pillar - metrics quality/efficiency]             │
└─────────────────────────────────────────────────────────────┘
```

### Investment Thesis Slide

**Structure each pillar with:**
1. **Headline claim** (bold, one sentence)
2. **Supporting evidence** (2-3 data points)
3. **"So what"** implication (why this matters for returns)

**Example:**
```
THESIS 1: QuickBooks displacement window is time-limited but actionable

• Intuit has 7M SMB users, $6B revenue, NO AI-native product yet
• Puzzle wins 72% of head-to-head deals vs. QuickBooks
• Window: 18-24 months before Intuit competitive response

→ Implication: First-mover can lock in 30-50K customers before market closes
```

### Financial Overview Slide

**Standard Table Format:**
```
| Metric        | 2024A | 2025E | 2026E | 2027E | 2028E | 5Y CAGR |
|---------------|-------|-------|-------|-------|-------|---------|
| Revenue       | $XXM  | $XXM  | $XXM  | $XXM  | $XXM  | XX%     |
| Growth %      | XX%   | XX%   | XX%   | XX%   | XX%   | —       |
| Gross Margin  | XX%   | XX%   | XX%   | XX%   | XX%   | —       |
| EBITDA Margin | (XX%) | (XX%) | X%    | XX%   | XX%   | —       |
```

**Always Include:**
- Historical vs. projected delineation
- Growth rate row
- Profitability inflection point highlighted
- CAGR column for quick reference

---

## 3. Excel Model Architecture

### LBO Model Structure (PE Deals)

**Tab Order:**
```
1. Cover / TOC
2. Assumptions (all inputs in one place)
3. Sources & Uses
4. Operating Model / P&L
5. Balance Sheet
6. Cash Flow Statement
7. Debt Schedule
8. Returns Analysis (MOIC, IRR, Equity Value Bridge)
9. Sensitivity Tables
10. Scenario Comparison (Bull / Base / Bear)
11. Football Field (Valuation Summary)
12. Appendix / Backup
```

### Growth Equity / Venture Model Structure

**Tab Order:**
```
1. Cover / TOC
2. Assumptions & Drivers
3. Revenue Build (Cohort Analysis for SaaS)
4. P&L Projection
5. Working Capital & Cash Flow
6. Cap Table (Pre/Post Round, Exit Dilution)
7. Returns Waterfall
8. Sensitivity Analysis
9. Scenario Comparison
10. Comps & Precedents
```

### Formatting Standards

| Element | Standard |
|---------|----------|
| Inputs/Assumptions | Blue font |
| Hardcoded values | Black font |
| Formulas/Links | Black font |
| External links | Green font |
| Error checks | Red font |
| Headers | Bold, gray background |
| Negative numbers | Parentheses, not minus sign |
| Percentages | One decimal: 12.5% |
| Currency | No decimals for large numbers: $1,234M |
| Dates | FYE Dec-25 or Q4'25 |

---

## 4. Key Financial Metrics & Frameworks

### SaaS Metrics (Growth Equity)

| Metric | Formula | Top Quartile | Median |
|--------|---------|--------------|--------|
| **NDR (Net Dollar Retention)** | (Beginning ARR + Expansion - Churn) / Beginning ARR | >120% | 105-115% |
| **Rule of 40** | Revenue Growth % + EBITDA Margin % | >40% | 30-40% |
| **Magic Number** | Net New ARR / S&M Spend (Prior Q) | >0.75x | 0.5-0.75x |
| **Burn Multiple** | Net Burn / Net New ARR | <1.5x | 1.5-2.5x |
| **CAC Payback** | CAC / (ARPU × Gross Margin) | <12 months | 12-18 months |
| **LTV:CAC** | LTV / CAC | >3x | 2-3x |
| **Gross Margin** | (Revenue - COGS) / Revenue | >80% | 70-80% |

### LBO Metrics (PE Deals)

| Metric | Target Range | Notes |
|--------|--------------|-------|
| Entry Multiple | 6-10x EBITDA | Industry-dependent |
| Leverage | 4-6x Debt/EBITDA | Senior + Mezz |
| Equity Check | 30-50% of TEV | Minimum equity cushion |
| Target IRR | 20-25% | Gross, before fees |
| Target MOIC | 2.0-3.0x | 5-year hold |
| Revenue Growth | 5-15% CAGR | Organic + M&A |
| EBITDA Margin Expansion | 200-500 bps | Operational improvements |

### Valuation Multiples by Sector

| Sector | EV/Revenue | EV/EBITDA | Notes |
|--------|------------|-----------|-------|
| Enterprise SaaS | 6-12x | 20-40x | Growth-dependent |
| SMB SaaS | 4-8x | 15-25x | Higher churn discount |
| Fintech | 5-10x | 15-30x | Regulatory premium/discount |
| Healthcare IT | 4-8x | 12-20x | Sticky revenue premium |
| Industrial Tech | 2-5x | 8-15x | Asset-heavy discount |

---

## 5. Investment Thesis Construction

### Three-Pillar Framework

Every investment thesis should have **exactly 3 pillars**:

1. **Market/Competitive Pillar**: Why this company wins in its market
2. **Growth/Distribution Pillar**: How it will scale
3. **Quality/Efficiency Pillar**: Why metrics justify valuation

### Thesis Validation Checklist

- [ ] Each pillar has quantitative support (not just qualitative claims)
- [ ] Thesis addresses obvious counter-arguments
- [ ] "What Must Be True" assumptions are explicit
- [ ] Downside scenario still returns capital (>1.0x MOIC)
- [ ] Thesis differentiates from consensus view

### Investment Recommendation Tiers

| Recommendation | Conviction | Conditions |
|----------------|------------|------------|
| **Strong Buy** | >80% | Metrics validated, attractive entry, clear path to 2.5x+ |
| **Buy** | 70-80% | Solid fundamentals, reasonable valuation |
| **Qualified Buy** | 60-70% | Conditional on diligence gates clearing |
| **Hold/Pass** | <60% | Valuation stretched or execution risk too high |

---

## 6. Competitive Analysis Frameworks

### 2x2 Positioning Matrix

```
                    AXIS 2 (e.g., Enterprise Readiness)
                           ▲
           High            │
                           │
      [Incumbents]         │         [Target Segment]
      Workday ●            │         ● Rillet
      NetSuite ●           │         ● Campfire
                           │
                           │ ● [COMPANY]
           ────────────────┼──────────────────►
                           │              AXIS 1
                           │         (e.g., Ease of Use)
      [Laggards]           │         [Blue Ocean]
      Legacy ●             │
           Low             │
                           │
```

### Win/Loss Analysis Table

| Competitor | Win Rate | Win Reasons | Loss Reasons | Sample Size |
|------------|----------|-------------|--------------|-------------|
| Competitor A | XX% | [Top 3 reasons] | [Top 3 reasons] | n=XX |
| Competitor B | XX% | [Top 3 reasons] | [Top 3 reasons] | n=XX |
| Incumbent | XX% | [Top 3 reasons] | [Top 3 reasons] | n=XX |

### Porter's Five Forces Summary

| Force | Rating | Key Insight | Company Advantage |
|-------|--------|-------------|-------------------|
| Threat of New Entrants | LOW/MED/HIGH | [One sentence] | [Moat] |
| Supplier Power | LOW/MED/HIGH | [One sentence] | [Position] |
| Buyer Power | LOW/MED/HIGH | [One sentence] | [Pricing power] |
| Threat of Substitutes | LOW/MED/HIGH | [One sentence] | [Differentiation] |
| Competitive Rivalry | LOW/MED/HIGH | [One sentence] | [Positioning] |

---

## 7. Returns Analysis Standards

### MOIC/IRR Sensitivity Table

**Standard format (Entry Multiple vs. Exit Multiple):**

```
MOIC Sensitivity — 5-Year Hold
┌──────────────┬─────────┬─────────┬─────────┬─────────┬─────────┐
│ Entry \ Exit │  5.0x   │  6.0x   │  7.0x   │  8.0x   │ 10.0x   │
├──────────────┼─────────┼─────────┼─────────┼─────────┼─────────┤
│ $750M (12x)  │  1.79x  │  2.15x  │ [2.42x] │  2.76x  │  3.58x  │
│ $800M (13x)  │  1.70x  │  2.04x  │  2.28x  │  2.63x  │  3.41x  │
│ $1,000M (16x)│  1.39x  │  1.67x  │  1.86x  │  2.15x  │  2.79x  │
│ $1,200M (19x)│  1.18x  │  1.42x  │  1.58x  │  1.82x  │  2.36x  │
└──────────────┴─────────┴─────────┴─────────┴─────────┴─────────┘
[Base case highlighted]
```

### Scenario Analysis Table

| Scenario | Probability | Exit Multiple | MOIC | IRR | Exit TEV | Key Assumptions |
|----------|-------------|---------------|------|-----|----------|-----------------|
| Bull | 20-25% | X.Xx | X.Xx | XX% | $XB | [2-3 bullets] |
| **Base** | 50-60% | X.Xx | X.Xx | XX% | $XB | [2-3 bullets] |
| Bear | 15-20% | X.Xx | X.Xx | XX% | $XM | [2-3 bullets] |
| Downside | 5-10% | X.Xx | X.Xx | XX% | $XM | [2-3 bullets] |
| **Blended EV** | 100% | — | X.Xx | XX% | — | Probability-weighted |

### Returns Waterfall (LBO)

```
Entry Equity Investment         $XXM
+ EBITDA Growth                 $XXM
+ Multiple Expansion            $XXM
+ Debt Paydown                  $XXM
- Transaction Costs             ($XM)
= Exit Equity Value             $XXM
─────────────────────────────────────
MOIC                            X.Xx
IRR                             XX.X%
```

---

## 8. Risk Framework Templates

### Risk Matrix

| Risk | Probability | Severity | Impact | Mitigation |
|------|-------------|----------|--------|------------|
| [Risk 1] | XX% | HIGH/MED/LOW | [Quantified impact] | [Specific action] |
| [Risk 2] | XX% | HIGH/MED/LOW | [Quantified impact] | [Specific action] |
| [Risk 3] | XX% | HIGH/MED/LOW | [Quantified impact] | [Specific action] |

### "What Must Be True" Framework

For base case returns to materialize:

1. **Growth**: [Specific threshold, e.g., ">40% YoY through 2028"]
2. **Market**: [External condition, e.g., "No major competitor launch before H2 2027"]
3. **Retention**: [Metric threshold, e.g., "NDR ≥120% sustained"]
4. **Exit**: [Market condition, e.g., "Multiples remain ≥7.0x"]

### Diligence Gates (Go/No-Go)

| Gate | Pass Criteria | Fail Action |
|------|---------------|-------------|
| Gate 1: [Metric] | [Threshold] | Walk away / Renegotiate X% |
| Gate 2: [Metric] | [Threshold] | Walk away / Reduce size X% |
| Gate 3: [Metric] | [Threshold] | Walk away / Add governance |

### Walk-Away Triggers

| Trigger | Reason |
|---------|--------|
| [Trigger 1] | [Why this is fatal to the thesis] |
| [Trigger 2] | [Why this is fatal to the thesis] |
| [Trigger 3] | [Why this is fatal to the thesis] |

---

## Appendix: Template Phrases

### For Investment Recommendations

- "We recommend a **[Qualified] Buy** with $XXM investment at $XXM post-money valuation"
- "Base case returns of **X.Xx MOIC / XX% IRR** are achievable assuming..."
- "The investment thesis rests on three pillars..."
- "Conviction would increase to High if we can validate..."

### For Risk Discussions

- "The primary risk is [X], with XX% probability and HIGH severity"
- "Mitigation: [Specific action that reduces probability or impact]"
- "In the bear case, we still achieve X.Xx MOIC / XX% IRR"
- "Break-even occurs at X.Xx exit multiple — below current market median"

### For Competitive Analysis

- "[Company] is NOT competing with [Competitor] — only XX% ICP overlap"
- "In fragmented [SMB/Enterprise] markets, distribution beats product"
- "Win rate vs. [Competitor]: XX% — [strong/weak] based on [reason]"

### For Q&A Preparation

- "If [condition], returns improve to X.Xx MOIC"
- "If [condition], we would walk away because..."
- "The killer insight is that [counter-consensus view]"

---

*This document should be updated as new case studies and industry best practices emerge.*
