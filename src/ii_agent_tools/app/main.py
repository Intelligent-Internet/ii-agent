import argparse
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI

from ii_agent_tools.app.exceptions import (
    ServiceError,
    generic_error_handler,
    service_error_handler,
    validation_error_handler,
)
from ii_agent_tools.app.middleware import configure_cors, log_requests_middleware
from ii_agent_tools.app.routers import (
    audio,
    database,
    health,
    image,
    voice,
    video,
    web_search,
    web_visit,
)
from ii_agent_tools.logger import configure_logging, get_logger

configure_logging()

# Create a logger using the shared logger utility
logger = get_logger("ii_agent_tools.app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for FastAPI application.
    Handles startup and shutdown events.
    """
    # Startup
    await validate_configuration()
    yield
    # Shutdown (if needed in the future)


app = FastAPI(lifespan=lifespan)

# Register exception handlers
app.add_exception_handler(ServiceError, service_error_handler)
app.add_exception_handler(ValueError, validation_error_handler)
app.add_exception_handler(Exception, generic_error_handler)

# Configure CORS middleware
configure_cors(app)

# Add request logging middleware
app.middleware("http")(log_requests_middleware)

# Include routers with API versioning
# Health endpoint at root for easy access by load balancers
app.include_router(health.router)

# All other endpoints under /v1 for versioning
app.include_router(audio.router, prefix="/v1")
app.include_router(image.router, prefix="/v1")
app.include_router(voice.router, prefix="/v1")
app.include_router(video.router, prefix="/v1")
app.include_router(web_search.router, prefix="/v1")
app.include_router(web_visit.router, prefix="/v1")
app.include_router(database.router, prefix="/v1")


async def validate_configuration():
    """
    Validate critical configuration settings on application startup.

    This ensures that misconfigurations are caught early rather than
    at runtime when handling user requests.
    """
    from ii_agent_tools.app.app_config import get_settings

    settings = get_settings()

    logger.info(
        "Validating application configuration",
        extra={"environment": settings.environment},
    )

    # Validate web search configuration (checks which API keys are available)
    web_search_config = settings.web_search_config
    if not any(
        [
            web_search_config.serpapi_api_key,
            web_search_config.jina_api_key,
            web_search_config.tavily_api_key,
        ]
    ):
        logger.warning("No web search API keys configured. Web search may not work.")

    # Validate web visit configuration (checks which API keys are available)
    web_visit_config = settings.web_visit_config
    if not any(
        [
            web_visit_config.firecrawl_api_key,
            web_visit_config.gemini_api_key,
            web_visit_config.jina_api_key,
            web_visit_config.tavily_api_key,
            web_visit_config.outcrawl_api_key,
        ]
    ):
        logger.warning("No web visit API keys configured. Web visit will use BeautifulSoup only.")

    # Validate storage configuration
    storage_config = settings.storage_config
    if storage_config.storage_provider == "gcs" and not storage_config.gcs_bucket_name:
        logger.warning(
            "Storage provider is 'gcs' but GCS_BUCKET_NAME is not set. "
            "Storage functionality may fail!"
        )

    # Validate LLM configuration
    if settings.llm_config and settings.llm_config.openai_api_key:
        logger.info("LLM client configured with OpenAI")
    else:
        logger.warning("LLM client not configured. Some features may be unavailable.")

    # Log environment and security settings
    logger.info(
        "Configuration validation complete",
        extra={
            "environment": settings.environment,
            "cors_origins": settings.cors_allowed_origins,
            "log_level": logger.level,
        },
    )

    # Warn if running in production with development-like settings
    if settings.environment == "production":
        if "localhost" in settings.cors_allowed_origins:
            logger.warning(
                "Production environment with localhost in CORS origins. "
                "This may be a misconfiguration!"
            )

    logger.info("Application startup complete")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the tool server")
    parser.add_argument("--port", type=int, default=7000, help="Port to run the server on")
    parser.add_argument("--workers", type=int, default=1, help="Number of worker processes")
    args = parser.parse_args()

    uvicorn.run(
        "ii_agent_tools.app.main:app",
        host="0.0.0.0",
        port=args.port,
        workers=args.workers,
    )
