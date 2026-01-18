#!/usr/bin/env python3
"""
Codex Agent - Async HTTP SSE Client for Codex Event Streaming
Connects to the HTTP server and streams Codex lifecycle events
"""

import asyncio
import json
from typing import Any, Optional
import uuid
from uuid import UUID

import httpx
from ii_agent.core.event import EventType, RealtimeEvent
from ii_agent.core.event_stream import EventStream
from ii_tool.tools.base import BaseTool, ToolResult


class CodexAgent(BaseTool):
    name = "codex_agent"
    display_name = "Codex Agent"
    description = "An AI agent that can perform complex tasks by utilizing various tools and resources."
    input_schema = {
        "type": "object",
        "properties": {
            "prompt": {
                "type": "string",
                "description": "The initial prompt or instruction for the Codex agent.",
            },
            "work_dir": {
                "type": "string",
                "description": "The working directory for the Codex agent to use.",
            },
        },
        "required": ["prompt", "work_dir"],
    }
    read_only = True

    def __init__(
        self,
        event_stream: EventStream,
        codex_url: str,
        timeout: int = 300,
        session_id: Optional[UUID] = None,
        run_id: Optional[UUID] = None,
    ):
        self.event_stream = event_stream
        self.codex_url = codex_url
        self.timeout = timeout
        self.session_id = session_id
        self.run_id = run_id

    def _get_session_id(self) -> Optional[UUID]:
        """Return session_id UUID if available."""
        return self.session_id

    def _get_run_id(self) -> Optional[UUID]:
        """Return run_id UUID if available."""
        return self.run_id

    async def execute(self, tool_input: dict[str, Any]) -> ToolResult:
        prompt = tool_input["prompt"]
        work_dir = tool_input["work_dir"]

        # Prepare payload for Codex server
        payload = {
            "type": "user_message",
            "message": prompt,
            "work_dir": work_dir,
        }

        try:
            result_text = await self._stream_codex_events(payload)

            await self.event_stream.publish(
                RealtimeEvent(
                    type=EventType.SUB_AGENT_COMPLETE,
                    session_id=self._get_session_id(),
                    run_id=self._get_run_id(),
                    content={"text": "Codex agent completed", "is_interrupted": False},
                )
            )

            return ToolResult(llm_content=result_text, user_display_content=result_text)
        except asyncio.CancelledError:
            # Handle cancellation/interruption
            await self.event_stream.publish(
                RealtimeEvent(
                    type=EventType.SUB_AGENT_INTERRUPTED,
                    session_id=self._get_session_id(),
                    run_id=self._get_run_id(),
                    content={"text": "Codex agent interrupted", "is_interrupted": True},
                )
            )
            return ToolResult(
                llm_content="Codex agent interrupted by user",
                user_display_content="Codex agent interrupted by user",
                is_interrupted=True,
            )
        except Exception as e:
            error_msg = f"Codex agent failed: {str(e)}"
            return ToolResult(
                llm_content=error_msg, user_display_content=error_msg, is_error=True
            )

    async def _stream_codex_events(self, payload: dict[str, Any]) -> str:
        """Stream events from Codex server and forward to event_stream"""
        collected_output: list[str] = []
        task_complete_message = None

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            async with client.stream(
                "POST",
                self.codex_url,
                json=payload,
                headers={"Accept": "text/event-stream"},
            ) as response:
                response.raise_for_status()

                async for line in response.aiter_lines():
                    if not line.strip():
                        continue

                    # Parse SSE format: "data: {json}"
                    if line.startswith("data: "):
                        data_str = line[6:]  # Remove "data: " prefix

                        try:
                            event_data = json.loads(data_str)
                            complete_msg = await self._process_codex_event(
                                event_data, collected_output
                            )
                            # Track the task_complete message if returned
                            if complete_msg is not None:
                                task_complete_message = complete_msg
                        except json.JSONDecodeError as e:
                            # Log but continue streaming
                            error_msg = f"Failed to parse event: {e}"
                            await self.event_stream.publish(
                                RealtimeEvent(
                                    type=EventType.ERROR,
                                    session_id=self._get_session_id(),
                                    run_id=self._get_run_id(),
                                    content={
                                        "message": error_msg,
                                        "source": "codex_agent",
                                    },
                                )
                            )

        # Return the task_complete message if available, otherwise join collected outputs
        if task_complete_message:
            result = task_complete_message
        elif collected_output:
            result = "\n".join(collected_output)
        else:
            result = "Codex agent completed with no output"

        # Note: We don't send a final TOOL_RESULT or COMPLETE event here
        # because the Codex server sends a task_complete event which we handle
        # in _process_codex_event, which already emits the COMPLETE event

        return result

    async def _process_codex_event(
        self, event_data: dict[str, Any], collected_output: list[str]
    ) -> str | None:
        """Process individual Codex event and forward to event_stream

        Maps Codex EventMsg types to ii_agent EventTypes:
        - AgentMessage -> AGENT_RESPONSE
        - AgentReasoning/AgentReasoningRawContent -> AGENT_THINKING
        - McpToolCallBegin/ExecCommandBegin/WebSearchBegin/PatchApplyBegin -> TOOL_CALL
        - McpToolCallEnd/ExecCommandEnd/WebSearchEnd/PatchApplyEnd -> TOOL_RESULT
        - TaskComplete -> COMPLETE
        - Error -> ERROR
        - Ignoring: all delta events, approval requests

        Returns:
            The completion message if this is a task_complete event, None otherwise
        """
        event_type = event_data.get("type", "unknown")

        # Agent message/response
        if event_type == "agent_message":
            message = event_data.get("message", "")
            collected_output.append(message)
            await self.event_stream.publish(
                RealtimeEvent(
                    type=EventType.AGENT_RESPONSE,
                    session_id=self._get_session_id(),
                    run_id=self._get_run_id(),
                    content={"text": message},
                )
            )

        # Agent reasoning (thinking)
        elif event_type in ("agent_reasoning", "agent_reasoning_raw_content"):
            thinking_text = event_data.get("text", "")
            await self.event_stream.publish(
                RealtimeEvent(
                    type=EventType.AGENT_THINKING,
                    session_id=self._get_session_id(),
                    run_id=self._get_run_id(),
                    content={"text": thinking_text},
                )
            )

        # MCP Tool Call Begin
        elif event_type == "mcp_tool_call_begin":
            invocation = event_data.get("invocation", {})
            call_id = event_data.get("call_id", f"mcp_{id(event_data)}")
            server = invocation.get("server", "unknown")
            tool = invocation.get("tool", "unknown")
            arguments = invocation.get("arguments", {})

            await self.event_stream.publish(
                RealtimeEvent(
                    type=EventType.TOOL_CALL,
                    session_id=self._get_session_id(),
                    run_id=self._get_run_id(),
                    content={
                        "tool_call_id": call_id,
                        "tool_name": f"{server}.{tool}",
                        "tool_input": arguments,
                        "tool_display_name": f"MCP: {tool}",
                    },
                )
            )

        # MCP Tool Call End
        elif event_type == "mcp_tool_call_end":
            invocation = event_data.get("invocation", {})
            call_id = event_data.get("call_id", f"mcp_{id(event_data)}")
            server = invocation.get("server", "unknown")
            tool = invocation.get("tool", "unknown")
            result = event_data.get("result", {})

            # Check if result is Ok or Err
            is_error = False
            tool_output = ""
            if isinstance(result, dict):
                if "Ok" in result:
                    tool_output = str(result["Ok"])
                elif "Err" in result:
                    tool_output = str(result["Err"])
                    is_error = True
                else:
                    tool_output = str(result)

            collected_output.append(f"[MCP:{tool}] {tool_output}")

            await self.event_stream.publish(
                RealtimeEvent(
                    type=EventType.TOOL_RESULT,
                    session_id=self._get_session_id(),
                    run_id=self._get_run_id(),
                    content={
                        "tool_call_id": call_id,
                        "tool_name": f"{server}.{tool}",
                        "tool_input": invocation.get("arguments", {}),
                        "result": tool_output,
                        "is_error": is_error,
                    },
                )
            )

        # Exec Command Begin (shell execution)
        elif event_type == "exec_command_begin":
            call_id = event_data.get("call_id", f"exec_{id(event_data)}")
            command = event_data.get("command", [])
            cwd = event_data.get("cwd", "")

            await self.event_stream.publish(
                RealtimeEvent(
                    type=EventType.TOOL_CALL,
                    session_id=self._get_session_id(),
                    run_id=self._get_run_id(),
                    content={
                        "tool_call_id": call_id,
                        "tool_name": "Bash",
                        "tool_input": {"command": " ".join(command), "cwd": cwd},
                        "tool_display_name": "Bash",
                    },
                )
            )

        # Exec Command End
        elif event_type == "exec_command_end":
            call_id = event_data.get("call_id", f"exec_{id(event_data)}")
            stdout = event_data.get("stdout", "")
            stderr = event_data.get("stderr", "")
            exit_code = event_data.get("exit_code", 0)
            formatted_output = event_data.get("formatted_output", "")

            is_error = exit_code != 0
            output = formatted_output or (stdout + stderr)

            collected_output.append(f"[bash] {output}")

            await self.event_stream.publish(
                RealtimeEvent(
                    type=EventType.TOOL_RESULT,
                    session_id=self._get_session_id(),
                    run_id=self._get_run_id(),
                    content={
                        "tool_call_id": call_id,
                        "tool_name": "Bash",
                        "tool_input": {},
                        "result": output,
                        "is_error": is_error,
                    },
                )
            )

        # Web Search Begin
        elif event_type == "web_search_begin":
            call_id = event_data.get("call_id", f"websearch_{id(event_data)}")

            await self.event_stream.publish(
                RealtimeEvent(
                    type=EventType.TOOL_CALL,
                    session_id=self._get_session_id(),
                    run_id=self._get_run_id(),
                    content={
                        "tool_call_id": call_id,
                        "tool_name": "web_search",
                        "tool_input": {},
                        "tool_display_name": "Web Search",
                    },
                )
            )

        # Web Search End
        elif event_type == "web_search_end":
            call_id = event_data.get("call_id", f"websearch_{id(event_data)}")
            query = event_data.get("query", "")

            collected_output.append(f"[web_search] Query: {query}")

            await self.event_stream.publish(
                RealtimeEvent(
                    type=EventType.TOOL_RESULT,
                    session_id=self._get_session_id(),
                    run_id=self._get_run_id(),
                    content={
                        "tool_call_id": call_id,
                        "tool_name": "web_search",
                        "tool_input": {"query": query},
                        "result": f"Search completed for: {query}",
                        "is_error": False,
                    },
                )
            )

        # Patch Apply Begin
        elif event_type == "patch_apply_begin":
            call_id = event_data.get("call_id", f"patch_{id(event_data)}")
            changes = event_data.get("changes", {})

            await self.event_stream.publish(
                RealtimeEvent(
                    type=EventType.TOOL_CALL,
                    session_id=self._get_session_id(),
                    run_id=self._get_run_id(),
                    content={
                        "tool_call_id": call_id,
                        "tool_name": "apply_patch",
                        "tool_input": {"changes": changes},
                        "tool_display_name": "Apply Patch",
                    },
                )
            )

        # Patch Apply End
        elif event_type == "patch_apply_end":
            call_id = event_data.get("call_id", f"patch_{id(event_data)}")
            stdout = event_data.get("stdout", "")
            stderr = event_data.get("stderr", "")
            success = event_data.get("success", False)

            output = stdout if stdout else stderr
            collected_output.append(f"[apply_patch] {output}")

            await self.event_stream.publish(
                RealtimeEvent(
                    type=EventType.TOOL_RESULT,
                    session_id=self._get_session_id(),
                    run_id=self._get_run_id(),
                    content={
                        "tool_call_id": call_id,
                        "tool_name": "apply_patch",
                        "tool_input": {},
                        "result": output,
                        "is_error": not success,
                    },
                )
            )

        # Task Complete
        elif event_type == "task_complete":
            last_message = event_data.get("last_agent_message")
            final_msg = last_message or "Task completed"
            # Return the completion message to be used as the final result
            return final_msg

        # Error
        elif event_type == "error":
            error_msg = event_data.get("message", "Unknown error")
            collected_output.append(f"ERROR: {error_msg}")
            await self.event_stream.publish(
                RealtimeEvent(
                    type=EventType.ERROR,
                    session_id=self._get_session_id(),
                    run_id=self._get_run_id(),
                    content={
                        "message": f"[Codex] {error_msg}",
                        "source": "codex_agent",
                    },
                )
            )

        # Ignore delta events and approval requests
        elif event_type in (
            "agent_message_delta",
            "agent_reasoning_delta",
            "agent_reasoning_raw_content_delta",
            "exec_command_output_delta",
            "exec_approval_request",
            "apply_patch_approval_request",
            "agent_reasoning_section_break",
        ):
            # Silently ignore streaming/approval events
            pass

        # Return None for all non-completion events
        return None
