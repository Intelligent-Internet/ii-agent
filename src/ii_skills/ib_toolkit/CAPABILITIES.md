# IB Toolkit Complete Capabilities Reference

A comprehensive breakdown of all capabilities, modules, and commands available in the IB Toolkit skill.

---

## Table of Contents

1. [Quick Start Commands](#quick-start-commands)
2. [Excel Model Modules](#excel-model-modules)
3. [PowerPoint Slide Modules](#powerpoint-slide-modules)
4. [Pre-Built Model Generators](#pre-built-model-generators)
5. [Module-by-Module Reference](#module-by-module-reference)
6. [Example Prompts](#example-prompts)
7. [Output Customization](#output-customization)

---

## Quick Start Commands

### Natural Language Requests

You can ask for any of the following and the agent will generate the appropriate outputs:

**Quick Builds**
- "Build a 24-hour LBO model for [Company]"
- "Create a quick screening model"
- "Generate a first-round IOI model"

**Specific Modules**
- "Create a synergy analysis for the acquisition"
- "Build a 100-day plan for post-close"
- "Generate a management incentive plan"

**Full Packages**
- "Build a complete IC package"
- "Create an institutional-quality LBO model"
- "Generate a full investment memo deck"

---

## Excel Model Modules

### Core LBO Modules (9)

| Module | Request Keywords | Function | Output |
|--------|-----------------|----------|--------|
| **Sources & Uses** | "S&U", "transaction structure", "funding" | `add_sources_uses()` | Transaction funding table |
| **Revenue Build** | "revenue", "segment", "top-line" | `add_revenue_build()` | 5-year revenue by segment |
| **Expense Build** | "expense", "COGS", "SG&A", "margin" | `add_expense_build()` | Cost structure breakdown |
| **Operating Model** | "P&L", "income statement", "operating" | `add_operating_model()` | Full integrated P&L |
| **Debt Schedule** | "debt", "amortization", "interest" | `add_debt_schedule()` | Multi-tranche debt with paydown |
| **Working Capital** | "NWC", "working capital", "AR/AP" | `add_working_capital()` | NWC days and cash impact |
| **WACC** | "WACC", "cost of capital", "discount rate" | `add_wacc_calculation()` | Blended cost of capital |
| **Returns Analysis** | "returns", "IRR", "MOIC" | `add_returns_analysis()` | IRR/MOIC by exit year |
| **Sensitivity** | "sensitivity", "matrix", "what-if" | `add_sensitivity_tables()` | Entry/exit/growth matrices |

### Institutional Modules (4)

| Module | Request Keywords | Function | Output |
|--------|-----------------|----------|--------|
| **Scenario Analysis** | "bull/bear/base", "scenarios", "cases" | `add_scenario_analysis()` | 3 scenarios with probability weighting |
| **Mgmt vs Buyer** | "management case", "buyer case", "variance" | `add_management_vs_buyer()` | Side-by-side case comparison |
| **DCF Valuation** | "DCF", "discounted cash flow", "intrinsic" | `add_dcf_valuation()` | UFCF to enterprise value |
| **Covenant Analysis** | "covenants", "leverage ratio", "coverage" | `add_covenant_analysis()` | Compliance tracking over time |

### Due Diligence Modules (4)

| Module | Request Keywords | Function | Output |
|--------|-----------------|----------|--------|
| **Quality of Earnings** | "QoE", "EBITDA adjustments", "normalized" | `add_quality_of_earnings()` | Adjusted EBITDA bridge |
| **NWC Normalization** | "NWC peg", "target NWC", "normalization" | `add_working_capital_normalization()` | Target NWC and peg mechanism |
| **Customer Quality** | "concentration", "churn", "retention", "LTV" | `add_customer_revenue_quality()` | Customer metrics and unit economics |
| **Credit Analysis** | "credit", "debt capacity", "stress test" | `add_credit_debt_sizing()` | Max debt and stress scenarios |

### Capital Structure Modules (4)

| Module | Request Keywords | Function | Output |
|--------|-----------------|----------|--------|
| **Dividend Recap** | "dividend", "recap", "recapitalization" | `add_dividend_recap()` | Mid-hold dividend analysis |
| **Refinancing** | "refinancing", "rate savings", "refi" | `add_refinancing_analysis()` | Rate reduction economics |
| **Cap Table Waterfall** | "waterfall", "cap table", "LP/GP" | `add_cap_table_waterfall()` | Distribution by exit value |
| **Sponsor Economics** | "carry", "GP economics", "fund returns" | `add_sponsor_economics()` | GP carry and fund metrics |

### Transaction Structure Modules (5)

| Module | Request Keywords | Function | Output |
|--------|-----------------|----------|--------|
| **Add-on Analysis** | "add-on", "bolt-on", "tuck-in" | `add_addon_analysis()` | Platform + add-on combination |
| **Synergy Model** | "synergies", "cost savings", "revenue synergy" | `add_synergy_model()` | Synergy quantification and timing |
| **Carve-out Analysis** | "carve-out", "spin-off", "divestiture" | `add_carveout_analysis()` | Standalone adjustments and TSA |
| **Earnout Model** | "earnout", "contingent", "milestone" | `add_earnout_model()` | Contingent consideration valuation |
| **Purchase Price Allocation** | "PPA", "goodwill", "intangibles" | `add_purchase_price_allocation()` | Asset step-up and amortization |

### Value Creation Modules (4)

| Module | Request Keywords | Function | Output |
|--------|-----------------|----------|--------|
| **Value Creation Bridge** | "value bridge", "value creation", "attribution" | `add_value_creation_bridge()` | EBITDA/multiple/deleveraging split |
| **100-Day Plan** | "100-day", "post-close", "quick wins" | `add_hundred_day_plan()` | Initiative prioritization |
| **Exit Readiness** | "exit readiness", "exit planning" | `add_exit_readiness()` | Exit options and scorecard |
| **Management Incentive Plan** | "MIP", "management equity", "incentive plan" | `add_management_incentive_plan()` | MIP structure and payouts |

### Specialized Modules (3)

| Module | Request Keywords | Function | Output |
|--------|-----------------|----------|--------|
| **Rollup Model** | "rollup", "platform build", "consolidation" | `add_rollup_model()` | Multi-acquisition tracking |
| **Tax Analysis** | "tax", "NOL", "step-up", "338(h)(10)" | `add_tax_analysis()` | Tax shields and effective rate |
| **Control Premium** | "control premium", "takeover premium" | `add_control_premium_analysis()` | Premium analysis vs precedents |

---

## PowerPoint Slide Modules

### Core Analysis Slides

| Module | Request Keywords | Function | Slides |
|--------|-----------------|----------|--------|
| **Industry Analysis** | "industry", "market", "TAM/SAM" | `add_industry_analysis()` | 3 |
| **Competitive Analysis** | "competitive", "SWOT", "positioning" | `add_competitive_analysis()` | 3 |
| **Financial Analysis** | "financials", "historical", "projections" | `add_financial_analysis()` | 3 |
| **Valuation** | "valuation", "comps", "multiples" | `add_valuation()` | 3 |
| **LBO Analysis** | "LBO", "transaction", "returns" | `add_lbo_analysis()` | 3 |
| **Debt Analysis** | "debt", "capital structure" | `add_debt_analysis()` | 3 |
| **Management Analysis** | "management", "team", "leadership" | `add_management_analysis()` | 2 |
| **Investment Thesis** | "thesis", "recommendation", "risks" | `add_investment_thesis()` | 3 |
| **Company Overview** | "overview", "business description" | `add_company_overview()` | 3 |
| **Due Diligence** | "DD findings", "diligence summary" | `add_due_diligence()` | 3 |

### Institutional Slides

| Module | Function | Slides |
|--------|----------|--------|
| **Scenario Analysis** | `add_scenario_analysis()` | 4 |
| **Mgmt vs Buyer** | `add_management_vs_buyer()` | 3 |
| **DCF Valuation** | `add_dcf_valuation()` | 3 |
| **Covenant Analysis** | `add_covenant_analysis()` | 4 |

### Due Diligence Slides

| Module | Function | Slides |
|--------|----------|--------|
| **Quality of Earnings** | `add_quality_of_earnings()` | 3 |
| **Working Capital** | `add_working_capital_analysis()` | 2 |
| **Customer Quality** | `add_customer_quality_analysis()` | 3 |
| **Credit Analysis** | `add_credit_analysis_slides()` | 3 |

### Capital Structure Slides

| Module | Function | Slides |
|--------|----------|--------|
| **Dividend Recap** | `add_dividend_recap_slides()` | 2 |
| **Refinancing** | `add_refinancing_slides()` | 2 |
| **Waterfall** | `add_waterfall_slides()` | 2 |
| **Sponsor Economics** | `add_sponsor_economics_slides()` | 2 |

### Transaction Structure Slides

| Module | Function | Slides |
|--------|----------|--------|
| **Add-on Analysis** | `add_addon_analysis_slides()` | 3 |
| **Synergy Model** | `add_synergy_slides()` | 3 |
| **Carve-out Analysis** | `add_carveout_slides()` | 3 |
| **Earnout Model** | `add_earnout_slides()` | 2 |
| **PPA** | `add_ppa_slides()` | 2 |

### Value Creation Slides

| Module | Function | Slides |
|--------|----------|--------|
| **Value Creation Bridge** | `add_value_creation_slides()` | 2 |
| **100-Day Plan** | `add_hundred_day_slides()` | 3 |
| **Exit Readiness** | `add_exit_readiness_slides()` | 2 |
| **MIP** | `add_mip_slides()` | 2 |

### Specialized Slides

| Module | Function | Slides |
|--------|----------|--------|
| **Rollup Model** | `add_rollup_slides()` | 3 |
| **Tax Analysis** | `add_tax_slides()` | 2 |
| **Control Premium** | `add_control_premium_slides()` | 2 |

---

## Pre-Built Model Generators

### Excel Model Packages

| Package | Function | Sheets | Use Case |
|---------|----------|--------|----------|
| **Quick LBO** | `generate_quick_lbo()` | 4 | 24-hour screening |
| **Standard LBO** | `generate_standard_lbo()` | 9 | 48-hour first round |
| **Comprehensive LBO** | `generate_comprehensive_lbo()` | 17 | 5-day final round |
| **Full LBO** | All modules | 30 | 7+ day institutional |

### Slide Deck Packages

| Package | Function | Slides | Use Case |
|---------|----------|--------|----------|
| **Full Deck** | `generate_full_deck()` | ~25 | Standard investment memo |
| **Institutional Deck** | `generate_institutional_deck()` | 60+ | IC presentation |
| **Comprehensive Deck** | All modules | 80+ | Full deal package |

---

## Module-by-Module Reference

### SOURCES & USES
**What it does:** Creates the transaction funding table showing how the deal is financed.

**Key Outputs:**
- Enterprise Value calculation
- Debt tranches and amounts
- Equity contribution (the "check")
- Uses of funds (purchase price, fees, refinancing)

**When to use:** Every LBO model needs this as the starting point.

**Request:** "Create sources and uses for a $500M EV deal at 5x leverage"

---

### REVENUE BUILD
**What it does:** Projects revenue by segment, product, or geography.

**Key Outputs:**
- Revenue by business segment
- Growth rates by segment
- Price vs volume decomposition
- Market share assumptions

**When to use:** When you need bottom-up revenue projections beyond top-line growth.

**Request:** "Build revenue projections by segment for the next 5 years"

---

### DEBT SCHEDULE
**What it does:** Models multi-tranche debt with amortization and cash sweep.

**Key Outputs:**
- Beginning/ending debt by tranche
- Mandatory amortization
- Cash sweep paydown
- Interest expense by tranche

**When to use:** When you have multiple debt tranches or need to model deleveraging.

**Request:** "Create a debt schedule with term loan and revolver"

---

### SCENARIO ANALYSIS
**What it does:** Models Bull/Bear/Base cases with probability-weighted returns.

**Key Outputs:**
- Three scenarios with different assumptions
- Returns by scenario
- Probability-weighted expected return
- Key driver comparison

**When to use:** For IC presentations requiring multiple scenarios.

**Request:** "Build bull, bear, and base case scenarios"

---

### QUALITY OF EARNINGS
**What it does:** Normalizes EBITDA for one-time items and owner add-backs.

**Key Outputs:**
- Reported to Adjusted EBITDA bridge
- Add-back detail and support
- Run-rate adjustments
- Quality assessment

**When to use:** During due diligence to validate seller's EBITDA.

**Request:** "Create a quality of earnings analysis with EBITDA adjustments"

---

### SYNERGY MODEL
**What it does:** Quantifies and phases revenue and cost synergies.

**Key Outputs:**
- Revenue synergies by category
- Cost synergies by category
- Phasing over years 1-3
- One-time costs to achieve

**When to use:** For strategic acquisitions or add-ons with identified synergies.

**Request:** "Build a synergy model with revenue and cost savings"

---

### VALUE CREATION BRIDGE
**What it does:** Attributes equity value creation to key drivers.

**Key Outputs:**
- EBITDA growth contribution
- Multiple expansion contribution
- Deleveraging contribution
- Total value created

**When to use:** For exit analysis or IC presentations showing value creation.

**Request:** "Create a value creation bridge showing where returns come from"

---

### 100-DAY PLAN
**What it does:** Structures post-close priorities and quick wins.

**Key Outputs:**
- Phase 1/2/3 priorities
- Initiative impact matrix
- Milestone timeline
- Owner assignments

**When to use:** Pre-close planning or portfolio company onboarding.

**Request:** "Build a 100-day plan for post-acquisition"

---

### MANAGEMENT INCENTIVE PLAN
**What it does:** Structures management equity and models payout scenarios.

**Key Outputs:**
- Pool size and allocation
- Vesting terms
- Payout at various exit values
- Management alignment metrics

**When to use:** When structuring management rollover or new MIP.

**Request:** "Create a management incentive plan with payout scenarios"

---

### ROLLUP MODEL
**What it does:** Tracks multiple acquisitions in a platform build strategy.

**Key Outputs:**
- Acquisition summary table
- Combined financials over time
- Blended entry multiple
- Pipeline tracking

**When to use:** For buy-and-build / consolidation strategies.

**Request:** "Build a rollup model tracking platform plus add-ons"

---

## Example Prompts

### By Timeframe

**24-Hour:**
- "Build a quick LBO model for Company X with $50M EBITDA at 8x entry"
- "I need a screening model in the next few hours"
- "Create a go/no-go analysis for this deal"

**48-Hour:**
- "Build a first-round model with detailed debt schedule"
- "Create an IOI support package"
- "I need revenue build and expense build detail"

**5-Day:**
- "Build a full IC model with scenarios and covenants"
- "Create a comprehensive package for final round"
- "I need management vs buyer case comparison"

**7+ Day:**
- "Build a complete institutional model with all modules"
- "Create a full deal package including due diligence"
- "I need value creation analysis and 100-day plan"

### By Deal Type

**Platform Acquisition:**
- "Build an LBO model for a new platform investment"
- "Create a standard buyout analysis"

**Add-on / Bolt-on:**
- "Analyze this add-on acquisition to our platform"
- "Build a synergy model for the bolt-on"
- "Show combined returns with the add-on"

**Carve-out:**
- "This is a corporate carve-out, model standalone costs"
- "Build a carve-out analysis with TSA assumptions"

**Public Take-Private:**
- "Analyze the control premium for this take-private"
- "Model the 338(h)(10) election benefits"

**Exit Planning:**
- "Build an exit readiness assessment"
- "Create a value creation bridge for our hold period"
- "Model dividend recap scenarios"

### By Analysis Type

**Valuation:**
- "Create a DCF valuation"
- "Build trading and transaction comps"
- "Show a football field valuation summary"

**Due Diligence:**
- "Create a quality of earnings analysis"
- "Build customer concentration analysis"
- "Model working capital normalization"

**Capital Structure:**
- "Analyze a dividend recapitalization"
- "Model refinancing economics"
- "Create a cap table and waterfall"

**Returns:**
- "Build returns sensitivity tables"
- "Show MOIC and IRR by exit year"
- "Create a value creation bridge"

---

## Output Customization

### Specifying Company Name
All outputs use the company name in headers and titles:
- "Build an LBO model for Acme Corporation"
- "Create slides for Target Company"

### Specifying Parameters
You can provide deal parameters directly:
- "50M EBITDA, 8x entry, 5x leverage, 5-year hold"
- "Revenue growing at 10%, margins expanding 200bps"

### Combining Modules
Request multiple specific modules:
- "Create sources and uses, debt schedule, and returns analysis"
- "Build synergy model and add-on analysis together"

### Output Location
Specify where to save:
- "Save to my Downloads folder"
- "Put it in the project directory"

---

## File Locations

| Resource | Path |
|----------|------|
| This Capabilities Reference | `CAPABILITIES.md` |
| LBO Case Guide | `LBO_CASE_GUIDE.md` |
| Quick Reference | `QUICK_REFERENCE.md` |
| Module Index | `templates/reference_outputs/MODULE_INDEX.md` |
| Excel Generator | `templates/excel_models/excel_modules.py` |
| Slide Generator | `templates/case_study/slide_modules.py` |
| Reference Templates | `templates/reference_outputs/` |

---

## Summary Statistics

| Category | Excel Modules | Slide Modules | Total |
|----------|--------------|---------------|-------|
| Core LBO | 9 | 10 | 19 |
| Institutional | 4 | 4 | 8 |
| Due Diligence | 4 | 4 | 8 |
| Capital Structure | 4 | 4 | 8 |
| Transaction Structure | 5 | 5 | 10 |
| Value Creation | 4 | 4 | 8 |
| Specialized | 3 | 3 | 6 |
| **Total** | **33** | **34** | **67** |

**Total Capabilities:** 67 individual analysis modules available for modular generation.
