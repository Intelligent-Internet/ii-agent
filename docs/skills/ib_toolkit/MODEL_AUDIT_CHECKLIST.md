# Model Audit & QA Checklist
## Comprehensive Validation Framework for PE/IB Financial Models

*Version: 1.0.0 | Last Updated: February 2026*

---

## When to Use This Checklist

| Stage | Checks to Run |
|-------|---------------|
| After building core model (Phase 2) | Sections 1-3 |
| After adding institutional modules | Sections 1-4 |
| Before IC submission | Full checklist (Sections 1-6) |
| After model feedback/updates | Section 6 + any modified sections |

---

## Section 1: Structural Integrity (10 Checks)

### 1.1 Balance Sheet Balance

- [ ] **A = L + E in every period** — Assets equal Liabilities plus Equity for all historical and projected years
- [ ] **No period shows imbalance > $0.01** — Check the balance check row; any non-zero value is a critical error
- [ ] **Balance sheet balances under all scenarios** — Toggle Bull/Base/Bear and verify each

### 1.2 Cash Flow Tie-Out

- [ ] **Ending cash = Balance Sheet cash** — Cash Flow Statement ending cash balance ties exactly to BS cash line
- [ ] **Beginning cash (Year N) = Ending cash (Year N-1)** — Period continuity verified
- [ ] **Net change in cash = Ending − Beginning** — Arithmetic check on each period

### 1.3 Sources & Uses

- [ ] **Total Sources = Total Uses exactly** — Zero difference, no rounding gaps
- [ ] **Equity check = TEV − Total Debt − Other Sources** — Sponsor equity is the plug
- [ ] **Transaction fees are reasonable** — Typically 2-4% of TEV for advisory + financing fees
- [ ] **Debt amounts tie to Debt Schedule opening balances** — Each tranche in S&U matches Day 1 of Debt Schedule

---

## Section 2: Formula Integrity (10 Checks)

### 2.1 No Hardcodes in Formula Cells

- [ ] **All projection cells contain formulas, not hardcoded numbers** — Hardcodes should only appear in the Assumptions tab (blue font)
- [ ] **No "magic numbers" embedded in formulas** — Every constant should reference a named assumption
- [ ] **Growth rates and margins reference assumption cells** — Not typed directly into P&L formulas

### 2.2 Formula Consistency

- [ ] **Same formula pattern across all projection years** — Copy a formula from Year 1 to Year 5; if the pattern breaks, investigate
- [ ] **Row formulas are consistent left to right** — No manual overrides in middle periods
- [ ] **Circular references resolved** — Use iterative calculation or average balance method for debt/interest circularity

### 2.3 Error Cell Scan

- [ ] **Zero #REF! errors** — Broken references from deleted rows/columns
- [ ] **Zero #VALUE! errors** — Type mismatches in formulas
- [ ] **Zero #DIV/0! errors** — Division by zero (use IFERROR where appropriate)
- [ ] **Zero #N/A errors** — Failed lookups (check VLOOKUP/INDEX-MATCH ranges)

---

## Section 3: Cross-Tab Reference Validation (8 Checks)

### 3.1 P&L ↔ Balance Sheet

- [ ] **Net Income flows from P&L to Retained Earnings on BS** — Exact match, every period
- [ ] **D&A on P&L ties to PP&E schedule on BS** — Depreciation reduces PP&E
- [ ] **Interest expense on P&L ties to Debt Schedule interest** — Exact match

### 3.2 Balance Sheet ↔ Cash Flow

- [ ] **All BS changes flow through CF Statement** — ΔAR, ΔAP, ΔNWC, ΔDebt, ΔEquity all captured
- [ ] **CapEx on CF ties to PP&E changes on BS** — PP&E(t) = PP&E(t-1) − D&A + CapEx
- [ ] **Debt issuance/repayment on CF ties to BS debt balances** — Net debt change reconciles

### 3.3 Debt Schedule ↔ Other Tabs

- [ ] **Opening debt balances match S&U tranche amounts** — Day 1 consistency
- [ ] **Ending debt balances match BS debt line items** — Each tranche ties to its BS line

### 3.4 Reference Map

```
Assumptions Tab
    │
    ├──→ Revenue Build (growth rates, pricing)
    │        │
    │        └──→ P&L / Operating Model (revenue line)
    │                 │
    │                 ├──→ Balance Sheet (retained earnings, NWC)
    │                 │        │
    │                 │        └──→ Cash Flow Statement (BS changes)
    │                 │                 │
    │                 │                 └──→ Debt Schedule (cash available for paydown)
    │                 │                          │
    │                 │                          └──→ Returns Analysis (exit equity)
    │                 │                                   │
    │                 │                                   └──→ Sensitivity (varies assumptions)
    │                 │
    │                 └──→ Working Capital (revenue/COGS-driven)
    │
    ├──→ Debt Schedule (interest rates, terms, covenants)
    │
    ├──→ Returns Analysis (exit multiple, hold period)
    │
    └──→ Sensitivity (variable ranges)
```

---

## Section 4: Debt & Covenant Validation (6 Checks)

### 4.1 Debt Mechanics

- [ ] **No tranche exceeds its commitment amount** — Revolver draw ≤ Revolver commitment
- [ ] **Mandatory amortization is correct** — TLB: typically 1% p.a.; TLA: typically 5-10% p.a.
- [ ] **All debt is repaid by or at maturity** — Balloon payment at maturity clears remaining balance
- [ ] **Cash sweep logic is correct** — Excess cash applies to debt in seniority order (Senior → Sub → Mezz)

### 4.2 Covenant Compliance

- [ ] **Leverage covenant met in all periods** — Total Debt / EBITDA < covenant threshold (every year)
- [ ] **Interest coverage met in all periods** — EBITDA / Interest Expense > minimum (typically 2.0x)

### 4.3 Covenant Compliance Under Stress

- [ ] **Covenants met in Bear case** — Toggle to bear scenario and reverify
- [ ] **Identify covenant cushion** — How much EBITDA decline triggers a breach?

---

## Section 5: Returns & Sensitivity Validation (6 Checks)

### 5.1 Returns Sanity

- [ ] **MOIC × timing ≈ IRR** — Quick check: 2.0x in 5 years ≈ 15% IRR; 3.0x in 5 years ≈ 25% IRR
- [ ] **Gross IRR > Net IRR** — If net is higher, fee treatment is wrong
- [ ] **Value creation bridge sums to exit equity** — Entry equity + all drivers = exit equity
- [ ] **Value creation percentages sum to 100%** — EBITDA growth + multiple expansion + debt paydown = total

### 5.2 Sensitivity Reasonableness

- [ ] **Sensitivity ranges bracket realistic outcomes** — Not too narrow (trivial) or too wide (implausible)
- [ ] **No negative MOIC in any reasonable scenario** — If negative, check for formula errors

### 5.3 Quick MOIC/IRR Cross-Reference

| MOIC | 3-Year IRR | 4-Year IRR | 5-Year IRR | 6-Year IRR | 7-Year IRR |
|------|------------|------------|------------|------------|------------|
| 1.5x | 14% | 11% | 8% | 7% | 6% |
| 2.0x | 26% | 19% | 15% | 12% | 10% |
| 2.5x | 36% | 26% | 20% | 16% | 14% |
| 3.0x | 44% | 32% | 25% | 20% | 17% |
| 3.5x | 52% | 37% | 28% | 23% | 20% |
| 4.0x | 59% | 41% | 32% | 26% | 22% |

---

## Section 6: Formatting & Presentation (5 Checks)

- [ ] **Color coding is consistent** — Blue = inputs, Black = formulas, Green = cross-tab links (see `EXCEL_CONVENTIONS.md`)
- [ ] **Number formats are consistent** — Currency in millions ($#,##0.0), percentages (0.0%), multiples (0.0x)
- [ ] **Negative numbers use parentheses** — ($5.0) not -$5.0
- [ ] **Print areas are set** — Each tab prints cleanly on standard paper
- [ ] **Tab order is logical** — Cover → Assumptions → S&U → OpModel → BS → CF → Debt → Returns → Sensitivity

---

## Model Debugging Guide

### Problem: Balance Sheet Doesn't Balance

**Diagnosis steps:**
1. Check which period first goes out of balance
2. Compare Net Income on P&L vs. Retained Earnings change on BS
3. Check if all CF items flow to BS (common miss: deferred taxes, goodwill amortization)
4. Verify NWC changes on CF match ΔAR, ΔAP, ΔInventory on BS
5. Check that equity issuance/buyback flows through both CF and BS

**Common causes:**
- Missing deferred tax asset/liability
- CapEx on CF doesn't match PP&E schedule
- Dividend or distribution not captured on both CF and BS
- Debt repayment on CF doesn't reduce BS debt

### Problem: Circular Reference (Debt ↔ Interest)

**The issue:** Interest expense depends on debt balance, which depends on cash available for paydown, which depends on interest expense.

**Solution — Average Balance Method:**
```
Interest = Average(Beginning Debt, Ending Debt) × Rate

Where:
  Beginning Debt = Prior period ending debt
  Ending Debt = Beginning Debt − Mandatory Amortization − Optional Paydown
  Optional Paydown = Max(0, Free Cash Flow − Interest − Mandatory Amort)
```

**Alternative — Prior Period Method (simpler):**
```
Interest = Beginning Debt × Rate
```
This avoids circularity entirely. Less precise but acceptable for screening models.

### Problem: Returns Look Wrong

**Diagnosis steps:**
1. Verify entry equity = TEV − Net Debt (from S&U)
2. Verify exit equity = Exit TEV − Exit Net Debt
3. Check that exit EBITDA is the correct year (Year 5 for 5-year hold, not Year 6)
4. Check that exit multiple is applied to the right metric (EBITDA, not Revenue, unless growth equity)
5. Verify IRR formula uses correct cash flow timing (negative at T=0, positive at exit)

**Common causes:**
- Using entry year EBITDA instead of exit year for exit valuation
- Forgetting to subtract remaining debt at exit
- Wrong hold period assumption in IRR calculation
- Not including management rollover / co-invest in entry equity

### Problem: Sensitivity Table Shows Unexpected Values

**Diagnosis steps:**
1. Verify DATA TABLE input cells point to correct assumption cells
2. Check that the output cell references the correct returns cell
3. Ensure row/column inputs don't reference each other
4. Toggle each input manually and verify the output changes as expected

**Common causes:**
- Data table input cell points to wrong assumption
- Output cell has a hardcode instead of a formula
- Two-way data table has row and column inputs swapped

### Problem: Scenarios Don't Switch Cleanly

**Diagnosis steps:**
1. Check scenario toggle cell (should be a single dropdown or input)
2. Verify all conditional formulas reference the toggle cell
3. Ensure no formulas bypass the scenario logic with hardcodes

**Best practice:** Use `INDEX(MATCH())` or `CHOOSE()` to select scenario assumptions:
```
=INDEX(Assumptions!B5:B7, MATCH(ScenarioToggle, {"Bull","Base","Bear"}, 0))
```

---

## Pre-Submission Final Checklist

Run this 5-minute check before sending any model:

1. [ ] Toggle through all scenarios — no errors appear
2. [ ] Scroll through every tab — no obviously broken formatting
3. [ ] Check the balance check row — all zeros
4. [ ] Verify S&U balance — Sources = Uses
5. [ ] Spot-check 3 cross-tab links — they point to the right cells
6. [ ] Save a clean copy — remove any scratch work or debug tabs

---

*See also: `EXCEL_CONVENTIONS.md` for formatting standards, `LBO_CASE_GUIDE.md` for model quality checklist*

*Version: 1.0.0 | Last Updated: February 2026*
