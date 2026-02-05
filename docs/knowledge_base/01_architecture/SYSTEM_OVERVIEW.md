# System Overview

## Three-Layer Architecture

```
┌─────────────────────────────────────────────────────┐
│                   FRONTEND (Tauri/React)             │
│                   Port 1420 • Desktop App            │
└──────────────────────┬──────────────────────────────┘
                       │ Socket.IO (WebSocket)
┌──────────────────────▼──────────────────────────────┐
│                   ii_agent (Orchestration)           │
│                   Port 8000 • FastAPI                │
│                                                      │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────┐ │
│  │SocketIO     │→ │AgentService  │→ │AgentController│
│  │Manager      │  │              │  │            │ │
│  └─────────────┘  └──────┬───────┘  └──────┬─────┘ │
│                          │                  │       │
│                   ┌──────▼──────────────────▼────┐  │
│                   │    AgentToolManager          │  │
│                   │    (registers all tools)     │  │
│                   └──────┬──────────────────┬────┘  │
│                          │                  │       │
└──────────────────────────┼──────────────────┼───────┘
                           │                  │
          ┌────────────────▼───┐   ┌──────────▼──────────┐
          │    ii_tool (MCP)   │   │  ii_skills (Bridge)  │
          │    Port 1236       │   │  ★ NEW CONNECTION ★  │
          │                    │   │                      │
          │ • Shell (tmux)     │   │ • IB Toolkit (67)    │
          │ • File I/O         │   │ • IR Toolkit (33)    │
          │ • Web search       │   │ • Net Worth          │
          │ • Browser (PW)     │   │ • Market News        │
          │ • Slides (pptx)    │   │ • Health Dashboard   │
          │ • Media gen        │   │                      │
          └────────────────────┘   └──────────────────────┘
                                            │
                                   ┌────────▼────────┐
                                   │  Shared Infra   │
                                   │                 │
                                   │ • TaskGraph     │
                                   │ • RunBudgets    │
                                   │ • Telemetry     │
                                   │ • DataStore     │
                                   │ • PriceFeeds    │
                                   │ • Research      │
                                   │ • Memory        │
                                   └─────────────────┘
```

## Component Responsibilities

### ii_agent (`src/ii_agent/`)
- **Role:** LLM orchestration, session management, tool dispatch
- **Key files:**
  - `server/socket/socketio.py` — WebSocket message reception
  - `server/socket/command/query_handler.py` — Routes messages to agent creation
  - `server/services/agent_service.py:200` — `create_agent()` registers all tools
  - `controller/agent_controller.py` — Runs the agent loop (LLM → tool call → result → LLM)
  - `controller/tool_manager.py` — Manages tool registration and batch execution
  - `config/agent_types.py` — Defines which tools each agent type can use

### ii_tool (`src/ii_tool/`)
- **Role:** MCP-compliant tool server, provides shell/file/web/browser capabilities
- **Key files:**
  - `tools/base.py` — `BaseTool` abstract class (the interface ALL tools must implement)
  - `tools/manager.py` — `get_sandbox_tools()` and `get_common_tools()`
  - `mcp/server.py` — FastMCP server that exposes tools via MCP protocol
  - `utils.py` — `load_tools_from_mcp()` fetches tool definitions from MCP server

### ii_skills (`src/ii_skills/`)
- **Role:** Domain-specific business logic (financial models, analysis, newsletters)
- **Key files:**
  - `__init__.py` — `BaseSkill`, `register_skill`, `discover_skills()`, `get_skill()`
  - `bridge/` — ★ NEW: Wraps skills as BaseTool instances
  - `shared/` — Infrastructure services (TaskGraph, budgets, telemetry, storage)
  - `ib_toolkit/` — 67 IB modules
  - `ir_toolkit/` — 33 IR modules

## Data Dependencies

```
PostgreSQL (port 5432)
  └── ii_agent: sessions, agent runs, tasks, messages
  └── ii_skills/shared: portfolio holdings, outputs, memories

Redis (port 6379)
  └── ii_agent: session cache, task queues, pubsub
  └── ii_skills/shared: price cache, alert state

GCS (Google Cloud Storage)
  └── ii_skills/shared: uploaded Excel/PPTX outputs

External APIs
  └── Yahoo Finance: stock data (free, no key needed)
  └── NewsAPI: market news
  └── WHOOP: health metrics (OAuth)
  └── Anthropic/OpenAI/Google: LLM inference
```

## Key Interfaces

### BaseTool (the universal tool contract)
```python
# src/ii_tool/tools/base.py
class BaseTool(ABC):
    name: str
    description: str
    input_schema: dict[str, Any]
    read_only: bool
    display_name: str

    async def execute(self, tool_input: dict[str, Any]) -> ToolResult
```

### BaseSkill (the skill contract)
```python
# src/ii_skills/__init__.py
class BaseSkill:
    name: str
    version: str
    description: str

    def get_capabilities(self) -> List[str]
    def execute(self, action: str, **kwargs) -> Dict
```

### The Bridge (SkillTool wraps BaseSkill as BaseTool)
```python
# src/ii_skills/bridge/skill_tool.py
class SkillTool(BaseTool):
    def __init__(self, skill: BaseSkill): ...
    async def execute(self, tool_input: dict) -> ToolResult: ...
```
