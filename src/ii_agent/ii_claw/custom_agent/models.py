"""User agents settings Pydantic models."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class UserAgentCreate(BaseModel):
    """Request to create a custom agent."""

    agent_name: str = Field(
        ...,
        max_length=128,
        description="Display name for the agent (unique per user)",
    )
    tag: Optional[str] = Field(None, max_length=64, description="Short tag/label for the agent")
    model_id: Optional[str] = Field(
        None,
        description="Model override (e.g. 'claude-sonnet-4-20250514'). NULL uses session default",
    )
    system_prompt: Optional[str] = Field(None, description="Custom system prompt")
    tool_args: Optional[Dict[str, Any]] = Field(
        None,
        description="Tool toggles, e.g. {'media_generation': false, 'browser': true}",
    )
    skill_mode: Optional[str] = Field(
        "default",
        description="Skill mode: 'default', 'custom_skill', 'default_and_custom_skill', or null",
    )
    connector_mode: Optional[str] = Field(
        "default",
        description="Connector mode: 'default', 'custom_connector', 'default_and_custom_connector', or null",
    )
    skill_config: Optional[Dict[str, Any]] = Field(
        None, description="Custom skill config (e.g. skill IDs, params)"
    )
    connector_config: Optional[Dict[str, Any]] = Field(
        None, description="Custom connector config (e.g. connector IDs, params)"
    )
    metadata: Optional[Dict[str, Any]] = Field(
        None, description="Arbitrary metadata"
    )


class UserAgentUpdate(BaseModel):
    """Request to update a custom agent. All fields optional for partial update."""

    agent_name: Optional[str] = Field(None, max_length=128, description="New display name")
    tag: Optional[str] = Field(None, max_length=64, description="Short tag/label for the agent")
    model_id: Optional[str] = Field(None, description="Model override")
    system_prompt: Optional[str] = Field(None, description="Custom system prompt")
    tool_args: Optional[Dict[str, Any]] = Field(None, description="Tool toggles")
    skill_mode: Optional[str] = Field(None, description="Skill mode")
    connector_mode: Optional[str] = Field(None, description="Connector mode")
    skill_config: Optional[Dict[str, Any]] = Field(None, description="Custom skill config")
    connector_config: Optional[Dict[str, Any]] = Field(None, description="Custom connector config")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Arbitrary metadata")
    is_active: Optional[bool] = Field(None, description="Enable/disable the agent")


class UserAgentInfo(BaseModel):
    """User agent response."""

    id: str = Field(..., description="Unique agent ID")
    agent_name: str = Field(..., description="Display name")
    tag: Optional[str] = Field(None, max_length=64, description="Short tag/label for the agent")
    model_id: Optional[str] = Field(None, description="Model override")
    system_prompt: Optional[str] = Field(None, description="Custom system prompt")
    tool_args: Optional[Dict[str, Any]] = Field(None, description="Tool toggles")
    skill_mode: Optional[str] = Field(None, description="Skill mode")
    connector_mode: Optional[str] = Field(None, description="Connector mode")
    skill_config: Optional[Dict[str, Any]] = Field(None, description="Custom skill config")
    connector_config: Optional[Dict[str, Any]] = Field(None, description="Custom connector config")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Arbitrary metadata")
    is_active: bool = Field(..., description="Whether the agent is active")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: Optional[datetime] = Field(None, description="Last update timestamp")

    model_config = ConfigDict(from_attributes=True)


class UserAgentList(BaseModel):
    """List of user agents response."""

    agents: List[UserAgentInfo] = Field(..., description="List of agents")
    total: int = Field(..., description="Total count")


class UserAgentDeleteResponse(BaseModel):
    """Response for agent deletion."""

    success: bool = Field(..., description="Whether deletion was successful")
    message: str = Field(..., description="Status message")
