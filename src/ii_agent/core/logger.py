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
