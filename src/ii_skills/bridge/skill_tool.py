"""
SkillTool: Wraps a BaseSkill as a BaseTool for the ii_agent framework.

This is the core bridge between ii_skills and ii_agent. Each SkillTool:
1. Takes a BaseSkill instance
2. Resolves its SkillManifest for rich action schemas
3. Exposes it as a BaseTool with manifest-enriched description and input_schema
4. Routes tool_input to skill.execute(action, **params) with optional workspace
5. Validates params against ActionSchema before dispatch
6. Gates DESTRUCTIVE actions with should_confirm_execute()
7. Returns ToolResult compatible with AgentToolManager
"""

import json
import logging
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from ii_tool.tools.base import BaseTool, ToolResult

logger = logging.getLogger(__name__)


class SkillTool(BaseTool):
    """Wraps a BaseSkill instance as a BaseTool for LLM agent use.

    The LLM sees this as a single tool (e.g., "skill_ib_toolkit") and
    can call it with an action name and parameters. The SkillTool
    dispatches to the underlying skill's execute() method.

    Enhanced with:
    - Manifest-aware descriptions (per-action parameter documentation)
    - Risk-based confirmation gating (DESTRUCTIVE actions prompt user)
    - Lightweight param validation before dispatch
    - Workspace integration (auto-creates workspace per execution)
    - Action tracking (count, last action, timestamps)

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

    def __init__(
        self,
        skill,
        workspace_path: Optional[str] = None,
        workspace_manager=None,
    ):
        """Initialize SkillTool from a BaseSkill instance.

        Args:
            skill: A BaseSkill instance (from ii_skills)
            workspace_path: Optional path to copy output files to
            workspace_manager: Optional WorkspaceManager for per-execution workspaces
        """
        from ii_skills import BaseSkill

        if not isinstance(skill, BaseSkill):
            raise TypeError(f"Expected BaseSkill, got {type(skill).__name__}")

        self._skill = skill
        self._workspace_path = workspace_path
        self._workspace_manager = workspace_manager

        # Resolve manifest (structured or auto-generated)
        self._manifest = self._resolve_manifest()

        # BaseTool interface
        self.name = f"skill_{skill.name}"
        self.display_name = f"Skill: {skill.name}"
        self.read_only = False
        self.metadata = None

        # Build enriched description using manifest
        self.description = self._build_description()

        # Build input schema using manifest
        self.input_schema = self._build_input_schema_from_manifest()

    def _resolve_manifest(self):
        """Resolve the skill's manifest, with fallback to auto-generation.

        Returns:
            SkillManifest instance
        """
        from ii_skills.shared.skill_manifest import SkillManifest

        try:
            manifest = self._skill.get_manifest()
            if manifest is not None:
                return manifest
        except Exception as e:
            logger.debug(
                f"get_manifest() failed for {self._skill.name}, "
                f"falling back to auto-generation: {e}"
            )

        return SkillManifest.from_capabilities(self._skill)

    def _build_description(self) -> str:
        """Build enriched tool description using manifest.

        If the manifest has rich action schemas with parameter docs,
        include them. Otherwise fall back to simple capability listing.
        """
        parts = [self._manifest.description or self._skill.description]

        # Add per-action documentation
        action_docs = self._manifest.build_action_docs()
        if action_docs and action_docs != "No actions available.":
            parts.append(f"\nAvailable actions:\n{action_docs}")
        else:
            # Fallback to simple listing
            capabilities = self._skill.get_capabilities()
            cap_list = ", ".join(capabilities) if capabilities else "none"
            parts.append(f"\nAvailable actions: {cap_list}")

        parts.append(
            "\nCall with an 'action' from the list above and 'params' object "
            "containing the action's parameters."
        )

        return "\n".join(parts)

    def _build_input_schema_from_manifest(self) -> Dict[str, Any]:
        """Build JSON Schema enriched with manifest action info.

        Creates a schema that the LLM can use to construct valid tool calls.
        Action enum is populated from manifest. Parameter descriptions
        are enriched when ActionSchema has typed input_schema.
        """
        action_names = self._manifest.get_action_names()

        # Build per-action parameter descriptions for the params field
        param_descriptions = []
        for name in action_names:
            action_schema = self._manifest.get_action(name)
            if action_schema:
                props = action_schema.input_schema.get("properties", {})
                if props:
                    param_list = ", ".join(props.keys())
                    param_descriptions.append(f"  {name}: {param_list}")

        params_desc = (
            "Parameters for the action. Each action accepts different parameters. "
            "Pass as key-value pairs."
        )
        if param_descriptions:
            params_desc += "\n\nAction parameters:\n" + "\n".join(param_descriptions)

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
                    "description": params_desc,
                    "additionalProperties": True,
                },
            },
            "required": ["action"],
        }

        # Add enum constraint if actions are known
        if action_names:
            schema["properties"]["action"]["enum"] = action_names

        return schema

    def _validate_params(
        self, action: str, params: Dict[str, Any]
    ) -> Optional[str]:
        """Lightweight param validation against ActionSchema.

        Checks required fields and basic type matching. Returns None
        if valid, or an error message string if invalid.
        """
        action_schema = self._manifest.get_action(action)
        if not action_schema:
            return None  # No schema to validate against

        input_schema = action_schema.input_schema
        if not input_schema or not input_schema.get("properties"):
            return None  # Open schema, anything goes

        # Check required fields
        required = input_schema.get("required", [])
        missing = [r for r in required if r not in params]
        if missing:
            return (
                f"Missing required parameter(s) for '{action}': "
                f"{', '.join(missing)}"
            )

        # Basic type checking
        properties = input_schema.get("properties", {})
        type_map = {
            "string": str,
            "number": (int, float),
            "integer": int,
            "boolean": bool,
            "array": list,
            "object": dict,
        }

        errors = []
        for param_name, param_value in params.items():
            if param_name in properties:
                expected_type_str = properties[param_name].get("type")
                if expected_type_str and expected_type_str in type_map:
                    expected_type = type_map[expected_type_str]
                    if not isinstance(param_value, expected_type):
                        errors.append(
                            f"'{param_name}' should be {expected_type_str}, "
                            f"got {type(param_value).__name__}"
                        )

        if errors:
            return f"Parameter validation errors for '{action}': " + "; ".join(errors)

        return None

    async def execute(self, tool_input: Dict[str, Any]) -> ToolResult:
        """Execute the skill action with optional workspace.

        Args:
            tool_input: Dict with 'action' (str) and optional 'params' (dict)

        Returns:
            ToolResult with the skill's output as JSON
        """
        action = tool_input.get("action")
        params = tool_input.get("params", {})

        if not action:
            action_names = self._manifest.get_action_names()
            return ToolResult(
                llm_content="Error: 'action' is required. "
                f"Available actions: {', '.join(action_names)}",
                is_error=True,
            )

        # Validate action exists
        action_names = self._manifest.get_action_names()
        if action_names and action not in action_names:
            return ToolResult(
                llm_content=(
                    f"Error: Unknown action '{action}'. "
                    f"Available actions: {', '.join(action_names)}"
                ),
                is_error=True,
            )

        # Validate params against schema
        validation_error = self._validate_params(action, params)
        if validation_error:
            return ToolResult(
                llm_content=f"Error: {validation_error}",
                is_error=True,
            )

        logger.info(
            f"Executing skill '{self._skill.name}' action '{action}' "
            f"with params: {list(params.keys())}"
        )

        # Determine if we should use a workspace
        use_workspace = self._workspace_manager is not None
        workspace = None

        try:
            # Initialize skill if needed
            if not self._skill._initialized:
                self._skill.initialize()

            if use_workspace:
                return await self._execute_with_workspace(action, params)
            else:
                return await self._execute_direct(action, params)

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

    async def _execute_direct(
        self, action: str, params: Dict[str, Any]
    ) -> ToolResult:
        """Execute without workspace (original behavior)."""
        result = self._skill.execute(action, **params)

        # Track action on skill
        self._track_action(action)

        return self._format_result(action, result)

    async def _execute_with_workspace(
        self, action: str, params: Dict[str, Any]
    ) -> ToolResult:
        """Execute within a workspace context."""
        import time

        with self._workspace_manager.create(
            skill_name=self._skill.name,
            action=action,
            params=params,
        ) as workspace:
            # Log tool call start to workspace events for session capture
            workspace.log_event("tool_call_start", {
                "sequence_index": self._skill._action_count,
                "tool_name": f"skill_{self._skill.name}",
                "action": action,
                "params": params,
            })

            start_time = time.monotonic()

            # Inject workspace as underscore-prefixed kwarg
            result = self._skill.execute(action, _workspace=workspace, **params)

            duration_ms = (time.monotonic() - start_time) * 1000

            # Track action on skill
            self._track_action(action)

            # Log tool call completion
            workspace.log_event("tool_call_complete", {
                "sequence_index": self._skill._action_count - 1,
                "tool_name": f"skill_{self._skill.name}",
                "action": action,
                "duration_ms": round(duration_ms, 2),
                "is_error": False,
            })

            # Auto-detect and register output artifacts
            if isinstance(result, dict):
                self._auto_register_artifacts(result, workspace)

                # Add workspace info to result
                result["_workspace_id"] = workspace.run_id
                result["_workspace_path"] = str(workspace.workspace_dir)

            return self._format_result(action, result)

    def _track_action(self, action: str) -> None:
        """Update action tracking on the skill instance."""
        self._skill._action_count += 1
        self._skill._last_action = action
        self._skill._last_action_at = datetime.now(timezone.utc).isoformat()

    def _auto_register_artifacts(self, result: Dict[str, Any], workspace) -> None:
        """Auto-detect output files in result and register as artifacts."""
        # Check common output path keys
        path_keys = ["output_path", "file_path", "excel_path", "slide_path"]
        for key in path_keys:
            path_value = result.get(key)
            if path_value and Path(path_value).exists():
                try:
                    workspace.register_artifact(path_value)
                except Exception as e:
                    logger.debug(f"Failed to register artifact for {key}: {e}")

        # Check for list of output paths
        output_paths = result.get("output_paths", [])
        if isinstance(output_paths, list):
            for path_value in output_paths:
                if path_value and Path(str(path_value)).exists():
                    try:
                        workspace.register_artifact(str(path_value))
                    except Exception as e:
                        logger.debug(f"Failed to register artifact: {e}")

    def _format_result(
        self, action: str, result: Any
    ) -> ToolResult:
        """Format skill result as ToolResult."""
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

    def should_confirm_execute(self, tool_input: Dict[str, Any]) -> bool:
        """Check if the action requires user confirmation.

        DESTRUCTIVE actions (from manifest risk_level) trigger confirmation.
        READ_ONLY and WRITE actions proceed without confirmation.
        """
        from ii_skills.shared.skill_manifest import RiskLevel

        action = tool_input.get("action", "")
        action_schema = self._manifest.get_action(action)

        if action_schema and action_schema.risk_level == RiskLevel.DESTRUCTIVE:
            return True

        return False
