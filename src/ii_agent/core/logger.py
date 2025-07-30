import logging
import os

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

logger = logging.getLogger("ii_agent")

logging.basicConfig(
    level=LOG_LEVEL,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

if LOG_LEVEL in ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]:
    logger.setLevel(LOG_LEVEL)

# Suppress verbose MCP server logs
logging.getLogger("mcp.server.lowlevel.server").setLevel(logging.WARNING)
logging.getLogger("mcp.server").setLevel(logging.WARNING)
logging.getLogger("mcp").setLevel(logging.WARNING)
logging.getLogger("fastmcp").setLevel(logging.WARNING)

# Suppress MoA-related logs
logging.getLogger("ii_agent.llm.moa_processor").setLevel(logging.WARNING)
logging.getLogger("ii_agent.llm.moa_async").setLevel(logging.WARNING)
logging.getLogger("ii_agent.agents.moa_agent").setLevel(logging.WARNING)

# Suppress google_genai logs
logging.getLogger("google_genai.models").setLevel(logging.WARNING)
logging.getLogger("google_genai.types").setLevel(logging.WARNING)

# Suppress OpenAI tool call logs
logging.getLogger("ii_agent.llm.openai").setLevel(logging.WARNING)
