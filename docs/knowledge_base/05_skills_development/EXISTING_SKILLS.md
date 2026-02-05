# Existing Skills Status

## Skill Inventory

| Skill | Location | Actions | Status |
|-------|----------|---------|--------|
| **ib_toolkit** | `src/ii_skills/ib_toolkit/` | 28 | Partially functional |
| **ir_toolkit** | `src/ii_skills/ir_toolkit/` | ~20 | Scaffolded |
| **networth_newsletter** | `src/ii_skills/networth_newsletter/` | ~5 | Functional (standalone) |
| **market_newsletter** | `src/ii_skills/market_newsletter/` | ~5 | Functional (standalone) |
| **health_dashboard** | `src/ii_skills/health_dashboard/` | ~5 | Functional (standalone) |
| **daily_investment_newsletter** | `src/ii_skills/daily_investment_newsletter/` | ~3 | Functional (standalone) |
| **wealth_macro_newsletter** | `src/ii_skills/wealth_macro_newsletter/` | ~3 | Scaffolded |
| **memory** | `src/ii_skills/memory/` | ~3 | Planned |

## IB Toolkit — Detailed Status

### Fully Implemented (real calculations)
| Action | What It Does |
|--------|-------------|
| `quick_lbo_analysis` | LBO math: IRR, MOIC, value creation attribution |
| `lbo_sensitivity` | Sensitivity matrix generation |
| `analyze_capital_structure` | Debt capacity analysis |
| `analyze_quality_of_earnings` | EBITDA adjustments and QoE report |
| `generate_dd_questions` | Due diligence question generation |
| `list_slide_modules` | Lists available slide types |

### Template Only (generates file, no dynamic calculations)
| Action | What It Does |
|--------|-------------|
| `create_lbo_model` | Excel template with 4 sheets (no formulas) |
| `create_dcf_model` | Excel template (no formulas) |

### Functional with Placeholder Data
| Action | What It Does |
|--------|-------------|
| `generate_industry_slides` | PPTX slides (needs real data input) |
| `generate_competitive_slides` | PPTX slides (needs real data input) |
| `generate_financial_slides` | PPTX slides (needs real data input) |
| `generate_lbo_slides` | PPTX slides (needs real data input) |
| `generate_full_deck` | Complete PPTX deck (needs real data input) |
| All other `generate_*` actions | Same pattern |

### Stubbed (returns template structure)
| Action | What It Does |
|--------|-------------|
| `run_case_intake` | Returns next-steps template |
| `execute_analysis_module` | Returns module file path |

### External Dependency
| Action | What It Does | Dependency |
|--------|-------------|------------|
| `fetch_company_data` | Yahoo Finance data | yfinance |
| `create_company_deck` | Company profile PPTX | yfinance + pptx |

## What Needs Hardening (Priority Order)

1. **Excel LBO model** — Add real formulas and calculations to sheets
2. **Data-driven slides** — Connect data_fetcher output to slide generators
3. **Deal orchestrator** — Wire 52-prompt system through bridge
4. **IR Toolkit** — Verify all modules work through bridge
5. **Newsletter skills** — Add BaseSkill interface to standalone scripts
