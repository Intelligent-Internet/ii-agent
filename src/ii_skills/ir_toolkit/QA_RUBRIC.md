# IR Narrative QA Rubric

Quality assurance scoring framework for IR deliverables.

## Scoring Criteria (1-5 Scale)

### 1. Data Fidelity
*Excel outputs match slide numbers and footnotes*

| Score | Description |
|-------|-------------|
| 5 | Perfect match, all numbers verified |
| 4 | Minor rounding differences only |
| 3 | 1-2 discrepancies, non-material |
| 2 | Multiple discrepancies |
| 1 | Significant mismatches |

### 2. Infra Nuance
*Contracted vs. merchant, inflation linkage, regulatory exposure are explicit*

| Score | Description |
|-------|-------------|
| 5 | All infra dimensions covered with specifics |
| 4 | Most dimensions covered, good detail |
| 3 | Some infra context, could be deeper |
| 2 | Generic IR, limited infra specificity |
| 1 | No infrastructure context |

### 3. Clarity
*Action-title headlines convey the takeaway*

| Score | Description |
|-------|-------------|
| 5 | All headlines are insights, compelling narrative |
| 4 | Most headlines actionable, good flow |
| 3 | Mix of action and description headlines |
| 2 | Mostly descriptive titles |
| 1 | No clear takeaways, confusing |

### 4. Consistency
*Terminology and KPI definitions are consistent throughout*

| Score | Description |
|-------|-------------|
| 5 | Perfect consistency, definitions documented |
| 4 | Minor variations, same meaning |
| 3 | Some inconsistencies, manageable |
| 2 | Multiple definition issues |
| 1 | Contradictory information |

### 5. Completeness
*All requested modules have paired slides*

| Score | Description |
|-------|-------------|
| 5 | All modules complete with Excel + Slide |
| 4 | Minor items missing, core complete |
| 3 | Some gaps, main deliverables present |
| 2 | Significant gaps |
| 1 | Major sections missing |

---

## Pass/Fail Gates

### Hard Requirements (Must Pass)

- [ ] **No mismatched KPIs** between Excel and slides
- [ ] **Coverage ratios reconcile** to cash flow and debt tables
- [ ] **All assumptions documented** with sources
- [ ] **Infra context present** (contracted %, regulatory, etc.)
- [ ] **No calculation errors** in Excel formulas

### Soft Requirements (Should Pass)

- [ ] Action-title headlines on all slides
- [ ] Consistent formatting throughout
- [ ] Footnotes explain non-standard items
- [ ] Version control in footer
- [ ] Benchmark data is current (within 12 months)

---

## QA Checklist by Deliverable

### LP Update
- [ ] Performance metrics tie to prior quarter
- [ ] Cash flow waterfall foots correctly
- [ ] Asset KPIs have period-over-period comparison
- [ ] Risks have mitigation actions
- [ ] Outlook is forward-looking (not backward)

### Fundraising Deck
- [ ] Track record is audited/verified
- [ ] Terms match current LPA
- [ ] Case studies are representative
- [ ] Pipeline is current and realistic
- [ ] ESG claims are substantiated

### DDQ Response
- [ ] All questions addressed
- [ ] Owners and dates assigned
- [ ] Responses are consistent with other materials
- [ ] Sensitive items flagged for legal review
- [ ] Format matches LP requirements

---

## Scoring Summary Template

| Criterion | Score (1-5) | Notes |
|-----------|-------------|-------|
| Data Fidelity | | |
| Infra Nuance | | |
| Clarity | | |
| Consistency | | |
| Completeness | | |
| **Total** | /25 | |

### Interpretation

| Score | Rating | Action |
|-------|--------|--------|
| 23-25 | Excellent | Ready for delivery |
| 20-22 | Good | Minor revisions needed |
| 17-19 | Acceptable | Review and improve |
| 14-16 | Needs Work | Significant revisions |
| <14 | Unacceptable | Major rework required |

---

## Common QA Findings

1. **IRR vs. TVPI mismatch** — Different calculation periods
2. **NAV doesn't foot** — Missing contribution or distribution
3. **Coverage ratio error** — Wrong denominator (gross vs. net)
4. **Stale benchmarks** — Using prior year peer data
5. **Missing infra context** — Generic statements without specifics
6. **Inconsistent currency** — Mixed $M and $B
7. **Description headlines** — "Q4 Summary" instead of insight
8. **Orphan tables** — Excel output without matching slide
