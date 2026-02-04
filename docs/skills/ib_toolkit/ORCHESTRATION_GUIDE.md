# Agent Orchestration Guide for IB Toolkit

## Overview

Claude Code can orchestrate multiple specialized agents running in parallel to accelerate complex analysis tasks. This guide explains how to leverage parallel execution for PE/IB work.

## Parallel Agent Execution

### How It Works

When you need multiple independent analyses, Claude can launch multiple agents simultaneously:

1. **Independent Tasks** - Tasks with no dependencies run in parallel
2. **Sequential Tasks** - Tasks that depend on each other run sequentially
3. **Mixed** - Combine both patterns for optimal efficiency

### Example: Full Company Analysis

When asked to "analyze Company X comprehensively", Claude can orchestrate:

```
┌─────────────────────────────────────────────────────────────┐
│                    PARALLEL EXECUTION                        │
├─────────────────────────────────────────────────────────────┤
│  Agent 1: Industry Analysis                                  │
│  ├─ Research market size (TAM/SAM/SOM)                      │
│  ├─ Identify growth drivers                                  │
│  └─ Generate industry slides                                 │
├─────────────────────────────────────────────────────────────┤
│  Agent 2: Competitive Analysis                               │
│  ├─ Research competitors                                     │
│  ├─ Build comp table                                         │
│  └─ Generate SWOT slides                                     │
├─────────────────────────────────────────────────────────────┤
│  Agent 3: Financial Analysis                                 │
│  ├─ Pull historical data                                     │
│  ├─ Build projections                                        │
│  └─ Generate financial slides                                │
├─────────────────────────────────────────────────────────────┤
│  Agent 4: Valuation                                          │
│  ├─ Build trading comps                                      │
│  ├─ Research precedents                                      │
│  └─ Generate valuation slides                                │
└─────────────────────────────────────────────────────────────┘
                           ↓
              SEQUENTIAL: Combine outputs
                           ↓
              Final: Complete Investment Deck
```

### Example Prompts for Parallel Execution

**Prompt 1: Parallel Research**
```
Research Company X in parallel:
1. Industry/market analysis
2. Competitive positioning
3. Financial performance
4. Management team
Then compile into a single investment deck.
```

**Prompt 2: Parallel Slide Generation**
```
Generate slides for Company X in parallel:
- Industry analysis slides
- Competitive analysis slides
- Valuation slides
- LBO analysis slides
Combine into one presentation.
```

**Prompt 3: Parallel Model Building**
```
Build the following models for Company X simultaneously:
1. LBO model (Excel)
2. Trading comps table
3. DCF model
Save all to my Downloads folder.
```

## Module-Specific Orchestration

### Slide Generation - Parallel Approach

Each slide module is independent and can run simultaneously:

| Module | Agent Task | Output |
|--------|------------|--------|
| `industry_analysis` | Research + generate | 3 slides |
| `competitive_analysis` | Research + generate | 3 slides |
| `financial_analysis` | Model + generate | 3 slides |
| `debt_analysis` | Analyze + generate | 3 slides |
| `lbo_analysis` | Model + generate | 3 slides |
| `management_analysis` | Research + generate | 2 slides |
| `valuation` | Comps + generate | 3 slides |
| `investment_thesis` | Synthesize + generate | 3 slides |

### Combining Results

After parallel execution, a coordinator agent:
1. Collects all slide outputs
2. Merges into single presentation
3. Ensures consistent formatting
4. Adds cover slide and table of contents

## Best Practices

### When to Use Parallel Agents

✅ **Good for parallel:**
- Independent research tasks
- Multiple slide modules
- Building different Excel models
- Analyzing different companies

❌ **Keep sequential:**
- Tasks that depend on prior results
- Financial modeling where inputs feed into outputs
- Investment recommendation (needs all analysis first)

### Optimal Task Sizing

| Task Complexity | Recommended Approach |
|-----------------|---------------------|
| Simple (1-2 slides) | Single agent |
| Moderate (3-5 slides) | Single agent |
| Complex (full deck) | Parallel agents |
| Multi-company | Parallel per company |

### Memory Efficiency

- Each parallel agent has independent context
- Large outputs should be written to files
- Use file paths to coordinate between agents

## Example Orchestration Patterns

### Pattern 1: Fan-Out / Fan-In

```
                    ┌──→ Agent A ──┐
                    │              │
User Request ──→ Coordinator ──→ Agent B ──→ Combiner ──→ Final Output
                    │              │
                    └──→ Agent C ──┘
```

### Pattern 2: Pipeline with Parallel Stage

```
User Request ──→ Research ──→ ┌ Analysis A ┐
                              ├ Analysis B ├ ──→ Synthesis ──→ Output
                              └ Analysis C ┘
```

### Pattern 3: Independent Outputs

```
                    ┌──→ Industry Slides ──→ File A
                    │
User Request ──→ Split ──→ Comp Slides ──→ File B
                    │
                    └──→ LBO Slides ──→ File C
```

## Technical Implementation

### For Claude Code

Claude Code automatically detects when parallel execution is beneficial:

1. **Automatic:** When given multiple independent tasks
2. **Explicit:** When you say "in parallel" or "simultaneously"
3. **Modular:** When requesting specific slide modules

### Code Reference

```python
# The slide_modules.py supports modular generation
from slide_modules import SlideGenerator

# Create separate presentations (can run in parallel agents)
gen1 = SlideGenerator("Company X")
gen1.add_industry_analysis()
gen1.save("industry.pptx")

gen2 = SlideGenerator("Company X")
gen2.add_competitive_analysis()
gen2.save("competitive.pptx")

# Or combine in single generator
gen = SlideGenerator("Company X")
gen.add_industry_analysis()
gen.add_competitive_analysis()
gen.save("combined.pptx")
```

## Limitations

1. **Context sharing:** Parallel agents don't share context by default
2. **File coordination:** Use explicit file paths for outputs
3. **Synthesis:** Combining insights requires a final sequential step

## Recommended Workflow

1. **Initial Request:** Describe what you need
2. **Claude Plans:** Identifies parallelizable components
3. **Parallel Execution:** Independent agents work simultaneously
4. **Coordination:** Results combined into final output
5. **Review:** You review and request refinements

---

*This orchestration approach can reduce analysis time by 50-70% for comprehensive company analyses.*
