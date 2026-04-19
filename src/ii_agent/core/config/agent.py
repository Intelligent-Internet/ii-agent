"""Agent execution configuration."""

from typing import Dict, Literal, Set
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Constants
MAX_OUTPUT_TOKENS_PER_TURN = 32000
MAX_TURNS = 200
TOKEN_BUDGET = 128000  # Default token budget

# Default Copilot premium request multipliers (April 2026).
# Source: docs.github.com/en/copilot/concepts/billing/copilot-requests
# Keys are normalised model-id prefixes; value is the multiplier applied
# to a single user prompt.
_DEFAULT_COPILOT_MULTIPLIERS: Dict[str, float] = {
    "gpt-5-mini": 0.0,
    "gpt-4.1": 0.0,
    "gpt-4o": 0.0,
    "claude-3-5-haiku": 0.33,
    "grok-code-fast": 0.33,
    "claude-sonnet": 1.0,
    "gemini-3-pro": 1.0,
    "gpt-5.1": 1.0,
    "claude-opus": 3.0,
}


class AgentSettings(BaseSettings):
    """Agent execution and runtime configuration.

    Environment variables use AGENT_ prefix:
        AGENT_MAX_OUTPUT_TOKENS_PER_TURN: Maximum output tokens per turn
        AGENT_MAX_TURNS: Maximum number of turns per run
        AGENT_TOKEN_BUDGET: Total token budget for agent execution
        AGENT_AUTO_APPROVE_TOOLS: Auto-approve all tool calls
        AGENT_ALLOW_TOOLS: Comma-separated list of pre-approved tools

    Example .env:
        AGENT_MAX_OUTPUT_TOKENS_PER_TURN=32000
        AGENT_MAX_TURNS=200
        AGENT_TOKEN_BUDGET=128000
        AGENT_AUTO_APPROVE_TOOLS=false
        AGENT_ALLOW_TOOLS=web_search,file_read
    """

    model_config = SettingsConfigDict(
        env_prefix="AGENT_",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Token limits
    max_output_tokens_per_turn: int = Field(
        default=MAX_OUTPUT_TOKENS_PER_TURN,
        description="Maximum number of output tokens per agent turn",
        gt=0,
    )

    max_turns: int = Field(
        default=MAX_TURNS,
        description="Maximum number of turns before agent stops",
        gt=0,
    )

    token_budget: int = Field(
        default=TOKEN_BUDGET,
        description="Total token budget for agent execution",
        gt=0,
    )

    # Tool approval settings
    auto_approve_tools: bool = Field(
        default=False,
        description="Automatically approve all tool calls without user confirmation",
    )

    allow_tools: Set[str] = Field(
        default_factory=set,
        description="Set of tool names that are pre-approved for execution",
    )

    # Inner-loop routing
    inner_loop_mode: Literal["native", "a2a"] = Field(
        default="native",
        description="Inner-loop execution mode used by agents",
    )

    chat_inner_loop_mode: Literal["direct", "a2a"] = Field(
        default="direct",
        description=(
            "Inner-loop execution mode for chat (/v1/chat) conversations. "
            "'direct': use the default LLMTurnLoopService (direct SDK calls). "
            "'a2a': route through the A2A adapter (same transport as agent mode). "
            "Shares a2a_backend, a2a_timeout_seconds, a2a_fallback_to_native, "
            "a2a_context_reuse, and billing settings with agent mode. "
            "Env: AGENT_CHAT_INNER_LOOP_MODE"
        ),
    )

    a2a_agent_url: str | None = Field(
        default=None,
        description=(
            "Base URL for an external A2A agent when inner_loop_mode is 'a2a' and no sandbox "
            "is available (e.g. development, CI, or a standalone external agent). "
            "In production the URL is resolved per-sandbox via expose_port() and "
            "this field is not required."
        ),
    )

    a2a_timeout_seconds: float = Field(
        default=30.0,
        description="HTTP timeout for A2A adapter streaming requests",
        gt=0,
    )

    a2a_fallback_to_native: bool = Field(
        default=True,
        description="Fallback to native model execution when A2A path fails",
    )

    a2a_chat_strict: bool = Field(
        default=True,
        description=(
            "When AGENT_CHAT_INNER_LOOP_MODE=a2a, treat any inability to "
            "reach the A2A adapter as a hard failure rather than silently "
            "serving the request via the native LLM. "
            "When True (default): (a) startup CRASHES if "
            "AGENT_A2A_AGENT_URL is not set; (b) at request time, a "
            "missing/unreachable adapter raises HTTP 503 to the caller "
            "instead of falling back to the native LLM. "
            "Native fallback is reserved for genuine A2A failures only "
            "(circuit breaker open, rate limits, transport errors at "
            "request time) — see a2a_fallback_to_native. "
            "Set False ONLY if you intentionally want chat to silently "
            "spend on direct provider API calls when the adapter is "
            "misconfigured. "
            "Env: AGENT_A2A_CHAT_STRICT"
        ),
    )

    a2a_context_reuse: bool = Field(
        default=True,
        description="Reuse A2A context identifiers across turns",
    )

    a2a_backend: Literal["copilot", "claude-code", "codex"] = Field(
        default="copilot",
        description=(
            "Which A2A backend the adapter uses when inner_loop_mode is 'a2a'. "
            "copilot: GitHub Copilot CLI (uses GITHUB_TOKEN or GH_TOKEN, falls back to 'gh auth'). "
            "claude-code: Anthropic Claude Code CLI (requires ANTHROPIC_API_KEY; claude-* models only). "
            "codex: OpenAI Codex CLI (requires OPENAI_API_KEY; o4-mini/o3 models only). "
            "Env: AGENT_A2A_BACKEND"
        ),
    )

    # ------------------------------------------------------------------
    # A2A billing strategy
    # ------------------------------------------------------------------
    a2a_billing_strategy: Literal["token_based", "provider_reported", "none"] = Field(
        default="token_based",
        description=(
            "How to bill users when the A2A backend serves a turn. "
            "'token_based': apply the same PricingInfo × token-count calculation "
            "as native execution (default — safe, may overcharge on subsidised "
            "backends like Copilot Business). "
            "'provider_reported': use the cost/premium-request data reported by "
            "the backend (decouples ii-agent billing from API list prices). "
            "'none': skip LLM billing entirely for A2A-served turns (useful when "
            "the subscription fully covers inference cost). "
            "Env: AGENT_A2A_BILLING_STRATEGY"
        ),
    )

    a2a_billing_multiplier: float = Field(
        default=1.0,
        description=(
            "Flat multiplier applied to the calculated credit cost when "
            "a2a_billing_strategy is 'token_based'. Values <1.0 reduce the "
            "charge to reflect subsidised backends (e.g. 0.0 for Copilot "
            "Business unlimited). "
            "Env: AGENT_A2A_BILLING_MULTIPLIER"
        ),
        ge=0.0,
    )

    a2a_copilot_premium_request_cost: float = Field(
        default=0.04,
        description=(
            "USD cost per premium request when a2a_billing_strategy is "
            "'provider_reported' and the backend is Copilot. Default $0.04 "
            "matches GitHub's overage price (April 2026). "
            "Env: AGENT_A2A_COPILOT_PREMIUM_REQUEST_COST"
        ),
        ge=0.0,
    )

    a2a_copilot_multipliers: Dict[str, float] = Field(
        default_factory=lambda: dict(_DEFAULT_COPILOT_MULTIPLIERS),
        description=(
            "Model-id prefix → premium-request multiplier mapping for Copilot "
            "billing. Only used when a2a_billing_strategy is 'provider_reported'. "
            "Updated without code changes via AGENT_A2A_COPILOT_MULTIPLIERS env "
            "(JSON object). "
            "Env: AGENT_A2A_COPILOT_MULTIPLIERS"
        ),
    )

    def is_tool_allowed(self, tool_name: str) -> bool:
        """Check if a tool is allowed to execute without confirmation.

        Args:
            tool_name: Name of the tool to check

        Returns:
            bool: True if tool is auto-approved or in allow list
        """
        return self.auto_approve_tools or tool_name in self.allow_tools

    def add_allowed_tool(self, tool_name: str) -> None:
        """Add a tool to the allowed tools set.

        Args:
            tool_name: Name of the tool to allow
        """
        self.allow_tools.add(tool_name)

    def remove_allowed_tool(self, tool_name: str) -> None:
        """Remove a tool from the allowed tools set.

        Args:
            tool_name: Name of the tool to remove
        """
        self.allow_tools.discard(tool_name)

    def clear_allowed_tools(self) -> None:
        """Clear all allowed tools."""
        self.allow_tools.clear()
