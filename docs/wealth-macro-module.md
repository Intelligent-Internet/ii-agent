# Wealth Macro Module: Approach & Architecture

## Objective
Build a **standalone** wealth macro module that produces a daily newsletter. The module should
synthesize global liquidity regimes (Michael Howell), the Changing World Order framework (Ray Dalio),
and macro/market data into actionable interpretation for asset classes and sectors.

## Non-Interference Principle
- Implemented as a **separate skill** (`src/ii_skills/wealth_macro_newsletter`).
- Uses its own storage folder under `Memory/wealth_macro_newsletter`.
- Can run on its own schedule/cron without touching other agents.

## Newsletter Sections (initial)
1. **Liquidity Regime**
   - Compute a global liquidity score (expanding/contracting) and explain key drivers.
2. **Changing World Order Lens**
   - Track debt-cycle position, internal/external conflict signals, and geopolitical risk.
3. **Macro Indicators**
   - Growth, inflation, labor, policy rates, credit conditions, and FX trends.
4. **Asset-Class & Sector Playbook**
   - Map liquidity regime to which assets/industries historically respond best.
5. **Media Watch**
   - Summaries of recent Howell/Dalio appearances (YouTube, podcasts, speeches) with citations.
6. **Social Pulse**
   - Include screenshots from tracked accounts (DrJStrategy, CrossBorder Capital) when posted.

## Data Ingestion Plan
- **Macro & Liquidity**: FRED/BIS/IMF/central bank releases.
- **Markets**: rates, FX, equities, credit spreads, commodities.
- **Media**: YouTube transcripts + RSS + web scraping for slide decks or notes.

## YouTube & Media Scanning Strategy
- Maintain a watchlist of authors/keywords (e.g., "Michael Howell", "CrossBorder Capital").
- Poll YouTube API for new uploads and capture transcripts when available.
- Fall back to RSS feeds/podcast indexes for episodes without transcripts.
- Extract slides/attachments from linked resources when present.
- Capture daily screenshots for the tracked social accounts when new posts are available.

## Output Targets
- Markdown/HTML newsletter stored in `Memory/wealth_macro_newsletter/newsletters/`.
- Source digest stored in `Memory/wealth_macro_newsletter/sources/`.
- Optional email delivery via shared skill config (Gmail SMTP).

## Next Steps
- Implement real fetchers (FRED + YouTube) and liquidity-score computation.
- Add a small evaluation layer to track forecast accuracy/learning.
- Integrate notification layer (email/Slack) using existing delivery tooling.

## Additional Macro Frameworks Worth Tracking
- **Growth/Inflation Quadrants** (risk-on/off mapping).
- **Policy Mix** (monetary + fiscal stance and transmission).
- **Financial Conditions Index** (credit spreads, vol, equity risk).
- **Yield Curve & Term Premium** (recession risk, duration sensitivity).
- **USD Funding Stress / Global Dollar Liquidity** (EM risk proxy).
- **China Credit Impulse** (global industrial demand signal).
- **Commodity Supercycle** (supply constraints, inventory cycle).
