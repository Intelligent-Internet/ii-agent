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
| Track portfolio | [Net Worth Newsletter](#networth_newsletter) |
| Market news | [Market Newsletter](#market_newsletter) |
| Health metrics | [Health Dashboard](#health_dashboard) |

---

## IB Toolkit

**Location:** `src/ii_skills/ib_toolkit/`

The most comprehensive skill - 67 modular analysis components for PE/IB deal work.

### Key Documentation Files

| Document | Purpose |
|----------|---------|
| `CAPABILITIES.md` | **Complete reference of all 67 modules** |
| `LBO_CASE_GUIDE.md` | **How to approach LBO cases by timeframe** |
| `QUICK_REFERENCE.md` | Request keywords → Module mapping |
| `templates/reference_outputs/MODULE_INDEX.md` | Template files with use cases |

### IB Toolkit - LBO Models

**By Timeframe:**

| Timeframe | Sheets | What's Included |
|-----------|--------|-----------------|
| **24-hour** | 4 | Sources & Uses, Operating Model, Returns, Sensitivity |
| **48-hour** | 9 | + Revenue Build, Expense Build, Debt Schedule, Working Capital, WACC |
| **5-day** | 17 | + Scenario Analysis, Mgmt vs Buyer, DCF, Covenants, Due Diligence |
| **7+ day** | 30 | + Transaction Structure, Value Creation, Specialized modules |

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
│       ├── ib_toolkit/
│       │   ├── CAPABILITIES.md      # Full module reference
│       │   ├── LBO_CASE_GUIDE.md    # Case approach guide
│       │   ├── QUICK_REFERENCE.md   # Request → Module map
│       │   └── templates/
│       │       ├── excel_models/    # Excel generation code
│       │       ├── case_study/      # Slide generation code
│       │       └── reference_outputs/ # 30 template files
│       ├── networth_newsletter/
│       ├── market_newsletter/
│       ├── health_dashboard/
│       └── daily_investment_newsletter/
├── docs/                            # Additional documentation
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
| Full deck | "Create institutional investment deck" |
| Track portfolio | "Show my net worth breakdown" |
| Market update | "What's happening in markets today?" |
| Health check | "What's my HRV trend this week?" |

---

*Base System: ii-agent (github.com/robertodbabaran/ii-agent)*
*IB Toolkit: 67 modules (33 Excel + 34 Slides)*
*Last Updated: 2026-02-04*
