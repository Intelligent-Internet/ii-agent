import json
import uvicorn
import argparse
import os
from pathlib import Path
from fastapi import FastAPI, HTTPException, Header, Depends
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import Field, BaseModel
from typing import Literal, List, Dict, Any
from sqlalchemy.orm.exc import StaleDataError

from ii_tool.integrations.web_visit.base import WebVisitError
from ii_tool.integrations.video_generation.base import VideoGenerationError
from ii_tool.integrations.logger import get_logger

from .config import config
from .services import image_search_service, web_visit_service, video_generation_service
from ii_tool.integrations.storage import LocalStorage
from .db import User, get_user_by_api_key, apply_tool_usage
from .utils import convert_dollars_to_credits
from ii_tool.integrations.image_generation import create_image_generation_client
from ii_tool.integrations.web_search import create_web_search_client
from ii_tool.integrations.web_search.exception import (
    WebSearchExhaustedError,
    WebSearchProviderError,
    WebSearchNetworkError,
)
from ii_tool.integrations.web_visit import create_web_visit_client
from ii_tool.integrations.database import create_database_client


app = FastAPI()

# Create a logger using the shared logger utility
logger = get_logger("ii_tool.app")
# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Get storage instance for serving files
_storage_instance = None

def get_storage_instance():
    """Get the storage instance (lazy loaded)."""
    global _storage_instance
    if _storage_instance is None:
        from .services import storage
        _storage_instance = storage
    return _storage_instance


@app.get("/storage/{file_path:path}")
async def serve_local_storage_file(file_path: str):
    """Serve files from local storage.

    This endpoint allows the frontend to access images and other files
    stored in local storage during development/local deployment.
    """
    storage = get_storage_instance()

    # Only serve files if using LocalStorage
    if not isinstance(storage, LocalStorage):
        raise HTTPException(
            status_code=404,
            detail="File serving only available in local storage mode"
        )

    try:
        # Get the full filesystem path
        full_path = storage.get_local_path(file_path)

        # Check if file exists
        if not os.path.exists(full_path):
            raise HTTPException(status_code=404, detail="File not found")

        # Check if it's a file (not directory)
        if not os.path.isfile(full_path):
            raise HTTPException(status_code=400, detail="Path is not a file")

        # Try to read content type from .meta file
        meta_path = full_path + ".meta"
        media_type = None
        if os.path.exists(meta_path):
            try:
                with open(meta_path, 'r') as f:
                    media_type = f.read().strip()
            except Exception as e:
                logger.warning(f"Could not read media type from {meta_path}: {e}")

        # Return the file
        return FileResponse(
            path=full_path,
            media_type=media_type,
            filename=os.path.basename(full_path)
        )

    except ValueError as e:
        # Path traversal or other security issue
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error serving file {file_path}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


async def get_current_user(
    authorization: str = Header(..., description="Bearer access token"),
):
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid authorization header")

    api_key = authorization.split(" ", 1)[1]
    user = await get_user_by_api_key(api_key)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid or expired API key")

    return user


# --- Usage Tracking ---


async def track_usage(user_id: str, session_id: str, endpoint: str, cost: float):
    """Track usage with the provided cost and data."""
    if cost is not None and cost > 0:
        credits = convert_dollars_to_credits(cost)
        logger.info(
            f"Tool usage tracked for session {session_id}: "
            f"endpoint={endpoint}, "
            f"credits={credits}"
        )
        success = await apply_tool_usage(user_id, session_id, credits)
        if not success:
            logger.error(
                f"Failed to apply tool usage for user {user_id} - session {session_id} - endpoint {endpoint} - cost {cost}"
            )


# --- Health Check ---


@app.get("/health")
async def health_check():
    return {"status": "ok"}


class BaseRequest(BaseModel):
    session_id: str


# --- Image Generation ---


class ImageGenerationRequest(BaseRequest):
    prompt: str
    aspect_ratio: Literal["1:1", "16:9", "9:16", "4:3", "3:4"] = "1:1"


class ImageGenerationResponse(BaseModel):
    success: bool
    url: str | None = None
    error: str | None = None
    size: int | None = None
    mime_type: str | None = None
    search_results: List[Dict[str, Any]] | None = None


@app.post("/image-generation", response_model=ImageGenerationResponse)
async def generate_image(
    request: ImageGenerationRequest,
    user: User = Depends(get_current_user),
):
    """Generate image from text prompt."""

    client = create_image_generation_client(config.image_generate_config)
    image_result = await client.generate_image(
        prompt=request.prompt, aspect_ratio=request.aspect_ratio
    )
    response = ImageGenerationResponse(
        success=True,
        url=image_result.url,
        size=image_result.size,
        mime_type=image_result.mime_type,
        search_results=image_result.search_results,
    )

    await track_usage(
        user_id=user.id,
        session_id=request.session_id,
        endpoint="/image-generation",
        cost=image_result.cost,
    )

    return response


# --- Video Generation ---


class VideoGenerationRequest(BaseRequest):
    prompt: str
    aspect_ratio: Literal["16:9", "9:16"] = "16:9"
    duration_seconds: int = Field(..., ge=5, le=30)
    image_base64: str | None = None
    image_mime_type: Literal["image/png", "image/jpeg", "image/webp"] | None = None


class VideoGenerationResponse(BaseModel):
    success: bool
    url: str | None = None
    size: int | None = None
    mime_type: str | None = None
    error: str | None = None
    search_results: List[Dict[str, Any]] | None = None


@app.post("/video-generation", response_model=VideoGenerationResponse)
async def video_generation(
    request: VideoGenerationRequest,
    user: User = Depends(get_current_user),
):
    """Generate video from text prompt or/and image."""

    try:
        video_result = await video_generation_service.generate_video(
            prompt=request.prompt,
            aspect_ratio=request.aspect_ratio,
            duration_seconds=request.duration_seconds,
            image_base64=request.image_base64,
            image_mime_type=request.image_mime_type,
        )
    except VideoGenerationError as e:
        error_message = str(e)
        # Provide user-friendly messages for common errors
        if "403" in error_message or "PermissionDenied" in error_message:
            if "verified" in error_message.lower():
                user_message = "Video generation requires OpenAI organization verification. Please verify your organization at https://platform.openai.com/settings/organization/general"
            else:
                user_message = "Access denied to video generation API. Please check your API key permissions."
        elif "401" in error_message or "Unauthorized" in error_message:
            user_message = "Invalid API key for video generation. Please check your configuration."
        elif "429" in error_message or "rate" in error_message.lower():
            user_message = "Video generation rate limit exceeded. Please try again later."
        elif "timeout" in error_message.lower():
            user_message = "Video generation timed out. Please try again with a shorter duration."
        else:
            user_message = f"Video generation failed: {error_message}"

        logger.error(f"Video generation error: {error_message}")
        return VideoGenerationResponse(
            success=False,
            error=user_message,
        )

    response = VideoGenerationResponse(
        success=True,
        url=video_result.url,
        size=video_result.size,
        mime_type=video_result.mime_type,
        search_results=video_result.search_results,
    )

    await track_usage(
        user_id=user.id,
        session_id=request.session_id,
        endpoint="/video-generation",
        cost=video_result.cost,
    )

    return response


# --- Web Search ---


class WebSearchRequest(BaseRequest):
    query: str
    max_results: int = 5


class WebSearchResponse(BaseModel):
    success: bool
    results: List[Dict[str, Any]] | None = None
    error: str | None = None


@app.post("/web-search", response_model=WebSearchResponse)
async def web_search(
    request: WebSearchRequest,
    user: User = Depends(get_current_user),
):
    """Perform web search using configured providers."""
    try:
        client = create_web_search_client(config.web_search_config)
        result = await client.search(request.query, request.max_results)

        # Always return success=True if we got here, even with empty results
        response = WebSearchResponse(success=True, results=result.result)

        await track_usage(
            user_id=user.id,
            session_id=request.session_id,
            endpoint="/web-search",
            cost=result.cost,
        )

        return response
    except WebSearchExhaustedError as e:
        logger.error(str(e))
        raise HTTPException(status_code=429, detail=str(e))
    except (WebSearchNetworkError, WebSearchProviderError) as e:
        logger.error(str(e))
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logger.exception(f"Unexpected error in web search: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


class WebBatchSearchRequest(BaseRequest):
    queries: List[str]
    max_results: int = 6


class WebBatchSearchResponse(BaseModel):
    success: bool
    results: List[List[Dict[str, Any]]] | None = None
    error: str | None = None


@app.post("/v2/web-search", response_model=WebBatchSearchResponse)
async def web_batch_search(
    request: WebBatchSearchRequest,
    user: User = Depends(get_current_user),
):
    """Perform web search using configured providers."""
    try:
        client = create_web_search_client(config.web_search_config)
        results = await client.batch_search(request.queries, request.max_results)
        response = WebBatchSearchResponse(
            success=True, results=[result.result for result in results]
        )

        await track_usage(
            user_id=user.id,
            session_id=request.session_id,
            endpoint="/web-batch-search",
            cost=sum([result.cost for result in results]),
        )

        return response
    except WebSearchExhaustedError as e:
        logger.error(str(e))
        raise HTTPException(status_code=429, detail=str(e))
    except (WebSearchNetworkError, WebSearchProviderError) as e:
        logger.error(str(e))
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logger.exception(f"Unexpected error in web search: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# --- Image Search ---


class ImageSearchRequest(BaseRequest):
    query: str
    aspect_ratio: Literal["all", "square", "tall", "wide", "panoramic"] = "all"
    image_type: Literal["all", "face", "photo", "clipart", "lineart", "animated"] = (
        "all"
    )
    min_width: int = 0
    min_height: int = 0
    is_product: bool = False
    max_results: int = 5


class ImageSearchResponse(BaseModel):
    success: bool
    results: List[Dict[str, Any]] | None = None
    error: str | None = None


@app.post("/image-search", response_model=ImageSearchResponse)
async def image_search(
    request: ImageSearchRequest,
    user: User = Depends(get_current_user),
):
    """Perform image search using configured providers."""
    result = await image_search_service.search(
        query=request.query,
        aspect_ratio=request.aspect_ratio,
        image_type=request.image_type,
        min_width=request.min_width,
        min_height=request.min_height,
        is_product=request.is_product,
        max_results=request.max_results,
    )
    response = ImageSearchResponse(success=True, results=result.result)

    await track_usage(
        user_id=user.id,
        session_id=request.session_id,
        endpoint="/image-search",
        cost=result.cost,
    )

    return response


# --- Web Visit ---


class WebVisitRequest(BaseRequest):
    url: str
    prompt: str | None = None


class WebVisitResponse(BaseModel):
    success: bool
    content: str | None = None
    error: str | None = None


@app.post("/web-visit", response_model=WebVisitResponse)
async def web_visit(
    request: WebVisitRequest,
    user: User = Depends(get_current_user),
):
    """Visit a web page and extract content."""
    try:
        result = await web_visit_service.visit(request.url, request.prompt)
    except Exception as e:
        logger.error(f"Failed to visit web page: {e}")
        return WebVisitResponse(success=False, error=str(e))
    response = WebVisitResponse(success=True, content=result.content)

    await track_usage(
        user_id=user.id,
        session_id=request.session_id,
        endpoint="/web-visit",
        cost=result.cost,
    )

    return response


class ResearcherVisitRequest(BaseRequest):
    urls: List[str]
    query: str


class ResearcherVisitResponse(BaseModel):
    success: bool
    error: str | None
    content: str


@app.post("/researcher-web-visit", response_model=ResearcherVisitResponse)
async def researcher_web_visit(
    request: ResearcherVisitRequest,
    user: User = Depends(get_current_user),
):
    """Visit a web page and extract content using specified client type."""
    try:
        logger.info("Using batch visit with normal search")
        result = await web_visit_service.batch_visit(request.urls, request.query)
    except WebVisitError:
        logger.info("Fall back to Gemini Visit")
        result = await web_visit_service.researcher_visit(request.urls, request.query)
    except Exception as e:
        logger.error(f"Failed to visit web page with gemini: {e}")
        return ResearcherVisitResponse(content="", success=False, error=str(e))

    await track_usage(
        user_id=str(user.id),
        session_id=request.session_id,
        endpoint="/researcher-web-visit",
        cost=result.cost,
    )
    return ResearcherVisitResponse(content=result.content, success=True, error=None)


# --- Database ---


class DatabaseConnectionRequest(BaseRequest):
    database_type: Literal["postgres"]


class DatabaseConnectionResponse(BaseModel):
    success: bool
    connection_string: str | None = None
    error: str | None = None


@app.post("/database", response_model=DatabaseConnectionResponse)
async def database_connection(
    request: DatabaseConnectionRequest,
    user: User = Depends(get_current_user),
):
    """Get a database connection."""
    try:
        client = create_database_client(request.database_type, config.database_config)
        connection_string = await client.get_database_connection()
    except Exception as e:
        logger.error(f"Failed to get database connection: {e}")
        return DatabaseConnectionResponse(success=False, error=str(e))
    return DatabaseConnectionResponse(success=True, connection_string=connection_string)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the tool server")
    parser.add_argument(
        "--port", type=int, default=7000, help="Port to run the server on"
    )
    parser.add_argument(
        "--workers", type=int, default=1, help="Number of worker processes"
    )
    args = parser.parse_args()

    uvicorn.run(
        "src.ii_tool.integrations.app.main:app",
        host="0.0.0.0",
        port=args.port,
        workers=args.workers,
    )
