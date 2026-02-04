# Claude for Excel - Investment Banking Prompts

Use these prompts with your Claude for Excel plugin to build and enhance financial models.

---

## DCF MODEL PROMPTS

### Build DCF from scratch
```
Create a DCF valuation model for [COMPANY NAME] with:
- 5-year projection period
- Revenue growing at [X]% annually
- EBITDA margin of [X]%
- WACC of [X]%
- Terminal growth rate of [X]%
- Calculate enterprise value and implied share price
```

### Add sensitivity analysis
```
Add a sensitivity table showing how the share price changes with:
- WACC ranging from 8% to 12% (columns)
- Terminal growth ranging from 1% to 3% (rows)
Use a two-variable data table
```

### Calculate WACC
```
Calculate WACC with these inputs:
- Risk-free rate: [X]%
- Equity risk premium: [X]%
- Beta: [X]
- Cost of debt: [X]%
- Tax rate: [X]%
- Debt/Equity ratio: [X]
```

---

## LBO MODEL PROMPTS

### Build Sources & Uses
```
Create an LBO sources and uses table:
- Purchase price: $[X]M at [X]x EBITDA
- Senior debt: [X]x EBITDA at [X]% interest
- Sub debt: $[X]M at [X]% interest
- Sponsor equity: remainder
- Transaction fees: [X]% of EV
- Financing fees: [X]% of debt
```

### Calculate IRR and MoM
```
Calculate LBO returns assuming:
- Entry EBITDA: $[X]M
- Entry multiple: [X]x
- Exit multiple: [X]x
- Hold period: [X] years
- EBITDA grows [X]% annually
- Debt paydown from free cash flow

Show IRR and multiple of money (MoM)
```

### Debt schedule
```
Create a debt amortization schedule with:
- Term loan: $[X]M, [X]% interest, [X]% annual amortization
- Revolver: $[X]M capacity, [X]% interest, drawn as needed
- Cash sweep: [X]% of excess cash flow
Show beginning balance, interest, principal, ending balance each year
```

---

## COMPS MODEL PROMPTS

### Build trading comps
```
Create a trading comps table for [INDUSTRY] with these companies:
[LIST TICKERS]

Include: Stock price, shares out, market cap, net debt, EV, LTM revenue, LTM EBITDA, EV/Revenue, EV/EBITDA, P/E

Calculate mean, median, high, low for each multiple
```

### Apply comps to target
```
Using these trading multiples:
- EV/Revenue: [X]x - [X]x
- EV/EBITDA: [X]x - [X]x

Value [COMPANY] with:
- LTM Revenue: $[X]M
- LTM EBITDA: $[X]M
- Net debt: $[X]M
- Shares outstanding: [X]M

Show implied share price range for each methodology
```

### Transaction comps
```
Create a precedent transactions table for [INDUSTRY] M&A deals.
Include columns: Date, Target, Acquirer, Deal Value, LTM Revenue, LTM EBITDA, EV/Revenue, EV/EBITDA, Premium

Calculate median multiples
```

---

## 3-STATEMENT MODEL PROMPTS

### Build income statement
```
Create an income statement projection for [COMPANY]:
- Base year revenue: $[X]M
- Revenue growth: [X]% annually
- Gross margin: [X]%
- SG&A: [X]% of revenue
- D&A: [X]% of revenue
- Interest expense: $[X]M
- Tax rate: [X]%

Project 5 years
```

### Build balance sheet
```
Create a balance sheet that links to the income statement:
- DSO (days sales outstanding): [X] days
- Inventory days: [X] days
- DPO (days payable outstanding): [X] days
- CapEx: [X]% of revenue
- Existing debt: $[X]M
- Minimum cash balance: $[X]M
```

### Build cash flow statement
```
Create a cash flow statement that:
- Starts with net income from income statement
- Adds back D&A
- Calculates working capital changes from balance sheet
- Shows CapEx from balance sheet
- Calculates debt changes to balance
- Links ending cash back to balance sheet
```

### Check model integrity
```
Verify my 3-statement model is working correctly:
1. Does the balance sheet balance (assets = liabilities + equity)?
2. Does ending cash on cash flow = cash on balance sheet?
3. Does retained earnings roll forward correctly?
4. Are all circular references resolved?

Highlight any errors and show how to fix them
```

---

## M&A / ACCRETION-DILUTION PROMPTS

### Build merger model
```
Create an accretion/dilution analysis:

Acquirer ([TICKER]):
- Stock price: $[X]
- Shares out: [X]M
- LTM EPS: $[X]

Target ([TICKER]):
- Stock price: $[X]
- Shares out: [X]M
- LTM EPS: $[X]

Deal terms:
- [X]% cash / [X]% stock
- Premium: [X]%
- Synergies: $[X]M
- Integration costs: $[X]M

Show pro forma EPS and accretion/dilution %
```

### Contribution analysis
```
Create a contribution analysis showing what % each company contributes:
- Revenue
- EBITDA
- Net Income
- Employees
- Assets

Compare to ownership split
```

---

## GENERAL TIPS FOR CLAUDE FOR EXCEL

1. **Be specific with cell references**: "Put the formula in cell D5" is better than "add a formula"

2. **Describe the logic**: "Calculate revenue growth as (current year - prior year) / prior year"

3. **Ask for formatting**: "Format as currency with no decimals" or "Format as percentage with 1 decimal"

4. **Request error handling**: "Use IFERROR to show 'N/A' if dividing by zero"

5. **Build incrementally**: Start with inputs/assumptions, then build calculations step by step

6. **Ask for validation**: "Add a check that shows TRUE if the balance sheet balances"
