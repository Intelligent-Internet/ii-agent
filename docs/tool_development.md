# Tool Development Guide

_Last updated: 31 May 2025 – commit `a6da824`_

II-Agent’s power comes from **tools** – little python classes the LLM can call to interact with the real world.  
This guide shows how to create, register, test, and ship your own tools using the **actual API** implemented in `ii_agent.tools.base`.

---

## 1   Anatomy of an LLM Tool

```text
YourTool (subclass of LLMTool)
 ├── name             # unique identifier used in function-call
 ├── description      # one-line human description
 ├── input_schema     # JSON-Schema (dict) describing arguments
 └── run_impl(...)    # do the work and return ToolImplOutput
```

### 1.1  Base Classes

| Object | Location | Purpose |
|--------|----------|---------|
| `LLMTool` | `ii_agent/tools/base.py` | Abstract base every tool extends |
| `ToolImplOutput` | same file | Dataclass container returned by `run_impl` |

```python
from ii_agent.tools.base import LLMTool, ToolImplOutput

class YourTool(LLMTool):
    name = "your_tool"
    description = "Do something useful."
    input_schema = {
        "type": "object",
        "properties": {"foo": {"type": "string"}},
        "required": ["foo"],
    }

    def run_impl(self, tool_input, message_history=None):
        # ① your code
        result = f"processed {tool_input['foo']}"
        # ② wrap in ToolImplOutput
        return ToolImplOutput(
            tool_output=result,               # goes back into LLM prompt
            tool_result_message="Success!",   # shown in UI/logs
        )
```

*`run()` is implemented in the base class (don’t override) – it validates `tool_input` against `input_schema` and forwards to `run_impl`.*

---

## 2   Crafting `input_schema`

`input_schema` follows JSON-Schema draft-07 (subset accepted by Anthropic/OpenAI):
* `type`, `description`, `enum`, `minimum`, `maxLength`, etc.
* Keep it **minimal** – the LLM must write valid JSON unaided.

Example with validation rules:

```python
input_schema = {
    "type": "object",
    "properties": {
        "path": {"type": "string", "description": "Relative path to file"},
        "max_lines": {"type": "integer", "minimum": 1, "maximum": 1000},
    },
    "required": ["path"],
}
```

---

## 3   Registering the Tool

### 3.1  One-off registration

```python
from ii_agent.tools.tool_manager import AgentToolManager
from my_tools.hello_tool import HelloTool

tool_manager = AgentToolManager(
    tools=[HelloTool()],
    logger_for_agent_logs=logging.getLogger("agent"),
    interactive_mode=True,          # ask before risky calls
)
```

### 3.2  Always-on registration

Add import + append to `DEFAULT_TOOLS` in `src/ii_agent/tools/__init__.py`:

```python
from .hello_tool import HelloTool       # new line
DEFAULT_TOOLS.append(HelloTool)         # keep order alphabetical if possible
```

Now every CLI/WS instance will expose `hello_tool`.

---

## 4   Permissions & Safety

* **Interactive mode** (`--needs-permission true`, default) – before executing tools flagged as risky (e.g. `bash_tool`) the UI asks the user to approve.
* Mark a tool as risky by overriding:

```python
@property
def risky(self) -> bool:
    return True
```

The framework will pause and await approval via WebSocket or CLI prompt.

---

## 5   Returning Files

Large binaries shouldn’t be embedded in prompts.  
Write to the session workspace and return the relative path:

```python
def run_impl(self, tool_input, *_):
    dst = workspace.write("outputs/report.pdf", pdf_bytes)
    return ToolImplOutput(
        tool_output=f"Generated report at {dst}",
        tool_result_message="PDF saved",
        auxiliary_data={"path": dst},
    )
```

Files under the workspace are served over HTTP at  
`{STATIC_FILE_BASE_URL}/workspace/<session_uuid>/<dst>`.

---

## 6   Access to Context

`message_history` parameter (optional) gives read/write access to conversation so far:

```python
def run_impl(self, tool_input, message_history=None):
    last_user_msg = message_history.get_messages_for_llm()[-1]
    ...
```

> Mutating history is powerful – do so sparingly.

---

## 7   Unit-Testing Your Tool

```python
from my_tools.hello_tool import HelloTool
from ii_agent.tools.base import ToolImplOutput
from ii_agent.llm.message_history import MessageHistory
from ii_agent.llm.context_manager.amortized_forgetting import AmortizedForgettingContextManager
from ii_agent.llm.token_counter import TokenCounter

def test_hello():
    tool = HelloTool()
    ctx_mgr = AmortizedForgettingContextManager(TokenCounter(), logger=None)
    hist = MessageHistory(context_manager=ctx_mgr)
    out = tool.run({"name": "Ada"}, hist)
    assert isinstance(out, str) and "Ada" in out
```

Run with `pytest`.

---

## 8   Integration Smoke Test

```bash
python cli.py --needs-permission false
# when prompt appears
User input: Use hello_tool to greet Alan.
```

You should see streamed events:

```
[tool_call] hello_tool {"name":"Alan"}
[tool_result] Hello, Alan!
```

---

## 9   Tips & Best Practices

1. **Validate** – the base class already runs `jsonschema`, but you can add deeper checks inside `run_impl`.
2. **Idempotent** – repeated calls shouldn’t corrupt state.
3. **Token-aware** – truncate long outputs before returning; or save to file.
4. **Log** – use `logging.getLogger(__name__)`; logs stream to `agent_logs`.
5. **Document** – update `/docs` when your tool is public.

---

## 10   Checklist Before Opening a PR

- [ ] Added unit tests under `tests/tools/`.
- [ ] `pre-commit run --all-files` passes (`ruff`, `black`, `mypy` optional).
- [ ] Updated documentation if tool is generally useful.
- [ ] Squash commits and follow Conventional Commit message, e.g.  
  `feat(tool): add hello_tool for simple greetings`

Happy hacking – your tool makes II-Agent smarter for everyone!  
