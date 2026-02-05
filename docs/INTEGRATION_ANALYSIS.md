# II-Agent + Skills Integration Analysis

A strategic framework for unifying the ii-agent core infrastructure with the specialized skills system to create a more powerful, integrated financial intelligence platform.

---

## Executive Summary

The ii-agent repository contains two parallel capability streams that have developed independently:

1. **Core II-Agent Infrastructure** - A production-grade agentic framework with 50+ tools, multi-model LLM support, sub-agent orchestration, cloud storage, real-time events, and MCP protocol support.

2. **II-Skills System** - Specialized domain skills (IB Toolkit, Portfolio Tracking, Market News, Health Dashboard) operating in isolation with their own data sources and outputs.

**The Opportunity:** These systems share no data, no communication channels, and no orchestration. Integrating them would create a unified platform where:
- Portfolio holdings inform deal analysis
- Market research feeds financial models
- Real-time data enhances static outputs
- Multi-agent orchestration accelerates complex workflows
- Persistent memory enables learning and context retention

---

## Current State Analysis

### Core II-Agent Capabilities (Underutilized by Skills)

| Capability | What It Does | Current Skills Usage |
|------------|--------------|---------------------|
| **Sub-Agent Orchestration** | Spawn agents as tools, parallel execution | Not used |
| **Web Search** | SerpAPI, DuckDuckGo with fallbacks | Not used (skills use own APIs) |
| **Web Browsing** | Firecrawl, Jina, Tavily content extraction | Not used |
| **Researcher Agent** | Deep research with II-Researcher | Not used |
| **Cloud Storage (GCS)** | Permanent URLs, file management | Not used (local files only) |
| **Real-Time Events** | Socket.IO pub/sub | Not used |
| **Database (PostgreSQL)** | Persistent storage, user data | Not used |
| **Redis** | Caching, distributed messaging | Not used |
| **MCP Protocol** | External tool integration | Not used |
| **Browser Automation** | Playwright-based web interaction | Not used |
| **Code Execution (E2B)** | Sandboxed Python/Node execution | Not used |
| **Context Management** | Token optimization, summarization | Not used |

### Skills System Capabilities (Isolated)

| Skill | Data Sources | Outputs | Integration Points |
|-------|--------------|---------|-------------------|
| **IB Toolkit** | Yahoo Finance (free) | Excel, PowerPoint | Could use: web search, researcher, cloud storage |
| **Net Worth** | Yahoo Finance, CoinGecko | Email, JSON history | Could use: database, real-time events |
| **Market News** | NewsAPI, Yahoo Finance | Email | Could use: web search, researcher |
| **Health Dashboard** | WHOOP API | Email | Could use: database, analytics |
| **Daily Investment** | Brave Search | Email | Could use: web search tools |

---

## Integration Opportunities

### 1. Unified Data Layer

**Current Problem:** Each skill fetches its own data, stores locally, and has no awareness of other skills.

**Integration Vision:**
```
                    ┌─────────────────────────────────────┐
                    │         UNIFIED DATA LAYER          │
                    │  PostgreSQL + Redis + GCS Storage   │
                    └─────────────────────────────────────┘
                                      │
        ┌─────────────┬───────────────┼───────────────┬─────────────┐
        ▼             ▼               ▼               ▼             ▼
   Portfolio      Market Data    Company Data    Health Data    Deal History
   (holdings,     (prices,       (financials,    (HRV, sleep,   (models,
    history)      news)          profiles)       recovery)      memos)
        │             │               │               │             │
        └─────────────┴───────────────┴───────────────┴─────────────┘
                                      │
                    ┌─────────────────┴─────────────────┐
                    │           ALL SKILLS              │
                    │  ib_toolkit | networth | market   │
                    └───────────────────────────────────┘
```

**Implementation:**
1. Create shared `DataStore` class wrapping PostgreSQL/Redis
2. Define common schemas for holdings, prices, company data
3. Skills read/write to shared store instead of isolated files
4. Enable cross-skill queries (e.g., "analyze my portfolio holdings")

**Value:** Portfolio analysis in IB Toolkit could automatically use your actual holdings. Market news could highlight stocks you own.

---

### 2. Research-Enhanced Analysis

**Current Problem:** IB Toolkit uses only Yahoo Finance. No web research, no news integration, no deep diligence capability.

**Integration Vision:**
```
User: "Build an LBO model for Tourmaline Oil"
                      │
                      ▼
            ┌─────────────────┐
            │  ORCHESTRATOR   │
            └────────┬────────┘
                     │
     ┌───────────────┼───────────────┐
     ▼               ▼               ▼
┌─────────┐    ┌─────────┐    ┌─────────┐
│ Yahoo   │    │ Web     │    │Researcher│
│ Finance │    │ Search  │    │ Agent   │
│ (basic) │    │ (news)  │    │ (deep)  │
└────┬────┘    └────┬────┘    └────┬────┘
     │              │              │
     └──────────────┴──────────────┘
                    │
                    ▼
         ┌─────────────────┐
         │ ENRICHED DATA   │
         │ for LBO Model   │
         └─────────────────┘
```

**Implementation:**
1. Add `EnrichedDataFetcher` that combines Yahoo Finance + Web Search + Researcher Agent
2. For company analysis: fetch financials + recent news + industry research
3. For due diligence: spawn Researcher Agent for deep investigation
4. Cache results in shared data layer

**New Capabilities:**
- "Research Tourmaline Oil's competitive position" → Deep web research
- "Find recent news about copper miners" → Integrated news search
- "What are analysts saying about this company?" → Web search + extraction

---

### 3. Multi-Agent Deal Orchestration

**Current Problem:** The 52-prompt orchestration framework exists in documentation but isn't connected to the core sub-agent system.

**Integration Vision:**
```
Deal Case Initiated
        │
        ▼
┌───────────────────────────────────────────────────────────┐
│                    DEAL ORCHESTRATOR                       │
│  (Uses core AgentController + Sub-Agent Framework)         │
└───────────────────────────────────────────────────────────┘
        │
        ├──▶ Phase 0: Foundation (Parallel)
        │    ├── Agent: Company Overview
        │    ├── Agent: Market Sizing
        │    └── Agent: Business Model
        │
        ├──▶ Phase 1: Analysis (Parallel)
        │    ├── Agent: Competitive Analysis
        │    ├── Agent: Customer Analysis
        │    └── Agent: Management Assessment
        │
        ├──▶ Phase 2: Modeling (Sequential)
        │    ├── Agent: Revenue Build
        │    ├── Agent: Operating Model
        │    └── Agent: Returns Analysis
        │
        └──▶ Phase 3: IC Prep (Parallel)
             ├── Agent: Thesis Builder
             ├── Agent: Risk Matrix
             └── Agent: Slide Generator
```

**Implementation:**
1. Create `DealOrchestrator` class using `BaseAgentTool` framework
2. Each phase spawns sub-agents using core orchestration
3. State managed in PostgreSQL (not local JSON)
4. Real-time progress via Socket.IO events
5. Checkpoints saved to cloud storage

**Value:** Full 72-hour deal analysis automated with parallel execution, 50-70% time reduction.

---

### 4. Real-Time Portfolio Intelligence

**Current Problem:** Net worth newsletter runs on schedule, produces static email. No real-time alerts, no integration with analysis.

**Integration Vision:**
```
┌─────────────────────────────────────────────────────────────┐
│                 REAL-TIME PORTFOLIO ENGINE                   │
└─────────────────────────────────────────────────────────────┘
        │
        ├── Live Price Feeds ──▶ Redis Pub/Sub ──▶ Alerts
        │
        ├── Holdings Database ──▶ PostgreSQL ──▶ Analytics
        │
        ├── Socket.IO Events ──▶ Frontend Dashboard
        │
        └── IB Toolkit Integration:
            • "Analyze my copper exposure" → Holdings + LBO analysis
            • "What if Tourmaline drops 20%?" → Portfolio stress test
            • "Build model for stock I own" → Auto-populate from holdings
```

**Implementation:**
1. Store holdings in PostgreSQL with real-time price updates
2. Publish price changes to Redis pub/sub
3. Create alert rules engine (price thresholds, % changes)
4. Connect to Socket.IO for live frontend updates
5. Enable IB Toolkit to query "my holdings" for personalized analysis

**New Capabilities:**
- Real-time portfolio dashboard
- Price alerts via Socket.IO
- "Analyze risk in my semiconductor holdings"
- "Stress test my portfolio at -20% copper"

---

### 5. Persistent Memory & Learning

**Current Problem:** Memory skill is planned but not implemented. No context retention across sessions.

**Integration Vision:**
```
┌─────────────────────────────────────────────────────────────┐
│                      MEMORY SYSTEM                           │
│         (PostgreSQL + Vector Store + Redis Cache)            │
└─────────────────────────────────────────────────────────────┘
        │
        ├── Deal History
        │   • Past analyses and models
        │   • Investment decisions and outcomes
        │   • Lessons learned
        │
        ├── User Preferences
        │   • Preferred model assumptions
        │   • Risk tolerance
        │   • Sector expertise
        │
        ├── Company Knowledge Base
        │   • Previously researched companies
        │   • Competitive landscapes
        │   • Industry dynamics
        │
        └── Learning Log
            • What worked in past analyses
            • Common adjustment patterns
            • User feedback on outputs
```

**Implementation:**
1. Implement memory skill using PostgreSQL tables
2. Add vector embeddings for semantic search (company knowledge)
3. Track deal outcomes for learning
4. Enable "remember this" commands
5. Auto-suggest based on similar past deals

**New Capabilities:**
- "What did we conclude about copper miners last time?"
- "Use the same assumptions as the last TOU analysis"
- "Show me all tech deals we've analyzed"
- Learning from user corrections over time

---

### 6. Enhanced Output Distribution

**Current Problem:** Skills output to local files or single email. No cloud storage, no shareable links, no collaboration.

**Integration Vision:**
```
Skill Output Generated
        │
        ▼
┌───────────────────┐
│  OUTPUT ROUTER    │
└────────┬──────────┘
         │
    ┌────┴────┬────────────┬────────────┐
    ▼         ▼            ▼            ▼
┌───────┐ ┌───────┐ ┌──────────┐ ┌──────────┐
│ Local │ │  GCS  │ │  Email   │ │ Frontend │
│ File  │ │Storage│ │ (Gmail)  │ │Dashboard │
└───────┘ └───┬───┘ └──────────┘ └──────────┘
              │
              ▼
        Shareable URL
        (custom domain)
```

**Implementation:**
1. All skill outputs upload to GCS automatically
2. Generate shareable URLs with custom domain
3. Track outputs in database with metadata
4. Enable "share this analysis" functionality
5. Frontend gallery of past outputs

**New Capabilities:**
- Shareable deal memos via URL
- Output history and versioning
- Collaborative review in frontend
- "Show me all models created this month"

---

### 7. Health-Wealth Correlation Engine

**Current Problem:** Health dashboard and portfolio are completely separate. No correlation analysis.

**Integration Vision:**
```
┌─────────────────────────────────────────────────────────────┐
│              HEALTH-WEALTH CORRELATION ENGINE                │
└─────────────────────────────────────────────────────────────┘
        │
        ├── Health Data (WHOOP)
        │   • Sleep quality
        │   • HRV trends
        │   • Recovery scores
        │
        ├── Portfolio Data (Net Worth)
        │   • Daily P&L
        │   • Trading activity
        │   • Risk metrics
        │
        └── Correlation Analysis
            • "Does poor sleep correlate with worse trading decisions?"
            • "Recovery score vs portfolio volatility"
            • "Optimal decision-making health metrics"
```

**Implementation:**
1. Store both datasets in unified database with timestamps
2. Create correlation analysis module
3. Generate insights: "Your best trading days have avg HRV of X"
4. Behavioral alerts: "Low recovery - consider avoiding trades today"

**Value:** Unique personal insights combining health and financial data.

---

## Implementation Roadmap

### Phase 1: Foundation (Week 1-2) ✅ COMPLETE

| Task | Priority | Status |
|------|----------|--------|
| Create shared DataStore class | High | ✅ **DONE** |
| Add GCS upload to skill outputs | Medium | ✅ **DONE** |
| Create unified configuration system | Medium | ✅ **DONE** |
| Migrate networth holdings to PostgreSQL | High | 🔄 Ready (run migration + loader) |
| Connect IB Toolkit to shared store | High | ✅ **DONE** |

**Completed Components:**
- `src/ii_agent/db/skills_models.py` - 7 new database models
- `src/ii_agent/migrations/versions/skills_001_add_skills_integration_tables.py` - Database migration
- `src/ii_skills/shared/datastore.py` - Unified DataStore with async methods
- `src/ii_skills/shared/storage.py` - GCS integration for skill outputs
- `src/ii_skills/shared/skill_config.py` - Centralized configuration
- `src/ii_skills/shared/portfolio_loader.py` - Migration helper for networth data
- `src/ii_skills/ib_toolkit/storage_integration.py` - IB Toolkit GCS + DB integration
- `scripts/run_migrations.py` - Standalone migration runner

### Phase 2: Research Integration (Week 3-4) ✅ COMPLETE

| Task | Priority | Status |
|------|----------|--------|
| Create EnrichedDataFetcher | High | ✅ **DONE** |
| Integrate web search into IB Toolkit | High | ✅ **DONE** |
| Add Researcher Agent for due diligence | Medium | ✅ **DONE** |
| News integration for deal analysis | Medium | ✅ **DONE** |

**Completed Components:**
- `src/ii_skills/shared/research.py` - Unified research client:
  - Web search (SerpAPI, DuckDuckGo with fallback)
  - Content extraction (FireCrawl, Jina, Tavily, BeautifulSoup fallback)
  - Deep research with multi-query support
- `src/ii_skills/ib_toolkit/enriched_data.py` - Enhanced data fetcher:
  - Yahoo Finance + web research integration
  - Company data enrichment with news, competitors, trends
  - Deal-focused research (LBO, growth equity, add-on, carve-out)
  - Investment thesis generation
- `storage_integration.py` updated with:
  - `generate_research_enhanced_model()` - LBO model with auto-research
  - `generate_research_enhanced_deck()` - Slides with enriched data
  - Automatic research report generation

### Phase 3: Multi-Agent Orchestration (Week 5-6) ✅ COMPLETE

| Task | Priority | Status |
|------|----------|--------|
| Create DealOrchestrator class | High | ✅ **DONE** |
| Implement Phase 0-3 agent spawning | High | ✅ **DONE** |
| Add real-time progress via Socket.IO | Medium | ✅ **DONE** |
| Cloud checkpoint storage | Medium | ✅ **DONE** |

**Completed Components:**
- `src/ii_skills/ib_toolkit/deal_orchestrator.py` - Multi-phase orchestrator:
  - 5 execution phases: DATA_COLLECTION, FOUNDATION, FINANCIAL, DEAL_STRUCTURE, OUTPUT
  - 17 specialized task handlers for parallel execution
  - DealState management with context passing between phases
  - Checkpoint saving after each phase for recovery
  - Console and async progress callbacks
- `src/ii_skills/ib_toolkit/orchestrator_events.py` - Real-time event system:
  - EventStreamProgressCallback for ii-agent event stream integration
  - WebhookProgressCallback for external integrations
  - CompositeProgressCallback for multi-channel broadcasting
  - Socket.IO ready event publishing
- `__init__.py` updated with orchestrator exports

### Phase 4: Real-Time & Memory (Week 7-8)

| Task | Priority | Effort |
|------|----------|--------|
| Implement memory skill | High | 4 days |
| Real-time price feeds to Redis | Medium | 2 days |
| Portfolio dashboard frontend | Medium | 3 days |
| Alert rules engine | Low | 2 days |

---

## Architecture After Integration

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          II-AGENT UNIFIED PLATFORM                       │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌────────────────────────────────────────────────────────────────────┐ │
│  │                        ORCHESTRATION LAYER                          │ │
│  │  • Deal Orchestrator (52-prompt framework)                         │ │
│  │  • Sub-Agent Spawning (parallel execution)                         │ │
│  │  • Task State Management                                           │ │
│  └────────────────────────────────────────────────────────────────────┘ │
│                                    │                                     │
│  ┌──────────────┬─────────────────┼─────────────────┬────────────────┐  │
│  │              │                 │                 │                │  │
│  ▼              ▼                 ▼                 ▼                ▼  │
│ ┌────────┐ ┌─────────┐ ┌─────────────┐ ┌─────────┐ ┌──────────────┐  │
│ │   IB   │ │   Net   │ │   Market    │ │  Health │ │    Memory    │  │
│ │Toolkit │ │  Worth  │ │    News     │ │Dashboard│ │    Skill     │  │
│ │ (67)   │ │ Tracker │ │  Aggregator │ │ (WHOOP) │ │ (Persistent) │  │
│ └────────┘ └─────────┘ └─────────────┘ └─────────┘ └──────────────┘  │
│      │          │             │             │             │           │
│      └──────────┴─────────────┴─────────────┴─────────────┘           │
│                                    │                                     │
│  ┌────────────────────────────────┴───────────────────────────────────┐ │
│  │                         SHARED DATA LAYER                           │ │
│  │  PostgreSQL (structured) + Redis (cache) + GCS (files)             │ │
│  │  • Holdings & Prices    • Deal History    • Company Knowledge      │ │
│  │  • User Preferences     • Output Archive  • Learning Log           │ │
│  └────────────────────────────────────────────────────────────────────┘ │
│                                    │                                     │
│  ┌────────────────────────────────┴───────────────────────────────────┐ │
│  │                         CORE CAPABILITIES                           │ │
│  │  • Multi-Model LLM (Claude/GPT/Gemini)                             │ │
│  │  • Web Search & Research Agents                                     │ │
│  │  • Browser Automation (Playwright)                                  │ │
│  │  • Real-Time Events (Socket.IO)                                     │ │
│  │  • MCP Protocol Integration                                         │ │
│  │  • Code Execution Sandbox (E2B)                                     │ │
│  └────────────────────────────────────────────────────────────────────┘ │
│                                    │                                     │
│  ┌────────────────────────────────┴───────────────────────────────────┐ │
│  │                          OUTPUT CHANNELS                            │ │
│  │  • Email (Gmail SMTP)           • Shareable URLs (GCS + CDN)       │ │
│  │  • Frontend Dashboard           • API Endpoints                     │ │
│  │  • Real-Time Alerts             • Scheduled Reports                 │ │
│  └────────────────────────────────────────────────────────────────────┘ │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## New Unified Capabilities (Post-Integration)

### Deal Analysis
```
"Build a comprehensive analysis of Tourmaline Oil"
  → Spawns parallel agents for:
    - Financial data (Yahoo Finance)
    - Recent news (Web Search)
    - Competitive research (Researcher Agent)
    - Industry dynamics (Web browsing)
  → Produces: LBO model + IC deck + Research summary
  → Stores: Cloud storage with shareable URL
  → Remembers: Adds to company knowledge base
```

### Portfolio-Aware Analysis
```
"Analyze my copper exposure risk"
  → Queries: Holdings database for copper positions
  → Fetches: Current prices and news
  → Runs: IB Toolkit stress test module
  → Correlates: With health data (optional)
  → Alerts: If thresholds exceeded
```

### Automated Deal Pipeline
```
"Start a 5-day deal analysis for [Company]"
  → Creates: Deal in database with state tracking
  → Executes: 52-prompt orchestration via sub-agents
  → Reports: Real-time progress via Socket.IO
  → Checkpoints: Saves state to cloud storage
  → Delivers: Final package to email + shareable URL
```

### Intelligent Assistant
```
"What do you remember about mining investments?"
  → Queries: Memory system for past analyses
  → Returns: Summary of companies analyzed, conclusions, lessons
  → Suggests: "Based on past work, you might want to look at X"
```

---

## Success Metrics

| Metric | Current | Target |
|--------|---------|--------|
| Cross-skill data sharing | 0% | 100% |
| Research sources per analysis | 1 (Yahoo Finance) | 5+ |
| Parallel agent utilization | 0% | 70% |
| Output persistence (cloud) | 0% | 100% |
| Analysis time (comprehensive) | Manual | 50% reduction |
| Context retention | 0 sessions | Unlimited |
| Real-time capabilities | None | Full dashboard |

---

## Next Steps

1. **Review this analysis** - Prioritize which integrations matter most
2. **Start with data layer** - Foundation for everything else
3. **Pilot with one skill** - Likely networth (smallest, clearest value)
4. **Expand incrementally** - Add capabilities one at a time
5. **Document as we go** - Update CLAUDE.md with new capabilities

---

*Document Version: 1.0.0*
*Created: 2026-02-04*
*Author: Claude Code + Roberto Babaran*
