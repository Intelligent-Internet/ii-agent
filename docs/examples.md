# II-Agent – Examples Cookbook

This page walks you through **four end-to-end examples** that showcase common workflows:

1. CLI – generate a summary of a local text file  
2. Browser automation – open a page and click a button  
3. Research workflow – search the web and summarise findings  
4. Extending II-Agent – create and invoke a custom tool  

All commands assume you are in the project root, have your virtual-env activated, and `.env` configured with at least `ANTHROPIC_API_KEY`, `TAVILY_API_KEY`, and `STATIC_FILE_BASE_URL`.

---

## 1. Simple CLI Use-Case: Summarise a Text File

### 1.1 Prepare demo file

```bash
echo "Large language models are transforming the way developers build software..." > demo.txt
```

### 1.2 Launch CLI

```bash
python cli.py --workspace ./workspace --needs-permission false
```

> When the prompt `You:` appears, paste:

```
Please read file demo.txt and give me a 3-sentence summary.
```

### 1.3 Expected flow

1. Agent sees the request, realises it needs file content.  
2. It calls the **TextInspectorTool** automatically to read `demo.txt`.  
3. LLM returns a concise 3-sentence summary.  

You’ll see streamed events similar to:

```
[tool_call] TextInspectorTool(read_file=demo.txt)
[tool_result] (content of demo.txt)
[assistant] • Large-language models ...  
```

Stop the session with `Ctrl-C`.

---

## 2. Browser Automation: Click a Button

### 2.1 Start WebSocket backend

```bash
python ws_server.py --port 8000 --needs-permission false
```

### 2.2 Run the browser-use tool from CLI (or UI)

Open a second terminal:

```bash
python cli.py --needs-permission false
```

Enter:

```
Go to https://example.com, find the “More information” link and click it. Tell me the resulting URL.
```

### 2.3 Behind the scenes

* Agent plans a **visit_webpage** → retrieves HTML.  
* Uses **BrowserClickElementTool** with CV-aided selector.  
* Captures the new URL and replies.

Sample log tail:

```
[tool_call] VisitWebpageTool(url=https://example.com)
[tool_result] page_title="Example Domain", html_saved=.../example.html
[tool_call] BrowserClickElementTool(selector="text=More information")
[tool_result] navigated_to=https://www.iana.org/domains/example
[assistant] The link redirected to https://www.iana.org/domains/example
```

A screenshot is saved in your workspace and served under `STATIC_FILE_BASE_URL`.

---

## 3. Research Workflow: Search ➜ Crawl ➜ Summarise

### 3.1 Prompt

```
Research the current market share of electric vehicles in Europe. Provide a sourced paragraph (with citations).
```

### 3.2 Tool chain

| Step | Tool | Purpose |
|------|------|---------|
| 1 | **WebSearchTool** (Tavily / SerpAPI) | Retrieve top-ranked articles |
| 2 | **VisitWebpageTool** | Extract readable content |
| 3 | **LLMSummarisingContextManager** | Compress long passages |
| 4 | **Agent** | Synthesise answer with citations |

### 3.3 Result excerpt

```
According to the European Automobile Manufacturers Association (ACEA), battery-electric vehicles accounted for 14.6 % of all new cars registered in the EU in 2023, up from 12.2 % in 2022 [1]. BloombergNEF’s 2024 outlook projects the share to exceed 20 % by 2025 [2].

[1] https://www.acea.auto/press-release/
[2] https://about.bnef.com/electric-vehicle-outlook/
```

All visited pages and scraped markdown are stored in the workspace for auditability.

---

## 4. Integrating a Custom Tool

Let’s build **HelloTool** that simply echoes a greeting.

### 4.1 Create the tool

`src/ii_agent/tools/hello_tool.py`

```python
from ii_agent.tools.base import LLMTool, ToolImplOutput

class HelloTool(LLMTool):
    name = "hello_tool"
    description = "Say hello to a given person"
    input_schema = {
        "type": "object",
        "properties": {
            "person": {"type": "string", "description": "The name of the person to greet."}
        },
        "required": ["person"],
    }

    def run_impl(self, tool_input, message_history=None) -> ToolImplOutput:
        person = tool_input.get("person", "world")
        return ToolImplOutput(tool_output=f"Hello, {person}!", tool_result_message=f"Greeted {person}")
```

### 4.2 Register it

Edit `src/ii_agent/tools/__init__.py`

```python
from .hello_tool import HelloTool  # ← add
DEFAULT_TOOLS.append(HelloTool)
```

### 4.3 Run

```bash
pytest tests                # ensure everything still passes
python cli.py --needs-permission false
```

Prompt:

```
Use hello_tool to greet Alice.
```

The agent recognises the tool schema and responds:

```
[tool_call] HelloTool(person="Alice")
[tool_result] Hello, Alice!
[assistant] Hello, Alice!
```

Your custom tool is now part of the agent’s repertoire.

---

## Next Steps

* Browse the full **Tool Reference** (`docs/technical_overview.md#tools-layer`).  
* Try the **presentation_tool** to auto-create slides.  
* Combine browser + bash tools for complex automation.  

Enjoy exploring II-Agent!  
