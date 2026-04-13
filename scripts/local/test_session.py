#!/usr/bin/env python3
"""Create an agent session via Socket.IO and send a prompt, then monitor SSE events."""

import asyncio
import json
import os
import sys
import time
import uuid

import socketio

BACKEND_URL = "http://localhost:8000"
TOKEN = os.environ.get(
    "TOKEN",
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VyX2lkIjoiM2EzODQ1MmEtMWQ0ZS00MTIyLWE4YzYtNWNlNWM3OTkzNGVlIiwiZW1haWwiOiJkZXZAbG9jYWxob3N0Iiwicm9sZSI6InVzZXIiLCJ0eXBlIjoiYWNjZXNzIiwiZXhwIjoxNzc4NDQ2OTg0LCJpYXQiOjE3NzU4NTQ5ODR9.-Y8dDmYHux8qlZwBdixMnczZ44C4vV5apImR_Fg9jbg",
)
USER_ID = "3a38452a-1d4e-4122-a8c6-5ce5c79934ee"

PROMPT = os.environ.get(
    "PROMPT",
    "Please have me sign into Walmart.ca and set the following order for delivery "
    "to 6000 Perth St, Richmond, Ontario K0A2Z0. Stop at appropriate points and "
    "ask me to live login to the shopping and delivery service and solve the captchas",
)
SESSION_ID = os.environ.get("SESSION_ID", "")


async def main():
    print(f"Prompt: {PROMPT[:80]}...")
    print("---")

    # Create Socket.IO client
    sio = socketio.AsyncClient(
        reconnection=False,
        logger=False,
        engineio_logger=False,
    )

    events_received = []
    connected = asyncio.Event()
    done = asyncio.Event()
    joined = asyncio.Event()
    actual_session_id = [None]  # Will be set by system event
    start_time = time.monotonic()

    @sio.event
    async def connect():
        print(f"[{_elapsed()}] Connected to Socket.IO")
        connected.set()

    @sio.event
    async def disconnect():
        print(f"[{_elapsed()}] Disconnected")
        done.set()

    @sio.event
    async def connect_error(data):
        print(f"[{_elapsed()}] Connection error: {data}")
        done.set()

    @sio.on("*")
    async def catch_all(event, data):
        elapsed = _elapsed()
        events_received.append((elapsed, event, data))
        
        # Parse and display key events
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except (json.JSONDecodeError, TypeError):
                pass

        if isinstance(data, dict):
            event_name = data.get("name", data.get("type", data.get("event", "")))
            group = data.get("group", "")
            content = data.get("content", {})
            
            # Capture session_id from connection.established event
            if isinstance(content, dict) and content.get("session_id"):
                sid = content["session_id"]
                if not actual_session_id[0]:
                    actual_session_id[0] = sid
                    print(f"\n[{elapsed}] SESSION CREATED: {sid}")
                    print(f"  Frontend URL: http://192.168.2.2:1420/{sid}")
                    joined.set()
                    return
            
            # Count reasoning deltas (high volume)
            if event_name == "agent.reasoning.delta":
                text = content.get("text", "") if isinstance(content, dict) else ""
                sys.stdout.write(f"💭")
                sys.stdout.flush()
                return
            
            if event_name == "agent.reasoning.start":
                print(f"\n[{elapsed}] REASONING STARTED")
                return

            if event_name == "agent.reasoning":
                text = content.get("text", "") if isinstance(content, dict) else ""
                print(f"\n[{elapsed}] REASONING COMPLETE ({len(text)} chars): {text[:150]}...")
                return

            # Tool-related events (important for A2A bridge monitoring)
            if "tool" in str(event_name).lower():
                tool_info = ""
                if isinstance(content, dict):
                    tool_info = content.get("tool_name", content.get("name", ""))
                    if not tool_info and isinstance(content.get("tool_executions"), list):
                        execs = content["tool_executions"]
                        tool_info = ", ".join(e.get("tool_name", "?") for e in execs if isinstance(e, dict))
                print(f"\n[{elapsed}] TOOL [{event_name}]: {tool_info}")
                if isinstance(content, dict) and content.get("result"):
                    result_preview = str(content["result"])[:200]
                    print(f"  Result: {result_preview}")
                return
            
            # Sandbox events
            if group == "sandbox":
                status = content.get("status", "") if isinstance(content, dict) else ""
                print(f"\n[{elapsed}] SANDBOX [{event_name}]: {status}")
                return

            # Agent response (full text)
            if event_name == "agent.response":
                text = ""
                if isinstance(content, dict):
                    text = content.get("text", content.get("content", ""))[:300]
                print(f"\n[{elapsed}] AGENT RESPONSE: {text}")
                return
            
            # Message deltas
            if "delta" in str(event_name).lower() or "message_delta" in str(event_name):
                delta = data.get("delta", data.get("text", ""))
                if not delta and isinstance(content, dict):
                    delta = content.get("text", content.get("delta", ""))
                if delta:
                    sys.stdout.write(delta)
                    sys.stdout.flush()
                return
                
            if event_name == "heartbeat":
                print(f"\n[{elapsed}] HEARTBEAT")
                return
            elif "error" in str(event_name).lower():
                print(f"\n[{elapsed}] ERROR: {json.dumps(data, default=str)[:500]}")
                return
        
        # Generic event
        summary = str(data)[:200]
        print(f"\n[{elapsed}] EVENT '{event}': {summary}")

    def _elapsed():
        return f"{time.monotonic() - start_time:.1f}s"

    try:
        # Connect with auth
        print(f"Connecting to {BACKEND_URL}...")
        await sio.connect(
            BACKEND_URL,
            auth={"token": TOKEN},
            transports=["websocket"],
            wait_timeout=10,
        )
        await connected.wait()
        
        # Join — use provided session ID or create a new session
        if SESSION_ID:
            print(f"Joining existing session: {SESSION_ID}")
            await sio.emit("join_session", {"session_uuid": SESSION_ID})
            actual_session_id[0] = SESSION_ID
            joined.set()
        else:
            print(f"Creating new session...")
            await sio.emit("join_session", {})
        
        # Wait for the session_id to come back
        try:
            await asyncio.wait_for(joined.wait(), timeout=10)
        except asyncio.TimeoutError:
            print("ERROR: Timed out waiting for session creation")
            return
        
        session_id = actual_session_id[0]
        print(f"Session ID: {session_id}")
        print(f"Frontend URL: http://192.168.2.2:1420/{session_id}")

        # Send the query
        print(f"Sending query...")
        await sio.emit(
            "chat_message",
            {
                "session_uuid": session_id,
                "content": {
                    "command": "query",
                    "text": PROMPT,
                    "model_id": "558a538b-30cc-58cc-9b6c-7dc12be34860",
                    "source": "user",
                    "agent_type": os.environ.get("AGENT_TYPE", "general"),
                    "tool_args": {},
                },
            },
        )

        # Monitor for up to 5 minutes
        print(f"Monitoring events (max 300s)...")
        print("=" * 60)
        try:
            await asyncio.wait_for(done.wait(), timeout=300)
        except asyncio.TimeoutError:
            print(f"\n\n[{_elapsed()}] Monitoring timeout (300s)")

    except Exception as e:
        print(f"Error: {e}")
    finally:
        if sio.connected:
            await sio.disconnect()
        
        print("\n" + "=" * 60)
        print(f"Total events received: {len(events_received)}")
        print(f"Total time: {_elapsed()}")
        
        # Summary
        if events_received:
            print("\nEvent summary:")
            type_counts: dict[str, int] = {}
            for _, evt, data in events_received:
                if isinstance(data, dict):
                    t = data.get("name", data.get("type", data.get("event", evt)))
                else:
                    t = evt
                type_counts[str(t)] = type_counts.get(str(t), 0) + 1
            for t, c in sorted(type_counts.items()):
                print(f"  {t}: {c}")


if __name__ == "__main__":
    asyncio.run(main())
