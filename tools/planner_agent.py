from copy import deepcopy
from typing import Any, Optional, Dict, List
from utils.common import (
    DialogMessages,
    LLMTool,
    ToolImplOutput,
)
from utils.llm_client import LLMClient, TextResult, TextPrompt
from utils.workspace_manager import WorkspaceManager
from prompts.system_prompt import SYSTEM_PROMPT
import datetime
import traceback
import json
import logging
import uuid


class PlannerAgent(LLMTool):
    name = "planner_agent"
    description = """\
A specialized agent that helps with creating, storing, and updating plan state for complex tasks -- Planner module.
Use this tool when you need to create a structured plan for a complex task, update an existing plan, 
or retrieve a plan's current state. Use this tool at very beginning of a task to create a plan.
"""
    input_schema = {
        "type": "object",
        "properties": {
            "instruction": {
                "type": "string",
                "description": "Instructions for planning or updating the plan.",
            },
            "plan_id": {
                "type": "string",
                "description": "Unique identifier for the plan. Required for 'update' and 'get' actions. For 'create' action, a new ID will be automatically generated if not provided.",
            },
            "action": {
                "type": "string",
                "description": "Action to perform: 'create', 'update', or 'get'.",
                "enum": ["create", "update", "get"]
            },
        },
        "required": ["instruction", "action"],
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
        # Store plans in a dictionary instead of files
        self.plans = {}
        # Keep track of the plan counter for auto-generating IDs
        self.plan_counter = 0

    def _generate_plan_id(self):
        """Generate a unique plan ID.
        
        Returns:
            A unique string identifier for a plan
        """
        self.plan_counter += 1
        return f"plan-{self.plan_counter}"

    def run_impl(
        self,
        tool_input: dict[str, Any],
        dialog_messages: Optional[DialogMessages] = None,
    ) -> ToolImplOutput:
        instruction = tool_input["instruction"]
        action = tool_input["action"]
        
        # Generate a plan ID for create action if not provided
        if action == "create":
            plan_id = tool_input.get("plan_id")
            if not plan_id:
                plan_id = self._generate_plan_id()
        else:
            # For update and get actions, plan_id is required
            plan_id = tool_input.get("plan_id")
            if not plan_id:
                error_message = f"Plan ID is required for {action} action"
                self.logger_for_agent_logs.error(error_message)
                return ToolImplOutput(
                    tool_output=error_message,
                    tool_result_message=error_message,
                )

        # Log the start of the planner agent
        delimiter = "-" * 45 + " PLANNER AGENT " + "-" * 45
        self.logger_for_agent_logs.info(f"\n{delimiter}\n")
        self.logger_for_agent_logs.info(f"Plan ID: {plan_id}")
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
            current_plan = self.plans.get(plan_id)
            
            # For update and get actions, ensure a plan exists
            if action in ["update", "get"] and current_plan is None:
                error_message = f"No plan exists with ID {plan_id} for {action} action"
                self.logger_for_agent_logs.error(error_message)
                return ToolImplOutput(
                    tool_output=error_message,
                    tool_result_message=error_message,
                )
            
            # For get action, simply return the current plan
            if action == "get":
                return ToolImplOutput(
                    tool_output=current_plan,
                    tool_result_message=f"Retrieved current plan with ID {plan_id}",
                )
            
            # Use parent agent's dialog for context
            parent_dialog = deepcopy(self.parent_agent.dialog)
            parent_dialog.drop_tool_calls_from_final_turn()
            
            # Prepare the appropriate prompt based on the action
            if action == "create":
                planning_prompt = self._create_plan_prompt(instruction, plan_id)
            else:  # action == "update"
                planning_prompt = self._update_plan_prompt(instruction, current_plan, plan_id)
            
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
            
            # Store the plan in the agent's plan dictionary
            self.plans[plan_id] = processed_plan
            
            # For create action, include the plan_id in the output
            if action == "create":
                processed_plan["plan_id"] = plan_id
            
            result_message = f"Plan successfully {'created' if action == 'create' else 'updated'} with ID {plan_id}"
            self.logger_for_agent_logs.info(f"\n{result_message}\n")
            
            return ToolImplOutput(
                tool_output=json.dumps(processed_plan, indent=2),
                tool_result_message=result_message,
            )
            
        except Exception as e:
            error_message = f"Error in planner agent: {str(e)}"
            self.logger_for_agent_logs.error(f"{error_message}\n{traceback.format_exc()}")
            return ToolImplOutput(
                tool_output=error_message,
                tool_result_message=error_message,
            )

    def _create_plan_prompt(self, instruction: str, plan_id: str) -> str:
        """Create a prompt for plan creation.
        
        Args:
            instruction: User's instruction
            plan_id: Unique identifier for the plan
            
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

Make sure each step is concrete and actionable. The plan will be stored with ID {plan_id} and will be used to track progress and guide execution.
"""

    def _update_plan_prompt(self, instruction: str, current_plan: Optional[Dict], plan_id: str) -> str:
        """Create a prompt for plan updating.
        
        Args:
            instruction: User's instruction for updating the plan
            current_plan: The current plan state
            plan_id: Unique identifier for the plan
            
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

Make sure to update only what needs changing. If a step is in progress or completed, only modify it if the instruction explicitly requires it. The updated plan will be stored with ID {plan_id}.
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

    def plan(self, instruction: str, plan_id: Optional[str] = None, action: str = "create") -> Dict:
        """Start a new planning task.

        Args:
            instruction: Instructions for the planning task.
            plan_id: Unique identifier for the plan. Required for update and get actions.
                     For create action, if not provided, a new ID will be automatically generated.
            action: Action to perform - create, update, or get.

        Returns:
            The plan as a dictionary with plan_id included.
        """
        tool_input = {
            "instruction": instruction,
            "action": action,
        }
        
        if plan_id or action in ["update", "get"]:
            tool_input["plan_id"] = plan_id
            
        result = self.run(tool_input, self.dialog)
        
        # Return the result which now includes plan_id for create actions
        return result 