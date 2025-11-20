# Migration Plan

## Phase 3: User Experience & State Management
1.  **Session Management API**: Implement REST endpoints (`GET`, `PATCH`, `DELETE`) for Sessions in `core/src/routes/sessions.ts` to allow users to list, rename, and delete their chat sessions.
2.  **Chat History API**: Implement `GET /sessions/:id/messages` to allow the frontend to load previous conversation history when opening a session.
3.  **User Settings**: Implement `core/src/routes/settings.ts` to allow users to save and retrieve their LLM API keys and Model preferences (persisting to the SQLite `llm_settings` store).

## Phase 4: Advanced Agent Capabilities
1.  **Code Execution Tool**: Implement a `code_interpreter` tool. For this migration, integrate with the existing E2B SDK (already in Python dependencies, exists for Node) or provide a Docker-based execution tool to replace `ii_sandbox_server` logic.
2.  **MCP (Model Context Protocol) Client**: Implement an MCP Client in `core/src/mcp/` to allow the Agent to connect to external tools/servers, replacing the Python `ii_tool` MCP logic.
3.  **Web Browser Tool**: Port the web browsing capabilities (using `puppeteer` or similar) to allow the agent to read websites, replacing the Python scraper.

## Phase 5: Integrations & Polish
1.  **Connectors Framework**: Create a basic structure for external connectors (Google Drive, etc.) to replace `connectors_router`.
2.  **Billing/Stripe**: Port the Stripe integration (if required for the self-hosted/local version, otherwise implement a mock/stub).
3.  **Final Verification**: Full end-to-end testing of the Agent loop with all tools and frontend integration.
