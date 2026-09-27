"""Generate <available_skills> XML from database records."""

import html
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ii_agent.settings.skills.models import Skill


def to_prompt_from_db(skills: list["Skill"]) -> str:
    """Generate <available_skills> XML from database Skill records.

    Uses ONLY metadata fields (name, description, sandbox_path).
    Does NOT include skill_md_content - that's returned via ToolResult
    when the skill is actually activated.

    Args:
        skills: List of Skill database records

    Returns:
        XML string with <available_skills> block (~50 tokens per skill)

    Example output:
        <available_skills>
        <skill>
        <name>pdf</name>
        <description>Comprehensive PDF manipulation toolkit...</description>
        <location>/workspace/.skills/pdf</location>
        </skill>
        </available_skills>
    """
    if not skills:
        return "<available_skills>\n</available_skills>"

    lines = ["<available_skills>"]

    for skill in skills:
        if not skill.is_enabled:
            continue

        lines.append("<skill>")
        lines.append("<name>")
        lines.append(html.escape(skill.name))
        lines.append("</name>")
        lines.append("<description>")
        lines.append(html.escape(skill.description))
        lines.append("</description>")
        lines.append("<location>")
        lines.append(html.escape(skill.sandbox_path))
        lines.append("</location>")
        lines.append("</skill>")

    lines.append("</available_skills>")

    return "\n".join(lines)


def generate_skill_tool_description(skills: list["Skill"]) -> str:
    """Generate the full description for SkillTool including instructions.

    Args:
        skills: List of Skill database records

    Returns:
        Complete tool description string
    """
    available_skills_xml = to_prompt_from_db(skills)

    description = f"""Execute a skill within the main conversation

<skills_instructions>
When users ask you to perform tasks, check if any of the available skills below can help complete the task more effectively. Skills provide specialized capabilities and domain knowledge.

How to use skills:
- Invoke this tool by passing a skill name in the required "skill" parameter
- When you invoke a skill, you will see <command-message>The "{{name}}" skill is loading</command-message>
- The skill's prompt will expand and provide detailed instructions on how to complete the task
- Examples:
  - `skill: "pdf"` - invoke the pdf skill
  - `skill: "xlsx"` - invoke the xlsx skill

Important:
- Only use skills listed in <available_skills> below
- Do not invoke a skill that is already running
</skills_instructions>

{available_skills_xml}
"""
    return description
