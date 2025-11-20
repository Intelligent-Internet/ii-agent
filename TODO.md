# Migration Plan

## Phase 3: User Experience & State Management
- [x] **Session Management API**: Implement REST endpoints (`GET`, `PATCH`, `DELETE`) for Sessions in `core/src/routes/sessions.ts`.
- [x] **Chat History API**: Implement `GET /sessions/:id/events` to allow the frontend to load previous conversation history.
- [x] **User Settings**: Implement `core/src/routes/settings.ts` to allow users to save and retrieve their LLM API keys and Model preferences.

## Phase 4: Advanced Agent Capabilities
- [x] **Code Execution Tool**: Implement a `code_interpreter` tool using `quickjs-emscripten`.
- [x] **MCP (Model Context Protocol) Client**: Implement an MCP Client in `core/src/mcp/` to allow the Agent to connect to external tools.
- [x] **Web Browser Tool**: Port the web browsing capabilities using `playwright`.

## Phase 5: Integrations & Polish
- [x] **Connectors Framework**: Create a basic structure for external connectors (Google Drive, etc.).
- [x] **Billing/Stripe**: Port the Stripe integration (mock/stub implemented).
- [x] **Final Verification**: Full end-to-end testing of the Agent loop with all tools and frontend integration (implemented in `core/tests/agent_e2e.test.ts`).
