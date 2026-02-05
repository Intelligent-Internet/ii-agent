---
name: wealth-macro-newsletter
description: "Daily macro + liquidity newsletter synthesis and media scanning for frameworks like Michael Howell global liquidity and Ray Dalio Changing World Order, including asset-class/sector playbooks and transcript monitoring."
---

# Wealth Macro Newsletter Skill

## Overview
Create a daily macro + liquidity focused newsletter that blends:
- Michael Howell-style global liquidity framework
- Ray Dalio-style Changing World Order framework
- Core macro indicators (growth, inflation, liquidity, policy, credit)
- Tactical asset-class/sector implications
- Continuous monitoring of podcasts/interviews (e.g., YouTube) and publications
- Social media screenshots from the tracked accounts (DrJStrategy, CrossBorder Capital)

This skill is designed as a **separate component** that can run independently
from other agents in the repository.

## Intended Outputs
- Daily newsletter (Markdown/HTML)
- Source digest (links + transcript excerpts)
- Data snapshot tables/figures for liquidity + macro indicators

## Data Sources (examples)
- **Liquidity**: BIS, IMF, Federal Reserve (H.4.1), ECB, PBoC, Treasury GA, RRP
- **Macro**: FRED, OECD, World Bank, IMF, national statistics
- **Markets**: major index returns, rates, credit spreads, FX, commodities
- **Media**: YouTube (transcripts), podcasts, policy speeches, sell-side notes

## Workflow
1. **Ingest**
   - Pull macro + liquidity series for the latest prints
   - Monitor new media appearances from tracked authors (YouTube, RSS, web)
   - Capture any daily screenshots from tracked social accounts when available
2. **Normalize/Compute**
   - Liquidity regime score (expanding/contracting)
   - Dalio-style cycle tags (debt cycle, internal/external conflict, etc.)
3. **Synthesize**
   - Map liquidity regime to asset-class/sector playbook
   - Summarize key media insights with citations
   - Tag insights with additional macro frameworks (see below)
4. **Publish**
   - Render newsletter template
   - Save to archive and (optionally) email/slack

## Configuration
- Add API keys to a dedicated settings file (see `settings.py`)
- Store per-source fetcher settings in JSON/YAML
- Use separate cron/job so other agents remain unaffected
- Email delivery uses shared skill config (set `GMAIL_ADDRESS`, `GMAIL_APP_PASSWORD`, and `RECIPIENT_EMAIL`)

## Additional Macro Frameworks to Consider
- **Growth/Inflation Quadrants (e.g., #Quad framework)**: classify regimes for asset behavior.
- **Policy Mix (monetary + fiscal)**: assess combined stance and transmission channels.
- **Financial Conditions Index (FCI)**: synthesize risk appetite, credit spreads, and volatility.
- **Yield Curve & Term Premium**: infer recession risk and duration sensitivity.
- **Global Dollar Liquidity / USD Smile**: proxy for EM risk and funding stress.
- **China Credit Impulse**: lead indicator for global industrial demand.
- **Commodity Supercycle Signals**: supply constraints, inventory cycles, and CAPEX trends.

## Usage
"Generate daily wealth macro newsletter"

To send an email:
```
python src/ii_skills/wealth_macro_newsletter/generate_newsletter.py --send --to you@example.com
```

## Notes
- This skill is a scaffold. It provides a place to integrate data fetchers and
  content synthesis without disrupting existing workflows.
