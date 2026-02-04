# CLAUDE.md - II-Agent Skills System

## Overview

This is the ii-agent repository configured as your personal cloud operations base. It includes specialized skills for financial tracking, market analysis, and health monitoring.

## Available Skills

| Skill | Location | Capabilities |
|-------|----------|--------------|
| `ib_toolkit` | `src/ii_skills/ib_toolkit/` | Investment banking presentations, Excel models, deal analysis (M1-M14 modules) |
| `networth_newsletter` | `src/ii_skills/networth_newsletter/` | Daily net worth tracking, portfolio analysis, 7am email reports |
| `market_newsletter` | `src/ii_skills/market_newsletter/` | Market news aggregation, price tracking, asset class performance |
| `health_dashboard` | `src/ii_skills/health_dashboard/` | WHOOP integration, recovery/sleep/strain metrics |
| `daily_investment_newsletter` | `src/ii_skills/daily_investment_newsletter/` | Canadian investment news via Brave Search |

## Quick Commands

### Run a Newsletter Manually
```bash
# Net Worth Newsletter
python src/ii_skills/networth_newsletter/networth.py

# Market Newsletter
python src/ii_skills/market_newsletter/newsletter.py

# WHOOP Dashboard
python src/ii_skills/health_dashboard/whoop_newsletter.py
```

### Check Scheduled Tasks
```bash
schtasks /query /fo LIST | findstr -i "newsletter\|whoop\|networth"
```

## Configuration

Skills require configuration files. Template configs are in each skill directory.

### Credential Locations
| Skill | Config File | Required Credentials |
|-------|-------------|---------------------|
| `networth_newsletter` | `config.py` | Gmail address + app password, portfolio holdings |
| `market_newsletter` | `config.py` | Gmail + NewsAPI key |
| `health_dashboard` | `config.py` | Gmail + WHOOP OAuth credentials |
| `daily_investment_newsletter` | Uses Config/ | Brave API key, Google credentials |

### Setting Up Credentials
For each skill, copy `config.py` and fill in your credentials:
```python
# Example: networth_newsletter/config.py
GMAIL_ADDRESS = "your.email@gmail.com"
GMAIL_APP_PASSWORD = "your-app-password"
```

## Skill Documentation

Each skill has detailed documentation:
- `src/ii_skills/ib_toolkit/SKILL.md` - IB Toolkit usage
- `src/ii_skills/networth_newsletter/SKILL.md` - Net Worth setup
- `src/ii_skills/market_newsletter/SKILL.md` - Market news setup
- `src/ii_skills/health_dashboard/SKILL.md` - WHOOP integration

Additional IB documentation:
- `docs/skills/ib_toolkit/BEST_PRACTICES.md`
- `docs/skills/ib_toolkit/ORCHESTRATION_FRAMEWORK.md`
- `docs/skills/ib_toolkit/PROMPT_LIBRARY.md`

## Development

### Install Dependencies
```bash
pip install -r src/ii_skills/networth_newsletter/requirements.txt
pip install -r src/ii_skills/market_newsletter/requirements.txt
pip install -r src/ii_skills/health_dashboard/requirements.txt
pip install -r src/ii_skills/ib_toolkit/requirements.txt
```

### Project Structure
```
ii-agent/
├── src/
│   ├── ii_agent/          # Core agent (for full deployment)
│   ├── ii_skills/         # Skills plugins (your tools)
│   │   ├── ib_toolkit/
│   │   ├── networth_newsletter/
│   │   ├── market_newsletter/
│   │   ├── health_dashboard/
│   │   ├── daily_investment_newsletter/
│   │   └── memory/
│   └── ii_tool/           # Tool server
├── docs/                  # Documentation site
├── frontend/              # Web UI (optional)
└── Config/                # Credentials (gitignored)
```

## Security

- **Never commit credentials** - Config files with real values stay local
- Template configs use placeholder values
- `.gitignore` excludes sensitive files

## Example Prompts

### Portfolio Management
> "Add 50 shares of NVDA at $800 to my net worth tracker in the IBKR USD account"
> "Update my student loan balance to $20,000"
> "Show me my asset allocation breakdown"

### Market Research
> "What's happening with copper prices today?"
> "Generate a company profile deck for Tourmaline Oil (TOU.TO)"
> "Run the M7 valuation module for a target company"

### Health Tracking
> "What was my average HRV this week?"
> "Set up the WHOOP dashboard to send at 7am"

---

*Base System: ii-agent (github.com/robertodbabaran/ii-agent)*
*Skills Version: 1.0.0*
*Last Updated: 2026-02-04*
