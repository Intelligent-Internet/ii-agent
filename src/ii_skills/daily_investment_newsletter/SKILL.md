# Daily Investment Newsletter Skill

## Overview
Automated daily newsletter covering the Canadian investment landscape, including market events, political developments affecting investments, and key financial news.

## Configuration

### Required Credentials
| Credential | Location | Purpose |
|------------|----------|---------|
| Brave API Key | `Config/brave-api-key.txt` | Real-time news search |
| Google Credentials | `Config/google-credentials.json` | Send newsletter via Gmail |

### Dependencies
- `brave-search` skill - for fetching current news
- `gog` skill - for email delivery

## Search Topics

The newsletter aggregates news from these categories:

### 1. Canadian Markets
- TSX/TSX-V index movements
- Major Canadian stock movers
- Canadian IPOs and M&A activity
- Bank of Canada announcements

### 2. Political & Regulatory
- Federal government policy affecting investments
- Provincial regulatory changes (Ontario, Quebec, Alberta, BC)
- Trade policy (US-Canada relations, CUSMA)
- Tax policy changes
- Energy and natural resources policy

### 3. Sector Focus
- Energy (oil, gas, renewables)
- Mining and natural resources
- Real estate and REITs
- Financial services
- Technology sector

### 4. Economic Indicators
- Interest rate decisions
- Inflation data (CPI)
- Employment reports
- GDP updates
- Housing market data

## Workflow

```
┌─────────────┐   ┌─────────────┐   ┌─────────────┐   ┌─────────────┐
│ 1.SEARCH    │ → │ 2.AGGREGATE │ → │ 3.FORMAT    │ → │ 4.DELIVER   │
└─────────────┘   └─────────────┘   └─────────────┘   └─────────────┘
```

### Step 1: Search (via brave-search skill)
Execute searches for each category:
```
- "Canada stock market news today"
- "Bank of Canada announcement"
- "Canadian federal government investment policy"
- "TSX today top movers"
- "Canada economic indicators latest"
```

### Step 2: Aggregate
- Deduplicate results
- Prioritize by relevance and recency
- Group by category
- Extract key insights

### Step 3: Format
- Apply newsletter template
- Generate executive summary (3-5 bullet points)
- Include source links
- Add market snapshot section

### Step 4: Deliver (via gog skill)
- Send to configured recipient
- Save copy to `Memory/newsletters/`
- Log delivery status

## Output Locations

```
Memory/
├── newsletters/
│   └── YYYY-MM-DD-daily-investment.md    # Archive copy
└── search-results/
    └── YYYY-MM-DD-investment-search.md   # Raw search results
```

## Newsletter Template

See `templates/newsletter-template.md` for the HTML/Markdown template.

## Scheduling

### Recommended Schedule
- **Time:** 6:00 AM local time (before market open)
- **Frequency:** Daily (Monday-Friday)
- **Skip:** Weekends and Canadian market holidays

### Scheduler Integration
See `SCHEDULER.md` for cron/launchd setup instructions.

## Usage

### Manual Trigger
```
Generate today's Canadian investment newsletter
```

### With Custom Focus
```
Generate investment newsletter focusing on [energy sector / Bank of Canada / etc.]
```

## Rate Limits
- Brave Search: Respect API tier limits (typically 5-10 searches per newsletter)
- Gmail: Standard sending limits apply

## Error Handling
- If search fails: Retry 3x with backoff, then send partial newsletter with note
- If email fails: Save to Memory/newsletters/ and alert user
- Log all errors to learnings/
