"""CLI-specific configuration settings."""

from pydantic import BaseModel, Field


class CliConfig(BaseModel):
    """Configuration for CLI behavior and user experience settings."""
    
    enable_arrow_navigation: bool = Field(
        default=True,
        description="Enable arrow key navigation in tool confirmation dialogs and other selections"
    )
    
    show_typing_indicator: bool = Field(
        default=True,
        description="Show typing indicator when the agent is thinking"
    )
    
    use_rich_formatting: bool = Field(
        default=True,
        description="Enable rich text formatting and colors in output"
    )
    
    max_history_entries: int = Field(
        default=1000,
        description="Maximum number of command history entries to keep",
        ge=100,
        le=10000
    )
    
    auto_save_session: bool = Field(
        default=True,
        description="Automatically save session state and history"
    )
    
    confirmation_timeout: int = Field(
        default=300,  # 5 minutes
        description="Timeout in seconds for tool confirmation dialogs (0 for no timeout)",
        ge=0
    )