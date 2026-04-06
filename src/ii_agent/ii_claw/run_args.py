"""
Simple runner for call_agent / call_agent_stream.

Usage:
    # Non-streaming (collect all, print final):
    python -m ii_agent.ii_claw.run "Build a portfolio website" --agent-type website_build

    # Streaming (print events as they arrive):
    python -m ii_agent.ii_claw.run "What are AI agent trends?" --agent-type fast_research --stream

    # With tool toggles:
    python -m ii_agent.ii_claw.run "Create a todo app" --agent-type website_build --browser

    # With specific model:
    python -m ii_agent.ii_claw.run "Hello" --model-id claude-sonnet-4-20250514

    # Multi-turn (reuse session):
    python -m ii_agent.ii_claw.run "Add dark mode" --session-id <uuid-from-previous-run>
"""

import argparse
import asyncio
import json
import sys

from ii_agent.agents.types import AgentType
from ii_agent.tasks.types import RunStatus
from ii_agent.ii_claw.call_agent import CallAgentInput, CallAgentOutput, call_agent, call_agent_stream


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run II-Agent from command line")

    parser.add_argument("message", help="User message to send to agent")
    parser.add_argument("--user-id", default="cli-user", help="User ID (default: cli-user)")
    parser.add_argument(
        "--model-id", default=None,
        help="Model ID (e.g. claude-sonnet-4-20250514). Uses system default if not set.",
    )
    parser.add_argument(
        "--source", choices=["user", "system"], default="system",
        help="LLM source: 'user' (user API key) or 'system' (platform key). Default: system",
    )
    parser.add_argument(
        "--agent-type", default="general",
        choices=[t.value for t in AgentType],
        help="Agent mode (default: general)",
    )
    parser.add_argument("--session-id", default=None, help="Session ID for multi-turn")
    parser.add_argument("--stream", action="store_true", help="Stream events as they arrive")

    # Tool toggles
    parser.add_argument("--browser", action="store_true", help="Enable browser tools")
    parser.add_argument("--media", action="store_true", help="Enable media generation tools")
    parser.add_argument("--task-agent", action="store_true", help="Enable task delegation sub-agent")
    parser.add_argument("--deep-research", action="store_true", help="Enable deep research tools")

    return parser.parse_args()


def _format_event(event) -> str:
    """Format an AppEvent for terminal display."""
    from ii_agent.realtime.events.app_events import (
        AgentProcessingEvent,
        AgentResponseDeltaEvent,
        AgentResponseEvent,
        AgentToolCallEvent,
        AgentToolResultEvent,
        AgentReasoningDeltaEvent,
        AgentCompleteEvent,
        SystemErrorEvent,
    )

    if isinstance(event, AgentProcessingEvent):
        return f"[processing] {getattr(event, 'message', '')}"

    if isinstance(event, AgentResponseDeltaEvent):
        return getattr(event, "text", "")

    if isinstance(event, AgentResponseEvent):
        content = event.content if hasattr(event, "content") and isinstance(event.content, dict) else {}
        return f"\n{content.get('text', '')}"

    if isinstance(event, AgentToolCallEvent):
        return f"\n[tool_call] {getattr(event, 'tool_name', '?')}"

    if isinstance(event, AgentToolResultEvent):
        tool_name = getattr(event, "tool_name", "?")
        is_error = getattr(event, "is_error", False)
        tag = "tool_error" if is_error else "tool_result"
        content = event.content if hasattr(event, "content") and isinstance(event.content, dict) else {}
        result_preview = str(content.get("result", ""))[:200]
        return f"\n[{tag}] {tool_name}: {result_preview}"

    if isinstance(event, AgentReasoningDeltaEvent):
        text = getattr(event, "text", "")
        return f"[thinking] {text}" if text else ""

    if isinstance(event, AgentCompleteEvent):
        return "\n[complete] Done"

    if isinstance(event, SystemErrorEvent):
        return f"\n[error] {getattr(event, 'message', 'Unknown error')}"

    # Default: show event name
    name = getattr(event, "name", type(event).__name__)
    return f"\n[{name}]"


async def run_streaming(inp: CallAgentInput) -> None:
    """Run agent in streaming mode, print events as they arrive."""
    print(f"--- Streaming agent ({inp.agent_type}) ---\n")

    from ii_agent.realtime.events.app_events import AgentResponseDeltaEvent

    session_id = None
    async for event in call_agent_stream(inp):
        if session_id is None and hasattr(event, "session_id"):
            session_id = str(event.session_id)

        text = _format_event(event)
        if text:
            # AGENT_RESPONSE_DELTA should print without newline for smooth streaming
            if isinstance(event, AgentResponseDeltaEvent):
                print(text, end="", flush=True)
            else:
                print(text, flush=True)

    print(f"\n\n--- Session: {session_id} ---")


async def run_blocking(inp: CallAgentInput) -> None:
    """Run agent, wait for completion, print result."""
    print(f"--- Running agent ({inp.agent_type}) ... ---\n")

    output: CallAgentOutput = await call_agent(inp)

    if output.error:
        print(f"[ERROR] {output.error}", file=sys.stderr)
        sys.exit(1)

    print(f"Status:  {output.status.value}")
    print(f"Session: {output.session_id}")
    print(f"Run ID:  {output.run_id}")
    print(f"Events:  {len(output.events)}")
    print(f"\n--- Response ---\n")
    from ii_agent.realtime.events.app_events import AgentResponseEvent, AgentToolCallEvent

    content = output.content
    if not content:
        # Fallback: extract from AgentResponseEvent events
        response_parts = []
        for e in output.events:
            if isinstance(e, AgentResponseEvent):
                c = e.content if hasattr(e, "content") and isinstance(e.content, dict) else {}
                response_parts.append(c.get("text", ""))
        content = "\n".join(response_parts) if response_parts else "(no content)"
    print(content)

    # Print tool calls summary
    tool_events = [e for e in output.events if isinstance(e, AgentToolCallEvent)]
    if tool_events:
        print(f"\n--- Tools used ({len(tool_events)}) ---")
        for e in tool_events:
            print(f"  - {getattr(e, 'tool_name', '?')}")


async def main() -> None:
    args = parse_args()

    tool_args: dict[str, bool] = {}
    if args.browser:
        tool_args["browser"] = True
    if args.media:
        tool_args["media_generation"] = True
    if args.task_agent:
        tool_args["task_agent"] = True
    if args.deep_research:
        tool_args["deep_research"] = True

    inp = CallAgentInput(
        user_id=args.user_id,
        text=args.message,
        model_id=args.model_id,
        source=args.source,
        agent_type=AgentType(args.agent_type),
        tool_args=tool_args,
        session_id=args.session_id,
    )

    if args.stream:
        await run_streaming(inp)
    else:
        await run_blocking(inp)


if __name__ == "__main__":
    asyncio.run(main())
