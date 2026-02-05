"""
SkillTool: Wraps a BaseSkill as a BaseTool for the ii_agent framework.

This is the core bridge between ii_skills and ii_agent. Each SkillTool:
1. Takes a BaseSkill instance
2. Exposes it as a BaseTool with proper name, description, and input_schema
3. Routes tool_input to skill.execute(action, **params)
4. Returns ToolResult compatible with AgentToolManager
"""

import json
import logging
import traceback
from typing import Any, Dict, Optional

from ii_tool.tools.base import BaseTool, ToolResult

logger = logging.getLogger(__name__)


class SkillTool(BaseTool):
    """Wraps a BaseSkill instance as a BaseTool for LLM agent use.

    The LLM sees this as a single tool (e.g., "skill_ib_toolkit") and
    can call it with an action name and parameters. The SkillTool
    dispatches to the underlying skill's execute() method.

    Example LLM tool call:
        {
            "name": "skill_ib_toolkit",
            "input": {
                "action": "quick_lbo_analysis",
                "params": {
                    "ebitda": 50,
                    "entry_multiple": 8.0,
                    "exit_multiple": 9.0
                }
            }
        }
    """

    def __init__(self, skill, workspace_path: Optional[str] = None):
        """Initialize SkillTool from a BaseSkill instance.

        Args:
            skill: A BaseSkill instance (from ii_skills)
            workspace_path: Optional path to copy output files to
        """
        from ii_skills import BaseSkill

        if not isinstance(skill, BaseSkill):
            raise TypeError(f"Expected BaseSkill, got {type(skill).__name__}")

        self._skill = skill
        self._workspace_path = workspace_path

        # BaseTool interface
        self.name = f"skill_{skill.name}"
        self.display_name = f"Skill: {skill.name}"
        self.read_only = False
        self.metadata = None

        # Build description with available actions
        capabilities = skill.get_capabilities()
        cap_list = ", ".join(capabilities) if capabilities else "none"
        self.description = (
            f"{skill.description}\n\n"
            f"Available actions: {cap_list}\n\n"
            f"Call with an 'action' from the list above and 'params' object "
            f"containing the action's parameters."
        )

        # Build input schema
        self.input_schema = self._build_input_schema(capabilities)

    def _build_input_schema(self, capabilities: list) -> Dict[str, Any]:
        """Build JSON Schema for the tool's input.

        Creates a schema that the LLM can use to construct valid tool calls.
        The schema requires an 'action' string (from the skill's capabilities)
        and an optional 'params' object.
        """
        schema: Dict[str, Any] = {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "description": (
                        "The skill action to execute. "
                        "Must be one of the available actions."
                    ),
                },
                "params": {
                    "type": "object",
                    "description": (
                        "Parameters for the action. "
                        "Each action accepts different parameters. "
                        "Pass as key-value pairs."
                    ),
                    "additionalProperties": True,
                },
            },
            "required": ["action"],
        }

        # Add enum constraint if capabilities are known
        if capabilities:
            schema["properties"]["action"]["enum"] = capabilities

        return schema

    async def execute(self, tool_input: Dict[str, Any]) -> ToolResult:
        """Execute the skill action.

        Args:
            tool_input: Dict with 'action' (str) and optional 'params' (dict)

        Returns:
            ToolResult with the skill's output as JSON
        """
        action = tool_input.get("action")
        params = tool_input.get("params", {})

        if not action:
            return ToolResult(
                llm_content="Error: 'action' is required. "
                f"Available actions: {', '.join(self._skill.get_capabilities())}",
                is_error=True,
            )

        # Validate action exists
        capabilities = self._skill.get_capabilities()
        if capabilities and action not in capabilities:
            return ToolResult(
                llm_content=(
                    f"Error: Unknown action '{action}'. "
                    f"Available actions: {', '.join(capabilities)}"
                ),
                is_error=True,
            )

        logger.info(
            f"Executing skill '{self._skill.name}' action '{action}' "
            f"with params: {list(params.keys())}"
        )

        try:
            # Initialize skill if needed
            if not self._skill._initialized:
                self._skill.initialize()

            # Execute the action
            result = self._skill.execute(action, **params)

            # Format result for LLM
            result_json = json.dumps(result, indent=2, default=str)

            # Build user display content
            display_content = {
                "skill": self._skill.name,
                "action": action,
                "result": result,
            }

            # If result contains an output_path, note it for the user
            if isinstance(result, dict) and result.get("output_path"):
                output_path = result["output_path"]
                logger.info(f"Skill output file: {output_path}")
                display_content["output_file"] = output_path

            return ToolResult(
                llm_content=result_json,
                user_display_content=display_content,
            )

        except NotImplementedError as e:
            logger.warning(f"Skill action not implemented: {e}")
            return ToolResult(
                llm_content=f"Error: Action '{action}' is not implemented. {str(e)}",
                is_error=True,
            )

        except Exception as e:
            error_msg = f"Skill execution failed: {type(e).__name__}: {str(e)}"
            logger.error(f"{error_msg}\n{traceback.format_exc()}")
            return ToolResult(
                llm_content=error_msg,
                is_error=True,
            )

    def should_confirm_execute(self, tool_input: Dict[str, Any]) -> bool:
        """Skills don't require confirmation (they don't modify system state)."""
        return False
