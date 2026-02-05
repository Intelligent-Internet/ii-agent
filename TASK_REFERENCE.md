# II-Agent Task Reference

Complete reference of all tasks and capabilities available in the ii-agent skills system.

---

## Quick Reference

| Category | Skill | Example Request |
|----------|-------|-----------------|
| **PE/IB Deal Analysis** | IB Toolkit | "Build an LBO model for Company X" |
| **Infrastructure IR** | IR Toolkit | "Generate LP quarterly update for Fund IV" |
| **Portfolio Tracking** | Net Worth Newsletter | "Show my asset allocation" |
| **Market Intelligence** | Market Newsletter | "What's happening with copper prices?" |
| **Health Monitoring** | Health Dashboard | "What's my HRV trend this week?" |

---

## IB Toolkit (PE/IB Deal Analysis)

**Location:** `src/ii_skills/ib_toolkit/`
**Modules:** 67 (33 Excel + 34 Slides)

### What It Does

Professional investment banking tools for private equity deal analysis, LBO modeling, and investment committee presentations.

### Task Categories

#### 1. LBO Modeling

| Timeframe | Complexity | Example Request |
|-----------|------------|-----------------|
| 24-hour | 4 sheets | "Build a quick LBO screen for ABC Corp" |
| 48-hour | 9 sheets | "Create detailed LBO with debt schedule" |
| 5-day | 17 sheets | "Build full IC package with scenarios" |
| 7+ day | 30 sheets | "Comprehensive institutional-grade model" |

**Request Examples:**
```
"Build a 24-hour LBO model for Company X"
"Create an LBO with 3.5x leverage and 8x entry multiple"
"Model the add-on acquisition with synergies"
"Build sources and uses for the transaction"
```

#### 2. Valuation Analysis

| Module | Request Keywords |
|--------|------------------|
| DCF Valuation | "DCF", "discounted cash flow", "intrinsic value" |
| Trading Comps | "comps", "comparable companies", "multiples" |
| Transaction Comps | "precedent transactions", "M&A comps" |
| Football Field | "valuation range", "football field" |

**Request Examples:**
```
"Create DCF valuation for the target"
"Build trading comps with these peers: AAPL, MSFT, GOOGL"
"Show valuation football field"
```

#### 3. Due Diligence

| Module | Request Keywords |
|--------|------------------|
| Quality of Earnings | "QoE", "EBITDA adjustments", "normalized earnings" |
| NWC Normalization | "NWC peg", "working capital target" |
| Customer Analysis | "concentration", "churn", "LTV:CAC" |
| Credit Analysis | "debt capacity", "leverage analysis" |

**Request Examples:**
```
"Build quality of earnings analysis"
"Analyze customer concentration risk"
"Model debt capacity under stress"
```

#### 4. Slide Generation

| Deck Type | Slides | Request |
|-----------|--------|---------|
| Quick Summary | 3-5 | "Create executive summary slides" |
| Investment Thesis | 10-15 | "Build investment thesis deck" |
| Full IC Deck | 25-40 | "Create IC presentation" |
| Institutional | 60+ | "Build institutional investment deck" |

**Request Examples:**
```
"Generate industry analysis slides"
"Create SWOT analysis for the target"
"Build financial analysis section"
"Create full investment committee deck"
```

#### 5. Transaction Structure

| Module | Request Keywords |
|--------|------------------|
| Add-on Analysis | "bolt-on", "add-on acquisition" |
| Synergy Model | "synergies", "cost savings" |
| Carve-out | "spin-off", "carve-out", "standalone" |
| Earnout | "contingent consideration", "earnout" |

**Request Examples:**
```
"Model the add-on with $5M cost synergies"
"Build carve-out analysis with standalone costs"
"Structure earnout based on revenue targets"
```

#### 6. Value Creation

| Module | Request Keywords |
|--------|------------------|
| Value Bridge | "value creation", "returns attribution" |
| 100-Day Plan | "post-close", "integration plan" |
| Exit Readiness | "exit planning", "sale preparation" |
| MIP Design | "management incentive", "equity plan" |

**Request Examples:**
```
"Show value creation bridge from entry to exit"
"Build 100-day post-close plan"
"Create exit readiness assessment"
```

---

## IR Toolkit (Infrastructure Investor Relations)

**Location:** `src/ii_skills/ir_toolkit/`
**Modules:** 33 (Excel ↔ Slide pairs)

### What It Does

Specialized toolkit for infrastructure fund investor relations, including LP updates, fundraising materials, and DDQ responses.

**Core Principle:** Every Excel analysis has a corresponding PowerPoint slide.

### Task Categories

#### 1. LP Quarterly Updates

| Module | Request Keywords |
|--------|------------------|
| Performance Summary | "IRR", "DPI", "TVPI", "returns" |
| Cash Flow Waterfall | "calls", "distributions" |
| Asset KPIs | "availability", "utilization" |
| NAV Roll-forward | "NAV bridge", "valuation drivers" |
| Leverage Profile | "DSCR", "debt coverage" |
| Risk Register | "top risks", "mitigation" |

**Request Examples:**
```
"Generate LP quarterly update for Q4 2025"
"Create performance summary for Global Infra Fund IV"
"Build cash flow waterfall with 8 quarters"
"Show NAV roll-forward with FX impact"
```

#### 2. Fundraising Materials

| Module | Request Keywords |
|--------|------------------|
| Fund Snapshot | "fund overview", "strategy summary" |
| Track Record | "historical returns", "prior funds" |
| Portfolio Composition | "sector mix", "geography" |
| Term Sheet | "fees", "carry", "hurdle" |
| ESG Metrics | "emissions", "safety", "TRIR" |
| Pipeline | "LP prospects", "funnel" |

**Request Examples:**
```
"Build fundraising deck for Fund V"
"Create track record summary across all vintages"
"Generate term sheet comparison"
"Build ESG metrics dashboard"
```

#### 3. DDQ Response

| Module | Request Keywords |
|--------|------------------|
| DDQ Tracker | "questions", "status", "owners" |
| Risk Framework | "risk management", "controls" |
| ESG Framework | "ESG policy", "sustainability" |

**Request Examples:**
```
"Create DDQ response pack"
"Build DDQ tracker with status"
"Generate risk framework summary"
```

#### 4. Asset Performance Analysis

| Module | Request Keywords |
|--------|------------------|
| KPI Dashboard | "availability", "capacity factor" |
| Revenue Quality | "contracted", "merchant split" |
| Capex Tracker | "maintenance", "growth capex" |
| Contract Summary | "WACL", "counterparty exposure" |

**Request Examples:**
```
"Analyze asset KPIs for the wind portfolio"
"Show contracted vs merchant revenue split"
"Build capex tracker by asset"
```

#### 5. Valuation & Sensitivity

| Module | Request Keywords |
|--------|------------------|
| NAV Sensitivity | "discount rate impact", "stress test" |
| Macro Exposure | "inflation linkage", "rate sensitivity" |
| Regulatory Reset | "RAB", "allowed ROE" |

**Request Examples:**
```
"Model NAV sensitivity to discount rates"
"Show inflation exposure by asset"
"Build regulatory reset calendar"
```

### Infrastructure-Specific Metrics

| Metric | Definition | Target Range |
|--------|------------|--------------|
| Contracted Revenue % | Revenue under long-term contracts | 70-95% |
| WACL | Weighted Average Contract Life | 8-15 years |
| Availability | Uptime percentage | >95% |
| DSCR | Debt Service Coverage Ratio | >1.3x |
| CPI Linkage | Revenue indexed to inflation | Higher = better |

---

## Net Worth Newsletter

**Location:** `src/ii_skills/networth_newsletter/`
**Schedule:** 7:00 AM daily

### What It Does

Tracks portfolio holdings across all investment accounts and calculates daily net worth.

### Supported Accounts

- TD Direct Investing (Non-Reg, TFSA, FHSA)
- Interactive Brokers (CAD & USD)
- Coinbase (Crypto)
- Physical Assets (Gold, etc.)

### Task Examples

```
"Show my net worth breakdown"
"Add 50 shares of NVDA at $800 to IBKR USD"
"Update my student loan balance to $15,000"
"Show asset allocation by account type"
"What's my exposure to semiconductors?"
"Run the net worth newsletter"
```

---

## Market Newsletter

**Location:** `src/ii_skills/market_newsletter/`
**Schedule:** 7:15 AM daily

### What It Does

Aggregates market news and tracks asset prices for a watchlist.

### Capabilities

- News aggregation via NewsAPI
- Asset class performance tracking
- Watchlist price monitoring
- Sector analysis

### Task Examples

```
"What's happening with copper prices?"
"Get today's market news"
"Show performance of my watchlist"
"What's moving in tech today?"
"Run the market newsletter"
```

---

## Health Dashboard

**Location:** `src/ii_skills/health_dashboard/`
**Schedule:** 7:30 AM daily

### What It Does

Integrates with WHOOP to track health and fitness metrics.

### Metrics Tracked

- Recovery score
- Sleep performance
- Strain levels
- HRV (Heart Rate Variability)
- Resting heart rate

### Task Examples

```
"What's my HRV trend this week?"
"Show my recovery score"
"How was my sleep last night?"
"What's my strain for the week?"
"Run the WHOOP dashboard"
```

---

## Shared Infrastructure

**Location:** `src/ii_skills/shared/`

### Components

| Module | Purpose |
|--------|---------|
| `event_telemetry.py` | Run tracking and persistence |
| `task_graph.py` | DAG-based dependency execution |
| `run_budgets.py` | Configurable execution limits |
| `event_schema.py` | Typed event payloads |

These components are used by the IB and IR toolkits for orchestrated multi-phase analysis.

---

## Prompt Templates

### IB Toolkit Prompts

See `docs/skills/ib_toolkit/PROMPT_LIBRARY.md` for 20+ executable prompts.

**Quick Examples:**
```
"Create company profile deck for [TICKER]"
"Build LBO model with [X]x entry multiple"
"Generate IC presentation for [COMPANY]"
"Analyze [COMPANY] using comparable companies"
```

### IR Toolkit Prompts

See `src/ii_skills/ir_toolkit/PROMPT_LIBRARY.md` for 12 ready-to-use prompts.

**Quick Examples:**
```
"Create LP quarterly update for [FUND] [PERIOD]"
"Build fundraising deck for [FUND]"
"Generate DDQ response pack"
"Analyze asset KPIs for [ASSET]"
```

---

## Getting Started

### Running Skills Manually

```bash
# Net Worth Newsletter
python src/ii_skills/networth_newsletter/networth.py

# Market Newsletter
python src/ii_skills/market_newsletter/newsletter.py

# Health Dashboard
python src/ii_skills/health_dashboard/whoop_newsletter.py

# IR Toolkit Demo
python -m ii_skills.ir_toolkit.run_demo
```

### Using the IB Toolkit

```python
from ii_skills.ib_toolkit import get_toolkit

toolkit = get_toolkit()
toolkit.execute("create_lbo_model", company_name="Target Corp", entry_multiple=8.0)
```

### Using the IR Toolkit

```python
from ii_skills.ir_toolkit import IRToolkit, IRCaseType

toolkit = IRToolkit(user_id="user")
result = await toolkit.generate_lp_update(
    fund_name="Global Infrastructure Fund IV",
    reporting_period="Q4 2025",
)
```

---

## Configuration

### Credential Locations

| Skill | Config Location |
|-------|-----------------|
| Net Worth Newsletter | `networth_newsletter/config.py` |
| Market Newsletter | `market_newsletter/config.py` |
| Health Dashboard | `health_dashboard/config.py` |
| IB Toolkit | `ib_toolkit/config.py` |
| IR Toolkit | `ir_toolkit/config.py` |

### Environment Variables

Credentials are stored in skill-specific config files (gitignored) or in the `Config/` directory.

---

*Base System: ii-agent (github.com/robertodbabaran/ii-agent)*
*Last Updated: 2026-02-04*
