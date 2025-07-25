import asyncio
import time
from typing import Any, Optional, cast
from functools import partial

from openai import BaseModel

from ii_agent.controller.agent import Agent
from ii_agent.core.event import EventType, RealtimeEvent
from ii_agent.core.event_stream import EventStream
from ii_agent.llm.base import TextResult, AssistantContentBlock
from ii_agent.controller.state import State
from ii_agent.tools.utils import encode_image
from ii_agent.tools import AgentToolManager, ToolCallParameters, ToolConfirmationDetails
from ii_tool.tools.base import ToolResult
from ii_agent.utils.constants import COMPLETE_MESSAGE
from ii_agent.utils.workspace_manager import WorkspaceManager
from ii_agent.core.logger import logger
from ii_agent.llm.context_manager.base import ContextManager

TOOL_RESULT_INTERRUPT_MESSAGE = "[Request interrupted by user for tool use]"
AGENT_INTERRUPT_MESSAGE = "Agent interrupted by user."
TOOL_CALL_INTERRUPT_FAKE_MODEL_RSP = "[Request interrupted by user for tool use]"
AGENT_INTERRUPT_FAKE_MODEL_RSP = (
    "Agent interrupted by user. You can resume by providing a new instruction."
)


class AgentOutput(BaseModel):
    agent_output: str
    agent_message: str


class AgentController:
    def __init__(
        self,
        agent: Agent,
        tool_manager: AgentToolManager,
        init_history: State,
        workspace_manager: WorkspaceManager,
        event_stream: EventStream,
        context_manager: ContextManager,
        max_turns: int = 200,
        interactive_mode: bool = True,
        config: Optional[Any] = None,
    ):
        """Initialize the agent.

        Args:
            agent: The agent to use
            tool_manager: Tool manager for tool execution
            init_history: Initial history to use
            workspace_manager: Workspace manager for file operations
            event_stream: Event stream for publishing events
            context_manager: Context manager for token counting and truncation
            max_turns: Maximum number of turns
            interactive_mode: Whether to use interactive mode
        """
        super().__init__()
        self.workspace_manager = workspace_manager
        self.agent = agent
        self.tool_manager = tool_manager
        self.config = config

        self.max_turns = max_turns
        self.interactive_mode = interactive_mode
        self.interrupted = False
        self.history = init_history
        self.event_stream = event_stream
        self.context_manager = context_manager
        
        # Tool confirmation tracking
        self._pending_confirmations: dict[str, dict] = {}
        self._confirmation_responses: dict[str, dict] = {}

    def add_confirmation_response(self, tool_call_id: str, approved: bool, alternative_instruction: str = "") -> None:
        """Add a confirmation response for a tool call."""
        self._confirmation_responses[tool_call_id] = {
            "approved": approved,
            "alternative_instruction": alternative_instruction
        }

    def _should_auto_approve_tool(self, tool_name: str) -> bool:
        """Check if a tool should be auto-approved based on config."""
        if not self.config:
            return False
        
        # Check if all tools are auto-approved
        if getattr(self.config, 'auto_approve_tools', False):
            return True
        
        # Check if this specific tool is in the allow list
        allow_tools = getattr(self.config, 'allow_tools', set())
        return tool_name in allow_tools

    async def _wait_for_confirmation(self, tool_call_id: str, timeout: float = 300.0) -> dict:
        """Wait for confirmation response for a specific tool call."""
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            if tool_call_id in self._confirmation_responses:
                response = self._confirmation_responses.pop(tool_call_id)
                return response
            
            # Check for interruption
            if self.interrupted:
                return {"approved": False, "alternative_instruction": "Operation interrupted"}
            
            await asyncio.sleep(0.1)
        
        # Timeout - default to deny
        return {"approved": False, "alternative_instruction": "Confirmation timeout"}

    async def run_impl(
        self,
        tool_input: dict[str, Any],
    ) -> AgentOutput:
        instruction = tool_input["instruction"]
        files = tool_input["files"]

        # Add instruction to dialog before getting model response
        image_blocks = []
        if files:
            # First, list all attached files
            instruction = f"""{instruction}\n\nAttached files:\n"""
            for file in files:
                relative_path = self.workspace_manager.relative_path(file)
                instruction += f" - {relative_path}\n"
                logger.debug(f"Attached file: {relative_path}")

            # Then process images for image blocks
            for file in files:
                ext = file.split(".")[-1]
                if ext == "jpg":
                    ext = "jpeg"
                if ext in ["png", "gif", "jpeg", "webp"]:
                    base64_image = encode_image(
                        str(self.workspace_manager.workspace_path(file))
                    )
                    image_blocks.append(
                        {
                            "source": {
                                "type": "base64",
                                "media_type": f"image/{ext}",
                                "data": base64_image,
                            }
                        }
                    )

        self.history.add_user_prompt(instruction, image_blocks)
        self.interrupted = False

        remaining_turns = self.max_turns
        while remaining_turns > 0:
            self.truncate_history()
            remaining_turns -= 1


            if self.interrupted:
                # Handle interruption during model generation or other operations
                self.add_fake_assistant_turn(AGENT_INTERRUPT_FAKE_MODEL_RSP)
                return AgentOutput(
                    agent_output=AGENT_INTERRUPT_MESSAGE,
                    agent_message=AGENT_INTERRUPT_MESSAGE,
                )

            # Only show token count in debug mode, not in interactive CLI
            if not self.interactive_mode:
                logger.info(f"(Current token count: {self.count_tokens()})\n")

            # Emit thinking event before model response
            self.event_stream.add_event(
                RealtimeEvent(type=EventType.AGENT_THINKING, content={})
            )

            loop = asyncio.get_event_loop()
            model_response = await loop.run_in_executor(
                None,
                partial(
                    self.agent.step,
                    self.history,
                ),
            )

            if len(model_response) == 0:
                model_response = [
                    cast(AssistantContentBlock, TextResult(text=COMPLETE_MESSAGE))
                ]

            # Add the raw response to the canonical history
            self.history.add_assistant_turn(cast(list[AssistantContentBlock], model_response))

            # Process all TextResult blocks first
            text_results = [
                item for item in model_response if isinstance(item, TextResult)
            ]
            for text_result in text_results:
                logger.debug(
                    f"Top-level agent planning next step: {text_result.text}\n",
                )
                # Emit event for each TextResult to be displayed in console
                self.event_stream.add_event(
                    RealtimeEvent(
                        type=EventType.AGENT_RESPONSE,
                        content={"text": text_result.text},
                    )
                )

            # Handle tool calls
            pending_tool_calls = self.history.get_pending_tool_calls()

            if len(pending_tool_calls) == 0:
                # No tools were called, so assume the task is complete
                logger.debug("[no tools were called]")
                # Only emit "Task completed" if there were no text results
                if not text_results:
                    self.event_stream.add_event(
                        RealtimeEvent(
                            type=EventType.AGENT_RESPONSE,
                            content={"text": "Task completed"},
                        )
                    )
                return AgentOutput(
                    agent_output=self.history.get_last_assistant_text_response()
                    or "Task completed",
                    agent_message="Task completed",
                )

            # Check for interruption before tool execution
            if self.interrupted:
                # Handle interruption during tool execution
                for tool_call in pending_tool_calls:
                    self.add_tool_call_result(tool_call, ToolResult(
                        llm_content=TOOL_RESULT_INTERRUPT_MESSAGE,
                        user_display_content=TOOL_RESULT_INTERRUPT_MESSAGE,
                    ))
                self.add_fake_assistant_turn(TOOL_CALL_INTERRUPT_FAKE_MODEL_RSP)
                return AgentOutput(
                    agent_output=TOOL_RESULT_INTERRUPT_MESSAGE,
                    agent_message=TOOL_RESULT_INTERRUPT_MESSAGE,
                )

            # Execute all tool calls using batch approach
            logger.debug(f"Executing {len(pending_tool_calls)} tool(s)")

            # Send events for all tool calls
            for tool_call in pending_tool_calls:
                self.event_stream.add_event(
                    RealtimeEvent(
                        type=EventType.TOOL_CALL,
                        content={
                            "tool_call_id": tool_call.tool_call_id,
                            "tool_name": tool_call.tool_name,
                            "tool_input": tool_call.tool_input,
                        },
                    )
                )

            # Handle tool confirmation and execution
            approved_tool_calls = []
            denied_tool_calls = []
            alternative_instructions = []
            
            for tool_call in pending_tool_calls:
                tool = self.tool_manager.get_tool(tool_call.tool_name)
                from ii_agent.tools.mcp_tool import MCPTool
                if not isinstance(tool, MCPTool):
                    approved_tool_calls.append(tool_call)
                    continue

                confirmation_details = await tool.should_confirm_execute(tool_call.tool_input)
                
                # Check if tool should be auto-approved
                if self._should_auto_approve_tool(tool_call.tool_name):
                    approved_tool_calls.append(tool_call)
                elif isinstance(confirmation_details, ToolConfirmationDetails):
                    # Send confirmation event and wait for response
                    self.event_stream.add_event(
                        RealtimeEvent(type=EventType.TOOL_CONFIRMATION, content={
                            "tool_call_id": tool_call.tool_call_id,
                            "tool_name": tool_call.tool_name,
                            "tool_input": tool_call.tool_input,
                            "message": confirmation_details.message,
                        })
                    )
                    
                    # Wait for confirmation response
                    confirmation_response = await self._wait_for_confirmation(tool_call.tool_call_id)
                    
                    if confirmation_response["approved"]:
                        approved_tool_calls.append(tool_call)
                    else:
                        denied_tool_calls.append(tool_call)
                        if confirmation_response["alternative_instruction"]:
                            alternative_instructions.append(confirmation_response["alternative_instruction"])
                else:
                    # No confirmation needed, approve by default
                    approved_tool_calls.append(tool_call)
            
            # Handle denied tools
            if denied_tool_calls:
                denial_message = f"Tool execution denied for: {', '.join([tc.tool_name for tc in denied_tool_calls])}"
                if alternative_instructions:
                    denial_message += f"\nAlternative instructions: {'; '.join(alternative_instructions)}"
                
                # Add denial results to history
                for tool_call in denied_tool_calls:
                    self.add_tool_call_result(tool_call, ToolResult(
                        llm_content=denial_message,
                        user_display_content=denial_message,
                    ))
            
            # Execute approved tools in batch
            if approved_tool_calls:
                tool_results = await self.tool_manager.run_tools_batch(approved_tool_calls)
                
                for tool_call, tool_result in zip(approved_tool_calls, tool_results):
                    self.add_tool_call_result(tool_call, tool_result)
            
            # If all tools were denied and we have alternative instructions, add them to history
            if not approved_tool_calls and alternative_instructions:
                alt_instruction_text = "User provided alternative instructions: " + "; ".join(alternative_instructions)
                self.history.add_user_prompt(alt_instruction_text)

        agent_answer = "Agent did not complete after max turns"
        self.event_stream.add_event(
            RealtimeEvent(type=EventType.AGENT_RESPONSE, content={"text": agent_answer})
        )
        return AgentOutput(agent_output=agent_answer, agent_message=agent_answer)

    def get_tool_start_message(self, tool_input: dict[str, Any]) -> str:
        return f"Agent started with instruction: {tool_input['instruction']}"

    async def run_agent_async(
        self,
        instruction: str,
        files: list[str] | None = None,
        resume: bool = False,
    ) -> AgentOutput:
        """Start a new agent run asynchronously.

        Args:
            instruction: The instruction to the agent.
            files: Optional list of files to attach
            resume: Whether to resume the agent from the previous state,
                continuing the dialog.

        Returns:
            The result from the agent execution.
        """
        if not resume:
            self.history.clear()
            self.interrupted = False

        tool_input = {
            "instruction": instruction,
            "files": files,
        }
        return await self.run_impl(tool_input)

    def run_agent(
        self,
        instruction: str,
        files: list[str] | None = None,
        resume: bool = False,
    ):
        """Start a new agent run synchronously.

        Args:
            instruction: The instruction to the agent.
            files: Optional list of files to attach
            resume: Whether to resume the agent from the previous state,
                continuing the dialog.
            orientation_instruction: Optional orientation instruction

        Returns:
            The result from the agent execution.
        """
        asyncio.run(self.run_agent_async(instruction, files, resume))

    def clear(self):
        """Clear the dialog and reset interruption state.
        Note: This does NOT clear the file manager, preserving file context.
        """
        self.history.clear()
        self.interrupted = False

    def cancel(self):
        """Cancel the agent execution."""
        self.interrupted = True
        logger.debug("Agent cancellation requested")

    def add_tool_call_result(self, tool_call: ToolCallParameters, tool_result: ToolResult):
        """Add a tool call result to the history and send it to the message queue."""
        llm_content = tool_result.llm_content
        user_display_content = tool_result.user_display_content

        if isinstance(llm_content, str):
            self.history.add_tool_call_result(tool_call, llm_content)
        else:
            # TODO: add support for multiple text/image blocks
            # Currently, we will support only the text blocks
            llm_content_text = [item.text for item in llm_content if item.type == "text"]
            llm_content_text = "\n".join(llm_content_text)
            self.history.add_tool_call_result(tool_call, llm_content_text)

        self.event_stream.add_event(
            RealtimeEvent(
                type=EventType.TOOL_RESULT,
                content={
                    "tool_call_id": tool_call.tool_call_id,
                    "tool_name": tool_call.tool_name,
                    "result": user_display_content
                },
            )
        )

    def add_fake_assistant_turn(self, text: str):
        """Add a fake assistant turn to the history and send it to the message queue."""
        self.history.add_assistant_turn(cast(list[AssistantContentBlock], [TextResult(text=text)]))
        if self.interrupted:
            rsp_type = EventType.AGENT_RESPONSE_INTERRUPTED
        else:
            rsp_type = EventType.AGENT_RESPONSE

        self.event_stream.add_event(
            RealtimeEvent(
                type=rsp_type,
                content={"text": text},
            )
        )

    def count_tokens(self) -> int:
        """Count the tokens in the current message history."""
        return self.context_manager.count_tokens(self.history.get_messages_for_llm())

    def truncate_history(self) -> None:
        """Remove oldest messages when context window limit is exceeded."""
        truncated_messages_for_llm = self.context_manager.apply_truncation_if_needed(
            self.history.get_messages_for_llm()
        )
        self.history.set_message_list(truncated_messages_for_llm)

    def compact_context(self) -> dict[str, Any]:
        """Manually compact the conversation context using truncation.

        Returns:
            Dict containing operation status and token information.
        """
        try:
            # Get current token count before compacting
            original_token_count = self.count_tokens()

            # Apply truncation regardless of current token count
            truncated_messages_for_llm = self.context_manager.apply_truncation(
                self.history.get_messages_for_llm()
            )

            # Update history with truncated messages
            self.history.set_message_list(truncated_messages_for_llm)

            # Get new token count after compacting
            new_token_count = self.count_tokens()

            return {
                "success": True,
                "original_tokens": original_token_count,
                "new_tokens": new_token_count,
                "tokens_saved": original_token_count - new_token_count,
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
            }
