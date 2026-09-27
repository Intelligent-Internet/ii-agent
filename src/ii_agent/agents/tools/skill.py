"""Skill tool for loading and activating skills in sandbox."""

from typing import TYPE_CHECKING, Any, Optional

from ii_agent.agents.tools.base import ToolResult
from ii_agent.agents.tools.sandbox.base import BaseSandboxTool
from ii_agent.agents.skills.storage import copy_skill_to_sandbox, skill_exists
from ii_agent.core.logger import logger

if TYPE_CHECKING:
    from ii_agent.settings.skills.models import Skill
    from ii_agent.core.storage.service import StorageService as BaseStorage
    from ii_agent.agents.agent import IIAgent
    from ii_agent.agents.tools.function import FunctionCall

INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "skill": {
            "type": "string",
            "description": "REQUIRED. Name of the skill to activate, e.g. 'pdf' or 'xlsx'.",
        },
    },
    "required": ["skill"],
}

# Sandbox path for skills
SANDBOX_SKILLS_PATH = "/workspace/.skills"


class SkillTool(BaseSandboxTool):
    """Tool for loading and activating skills.

    This tool loads entire skill directories (SKILL.md + scripts/ + references/ + assets/)
    into the sandbox when invoked. The description is dynamically generated per-user
    to show their available skills.
    """

    name: str = "Skill"
    display_name: str = "Skill"
    input_schema = INPUT_SCHEMA
    read_only: bool = True

    def __init__(
        self,
        description: str,
        skills_registry: Optional[dict[str, "Skill"]] = None,
        storage: Optional["BaseStorage"] = None,
    ):
        """Initialize SkillTool.

        Args:
            description: Tool description with available skills XML
            skills_registry: Mapping of skill_name -> Skill DB model for lookup
                Contains storage_uri for each skill to locate skill files.
            storage: GCS storage client for loading custom skills from cloud storage.
                Required when using skills with storage_uri starting with "skills/".
        """
        self.description = description
        self._skills_registry = skills_registry or {}
        self._storage = storage
        self._agent: Optional["IIAgent"] = None

    async def on_tool_start(self, agent: "IIAgent", fc: "FunctionCall") -> None:
        """Store agent reference and initialize sandbox.

        Args:
            agent: The IIAgent instance executing the tool
            fc: The FunctionCall instance with arguments
        """
        await super().on_tool_start(agent, fc)
        self._agent = agent

    async def execute(self, tool_input: dict[str, Any]) -> ToolResult:
        """Execute skill activation.

        Copies the entire skill directory to sandbox at /workspace/.skills/{skill_name}/
        This includes:
        - SKILL.md (main instructions)
        - scripts/ (executable code)
        - references/ (additional docs)
        - assets/ (templates, images)

        Args:
            tool_input: Dict with "skill" key containing skill name

        Returns:
            ToolResult with skill content and activation status
        """
        skill_name = tool_input.get("skill", "").strip().lower()
        logger.info("[SkillTool] Activating skill: {}", skill_name)

        if not skill_name:
            available = (
                ", ".join(sorted(self._skills_registry.keys()))
                if self._skills_registry
                else "(none loaded)"
            )
            logger.error("[SkillTool] No skill name provided. Available: {}", available)
            return ToolResult(
                llm_content=(
                    'Error: No skill name provided. You MUST pass the "skill" argument. '
                    'Call this tool with arguments like {"skill": "agent-browser"} or '
                    '{"skill": "pdf"}. '
                    f"Available skills: {available}"
                ),
                user_display_content="No skill name provided",
                is_error=True,
            )

        # Check if skill exists in our registry
        if skill_name not in self._skills_registry:
            available = ", ".join(sorted(self._skills_registry.keys()))
            logger.error(
                f"[SkillTool] Skill '{skill_name}' not in registry. Available: {available}"
            )
            return ToolResult(
                llm_content=f"Error: Skill '{skill_name}' not found. Available skills: {available}",
                user_display_content=f"Skill '{skill_name}' not found",
                is_error=True,
            )

        skill = self._skills_registry[skill_name]
        logger.info(
            f"[SkillTool] Found skill in registry: {skill_name}, storage_uri={skill.storage_uri}, source={skill.source}"
        )

        try:
            # Get sandbox from agent (set by on_tool_start)
            if self._agent is None:
                logger.error("[SkillTool] Agent not initialized")
                return ToolResult(
                    llm_content="Error: Agent not initialized. Cannot load skill.",
                    user_display_content="Agent not available",
                    is_error=True,
                )

            sandbox = self._agent.sandbox

            if sandbox is None:
                logger.error("[SkillTool] Sandbox not initialized")
                return ToolResult(
                    llm_content="Error: Sandbox not initialized. Cannot load skill.",
                    user_display_content="Sandbox not available",
                    is_error=True,
                )

            # Check if skill exists (directory, zip, or in GCS)
            logger.info(
                f"[SkillTool] Checking if skill exists at {skill.storage_uri}, storage={'available' if self._storage else 'None'}"
            )
            if not await skill_exists(skill.storage_uri, storage=self._storage):
                logger.error(f"[SkillTool] Skill not found at {skill.storage_uri}")
                return ToolResult(
                    llm_content=f"Error: Skill not found at {skill.storage_uri}",
                    user_display_content=f"Skill files not found: {skill_name}",
                    is_error=True,
                )

            # Copy skill to sandbox (handles builtin, GCS, and local paths)
            logger.info(
                f"[SkillTool] Copying skill to sandbox: {skill_name} from {skill.storage_uri}"
            )
            sandbox_skill_dir = await copy_skill_to_sandbox(
                storage_uri=skill.storage_uri,
                skill_name=skill_name,
                sandbox=sandbox,
                sandbox_base_path=SANDBOX_SKILLS_PATH,
                storage=self._storage,
            )
            logger.info(f"[SkillTool] Successfully copied skill to {sandbox_skill_dir}")

            # Get SKILL.md content from DB (fast - no storage I/O)
            # This is the key optimization: skill_md_content is already in DB
            skill_md_content = skill.skill_md_content

            logger.info(f"Activated skill '{skill_name}': extracted files to {sandbox_skill_dir}")

            # Return the skill content for the LLM to use
            return ToolResult(
                llm_content=f'<command-message>The "{skill_name}" skill is loading</command-message>\n\nBase directory for this skill: {sandbox_skill_dir}\n\n{skill_md_content}',
                user_display_content=f"Activated skill: {skill_name}",
                is_error=False,
            )

        except Exception as e:
            logger.error(f"Failed to load skill '{skill_name}': {e}")
            return ToolResult(
                llm_content=f"Error loading skill '{skill_name}': {str(e)}",
                user_display_content=f"Failed to load skill: {skill_name}",
                is_error=True,
            )
