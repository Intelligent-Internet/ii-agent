# IR Case Guide — Infrastructure (Private IR)

*Comprehensive execution guide for infrastructure investor relations case studies and deliverables.*

---

## READ THIS FIRST: IR vs IC Decks

**This guide is for Investor Relations (IR) roles — NOT investing/deal team roles.**

IR deliverables are fundamentally different from PE investing case studies. You are NOT building an LBO model or writing an Investment Committee memo. You are being tested on your ability to **communicate the fund's story to LPs, produce fundraising materials, handle investor reporting, and manage LP relationships.**

### IC Deck vs LP Pitchbook Comparison

| Dimension | IC Deck (Investing Role) | LP Pitchbook (IR Role) |
|-----------|------------------------|----------------------|
| **Audience** | 5-10 IC members who read the memo | Prospective LPs (pension CIOs, endowment heads, FoF managers) |
| **Purpose** | Get approval to invest in a single deal | Get LPs to commit capital to the entire fund |
| **Slide titles** | Action-oriented conclusions ("8% CAGR Drives 18% IRR") | Descriptive / informational ("Fund Performance Summary") |
| **Tone** | Analytical, thesis-driven, confrontational | Professional, relationship-building, trust-establishing |
| **Data focus** | Single deal returns (IRR, MOIC, sensitivity) | Fund-level track record (Net IRR, DPI, TVPI, benchmarks) |
| **Slides about** | Company analysis, LBO structure, value creation | Firm overview, team, strategy, track record, fund terms |
| **Design** | Functional, dense, data-forward | Polished but understated, brand-consistent, clean |
| **Call to action** | "We recommend investing $XM" | "We invite you to commit to Fund IV" |
| **Who presents** | Junior analyst/associate to IC | MD/Partner to LP, supported by IR |

**The cardinal rule for LP pitchbooks:** You are selling the GP — the firm, the team, the strategy, the process — not a single deal. Individual asset case studies appear as portfolio examples supporting the broader narrative.

### What IR Case Studies Typically Involve

- Reading fund materials and creating LP-facing presentation slides
- Basic Excel work — summarizing fund/investment data aesthetically
- Writing LP-facing communications (emails, update letters, cover notes)
- Reformatting or polishing existing slides for roadshows
- Answering DDQ-style questions (fund formation, fee structure, track record)
- Building or interpreting fund models (economics, drawdowns, distributions, J-curve)

### What IR Case Studies Are NOT

- NOT an LBO / leveraged buyout model
- NOT an Investment Committee memo with "invest/pass" recommendation
- NOT a deep-dive company valuation
- NOT a DCF or comparable companies analysis

---

## Environment Routing

| Environment | Best For | Examples |
|-------------|----------|----------|
| **Claude Web** (claude.ai) | Writing LP communications, slide content, DDQ answers, research, PPTX generation | Drafting quarterly letter, slide narrative, market research |
| **Claude for Excel** | Fund model work, track record formatting, performance tables, chart-ready data | NAV roll-forward, KPI dashboard, fee calculations |

**Routing Logic:**
- If the task produces or modifies an **.xlsx workbook** → Claude for Excel
- If the task produces **text, slides, memos, emails, .pptx** → Claude Web
- If the task requires **web search or research** → Claude Web
- If the task reads Excel output to write about it → Claude Web (reference the Excel)

### Data Transfer Protocols

**📊→🌐** (Excel to Web): Copy text/tables from Excel sidebar → paste into Claude Web prompt.

**🌐→📊** (Web to Excel): Copy structured data from Claude Web → paste into Excel sidebar.

**Key Metrics Table Concept:**
Maintain a single "Key Metrics Table" as your source of truth. Update it after every Excel change. Paste it into every Claude Web prompt that needs numbers.

```
KEY METRICS TABLE (as of [date])
Fund: [Name] | Vintage: [Year] | Strategy: [Description]
Size: $[X]M | GP Commitment: $[X]M ([X]%)

Performance:
| Fund | Vintage | Size | Net IRR | Net MOIC | DPI | TVPI |
|------|---------|------|---------|----------|-----|------|
| I    | 20XX    | $XM  | XX.X%   | X.Xx     | X.Xx| X.Xx |
| II   | 20XX    | $XM  | XX.X%   | X.Xx     | X.Xx| X.Xx |

Fee Structure:
Mgmt Fee: X.X% | Carry: XX% | Hurdle: X% | Waterfall: [Type]
```

---

## Phased Workflow

### Phase 0: Triage & Intake (0-1 hours)

**Goal:** Understand what you've been given and build your execution plan.

**Steps:**
1. **Material Inventory** — Classify all files (case instructions, pitchbook, performance data, DDQ, etc.)
2. **Data Reconnaissance** — Map the Excel workbook (tabs, key data points, formulas vs hardcodes)
3. **Identify Case Type** — LP update, fundraising, DDQ response, annual meeting, crisis comms
4. **Extract Deliverables** — What specifically must you produce?
5. **Build Execution Plan** — Map deliverables to time blocks

**Output:** Triage report + execution plan

---

### Phase 1: Data Foundation (1-4 hours)

**Goal:** Clean, accurate fund data in Excel; key metrics extracted for all other deliverables.

**Steps:**
1. **Extract Fund Data** — From case materials, extract fund overview, economics, performance, portfolio
2. **Build Excel Foundation** — Create/update Fund Summary, Portfolio Summary, Track Record tabs
3. **Build Fund Model** (if required) — Capital account, fee calculations, return metrics
4. **Extract Chart Data** — Format data for presentation visuals
5. **Run Quality Gate 1** — Validate all data (see Quality Gates below)

**Output:** Clean Excel workbook + Key Metrics Table

---

### Phase 2: Research & Narrative (4-8 hours)

**Goal:** Develop the fund story and draft key written deliverables.

**Steps:**
1. **Strategy Research** — Market context, benchmarks, competitive landscape
2. **DDQ Preparation** (if required) — Firm overview, strategy, terms, track record, team, risk
3. **LP Communication Draft** — Quarterly update, fundraising email, or cover letter

**Output:** Research brief + DDQ drafts + LP communication draft

---

### Phase 3: LP Presentation (8-16 hours)

**Goal:** Professional LP-facing presentation slides.

**Steps:**
1. **Slide Content Generation** — Full content for each slide (title, message, data, visual concept, speaker notes)
2. **PPTX Generation** — Create the actual PowerPoint file
3. **Presentation QA** — Data accuracy, LP communication standards, visual quality

**Output:** Polished .pptx file

---

### Phase 4: Polish & Supporting Deliverables (16-24 hours)

**Goal:** Final formatting, portfolio summaries, Q&A preparation.

**Steps:**
1. **Excel Final Formatting** — Professional styling, print areas, validation
2. **Portfolio One-Pagers** (if required) — Asset-by-asset summaries
3. **Q&A Preparation** — Interview prep document
4. **Cheat Sheet** — One-page summary for interview

**Output:** Polished Excel + supporting documents

---

### Phase 5: Final QA & Interview Prep (24-36 hours)

**Goal:** Cross-deliverable consistency and interview readiness.

**Steps:**
1. **Consistency Audit** — Verify all numbers match across Excel, slides, written docs
2. **Mock Interview** — Practice walkthrough and Q&A

**Output:** Validated deliverables + interview readiness

---

## Rapid Path (6-Hour Submission)

For time-constrained submissions, execute only:

| Hour | Focus | Deliverable |
|------|-------|-------------|
| 0-0.5 | Triage + Data Map | Execution plan |
| 0.5-1.5 | Fund data extraction + Excel build | Core Excel tabs |
| 1.5-2.5 | Chart data + data audit | Validated metrics |
| 2.5-4 | Slide content + PPTX | Core presentation |
| 4-5 | LP communication (if required) | Written deliverable |
| 5-5.5 | Cheat sheet | Interview prep |
| 5.5-6 | Consistency check | Final validation |

**Cut list:** Fund model, DDQ, portfolio one-pagers, Anki decks, mock interview

---

## Quality Gates

### Quality Gate 1: Data Validation (After Phase 1)

Run these checks on all Excel tabs:

**Performance Metric Reconciliation:**
- [ ] Does DPI + RVPI = TVPI?
- [ ] Is Gross IRR > Net IRR?
- [ ] Is Gross MOIC > Net MOIC?
- [ ] Do portfolio company values sum to total fund NAV?

**Formula & Formatting Checks:**
- [ ] No error cells (#REF!, #VALUE!, #DIV/0!)?
- [ ] Sector allocations sum to 100%?
- [ ] Capital calls and distributions tie to capital account?
- [ ] Number formatting consistent across all tabs?

**Infra-Specific Checks:**
- [ ] Contracted % + Merchant % = 100%?
- [ ] DSCR calculated correctly (Cash Flow / Debt Service)?
- [ ] Availability metrics within realistic range (90-99%)?

**Output:** Key Metrics Table (copy to all subsequent prompts)

---

### Quality Gate 2: Cross-Deliverable Consistency (After Phase 4)

Verify numbers match across ALL deliverables:

| Data Point | Excel Value | Presentation | Written Docs | Match? |
|------------|-------------|--------------|--------------|--------|
| Fund Size | | | | |
| Net IRR (each fund) | | | | |
| Net MOIC (each fund) | | | | |
| DPI (each fund) | | | | |
| TVPI (each fund) | | | | |
| Mgmt Fee | | | | |
| Carry % | | | | |
| GP Commitment | | | | |
| # Portfolio Assets | | | | |
| Total NAV | | | | |
| Contracted Revenue % | | | | |

**If mismatches found:** Fix immediately. In IR, data accuracy IS the core competency.

---

## Common Mistakes (And How to Avoid Them)

| Mistake | Why It Hurts | Fix |
|---------|-------------|-----|
| **Treating it like an IC deck** | Shows you don't understand IR | Reframe: you're selling the GP, not a single deal |
| **Overly promotional tone** | LPs are sophisticated; marketing language = red flag | Factual, data-driven, let the numbers speak |
| **Missing performance benchmarks** | Numbers without context are meaningless | Always show quartile ranking or benchmark comparison |
| **Ignoring DPI** | IRR alone can be manufactured; LPs want cash returns | Always include DPI alongside MOIC and IRR |
| **No "Confidential" marking** | Shows lack of attention to compliance | Footer on every slide |
| **Too many slides** | Case study = 10-15 slides, not 30 | Edit ruthlessly — each slide earns its place |
| **Numbers don't match across deliverables** | In IR, data accuracy IS the core competency | Run QG2 consistency audit |
| **Can't explain fee mechanics** | IR professionals must understand fund economics | Memorize: mgmt fee, carry, hurdle, waterfall |
| **Generic "why IR?" answer** | Shows you're using IR as a fallback | Prepare a genuine, specific answer |
| **Reading the slides** | Universal presentation sin | Know the material; slides are reference, not script |

### Infra-Specific Mistakes

| Mistake | Why It Hurts | Fix |
|---------|-------------|-----|
| **Ignoring contracted vs. merchant split** | Core infra risk differentiation | Always show revenue stability metrics |
| **Missing regulatory exposure** | LPs need to understand downside | Explain reset schedules and protections |
| **No availability/uptime metrics** | Infra-specific operational KPI | Include for all operating assets |
| **Forgetting inflation linkage** | Key infra value driver | Quantify CPI escalators |
| **Ignoring DSCR and covenant headroom** | Infra debt is asset-level | Show coverage ratios by asset |

---

## Timeboxed Case Approaches

### 30-60 Minutes (Screening / Quick Update)
**Scope:** 6-slide LP update outline

**Focus Areas:**
- Fund performance summary
- Cash flow snapshot
- Asset KPI highlights
- Key risks

**Deliverables:**
- Performance Summary table + slide
- Cash Flow Waterfall table + slide
- 3 asset KPI bullet points

---

### 2-4 Hours (Intermediate / Quarterly Update)
**Scope:** Full LP update with analysis

**Additional Elements:**
- NAV roll-forward with drivers
- Valuation sensitivity analysis
- Asset case study with KPI trend
- Leverage and coverage detail

**Deliverables:**
- Full 8-slide deck
- Supporting Excel with 5-6 tabs
- Asset deep-dive section

---

### 24 Hours (Final Round / Full Deck)
**Scope:** Complete 10-14 slide deck + full Excel model

**Full Suite:**
- Fund overview and strategy
- Detailed performance attribution
- Asset-by-asset KPIs
- NAV drivers and sensitivity
- Fundraising pipeline
- DDQ summary
- Downside stress test

**Deliverables:**
- Polished presentation deck
- Full Excel model (10+ tabs)
- Scenario analysis
- Data room checklist (if fundraising)

---

## Recommended Slide Sequence

### LP Quarterly Update

| # | Slide | Key Content |
|---|-------|-------------|
| 1 | Executive Summary | What changed vs. last period, key wins/risks |
| 2 | Fund Performance | IRR/DPI/RVPI/TVPI table and drivers |
| 3 | Cash Flows | Calls vs. distributions, net cash flow trend |
| 4 | Asset Highlights | 2-3 asset KPI spotlights (infra-specific) |
| 5 | NAV & Sensitivity | NAV roll-forward, discount rate sensitivity |
| 6 | Leverage & Coverage | Debt profile, DSCR, covenant headroom |
| 7 | Risks & Mitigations | Top 3-5 risks with mitigation actions |
| 8 | Outlook | Near-term catalysts, capex, refinancing |

### Fundraising Deck

| # | Slide | Key Content |
|---|-------|-------------|
| 1 | Cover | Fund name, vintage, strategy tagline |
| 2 | Firm Overview | History, AUM, team, offices |
| 3 | Strategy & Edge | Why infrastructure, competitive advantage |
| 4 | Investment Team | Key professionals, experience, tenure |
| 5 | Track Record | Realized returns, cash yield history, benchmarks |
| 6 | Portfolio Overview | Sector/region/stage mix, diversification |
| 7-8 | Asset Case Studies | 1-2 flagship assets with KPIs |
| 9 | Pipeline & Sourcing | Deal flow, proprietary access |
| 10 | Term Sheet | Fees, carry, governance, LP protections |
| 11 | Risk Management | Framework, top risks, mitigants |
| 12 | ESG Framework | Approach, key metrics, targets |
| 13-14 | Appendix | Detailed tables, benchmarks, bios |

---

## Infra Nuances to Emphasize

### Always Include
- **Contracted vs. Merchant Split**: Show % of revenue under long-term contracts
- **Inflation Linkage**: Quantify CPI escalators and pass-through mechanisms
- **Regulatory Exposure**: Explain downside protections and reset schedules
- **Cash Yield Stability**: Highlight distribution coverage and volatility

### Infra-Specific Risks
1. Regulatory reset / tariff changes
2. Counterparty credit deterioration
3. Capex overrun / lifecycle cost spikes
4. Merchant price volatility
5. Operational availability shortfalls
6. FX / rate shocks for cross-border assets

### Key Metrics to Highlight
- Availability / uptime trends
- DSCR and covenant headroom
- Contract tenor and roll-off schedule
- Maintenance vs. growth capex split

---

## Case Intake Checklist

Before starting, confirm:

1. **Case Type**: LP update, fundraising, annual meeting, DDQ, crisis comms
2. **Fund Details**: Vintage, size, strategy, geography, currency
3. **Audience**: Existing LPs, prospective LPs, IC, board
4. **Time Horizon**: Quarterly, annual, ad hoc
5. **Asset Mix**: Regulated, contracted, merchant; sector exposure
6. **Performance Metrics**: Net IRR, DPI/RVPI/TVPI, cash yield, NAV
7. **Key Issues**: Underperformance, regulatory changes, refinancing
8. **Data Availability**: Asset KPIs, contract coverage, ESG
9. **Output Required**: Excel + slides (default: both)
10. **Formatting**: Charts, branding, slide count

---

*Version: 2.0 | Last Updated: February 2026*
