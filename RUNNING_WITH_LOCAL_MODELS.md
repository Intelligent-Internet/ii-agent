# How to Run II-Agent with a Local LLM using LMStudio

This guide explains how to configure and run `ii-agent` with a large language model (LLM) hosted locally using LMStudio. LMStudio provides an OpenAI-compatible API endpoint, allowing `ii-agent` to interact with a variety of local models.

## Prerequisites

*   **LMStudio:** You need to have LMStudio installed and running. Download it from [https://lmstudio.ai/](https://lmstudio.ai/).
*   **A local LLM:** Download a model compatible with LMStudio (e.g., a GGUF format model like DeepSeek Coder).

## Step 1: Configure and Start LMStudio Server

1.  **Open LMStudio.**
2.  **Download a Model:** If you haven't already, search for and download your desired model from the LMStudio interface (e.g., a DeepSeek Coder variant).
3.  **Load the Model:** Select the model you want to use from the "My Models" tab or the model selection dropdown.
4.  **Start the Local Server:**
    *   Navigate to the "Local Server" tab (usually looks like `<->`).
    *   Select your loaded model at the top.
    *   **Important:** Under "Server Settings" or a similar section, ensure you enable **"Serve on Local Network"** or an equivalent option (e.g., by selecting your network IP instead of `localhost` or `127.0.0.1` in the "Server Host" dropdown). This is crucial if you are running `ii-agent` in a different environment (like WSL on Windows) than where LMStudio is graphically running (Windows itself). LMStudio will display the IP address and port it's using (e.g., `http://192.168.1.100:1234`). Note this down.
    *   Click "Start Server".

## Step 2: Set Environment Variables for II-Agent

Before running `ii-agent`, you need to configure two environment variables:

*   `OPENAI_BASE_URL`: This tells `ii-agent` where to find your LMStudio API. Set it to the full URL provided by LMStudio in the previous step, including the `/v1` path for the OpenAI-compatible endpoint.
    *   Example: `export OPENAI_BASE_URL="http://100.110.67.102:1234/v1"`
*   `OPENAI_API_KEY`: The OpenAI client library used by `ii-agent` expects an API key. LMStudio typically doesn't require one by default. You can set this to any non-empty string.
    *   Example: `export OPENAI_API_KEY="lmstudio"`

You can set these in your shell session or add them to your shell's configuration file (e.g., `.bashrc`, `.zshrc`).

## Step 3: Run II-Agent

Now you can run `ii-agent` (either `cli.py` or `ws_server.py`) with specific command-line arguments to use your local model:

*   `--llm-client openai-direct`: This flag tells `ii-agent` to use the OpenAI-compatible client.
*   `--model-name <your-model-identifier>`: Specify the model identifier. For LMStudio, this is often the model file name or path as shown in the LMStudio server UI (e.g., `deepseek-ai/deepseek-coder-6.7b-instruct`). Consult your LMStudio server tab for the exact identifier it expects or serves.

### Example Commands:

**For `cli.py`:**

```bash
# Ensure environment variables are set first
# export OPENAI_BASE_URL="http://<your-lmstudio-ip>:<port>/v1"
# export OPENAI_API_KEY="lmstudio"

python cli.py \
    --llm-client openai-direct \
    --model-name <your-model-identifier-in-lmstudio> \
    --prompt "Write a Python function to calculate the factorial of a number."
```

**For `ws_server.py` (to use with the web interface):**

```bash
# Ensure environment variables are set first
# export OPENAI_BASE_URL="http://<your-lmstudio-ip>:<port>/v1"
# export OPENAI_API_KEY="lmstudio"

python ws_server.py \
    --llm-client openai-direct \
    --model-name <your-model-identifier-in-lmstudio>
```

Replace `<your-lmstudio-ip>:<port>` and `<your-model-identifier-in-lmstudio>` with the actual values from your LMStudio setup.

## Troubleshooting

*   **Connection Errors:**
    *   Double-check the `OPENAI_BASE_URL`. Ensure it matches the IP and port LMStudio is serving on, including the `/v1` suffix.
    *   Verify that LMStudio is serving on your local network IP, not just `localhost`, if `ii-agent` is running in a container or WSL.
    *   Check your firewall settings to ensure connections to the LMStudio port are allowed.
*   **Model Not Found / Incorrect Model:**
    *   Ensure the `--model-name` matches the identifier LMStudio expects. This is often displayed in the LMStudio server log or UI when you select a model to serve.
*   **LMStudio Logs:** Check the LMStudio server logs for any error messages or information about incoming requests.

By following these steps, you can leverage the power of local LLMs with `ii-agent` for development, testing, or offline use. 