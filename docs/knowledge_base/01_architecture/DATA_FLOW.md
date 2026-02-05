# Data Flow: User Message → Output File

## Complete Request Lifecycle

### Step 1: User Input (Frontend)
```
User types: "Build a quick LBO analysis for a company with $50M EBITDA"
Frontend sends via Socket.IO → ws-server port 8000
```

### Step 2: Message Reception
```
File: src/ii_agent/server/socket/socketio.py:117
Method: chat_message(sid, data)
  → data = {"type": "user_query", "content": {"message": "Build a quick LBO..."}}
  → Dispatches to CommandHandlerFactory
```

### Step 3: Agent Creation
```
File: src/ii_agent/server/socket/command/query_handler.py:315
Method: _init_chat_session()
  → Calls agent_service.create_agent()

File: src/ii_agent/server/services/agent_service.py:200
Method: create_agent()
  → Creates LLM client (Anthropic/OpenAI/Google)
  → Creates AgentToolManager
  → Registers tools:
      1. MCP tools from sandbox (shell, file, web, browser, slides)
      2. Common tools (RegisterPort, MessageUser)
      3. Sub-agents (Task, Researcher, DesignDoc, Codex)
      4. ★ Skill tools via bridge (ib_toolkit, ir_toolkit, etc.)
  → Creates FunctionCallAgent with tool definitions
  → Returns AgentController
```

### Step 4: Agent Execution Loop
```
File: src/ii_agent/controller/agent_controller.py:196
Method: run_impl()
  → Sends message + tool definitions to LLM
  → LLM responds with tool_use block:
      {
        "name": "skill_ib_toolkit",
        "input": {
          "action": "quick_lbo_analysis",
          "params": {"ebitda": 50, "entry_multiple": 8.0, ...}
        }
      }
  → AgentToolManager.run_tools_batch() dispatches to SkillTool
```

### Step 5: Skill Execution
```
File: src/ii_skills/bridge/skill_tool.py
Method: SkillTool.execute(tool_input)
  → Extracts action="quick_lbo_analysis" and params
  → Calls IBToolkitSkill.execute("quick_lbo_analysis", ebitda=50, ...)

File: src/ii_skills/ib_toolkit/__init__.py:106
Method: execute("quick_lbo_analysis", ...)
  → Calls _quick_lbo_analysis()
  → Imports lbo_calculator.py
  → Runs quick_lbo() → returns {moic, irr, value_creation}
  → Returns result dict to SkillTool
```

### Step 6: Result Return
```
SkillTool.execute() → ToolResult(llm_content=JSON, user_display_content=dict)
  → AgentController feeds result back to LLM
  → LLM may:
      a) Present results to user (via MessageUser or text response)
      b) Make another tool call (e.g., generate Excel model)
      c) Chain multiple skill calls (fetch data → analyze → generate slides)
```

### Step 7: File Output (for generation actions)
```
If the LLM calls: skill_ib_toolkit(action="create_lbo_model", params={...})
  → IBToolkitSkill generates Excel file
  → Saves to: src/ii_skills/ib_toolkit/output/LBO_Model_Company_20260205.xlsx
  → Returns {"output_path": "/path/to/file.xlsx"}
  → LLM can then use file tools to copy to workspace
  → User downloads from desktop app workspace (~/.ii_agent/workspace)
```

## Multi-Step Deal Analysis Flow

```
User: "Run a full LBO analysis for Acme Corp"

LLM Plan (autonomous multi-step):
  1. skill_ib_toolkit(action="fetch_company_data", params={ticker: "ACME"})
     → Gets financial data
  2. skill_ib_toolkit(action="quick_lbo_analysis", params={ebitda: X, ...})
     → Gets IRR/MOIC
  3. skill_ib_toolkit(action="lbo_sensitivity", params={ebitda: X, ...})
     → Gets sensitivity matrix
  4. skill_ib_toolkit(action="create_lbo_model", params={company_name: "Acme"})
     → Generates Excel
  5. skill_ib_toolkit(action="generate_lbo_slides", params={company_name: "Acme"})
     → Generates PowerPoint
  6. MessageUser(message="Analysis complete. Files saved to workspace.")
```

## Output Path Strategy

| Output Type | Default Location | Final Destination |
|-------------|-----------------|-------------------|
| Excel models | `src/ii_skills/ib_toolkit/output/` | `~/.ii_agent/workspace/` (via file copy) |
| PowerPoint decks | `src/ii_skills/ib_toolkit/output/` | `~/.ii_agent/workspace/` |
| IR deliverables | `src/ii_skills/ir_toolkit/output/` | `~/.ii_agent/workspace/` |
| Newsletter HTML | Generated in memory | Sent via email |
| Telemetry logs | `logs/telemetry/YYYY-MM-DD/` | Stays local |
