"""Agent execution configuration."""

from typing import Literal, Set
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Constants
MAX_OUTPUT_TOKENS_PER_TURN = 32000
MAX_TURNS = 200
TOKEN_BUDGET = 128000  # Default token budget


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
