# Add Parallel Search to the MCP Integration Hub

## Purpose

Let users copy a free, keyless web search and page fetching configuration from
II-Agent's MCP Integration Hub. The existing remote HTTP MCP transport runs the
configuration. Users select Parallel Search in the Hub, copy its JSON, and add it
to their custom MCP settings. Anonymous search uses Fast mode and is rate limited.

## Progress

- [x] (2026-10-10 17:58Z) Read repository and linked contributor guidance; use a branch from `develop`.
- [x] (2026-10-10 17:58Z) Add an opt-in entry to `frontend/src/constants/mcp.tsx`.
- [x] (2026-10-10 17:58Z) Verify the catalog configuration through the existing MCP loader.
- [x] (2026-10-10 17:58Z) Run frontend formatting, lint and TypeScript checks.
- [x] (2026-10-10 17:58Z) Build documentation with `npm run build` (static site generated).

## Repository context and implementation

`frontend/src/components/agent-setting/mcp-setting.tsx` displays `MCP_TOOLS`.
`mcp-tool.tsx` copies the selected entry's JSON configuration. The new entry uses
`mcpServers`, the HTTPS endpoint `https://search.parallel.ai/mcp`, and a project
User-Agent header. It has no credentials or local subprocess dependencies.
`src/ii_agent/server/mcp_settings/models.py` validates saved remote server
configurations. `src/ii_tool/utils.py` loads MCP tools, and `MCPTool.execute` calls
them and produces content for the application.

## Acceptance and validation

Install backend dependencies with `uv sync --frozen`, frontend dependencies with
`pnpm install --frozen-lockfile`, and documentation dependencies with `npm ci`
inside `docs`. Select the actual catalog entry, validate its JSON with
`MCPServersConfig`, and use `load_tools_from_mcp` followed by `MCPTool.execute`
to search and fetch a page without saved or environment credentials. Observe
the outgoing endpoint and User-Agent on discovery, search and fetch. Compare
all older catalog entries with the base to ensure they are unchanged. Run
the following commands from the indicated directory:

```bash
# frontend/
npx prettier --check src/constants/mcp.tsx
npx eslint src/constants/mcp.tsx
npx tsc --noEmit

# docs/
npm run build
```

Each command must exit successfully; the documentation build must generate
static files. No Python files change, so Ruff is not needed.

To repeat tool execution, copy the Parallel Search catalog JSON to
`/tmp/parallel-search.json`, then run from the repository root:

```bash
uv run python - <<'PY'
import asyncio
import json
import uuid
from pathlib import Path
from ii_tool.utils import load_tools_from_mcp

async def main():
    config = json.loads(Path("/tmp/parallel-search.json").read_text())
    tools = await load_tools_from_mcp(config)
    by_name = {tool.name: tool for tool in tools}
    session = uuid.uuid4().hex
    cases = {
        "web_search": {
            "objective": "Find the official Python asyncio documentation",
            "search_queries": ["Python asyncio documentation"],
            "session_id": session,
        },
        "web_fetch": {
            "urls": ["https://docs.python.org/3/library/asyncio.html"],
            "session_id": session,
        },
    }
    for name, arguments in cases.items():
        result = await by_name[name].execute(arguments)
        assert result.is_error is not True
        assert "asyncio" in str(result.llm_content).lower()
        print(name, result.user_display_content)

asyncio.run(main())
PY
```

Both tools must return content about asyncio. Use an empty credential
configuration and inspect outgoing HTTP requests to check that the catalog
User-Agent survives discovery and execution and that no Authorization header
is sent. Preserve required network proxy settings when isolating environment
variables. A network or rate-limit failure is a validation failure, not a pass.

## Surprises and discoveries

- The contributor guide on `main` requires `develop`, which has the earlier
  module layout. The existing catalog and loader on that branch support remote
  HTTP MCP configuration.
- The Hub exposes copyable configuration; it does not automatically enable a
  server. This change preserves that workflow.

## Decision log

Decisions below were recorded on 2026-10-10 by the Parallel contributor.

- Add one catalog item instead of changing default web search routing. Existing
  entries and saved configurations remain unchanged.
- Use the supported native HTTP transport and an identifying project header.
- Validate tool loading and execution without claiming an agent-loop test.

## Outcomes and retrospective

The actual catalog entry validates as a remote MCP configuration. Both tools
loaded through `load_tools_from_mcp` and returned useful search and fetch content
through `MCPTool.execute`, with no Authorization header. Observed requests used
the project User-Agent. All six existing catalog entries are unchanged. Frontend
formatting, lint, TypeScript checks and the documentation build pass. The full Python suite stops during
collection on existing imports of the absent `ii_agent.tools` package on this
base. The isolated MCP loader check passes without starting the full app.

Remove the entry to undo the change; it does not alter saved settings or provider
selection. No full agent-loop validation is claimed.
