"""
II-Skills Bridge Layer

Connects ii_skills (domain logic) to ii_agent (LLM orchestration)
by wrapping BaseSkill instances as BaseTool instances that the
AgentToolManager can register and dispatch to.

Usage in agent_service.py:
    from ii_skills.bridge import get_skill_tools
    skill_tools = get_skill_tools()
    tool_manager.register_tools(skill_tools)
"""

from .skill_tool import SkillTool
from .skill_registry import get_skill_tools, get_skill_tool, list_available_skills

__all__ = [
    "SkillTool",
    "get_skill_tools",
    "get_skill_tool",
    "list_available_skills",
]
