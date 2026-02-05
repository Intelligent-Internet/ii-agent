# II-Agent Skills Documentation

This directory contains documentation for ii-agent skills - modular plugins that extend the agent's capabilities.

For a complete task reference, see [TASK_REFERENCE.md](../../TASK_REFERENCE.md) in the repository root.

## Available Skills

### [IB Toolkit](./ib_toolkit/)

Professional investment banking tools for PE/IB deal analysis, LBO modeling, and IC presentations.

**Modules:** 67 (33 Excel + 34 Slides)

### [IR Toolkit](./ir_toolkit/)

Infrastructure fund investor relations tools for LP communications, fundraising materials, and DDQ responses.

**Modules:** 33 (Excel ↔ Slide pairs)

---

## IB Toolkit Details

| Document | Description |
|----------|-------------|
| [BEST_PRACTICES.md](./ib_toolkit/BEST_PRACTICES.md) | Comprehensive guide covering slide structure, model architecture, financial metrics, risk frameworks |
| [SLIDE_TEMPLATES.md](./ib_toolkit/SLIDE_TEMPLATES.md) | ASCII templates for IC presentations (Growth Equity, PE/LBO) |
| [ORCHESTRATION_FRAMEWORK.md](./ib_toolkit/ORCHESTRATION_FRAMEWORK.md) | Modular prompt system with dependency tracking and state management |
| [PROMPT_LIBRARY.md](./ib_toolkit/PROMPT_LIBRARY.md) | 20+ executable prompts for structured deal execution |
| [CASE_INTAKE_PROTOCOL.md](./ib_toolkit/CASE_INTAKE_PROTOCOL.md) | Middle market interview case study approach |
| [CLAUDE_FOR_EXCEL_PROMPTS.md](./ib_toolkit/CLAUDE_FOR_EXCEL_PROMPTS.md) | Excel modeling prompts for Claude |

## Quick Start

### Using IB Toolkit

```python
from ii_skills.ib_toolkit import get_toolkit

toolkit = get_toolkit()

# Create company profile deck
toolkit.execute("create_company_deck", ticker="MSFT", comp_tickers=["AAPL", "GOOGL"])

# Create LBO model
toolkit.execute("create_lbo_model", company_name="Target Corp", entry_multiple=8.0)

# Run case intake for interview prep
toolkit.execute("run_case_intake", company_name="ABC Corp", deal_type="lbo")
```

### Middle Market Case Studies

For interview case studies, follow the [Case Intake Protocol](./ib_toolkit/CASE_INTAKE_PROTOCOL.md):

1. **Identify Case Type** (A-F) - Model Build, Analysis, Memo, Structuring, DD, Valuation
2. **Inventory Materials** - CIM, financials, model (if provided)
3. **Select Modules** - M1-M14 based on case type
4. **Execute Analysis** - Use prompt templates from the library

## Key Frameworks

### Investment Thesis (3 Pillars)
1. Market/Competitive Pillar - Why this company wins
2. Growth/Distribution Pillar - How it will scale
3. Quality/Efficiency Pillar - Why metrics justify valuation

### Middle Market Specifics
- Leverage: 3-4x senior, 4-5x total
- Equity: 40-50% of TEV
- Focus: Operational value creation, buy-and-build
- Exit: Strategic sale most likely

### SaaS Metrics Benchmarks
| Metric | Top Quartile | Median |
|--------|--------------|--------|
| NDR | >120% | 105-115% |
| Rule of 40 | >40% | 30-40% |
| LTV:CAC | >3x | 2-3x |
| Gross Margin | >80% | 70-80% |

### LBO Returns Targets
| Metric | Target |
|--------|--------|
| MOIC | 2.0-3.0x |
| IRR | 20-25% |
| Hold Period | 4-6 years |

---

*Documentation migrated from Claire Agent System*
*Sources: BCI Growth Equity (2026), Northleaf PE (2025), Buyside Agent Resources*
