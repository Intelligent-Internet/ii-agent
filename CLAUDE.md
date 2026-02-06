# CLAUDE.md - II-Agent Skills System

## Overview

Personal cloud operations base with specialized skills for investment banking analysis, financial tracking, market research, and health monitoring.

---

## Quick Navigation

| Need | Go To |
|------|-------|
| Build an LBO model | [IB Toolkit - LBO Models](#ib-toolkit---lbo-models) |
| Create deal slides | [IB Toolkit - Slide Generation](#ib-toolkit---slide-generation) |
| Full IB capabilities | [IB Toolkit Complete Reference](#ib-toolkit-complete-reference) |
| Audit a model | `docs/skills/ib_toolkit/MODEL_AUDIT_CHECKLIST.md` |
| Excel formatting standards | `docs/skills/ib_toolkit/EXCEL_CONVENTIONS.md` |
| Sector-specific analysis | `docs/skills/ib_toolkit/SECTOR_PLAYBOOKS.md` |
| Prep for IC presentation | `docs/skills/ib_toolkit/IC_PRESENTATION_PLAYBOOK.md` |
| LP quarterly update | [IR Toolkit](#ir-toolkit-infrastructure-investor-relations) |
| Fundraising deck | [IR Toolkit - Case Types](#ir-case-types) |
| Prep for interview | [Spaced Repetition](#spaced_repetition) |
| Track portfolio | [Net Worth Newsletter](#networth_newsletter) |
| Market news | [Market Newsletter](#market_newsletter) |
| Health metrics | [Health Dashboard](#health_dashboard) |

---

## File Governance (MANDATORY)

**All file operations MUST follow the three-tier protection model defined in `PROTECTED_RESOURCES.md`.**

### Tier 1 — Personal Vault (STOP — ask user before any edit)
- **Credentials & personal financial data** stored at `Desktop\RJ\II-Agent Credentials\`
- Repo `config.py` files are disposable mirrors auto-restored by runner scripts
- Net worth holdings, API keys, OAuth tokens — NEVER committed to git
- **Only modify when the user explicitly requests it**

### Tier 2 — Canonical Reference Templates (STOP — ask user before any edit)
- Reference output templates (`templates/reference_outputs/`, `shared/excel_templates/`)
- Excel model infrastructure (`excel_modules.py`, `formula_builder.py`)
- All IB/IR toolkit documentation (`docs/skills/ib_toolkit/`, `docs/skills/ir_toolkit/`)
- Capability docs, prompt libraries, slide templates, sector playbooks
- **READ for patterns and standards. NEVER write during case work.**
- **Only modify when the user explicitly says "update the [resource]" or "add this to the templates"**

### Tier 3 — Case Workspaces (PROCEED — active working area)
- Location: `output/cases/<date>_<case-name>/`
- When user starts a new case → create a dedicated case folder
- ALL generated Excel models, slide decks, and notes go in the case folder
- Reference Tier 2 templates for structure, write output to Tier 3
- Standard structure: `excel/`, `slides/`, `notes/`, `data/`, `deliverables/`

### Decision Rule
| File Location | Action |
|---|---|
| Tier 1 (vault / credentials / personal data) | **STOP** — ask user |
| Tier 2 (canonical templates / reference docs) | **STOP** — ask user |
| Tier 3 (case workspace under `output/cases/`) | **PROCEED** |
| New file not in any tier | **PROCEED with caution** |

---

## IB Toolkit

**Location:** `src/ii_skills/ib_toolkit/`

The most comprehensive skill - 67 modular analysis components for PE/IB deal work.

### Key Documentation Files

| Document | Location | Purpose |
|----------|----------|---------|
| `CAPABILITIES.md` | `src/ii_skills/ib_toolkit/` | **Complete reference of all 67 modules** |
| `LBO_CASE_GUIDE.md` | `src/ii_skills/ib_toolkit/` | **How to approach LBO cases by timeframe** |
| `QUICK_REFERENCE.md` | `src/ii_skills/ib_toolkit/` | Request keywords → Module mapping |
| `MODULE_INDEX.md` | `templates/reference_outputs/` | Template files with use cases |
| `MODEL_AUDIT_CHECKLIST.md` | `docs/skills/ib_toolkit/` | **30+ point model audit & debugging guide** |
| `EXCEL_CONVENTIONS.md` | `docs/skills/ib_toolkit/` | **Color coding, number formats, model architecture** |
| `SECTOR_PLAYBOOKS.md` | `docs/skills/ib_toolkit/` | **Sector-specific adjustments (SaaS, Healthcare, Industrial, Business Services, Consumer)** |
| `IC_PRESENTATION_PLAYBOOK.md` | `docs/skills/ib_toolkit/` | **IC oral prep, Q&A frameworks, handling objections** |
| `PROMPT_LIBRARY.md` | `docs/skills/ib_toolkit/` | 23 execution prompts (P00-P38) |
| `ORCHESTRATION_FRAMEWORK.md` | `docs/skills/ib_toolkit/` | Phased workflow with validation gates |
| `BEST_PRACTICES.md` | `docs/skills/ib_toolkit/` | Slide & model standards from real case studies |
| `CASE_INTAKE_PROTOCOL.md` | `docs/skills/ib_toolkit/` | 4-step intake with case type routing |
| `SLIDE_TEMPLATES.md` | `docs/skills/ib_toolkit/` | 25+ ASCII slide layout diagrams |

### IB Toolkit - LBO Models

**By Timeframe:**

| Timeframe | Sheets | What's Included |
|-----------|--------|-----------------|
| **24-hour** | 5 | Assumptions, Sources & Uses, Operating Model, Returns, Sensitivity |
| **48-hour** | 10 | + Revenue Build, Expense Build, Debt Schedule, Working Capital, WACC |
| **5-day** | 18 | + Scenario Analysis, Mgmt vs Buyer, DCF, Covenants, Due Diligence |
| **7+ day** | 31 | + Transaction Structure, Value Creation, Specialized modules |

**Smart Excel Models (Live Formulas):**

All generated workbooks include a central **Assumptions** sheet. The 8 core financial modules write real Excel formulas instead of static values — change an assumption and all downstream sheets update automatically.

| Sheet | Formula References |
|-------|-------------------|
| **Assumptions** | Central input sheet (all blue-font inputs) |
| **Sources & Uses** | `=Assumptions!B6*Assumptions!B12` for debt, residual equity |
| **Operating Model** | `=B10*(1+C5)` revenue growth, `=C10*C6` EBITDA |
| **Debt Schedule** | Multi-tranche with `=MAX(0,...)` balance rollforward, cash sweep referencing Operating Model EBITDA |
| **Returns Analysis** | Cross-refs Sources & Uses, Operating Model, Debt Schedule for MOIC/IRR |
| **Working Capital** | `=Revenue*NWC%` referencing Operating Model |
| **DCF Valuation** | UFCF/Terminal Value/PV formulas with `=1/(1+WACC)^n` discount factors |
| **Sensitivity Tables** | Formula grids computing MOIC/IRR from entry/exit multiple headers |

Helper: `formula_builder.py` provides `FormulaBuilder` class with `ref()`, `sheet_ref()`, `sum_range()`, `iferror()`, `max_zero()` utilities.

**Quick Commands:**
```
"Build a 24-hour LBO model for [Company]"
"Create a 48-hour model with detailed debt schedule"
"Build a full IC package for final round"
"Generate comprehensive LBO with all modules"
```

### IB Toolkit - Slide Generation

**Core Slides:**
| Request | Slides |
|---------|--------|
| "industry analysis" | 3 |
| "competitive analysis", "SWOT" | 3 |
| "financial analysis" | 3 |
| "valuation", "comps" | 3 |
| "LBO analysis", "transaction" | 3 |
| "investment thesis" | 3 |

**Full Decks:**
| Request | Slides |
|---------|--------|
| "full investment deck" | ~25 |
| "institutional deck" | 60+ |
| "comprehensive deck" | 80+ |

### IB Toolkit Complete Reference

#### Module Categories (67 Total)

**Core LBO (9 Excel + 10 Slides)**
| Module | Keywords |
|--------|----------|
| Sources & Uses | "S&U", "transaction structure" |
| Revenue Build | "revenue", "segment", "top-line" |
| Expense Build | "expense", "COGS", "SG&A" |
| Operating Model | "P&L", "income statement" |
| Debt Schedule | "debt", "amortization" |
| Working Capital | "NWC", "AR/AP" |
| WACC | "cost of capital", "discount rate" |
| Returns Analysis | "IRR", "MOIC", "returns" |
| Sensitivity | "sensitivity", "matrix" |

**Institutional (4 Excel + 4 Slides)**
| Module | Keywords |
|--------|----------|
| Scenario Analysis | "bull/bear/base", "scenarios" |
| Mgmt vs Buyer | "management case", "buyer case" |
| DCF Valuation | "DCF", "discounted cash flow" |
| Covenant Analysis | "covenants", "leverage ratio" |

**Due Diligence (4 Excel + 4 Slides)**
| Module | Keywords |
|--------|----------|
| Quality of Earnings | "QoE", "EBITDA adjustments" |
| NWC Normalization | "NWC peg", "target NWC" |
| Customer Quality | "concentration", "churn", "LTV" |
| Credit Analysis | "debt capacity", "stress test" |

**Capital Structure (4 Excel + 4 Slides)**
| Module | Keywords |
|--------|----------|
| Dividend Recap | "dividend", "recap" |
| Refinancing | "refinancing", "rate savings" |
| Cap Table Waterfall | "waterfall", "LP/GP" |
| Sponsor Economics | "carry", "GP economics" |

**Transaction Structure (5 Excel + 5 Slides)**
| Module | Keywords |
|--------|----------|
| Add-on Analysis | "add-on", "bolt-on" |
| Synergy Model | "synergies", "cost savings" |
| Carve-out Analysis | "carve-out", "spin-off" |
| Earnout Model | "earnout", "contingent" |
| Purchase Price Allocation | "PPA", "goodwill" |

**Value Creation (4 Excel + 4 Slides)**
| Module | Keywords |
|--------|----------|
| Value Creation Bridge | "value bridge", "attribution" |
| 100-Day Plan | "100-day", "post-close" |
| Exit Readiness | "exit readiness", "exit planning" |
| Management Incentive Plan | "MIP", "management equity" |

**Specialized (3 Excel + 3 Slides)**
| Module | Keywords |
|--------|----------|
| Rollup Model | "rollup", "platform build" |
| Tax Analysis | "tax", "NOL", "step-up" |
| Control Premium | "control premium", "takeover" |

### IB Toolkit - Example Prompts

**By Deal Type:**
```
Platform: "Build an LBO model for a new platform investment"
Add-on: "Analyze this bolt-on with synergies"
Carve-out: "Model standalone costs for the carve-out"
Take-private: "Analyze control premium for the take-private"
Rollup: "Build a rollup model tracking acquisitions"
```

**By Analysis:**
```
Valuation: "Create DCF and comps valuation"
Due Diligence: "Build quality of earnings analysis"
Returns: "Show value creation bridge"
Exit: "Create exit readiness assessment"
```

### IB Toolkit - Reference Templates

**Location:** `src/ii_skills/ib_toolkit/templates/reference_outputs/`

30 template files available:
- `Institutional_LBO_Template.xlsx` (17 sheets)
- `Institutional_Deck_Template.pptx` (60+ slides)
- Individual module templates (Excel + PPT for each)

---

## IR Toolkit (Infrastructure Investor Relations)

**Location:** `src/ii_skills/ir_toolkit/`

Specialized toolkit for infrastructure fund investor relations - orthogonal to IB/PE deal work.

**Core Principle:** Every Excel analysis has a corresponding PowerPoint slide.

### Key Documentation Files

| Document | Purpose |
|----------|---------|
| `CAPABILITIES.md` | **Complete reference of all 33 Excel ↔ Slide pairs** |
| `CASE_GUIDE.md` | **IR deliverable guide with IC vs LP differentiation, quality gates** |
| `QUICK_REFERENCE.md` | Request keywords → Module mapping |
| `PROMPT_LIBRARY.md` | **24 ready-to-use prompts (core + interview prep + Anki)** |
| `SLIDE_LAYOUTS.md` | **Visual slide templates with ASCII diagrams** |
| `references/infra_jargon_metrics.md` | Infrastructure terminology guide |

### IR Case Types

| Case Type | Modules | Use Case |
|-----------|---------|----------|
| **LP Update** | 6 | Quarterly LP communications |
| **Fundraising** | 12 | New fund marketing materials |
| **DDQ Response** | 3 | Due diligence questionnaire packs |
| **Annual Meeting** | 12 | AGM presentations |
| **Crisis Comms** | 4 | Rapid response materials |

### IR Toolkit - Module Categories

**Fund Overview (4 Excel + 4 Slides)**
| Module | Keywords |
|--------|----------|
| Fund Snapshot | "fund overview", "strategy" |
| Performance Summary | "IRR", "DPI", "TVPI", "returns" |
| Portfolio Composition | "sector mix", "geography" |
| Track Record | "historical performance" |

**Cash Flows (3 Excel + 3 Slides)**
| Module | Keywords |
|--------|----------|
| Cash Flow Waterfall | "calls", "distributions" |
| Distribution Coverage | "coverage ratio" |
| IRR Bridge | "return attribution" |

**Asset Performance (4 Excel + 4 Slides)**
| Module | Keywords |
|--------|----------|
| Asset KPI Dashboard | "availability", "utilization" |
| Revenue Quality | "contracted", "merchant" |
| Capex Tracker | "maintenance", "growth capex" |
| Contract Summary | "WACL", "counterparty" |

**Valuation (3 Excel + 3 Slides)**
| Module | Keywords |
|--------|----------|
| NAV Roll-forward | "NAV bridge", "drivers" |
| Sensitivity Analysis | "discount rate", "stress" |
| Macro Exposure | "inflation", "rates" |

**Risk (2 Excel + 2 Slides)**
| Module | Keywords |
|--------|----------|
| Risk Register | "top risks", "mitigation" |
| Regulatory Calendar | "reset dates", "RAB" |

**ESG (1 Excel + 1 Slide)**
| Module | Keywords |
|--------|----------|
| ESG Metrics | "emissions", "TRIR", "safety" |

**Fundraising (4 Excel + 4 Slides)**
| Module | Keywords |
|--------|----------|
| LP Pipeline | "funnel", "prospects" |
| DDQ Tracker | "questions", "status" |
| Term Sheet | "fees", "carry", "hurdle" |
| Data Room Checklist | "diligence", "documents" |

### IR Toolkit - Quick Commands

```
"Generate an LP quarterly update for Q4 2025"
"Build a fundraising deck for Fund V"
"Create DDQ response pack"
"Analyze asset KPIs for the wind portfolio"
"Build NAV roll-forward with FX impact"
"Generate leverage and coverage profile"
```

### Infrastructure-Specific Metrics

| Metric | Definition |
|--------|------------|
| **Contracted Revenue %** | Revenue under long-term contracts (target: 70-95%) |
| **WACL** | Weighted Average Contract Life (years) |
| **Availability** | Uptime percentage (target: >95%) |
| **DSCR** | Debt Service Coverage Ratio (target: >1.3x) |
| **CPI Linkage** | Revenue indexed to inflation |
| **Rate Base** | Regulated asset value earning allowed return |

---

## Deal & Analysis Support Skills

### deal_memory
**Location:** `src/ii_skills/deal_memory/`

Persistent deal context across conversations. Wraps existing DealMemory and DataStore infrastructure.

**Capabilities (10 actions):**
- Store/recall deal notes, decisions, assumptions
- Store/recall company research and knowledge
- List active and past deals
- Search across deal history
- Store/recall user modeling preferences
- Export deal context as JSON

**Commands:**
```
"Remember this assumption for the Acme deal"
"What do we know about ACME?"
"List my active deals"
"Search deal history for SaaS LBOs"
"Export all context for the Acme deal"
```

### output_organizer
**Location:** `src/ii_skills/output_organizer/`

Auto-organize skill outputs into standardized deal folders.

**Capabilities (7 actions):**
- Create deal folder structure (LBO, Growth Equity, Add-on, Carve-out templates)
- Organize outputs by deal (auto-map files to subfolders)
- Link outputs to deals, search outputs, export deal packages

**Commands:**
```
"Create a deal folder for the Acme LBO"
"Organize all outputs for deal X"
"What files do we have for the Acme deal?"
"Export deal package for IC review"
```

### pdf_extractor
**Location:** `src/ii_skills/pdf_extractor/`

Extract financial data from CIM PDFs using PyMuPDF + pattern matching.

**Capabilities (6 actions):**
- Extract all financials (P&L, BS, CF) from CIM PDFs
- Extract specific statements (income statement, balance sheet)
- Extract key metrics (margins, growth, leverage)
- Export extracted data to formatted Excel workbook

**Commands:**
```
"Extract financials from this CIM PDF"
"Pull the income statement from the CIM"
"Export the extracted data to Excel"
```

### spaced_repetition
**Location:** `src/ii_skills/spaced_repetition/`

Generate, manage, and export Anki-ready flashcard decks for interview prep.

**Capabilities (8 actions):**
- Generate cards from 8 prompt templates (interview prep, technical finance, behavioral, sector-specific, case study, market knowledge, custom notes)
- Create/manage decks per interview
- Export to TSV (Anki import), markdown Q&A, markdown table
- Search across all decks
- Generate study plans based on exam date

**No pre-built decks** — create decks per-interview using prompts.

**Prompt Templates:** `P01_interview_prep`, `P02_general_knowledge`, `P03_technical_finance`, `P04_sector_specific`, `P05_behavioral`, `P06_market_knowledge`, `P07_case_study`, `P08_custom_notes`

**Commands:**
```
"Generate flashcards for my BCI interview on LBO mechanics"
"Create a deck for the Acme case study"
"Export my interview deck to Anki TSV"
"Search my cards for EBITDA"
"Build a study plan for my March 15 interview"
```

**Docs:** `SKILL.md` (full reference), `QUICK_REFERENCE.md` (prompt-to-use-case mapping)

---

## Other Skills

### networth_newsletter
**Location:** `src/ii_skills/networth_newsletter/`

Daily portfolio tracking across all accounts.

**Capabilities:**
- Track holdings across TD, IBKR, Coinbase, physical assets
- Daily net worth calculation
- Asset allocation breakdown
- 7:00 AM email reports

**Commands:**
```
"Add 50 shares of NVDA at $800 to IBKR USD"
"Update my student loan balance"
"Show asset allocation breakdown"
"Run the net worth newsletter"
```

### market_newsletter
**Location:** `src/ii_skills/market_newsletter/`

Market news and price tracking.

**Capabilities:**
- News aggregation via NewsAPI
- Asset class performance
- Price tracking for watchlist
- 7:15 AM email reports

**Commands:**
```
"What's happening with copper prices?"
"Get market news for today"
"Run the market newsletter"
```

### health_dashboard
**Location:** `src/ii_skills/health_dashboard/`

WHOOP integration for health metrics.

**Capabilities:**
- Recovery, sleep, strain metrics
- HRV tracking
- Weekly trends
- 7:30 AM email reports

**Commands:**
```
"What was my average HRV this week?"
"Show my recovery score"
"Run the WHOOP dashboard"
```

### daily_investment_newsletter
**Location:** `src/ii_skills/daily_investment_newsletter/`

Canadian investment news via Brave Search.

---

## Configuration

### Credential Locations
| Skill | Config File |
|-------|-------------|
| networth_newsletter | `config.py` - Gmail + portfolio |
| market_newsletter | `config.py` - Gmail + NewsAPI |
| health_dashboard | `config.py` - Gmail + WHOOP OAuth |
| daily_investment_newsletter | `Config/` directory |

### Scheduled Tasks
```bash
# Check Windows scheduled tasks
schtasks /query /fo LIST | findstr -i "newsletter\|whoop\|networth"
```

### Manual Execution
```bash
python src/ii_skills/networth_newsletter/networth.py
python src/ii_skills/market_newsletter/newsletter.py
python src/ii_skills/health_dashboard/whoop_newsletter.py
```

---

## Project Structure

```
ii-agent/
├── src/
│   └── ii_skills/
│       ├── ib_toolkit/              # PE/IB deal analysis (67 modules)
│       │   ├── CAPABILITIES.md      # Full module reference
│       │   ├── LBO_CASE_GUIDE.md    # Case approach guide
│       │   ├── QUICK_REFERENCE.md   # Request → Module map
│       │   └── templates/
│       │       ├── excel_models/    # Excel generation code (smart formulas)
│       │       │   ├── excel_modules.py   # 33 module functions (8 with live formulas)
│       │       │   └── formula_builder.py # Cell reference & formula helpers
│       │       ├── case_study/      # Slide generation code
│       │       └── reference_outputs/ # 30 template files
│       ├── ir_toolkit/              # Infrastructure IR (33 modules)
│       │   ├── CAPABILITIES.md      # Full module reference
│       │   ├── CASE_GUIDE.md        # IR deliverable guide
│       │   ├── PROMPT_LIBRARY.md    # 24 ready-to-use prompts
│       │   ├── SLIDE_LAYOUTS.md     # Visual slide templates
│       │   └── references/          # Jargon and metrics guide
│       ├── deal_memory/             # Persistent deal context (10 actions)
│       ├── output_organizer/        # Auto-organize files into deal folders (7 actions)
│       ├── pdf_extractor/           # Extract financials from CIM PDFs (6 actions)
│       │   ├── extractor.py         # PyMuPDF text extraction engine
│       │   ├── patterns.py          # Financial regex patterns
│       │   └── excel_writer.py      # Formatted Excel output
│       ├── spaced_repetition/        # Anki flashcard generation (8 actions)
│       │   ├── prompts/             # 8 prompt templates (P01-P08)
│       │   ├── decks/               # Generated decks (per interview)
│       │   └── output/              # Exported TSV/markdown files
│       ├── shared/                  # Common infrastructure
│       │   ├── memory.py            # MemoryService, DealMemory, ConversationMemory
│       │   ├── datastore.py         # DataStore (deals, outputs, memories)
│       │   ├── storage.py           # SkillStorage (GCS uploads)
│       │   ├── event_telemetry.py   # Run tracking
│       │   ├── task_graph.py        # DAG execution
│       │   ├── run_budgets.py       # Execution limits
│       │   └── event_schema.py      # Typed events
│       ├── networth_newsletter/
│       ├── market_newsletter/
│       ├── health_dashboard/
│       └── daily_investment_newsletter/
├── docs/
│   └── skills/
│       └── ib_toolkit/              # Extended IB documentation
│           ├── BEST_PRACTICES.md    # Slide & model standards
│           ├── CASE_INTAKE_PROTOCOL.md  # Case type routing
│           ├── ORCHESTRATION_FRAMEWORK.md # Phased workflow
│           ├── PROMPT_LIBRARY.md    # 23 execution prompts
│           ├── SLIDE_TEMPLATES.md   # 25+ ASCII slide diagrams
│           ├── MODEL_AUDIT_CHECKLIST.md  # Model QA & debugging
│           ├── EXCEL_CONVENTIONS.md # Formatting standards
│           ├── SECTOR_PLAYBOOKS.md  # SaaS/Healthcare/Industrial/etc.
│           └── IC_PRESENTATION_PLAYBOOK.md # IC oral prep & Q&A
└── Config/                          # Credentials (gitignored)
```

---

## Quick Reference Card

| I want to... | Say... |
|--------------|--------|
| Screen an LBO | "Build a quick 24-hour LBO model" |
| Full IC package | "Create comprehensive LBO with all modules" |
| Analyze add-on | "Build add-on analysis with synergies" |
| Value creation | "Show value creation bridge" |
| Exit planning | "Create exit readiness assessment" |
| Industry slides | "Generate industry analysis slides" |
| Full deal deck | "Create institutional investment deck" |
| LP quarterly update | "Generate LP update for Q4" |
| Fundraising deck | "Build fundraising deck for Fund V" |
| DDQ response | "Create DDQ response pack" |
| Asset KPIs | "Analyze asset KPI dashboard" |
| NAV analysis | "Build NAV roll-forward" |
| Remember deal context | "Remember this assumption for the Acme deal" |
| Recall company facts | "What do we know about ACME?" |
| Organize deal files | "Create a deal folder for the Acme LBO" |
| Extract CIM financials | "Extract financials from this CIM PDF" |
| Prep interview flashcards | "Generate flashcards for my interview on LBO" |
| Export deck to Anki | "Export my interview deck to TSV" |
| Study plan | "Build a study plan for my March 15 interview" |
| Track portfolio | "Show my net worth breakdown" |
| Market update | "What's happening in markets today?" |
| Health check | "What's my HRV trend this week?" |

---

*Base System: ii-agent (github.com/robertodbabaran/ii-agent)*
*IB Toolkit: 67 modules (33 Excel + 34 Slides)*
*IR Toolkit: 33 modules (Excel ↔ Slide pairs)*
*Deal Support: deal_memory (10), output_organizer (7), pdf_extractor (6), spaced_repetition (8)*
*Productivity: memory (14), task_management (12), connectors (16), productivity (5)*
*Last Updated: 2026-02-06*

---

## Productivity Layer

**New Skills:**

| Skill | Location | Actions |
|-------|----------|---------|
| **memory** | `src/ii_skills/memory/` | 14 actions — Two-tier workplace memory |
| **task_management** | `src/ii_skills/task_management/` | 12 actions — TASKS.md tracking |
| **connectors** | `src/ii_skills/connectors/` | 16 actions — MCP connector layer |
| **productivity** | `src/ii_skills/productivity/` | 5 actions — /start, /update workflows |

**Architecture:**
- `shared/memory_tiers.py` — TieredMemoryStore engine (hot cache + deep file storage)
- `connectors/registry.py` — ConnectorRegistry maps categories to MCP servers
- `connectors/adapters/base.py` — Abstract adapters for chat, email, calendar, KB, tracker
- `productivity/workflows/` — Orchestrator workflows calling across skills via `get_skill()`
- `task_management/dashboard/dashboard.html` — Kanban board (standalone HTML)

**Quick Commands:**

| Command | What it does |
|---------|-------------|
| "Start my productivity workspace" | Initialize TASKS.md + memory + dashboard |
| "What's on my plate?" | Show active tasks and overdue items |
| "Add a task: Send proposal to Todd by Friday" | Add task with context and due date |
| "Done with the proposal" | Complete task, move to Done |
| "Who is Todd?" | Tiered memory lookup |
| "Remember that PSR means Pipeline Status Report" | Add to glossary |
| "Update my tasks" | Triage stale items, sync from trackers |
| "Deep update" | Comprehensive scan of email/calendar/chat |
| "Daily brief" | Morning briefing with tasks + memory + connectors |
| "Weekly review" | Summary of completed tasks and memory growth |

**Dashboard:**
```bash
# Open Kanban board (drag-and-drop task management)
start src/ii_skills/task_management/dashboard/dashboard.html
```

**Configuration:**
- `.mcp.json` at workspace root configures external connectors (gitignored)
- See `src/ii_skills/connectors/config/connectors.example.json` for template
- No new Python dependencies — all skills use stdlib only
