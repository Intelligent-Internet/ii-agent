# Investment Banking Orchestration Framework
## Modular Prompt System for Deal Execution

*Adapted from 52-Prompt PE Case Study System*
*Version: 1.0.0 | Created: 2026-02-04*

---

## Overview

This framework enables structured, multi-phase deal analysis using modular prompts with dependency tracking, state management, and checkpoint validation. It transforms ad-hoc analysis into repeatable, institutional-quality workflows.

## Architecture

### Phase Structure

```
┌─────────────────────────────────────────────────────────────────┐
│ PHASE 0: FOUNDATION (Hours 0-8)                                 │
│ Setup → Material Inventory → Company Overview → Market Sizing   │
├─────────────────────────────────────────────────────────────────┤
│ PHASE 1: ANALYSIS (Hours 8-24)                                  │
│ Competitive → Customer → Management → Diligence Questions       │
├─────────────────────────────────────────────────────────────────┤
│ PHASE 2: MODELING (Hours 24-48)                                 │
│ Revenue Build → Operating Model → Debt Schedule → Returns       │
├─────────────────────────────────────────────────────────────────┤
│ PHASE 3: IC PREPARATION (Hours 48-72)                           │
│ Thesis → Risk Matrix → Scenarios → Deck Assembly → Q&A Prep     │
└─────────────────────────────────────────────────────────────────┘
```

---

## Prompt Library

### Phase 0: Foundation Prompts

| ID | Prompt Name | Dependencies | Output |
|----|-------------|--------------|--------|
| P00 | Case Setup Orchestrator | None | `case_state.json`, material inventory |
| P01 | Material Inventory | P00 | Categorized document list |
| P02 | Company Overview | P01 | 1-page company summary |
| P03 | Market Sizing (TAM/SAM/SOM) | P02 | Market size exhibit |
| P04 | Business Model Canvas | P02 | Revenue drivers, unit economics |

### Phase 1: Analysis Prompts

| ID | Prompt Name | Dependencies | Output |
|----|-------------|--------------|--------|
| P10 | Competitive Landscape | P02, P03 | 2x2 matrix, win/loss table |
| P11 | Customer Analysis | P04 | ICP definition, cohort analysis |
| P12 | Management Assessment | P02 | Team scorecard, gaps identified |
| P13 | Diligence Question Generator | P10-P12 | Prioritized Q&A list |
| P14 | Red Flag Scanner | P01 | Risk inventory with severity |

### Phase 2: Modeling Prompts

| ID | Prompt Name | Dependencies | Output |
|----|-------------|--------------|--------|
| P20 | Revenue Build | P04, P11 | Bottoms-up revenue model |
| P21 | Operating Model | P20 | Full P&L with margins |
| P22 | Debt Schedule Builder | P21 | Sources/uses, amortization |
| P23 | Returns Calculator | P21, P22 | MOIC/IRR sensitivity tables |
| P24 | Scenario Engine | P23 | Bull/Base/Bear cases |

### Phase 3: IC Preparation Prompts

| ID | Prompt Name | Dependencies | Output |
|----|-------------|--------------|--------|
| P30 | Investment Thesis Builder | P10, P23 | 3-pillar thesis |
| P31 | Risk Matrix Generator | P14, P24 | Probability/severity matrix |
| P32 | "What Must Be True" | P30, P31 | Critical assumptions list |
| P33 | Slide Content Generator | P30-P32 | 17-slide IC deck content |
| P34 | Q&A Preparation | P30-P33 | Anticipated questions + answers |
| P35 | Executive Summary | All | 1-page deal summary |

---

## State Management

### Case State Schema (`case_state.json`)

```json
{
  "case_id": "deal_2026_001",
  "company_name": "Target Corp",
  "deal_type": "growth_equity",
  "created_at": "2026-02-04T09:00:00Z",
  "current_phase": 1,

  "materials": {
    "cim": {"path": "...", "pages": 45, "ingested": true},
    "data_room": {"path": "...", "files": 127, "ingested": false},
    "management_deck": {"path": "...", "pages": 32, "ingested": true}
  },

  "prompts_completed": ["P00", "P01", "P02", "P03", "P04"],
  "prompts_in_progress": ["P10"],
  "prompts_blocked": [],

  "outputs": {
    "P02": {"file": "company_overview.md", "validated": true},
    "P03": {"file": "market_sizing.xlsx", "validated": true}
  },

  "checkpoints": {
    "phase_0_complete": true,
    "phase_1_complete": false,
    "model_ready": false,
    "ic_ready": false
  },

  "blockers": [],
  "notes": []
}
```

### State Operations

```python
# Initialize new case
def init_case(company_name: str, deal_type: str) -> dict:
    """Create new case_state.json with material inventory."""

# Update prompt status
def complete_prompt(prompt_id: str, output_file: str) -> bool:
    """Mark prompt complete, validate dependencies, update state."""

# Check if prompt can run
def can_run_prompt(prompt_id: str) -> tuple[bool, list]:
    """Returns (can_run, missing_dependencies)."""

# Get next available prompts
def get_available_prompts() -> list:
    """Return prompts with all dependencies satisfied."""
```

---

## Checkpoint Validation

### Phase Gates

Each phase transition requires validation. Run the full checklist before advancing.

#### Phase 0 → Phase 1 Gate (Foundation Complete)

**Material Completeness:**
- [ ] Material inventory complete — all documents catalogued with page references
- [ ] Company overview validated — all metrics sourced and cross-checked
- [ ] Market sizing documented — TAM/SAM/SOM with methodology
- [ ] Business model understood — revenue model, unit economics, cost structure mapped

**Data Quality Check:**
- [ ] No conflicting numbers between CIM, management deck, and financials
- [ ] Historical financials extracted accurately (verify totals, margins)
- [ ] Missing data gaps identified and flagged for diligence
- [ ] Key Metrics Table created and verified

#### Phase 1 → Phase 2 Gate (Analysis Complete)

**Analysis Completeness:**
- [ ] Competitive landscape mapped — all major competitors identified, 2x2 positioned
- [ ] Customer analysis complete — concentration, cohorts, ICP defined
- [ ] Management team assessed — scorecard complete, gaps identified
- [ ] Red flags scanned — all materials reviewed, flags severity-rated
- [ ] Diligence questions prioritized — Priority 1 questions identified

**Judgment Check:**
- [ ] No critical red flags that should halt the process
- [ ] Thesis direction is forming (even if not finalized)
- [ ] Sufficient data exists to build a credible model

#### Phase 2 → Phase 3 Gate (Model Complete)

**Model Integrity (run MODEL_AUDIT_CHECKLIST.md Sections 1-4):**
- [ ] Balance sheet balances in every period (A = L + E)
- [ ] Cash flow ending cash = Balance Sheet cash (every period)
- [ ] Sources = Uses exactly (zero difference)
- [ ] Debt schedule opening balances = S&U tranche amounts
- [ ] Net Income flows from P&L to Retained Earnings exactly
- [ ] No #REF!, #VALUE!, #DIV/0! errors in any tab
- [ ] All projection cells contain formulas (no hardcodes in formula cells)
- [ ] Covenants met in Base case (and checked in Bear case)

**Model Reasonableness:**
- [ ] Revenue growth in realistic range for industry (see SECTOR_PLAYBOOKS.md)
- [ ] Margin expansion supported by identified initiatives
- [ ] Debt paydown consistent with free cash flow generation
- [ ] Exit multiple justified by comparable transactions
- [ ] MOIC × timing ≈ IRR (sanity check per reference table)
- [ ] Returns in investable range (20%+ IRR for buyout, 25%+ for growth)

**Sensitivity Verification:**
- [ ] Sensitivity ranges bracket realistic outcomes
- [ ] Model doesn't break at reasonable stress levels
- [ ] Downside case still services debt
- [ ] Breakeven assumptions identified

#### Phase 3 → IC Gate (IC Materials Complete)

**Deliverable Completeness:**
- [ ] Investment thesis finalized — 3 pillars with evidence and counter-arguments
- [ ] Risk matrix complete — probability × severity, top 5 deep dives
- [ ] "What Must Be True" documented — critical assumptions with validation plans
- [ ] All slides drafted — 15-20 slide IC deck content complete
- [ ] Q&A prep complete — 15 anticipated questions with written answers

**Cross-Deliverable Consistency (Critical):**
- [ ] Numbers in slides match the financial model exactly
- [ ] Numbers in IC memo (if written) match the model exactly
- [ ] Thesis pillars in deck match thesis in memo
- [ ] Risk assessment in deck matches risk matrix
- [ ] Returns in executive summary match returns tab
- [ ] Scenario analysis in deck matches model scenarios

**Presentation Readiness:**
- [ ] Can present thesis in 60 seconds without notes
- [ ] Key numbers memorized (IRR, MOIC, entry multiple, revenue CAGR)
- [ ] Backup slides prepared for anticipated deep-dive questions

#### Post-Feedback Gate (After IC Review)

If the IC requests changes or additional analysis:
- [ ] All feedback items logged (use P38: Model Iteration prompt)
- [ ] Changes implemented and impact quantified
- [ ] Updated model passes Phase 2 → Phase 3 gate checks
- [ ] Version control maintained (prior version saved)

---

## Prompt Templates

### Standard Prompt Structure

Every prompt follows this template:

```markdown
# [PROMPT_ID]: [Prompt Name]

## Context
You are a [role] working on [deal type] for [company].
Current phase: [phase] | Prior completions: [list]

## Objective
[Clear, single objective]

## Inputs Required
- [Input 1]: [source/path]
- [Input 2]: [source/path]

## Output Specification
Format: [markdown/excel/json]
Sections required:
1. [Section 1]
2. [Section 2]

## Validation Criteria
- [ ] [Criterion 1]
- [ ] [Criterion 2]

## Handoff
Next prompts unlocked: [P_XX, P_YY]
```

### Example: P10 Competitive Landscape

```markdown
# P10: Competitive Landscape Analysis

## Context
You are a senior associate analyzing the competitive dynamics for [COMPANY].
Phase 1 Analysis | Completed: P00-P04

## Objective
Create a comprehensive competitive analysis including positioning matrix and win/loss analysis.

## Inputs Required
- Company Overview (P02 output)
- Market Sizing (P03 output)
- CIM competitive section (pages X-Y)

## Output Specification
Format: Markdown with ASCII tables

### Required Sections:
1. **Competitor Inventory**
   - Direct competitors (same ICP, same solution)
   - Indirect competitors (same ICP, different solution)
   - Potential entrants (adjacent players)

2. **2x2 Positioning Matrix**
   - Axes: [Axis 1] vs [Axis 2]
   - Plot all competitors + target company

3. **Win/Loss Analysis Table**
   | Competitor | Win Rate | Top Win Reasons | Top Loss Reasons | Sample Size |

4. **Porter's Five Forces Summary**
   | Force | Rating | Key Insight |

5. **Competitive Moat Assessment**
   - Current moat strength: [1-5]
   - Moat sustainability: [years]
   - Key differentiators

## Validation Criteria
- [ ] All direct competitors identified (minimum 3)
- [ ] Win rates supported by data or estimates
- [ ] Positioning matrix has clear axes
- [ ] Moat assessment is quantified

## Handoff
Next prompts unlocked: P11 (Customer Analysis), P13 (Diligence Questions)
```

---

## Integration with Claire Skills

### Skill Invocation Pattern

```python
# In ib_toolkit.py

def run_orchestrated_analysis(company: str, deal_type: str, materials_path: str):
    """
    Run full orchestrated deal analysis.

    1. Initialize case state
    2. Ingest materials
    3. Execute prompts in dependency order
    4. Validate at each checkpoint
    5. Generate final outputs
    """

    # Initialize
    state = init_case(company, deal_type)
    state = ingest_materials(state, materials_path)

    # Execute phases
    for phase in [0, 1, 2, 3]:
        prompts = get_phase_prompts(phase)
        for prompt_id in prompts:
            if can_run_prompt(prompt_id, state):
                output = execute_prompt(prompt_id, state)
                state = complete_prompt(state, prompt_id, output)

        # Validate phase gate
        if not validate_phase_gate(phase, state):
            handle_blockers(state)

    return generate_final_deliverables(state)
```

### Output Integration

Generated outputs integrate with existing IB Toolkit:

| Orchestration Output | IB Toolkit Integration |
|---------------------|------------------------|
| Company Overview | → Company Profile Deck (Slide 3) |
| Market Sizing | → Company Profile Deck (Slide 5) |
| Competitive Analysis | → Company Profile Deck (Slide 6) |
| Revenue Build | → DCF Model (Revenue tab) |
| Operating Model | → 3-Statement Model |
| Debt Schedule | → LBO Model |
| Returns Analysis | → All models (Returns tab) |
| IC Deck Content | → PowerPoint generation |

---

## Quick Start

### For a New Deal

1. **Initialize Case**
   ```
   "Initialize a growth equity case for [Company Name] with materials at [path]"
   ```

2. **Run Phase 0**
   ```
   "Run Foundation phase prompts P00-P04 for [Company]"
   ```

3. **Check Status**
   ```
   "What's the current state of the [Company] case?"
   ```

4. **Continue Execution**
   ```
   "Run the next available prompts for [Company]"
   ```

5. **Generate Deliverables**
   ```
   "Generate IC deck for [Company] using completed analysis"
   ```

---

## Appendix: Full Prompt Dependency Graph

```
P00 ─┬─► P01 ─┬─► P02 ─┬─► P03 ─┬─► P10 ─┬─► P13
     │        │        │        │        │
     │        │        └─► P04 ─┼─► P11 ─┤
     │        │                 │        │
     │        └─► P14           │        └─► P20 ─► P21 ─┬─► P22 ─► P23 ─► P24
     │                          │                        │
     │                          └─► P12                  └─► P30 ─► P31 ─► P32 ─► P33 ─► P34 ─► P35
     │
     └─► [State Management Thread]
```

---

*Framework Version: 1.0.0*
*Source: Buyside Agent Resources (52-Prompt PE System)*
*Adapted for Claire Skills Repository*
