# Investment Banking Prompt Library
## 52-Prompt System for Deal Execution

*Version: 1.0.0 | Created: 2026-02-04*
*Source: Buyside Agent Resources*

---

## How to Use This Library

Each prompt is self-contained with:
- **Context**: Role and situation
- **Objective**: Clear deliverable
- **Inputs**: Required materials
- **Output Spec**: Exact format expected
- **Validation**: Quality checklist
- **Handoff**: Next prompts unlocked

Copy the prompt, fill in `[BRACKETED]` variables, and execute.

---

## Phase 0: Foundation Prompts

### P00: Case Setup Orchestrator

```markdown
# ROLE
You are a private equity associate initializing a new deal case.

# CONTEXT
Company: [COMPANY_NAME]
Deal Type: [growth_equity / lbo / venture]
Materials Location: [PATH_TO_MATERIALS]

# OBJECTIVE
Create the case infrastructure and material inventory.

# TASKS
1. Create case_state.json with initial structure
2. Scan all materials and categorize:
   - CIM / Information Memorandum
   - Management Presentation
   - Financial Statements (historical)
   - Data Room Index
   - Third-Party Reports (market studies, QofE)
3. Flag any missing critical materials
4. Identify immediate questions for management

# OUTPUT FORMAT
## Material Inventory

| Category | Document | Pages/Files | Status | Notes |
|----------|----------|-------------|--------|-------|
| CIM | [filename] | XX pages | ✓ Ingested | [key sections] |
| ... | ... | ... | ... | ... |

## Missing Materials
- [ ] [Material 1] - Impact: [HIGH/MED/LOW]

## Initial Questions
1. [Question about unclear item]

## Case State Initialized
- Case ID: [auto-generate]
- Created: [timestamp]
- Phase: 0 - Foundation
```

---

### P01: Material Inventory Deep Dive

```markdown
# ROLE
You are a PE analyst conducting document triage.

# CONTEXT
Case: [COMPANY_NAME]
Materials from P00 inventory.

# OBJECTIVE
Deep-index all materials with page-level references for quick retrieval.

# TASKS
For each document:
1. Table of contents extraction
2. Key data points with page references
3. Flag inconsistencies between documents
4. Identify data gaps

# OUTPUT FORMAT
## CIM Index
| Section | Pages | Key Data Points |
|---------|-------|-----------------|
| Executive Summary | 1-5 | Revenue: $XXM, Growth: XX%, Key thesis points |
| Company Overview | 6-15 | Founded XXXX, HQ: [city], Employees: XXX |
| Market | 16-25 | TAM: $XB, CAGR: XX% |
| ... | ... | ... |

## Cross-Document Inconsistencies
| Data Point | CIM Value | Mgmt Deck Value | Financial Value | Resolution |
|------------|-----------|-----------------|-----------------|------------|

## Data Gaps Identified
1. [Missing data] - Needed for: [analysis type]
```

---

### P02: Company Overview Generator

```markdown
# ROLE
You are a PE associate creating a company overview.

# CONTEXT
Company: [COMPANY_NAME]
Sector: [SECTOR]
Deal Type: [DEAL_TYPE]
Source Materials: CIM pages 1-15, Management Deck pages 1-10

# OBJECTIVE
Create a 1-page company overview suitable for IC discussion.

# OUTPUT FORMAT
## [COMPANY_NAME] | Company Overview

### Snapshot
| Metric | Value |
|--------|-------|
| Founded | XXXX |
| Headquarters | [City, Country] |
| Employees | XXX |
| LTM Revenue | $XXM |
| LTM Growth | XX% |
| Business Model | [B2B SaaS / Marketplace / etc.] |

### Business Description
[2-3 sentence description of what the company does, for whom, and how they make money]

### Product/Service Overview
- **Core Product**: [Description]
- **Key Features**: [Feature 1], [Feature 2], [Feature 3]
- **Customer Value Prop**: [Why customers buy]

### Funding History
| Round | Date | Amount | Investors | Post-Money |
|-------|------|--------|-----------|------------|

### Key Milestones
- YYYY: [Milestone 1]
- YYYY: [Milestone 2]
- YYYY: [Milestone 3]

### Current Round
- Seeking: $[X]M [equity type]
- Use of Proceeds: [primary uses]
- Valuation: $[X]M [pre/post]-money

# VALIDATION
- [ ] All metrics sourced and page-referenced
- [ ] No unsourced claims
- [ ] Fits on one page when formatted
```

---

### P03: Market Sizing (TAM/SAM/SOM)

```markdown
# ROLE
You are a PE associate building a market sizing analysis.

# CONTEXT
Company: [COMPANY_NAME]
Sector: [SECTOR]
Source: CIM market section, third-party reports

# OBJECTIVE
Create bottoms-up and top-down market sizing with clear methodology.

# OUTPUT FORMAT
## Market Sizing | [COMPANY_NAME]

### Top-Down Approach
```
Global [Industry] Market: $[X]B (Source: [Report], [Year])
├── Geography Filter ([Region]): $[X]B ([X]% of global)
├── Segment Filter ([Segment]): $[X]B ([X]% of region)
└── TAM: $[X]B
```

### Bottoms-Up Approach
```
Target Customers: [X] companies
× Average Contract Value: $[X]K
× Penetration Ceiling: [X]%
= SAM: $[X]M
```

### Serviceable Obtainable Market (SOM)
- Current Market Share: [X]%
- 5-Year Target Share: [X]%
- SOM (Year 5): $[X]M

### Market Growth
| Metric | Historical | Projected | Source |
|--------|------------|-----------|--------|
| Market CAGR | XX% (20XX-20XX) | XX% (20XX-20XX) | [Source] |
| Company Growth vs Market | [X]x market | [X]x market | Calculated |

### "Why Now" Factors
1. [Secular trend 1]
2. [Secular trend 2]
3. [Catalyst / inflection point]

# VALIDATION
- [ ] TAM > SAM > SOM logic holds
- [ ] Multiple sources triangulated
- [ ] Growth rates are realistic
- [ ] "Why now" is compelling
```

---

### P04: Business Model Canvas

```markdown
# ROLE
You are a PE associate mapping the business model.

# CONTEXT
Company: [COMPANY_NAME]
Source: CIM, management deck, financial statements

# OBJECTIVE
Create comprehensive business model analysis including unit economics.

# OUTPUT FORMAT
## Business Model Canvas | [COMPANY_NAME]

### Revenue Model
| Stream | % of Revenue | Model Type | Pricing | Growth Driver |
|--------|--------------|------------|---------|---------------|
| [Stream 1] | XX% | [Subscription/Transaction/etc.] | $[X]/[unit] | [Driver] |

### Customer Segments
| Segment | % of Revenue | Characteristics | Avg Deal Size |
|---------|--------------|-----------------|---------------|
| [Segment 1] | XX% | [Description] | $[X]K |

### Unit Economics (SaaS)
| Metric | Value | Benchmark | Status |
|--------|-------|-----------|--------|
| ARPU | $[X]K | $[X]K | ✓/⚠/✗ |
| Gross Margin | XX% | >70% | ✓/⚠/✗ |
| CAC | $[X]K | — | — |
| LTV | $[X]K | — | — |
| LTV:CAC | [X]x | >3x | ✓/⚠/✗ |
| CAC Payback | [X] mo | <18 mo | ✓/⚠/✗ |
| NDR | XXX% | >110% | ✓/⚠/✗ |
| Logo Churn | XX% | <10% | ✓/⚠/✗ |

### Cost Structure
| Category | % of Revenue | Fixed/Variable | Key Drivers |
|----------|--------------|----------------|-------------|
| COGS | XX% | Variable | [Driver] |
| S&M | XX% | Mixed | [Driver] |
| R&D | XX% | Fixed | [Driver] |
| G&A | XX% | Fixed | [Driver] |

### Key Resources
- [Resource 1]: [Why critical]
- [Resource 2]: [Why critical]

### Key Activities
- [Activity 1]: [Purpose]
- [Activity 2]: [Purpose]

### Key Partnerships
- [Partner type]: [Strategic value]

# VALIDATION
- [ ] Revenue streams sum to 100%
- [ ] Unit economics are internally consistent
- [ ] Cost structure matches P&L
- [ ] All metrics have sources
```

---

## Phase 1: Analysis Prompts

### P10: Competitive Landscape

```markdown
# ROLE
You are a PE associate analyzing competitive dynamics.

# CONTEXT
Company: [COMPANY_NAME]
Sector: [SECTOR]
Completed: P02 (Company Overview), P03 (Market Sizing)

# OBJECTIVE
Map competitive landscape with positioning analysis and win/loss data.

# OUTPUT FORMAT
## Competitive Landscape | [COMPANY_NAME]

### Competitor Universe
| Competitor | Type | Revenue | Funding | Key Differentiator |
|------------|------|---------|---------|-------------------|
| [Comp 1] | Direct | $[X]M | $[X]M raised | [Differentiator] |
| [Comp 2] | Indirect | $[X]M | Public | [Differentiator] |
| [Incumbent] | Incumbent | $[X]B | Public | [Differentiator] |

### 2x2 Positioning Matrix
```
                    [AXIS 2: e.g., Enterprise Readiness]
                              ▲ High
                              │
         [Quadrant 2]         │         [Quadrant 1]
         ● [Comp A]           │         ● [COMPANY]
         ● [Comp B]           │         ● [Comp C]
                              │
    ──────────────────────────┼──────────────────────►
    Low                       │                    High
                              │               [AXIS 1: e.g., Ease of Use]
         [Quadrant 3]         │         [Quadrant 4]
         ● [Comp D]           │         ● [Comp E]
                              │
                              ▼ Low
```

### Win/Loss Analysis
| Competitor | Win Rate | Sample | Top Win Reasons | Top Loss Reasons |
|------------|----------|--------|-----------------|------------------|
| [Comp 1] | XX% | n=[X] | 1. [Reason] 2. [Reason] | 1. [Reason] |
| [Comp 2] | XX% | n=[X] | 1. [Reason] 2. [Reason] | 1. [Reason] |
| Incumbent | XX% | n=[X] | 1. [Reason] 2. [Reason] | 1. [Reason] |

### Porter's Five Forces
| Force | Rating | Assessment |
|-------|--------|------------|
| New Entrants | LOW/MED/HIGH | [One sentence] |
| Supplier Power | LOW/MED/HIGH | [One sentence] |
| Buyer Power | LOW/MED/HIGH | [One sentence] |
| Substitutes | LOW/MED/HIGH | [One sentence] |
| Rivalry | LOW/MED/HIGH | [One sentence] |

### Competitive Moat Assessment
| Moat Type | Strength (1-5) | Evidence |
|-----------|----------------|----------|
| Network Effects | [X] | [Evidence] |
| Switching Costs | [X] | [Evidence] |
| Data/IP | [X] | [Evidence] |
| Brand | [X] | [Evidence] |
| Scale | [X] | [Evidence] |
| **Overall Moat** | **[X]/5** | **[Summary]** |

# VALIDATION
- [ ] All major competitors included
- [ ] Win rates have sample sizes
- [ ] Moat assessment is evidenced
- [ ] 2x2 axes are meaningful and differentiated
```

---

### P11: Customer Analysis

```markdown
# ROLE
You are a PE associate analyzing customer dynamics.

# CONTEXT
Company: [COMPANY_NAME]
Completed: P04 (Business Model)

# OBJECTIVE
Deep-dive customer analysis including ICP, cohorts, and concentration.

# OUTPUT FORMAT
## Customer Analysis | [COMPANY_NAME]

### Ideal Customer Profile (ICP)
| Dimension | ICP Definition |
|-----------|----------------|
| Industry | [Industries] |
| Company Size | [Revenue/Employees range] |
| Geography | [Regions] |
| Use Case | [Primary use case] |
| Buyer Persona | [Title/Role] |
| Budget | $[X]K - $[X]K |

### Customer Concentration
| Metric | Value | Risk Level |
|--------|-------|------------|
| Top 1 Customer | XX% of revenue | 🟢/🟡/🔴 |
| Top 5 Customers | XX% of revenue | 🟢/🟡/🔴 |
| Top 10 Customers | XX% of revenue | 🟢/🟡/🔴 |

### Cohort Analysis
| Cohort | Starting ARR | Current ARR | NDR | Logo Retention |
|--------|--------------|-------------|-----|----------------|
| 2022 | $[X]M | $[X]M | XXX% | XX% |
| 2023 | $[X]M | $[X]M | XXX% | XX% |
| 2024 | $[X]M | $[X]M | XXX% | XX% |

### Logo Metrics
- Total Customers: [X]
- Net New Logos (LTM): [+X]
- Gross Adds: [X]
- Churned: [X]
- Logo Churn Rate: XX%

### Expansion Revenue Analysis
- Expansion Revenue (LTM): $[X]M
- % of Total Revenue from Expansion: XX%
- Primary Expansion Drivers:
  1. [Driver 1]: XX% of expansion
  2. [Driver 2]: XX% of expansion

### Customer Feedback Themes
| Theme | Sentiment | Frequency | Implication |
|-------|-----------|-----------|-------------|
| [Theme 1] | Positive | High | [Implication] |
| [Theme 2] | Negative | Medium | [Implication] |

# VALIDATION
- [ ] Customer concentration assessed
- [ ] Cohort data is consistent with P&L
- [ ] ICP is specific and actionable
- [ ] Expansion drivers identified
```

---

### P12: Management Assessment

```markdown
# ROLE
You are a PE associate assessing the management team.

# CONTEXT
Company: [COMPANY_NAME]
Source: Management bios, LinkedIn, prior interactions

# OBJECTIVE
Evaluate management team quality and identify gaps.

# OUTPUT FORMAT
## Management Assessment | [COMPANY_NAME]

### Executive Team Scorecard
| Role | Name | Tenure | Prior Experience | Score (1-5) | Notes |
|------|------|--------|------------------|-------------|-------|
| CEO | [Name] | [X] yrs | [Background] | [X] | [Key strength/concern] |
| CFO | [Name] | [X] yrs | [Background] | [X] | [Key strength/concern] |
| CTO | [Name] | [X] yrs | [Background] | [X] | [Key strength/concern] |
| CRO | [Name] | [X] yrs | [Background] | [X] | [Key strength/concern] |
| CMO | [Name] | [X] yrs | [Background] | [X] | [Key strength/concern] |

### Team Composition Analysis
| Metric | Value | Benchmark | Assessment |
|--------|-------|-----------|------------|
| Avg Executive Tenure | [X] yrs | >2 yrs | ✓/⚠ |
| Prior Exits | [X] | >1 | ✓/⚠ |
| Domain Experience | XX% | >60% | ✓/⚠ |
| Public Co Experience | [Y/N] | Preferred | ✓/⚠ |

### Organizational Gaps
| Gap | Priority | Risk if Unfilled | Suggested Profile |
|-----|----------|------------------|-------------------|
| [Role/Capability] | HIGH/MED | [Impact] | [Profile description] |

### Reference Check Themes
| Theme | Positive/Negative | Source Type | Quote/Summary |
|-------|-------------------|-------------|---------------|
| [Theme] | [P/N] | [Investor/Customer/Employee] | "[Quote]" |

### Governance Assessment
- Board Composition: [X] members ([X] independent)
- Board Meeting Cadence: [Monthly/Quarterly]
- Key Board Members: [Names and relevant experience]
- Governance Gaps: [If any]

### Overall Management Score
| Dimension | Score (1-5) | Weight | Weighted |
|-----------|-------------|--------|----------|
| CEO Quality | [X] | 30% | [X] |
| Team Completeness | [X] | 25% | [X] |
| Execution Track Record | [X] | 25% | [X] |
| Coachability | [X] | 20% | [X] |
| **Overall** | — | 100% | **[X.X]/5** |

# VALIDATION
- [ ] All C-suite covered
- [ ] Gaps prioritized
- [ ] Reference themes are sourced
- [ ] Governance reviewed
```

---

### P13: Diligence Question Generator

```markdown
# ROLE
You are a PE associate preparing for management meetings.

# CONTEXT
Company: [COMPANY_NAME]
Completed: P10-P12

# OBJECTIVE
Generate prioritized diligence questions based on analysis gaps.

# OUTPUT FORMAT
## Diligence Questions | [COMPANY_NAME]

### Priority 1: Must-Answer Before IC
| # | Topic | Question | Why Critical | Source |
|---|-------|----------|--------------|--------|
| 1 | [Topic] | [Specific question] | [Investment impact] | Management |
| 2 | [Topic] | [Specific question] | [Investment impact] | Data Room |
| ... | ... | ... | ... | ... |

### Priority 2: Important for Thesis
| # | Topic | Question | Why Important | Source |
|---|-------|----------|---------------|--------|
| 1 | [Topic] | [Specific question] | [Thesis pillar impact] | [Source] |
| ... | ... | ... | ... | ... |

### Priority 3: Nice-to-Have
| # | Topic | Question | Context | Source |
|---|-------|----------|---------|--------|
| 1 | [Topic] | [Specific question] | [Context] | [Source] |
| ... | ... | ... | ... | ... |

### Questions by Functional Area
**Financial**
1. [Question]
2. [Question]

**Commercial**
1. [Question]
2. [Question]

**Product/Technology**
1. [Question]
2. [Question]

**Operations**
1. [Question]
2. [Question]

**Legal/Regulatory**
1. [Question]
2. [Question]

### Red Flag Follow-ups
| Red Flag (from P14) | Follow-up Question | Acceptable Answer |
|---------------------|-------------------|-------------------|
| [Flag] | [Question] | [What would resolve concern] |

# VALIDATION
- [ ] Priority 1 questions address investment decision
- [ ] Questions are specific, not generic
- [ ] Red flags have follow-up questions
- [ ] All functional areas covered
```

---

### P14: Red Flag Scanner

```markdown
# ROLE
You are a PE associate conducting risk identification.

# CONTEXT
Company: [COMPANY_NAME]
Completed: P01 (Material Inventory)

# OBJECTIVE
Systematically scan all materials for red flags and concerns.

# OUTPUT FORMAT
## Red Flag Analysis | [COMPANY_NAME]

### Critical Red Flags (Deal-Breaker Potential)
| # | Category | Flag | Source | Severity | Mitigation Possible? |
|---|----------|------|--------|----------|---------------------|
| 1 | [Category] | [Description] | [Doc, page X] | CRITICAL | [Y/N] |

### Significant Concerns (Requires Diligence)
| # | Category | Concern | Source | Impact | Diligence Action |
|---|----------|---------|--------|--------|------------------|
| 1 | [Category] | [Description] | [Doc, page X] | HIGH | [Action needed] |

### Yellow Flags (Monitor)
| # | Category | Flag | Source | Implication |
|---|----------|------|--------|-------------|
| 1 | [Category] | [Description] | [Doc, page X] | [What to watch] |

### Red Flag Categories Scanned
- [ ] Financial inconsistencies
- [ ] Customer concentration
- [ ] Regulatory/compliance
- [ ] Management concerns
- [ ] Market risks
- [ ] Technology/IP risks
- [ ] Litigation/legal
- [ ] Related party transactions
- [ ] Accounting policy concerns
- [ ] Competitive threats

### Data Quality Issues
| Issue | Documents Affected | Impact on Analysis |
|-------|-------------------|-------------------|
| [Issue] | [Documents] | [Impact] |

### Missing Information (Suspicious Gaps)
| Missing Item | Expected Location | Concern |
|--------------|-------------------|---------|
| [Item] | [Where it should be] | [Why concerning] |

# VALIDATION
- [ ] All material documents scanned
- [ ] Flags are page-referenced
- [ ] Severity is justified
- [ ] Mitigation paths identified where possible
```

---

## Phase 2: Modeling Prompts

### P20: Revenue Build

```markdown
# ROLE
You are a PE associate building a revenue model.

# CONTEXT
Company: [COMPANY_NAME]
Business Model: [Model type from P04]
Completed: P04 (Business Model), P11 (Customer Analysis)

# OBJECTIVE
Create bottoms-up revenue projection with driver assumptions.

# OUTPUT FORMAT
## Revenue Model | [COMPANY_NAME]

### Revenue Build Methodology
[Describe approach: cohort-based, customer count × ARPU, etc.]

### Key Assumptions
| Driver | Historical | Projection | Rationale |
|--------|------------|------------|-----------|
| Customer Adds/Year | [X] | [X] | [Why] |
| ARPU | $[X]K | $[X]K growing X%/yr | [Why] |
| NDR | XXX% | XXX% | [Why] |
| Gross Churn | XX% | XX% | [Why] |

### Revenue Projection
| Metric | 2024A | 2025E | 2026E | 2027E | 2028E | 2029E |
|--------|-------|-------|-------|-------|-------|-------|
| Beginning Customers | [X] | [X] | [X] | [X] | [X] | [X] |
| + Gross Adds | [X] | [X] | [X] | [X] | [X] | [X] |
| - Churned | ([X]) | ([X]) | ([X]) | ([X]) | ([X]) | ([X]) |
| = Ending Customers | [X] | [X] | [X] | [X] | [X] | [X] |
| ARPU ($K) | [X] | [X] | [X] | [X] | [X] | [X] |
| **ARR ($M)** | **[X]** | **[X]** | **[X]** | **[X]** | **[X]** | **[X]** |
| Growth % | XX% | XX% | XX% | XX% | XX% | XX% |

### Cohort Revenue Waterfall
| Cohort | 2024A | 2025E | 2026E | 2027E | 2028E | 2029E |
|--------|-------|-------|-------|-------|-------|-------|
| Pre-2024 | $[X]M | $[X]M | $[X]M | $[X]M | $[X]M | $[X]M |
| 2024 | $[X]M | $[X]M | $[X]M | $[X]M | $[X]M | $[X]M |
| 2025 | — | $[X]M | $[X]M | $[X]M | $[X]M | $[X]M |
| ... | ... | ... | ... | ... | ... | ... |
| **Total** | **$[X]M** | **$[X]M** | **$[X]M** | **$[X]M** | **$[X]M** | **$[X]M** |

### Revenue by Segment
| Segment | 2024A | Mix | 2029E | Mix | CAGR |
|---------|-------|-----|-------|-----|------|
| [Segment 1] | $[X]M | XX% | $[X]M | XX% | XX% |
| [Segment 2] | $[X]M | XX% | $[X]M | XX% | XX% |
| **Total** | **$[X]M** | 100% | **$[X]M** | 100% | **XX%** |

# VALIDATION
- [ ] Bottoms-up ties to reported revenue
- [ ] Assumptions are sourced/justified
- [ ] Growth deceleration is realistic
- [ ] Cohort math is internally consistent
```

---

### P21: Operating Model

```markdown
# ROLE
You are a PE associate building an operating model.

# CONTEXT
Company: [COMPANY_NAME]
Completed: P20 (Revenue Build)

# OBJECTIVE
Create full P&L projection with margin progression.

# OUTPUT FORMAT
## Operating Model | [COMPANY_NAME]

### P&L Summary ($M)
| Line Item | 2024A | 2025E | 2026E | 2027E | 2028E | 2029E |
|-----------|-------|-------|-------|-------|-------|-------|
| Revenue | [X] | [X] | [X] | [X] | [X] | [X] |
| Growth % | XX% | XX% | XX% | XX% | XX% | XX% |
| Gross Profit | [X] | [X] | [X] | [X] | [X] | [X] |
| Gross Margin % | XX% | XX% | XX% | XX% | XX% | XX% |
| S&M | ([X]) | ([X]) | ([X]) | ([X]) | ([X]) | ([X]) |
| % of Revenue | XX% | XX% | XX% | XX% | XX% | XX% |
| R&D | ([X]) | ([X]) | ([X]) | ([X]) | ([X]) | ([X]) |
| % of Revenue | XX% | XX% | XX% | XX% | XX% | XX% |
| G&A | ([X]) | ([X]) | ([X]) | ([X]) | ([X]) | ([X]) |
| % of Revenue | XX% | XX% | XX% | XX% | XX% | XX% |
| **EBITDA** | **[X]** | **[X]** | **[X]** | **[X]** | **[X]** | **[X]** |
| **EBITDA Margin %** | **XX%** | **XX%** | **XX%** | **XX%** | **XX%** | **XX%** |

### Cost Assumptions
| Cost Line | Driver | 2024A | 2029E | Rationale |
|-----------|--------|-------|-------|-----------|
| COGS | % of Revenue | XX% | XX% | [Scale benefits] |
| S&M | % of Revenue | XX% | XX% | [Efficiency gains] |
| R&D | % of Revenue | XX% | XX% | [Investment level] |
| G&A | Fixed + % | $[X]M + X% | $[X]M + X% | [Leverage] |

### Rule of 40 Progression
| Year | Growth | EBITDA Margin | Rule of 40 |
|------|--------|---------------|------------|
| 2024A | XX% | XX% | XX |
| 2025E | XX% | XX% | XX |
| 2026E | XX% | XX% | XX |
| 2027E | XX% | XX% | XX |
| 2028E | XX% | XX% | XX |
| 2029E | XX% | XX% | XX |

### Headcount Model
| Department | 2024A | 2025E | 2026E | 2027E | 2028E | 2029E |
|------------|-------|-------|-------|-------|-------|-------|
| Sales | [X] | [X] | [X] | [X] | [X] | [X] |
| Marketing | [X] | [X] | [X] | [X] | [X] | [X] |
| Engineering | [X] | [X] | [X] | [X] | [X] | [X] |
| Product | [X] | [X] | [X] | [X] | [X] | [X] |
| G&A | [X] | [X] | [X] | [X] | [X] | [X] |
| **Total** | **[X]** | **[X]** | **[X]** | **[X]** | **[X]** | **[X]** |
| Rev/Employee | $[X]K | $[X]K | $[X]K | $[X]K | $[X]K | $[X]K |

# VALIDATION
- [ ] Revenue ties to P20
- [ ] Historical margins match reported
- [ ] Margin expansion is realistic
- [ ] Headcount supports revenue
```

---

### P22: Model Builder Engine (LBO)

```markdown
# ROLE
You are a PE associate building an LBO model.

# CONTEXT
Company: [COMPANY_NAME]
Entry Valuation: [ENTRY_MULTIPLE]x EBITDA = $[ENTRY_TEV]M
Completed: P21 (Operating Model)

# OBJECTIVE
Build complete LBO model with sources/uses, debt schedule, and returns.

# OUTPUT FORMAT
## LBO Model | [COMPANY_NAME]

### Transaction Summary
| Metric | Value |
|--------|-------|
| Entry Date | [Date] |
| Entry EBITDA | $[X]M |
| Entry Multiple | [X]x |
| Enterprise Value | $[X]M |
| Hold Period | [X] years |

### Sources & Uses ($M)
| Sources | Amount | % | Uses | Amount | % |
|---------|--------|---|------|--------|---|
| Senior Debt | [X] | XX% | Purchase Price | [X] | XX% |
| Subordinated Debt | [X] | XX% | Refinance Existing | [X] | XX% |
| Sponsor Equity | [X] | XX% | Transaction Fees | [X] | XX% |
| Management Rollover | [X] | XX% | Cash to Balance Sheet | [X] | XX% |
| **Total Sources** | **[X]** | 100% | **Total Uses** | **[X]** | 100% |

### Debt Structure
| Tranche | Amount | Rate | Amort | Maturity | Covenant |
|---------|--------|------|-------|----------|----------|
| Revolver | $[X]M | L+[X]bps | — | [X] yrs | — |
| Term Loan A | $[X]M | L+[X]bps | [X]% | [X] yrs | [X]x |
| Term Loan B | $[X]M | L+[X]bps | 1% | [X] yrs | — |
| Subordinated | $[X]M | [X]% cash + [X]% PIK | — | [X] yrs | — |

### Leverage Summary
| Metric | Entry | Year 1 | Year 2 | Year 3 | Year 4 | Year 5 |
|--------|-------|--------|--------|--------|--------|--------|
| Total Debt | $[X]M | $[X]M | $[X]M | $[X]M | $[X]M | $[X]M |
| Debt/EBITDA | [X]x | [X]x | [X]x | [X]x | [X]x | [X]x |
| Interest Coverage | [X]x | [X]x | [X]x | [X]x | [X]x | [X]x |

### Returns Analysis
| Scenario | Exit Multiple | Exit TEV | Equity Value | MOIC | IRR |
|----------|---------------|----------|--------------|------|-----|
| Downside | [X]x | $[X]M | $[X]M | [X]x | XX% |
| Bear | [X]x | $[X]M | $[X]M | [X]x | XX% |
| **Base** | **[X]x** | **$[X]M** | **$[X]M** | **[X]x** | **XX%** |
| Bull | [X]x | $[X]M | $[X]M | [X]x | XX% |
| Upside | [X]x | $[X]M | $[X]M | [X]x | XX% |

### Value Creation Bridge ($M)
```
Entry Equity               $[X]M
+ EBITDA Growth           +$[X]M    (XX%)
+ Multiple Expansion      +$[X]M    (XX%)
+ Debt Paydown           +$[X]M    (XX%)
- Interest Paid          -$[X]M    (XX%)
- Fees & Costs           -$[X]M    (XX%)
= Exit Equity Value       $[X]M
─────────────────────────────────
MOIC                      [X]x
IRR                       XX%
```

### MOIC Sensitivity (Entry vs Exit Multiple)
|Entry\Exit| 5.0x | 6.0x | 7.0x | 8.0x | 9.0x |
|----------|------|------|------|------|------|
| 6.0x | [X]x | [X]x | [X]x | [X]x | [X]x |
| 7.0x | [X]x | [X]x | **[X]x** | [X]x | [X]x |
| 8.0x | [X]x | [X]x | [X]x | [X]x | [X]x |
| 9.0x | [X]x | [X]x | [X]x | [X]x | [X]x |

# VALIDATION
- [ ] Sources = Uses
- [ ] Debt amortization matches cash flow
- [ ] Returns math is correct
- [ ] Sensitivity ranges are reasonable
```

---

### P23: Returns Calculator

```markdown
# ROLE
You are a PE associate calculating investment returns.

# CONTEXT
Company: [COMPANY_NAME]
Deal Type: [growth_equity / lbo]
Completed: P21 or P22

# OBJECTIVE
Create comprehensive returns analysis with sensitivities.

# OUTPUT FORMAT
## Returns Analysis | [COMPANY_NAME]

### Investment Parameters
| Parameter | Value |
|-----------|-------|
| Investment Amount | $[X]M |
| Ownership % | XX% |
| Entry Valuation | $[X]M [pre/post] |
| Entry Multiple | [X]x [Revenue/EBITDA] |

### Base Case Returns
| Metric | Year 3 | Year 4 | Year 5 | Year 6 | Year 7 |
|--------|--------|--------|--------|--------|--------|
| Exit Revenue | $[X]M | $[X]M | $[X]M | $[X]M | $[X]M |
| Exit EBITDA | $[X]M | $[X]M | $[X]M | $[X]M | $[X]M |
| Exit Multiple | [X]x | [X]x | [X]x | [X]x | [X]x |
| Exit Valuation | $[X]M | $[X]M | $[X]M | $[X]M | $[X]M |
| Proceeds | $[X]M | $[X]M | $[X]M | $[X]M | $[X]M |
| **MOIC** | **[X]x** | **[X]x** | **[X]x** | **[X]x** | **[X]x** |
| **IRR** | **XX%** | **XX%** | **XX%** | **XX%** | **XX%** |

### MOIC Sensitivity: Entry Valuation vs Exit Multiple
| Entry \ Exit | [X]x | [X]x | [X]x | [X]x | [X]x |
|--------------|------|------|------|------|------|
| $[X]M | [X]x | [X]x | [X]x | [X]x | [X]x |
| $[X]M | [X]x | [X]x | **[X]x** | [X]x | [X]x |
| $[X]M | [X]x | [X]x | [X]x | [X]x | [X]x |
| $[X]M | [X]x | [X]x | [X]x | [X]x | [X]x |

### IRR Sensitivity: Exit Multiple vs Hold Period
| Multiple \ Years | 3 | 4 | 5 | 6 | 7 |
|------------------|---|---|---|---|---|
| [X]x | XX% | XX% | XX% | XX% | XX% |
| [X]x | XX% | XX% | **XX%** | XX% | XX% |
| [X]x | XX% | XX% | XX% | XX% | XX% |
| [X]x | XX% | XX% | XX% | XX% | XX% |

### Breakeven Analysis
| Scenario | Breakeven Multiple | vs Entry | Probability |
|----------|-------------------|----------|-------------|
| 1.0x MOIC (Capital Return) | [X]x | ([X]x) below | XX% |
| [Target] IRR | [X]x | [+/-X]x vs entry | XX% |

### Dilution Assumptions
| Event | Dilution | Ownership After |
|-------|----------|-----------------|
| Entry | — | XX% |
| Future Round(s) | (X%) | XX% |
| Option Pool Refresh | (X%) | XX% |
| Exit Dilution | (X%) | XX% |
| **Fully Diluted Exit** | — | **XX%** |

# VALIDATION
- [ ] MOIC and IRR formulas are correct
- [ ] Dilution is accounted for
- [ ] Sensitivity ranges bracket realistic outcomes
- [ ] Breakeven multiples make sense
```

---

## Phase 3: IC Preparation Prompts

### P30: Investment Thesis Builder

```markdown
# ROLE
You are a PE principal constructing an investment thesis.

# CONTEXT
Company: [COMPANY_NAME]
Deal Type: [DEAL_TYPE]
Completed: P10 (Competitive), P23 (Returns)

# OBJECTIVE
Construct a compelling 3-pillar investment thesis.

# OUTPUT FORMAT
## Investment Thesis | [COMPANY_NAME]

### Thesis Summary (1 paragraph)
[COMPANY] represents an attractive [deal type] investment because [Pillar 1 headline], [Pillar 2 headline], and [Pillar 3 headline]. At [X]x [metric], the entry valuation provides a path to [X]x MOIC / [X]% IRR in the base case, with downside protection from [key protection factor].

### Pillar 1: [Market/Competitive Pillar Title]

**Claim**: [One sentence thesis statement]

**Evidence**:
1. [Data point 1 with source]
2. [Data point 2 with source]
3. [Data point 3 with source]

**Counter-argument**: [Obvious objection]

**Rebuttal**: [Why counter-argument is wrong or manageable]

**Implication for Returns**: [How this pillar impacts MOIC/IRR]

---

### Pillar 2: [Growth/Distribution Pillar Title]

**Claim**: [One sentence thesis statement]

**Evidence**:
1. [Data point 1 with source]
2. [Data point 2 with source]
3. [Data point 3 with source]

**Counter-argument**: [Obvious objection]

**Rebuttal**: [Why counter-argument is wrong or manageable]

**Implication for Returns**: [How this pillar impacts MOIC/IRR]

---

### Pillar 3: [Quality/Efficiency Pillar Title]

**Claim**: [One sentence thesis statement]

**Evidence**:
1. [Data point 1 with source]
2. [Data point 2 with source]
3. [Data point 3 with source]

**Counter-argument**: [Obvious objection]

**Rebuttal**: [Why counter-argument is wrong or manageable]

**Implication for Returns**: [How this pillar impacts MOIC/IRR]

---

### Thesis Validation Matrix
| Pillar | Evidence Strength | Counter-Argument Severity | Net Conviction |
|--------|-------------------|---------------------------|----------------|
| Pillar 1 | HIGH/MED/LOW | HIGH/MED/LOW | HIGH/MED/LOW |
| Pillar 2 | HIGH/MED/LOW | HIGH/MED/LOW | HIGH/MED/LOW |
| Pillar 3 | HIGH/MED/LOW | HIGH/MED/LOW | HIGH/MED/LOW |
| **Overall** | — | — | **HIGH/MED/LOW** |

### Differentiated Insight
**Consensus View**: [What most investors think]

**Our View**: [Where we disagree and why we're right]

# VALIDATION
- [ ] All 3 pillars have quantitative support
- [ ] Counter-arguments are addressed honestly
- [ ] Thesis ties to returns
- [ ] Differentiated insight is non-obvious
```

---

### P31: Risk Matrix Generator

```markdown
# ROLE
You are a PE associate creating a risk framework.

# CONTEXT
Company: [COMPANY_NAME]
Completed: P14 (Red Flags), P24 (Scenarios)

# OBJECTIVE
Create comprehensive risk matrix with mitigations.

# OUTPUT FORMAT
## Risk Matrix | [COMPANY_NAME]

### Risk Summary
| Risk Category | Count | Critical | Significant | Moderate |
|---------------|-------|----------|-------------|----------|
| Market | [X] | [X] | [X] | [X] |
| Competitive | [X] | [X] | [X] | [X] |
| Execution | [X] | [X] | [X] | [X] |
| Financial | [X] | [X] | [X] | [X] |
| Management | [X] | [X] | [X] | [X] |
| **Total** | **[X]** | **[X]** | **[X]** | **[X]** |

### Detailed Risk Matrix
| # | Risk | Category | Probability | Severity | Impact ($M) | Mitigation | Residual Risk |
|---|------|----------|-------------|----------|-------------|------------|---------------|
| 1 | [Risk] | [Cat] | XX% | HIGH | $[X]M | [Action] | MED |
| 2 | [Risk] | [Cat] | XX% | MED | $[X]M | [Action] | LOW |
| 3 | [Risk] | [Cat] | XX% | HIGH | $[X]M | [Action] | MED |
| ... | ... | ... | ... | ... | ... | ... | ... |

### Risk Heat Map
```
           Severity
             HIGH │  ●[R1]     ●[R3]
                  │
             MED  │     ●[R5]  ●[R2]     ●[R4]
                  │
             LOW  │  ●[R6]           ●[R7]
                  └────────────────────────────
                     LOW     MED      HIGH
                          Probability
```

### Top 5 Risks Deep Dive

#### Risk 1: [Risk Name]
- **Description**: [Detailed description]
- **Trigger Events**: [What would cause this]
- **Early Warning Signs**: [What to monitor]
- **Mitigation Actions**: [Specific steps]
- **Contingency Plan**: [If risk materializes]
- **Impact on Thesis**: [Which pillar affected]

[Repeat for Risks 2-5]

### Walk-Away Triggers
| Trigger | Threshold | Why Fatal |
|---------|-----------|-----------|
| [Trigger 1] | [Specific threshold] | [Why this kills the deal] |
| [Trigger 2] | [Specific threshold] | [Why this kills the deal] |

# VALIDATION
- [ ] All P14 red flags addressed
- [ ] Mitigations are specific and actionable
- [ ] Probability estimates are justified
- [ ] Walk-away triggers are clear
```

---

### P32: "What Must Be True"

```markdown
# ROLE
You are a PE principal stress-testing investment assumptions.

# CONTEXT
Company: [COMPANY_NAME]
Completed: P30 (Thesis), P31 (Risk Matrix)

# OBJECTIVE
Identify critical assumptions that must hold for base case returns.

# OUTPUT FORMAT
## "What Must Be True" | [COMPANY_NAME]

### Critical Assumptions Summary

For base case returns of [X]x MOIC / [X]% IRR, the following must be true:

| # | Assumption | Current Evidence | Confidence | Diligence to Validate |
|---|------------|------------------|------------|----------------------|
| 1 | [Assumption] | [Evidence] | HIGH/MED/LOW | [Validation method] |
| 2 | [Assumption] | [Evidence] | HIGH/MED/LOW | [Validation method] |
| 3 | [Assumption] | [Evidence] | HIGH/MED/LOW | [Validation method] |
| 4 | [Assumption] | [Evidence] | HIGH/MED/LOW | [Validation method] |
| 5 | [Assumption] | [Evidence] | HIGH/MED/LOW | [Validation method] |

### Assumption Details

#### Assumption 1: [Growth Assumption]
**What must be true**: [Specific metric/threshold]
**Current evidence**: [Data supporting this]
**Sensitivity**: If wrong, returns become [X]x MOIC / [X]% IRR
**Validation plan**: [How to verify before close]

#### Assumption 2: [Market Assumption]
**What must be true**: [Specific condition]
**Current evidence**: [Data supporting this]
**Sensitivity**: If wrong, returns become [X]x MOIC / [X]% IRR
**Validation plan**: [How to verify before close]

#### Assumption 3: [Exit Assumption]
**What must be true**: [Exit multiple/timing]
**Current evidence**: [Comps, precedents]
**Sensitivity**: If wrong, returns become [X]x MOIC / [X]% IRR
**Validation plan**: [How to verify before close]

#### Assumption 4: [Execution Assumption]
**What must be true**: [Operational metric]
**Current evidence**: [Historical performance]
**Sensitivity**: If wrong, returns become [X]x MOIC / [X]% IRR
**Validation plan**: [How to verify before close]

#### Assumption 5: [Competitive Assumption]
**What must be true**: [Competitive condition]
**Current evidence**: [Market data]
**Sensitivity**: If wrong, returns become [X]x MOIC / [X]% IRR
**Validation plan**: [How to verify before close]

### Assumption Failure Matrix
| If This Fails... | ...Returns Become | ...And We Should |
|------------------|-------------------|------------------|
| Assumption 1 | [X]x / [X]% | [Action] |
| Assumption 2 | [X]x / [X]% | [Action] |
| Assumption 3 | [X]x / [X]% | [Action] |
| Assumption 4 | [X]x / [X]% | [Action] |
| Assumption 5 | [X]x / [X]% | [Action] |

### Conviction Scorecard
| Assumption | Confidence | Weight | Weighted Score |
|------------|------------|--------|----------------|
| Assumption 1 | [1-5] | XX% | [X.X] |
| Assumption 2 | [1-5] | XX% | [X.X] |
| Assumption 3 | [1-5] | XX% | [X.X] |
| Assumption 4 | [1-5] | XX% | [X.X] |
| Assumption 5 | [1-5] | XX% | [X.X] |
| **Overall Confidence** | — | 100% | **[X.X]/5** |

# VALIDATION
- [ ] All critical assumptions identified
- [ ] Sensitivities are quantified
- [ ] Validation plans are actionable
- [ ] Overall confidence score makes sense
```

---

### P35: Executive Summary

```markdown
# ROLE
You are a PE principal writing the executive summary.

# CONTEXT
Company: [COMPANY_NAME]
Completed: All prior prompts

# OBJECTIVE
Create 1-page executive summary for IC.

# OUTPUT FORMAT
## Executive Summary | [COMPANY_NAME]

### Deal Overview
| Field | Value |
|-------|-------|
| Company | [COMPANY_NAME] |
| Sector | [Sector] |
| Deal Type | [Growth Equity / LBO / Venture] |
| Recommendation | **[BUY / QUALIFIED BUY / PASS]** |

### Investment Terms
| Metric | Value |
|--------|-------|
| Investment Size | $[X]M |
| Valuation | $[X]M [pre/post]-money |
| Ownership | XX% |
| Entry Multiple | [X]x [Revenue/EBITDA] |

### Key Metrics
| Metric | LTM | Projection (Exit Year) |
|--------|-----|------------------------|
| Revenue | $[X]M | $[X]M |
| Growth | XX% | XX% CAGR |
| Gross Margin | XX% | XX% |
| EBITDA Margin | XX% | XX% |
| NDR (if SaaS) | XXX% | XXX% |

### Base Case Returns
| Metric | Value |
|--------|-------|
| MOIC | **[X]x** |
| IRR | **XX%** |
| Exit Year | [Year] |
| Exit Multiple | [X]x |

### Investment Thesis (3 Pillars)
1. **[Pillar 1 Title]**: [One sentence summary]
2. **[Pillar 2 Title]**: [One sentence summary]
3. **[Pillar 3 Title]**: [One sentence summary]

### Key Risks
1. **[Risk 1]** (Probability: XX%, Severity: HIGH) — Mitigation: [Brief]
2. **[Risk 2]** (Probability: XX%, Severity: MED) — Mitigation: [Brief]
3. **[Risk 3]** (Probability: XX%, Severity: MED) — Mitigation: [Brief]

### "What Must Be True"
1. [Critical assumption 1]
2. [Critical assumption 2]
3. [Critical assumption 3]

### Scenario Summary
| Scenario | Probability | MOIC | IRR |
|----------|-------------|------|-----|
| Bull | XX% | [X]x | XX% |
| **Base** | XX% | **[X]x** | **XX%** |
| Bear | XX% | [X]x | XX% |
| Blended | 100% | [X]x | XX% |

### Diligence Gates (Conditional Buy)
| Gate | Criteria | Status |
|------|----------|--------|
| Gate 1 | [Condition] | Pending |
| Gate 2 | [Condition] | Pending |

### Recommendation
[1-2 sentences restating recommendation with key caveat if any]

---
*Prepared by: [Analyst Name] | Date: [Date] | Status: [Draft/Final]*

# VALIDATION
- [ ] All key metrics included
- [ ] Returns match model
- [ ] Thesis is clear and compelling
- [ ] Risks and gates are actionable
- [ ] Fits on one page
```

---

## Appendix: Quick Reference

### Prompt Dependency Map
```
P00 → P01 → P02 → P03 → P04
              ↓
        ┌─────┼─────┬─────┐
        ↓     ↓     ↓     ↓
       P10   P11   P12   P14
        └─────┼─────┘
              ↓
             P13
              ↓
        ┌─────┴─────┐
        ↓           ↓
       P20 ────→ P21 ────→ P22 ────→ P23 ────→ P24
                                      ↓
                            ┌─────────┴─────────┐
                            ↓         ↓         ↓
                           P30 ───→ P31 ───→ P32
                            └─────────┬─────────┘
                                      ↓
                                     P33 → P34 → P35
```

### Phase Timing Guide
| Phase | Prompts | Typical Duration | Output |
|-------|---------|------------------|--------|
| 0: Foundation | P00-P04 | 4-8 hours | Company understanding |
| 1: Analysis | P10-P14 | 8-16 hours | Due diligence insights |
| 2: Modeling | P20-P24 | 8-16 hours | Financial projections |
| 3: IC Prep | P30-P35 | 8-16 hours | IC materials |

---

*Prompt Library Version: 1.0.0*
*Total Prompts: 20 (Core Set)*
*Full Library: 52 prompts available in extended version*
