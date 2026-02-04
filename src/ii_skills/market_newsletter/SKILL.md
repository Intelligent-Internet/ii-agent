# Daily Market Newsletter Skill

## Overview
Automated daily newsletter that fetches market data and news for tracked assets, then sends a formatted HTML email.

## Capabilities
- Fetches real-time prices from Yahoo Finance and CoinGecko
- Retrieves latest news headlines from NewsAPI
- Generates professional HTML email with:
  - Asset Performance Summary table (1D, 7D, 1M, 1Y returns)
  - Asset Class Performance (equal-weighted)
  - Key news drivers for each asset
  - Detailed asset cards with full news links

## Tracked Assets

### Precious Metals
- Gold (GC=F)
- Silver (SI=F)

### Base Metals
- Copper (HG=F)
- Alfamin Resources (AFM.V)
- Global X Copper Producers (COPX)

### Crypto
- Bitcoin
- Ethereum

### Semiconductors
- Lumentum (LITE)
- Coherent (COHR)
- Lattice Semiconductor (LSCC)
- Micron Technology (MU)
- iShares Semiconductor ETF (SOXX)

### Energy
- Tourmaline Oil (TOU.TO)

## Required Configuration
| Config File | Description | Required |
|-------------|-------------|----------|
| `Config/gmail-credentials.txt` | Gmail address and app password | Yes |
| `Config/newsapi-key.txt` | NewsAPI.org API key | Yes |

### Setup Gmail App Password
1. Enable 2-Factor Authentication on Gmail
2. Go to https://myaccount.google.com/apppasswords
3. Create app password for "Mail"

### Get NewsAPI Key
1. Register at https://newsapi.org/register
2. Copy API key (free tier: 100 requests/day)

## Output
- Email sent to configured Gmail address
- Log file: `newsletter.log`

## Usage

### Manual Run
```bash
python Claire/Skills/market-newsletter/newsletter.py
```

### Scheduled (Windows Task Scheduler)
Task Name: "Daily Market Newsletter"
Schedule: Daily at 7:00 AM
Script: `run_newsletter.bat`

## Customization

### Add New Assets
Edit `config.py`:
```python
ASSETS = {
    "New Asset": {
        "ticker": "TICKER",
        "news_query": "search terms",
        "asset_class": "Category"
    },
}
```

### Modify Asset Classes
Edit `ASSET_CLASSES` in `config.py` to change groupings for the summary table.

## Example Prompts for Claude

> "Add Tesla (TSLA) to the market newsletter under a new 'EV' asset class"

> "Change the newsletter to run at 6 AM instead of 7 AM"

> "Add a week-over-week price comparison chart to the newsletter"

## Dependencies
```
yfinance>=0.2.0
requests>=2.28.0
```

---
*Skill Version: 1.0.0*
*Last Updated: 2026-02-04*
