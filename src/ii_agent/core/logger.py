import logging
import os

logging.basicConfig(level=logging.ERROR)
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

logger = logging.getLogger("ii_agent")

if LOG_LEVEL in ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]:
    logger.setLevel(LOG_LEVEL)
