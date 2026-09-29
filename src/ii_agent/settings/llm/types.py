"""LLM settings domain enums."""

from enum import StrEnum


class Provider(StrEnum):
    """LLM provider identifier — who makes the model.

    Single source of truth — imported by settings/llm models, agent models,
    billing/credits, and any module that needs provider discrimination.

    The hosting platform (VertexAI, Azure, Bedrock) is expressed via
    ``ApiType``, not here.
    """

    OPENAI = "OpenAI"
    ANTHROPIC = "Anthropic"
    GOOGLE = "Google"
    CEREBRAS = "Cerebras"
    ATLASCLOUD = "AtlasCloud"
    CUSTOM = "Custom"


class ApiType(StrEnum):
    """Hosting platform / API variant for an LLM provider.

    Determines *how* to reach the model (SDK, auth, endpoint), while
    ``Provider`` determines *whose* model it is.

    Examples:
        Provider.ANTHROPIC + ApiType.VERTEX_AI  → AsyncAnthropicVertex
        Provider.GOOGLE    + ApiType.VERTEX_AI  → genai.Client(vertexai=True)
        Provider.OPENAI    + ApiType.AZURE      → AsyncAzureOpenAI
        Provider.ANTHROPIC + None               → AsyncAnthropic (direct API)
    """

    VERTEX_AI = "vertex_ai"
    AZURE = "azure"
    BEDROCK = "bedrock"


class ConfigType(StrEnum):
    """Discriminator for system vs user LLM settings."""

    USER = "user"
    SYSTEM = "system"
