"""Pydantic schemas (DTOs) for llm_settings domain."""

from __future__ import annotations

import logging

from pydantic import BaseModel, ConfigDict, Field, SecretStr
from uuid import UUID

from .types import ApiType, Provider
from ii_agent.settings.llm.types import ConfigType

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Nested JSONB schemas
# ---------------------------------------------------------------------------


class ModelParams(BaseModel):
    """Provider-specific settings stored in the ``configs`` JSONB column."""

    max_retries: int = Field(default=3)
    max_message_chars: int = Field(default=30000)
    temperature: float = Field(default=0.0)
    thinking_tokens: int = Field(default=16000)
    # API type — hosting platform (None = direct provider API)
    api_type: ApiType | None = None
    # Vertex AI
    vertex_region: str | None = None
    vertex_project_id: str | None = None
    # Azure
    azure_endpoint: str | None = None
    azure_api_version: str | None = None
    # Flags
    cot_model: bool = False


class PricingInfo(BaseModel):
    """Pricing stored in the ``pricing`` JSONB column.

    Also serves as the single source of truth for default model pricing
    via :meth:`get_default_pricing`.
    """

    input_price_per_million: float = Field(
        default=0.0, description="Price per million input tokens in USD"
    )
    output_price_per_million: float = Field(
        default=0.0, description="Price per million output tokens in USD"
    )
    cache_write_price_per_million: float = Field(
        default=0.0, description="Price per million cache write tokens"
    )
    cache_read_price_per_million: float = Field(
        default=0.0, description="Price per million cache read tokens"
    )
    is_fallback: bool = Field(
        default=False,
        description="True when pricing was resolved via provider/global fallback, not exact match",
    )

    @classmethod
    def get_default_pricing(cls, model_id: str, provider: Provider | None = None) -> PricingInfo:
        """Get default pricing for common models.

        Args:
            model_id: The model ID (e.g., "claude-sonnet-4-5-20250929")
            provider: Optional provider name for disambiguation

        Returns:
            PricingInfo with appropriate pricing for the model
        """
        pricing_map: dict[str, PricingInfo] = {
            # ===== Anthropic Claude Models =====
            "claude-opus-4-7": cls(
                input_price_per_million=5.0,
                output_price_per_million=25.0,
                cache_write_price_per_million=6.25,
                cache_read_price_per_million=0.5,
            ),
            "claude-opus-4-6": cls(
                input_price_per_million=5.0,
                output_price_per_million=25.0,
                cache_write_price_per_million=6.25,
                cache_read_price_per_million=0.5,
            ),
            "claude-opus-4-5": cls(
                input_price_per_million=5.0,
                output_price_per_million=25.0,
                cache_write_price_per_million=6.25,
                cache_read_price_per_million=0.5,
            ),
            "claude-sonnet-4-5": cls(
                input_price_per_million=3.0,
                output_price_per_million=15.0,
                cache_write_price_per_million=3.75,
                cache_read_price_per_million=0.3,
            ),
            "claude-sonnet-4": cls(
                input_price_per_million=3.0,
                output_price_per_million=15.0,
                cache_write_price_per_million=3.75,
                cache_read_price_per_million=0.3,
            ),
            "claude-opus-4": cls(
                input_price_per_million=15.0,
                output_price_per_million=75.0,
                cache_write_price_per_million=18.75,
                cache_read_price_per_million=1.5,
            ),
            "claude-3-5-haiku": cls(
                input_price_per_million=0.8,
                output_price_per_million=4.0,
                cache_write_price_per_million=1.0,
                cache_read_price_per_million=0.08,
            ),
            # ===== OpenAI Models =====
            "gpt-4o": cls(
                input_price_per_million=2.5,
                output_price_per_million=10.0,
                cache_read_price_per_million=1.25,
            ),
            "gpt-4o-mini": cls(
                input_price_per_million=0.15,
                output_price_per_million=0.6,
                cache_read_price_per_million=0.075,
            ),
            "o1": cls(
                input_price_per_million=15.0,
                output_price_per_million=60.0,
                cache_read_price_per_million=7.5,
            ),
            "o1-mini": cls(
                input_price_per_million=1.1,
                output_price_per_million=4.4,
                cache_read_price_per_million=0.55,
            ),
            "o3": cls(
                input_price_per_million=10.0,
                output_price_per_million=40.0,
                cache_read_price_per_million=2.5,
            ),
            "o3-mini": cls(
                input_price_per_million=1.1,
                output_price_per_million=4.4,
                cache_read_price_per_million=0.55,
            ),
            # ===== Google Gemini Models =====
            "gemini-2.5-pro": cls(
                input_price_per_million=1.25,
                output_price_per_million=10.0,
            ),
            "gemini-2.5-flash": cls(
                input_price_per_million=0.15,
                output_price_per_million=0.6,
            ),
            "gemini-2.0-flash": cls(
                input_price_per_million=0.1,
                output_price_per_million=0.4,
            ),
            "gemini-3-pro-preview": cls(
                input_price_per_million=2.0,
                output_price_per_million=12.0,
            ),
            "gemini-3-flash-preview": cls(
                input_price_per_million=0.5,
                output_price_per_million=3.0,
            ),
            "gemini-3.1-pro-preview": cls(
                input_price_per_million=2.0,
                output_price_per_million=12.0,
            ),
            # ===== DeepSeek Models =====
            "deepseek-reasoner": cls(
                input_price_per_million=0.55,
                output_price_per_million=2.19,
                cache_read_price_per_million=0.14,
            ),
            "deepseek-chat": cls(
                input_price_per_million=0.27,
                output_price_per_million=1.1,
                cache_read_price_per_million=0.07,
            ),
        }

        normalized_id = model_id.lower()

        # Try exact match
        if normalized_id in pricing_map:
            return pricing_map[normalized_id]

        # Try prefix matching (handles versioned IDs like "claude-sonnet-4-5-20250929")
        for pattern, pricing in pricing_map.items():
            if normalized_id.startswith(pattern):
                return cls(
                    input_price_per_million=pricing.input_price_per_million,
                    output_price_per_million=pricing.output_price_per_million,
                    cache_write_price_per_million=pricing.cache_write_price_per_million,
                    cache_read_price_per_million=pricing.cache_read_price_per_million,
                )

        # Provider-based defaults
        logger.warning(
            "BILLING_PRICING_FALLBACK: No exact or prefix pricing match for model '%s' "
            "(provider=%s) — using provider default. Add this model to the pricing table "
            "to ensure correct billing.",
            model_id,
            provider,
        )
        if provider:
            provider_defaults: dict[Provider, PricingInfo] = {
                Provider.ANTHROPIC: cls(
                    input_price_per_million=3.0,
                    output_price_per_million=15.0,
                    cache_write_price_per_million=3.75,
                    cache_read_price_per_million=0.3,
                    is_fallback=True,
                ),
                Provider.OPENAI: cls(
                    input_price_per_million=2.5,
                    output_price_per_million=10.0,
                    cache_read_price_per_million=1.25,
                    is_fallback=True,
                ),
                Provider.GOOGLE: cls(
                    input_price_per_million=0.15,
                    output_price_per_million=0.6,
                    is_fallback=True,
                ),
            }
            if provider in provider_defaults:
                return provider_defaults[provider]

        # No provider either — this should not happen in production.
        logger.error(
            "BILLING_PRICING_MISSING: No provider default for model '%s' "
            "(provider=%s) — using global conservative fallback. This model is "
            "being billed at an estimated rate.",
            model_id,
            provider,
        )
        return cls(
            input_price_per_million=2.5,
            output_price_per_million=10.0,
            cache_read_price_per_million=1.25,
            is_fallback=True,
        )


class ModelConfigEntry(BaseModel):
    """A single model configuration entry for seeding.

    Used in ``MODEL_CONFIGS`` env var (JSON list) or ``MODEL_CONFIGS_FILE``
    (YAML list). Maps directly to a ``ModelSetting`` DB row.
    """

    model_id: str
    provider: Provider
    api_key: str | None = None
    base_url: str | None = None
    display_name: str | None = None
    is_default: bool = False
    params: ModelParams = Field(default_factory=ModelParams)
    pricing: PricingInfo | None = None


class ModelConfig(BaseModel):
    """Resolved model configuration for agent / LLM provider construction.

    Built from a ``ModelSetting`` DB row.  Carries everything needed to
    instantiate an LLM provider: credentials, endpoint, provider-specific
    params, and pricing.
    """

    id: UUID
    model_id: str
    provider: Provider
    api_key: SecretStr | None = None
    base_url: str | None = None
    display_name: str | None = None
    params: ModelParams = Field(default_factory=ModelParams)
    pricing: PricingInfo | None = None
    config_type: ConfigType = ConfigType.SYSTEM

    def is_user_model(self) -> bool:
        """Return True when the config originates from a user-provided key."""
        return self.config_type == ConfigType.USER

    @property
    def setting_id(self) -> str:
        """Backward-compatible string ID used by callers that expect ``str``."""
        return str(self.id)

    @property
    def api_type(self) -> ApiType | None:
        """Hosting platform for this model (None = direct provider API)."""
        return self.params.api_type

    # Convenience accessors that mirror legacy LLMConfig field names so that
    # consumer code (agent factory, model utils) can migrate incrementally.
    @property
    def model(self) -> str:
        return self.model_id

    @property
    def temperature(self) -> float:
        return self.params.temperature

    @property
    def max_retries(self) -> int:
        return self.params.max_retries

    @property
    def max_message_chars(self) -> int:
        return self.params.max_message_chars

    @property
    def thinking_tokens(self) -> int:
        return self.params.thinking_tokens

    @property
    def vertex_region(self) -> str | None:
        return self.params.vertex_region

    @property
    def vertex_project_id(self) -> str | None:
        return self.params.vertex_project_id

    @property
    def azure_endpoint(self) -> str | None:
        return self.params.azure_endpoint

    @property
    def azure_api_version(self) -> str | None:
        return self.params.azure_api_version

    @property
    def cot_model(self) -> bool:
        return self.params.cot_model


# ---------------------------------------------------------------------------
# Create / Update DTOs
# ---------------------------------------------------------------------------


class ModelSettingCreate(BaseModel):
    """Input for creating / upserting an LLM model setting."""

    model_id: str = Field(..., description="Model identifier (e.g. 'claude-sonnet-4-6')")
    provider: str = Field(..., description="Provider name (Anthropic, OpenAI, Google, Custom)")
    api_key: str = Field(..., description="API key for the model")
    base_url: str | None = Field(None, description="Base URL for API endpoint")
    display_name: str | None = Field(None, description="Human-readable label")
    configs: ModelParams | None = Field(None, description="Provider-specific settings")
    pricing: PricingInfo | None = Field(None, description="Token pricing info")
    config_type: ConfigType = Field(default=ConfigType.USER)
    is_default: bool = Field(default=False)
    is_active: bool = Field(default=True)


class ModelSettingUpdate(BaseModel):
    """Input for partial-updating an existing LLM model setting."""

    api_key: str | None = None
    base_url: str | None = None
    display_name: str | None = None
    configs: ModelParams | None = None
    pricing: PricingInfo | None = None
    config_type: ConfigType | None = None
    is_default: bool | None = None
    is_active: bool | None = None


# ---------------------------------------------------------------------------
# Response DTOs
# ---------------------------------------------------------------------------


class ModelSettingInfo(BaseModel):
    """LLM model setting response (no sensitive data)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    model_id: str
    provider: str
    base_url: str | None = None
    display_name: str | None = None
    configs: ModelParams | None = None
    pricing: PricingInfo | None = None
    config_type: ConfigType
    is_default: bool
    is_active: bool
    has_api_key: bool
    created_at: str
    updated_at: str | None = None


class ModelSettingInfoWithKey(ModelSettingInfo):
    """LLM model setting response (includes decrypted API key)."""

    api_key: str | None = None


class ModelSettingList(BaseModel):
    """Wrapper for listing model settings."""

    models: list[ModelSettingInfo]

    def get_by_id(self, setting_id: str) -> ModelSettingInfo | None:
        return next(
            (s for s in self.models if str(s.id) == setting_id),
            None,
        )

    def get_by_model(self, model_id: str) -> ModelSettingInfo | None:
        return next(
            (s for s in self.models if s.model_id == model_id),
            None,
        )


# ---------------------------------------------------------------------------
# Unified model list (system + user)
# ---------------------------------------------------------------------------


class LLMModelInfo(BaseModel):
    """Combined model info for the "all available models" endpoint."""

    id: UUID
    model_id: str
    model: str = ""  # Alias for model_id, used by FE
    provider: str
    display_name: str | None = None
    source: str = "system"
    base_url: str | None = None
    pricing: PricingInfo | None = None
    is_default: bool = False


class LLMModelList(BaseModel):
    """Response for listing all available models."""

    models: list[LLMModelInfo]
