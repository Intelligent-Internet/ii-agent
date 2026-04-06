from typing import Any, Dict, List, Optional

from pydantic import BaseModel

from ii_agent.realtime.schemas import QueryCommandContent


class CoworkAgentConfig(BaseModel):
    """Runtime overrides for cowork-specific IIAgent creation."""

    name: Optional[str] = None
    description: Optional[str] = None
    additional_context: Optional[str] = None
    retries: Optional[int] = None
    delay_between_retries: Optional[int] = None
    exponential_backoff: Optional[bool] = None
    stream: Optional[bool] = None
    stream_events: Optional[bool] = None
    store_events: Optional[bool] = None
    tool_call_limit: Optional[int] = None
    tool_choice: Optional[Any] = None
    delegate_to_all_members: Optional[bool] = None
    stream_member_events: Optional[bool] = None
    store_member_responses: Optional[bool] = None
    role: Optional[str] = None


class DesktopCapabilityToolDescriptor(BaseModel):
    """Desktop tool descriptor sent by the desktop runtime."""

    name: str
    aliases: List[str] = []
    display_name: Optional[str] = None
    description: str
    input_schema: Dict[str, Any] = {}


class DesktopCapabilitySkillDescriptor(BaseModel):
    """Desktop skill descriptor sent by the desktop runtime."""

    name: str
    description: str


class DesktopCapabilitiesContent(BaseModel):
    """Desktop tool and skill catalog sent with cowork requests."""

    tools: List[DesktopCapabilityToolDescriptor] = []
    skills: List[DesktopCapabilitySkillDescriptor] = []


class CoworkQueryCommandContent(QueryCommandContent):
    """Extended query contract for cowork-specific agent overrides."""

    system_prompt: Optional[str] = None
    tool_names: Optional[List[str]] = None
    skill_names: Optional[List[str]] = None
    agent_config: Optional[CoworkAgentConfig] = None
    desktop_capabilities: Optional[DesktopCapabilitiesContent] = None
