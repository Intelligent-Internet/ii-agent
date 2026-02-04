# Daily Net Worth Newsletter Skill

## Overview
Automated daily net worth tracking that calculates portfolio value, tracks historical performance, runs risk analytics, and sends a formatted dashboard email.

## Capabilities
- Fetches real-time prices for all holdings
- Converts between USD and CAD using live exchange rates
- Tracks cost basis and unrealized gains/losses
- Maintains historical net worth data (up to 365 days)
- Generates 3-month trend chart
- **Portfolio Risk Analytics** (NEW in v1.1)
- Sends professional HTML dashboard email

## Dashboard Contents
1. **Total Net Worth** (in CAD and USD)
2. **Daily Change** (compared to previous day)
3. **3-Month Trend Chart** (embedded in email)
4. **Summary** (Total Assets vs Liabilities)
5. **Asset Allocation** (by asset class with visual bars)
6. **Portfolio Risk Analytics** (NEW)
   - Volatility (daily/annual)
   - Sharpe Ratio
   - Beta vs S&P 500
   - Max Drawdown
   - Value at Risk (95%)
7. **Concentration Analysis** (NEW)
   - Top 5 holdings weight
   - HHI concentration index
   - Largest position alert
8. **Rebalancing Recommendations** (NEW)
   - Current vs target allocation
   - Drift alerts (>5% threshold)
   - Buy/Sell recommendations
9. **Correlation Highlights** (NEW)
   - Highest correlated positions
   - Diversification risk alerts
10. **Market Assets Table** (with gains/losses)
11. **Cash & Bank Accounts**
12. **Liabilities**

## Asset Categories Supported
- Market assets (stocks, ETFs, commodities, crypto)
- Cash & bank accounts (CAD or USD)
- Retirement accounts (RRSP, TFSA, 401k)
- Real estate
- Liabilities (loans, debts)

## Required Configuration
| Config File | Description | Required |
|-------------|-------------|----------|
| `Config/gmail-credentials.txt` | Gmail address and app password | Yes |

## Output
- Email sent to configured Gmail address
- Historical data: `networth_history.json`
- Log file: `networth.log`

## Usage

### Manual Run
```bash
python Claire/Skills/networth-newsletter/networth.py
```

### Scheduled (Windows Task Scheduler)
Task Name: "Daily Net Worth Newsletter"
Schedule: Daily at 7:00 AM
Script: `run_networth.bat`

## Customization

### Update Holdings
Edit `config.py`:
```python
MARKET_HOLDINGS = {
    "Gold": {
        "quantity": 8.656,      # ounces
        "cost_basis_usd": 15000,
        "ticker": "GC=F",
        "type": "commodity",
        "unit": "oz"
    },
    "Bitcoin": {
        "quantity": 0.1,
        "cost_basis_usd": 5000,
        "ticker": "bitcoin",    # CoinGecko ID
        "type": "crypto",
        "unit": "BTC"
    },
}

CASH_ACCOUNTS = {
    "Checking": {"balance": 7000, "currency": "CAD"},
}

LIABILITIES = {
    "Student Loans": {"balance": 25215.60, "currency": "CAD"},
}
```

### Change Base Currency
Edit `BASE_CURRENCY` in `config.py` (default: "CAD")

### Customize Target Allocation (for Rebalancing Alerts)
Edit `portfolio_analytics.py`:
```python
DEFAULT_TARGET_ALLOCATION = {
    "Equities": 0.50,      # 50%
    "Fixed Income": 0.10,  # 10%
    "Commodities": 0.15,   # 15%
    "Crypto": 0.10,        # 10%
    "Cash": 0.15,          # 15%
}

REBALANCING_THRESHOLD = 0.05  # Alert if drift > 5%
```

## Example Prompts for Claude

> "Add 50 shares of Apple to my net worth tracker with a cost basis of $8,000 USD"

> "Update my student loan balance to $22,000"

> "Add a TFSA account with $15,000 CAD to the net worth newsletter"

> "Show me my net worth history for the last 30 days"

## Dependencies
```
yfinance>=0.2.0
requests>=2.28.0
matplotlib>=3.5.0
numpy>=1.21.0
```

## Files
| File | Description |
|------|-------------|
| `networth.py` | Main newsletter generator |
| `portfolio_analytics.py` | Risk analytics module (NEW) |
| `config.py` | Holdings and credentials |
| `networth_history.json` | Historical data |

---
*Skill Version: 1.1.0*
*Last Updated: 2026-02-04*
