# Module Specification: LP/GP Deal-Term Analyzer

*Extracts, scores, and flags fund and co-invest terms for LP due diligence and negotiation.*

See ROADMAP_II_AGENT_IR_TOOLKIT.md § 5 for strategic context.

---

## Overview

The Terms Analyzer is a module family that:
1. **Extracts** structured term data from LPAs, side letters, and term sheets.
2. **Scores** LP-friendliness and GP-flexibility across four dimensions.
3. **Detects** red flags using rules-based triggers aligned to ILPA best practices.
4. Produces a one-page **Negotiation Priorities** summary.

---

## Module Components

### TA-1: Term Extraction

**Input:** LPA text, term sheet PDF/text, side letter excerpts

**Extracted Fields:**

| Category | Fields |
|----------|--------|
| **Economics** | Management fee basis, fee step-down schedule, carry %, preferred return / hurdle rate, catch-up %, GP commitment ($, %), fee offset / rebate mechanics |
| **Carry Waterfall** | European vs. American, whole-fund vs. deal-by-deal, clawback provisions, escrow %, tax distribution treatment |
| **Fund Structure** | Fund size (target/hard cap), commitment period, fund life, extension options (number + LP consent threshold), recycling provisions, recallable distributions |
| **Governance** | LPAC composition, key-person provisions (trigger events + consequences), no-fault divorce (threshold + mechanics), removal for cause (threshold), GP removal / replacement |
| **Transparency** | Reporting frequency, audit rights, valuation policy (independent vs. GP discretion), LPAC information rights, advisory committee scope |
| **Co-Invest** | Co-invest rights (pro-rata, discretionary), co-invest fee/carry (none, reduced, full), allocation policy, minimum ticket size |
| **Liquidity** | Transfer restrictions, secondary approval process, ROFR provisions, lock-up period, distribution waterfall (timing) |
| **Conflicts** | Related-party transaction policy, cross-fund investment, allocation of opportunities, GP fund-level leverage |

**Output:** Structured JSON/YAML of all extracted fields with source references.

---

### TA-2: Term Quality Scoring

**Scoring Dimensions (1-5 scale each):**

| Dimension | Weight | What It Measures |
|-----------|--------|------------------|
| **Economics** | 30% | Fee level, carry alignment, GP co-investment |
| **Governance** | 30% | LP oversight, key-person, removal rights |
| **Transparency** | 20% | Reporting, valuation policy, audit access |
| **Liquidity** | 20% | Transfer rights, distribution mechanics, lock-up |

**Composite Scores:**
- **LP-Friendliness Score** (0-100): Weighted aggregate favoring LP protections
- **GP-Flexibility Score** (0-100): Weighted aggregate favoring GP operating room
- **Alignment Score** (0-100): How well GP incentives align with LP outcomes

**Benchmark Comparisons:**
- vs. ILPA Principles 3.0 recommendations
- vs. market median for same vintage/strategy
- vs. prior fund terms (if available)

---

### TA-3: Red-Flag Detection

**Rules Engine — Triggers:**

| # | Red Flag | Severity | Trigger Condition |
|---|----------|----------|-------------------|
| 1 | High fee on committed capital | High | Mgmt fee on committed > 4 years post-commitment period |
| 2 | No fee step-down | Medium | No reduction in mgmt fee basis after commitment period |
| 3 | Weak LP oversight on valuation | High | GP sole discretion on valuation, no independent agent |
| 4 | No key-person provision | Critical | No defined key-person event or consequence |
| 5 | High no-fault divorce threshold | High | Requires >75% LP vote for no-fault termination |
| 6 | Aggressive recycling | Medium | Recycling beyond commitment period or > 125% of commitments |
| 7 | No clawback | Critical | No GP clawback provision or weak escrow |
| 8 | Asymmetric information rights | High | LPAC members get materially more info than other LPs |
| 9 | Broad related-party carve-outs | High | Wide exceptions for GP affiliates in conflict policy |
| 10 | No co-invest fee/carry offset | Medium | Full economics charged on co-invest allocations |
| 11 | Unlimited extensions | Medium | GP can extend fund life without LP consent |
| 12 | Weak transfer rights | Medium | GP can unreasonably withhold transfer consent |

**Output per flag:**
- Clause reference
- Plain-language risk description
- ILPA benchmark comparison
- Suggested revision language
- Negotiation priority rating (must / should / nice-to-have / acceptable)

---

### TA-4: Negotiation Priorities Summary

**One-page output containing:**

```
┌─────────────────────────────────────────────────────┐
│  NEGOTIATION PRIORITIES — [Fund Name]               │
├─────────────────────────────────────────────────────┤
│                                                     │
│  COMPOSITE SCORES                                   │
│  LP-Friendliness: [XX]/100    GP-Flexibility: [XX]  │
│  Alignment: [XX]/100          vs. ILPA: [X/5]       │
│                                                     │
│  ┌─ MUST NEGOTIATE (Critical/High) ──────────────┐  │
│  │ 1. [Red flag + suggested revision]            │  │
│  │ 2. [Red flag + suggested revision]            │  │
│  └───────────────────────────────────────────────┘  │
│                                                     │
│  ┌─ SHOULD NEGOTIATE (Medium) ───────────────────┐  │
│  │ 3. [Red flag + suggested revision]            │  │
│  │ 4. [Red flag + suggested revision]            │  │
│  └───────────────────────────────────────────────┘  │
│                                                     │
│  ┌─ NICE TO HAVE ────────────────────────────────┐  │
│  │ 5. [Improvement opportunity]                  │  │
│  └───────────────────────────────────────────────┘  │
│                                                     │
│  TERM COMPARISON vs. PRIOR FUND                     │
│  [Table: Field | Fund III | Fund IV | Direction]    │
│                                                     │
│  CONFIDENTIAL — Prepared [Date]                     │
└─────────────────────────────────────────────────────┘
```

---

## Excel ↔ Slide Pairing

| Excel Module | Paired Slide |
|-------------|-------------|
| Term Extraction Table | Term Sheet Overview |
| LP-Friendliness Scorecard | Terms Quality Summary |
| Red-Flag Register | Negotiation Priorities |
| Term Comparison (Fund-over-Fund) | Terms Evolution |

---

## Integration Points

- **DDQ Case Flow:** TA-1 populates term-related DDQ answers automatically
- **Fundraising Case Flow:** TA-4 generates LP-facing term highlights
- **QA Rubric:** Evidence coverage for term claims uses claim-evidence schema
- **Event Telemetry:** Each extraction emits `term_risk_flagged` events (see `ir_event_schemas.yml`)

---

## Prompt Library References

- **Prompt 10** (existing): Term Sheet Summary — enhanced by TA-1 extraction
- **Prompt 25** (new): Term Sheet Red-Flag Scan
- **Prompt 26** (new): Negotiation Priorities Memo
- **Prompt 27** (new): Term Comparison (Fund vs. Peers)
- **Prompt 28** (new): LP-Friendliness Scorecard

---

*Version: 1.0 | Created: February 2026*
