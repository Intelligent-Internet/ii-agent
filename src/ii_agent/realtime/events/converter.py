"""Convert V1 agent events to BaseEvent subclasses for frontend compatibility."""

import uuid
from typing import Optional, Union

from ii_agent.realtime.events.app_events import (
    AgentCompleteEvent,
    AgentModelCompactEvent,
    AgentProcessingEvent,
    AgentResponseDeltaEvent,
    AgentResponseEvent,
    AgentResponseInterruptedEvent,
    AgentReasoningDeltaEvent,
    AgentReasoningEvent,
    AgentReasoningStartEvent,
    AgentToolCallEvent,
    AgentToolConfirmationEvent,
    AgentToolResultEvent,
    AppEvent,
    ErrorCode,
    SandboxStatusChangedEvent,
    SubAgentCompleteEvent,
    SystemErrorEvent,
)
from ii_agent.tasks.types import RunStatus

from ii_agent.agents.runs.agent import (
    RunStartedEvent,
    RunContentEvent,
    RunContentDeltaEvent,
    RunCompletedEvent,
    RunErrorEvent,
    RunCancelledEvent,
    RunPausedEvent,
    RunContinuedEvent,
    ReasoningStartedEvent,
    ReasoningDeltaEvent,
    ReasoningCompletedEvent,
    SandboxInitializedEvent,
    ToolCallStartedEvent,
    ToolCallCompletedEvent,
    AgentSummaryStartedEvent,
    AgentSummaryCompletedEvent,
    RunOutput,
    RunOutputEvent,
)


def _get_sub_agent_info(event: Union[RunOutputEvent, RunOutput]) -> dict:
    """Extract sub-agent identification info from an event.

    Returns a dict with sub-agent fields if present, empty dict otherwise.
    """
    info = {}

    # Check for sub-agent identification fields
    if hasattr(event, "delegated_from") and event.delegated_from:
        info["delegated_from"] = event.delegated_from

    if hasattr(event, "is_sub_agent_event") and event.is_sub_agent_event:
        info["is_sub_agent_event"] = True

    if hasattr(event, "parent_run_id") and event.parent_run_id:
        info["parent_run_id"] = event.parent_run_id

    # For RunOutput, check is_sub_agent_response property
    if isinstance(event, RunOutput) and hasattr(event, "is_sub_agent_response"):
        if event.is_sub_agent_response:
            info["is_sub_agent_response"] = True
    # Include agent name for identification
    if hasattr(event, "agent_name") and event.agent_name:
        info["agent_name"] = event.agent_name

    return info


def convert_agent_event_to_realtime(
    event: Union[RunOutputEvent, RunOutput],
    run_id: uuid.UUID,
    session_id: uuid.UUID,
) -> Optional[AppEvent]:
    """Convert a V1 agent event to a BaseEvent subclass for frontend compatibility.

    Args:
        event: V1 agent event (RunOutputEvent or RunOutput)
        session_id: Session ID for the event

    Returns:
        BaseEvent subclass or None if the event should be skipped
    """
    session_uuid = session_id

    # Extract sub-agent identification info
    sub_agent_info = _get_sub_agent_info(event)

    # Extract origin event type
    origin = event.event if hasattr(event, "event") and event.event else RunOutput.__name__

    # RunOutput -> COMPLETE, SUB_AGENT_COMPLETE, or AGENT_RESPONSE_INTERRUPTED (if aborted)
    if isinstance(event, RunOutput):
        is_sub_agent = getattr(event, "is_sub_agent_response", False)
        status = getattr(event, "status", None)

        # If the run was aborted/cancelled, send interrupted event instead of complete
        if status == RunStatus.CANCELLED:
            return AgentResponseInterruptedEvent(
                run_id=run_id,
                session_id=session_uuid,
                content={
                    "origin": origin,
                    "message": getattr(event, "content", None) or "Run was cancelled",
                    "is_sub_agent_event": is_sub_agent,
                    "run_id": str(run_id) if run_id else None,
                    "run_status": RunStatus.CANCELLED if not is_sub_agent else None,
                    **sub_agent_info,
                },
            )

        if is_sub_agent:
            default_text = "Sub-agent completed"
            return SubAgentCompleteEvent(
                run_id=run_id,
                session_id=session_uuid,
                content={
                    "origin": origin,
                    "text": event.content or default_text,
                    "run_id": str(run_id) if run_id else None,
                    **sub_agent_info,
                },
            )
        else:
            default_text = "Task completed"
            return AgentCompleteEvent(
                run_id=run_id,
                session_id=session_uuid,
                content={
                    "origin": origin,
                    "text": event.content or default_text,
                    "run_id": str(run_id) if run_id else None,
                    "run_status": RunStatus.COMPLETED,
                    **sub_agent_info,
                },
            )

    # RunStartedEvent -> PROCESSING
    if isinstance(event, RunStartedEvent):
        return AgentProcessingEvent(
            run_id=run_id,
            session_id=session_uuid,
            content={
                "origin": origin,
                "message": "Processing your message...",
                "model": event.model,
                "model_provider": event.model_provider,
                "agent_name": event.agent_name,
                "run_id": str(run_id) if run_id else None,
                "run_status": RunStatus.RUNNING,
                **sub_agent_info,
            },
        )

    # RunContentEvent -> AGENT_RESPONSE
    if isinstance(event, RunContentEvent):
        return AgentResponseEvent(
            run_id=run_id,
            session_id=session_uuid,
            content={
                "origin": origin,
                "text": event.content,
                "image": event.image,
                "citations": event.citations,
                "run_id": str(run_id) if run_id else None,
                **sub_agent_info,
            },
        )

    # RunCompletedEvent -> COMPLETE or SUB_AGENT_COMPLETE
    if isinstance(event, RunCompletedEvent):
        is_sub_agent = bool(
            sub_agent_info.get("is_sub_agent_event")
            or sub_agent_info.get("delegated_from")
            or sub_agent_info.get("parent_run_id")
            or sub_agent_info.get("is_sub_agent_response")
        )
        if is_sub_agent:
            return SubAgentCompleteEvent(
                run_id=run_id,
                session_id=session_uuid,
                content={
                    "origin": origin,
                    "run_id": str(run_id) if run_id else None,
                    **sub_agent_info,
                },
            )
        else:
            return AgentCompleteEvent(
                run_id=run_id,
                session_id=session_uuid,
                content={
                    "origin": origin,
                    "run_id": str(run_id) if run_id else None,
                    "run_status": RunStatus.COMPLETED,
                    **sub_agent_info,
                },
            )

    # RunErrorEvent -> ERROR
    if isinstance(event, RunErrorEvent):
        # Map runtime error_type string to strict ErrorCode; default to EXECUTION_ERROR.
        try:
            error_code = (
                ErrorCode(event.error_type) if event.error_type else ErrorCode.EXECUTION_ERROR
            )
        except ValueError:
            error_code = ErrorCode.EXECUTION_ERROR

        detail = event.content or "An error occurred"
        return SystemErrorEvent(
            run_id=run_id,
            session_id=session_uuid,
            error_code=error_code,
            detail=detail,
            content={
                "origin": origin,
                "message": detail,
                "error_code": str(error_code),
                "error_id": event.error_id,
                "additional_data": event.additional_data,
                "run_id": str(run_id) if run_id else None,
                "run_status": RunStatus.FAILED,
                **sub_agent_info,
            },
        )

    # RunCancelledEvent -> AGENT_RESPONSE_INTERRUPTED
    if isinstance(event, RunCancelledEvent):
        return AgentResponseInterruptedEvent(
            run_id=run_id,
            session_id=session_uuid,
            content={
                "origin": origin,
                "message": event.reason or "Agent run was cancelled",
                "run_id": str(run_id) if run_id else None,
                "run_status": RunStatus.CANCELLED,
                **sub_agent_info,
            },
        )

    # RunPausedEvent -> TOOL_CONFIRMATION (if tools require confirmation)
    if isinstance(event, RunPausedEvent):
        tools_data = []
        if event.tools:
            for tool in event.tools:
                tool_data = {
                    "tool_call_id": tool.tool_call_id if hasattr(tool, "tool_call_id") else None,
                    "tool_name": tool.tool_name if hasattr(tool, "tool_name") else None,
                    "tool_input": tool.tool_args if hasattr(tool, "tool_args") else None,
                    "requires_confirmation": tool.requires_confirmation
                    if hasattr(tool, "requires_confirmation")
                    else False,
                    "requires_user_input": tool.requires_user_input
                    if hasattr(tool, "requires_user_input")
                    else False,
                    "external_execution_required": tool.external_execution_required
                    if hasattr(tool, "external_execution_required")
                    else False,
                }

                # Include user input schema if present
                if hasattr(tool, "user_input_schema") and tool.user_input_schema:
                    tool_data["user_input_schema"] = [
                        field.to_dict() for field in tool.user_input_schema
                    ]

                tools_data.append(tool_data)

        # Build comprehensive requirements data
        requirements_data = []
        if event.requirements:
            for req in event.requirements:
                req_data = {
                    "id": getattr(req, "id", None),
                    "needs_confirmation": req.needs_confirmation,
                    "needs_user_input": req.needs_user_input,
                    "needs_external_execution": req.needs_external_execution,
                    "is_resolved": req.is_resolved(),
                }

                # Include tool execution details
                if req.tool_execution:
                    req_data["tool_execution"] = {
                        "tool_call_id": req.tool_execution.tool_call_id,
                        "tool_name": req.tool_execution.tool_name,
                        "tool_args": req.tool_execution.tool_args,
                        "requires_confirmation": req.tool_execution.requires_confirmation,
                        "requires_user_input": req.tool_execution.requires_user_input,
                        "external_execution_required": req.tool_execution.external_execution_required,
                    }

                    # Include user input schema if present
                    if req.tool_execution.user_input_schema:
                        req_data["tool_execution"]["user_input_schema"] = [
                            field.to_dict() for field in req.tool_execution.user_input_schema
                        ]

                requirements_data.append(req_data)

        # Get active (unresolved) requirements
        active_requirements = []
        if hasattr(event, "active_requirements"):
            for req in event.active_requirements:
                active_req_data = {
                    "id": getattr(req, "id", None),
                    "needs_confirmation": req.needs_confirmation,
                    "needs_user_input": req.needs_user_input,
                    "needs_external_execution": req.needs_external_execution,
                }

                if req.tool_execution:
                    active_req_data["tool_execution"] = {
                        "tool_call_id": req.tool_execution.tool_call_id,
                        "tool_name": req.tool_execution.tool_name,
                        "tool_args": req.tool_execution.tool_args,
                    }

                    # Include user input schema for active requirements
                    if req.tool_execution.user_input_schema:
                        active_req_data["user_input_schema"] = [
                            field.to_dict() for field in req.tool_execution.user_input_schema
                        ]

                active_requirements.append(active_req_data)

        return AgentToolConfirmationEvent(
            run_id=run_id,
            session_id=session_uuid,
            content={
                "origin": origin,
                "message": "Agent is paused awaiting confirmation",
                "tools": tools_data,
                "requirements": requirements_data,
                "active_requirements": active_requirements,
                "run_id": str(run_id) if run_id else None,
                "run_status": RunStatus.PAUSED,
                **sub_agent_info,
            },
        )

    # RunContinuedEvent -> PROCESSING
    if isinstance(event, RunContinuedEvent):
        return AgentProcessingEvent(
            run_id=run_id,
            session_id=session_uuid,
            content={
                "origin": origin,
                "message": "Agent resumed processing...",
                "run_id": str(run_id) if run_id else None,
                "run_status": RunStatus.RUNNING,
                **sub_agent_info,
            },
        )

    # ReasoningStartedEvent -> AGENT_REASONING_START
    if isinstance(event, ReasoningStartedEvent):
        return AgentReasoningStartEvent(
            run_id=run_id,
            session_id=session_uuid,
            content={
                "origin": origin,
                "run_id": str(run_id) if run_id else None,
                **sub_agent_info,
            },
        )

    # ReasoningDeltaEvent -> AGENT_REASONING_DELTA (streaming reasoning tokens)
    if isinstance(event, ReasoningDeltaEvent):
        # Use redacted content if available, otherwise use regular content
        reasoning_text = (
            event.redacted_reasoning_content if event.is_redacted else event.reasoning_content
        )
        return AgentReasoningDeltaEvent(
            run_id=run_id,
            session_id=session_uuid,
            content={
                "origin": origin,
                "text": reasoning_text or "",
                "is_redacted": event.is_redacted,
                "run_id": str(run_id) if run_id else None,
                **sub_agent_info,
            },
        )

    # RunContentDeltaEvent -> AGENT_RESPONSE_DELTA (streaming response tokens)
    if isinstance(event, RunContentDeltaEvent):
        return AgentResponseDeltaEvent(
            run_id=run_id,
            session_id=session_uuid,
            content={
                "origin": origin,
                "text": event.content or "",
                "run_id": str(run_id) if run_id else None,
                **sub_agent_info,
            },
        )

    # ReasoningCompletedEvent -> AGENT_REASONING
    if isinstance(event, ReasoningCompletedEvent):
        return AgentReasoningEvent(
            run_id=run_id,
            session_id=session_uuid,
            content={
                "origin": origin,
                "text": event.content,
                "run_id": str(run_id) if run_id else None,
                **sub_agent_info,
            },
        )

    if isinstance(event, SandboxInitializedEvent):
        status_val = event.sandbox_info.status if event.sandbox_info else None
        # Normalize status to match the Literal constraint
        valid_statuses = {"starting", "ready", "paused", "terminated", "error"}
        normalized_status = status_val if status_val in valid_statuses else "starting"
        _vscode_url = event.sandbox_info.vscode_url if event.sandbox_info else None
        _vnc_url = event.sandbox_info.vnc_url if event.sandbox_info else None
        return SandboxStatusChangedEvent(
            run_id=run_id,
            session_id=session_uuid,
            status=normalized_status,
            vscode_url=_vscode_url,
            vnc_url=_vnc_url,
            content={
                "origin": origin,
                "status": status_val,
                "vscode_url": _vscode_url,
                "vnc_url": _vnc_url,
                "run_id": str(run_id) if run_id else None,
                **sub_agent_info,
            },
        )

    # ToolCallStartedEvent -> TOOL_CALL
    if isinstance(event, ToolCallStartedEvent):
        tool = event.tool
        tool_data = {"origin": origin}
        if tool:
            tool_data.update(
                {
                    "tool_call_id": tool.tool_call_id if hasattr(tool, "tool_call_id") else None,
                    "tool_name": tool.tool_name if hasattr(tool, "tool_name") else None,
                    "tool_input": tool.tool_args if hasattr(tool, "tool_args") else None,
                    "tool_display_name": tool.display_name
                    if hasattr(tool, "display_name") and tool.display_name
                    else tool.tool_name,
                    "tool_logo": tool.tool_logo if hasattr(tool, "tool_logo") else None,
                }
            )
        # Include sub-agent info in tool_data
        tool_data.update(sub_agent_info)
        tool_data["run_id"] = str(run_id) if run_id else None
        return AgentToolCallEvent(
            run_id=run_id,
            session_id=session_uuid,
            tool_name=tool.tool_name if tool and hasattr(tool, "tool_name") else "",
            tool_call_id=tool.tool_call_id if tool and hasattr(tool, "tool_call_id") else "",
            content=tool_data,
        )

    # ToolCallCompletedEvent -> TOOL_RESULT
    if isinstance(event, ToolCallCompletedEvent):
        from ii_agent.agents.tools.base import ToolResult as BaseToolResult

        tool = event.tool
        result_for_display = tool.result
        is_error = False
        tool_cost = 0.0

        # If result is a BaseToolResult, extract user_display_content for websocket display
        # user_display_content can be a string, dict, or list - pass it directly to frontend
        if isinstance(tool.result, BaseToolResult):
            is_error = tool.result.is_error or False
            tool_cost = tool.result.cost
            # Use user_display_content if available, otherwise fallback to llm_content
            if tool.result.user_display_content is not None:
                result_for_display = tool.result.user_display_content
            else:
                llm_content = tool.result.llm_content
                if isinstance(llm_content, str):
                    result_for_display = llm_content
                elif isinstance(llm_content, list):
                    # Convert content objects to dicts for JSON serialization
                    result_for_display = [
                        content.model_dump() if hasattr(content, "model_dump") else str(content)
                        for content in llm_content
                    ]
                else:
                    result_for_display = str(llm_content)

        tool_data = {
            "origin": origin,
            "result": result_for_display,
            "is_error": is_error,
            "cost": tool_cost,
        }
        if tool:
            tool_data.update(
                {
                    "tool_call_id": tool.tool_call_id if hasattr(tool, "tool_call_id") else None,
                    "tool_name": tool.tool_name if hasattr(tool, "tool_name") else None,
                    "tool_input": tool.tool_args if hasattr(tool, "tool_args") else None,
                    "tool_display_name": tool.display_name
                    if hasattr(tool, "display_name") and tool.display_name
                    else tool.tool_name,
                    "tool_logo": tool.tool_logo if hasattr(tool, "tool_logo") else None,
                }
            )
        # Include sub-agent info in tool_data
        tool_data.update(sub_agent_info)
        tool_data["run_id"] = str(run_id) if run_id else None
        return AgentToolResultEvent(
            run_id=run_id,
            session_id=session_uuid,
            tool_name=tool.tool_name if tool and hasattr(tool, "tool_name") else "",
            tool_call_id=tool.tool_call_id if tool and hasattr(tool, "tool_call_id") else "",
            content=tool_data,
        )

    # AgentSummaryStartedEvent -> Skip (wait for completed event)
    if isinstance(event, AgentSummaryStartedEvent):
        return None

    # AgentSummaryCompletedEvent -> MODEL_COMPACT
    if isinstance(event, AgentSummaryCompletedEvent):
        summary_content = None
        if hasattr(event, "session_summary") and event.session_summary:
            summary_content = event.session_summary.content

        return AgentModelCompactEvent(
            run_id=run_id,
            session_id=session_uuid,
            content={
                "origin": origin,
                "status": "compacted",
                "summary": summary_content,
                "run_id": str(run_id) if run_id else None,
                **sub_agent_info,
            },
        )

    # For any unhandled event types, return None to skip
    return None
