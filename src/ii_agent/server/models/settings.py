"""Settings management Pydantic models."""

from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List


class LLMProviderCreate(BaseModel):
    """Model for creating LLM provider settings."""

    provider: str = Field(..., regex="^(openai|anthropic|bedrock|gemini|azure)$")
    api_key: str = Field(..., description="API key for the provider")
    base_url: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class LLMProviderUpdate(BaseModel):
    """Model for updating LLM provider settings."""

    api_key: Optional[str] = None
    base_url: Optional[str] = None
    is_active: Optional[bool] = None
    metadata: Optional[Dict[str, Any]] = None


class LLMProviderInfo(BaseModel):
    """Model for LLM provider information."""

    id: str
    provider: str
    base_url: Optional[str] = None
    is_active: bool
    has_api_key: bool
    created_at: str
    updated_at: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class LLMProviderList(BaseModel):
    """Model for LLM provider list response."""

    providers: List[LLMProviderInfo]


class MCPConfigCreate(BaseModel):
    """Model for creating MCP configuration."""

    mcp_config: Dict[str, Any] = Field(..., description="MCP configuration object")


class MCPConfigUpdate(BaseModel):
    """Model for updating MCP configuration."""

    mcp_config: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = None


class MCPConfigInfo(BaseModel):
    """Model for MCP configuration information."""

    id: str
    mcp_config: Dict[str, Any]
    is_active: bool
    created_at: str
    updated_at: Optional[str] = None


class MCPConfigList(BaseModel):
    """Model for MCP configuration list response."""

    configurations: List[MCPConfigInfo]


class ProviderValidation(BaseModel):
    """Model for provider validation response."""

    provider: str
    valid: bool
    error_message: Optional[str] = None
    supported_models: Optional[List[str]] = None


class LLMModelInfo(BaseModel):
    """Model for LLM model information."""

    id: str
    name: str
    provider: str
    context_length: int
    input_price_per_token: float
    output_price_per_token: float
    supports_function_calling: bool
    supports_vision: bool
    description: Optional[str] = None


class APIKeyTest(BaseModel):
    """Model for testing API key."""

    provider: str
    api_key: str
    base_url: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class SettingsExport(BaseModel):
    """Model for exporting user settings."""

    llm_providers: List[LLMProviderInfo]
    mcp_configurations: List[MCPConfigInfo]
    export_timestamp: str


class SettingsImport(BaseModel):
    """Model for importing user settings."""

    llm_providers: Optional[List[LLMProviderCreate]] = []
    mcp_configurations: Optional[List[MCPConfigCreate]] = []
    overwrite_existing: bool = False
