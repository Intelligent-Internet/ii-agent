"""API endpoints for NVIDIA model management."""

from typing import List, Dict, Any
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
import httpx
import os

from ii_agent.core.config.ii_agent_config import config
from ii_agent.server.shared import session_service

router = APIRouter(prefix="/nvidia", tags=["nvidia"])


class NvidiaModel(BaseModel):
    """NVIDIA model information."""
    id: str
    object: str = "model"
    created: int | None = None
    owned_by: str = "nvidia"


class NvidiaModelsResponse(BaseModel):
    """Response model for NVIDIA models list."""
    object: str = "list"
    data: List[NvidiaModel]


@router.get("/models", response_model=NvidiaModelsResponse)
async def list_nvidia_models():
    """
    List available NVIDIA models from the NVIDIA API.

    This endpoint queries the NVIDIA API to get the list of available models
    and returns them in OpenAI-compatible format.
    """
    api_key = os.getenv("NVIDIA_API_KEY")
    if not api_key:
        raise HTTPException(
            status_code=401,
            detail="NVIDIA_API_KEY environment variable not set"
        )

    url = "https://integrate.api.nvidia.com/v1/models"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers, timeout=30.0)

            if response.status_code == 401:
                raise HTTPException(
                    status_code=401,
                    detail="Invalid NVIDIA API key"
                )
            elif response.status_code != 200:
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"NVIDIA API error: {response.text}"
                )

            data = response.json()

            # Convert to our response format
            models = []
            for model_data in data.get("data", []):
                model_id = model_data.get("id", "")
                # Filter to only include model IDs (exclude specific deployments)
                if "/" in model_id:
                    continue

                models.append(NvidiaModel(
                    id=model_id,
                    created=model_data.get("created"),
                    owned_by=model_data.get("owned_by", "nvidia")
                ))

            return NvidiaModelsResponse(data=models)

    except httpx.RequestError as e:
        raise HTTPException(
            status_code=503,
            detail=f"Failed to connect to NVIDIA API: {str(e)}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )


@router.get("/models/populate", response_model=Dict[str, Any])
async def populate_nvidia_models():
    """
    Populate the configuration with NVIDIA models.

    This endpoint fetches available NVIDIA models and updates the
    configuration to include them as available options.
    """
    models_response = await list_nvidia_models()

    # Extract model IDs
    model_ids = [model.id for model in models_response.data]

    # Define recommended NVIDIA models with their configurations
    recommended_models = {
        "kimi/kimi2-0905": {
            "name": "Kimi 2 (0905)",
            "description": "Advanced language model with strong reasoning",
            "category": "chat"
        },
        "qwen/qwen2.5-72b-instruct": {
            "name": "Qwen 2.5 72B Instruct",
            "description": "Large instruction-tuned model",
            "category": "chat"
        },
        "qwen/qwen3-coder-480b-a35b-instruct": {
            "name": "Qwen 3 Coder 480B",
            "description": "Specialized coding model",
            "category": "code"
        },
        "deepseek-ai/deepseek-r1": {
            "name": "DeepSeek R1",
            "description": "High-performance reasoning model",
            "category": "chat"
        },
        "meta/llama3.1-405b-instruct": {
            "name": "Llama 3.1 405B Instruct",
            "description": "Large instruction model with 405B parameters",
            "category": "chat"
        },
        "mistralai/mixtral-8x7b-instruct-v0.1": {
            "name": "Mixtral 8x7B Instruct",
            "description": "Mixture of experts model",
            "category": "chat"
        }
    }

    # Filter available models to only include recommended ones
    available_recommended = {
        model_id: model_info
        for model_id, model_info in recommended_models.items()
        if model_id in model_ids
    }

    return {
        "status": "success",
        "total_models": len(model_ids),
        "available_models": model_ids,
        "recommended_models": available_recommended,
        "config_updates": {
            "nvidia_models": available_recommended,
            "default_nvidia_model": "kimi/kimi2-0905" if "kimi/kimi2-0905" in model_ids else model_ids[0] if model_ids else None
        }
    }


@router.get("/models/{model_id}")
async def get_nvidia_model(model_id: str):
    """Get details about a specific NVIDIA model."""
    models_response = await list_nvidia_models()

    for model in models_response.data:
        if model.id == model_id:
            return {
                "id": model.id,
                "object": model.object,
                "created": model.created,
                "owned_by": model.owned_by,
                "provider": "nvidia",
                "api_base": "https://integrate.api.nvidia.com/v1"
            }

    raise HTTPException(
        status_code=404,
        detail=f"Model {model_id} not found"
    )