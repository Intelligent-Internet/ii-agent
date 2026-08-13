from ii_agent.core.config.llm_config import LLMConfig
from ii_agent.agents.models.base import Model
from ii_agent.settings.llm import Provider
from ii_agent.settings.llm.types import ApiType


def _is_opus_4_7_or_later(model_id: str) -> bool:
    """Return True for Opus 4.7 or later model ids.

    Opus 4.7 removed support for manual extended thinking
    (``thinking: {type: "enabled", budget_tokens: N}`` returns HTTP 400).
    These models require ``thinking: {type: "adaptive"}`` combined with
    ``output_config: {"effort": ...}``. The check matches the base id
    ``claude-opus-4-7`` as well as dated snapshots (``claude-opus-4-7-YYYYMMDD``)
    and Vertex aliases (``claude-opus-4-7@YYYYMMDD``).

    See https://platform.claude.com/docs/en/build-with-claude/adaptive-thinking
    """
    mid = (model_id or "").lower()
    return mid.startswith("claude-opus-4-7") or mid.startswith("anthropic.claude-opus-4-7")


def _build_anthropic_direct(api_key: str | None, llm_config: LLMConfig) -> Model:
    """Build an Anthropic Claude model using the direct API.

    Extended thinking is enabled unconditionally here, which means Anthropic
    forbids any ``temperature`` value other than 1 (the API default).  We
    therefore do NOT forward ``llm_config.temperature`` — passing a non-1
    value would cause every request to fail with HTTP 400
    ``invalid_request_error`` (``temperature may only be set to 1 when
    thinking is enabled``) and break the native-fallback path.  See
    https://docs.claude.com/en/docs/build-with-claude/extended-thinking
    #important-considerations-when-using-extended-thinking

    Claude Opus 4.7 removed manual extended thinking; we use adaptive thinking
    with the ``output_config.effort`` parameter instead. ``display`` defaults
    to ``"omitted"`` on Opus 4.7, so we set it to ``"summarized"`` explicitly
    to preserve the current behaviour of surfacing reasoning summaries.
    """
    from ii_agent.agents.models.anthropic.claude import Claude

    client_params = {}
    if llm_config.base_url:
        client_params["base_url"] = llm_config.base_url

    if _is_opus_4_7_or_later(llm_config.model):
        return Claude(
            id=llm_config.model,
            # temperature intentionally omitted — incompatible with thinking
            thinking={"type": "adaptive", "display": "summarized"},
            # effort replaces budget_tokens on Opus 4.7; xhigh is the docs'
            # recommended starting point for coding/agentic workloads.
            request_params={"output_config": {"effort": "xhigh"}},
            api_key=api_key,
            max_tokens=64_000,
            # interleaved thinking is automatic with adaptive; beta header
            # is deprecated and not required on Opus 4.7.
            cache_conversation=True,
            cache_system_prompt=True,
            retries=llm_config.max_retries,
            extended_cache_time=False,
            timeout=600.0,
            client_params=client_params or None,
        )

    return Claude(
        id=llm_config.model,
        # temperature intentionally omitted — incompatible with thinking=enabled
        thinking={"type": "enabled", "budget_tokens": 16_000},
        api_key=api_key,
        max_tokens=32_000,
        betas=["interleaved-thinking-2025-05-14"],
        cache_conversation=True,
        cache_system_prompt=True,
        retries=llm_config.max_retries,
        extended_cache_time=False,
        timeout=600.0,
        client_params=client_params or None,
    )


def _build_anthropic_vertex(api_key: str | None, llm_config: LLMConfig) -> Model:
    """Build an Anthropic Claude model routed through VertexAI.

    See :func:`_build_anthropic_direct` for why ``temperature`` is omitted
    and for the Opus 4.7 adaptive-thinking branch.
    """
    from ii_agent.agents.models.vertexai.claude import Claude as VertexAIClaude

    client_params = {}
    if llm_config.base_url:
        client_params["base_url"] = llm_config.base_url

    if _is_opus_4_7_or_later(llm_config.model):
        return VertexAIClaude(
            id=llm_config.model,
            api_key=api_key,
            project_id=llm_config.vertex_project_id,
            region=llm_config.vertex_region,
            # temperature intentionally omitted — incompatible with thinking
            timeout=600.0,
            thinking={"type": "adaptive", "display": "summarized"},
            request_params={"output_config": {"effort": "xhigh"}},
            cache_conversation=True,
            retries=llm_config.max_retries,
            base_url=llm_config.base_url,
            max_tokens=64_000,
            cache_system_prompt=True,
            extended_cache_time=False,
            client_params=client_params or None,
        )

    return VertexAIClaude(
        id=llm_config.model,
        api_key=api_key,
        project_id=llm_config.vertex_project_id,
        region=llm_config.vertex_region,
        # temperature intentionally omitted — incompatible with thinking=enabled
        betas=["interleaved-thinking-2025-05-14"],
        timeout=600.0,
        thinking={"type": "enabled", "budget_tokens": 16_000},
        cache_conversation=True,
        retries=llm_config.max_retries,
        base_url=llm_config.base_url,
        max_tokens=32_000,
        cache_system_prompt=True,
        extended_cache_time=False,
        client_params=client_params or None,
    )


def _build_google(api_key: str | None, llm_config: LLMConfig, vertexai: bool) -> Model:
    """Build a Google Gemini model (direct or VertexAI)."""
    from ii_agent.agents.models.google import Gemini

    # Gemini 3 strongly recommends keeping temperature at 1.0 (default) when thinking is enabled.
    is_gemini3 = llm_config.model.startswith("gemini-3")
    temperature = None if is_gemini3 else llm_config.temperature

    return Gemini(
        api_key=api_key,
        id=llm_config.model,
        temperature=temperature,
        retries=llm_config.max_retries,
        include_thoughts=True,
        thinking_level="high",
        vertexai=vertexai,
        max_output_tokens=llm_config.max_message_chars,
        project_id=llm_config.vertex_project_id,
        location=llm_config.vertex_region,
    )


def _build_openai(api_key: str | None, llm_config: LLMConfig) -> Model:
    """Build an OpenAI model (direct API)."""
    from ii_agent.agents.models.openai import OpenAIResponses

    return OpenAIResponses(
        api_key=api_key,
        id=llm_config.model,
        parallel_tool_calls=True,
        max_retries=llm_config.max_retries,
        base_url=llm_config.base_url,
        max_output_tokens=64_000,
        timeout=600.0,
        truncation="auto",
        reasoning={"effort": "medium", "summary": "auto"},
    )


def _build_custom(api_key: str | None, llm_config: LLMConfig) -> Model:
    """Build a custom OpenAI-compatible model."""
    from ii_agent.agents.models.custom import OpenAIChatCustom

    return OpenAIChatCustom(
        api_key=api_key,
        provider=Provider.CUSTOM,
        id=llm_config.model,
        max_retries=llm_config.max_retries,
        base_url=llm_config.base_url,
        max_completion_tokens=64_000,
        timeout=600.0,
        reasoning_effort="high",
    )


# (Provider, ApiType | None) → builder function
_MODEL_BUILDERS: dict[
    tuple[Provider, ApiType | None],
    callable,
] = {
    (Provider.ANTHROPIC, None): lambda ak, cfg: _build_anthropic_direct(ak, cfg),
    (Provider.ANTHROPIC, ApiType.VERTEX_AI): lambda ak, cfg: _build_anthropic_vertex(ak, cfg),
    (Provider.GOOGLE, None): lambda ak, cfg: _build_google(ak, cfg, vertexai=False),
    (Provider.GOOGLE, ApiType.VERTEX_AI): lambda ak, cfg: _build_google(ak, cfg, vertexai=True),
    (Provider.OPENAI, None): lambda ak, cfg: _build_openai(ak, cfg),
    (Provider.CEREBRAS, None): lambda ak, cfg: _build_custom(ak, cfg),
    (Provider.CUSTOM, None): lambda ak, cfg: _build_custom(ak, cfg),
}


def get_model(model_provider: Provider, llm_config: LLMConfig, **kwargs) -> Model:
    """Create an agent Model based on (provider, api_type).

    The ``api_type`` field on ``LLMConfig`` determines the hosting platform
    (VertexAI, Azure, Bedrock) while ``model_provider`` identifies the model
    maker (Anthropic, Google, OpenAI, etc.).
    """
    api_key = llm_config.api_key.get_secret_value() if llm_config.api_key else None
    api_type = llm_config.api_type

    builder = _MODEL_BUILDERS.get((model_provider, api_type))
    if builder is None:
        # Fall back to provider-only lookup (api_type=None)
        builder = _MODEL_BUILDERS.get((model_provider, None))
    if builder is None:
        return _build_custom(api_key, llm_config)

    return builder(api_key, llm_config)
