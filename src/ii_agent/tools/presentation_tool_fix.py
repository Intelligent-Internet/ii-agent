import asyncio
from ii_agent.core.event import EventType, RealtimeEvent
from ii_agent.tools.advanced_tools.image_search_tool import ImageSearchTool
from ii_agent.tools.base import LLMTool
from ii_agent.utils import WorkspaceManager
from ii_agent.tools.bash_tool import create_bash_tool
from ii_agent.tools.str_replace_tool_relative import StrReplaceEditorTool

from ii_agent.llm.message_history import MessageHistory
from ii_agent.tools.base import ToolImplOutput

from typing import Any, Optional

from copy import deepcopy


class PresentationTool(LLMTool):
    """A tool for creating and managing presentations.

    This tool allows the agent to create, update, and manage slide presentations.
    It provides functionality to initialize a presentation, add/edit/delete slides,
    and finalize the presentation with consistent styling and formatting.
    The tool uses reveal.js as the presentation framework and supports various
    content elements like text, images, charts, and icons.
    """

    name = "presentation"
    description = """\
Create professional presentations. Actions: init (setup), create/update/delete (slides), final_check (QA).
Init creates skeleton with all slide placeholders. Each slide fits 1280x720px with consistent design.
"""
    PROMPT = """
Presentation expert. Working dir: "."

KEY RULES:
- Max 10 slides unless specified
- Init: Update index.html with iframe placeholders only (slides/[name].html)
- Actions create HTML in ./presentation/reveal.js/slides/
- Slides fit 1280x720px, overflow-y:auto
- Use image_search tool or provided URLs only

DESIGN:
- Clear visual hierarchy, consistent colors/typography
- Modern CSS: Flexbox/Grid, rem/em units, CSS vars
- Tailwind CSS, FontAwesome icons, Chart.js
- Smooth transitions, proper contrast

FINAL_CHECK: Verify all styles applied, URLs work, consistency maintained.
"""

    input_schema = {
        "type": "object",
        "properties": {
            "description": {
                "type": "string",
                "description": "The detail description of how to update the presentation.",
            },
            "action": {
                "type": "string",
                "description": "The action to perform on the presentation.",
                "enum": ["init", "create", "update", "delete", "final_check"],
            },
            "images": {
                "type": "array",
                "description": "List of image URLs and their descriptions to be used in the presentation slides.",
                "items": {
                    "type": "object",
                    "properties": {
                        "url": {"type": "string", "description": "URL of an image"},
                        "description": {
                            "type": "string",
                            "description": "Description of what the image represents or how it should be used",
                        },
                    },
                    "required": ["url", "description"],
                },
            },
        },
        "required": ["description", "action"],
    }

    def __init__(
        self,
        client,
        workspace_manager: WorkspaceManager,
        message_queue: asyncio.Queue,
        ask_user_permission: bool = False,
    ):
        super().__init__()
        self.client = client
        self.workspace_manager = workspace_manager
        self.message_queue = message_queue
        self.bash_tool = create_bash_tool(ask_user_permission, workspace_manager.root)
        self.tools = [
            self.bash_tool,
            StrReplaceEditorTool(workspace_manager=workspace_manager),
        ]
        image_search_tool = ImageSearchTool()
        if image_search_tool.is_available():
            self.tools.append(image_search_tool)
        self.history = MessageHistory()
        self.tool_params = [tool.get_tool_param() for tool in self.tools]
        self.max_turns = 200

    def run_impl(
        self,
        tool_input: dict[str, Any],
        message_history: Optional[MessageHistory] = None,
    ) -> ToolImplOutput:
        action = tool_input["action"]
        description = tool_input["description"]

        if action == "init":
            self.history = MessageHistory()

            # Clone the reveal.js repository to the specified path
            clone_result = self.bash_tool.run_impl(
                {
                    "command": f"git clone https://github.com/khoangothe/reveal.js.git {self.workspace_manager.root}/presentation/reveal.js"
                }
            )

            if not clone_result.auxiliary_data.get("success", False):
                return ToolImplOutput(
                    f"Failed to clone reveal.js repository: {clone_result.content}",
                    f"Failed to clone reveal.js repository: {clone_result.content}",
                    auxiliary_data={"success": False},
                )

            # Install dependencies
            install_result = self.bash_tool.run_impl(
                {
                    "command": f"cd {self.workspace_manager.root}/presentation/reveal.js && npm install && cd {self.workspace_manager.root}"
                }
            )

            if not install_result.auxiliary_data.get("success", False):
                return ToolImplOutput(
                    f"Failed to install dependencies: {install_result.content}",
                    f"Failed to install dependencies: {install_result.content}",
                    auxiliary_data={"success": False},
                )

        # Handle other actions (create, update, delete, final_refinement)
        # Add description to history
        instruction = f"Perform '{action}' on presentation at path './presentation/reveal.js' with description: {description}"
        self.history.add_user_prompt(instruction)
        self.interrupted = False

        remaining_turns = self.max_turns
        while remaining_turns > 0:
            remaining_turns -= 1

            delimiter = "-" * 45 + "PRESENTATION AGENT" + "-" * 45
            print(f"\n{delimiter}\n")

            # Get tool parameters for available tools
            tool_params = [tool.get_tool_param() for tool in self.tools]

            # Check for duplicate tool names
            tool_names = [param.name for param in tool_params]
            sorted_names = sorted(tool_names)
            for i in range(len(sorted_names) - 1):
                if sorted_names[i] == sorted_names[i + 1]:
                    raise ValueError(f"Tool {sorted_names[i]} is duplicated")

            current_messages = self.history.get_messages_for_llm()

            # Estimate token count for messages (rough estimate)
            total_chars = sum(len(str(msg)) for msg in current_messages)
            total_chars += len(self.PROMPT)
            estimated_tokens = total_chars // 3  # Rough estimate
            
            # If approaching token limit, truncate history
            if estimated_tokens > 900000:  # Leave buffer below 1048575 limit
                # Keep only last 10 messages
                truncated_messages = current_messages[-10:]
                self.history.set_message_list(truncated_messages)
                current_messages = truncated_messages

            # Generate response using the client
            model_response, _ = self.client.generate(
                messages=current_messages,
                max_tokens=8192,
                tools=tool_params,
                system_prompt=self.PROMPT,
            )

            print(model_response)

            # Add the raw response to the canonical history
            self.history.add_assistant_turn(model_response)

            # Handle tool calls
            pending_tool_calls = self.history.get_pending_tool_calls()

            if len(pending_tool_calls) == 0:
                # No tools were called, so assume the task is complete
                return ToolImplOutput(
                    tool_output=self.history.get_last_assistant_text_response(),
                    tool_result_message="Task completed",
                    auxiliary_data={"success": True},
                )

            # Process all pending tool calls
            tool_results = []
            tool_calls_params = []
            
            for tool_call in pending_tool_calls:
                self.message_queue.put_nowait(
                    RealtimeEvent(
                        type=EventType.TOOL_CALL,
                        content={
                            "tool_call_id": tool_call.tool_call_id,
                            "tool_name": tool_call.tool_name,
                            "tool_input": tool_call.tool_input,
                        },
                    )
                )

                try:
                    tool = next(t for t in self.tools if t.name == tool_call.tool_name)
                except StopIteration as exc:
                    raise ValueError(
                        f"Tool with name {tool_call.tool_name} not found"
                    ) from exc

                # Execute the tool
                # Create a clean history for sub-tools that ends at user's turn
                # by excluding the current assistant turn with pending tool calls
                clean_history = MessageHistory()
                messages = self.history.get_messages_for_llm()
                
                # Ensure we have a history that ends at user's turn
                # The history alternates between user and assistant turns (user at even indices)
                if len(messages) > 0:
                    # If we have an odd number of messages, the last one is an assistant turn
                    # We need to exclude it to end at a user turn
                    if len(messages) % 2 == 1:
                        clean_history.set_message_list(messages[:-1])
                    else:
                        # Already ends at user turn
                        clean_history.set_message_list(messages)
                
                # Only pass history if it's not empty
                result = tool.run(tool_call.tool_input, clean_history if len(clean_history) > 0 else None)

                # Handle both string results and tuples
                if isinstance(result, tuple):
                    tool_result, _ = result
                else:
                    tool_result = result

                # Collect results instead of adding them immediately
                tool_results.append(tool_result)
                tool_calls_params.append(tool_call)

                self.message_queue.put_nowait(
                    RealtimeEvent(
                        type=EventType.TOOL_RESULT,
                        content={
                            "tool_call_id": tool_call.tool_call_id,
                            "tool_name": tool_call.tool_name,
                            "result": tool_result,
                        },
                    )
                )
            
            # After processing all tool calls, add all results at once
            if tool_results:
                self.history.add_tool_call_results(tool_calls_params, tool_results)

        # If we exit the loop without returning, we've hit max turns
        return ToolImplOutput(
            tool_output=f"Action '{action}' did not complete after {self.max_turns} turns",
            tool_result_message=f"Action '{action}' exceeded maximum turns",
            auxiliary_data={"success": False},
        )
