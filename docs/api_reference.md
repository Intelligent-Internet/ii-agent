# II-Agent API Reference  

_Commit: a6da824638202089d0f43819d62d8e67506d2240 • Updated 31 May 2025_

This reference documents the **public Python interfaces** you are expected to use or extend when integrating with II-Agent.  
All import paths are relative to `ii_agent`, e.g.

```python
from ii_agent.tools.base import LLMTool
```

---

## 1  Tooling Framework

### 1.1 `ToolImplOutput`

File `src/ii_agent/tools/base.py`

```python
@dataclass
class ToolImplOutput:
    tool_output: str | list[dict[str, Any]]
    tool_result_message: str
    auxiliary_data: dict[str, Any] = field(default_factory=dict)
```

* **tool_output** – value injected back into the LLM prompt (string or list of JSON objects).  
* **tool_result_message** – concise log message, forwarded to UI.  
* **auxiliary_data** – optional metadata (not shown to the model).

---

### 1.2 `LLMTool`

File `src/ii_agent/tools/base.py`

```python
class LLMTool(ABC):
    # metadata
    name: str
    description: str
    input_schema: dict[str, Any]          # JSON-Schema (Draft-07 subset)

    # public
    def run(
        self,
        tool_input: dict[str, Any],
        message_history: MessageHistory | None = None,
    ) -> str | list[dict[str, Any]]: ...

    # override
    @abstractmethod
    def run_impl(
        self,
        tool_input: dict[str, Any],
        message_history: MessageHistory | None = None,
    ) -> ToolImplOutput: ...
```

`run()` is **@final** – it validates `tool_input` with `jsonschema`, calls `run_impl()`, catches errors and always returns a value suitable for LLM injection.

#### Minimal Example

```python
# hello_tool.py
from ii_agent.tools.base import LLMTool, ToolImplOutput

class HelloTool(LLMTool):
    name = "hello_tool"
    description = "Return a friendly greeting"
    input_schema = {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Person to greet"}
        },
        "required": ["name"],
    }

    def run_impl(self, tool_input, *_):
        greeting = f"Hello, {tool_input['name']}!"
        return ToolImplOutput(tool_output=greeting,
                              tool_result_message="Greeted user")
```

Register it (see _AgentToolManager_ below) and the LLM can invoke:

```json
{"name": "hello_tool", "arguments": {"name": "Ada"}}
```

---

### 1.3 `AgentToolManager`

File `src/ii_agent/tools/tool_manager.py`

```python
class AgentToolManager:
    def __init__(self,
        tools: list[LLMTool],
        logger_for_agent_logs: logging.Logger,
        interactive_mode: bool = True,
    )
    def reset(self) -> None             # clear internal state
    def get_tools(self) -> list[LLMTool]
    def run_tool(
        self,
        tool_call: ToolCallParameters,
        history: MessageHistory
    ) -> str | list[dict[str, Any]]

    def should_stop(self) -> bool       # True when tool chain decided to finish
    def get_final_answer(self) -> str   # Return cached answer
```

`run_tool()` enforces permission prompts (via WebSocket/CLI) if `interactive_mode` is **True** and the tool is risky (e.g. `bash_tool`).

---

## 2  Agent Layer

### 2.1 `AnthropicFC`

File `src/ii_agent/agents/anthropic_fc.py`

Asynchronous orchestration around Anthropic function-calling:

```python
class AnthropicFC(BaseAgent):
    def __init__(self,
        system_prompt: str,
        client: LLMClient,
        tools: list[LLMTool],
        workspace_manager: WorkspaceManager,
        message_queue: asyncio.Queue[RealtimeEvent],
        logger_for_agent_logs: logging.Logger,
        context_manager: ContextManager,
        max_output_tokens_per_turn: int = 8_192,
        max_turns: int = 10,
        websocket: WebSocket | None = None,
        session_id: uuid.UUID | None = None,
        interactive_mode: bool = True,
    )

    def start_message_processing(self) -> asyncio.Task
    def run_agent(
        self,
        instruction: str,
        files: list[str] | None = None,
        resume: bool = False,
        orientation_instruction: str | None = None,
    ) -> str      # synchronous, but normally executed in ThreadPool
    def cancel(self) -> None        # graceful interrupt
```

**Key behaviours**

* Maintains `MessageHistory`; applies `context_manager.truncate()` each turn.  
* Streams every stage to `message_queue` as `RealtimeEvent`s (see below).  
* Handles single _tool_call_ per LLM turn; loops until `should_stop()` or `max_turns`.  
* Supports _resume_: continue from previous interrupted state.

---

## 3  Communication Primitives

### 3.1 `EventType` (enum)

File `src/ii_agent/core/event.py`

* `USER_MESSAGE`  
* `AGENT_RESPONSE` / `AGENT_RESPONSE_INTERRUPTED`  
* `TOOL_CALL`  
* `TOOL_RESULT`  
* `PROCESSING`, `SYSTEM`, `ERROR`, etc.

### 3.2 `RealtimeEvent`

```python
class RealtimeEvent(BaseModel):
    type: EventType
    content: dict[str, Any]
    timestamp: datetime = Field(default_factory=datetime.utcnow)
```

* **JSON-serialisable**; `.model_dump()` used by WS server.  
* Persisted to DB (`event` table) for replay.

---

## 4  Conversation State

### 4.1 `MessageHistory`

File `src/ii_agent/llm/message_history.py`

```python
class MessageHistory:
    def __init__(self, context_manager: ContextManager)

    # add
    def add_user_prompt(text: str, image_blocks: list[dict] | None = None) -> None
    def add_assistant_turn(results: list[TextResult]) -> None
    def add_tool_call_result(call: ToolCallParameters, result: str) -> None

    # query
    def get_messages_for_llm() -> list[dict]
    def get_pending_tool_calls() -> list[ToolCallParameters]
    def get_last_assistant_text_response() -> str

    # maintenance
    def truncate() -> None              # delegate to context_manager
    def clear() -> None
    def clear_from_last_to_user_message() -> None
    def count_tokens() -> int
```

### 4.2 Context Managers

| Class | Strategy | Module |
|-------|----------|--------|
| `LLMSummarizingContextManager` | Call LLM to summarise oldest turns | `llm/context_manager/llm_summarizing.py` |
| `AmortizedForgettingContextManager` | Probabilistic dropping as budget nears | `llm/context_manager/amortized_forgetting.py` |
| `PipelineContextManager` | Chain multiple managers | `llm/context_manager/pipeline.py` |

---

## 5  LLM Client Abstraction

```python
class LLMClient(Protocol):
    def generate(
        self,
        messages: list[dict],
        max_tokens: int,
        tools: list[ToolParam] | None,
        system_prompt: str,
    ) -> tuple[list[ModelResult], int]   # returns chunks + token count
```

Concrete implementation: `ii_agent.llm.anthropic.AnthropicClient`.

---

## 6  Putting It Together – Quick Code Sample

```python
import asyncio, uuid, logging
from ii_agent.tools.tool_manager import AgentToolManager
from ii_agent.tools.base import LLMTool, ToolImplOutput
from ii_agent.agents.anthropic_fc import AnthropicFC
from ii_agent.llm.anthropic import AnthropicClient
from ii_agent.llm.context_manager.llm_summarizing import LLMSummarizingContextManager
from ii_agent.utils.workspace_manager import WorkspaceManager
from ii_agent.core.event import RealtimeEvent, EventType

# 1. custom tool
class HelloTool(LLMTool):
    name, description = "hello_tool", "Say hello"
    input_schema = {"type":"object","properties":{"name":{"type":"string"}},"required":["name"]}
    def run_impl(self, params, *_):
        return ToolImplOutput(f"Hello {params['name']}!", "Greeted user")

# 2. infrastructure
workspace = WorkspaceManager(root="./workspace_demo")
queue = asyncio.Queue()

client = AnthropicClient(api_key="sk-...", model="claude-3-7-sonnet")
context_mgr = LLMSummarizingContextManager(client=client, token_budget=120_000)
tools = [HelloTool()]
agent = AnthropicFC(
    system_prompt="You are II-Agent.",
    client=client,
    tools=tools,
    workspace_manager=workspace,
    message_queue=queue,
    logger_for_agent_logs=logging.getLogger("agent"),
    context_manager=context_mgr,
    session_id=uuid.uuid4(),
)

# 3. fire and forget
async def main():
    agent.start_message_processing()          # background task
    print(agent.run_agent("Use hello_tool to greet Ada.", resume=False))

asyncio.run(main())
```

---

_End of API Reference_
