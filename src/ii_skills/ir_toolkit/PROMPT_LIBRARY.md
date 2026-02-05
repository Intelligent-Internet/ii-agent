# Prompt Library — Infrastructure IR

*Ready-to-use prompts for common IR analysis requests. 28 prompts covering core deliverables, interview prep, specialized analyses, and LP/GP term negotiation.*

---

## Core Deliverables (Prompts 1-12)

### 1. LP Quarterly Update

**Prompt:**
```
Create an infrastructure LP quarterly update. Use Excel tables for fund
performance, cash flows, and asset KPIs, and produce matching slides.
Highlight contracted revenue %, inflation linkage, and regulatory exposure.

Inputs needed:
- Fund name and vintage
- Reporting period
- Performance metrics (IRR, DPI, RVPI, TVPI)
- Cash flow data (calls, distributions)
- Top 3 asset KPIs
```

**Sample Output:**
- Excel: Fund Performance Table (IRR/DPI/RVPI/TVPI by fund)
- Slide: "Fund returns remain in top-quartile driven by stable cash yield"

---

### 2. Fundraising Narrative

**Prompt:**
```
Build a fundraising deck outline for a global infrastructure strategy.
Provide Excel analysis for track record and portfolio mix and pair each
table with a slide. Include term sheet summary and ESG framework.

Inputs needed:
- Fund strategy and target size
- Historical track record
- Current portfolio composition
- Proposed terms (fees, carry, hurdle)
```

**Sample Output:**
- Excel: Portfolio mix by sector/region
- Slide: "Diversified portfolio reduces regulatory concentration risk"

---

### 3. Asset Performance Deep Dive

**Prompt:**
```
Generate an asset KPI dashboard (availability, utilization, contracted
coverage) and a slide summarizing top 3 KPIs for our largest asset.

Inputs needed:
- Asset name and type
- Quarterly KPI data (8 quarters)
- Contract details (tenor, counterparty)
- Safety metrics
```

**Sample Output:**
- Excel: KPI table with YoY deltas
- Slide: "Availability improved to 98.4% post-maintenance"

---

### 4. Downside Case Stress Test

**Prompt:**
```
Model a downside case with a 100 bps discount rate increase and a 10%
merchant price decline. Provide Excel sensitivity and a paired slide.

Inputs needed:
- Current NAV and discount rate
- Revenue split (contracted vs. merchant)
- Sensitivity parameters
```

**Sample Output:**
- Excel: Sensitivity grid for NAV
- Slide: "NAV remains resilient with <5% downside under stress"

---

### 5. DDQ Response Pack

**Prompt:**
```
Prepare DDQ tracker Excel outputs and a summary slide showing open
items, owners, and dates.

Inputs needed:
- DDQ question list
- Current status by question
- Owners and target dates
```

**Sample Output:**
- Excel: DDQ tracker table
- Slide: "85% of DDQ items closed; 3 high-priority pending"

---

### 6. NAV Roll-Forward

**Prompt:**
```
Build a NAV roll-forward with prior NAV, contributions, distributions,
valuation changes, and FX impact. Provide slide headline and waterfall chart.

Inputs needed:
- Prior period NAV
- Capital activity (calls, distributions)
- Valuation changes by driver
- FX impact
```

**Sample Output:**
- Excel: NAV driver breakdown table
- Slide: "NAV growth driven by cash yield and FX tailwinds"

---

### 7. Regulatory Reset View

**Prompt:**
```
Build a regulatory reset calendar for our regulated assets with upcoming
reset dates and mitigation actions. Output the table and a timeline slide.

Inputs needed:
- Asset list (regulated only)
- Reset dates and regulatory body
- Current rate base
- Mitigation actions
```

**Sample Output:**
- Excel: Reset schedule by asset and year
- Slide: "Regulatory resets are back-weighted with mitigants in place"

---

### 8. Distribution Coverage Analysis

**Prompt:**
```
Create a distribution coverage analysis by quarter (cash generated vs.
distributions) and pair it with a coverage slide.

Inputs needed:
- Quarterly cash generation (8 quarters)
- Quarterly distributions
- Target coverage ratio
```

**Sample Output:**
- Excel: Coverage ratio table with 8-quarter trend
- Slide: "Coverage remains >1.2x through the period"

---

### 9. Leverage & Coverage Profile

**Prompt:**
```
Build a leverage profile showing Debt/EBITDA, DSCR, and debt maturity
ladder with covenant headroom. Provide Excel and paired slide.

Inputs needed:
- Current debt by facility
- EBITDA (trailing 12 months)
- Debt service schedule
- Covenant thresholds
```

**Sample Output:**
- Excel: Leverage metrics + maturity ladder
- Slide: "Leverage remains conservative with strong coverage ratios"

---

### 10. Term Sheet Summary

**Prompt:**
```
Draft a term sheet summary table (fees, carry, hurdle, governance) and
provide a paired slide headline.

Inputs needed:
- Management fee structure
- Carry and hurdle
- Key LP protections
- Governance provisions
```

**Sample Output:**
- Excel: Term sheet table with key terms
- Slide: "Terms provide strong governance and alignment"

---

### 11. Peer Benchmarking

**Prompt:**
```
Create a peer benchmark analysis comparing fund performance to quartiles.
Include infra-specific adjustments for cash yield profile.

Inputs needed:
- Fund performance metrics
- Peer universe data
- Vintage adjustment factors
```

**Sample Output:**
- Excel: Performance vs. quartile table
- Slide: "Top-quartile performance vs. infrastructure peer group"

---

### 12. ESG Impact Summary

**Prompt:**
```
Build an ESG metrics dashboard with emissions, safety, and community
impact. Include infra-specific KPIs like grid reliability.

Inputs needed:
- Emissions data (Scope 1, 2, 3)
- Safety metrics (TRIR, LTIR)
- Community/social metrics
- Environmental certifications
```

**Sample Output:**
- Excel: ESG scorecard table
- Slide: "Strong ESG performance across safety and emissions"

---

## Additional Analysis Prompts (Prompts 13-18)

### 13. Fund Economics Model

**Prompt:**
```
Build a fund economics model showing management fees, carried interest,
and net returns to LPs over the fund life. Include J-curve visualization.

Inputs needed:
- Fund size and GP commitment
- Fee structure (mgmt fee, carry, hurdle)
- Projected deployment pace
- Projected exit timing and multiples

Create:
1. Capital account with annual calls/distributions
2. Fee calculations (mgmt fee with step-down, carry waterfall)
3. Gross vs. net returns comparison
4. J-curve chart data
```

**Sample Output:**
- Excel: Full fund model with fee waterfall
- Slide: "Net returns of 11.5% after fees vs. 13.0% gross"

---

### 14. LP Communication Draft

**Prompt:**
```
Draft an LP-facing communication for [quarterly update / fundraising
outreach / exit announcement]. Tone should be professional and factual.

Inputs needed:
- Communication type and purpose
- Key metrics to highlight
- Any issues to address proactively
- Call to action (if applicable)

Format:
- Subject line (for email)
- Opening paragraph (key message)
- Performance summary (with data)
- Portfolio/activity update
- Outlook and next steps
- Closing and contact information
```

**Sample Output:**
- 1-2 page LP letter or email

---

### 15. Asset One-Pager

**Prompt:**
```
Create a single-page asset summary for LP reporting or data room.
Include business overview, KPIs, value creation, and outlook.

Inputs needed:
- Asset name, sector, geography
- Acquisition details (date, price, multiple)
- Current financials (revenue, EBITDA, margins)
- Operational KPIs (availability, contracted %)
- Value creation initiatives
- Exit pathway and timing

Format (single page):
- Header: Asset name, sector, geography
- Business Overview (3-4 sentences)
- Financial Highlights (entry vs. current table)
- Operational KPIs (key metrics)
- Value Creation (3 bullet points)
- Status & Outlook (2-3 sentences)
```

**Sample Output:**
- 1-page asset summary PDF-ready

---

### 16. Co-Investment Memo

**Prompt:**
```
Draft a co-investment opportunity memo for LPs considering a direct
investment alongside the fund.

Inputs needed:
- Asset overview and investment thesis
- Transaction terms (size, structure, timeline)
- Co-invest allocation and minimum
- Risk factors and mitigants
- GP track record with similar assets

Format:
1. Executive Summary
2. Asset Overview
3. Investment Thesis
4. Transaction Terms
5. Co-Invest Terms
6. Risks and Mitigants
7. Next Steps
```

**Sample Output:**
- 3-5 page co-invest memo

---

### 17. Annual Meeting Deck

**Prompt:**
```
Create an annual meeting presentation for existing LPs. Cover fund
performance, portfolio review, market outlook, and strategic priorities.

Inputs needed:
- Annual performance summary
- Portfolio asset updates
- Market and competitive landscape
- Strategic priorities for coming year
- Q&A preparation topics

Slide sequence:
1. Agenda
2. Fund Performance Summary
3-5. Portfolio Asset Reviews (top 3-5 assets)
6. Cash Flow Summary
7. Valuation & NAV
8. Market Outlook
9. Strategic Priorities
10. Q&A / Discussion
```

**Sample Output:**
- 10-12 slide annual meeting deck

---

### 18. Crisis Communication

**Prompt:**
```
Draft a crisis communication for LPs regarding [asset incident /
performance issue / regulatory development / market event].

Inputs needed:
- Nature of the issue
- Impact on fund/asset
- Actions taken / mitigants
- Outlook and next steps

Format:
- Immediate acknowledgment of issue
- Facts (what happened, when, impact)
- Response (actions taken)
- Mitigation (how we're protecting value)
- Outlook (expected resolution, timeline)
- Commitment (ongoing communication cadence)

Tone: Transparent, proactive, accountable
```

**Sample Output:**
- 1-page crisis communication

---

## Interview Prep Prompts (Prompts 19-22)

### 19. Q&A Preparation Document

**Prompt:**
```
Create a Q&A preparation document for my IR case interview. Include
questions about my deliverables, fund mechanics, LP relations, and
role fit.

KEY METRICS:
[PASTE YOUR KEY METRICS TABLE HERE]

Generate 50 questions across these categories:

1. ABOUT YOUR DELIVERABLES (10 questions):
   "Walk me through the pitchbook you created"
   "Why did you choose this slide sequence?"
   "How would you pitch this fund in 60 seconds?"

2. FUND MECHANICS (10 questions):
   "Explain the management fee calculation"
   "Walk me through the carried interest waterfall"
   "What is DPI and why do LPs care about it?"

3. LP RELATIONS & COMMUNICATION (10 questions):
   "How would you handle an LP who is unhappy with performance?"
   "Describe your approach to a quarterly investor update"
   "What makes a good fundraising pitchbook?"

4. INFRA-SPECIFIC (10 questions):
   "What is contracted vs. merchant revenue?"
   "How do regulatory resets affect infrastructure returns?"
   "What is DSCR and why is it important?"

5. ROLE FIT & MOTIVATION (10 questions):
   "Why investor relations vs. the deal team?"
   "What skills transfer to IR?"
   "Where do you see IR career progression?"

For EACH question provide:
- Model answer (2-4 sentences, uses real data from case)
- Key numbers to cite
- Common mistakes to avoid
```

**Sample Output:**
- 50-question Q&A preparation document

---

### 20. One-Page Cheat Sheet

**Prompt:**
```
Create a one-page cheat sheet with EVERY number I need memorized for
the interview. Format to fit on one printed page.

KEY METRICS:
[PASTE YOUR KEY METRICS TABLE HERE]

Include:

FUND SNAPSHOT:
Fund: ___ | Vintage: ___ | Strategy: ___ | Size: $___M
GP: ___ | AUM: $___B | GP Commitment: $___M (___%)

FEE STRUCTURE:
Mgmt Fee: ___% on ___ | Carry: ___% | Hurdle: ___% | Waterfall: ___

PERFORMANCE (ALL FUNDS):
| Fund | Vintage | Size | Net IRR | Net MOIC | DPI | TVPI |

CURRENT PORTFOLIO (top 5 assets):
| Asset | Sector | Cost | Value | MOIC | Contracted % |

INFRA-SPECIFIC:
Contracted Revenue: ___% | Cash Yield: ___% | Avg DSCR: ___x

60-SECOND FUND PITCH:
[Write out a verbal pitch of the fund]

KEY LP CONCERNS & RESPONSES:
1. ___
2. ___
3. ___

BENCHMARKS:
Strategy median Net IRR: ___% | Top quartile: ___%
```

**Sample Output:**
- 1-page cheat sheet

---

### 21. Mock Interview Simulation

**Prompt:**
```
Conduct a mock interview. You are the Head of IR at [target firm],
interviewing me for an IR Analyst/Associate position. Ask me 15
questions, one at a time:

ROUND 1 — WARM-UP (3 questions):
1. "Tell me about yourself and why you're interested in IR"
2. "Walk me through the work you did on this case study"
3. "How would you pitch this fund to an LP in 60 seconds?"

ROUND 2 — DELIVERABLE DEEP DIVE (4 questions):
4-7. Questions about specific choices in the pitchbook, data
presentation, and written communications

ROUND 3 — IR KNOWLEDGE (4 questions):
8-11. Fund mechanics, LP relations, fundraising process,
communication scenarios

ROUND 4 — JUDGMENT & FIT (4 questions):
12-15. "What would you do differently with more time?"
"How would you tailor this for different LP types?"
"Why IR instead of the deal team?"

After each answer, score 1-5 and provide:
- What was good
- What was missing
- The "perfect answer" for comparison

Focus scoring on: communication clarity, accuracy,
professionalism, and LP-centricity.
```

**Sample Output:**
- Interactive mock interview session

---

### 22. 60-Second Fund Pitch

**Prompt:**
```
Create a 60-second verbal pitch for this infrastructure fund.
Structure it for an LP meeting opening.

KEY METRICS:
[PASTE YOUR KEY METRICS TABLE HERE]

Format:

[Opening hook - 10 seconds]
"[Fund Name] is a $[X]B infrastructure fund focused on [strategy]..."

[Track record - 15 seconds]
"Across [X] funds, we've generated [X]% net IRR, top-quartile vs.
Cambridge benchmarks, with [X]x DPI reflecting real cash returns..."

[Differentiation - 15 seconds]
"What sets us apart is [key differentiator]. Our portfolio is [X]%
contracted with [X]% inflation linkage, providing..."

[Current opportunity - 10 seconds]
"Fund IV is [X]% deployed with a strong pipeline in [sectors].
We're seeing attractive entry points at [X]x..."

[Ask - 10 seconds]
"We'd welcome the opportunity to discuss a $[X]M commitment
and how [Fund] fits your infrastructure allocation."

Provide:
- Full 60-second script
- Key numbers to emphasize
- Backup data points if asked follow-up
```

**Sample Output:**
- 60-second pitch script with backup points

---

## Anki Flashcard Generation (Prompts 23-24)

### 23. IR Fundamentals Flashcards

**Prompt:**
```
Create Anki flashcards covering IR fundamentals. TSV format (front\tback).
Generate 80 cards across these categories:

1. FUND MECHANICS (20 cards):
   "What is a management fee step-down?"
   "What is DPI vs. TVPI?"
   "Explain European vs. American waterfall"
   "What is a GP commitment and why does it matter?"
   "What is a key-man provision?"
   "What is preferred return / hurdle rate?"

2. INFRA-SPECIFIC CONCEPTS (20 cards):
   "What is contracted vs. merchant revenue?"
   "What is DSCR?"
   "What are regulatory resets?"
   "What is availability in infrastructure?"
   "What is WACL (weighted average contract life)?"
   "What is CPI linkage?"

3. IR ROLE KNOWLEDGE (15 cards):
   "What does an IR analyst do day-to-day?"
   "What is a DDQ?"
   "What is a pitchbook vs. a tearsheet?"
   "Describe the fundraising process"
   "What is an LPAC?"

4. LP TYPES & CONCERNS (15 cards):
   "What are the main LP types?"
   "What do pensions prioritize?"
   "What do endowments prioritize?"
   "What are common LP objections?"

5. COMMUNICATION SKILLS (10 cards):
   "How to pitch a fund in 60 seconds"
   "How to handle a tough LP question"
   "Key differences between marketing and reporting"

Format: question\tanswer
```

**Sample Output:**
- TSV file with 80 flashcards

---

### 24. Case-Specific Flashcards

**Prompt:**
```
Create Anki flashcards for this specific case study.
TSV format (front\tback). Generate 50 cards.

KEY METRICS:
[PASTE YOUR KEY METRICS TABLE HERE]

Categories:

1. THIS FUND'S DATA (20 cards):
   "What is [Fund Name]'s Fund III net IRR?"
   "What is the DPI for Fund II?"
   "What is the current fund size target?"
   "What is the GP commitment?"
   "Name the top 3 portfolio assets"

2. DELIVERABLE CONTENT (15 cards):
   "What are the key slides in the pitchbook?"
   "What is the main message of slide 5?"
   "What are the fund's top 3 differentiators?"

3. INTERVIEW ANSWERS (15 cards):
   "How would you pitch this fund in 60 seconds?"
   "Why is DPI important for this fund?"
   "What are the main risks and mitigants?"
   "How does this fund compare to benchmarks?"

Study schedule:
- Night before: Full deck review
- Morning of: #funddata + #pitchbook only
- 1 hour before: Cheat sheet cards only

Format: question\tanswer
```

**Sample Output:**
- TSV file with 50 case-specific flashcards

---

## LP/GP Term Negotiation Prompts (Prompts 25-28)

### 25. Term Sheet Red-Flag Scan

**Prompt:**
```
Scan the attached term sheet or LPA excerpt for LP red flags. For each
flagged item, provide the clause reference, a plain-language risk
description, ILPA benchmark comparison, and a suggested revision.

Inputs needed:
- Term sheet text or LPA excerpt
- Fund strategy and vintage (for market comparison)
- Any known side-letter provisions

Output:
1. Red-Flag Register (table: # | Clause | Risk | Severity | ILPA Benchmark | Suggested Revision)
2. One-page Negotiation Priorities summary (must / should / nice-to-have)
3. Overall LP-Friendliness score (0-100)

Key areas to scan:
- Management fee basis and step-down
- Carry waterfall and clawback
- Key-person and no-fault divorce thresholds
- Valuation policy and LP oversight
- Co-invest economics and allocation
- Recycling and extension provisions
- Related-party and conflict provisions
```

**Sample Output:**
- Red-Flag Register with 8-12 flagged items
- Negotiation Priorities one-pager
- LP-Friendliness score with subscores

---

### 26. Negotiation Priorities Memo

**Prompt:**
```
Using the term extraction and red-flag analysis, draft a one-page
Negotiation Priorities memo for the LP investment committee.

Inputs needed:
- Red-Flag Register from Prompt 25
- LP-Friendliness and Alignment scores
- Prior fund terms (if available, for comparison)
- LP's specific negotiation priorities or constraints

Format:
1. Composite Scores (LP-Friendliness, GP-Flexibility, Alignment)
2. MUST NEGOTIATE items (critical/high severity)
3. SHOULD NEGOTIATE items (medium severity)
4. NICE-TO-HAVE improvements
5. Term Comparison vs. Prior Fund (table)
6. Recommended side-letter requests

Tone: Factual, action-oriented, suitable for investment committee review.
```

**Sample Output:**
- 1-page negotiation memo with prioritized action items

---

### 27. Term Comparison (Fund vs. Peers)

**Prompt:**
```
Create a side-by-side comparison of fund terms against peer funds
and ILPA Principles 3.0 benchmarks.

Inputs needed:
- Target fund term sheet
- 2-3 peer fund term sheets (or market median data)
- ILPA Principles reference points

Output Excel table:
| Term | Target Fund | Peer 1 | Peer 2 | Market Median | ILPA Best Practice | Assessment |

Cover these fields:
- Management fee (commitment period + post-investment)
- Carried interest % and hurdle rate
- Catch-up structure
- GP commitment ($ and %)
- Key-person provision
- No-fault divorce threshold
- Fund life and extension options
- Recycling provisions
- Co-invest fee/carry policy
- Valuation policy
- Transfer restrictions
- LPAC rights

Assessment column: "LP-favorable" / "Market" / "GP-favorable" / "Red flag"

Paired slide: Summary heat map showing LP vs. GP positioning by term category.
```

**Sample Output:**
- Excel: Term comparison table (12+ rows)
- Slide: "Fund IV terms are market-standard on economics, below-market on governance"

---

### 28. LP-Friendliness Scorecard

**Prompt:**
```
Score the fund's terms on LP-friendliness across four dimensions.
Provide an explainable scorecard suitable for LP committee reporting.

Inputs needed:
- Complete term sheet or LPA summary
- Fund strategy and vintage
- Market benchmarks (optional — will use defaults if not provided)

Scoring Framework:
1. ECONOMICS (30% weight): Fee level, carry alignment, GP co-invest, fee offsets
2. GOVERNANCE (30% weight): Key-person, no-fault, LPAC scope, removal rights
3. TRANSPARENCY (20% weight): Reporting, valuation policy, audit, information rights
4. LIQUIDITY (20% weight): Transfer, secondary, distribution mechanics, lock-up

For each dimension:
- Score 1-5 with rationale
- Benchmark vs. ILPA and market median
- Specific items driving the score

Output:
1. Scorecard table (Dimension | Score | Weight | Weighted | Key Drivers)
2. Composite LP-Friendliness Score (0-100)
3. Radar chart data (4-axis)
4. 3-5 sentence executive summary
5. Paired slide with radar chart and composite score
```

**Sample Output:**
- Excel: Scored rubric with weighted composite
- Slide: "LP-Friendliness: 72/100 — strong economics, governance needs improvement"

---

## Prompt Structure Template

For any IR analysis, use this structure:

```
[Action]: Create/Build/Generate/Analyze
[Module]: [specific module from CAPABILITIES.md]
[Data requirements]: [list specific inputs]
[Output format]: Excel table + paired slide
[Infra nuance]: [specific infra elements to highlight]
```

---

## Quick Reference: Prompt Routing

| Prompt | Environment | Primary Output |
|--------|-------------|----------------|
| 1-12 | Excel + Web | Excel tables + slides |
| 13 | Excel | Fund model |
| 14, 16, 18 | Web | Written communications |
| 15, 17 | Web | Presentations |
| 19-22 | Web | Interview prep docs |
| 23-24 | Web | Anki TSV files |
| 25 | Excel + Web | Red-flag register + negotiation priorities |
| 26 | Web | Negotiation priorities memo |
| 27 | Excel + Web | Term comparison table + slide |
| 28 | Excel + Web | LP-friendliness scorecard + slide |

---

*Version: 2.0 | Last Updated: February 2026*
*28 prompts covering core deliverables, additional analysis, interview preparation, and LP/GP term negotiation*
