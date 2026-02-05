"""
Skill Registry: Discovers and instantiates skill tools for the agent framework.

This module bridges ii_skills discovery with ii_agent tool registration.
It imports ii_skills, triggers auto-discovery, and wraps each registered
skill as a SkillTool that the AgentToolManager can use.

Usage:
    from ii_skills.bridge import get_skill_tools
    tools = get_skill_tools()  # Returns list of SkillTool instances
"""

import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


def get_skill_tools(
    config: Optional[Dict] = None,
    workspace_path: Optional[str] = None,
    include: Optional[List[str]] = None,
    exclude: Optional[List[str]] = None,
) -> list:
    """Get all registered skills as SkillTool instances.

    This is the main entry point for agent_service.py to get skill tools.
    It triggers skill discovery, instantiates each skill, and wraps it
    as a SkillTool.

    Args:
        config: Optional config dict passed to each skill
        workspace_path: Optional workspace path for output file handling
        include: If set, only include these skill names
        exclude: If set, exclude these skill names

    Returns:
        List of SkillTool instances ready for AgentToolManager.register_tools()
    """
    from .skill_tool import SkillTool

    try:
        # Import ii_skills triggers discover_skills() automatically
        import ii_skills
        from ii_skills import _SKILLS, get_skill
    except ImportError as e:
        logger.error(f"Failed to import ii_skills: {e}")
        return []

    tools = []
    skill_names = list(_SKILLS.keys())

    for skill_name in skill_names:
        # Apply include/exclude filters
        if include and skill_name not in include:
            continue
        if exclude and skill_name in exclude:
            continue

        try:
            # Get skill instance
            skill = get_skill(skill_name, config)
            if skill is None:
                logger.warning(f"Skill '{skill_name}' returned None from get_skill()")
                continue

            # Validate config (non-blocking — just log warnings)
            issues = skill.validate_config()
            if issues:
                logger.warning(
                    f"Skill '{skill_name}' has config issues: {issues}"
                )

            # Initialize
            skill.initialize()

            # Wrap as SkillTool
            tool = SkillTool(skill, workspace_path=workspace_path)
            tools.append(tool)
            logger.info(
                f"Registered skill tool: {tool.name} "
                f"({len(skill.get_capabilities())} actions)"
            )

        except Exception as e:
            logger.error(
                f"Failed to create SkillTool for '{skill_name}': {e}",
                exc_info=True,
            )

    logger.info(f"Loaded {len(tools)} skill tools: {[t.name for t in tools]}")
    return tools


def get_skill_tool(
    skill_name: str,
    config: Optional[Dict] = None,
    workspace_path: Optional[str] = None,
) -> Optional["SkillTool"]:
    """Get a single skill as a SkillTool by name.

    Args:
        skill_name: Name of the skill (e.g., 'ib_toolkit')
        config: Optional config dict
        workspace_path: Optional workspace path

    Returns:
        SkillTool instance or None if skill not found
    """
    tools = get_skill_tools(
        config=config,
        workspace_path=workspace_path,
        include=[skill_name],
    )
    return tools[0] if tools else None


def list_available_skills() -> List[Dict]:
    """List all registered skills with their metadata.

    Returns:
        List of dicts with skill name, version, description, capabilities
    """
    try:
        import ii_skills
        from ii_skills import list_skills, _SKILLS, get_skill
    except ImportError:
        return []

    result = []
    for skill_info in list_skills():
        name = skill_info["name"]
        skill = get_skill(name)
        if skill:
            result.append({
                **skill_info,
                "capabilities": skill.get_capabilities(),
                "capability_count": len(skill.get_capabilities()),
                "is_ready": skill.is_ready,
                "config_issues": skill.validate_config(),
            })

    return result
