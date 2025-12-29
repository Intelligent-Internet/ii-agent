"""Settings management Pydantic models."""

from pydantic import BaseModel, SecretStr, Field
from typing import Optional, Dict, Any, List
from ii_agent.core.config.llm_config import APITypes, LLMConfig


class ModelSettingCreate(BaseModel):
    """Model for creating/updating LLM model settings."""

    model: str = Field(..., description="Model name (e.g., 'gpt-4', 'claude-3-opus')")
    api_type: APITypes = Field(..., description="API type (openai, anthropic, gemini)")
    api_key: str = Field(..., description="API key for the model")
    base_url: Optional[str] = Field(None, description="Base URL for API endpoint")
    max_retries: int = Field(default=10, description="Maximum number of retries")
    max_message_chars: int = Field(
        default=30000, description="Maximum message characters"
    )
    temperature: float = Field(default=0.0, description="Temperature for generation")
    thinking_tokens: int = Field(default=16000, description="Number of thinking tokens")
    metadata: Optional[Dict[str, Any]] = Field(
        None, description="Additional metadata (Azure/Bedrock/Vertex config)"
    )


class ModelSettingUpdate(BaseModel):
    """Model for updating existing LLM model settings."""

    api_key: Optional[str] = Field(None, description="API key for the model")
    base_url: Optional[str] = Field(None, description="Base URL for API endpoint")
    max_retries: Optional[int] = Field(None, description="Maximum number of retries")
    max_message_chars: Optional[int] = Field(
        None, description="Maximum message characters"
    )
    temperature: Optional[float] = Field(None, description="Temperature for generation")
    thinking_tokens: Optional[int] = Field(
        None, description="Number of thinking tokens"
    )
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional metadata")
    is_active: Optional[bool] = Field(None, description="Whether the model is active")


class ModelSettingInfo(BaseModel):
    """Model for LLM model setting information (without sensitive data)."""

    id: str
    model: str
    api_type: APITypes
    base_url: Optional[str] = None
    max_retries: int
    max_message_chars: int
    temperature: float
    thinking_tokens: int = 16000
    is_active: bool
    has_api_key: bool
    created_at: str
    updated_at: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class ModelSettingInfoWithKey(ModelSettingInfo):
    """Model for LLM model setting information (with API key)."""

    api_key: Optional[str] = None

    def to_llm_config(self) -> LLMConfig:
        """Convert to LLMConfig."""
        if not self.api_key:
            raise ValueError("API key is required for LLMConfig conversion")

        return LLMConfig(
            setting_id=self.id,
            model=self.model,
            api_type=self.api_type,
            api_key=SecretStr(self.api_key),
            base_url=self.base_url,
            max_retries=self.max_retries,
            max_message_chars=self.max_message_chars,
            temperature=self.temperature,
            thinking_tokens=self.thinking_tokens,
            # Extract Azure/Vertex settings from metadata if present
            azure_endpoint=(
                self.metadata.get("azure_endpoint") if self.metadata else None
            ),
            azure_api_version=(
                self.metadata.get("azure_api_version") if self.metadata else None
            ),
            vertex_region=self.metadata.get("vertex_region") if self.metadata else None,
            vertex_project_id=(
                self.metadata.get("vertex_project_id") if self.metadata else None
            ),
            cot_model=self.metadata.get("cot_model", False) if self.metadata else False,
            enable_extended_context=self.metadata.get("enable_extended_context", False) if self.metadata else False,
            config_type="user",
        )


class ModelSettingList(BaseModel):
    """Model for LLM model setting list response."""

    models: List[ModelSettingInfo]

    def get_by_id(self, model_id: str) -> Optional[ModelSettingInfo]:
        """Get model setting by ID."""
        return next(
            (setting for setting in self.models if setting.id == model_id),
            None,
        )

    def get_by_model(self, model_name: str) -> Optional[ModelSettingInfo]:
        """Get model setting by model name."""
        return next(
            (setting for setting in self.models if setting.model == model_name),
            None,
        )


class LLMModelInfo(BaseModel):
    """Model for LLM model information."""

    id: str
    model: str
    api_type: APITypes
    description: Optional[str] = None
    source: str = "system"  # 'system' or 'user'
    base_url: Optional[str] = None


class LLMModelList(BaseModel):
    """Model for LLM model list response."""

    models: List[LLMModelInfo]
