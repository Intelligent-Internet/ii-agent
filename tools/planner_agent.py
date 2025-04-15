from copy import deepcopy
from typing import Any, Optional, Dict, List
from utils.common import (
    DialogMessages,
    LLMTool,
    ToolImplOutput,
)
from utils.llm_client import LLMClient, TextResult
from utils.workspace_manager import WorkspaceManager
from prompts.system_prompt import SYSTEM_PROMPT
import os
import json
import logging
import datetime
import traceback


class PlannerAgent(LLMTool):
    name = "planner_agent"
    description = """\
A specialized agent that helps with creating, storing, and updating plan state for complex tasks.
Use this tool when you need to create a structured plan for a complex task, update an existing plan, 
or retrieve a plan's current state.
"""
    input_schema = {
        "type": "object",
        "properties": {
            "instruction": {
                "type": "string",
                "description": "Instructions for planning or updating the plan.",
            },
            "plan_file_path": {
                "type": "string",
                "description": "The path where the plan should be stored.",
            },
            "action": {
                "type": "string",
                "description": "Action to perform: 'create', 'update', or 'get'.",
                "enum": ["create", "update", "get"]
            },
        },
        "required": ["instruction", "plan_file_path", "action"],
    }

    def _get_system_prompt(self):
        """Get the system prompt for the planner agent.

        Returns:
            The system prompt with workspace root information
        """
        return SYSTEM_PROMPT.format(
            workspace_root=self.workspace_manager.root,
        )

    def __init__(
        self,
        client: LLMClient,
        workspace_manager: WorkspaceManager,
        parent_agent,
        logger_for_agent_logs: logging.Logger,
        max_output_tokens: int = 8192,
    ):
        """Initialize the planner agent.

        Args:
            client: The LLM client to use
            workspace_manager: Workspace manager for file operations
            parent_agent: The parent general agent that will hand off to this agent
            logger_for_agent_logs: Logger for agent activities
            max_output_tokens: Maximum tokens per generation
        """
        super().__init__()
        self.client = client
        self.workspace_manager = workspace_manager
        self.parent_agent = parent_agent
        self.logger_for_agent_logs = logger_for_agent_logs
        self.max_output_tokens = max_output_tokens
        self.dialog = DialogMessages(
            logger_for_agent_logs=logger_for_agent_logs,
            use_prompt_budgeting=True,
        )
        self.current_plan = None

    def run_impl(
        self,
        tool_input: dict[str, Any],
        dialog_messages: Optional[DialogMessages] = None,
    ) -> ToolImplOutput:
        instruction = tool_input["instruction"]
        plan_file_path = tool_input["plan_file_path"]
        action = tool_input["action"]

        # Log the start of the planner agent
        delimiter = "-" * 45 + " PLANNER AGENT " + "-" * 45
        self.logger_for_agent_logs.info(f"\n{delimiter}\n")
        self.logger_for_agent_logs.info(f"Plan file: {plan_file_path}")
        self.logger_for_agent_logs.info(f"Action: {action}")
        self.logger_for_agent_logs.info(f"Instruction: {instruction}")

        # Validate action
        if action not in ["create", "update", "get"]:
            error_message = f"Invalid action: {action}. Must be one of: create, update, get"
            self.logger_for_agent_logs.error(error_message)
            return ToolImplOutput(
                tool_output=error_message,
                tool_result_message=error_message,
            )

        try:
            # Get the current plan if it exists
            current_plan = self._load_plan(plan_file_path)
            
            # For update and get actions, ensure a plan exists
            if action in ["update", "get"] and current_plan is None:
                error_message = f"No plan exists at {plan_file_path} for {action} action"
                self.logger_for_agent_logs.error(error_message)
                return ToolImplOutput(
                    tool_output=error_message,
                    tool_result_message=error_message,
                )
            
            # For get action, simply return the current plan
            if action == "get":
                return ToolImplOutput(
                    tool_output=current_plan,
                    tool_result_message=f"Retrieved current plan from {plan_file_path}",
                )
            
            # Use parent agent's dialog for context
            parent_dialog = deepcopy(self.parent_agent.dialog)
            
            # Prepare the appropriate prompt based on the action
            if action == "create":
                planning_prompt = self._create_plan_prompt(instruction, plan_file_path)
            else:  # action == "update"
                planning_prompt = self._update_plan_prompt(instruction, current_plan, plan_file_path)
            
            parent_dialog.add_user_prompt(planning_prompt)

            # Generate plan using the LLM with the parent's dialog context
            model_response, _ = self.client.generate(
                messages=parent_dialog.get_messages_for_llm_client(),
                max_tokens=self.max_output_tokens,
                system_prompt=self._get_system_prompt(),
            )
            
            parent_dialog.add_model_response(model_response)
            plan_content = parent_dialog.get_last_model_text_response()
            
            # Process the plan content
            processed_plan = self._process_plan(plan_content, action, current_plan)
            
            # Ensure the directory exists
            dir_path = os.path.dirname(os.path.abspath(plan_file_path))
            if dir_path:  # Check if dirname is not empty
                os.makedirs(dir_path, exist_ok=True)
            
            # Save the plan to the specified file
            with open(plan_file_path, 'w') as f:
                json.dump(processed_plan, f, indent=2)
            
            # Update the current plan
            self.current_plan = processed_plan
            
            result_message = f"Plan successfully {'created' if action == 'create' else 'updated'} at {plan_file_path}"
            self.logger_for_agent_logs.info(f"\n{result_message}\n")
            
            return ToolImplOutput(
                tool_output=processed_plan,
                tool_result_message=result_message,
            )
            
        except Exception as e:
            error_message = f"Error in planner agent: {str(e)}"
            self.logger_for_agent_logs.error(f"{error_message}\n{traceback.format_exc()}")
            return ToolImplOutput(
                tool_output=error_message,
                tool_result_message=error_message,
            )

    def _load_plan(self, plan_file_path: str) -> Optional[Dict]:
        """Load a plan from a file if it exists.
        
        Args:
            plan_file_path: Path to the plan file
            
        Returns:
            The loaded plan or None if the file doesn't exist
        """
        try:
            if os.path.exists(plan_file_path):
                with open(plan_file_path, 'r') as f:
                    plan_data = json.load(f)
                    # Validate basic plan structure
                    if not isinstance(plan_data, dict):
                        self.logger_for_agent_logs.warning(f"Plan file does not contain a valid JSON object: {plan_file_path}")
                        return None
                    
                    # Ensure required fields are present
                    required_fields = ["goal", "steps", "metadata"]
                    missing_fields = [field for field in required_fields if field not in plan_data]
                    if missing_fields:
                        self.logger_for_agent_logs.warning(
                            f"Plan file missing required fields {missing_fields}: {plan_file_path}"
                        )
                        # Add missing fields with default values
                        if "goal" not in plan_data:
                            plan_data["goal"] = "No goal specified"
                        if "steps" not in plan_data:
                            plan_data["steps"] = []
                        if "metadata" not in plan_data:
                            plan_data["metadata"] = {
                                "created_at": datetime.datetime.now().isoformat(),
                                "last_updated": datetime.datetime.now().isoformat(),
                                "progress": 0
                            }
                    
                    return plan_data
        except json.JSONDecodeError as e:
            self.logger_for_agent_logs.error(f"Error parsing plan JSON: {str(e)}")
        except Exception as e:
            self.logger_for_agent_logs.error(f"Error loading plan: {str(e)}")
        return None

    def _create_plan_prompt(self, instruction: str, plan_file_path: str) -> str:
        """Create a prompt for plan creation.
        
        Args:
            instruction: User's instruction
            plan_file_path: Path where the plan will be stored
            
        Returns:
            A prompt string for plan creation
        """
        return f"""
Create a structured plan based on the following instruction:
{instruction}

The plan should be a well-organized, step-by-step approach to accomplish the task.
Each step should be clear, actionable, and include:
1. A concise description of what needs to be done
2. Any dependencies or prerequisites for the step
3. Expected outcomes or success criteria

Format the plan as a JSON object with the following structure:
{{
  "goal": "Main goal or objective",
  "steps": [
    {{
      "id": 1,
      "description": "Step description",
      "status": "pending",
      "dependencies": [],
      "expected_outcome": "Expected result of this step"
    }},
    // More steps...
  ],
  "metadata": {{
    "created_at": "creation timestamp",
    "last_updated": "last update timestamp",
    "progress": 0
  }}
}}

Make sure each step is concrete and actionable. When complete, the plan will be stored at {plan_file_path} and will be used to track progress and guide execution.
"""

    def _update_plan_prompt(self, instruction: str, current_plan: Optional[Dict], plan_file_path: str) -> str:
        """Create a prompt for plan updating.
        
        Args:
            instruction: User's instruction for updating the plan
            current_plan: The current plan state
            plan_file_path: Path where the plan is stored
            
        Returns:
            A prompt string for plan updating
        """
        plan_str = json.dumps(current_plan, indent=2) if current_plan else "No existing plan."
        return f"""
Update the existing plan based on the following instruction:
{instruction}

Current plan:
{plan_str}

Make appropriate modifications to the plan while preserving its structure. You can:
1. Add new steps
2. Remove steps that are no longer relevant
3. Modify existing steps
4. Update step statuses (pending, in_progress, completed, blocked)
5. Update the overall progress percentage

Ensure the updated plan maintains the same JSON structure:
{{
  "goal": "Main goal or objective",
  "steps": [
    {{
      "id": 1,
      "description": "Step description",
      "status": "pending|in_progress|completed|blocked",
      "dependencies": [],
      "expected_outcome": "Expected result of this step"
    }},
    // More steps...
  ],
  "metadata": {{
    "created_at": "creation timestamp",
    "last_updated": "current timestamp",
    "progress": 0-100
  }}
}}

Make sure to update only what needs changing. If a step is in progress or completed, only modify it if the instruction explicitly requires it. The updated plan will be stored at {plan_file_path}.
"""

    def _process_plan(self, plan_content: str, action: str, current_plan: Optional[Dict]) -> Dict:
        """Process the plan content generated by the LLM.
        
        Args:
            plan_content: Plan content from LLM
            action: The action performed (create or update)
            current_plan: The current plan if it exists
            
        Returns:
            The processed plan as a dictionary
        """
        # Extract JSON from the content in case the LLM includes extra text
        import re
        
        json_match = re.search(r'({[\s\S]*})', plan_content)
        if json_match:
            try:
                extracted_plan = json.loads(json_match.group(1))
                
                # Ensure the plan has the required structure
                if "goal" not in extracted_plan:
                    extracted_plan["goal"] = ""
                if "steps" not in extracted_plan:
                    extracted_plan["steps"] = []
                if "metadata" not in extracted_plan:
                    extracted_plan["metadata"] = {}
                
                # Update timestamps
                current_time = datetime.datetime.now().isoformat()
                if action == "create":
                    extracted_plan["metadata"]["created_at"] = current_time
                elif current_plan and "metadata" in current_plan and "created_at" in current_plan["metadata"]:
                    # Preserve the original creation timestamp for updates
                    extracted_plan["metadata"]["created_at"] = current_plan["metadata"]["created_at"]
                else:
                    extracted_plan["metadata"]["created_at"] = current_time
                    
                extracted_plan["metadata"]["last_updated"] = current_time
                
                # Calculate progress if not specified
                if "progress" not in extracted_plan["metadata"]:
                    # Count completed steps and calculate percentage
                    total_steps = len(extracted_plan["steps"])
                    if total_steps > 0:
                        completed_steps = len([s for s in extracted_plan["steps"] if s.get("status") == "completed"])
                        extracted_plan["metadata"]["progress"] = int((completed_steps / total_steps) * 100)
                    else:
                        extracted_plan["metadata"]["progress"] = 0
                
                # Validate steps
                for step in extracted_plan["steps"]:
                    if "id" not in step:
                        step["id"] = len(extracted_plan["steps"])
                    if "status" not in step:
                        step["status"] = "pending"
                    if "dependencies" not in step:
                        step["dependencies"] = []
                    if "expected_outcome" not in step:
                        step["expected_outcome"] = ""
                
                return extracted_plan
            except json.JSONDecodeError as e:
                self.logger_for_agent_logs.error(f"Error parsing plan JSON: {str(e)}")
                self.logger_for_agent_logs.error(f"Invalid JSON content: {plan_content}")
        else:
            self.logger_for_agent_logs.error(f"No valid JSON found in content: {plan_content}")
        
        # Fallback: create a basic plan structure
        current_time = datetime.datetime.now().isoformat()
        created_at = current_time
        if action == "update" and current_plan and "metadata" in current_plan and "created_at" in current_plan["metadata"]:
            created_at = current_plan["metadata"]["created_at"]
            
        return {
            "goal": "Generated from instruction",
            "steps": [{"id": 1, "description": plan_content, "status": "pending", "dependencies": [], "expected_outcome": "Complete the task"}],
            "metadata": {
                "created_at": created_at,
                "last_updated": current_time,
                "progress": 0,
                "note": "This plan was generated as a fallback due to JSON parsing errors"
            }
        }

    def get_tool_start_message(self, tool_input: dict[str, Any]) -> str:
        return f"Planner agent started with action: {tool_input['action']}"

    def plan(self, instruction: str, plan_file_path: str, action: str = "create") -> Dict:
        """Start a new planning task.

        Args:
            instruction: Instructions for the planning task.
            plan_file_path: Path where to store the plan.
            action: Action to perform - create, update, or get.

        Returns:
            The plan as a dictionary.
        """
        tool_input = {
            "instruction": instruction,
            "plan_file_path": plan_file_path,
            "action": action,
        }
        return self.run(tool_input, self.dialog) 