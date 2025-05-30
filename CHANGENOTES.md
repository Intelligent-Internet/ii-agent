# Change Notes: LMStudio and Local Model Support

This document outlines the changes made to the `ii-agent` codebase to enable support for local large language models (LLMs) served via LMStudio, which exposes an OpenAI-compatible API endpoint. These changes allow users to leverage models like DeepSeek alongside the existing Anthropic API functionality.

## Key Feature: Local LLM Support via LMStudio

The primary goal of these modifications is to allow users to specify an "openai-direct" client that can connect to an LMStudio instance (or any other OpenAI-compatible API endpoint). This enables the use of locally hosted models, offering greater flexibility and control over LLM usage.

## Detailed Code Modifications:

### 1. Command-Line Interface (CLI) and Server Enhancements

*   **New Command-Line Arguments (`utils.py`, `cli.py`, `ws_server.py`):**
    *   Added `--llm-client`: Allows users to choose between "anthropic-direct" (default) and "openai-direct".
    *   Added `--model-name`: Allows users to specify the model name to be used (e.g., "deepseek-coder", "claude-3-opus-20240229").
*   **Dynamic Client Initialization (`cli.py`, `ws_server.py`):**
    *   The `get_client` function in `src/ii_agent/llm/__init__.py` is now used to dynamically instantiate either `AnthropicDirectClient` or `OpenAIDirectClient` based on the `--llm-client` argument.
*   **Conditional Argument Passing (`cli.py`, `ws_server.py`):**
    *   Modified `cli.py` and `ws_server.py` to conditionally pass client-specific keyword arguments to `get_client`. For example, Anthropic-specific parameters (`use_caching`, `project_id`, `region`, `thinking_tokens`) are only passed if `--llm-client` is "anthropic-direct". This prevents `TypeError`s when using `OpenAIDirectClient`.

### 2. `OpenAIDirectClient` Refinements (`src/ii_agent/llm/openai.py`)

The `OpenAIDirectClient` was enhanced to ensure compatibility and robustness when interacting with OpenAI-compatible APIs, particularly LMStudio serving models like DeepSeek.

*   **Environment Variables for Configuration:**
    *   `OPENAI_BASE_URL`: Users must set this environment variable to point to their LMStudio server (e.g., `http://<your-lmstudio-host-ip>:1234/v1`).
    *   `OPENAI_API_KEY`: While the OpenAI library requires this, it can be set to a dummy value (e.g., "lmstudio") if the LMStudio server does not require authentication.
*   **System Prompt Handling:**
    *   Modified the `generate()` method: If `cot_model` is `True` (which is the default and suitable for models like DeepSeek Coder) and a `system_prompt` is provided, the system prompt is prepended to the content of the first user message. This ensures system instructions are passed correctly to models that expect them within the user message stream when Chain-of-Thought prompting is active.
*   **Tool Call Robustness:**
    *   Enhanced `generate()` to gracefully handle responses from models that might return multiple tool calls or tool calls with invalid/placeholder names (as observed with DeepSeek via LMStudio).
    *   The client now iterates through the `tool_calls` in the model's response.
    *   It identifies available tool names from the `tools` parameter passed to the client.
    *   It selects and processes only the *first* valid tool call whose name matches an available tool and has correctly parsable arguments.
    *   Warnings are logged for skipped or malformed tool calls, improving debuggability.
*   **Tool Argument Serialization for History:**
    *   Modified `generate()` to ensure that when constructing the message history to be sent *to* the OpenAI-compatible API, the `arguments` for a previous tool call (which are stored as a Python dictionary in `internal_message.tool_input`) are serialized to a JSON string using `json.dumps()`. This resolves `openai.BadRequestError` related to incorrect content types for the `arguments` field.
*   **Logging Initialization:**
    *   Added `import logging` and `logger = logging.getLogger(__name__)` at the beginning of the file to resolve `NameError` for the logger.

### 3. `LLMClient` Interface (`src/ii_agent/llm/__init__.py`)

*   The `get_client` function was updated to accept `llm_client_name` and `model_name` as arguments to facilitate the dynamic selection and configuration of the appropriate LLM client.

## Impact on Existing Anthropic Functionality

These changes are designed to be additive. The existing Anthropic functionality remains the default and is unaffected:
*   If the `--llm-client` argument is not provided, or is explicitly set to "anthropic-direct", the system behaves as before, using `AnthropicDirectClient`.
*   Anthropic-specific configurations and parameters are handled correctly.
*   The `AnthropicDirectClient` continues to expect tool input arguments as dictionaries, which is consistent with its API.

## How to Use LMStudio Support

1.  **Start LMStudio:**
    *   Download and run LMStudio.
    *   Load your desired model (e.g., a DeepSeek Coder variant).
    *   Start the server in LMStudio. **Crucially, ensure you select "Serve on Local Network" in the LMStudio server settings if running `ii-agent` in a different environment (like WSL) than where LMStudio is hosted (e.g., Windows).** Note the IP address and port provided by LMStudio.
2.  **Set Environment Variables:**
    *   `OPENAI_BASE_URL`: Set this to the address of your LMStudio server (e.g., `export OPENAI_BASE_URL="http://100.110.67.102:1234/v1"`). Replace the IP and port with your LMStudio server details.
    *   `OPENAI_API_KEY`: Set this to any non-empty string (e.g., `export OPENAI_API_KEY="lmstudio"`). LMStudio typically does not require an API key by default.
3.  **Run `ii-agent`:**
    *   Use the `--llm-client openai-direct` argument.
    *   Specify the model using `--model-name <your-model-identifier-in-lmstudio>` (e.g., `--model-name deepseek-ai/deepseek-coder-6.7b-instruct`). The exact model name might depend on how LMStudio identifies it; often, it's the path/name shown in the LMStudio UI.

    **Example `cli.py` command:**
    ```bash
    OPENAI_BASE_URL="http://<your-lmstudio-ip>:<port>/v1" OPENAI_API_KEY="lmstudio" python cli.py --llm-client openai-direct --model-name <your-model-identifier> --prompt "Write a python script to sort a list of numbers."
    ```

    **Example `ws_server.py` command:**
    ```bash
    OPENAI_BASE_URL="http://<your-lmstudio-ip>:<port>/v1" OPENAI_API_KEY="lmstudio" python ws_server.py --llm-client openai-direct --model-name <your-model-identifier>
    ```

This feature significantly expands the agent's capabilities by allowing integration with a wider range of models, including those run locally. 