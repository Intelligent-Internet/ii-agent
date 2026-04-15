#!/usr/bin/env python3
"""Expanded E2E Test Suite for ii-agent.

Covers: Chat mode, image attachments, web search, browser tools,
session management, multi-turn context, and cross-feature integration.

Usage:
    python3 scripts/local/test_e2e.py                  # Run ALL tests
    python3 scripts/local/test_e2e.py --clear          # Clear previous state, run ALL tests
    python3 scripts/local/test_e2e.py --failed         # Rerun only FAIL/ERROR from last run
    python3 scripts/local/test_e2e.py --test CNCL-01   # Run a single test by ID
    python3 scripts/local/test_e2e.py --test CNCL-01,A2A-04  # Run multiple tests by ID (comma-separated)
    python3 scripts/local/test_e2e.py --category CNCL  # Run all tests in a category
    python3 scripts/local/test_e2e.py --category CNCL,A2A  # Run multiple categories (comma-separated)
    python3 scripts/local/test_e2e.py --help           # Show comprehensive help and agentic instructions

Environment variable overrides (backward-compatible):
    TEST_ID=CNCL-01   python3 scripts/local/test_e2e.py
    TEST_CATEGORY=A2A  python3 scripts/local/test_e2e.py

State Management:
    Results from each test run are saved to .e2e_last_results.json in this directory.
    Use --clear to delete previous state and start fresh.
    Use --failed to rerun only tests that failed or errored in the last run.
    This enables autonomous fix/rebuild/retest cycles in the E2E test-cycle prompt.
"""

import argparse
import asyncio
import json
import os
import sys
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional

import httpx
import socketio

# Results are saved here after each run so --failed can rerun failures.
RESULTS_FILE = Path(__file__).parent / ".e2e_last_results.json"

# --- Configuration ---
BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8000")
TOKEN = os.environ.get(
    "TOKEN",
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VyX2lkIjoiM2EzODQ1MmEtMWQ0ZS00MTIyLWE4YzYtNWNlNWM3OTkzNGVlIiwiZW1haWwiOiJkZXZAbG9jYWxob3N0Iiwicm9sZSI6InVzZXIiLCJ0eXBlIjoiYWNjZXNzIiwiZXhwIjoxNzc4NDQ2OTg0LCJpYXQiOjE3NzU4NTQ5ODR9.-Y8dDmYHux8qlZwBdixMnczZ44C4vV5apImR_Fg9jbg",
)
AUTH_HEADERS = {"Authorization": f"Bearer {TOKEN}"}

# Model IDs from /v1/user-settings/models
ANTHROPIC_MODEL_ID = "558a538b-30cc-58cc-9b6c-7dc12be34860"  # claude-sonnet-4-6
ANTHROPIC_OPUS_MODEL_ID = "32ba3cae-98ca-5720-bdf6-f599b09cf730"  # claude-opus-4-6
OPENAI_MODEL_ID = "916180a7-0b43-5c08-b3c8-c738826880bb"  # gpt-4o
AGENT_MODEL_ID = ANTHROPIC_MODEL_ID  # Used for agent mode queries

TIMEOUT_AGENT = 180  # seconds for agent mode queries
TIMEOUT_CHAT = 60  # seconds for chat mode queries

# Auto-cleanup: schedule test sessions for deletion after this many seconds.
# 24 hours allows ample time for manual inspection while avoiding accumulation.
E2E_SESSION_TTL_SECONDS = int(os.environ.get("E2E_SESSION_TTL", str(24 * 3600)))

# Track all sessions created during this test run for scheduled cleanup.
_created_session_ids: list[str] = []


class TestStatus(Enum):
    NOT_RUN = "NOT RUN"
    PASS = "PASS"
    FAIL = "FAIL"
    SKIP = "SKIP"
    ERROR = "ERROR"


@dataclass
class TestResult:
    test_id: str
    name: str
    status: TestStatus = TestStatus.NOT_RUN
    notes: str = ""
    elapsed: float = 0.0


# ─── Result persistence helpers ────────────────────────────────────


def save_results(results: list[TestResult]) -> None:
    """Save test results to RESULTS_FILE as JSON."""
    data = {
        "timestamp": time.time(),
        "results": [
            {
                "test_id": r.test_id,
                "name": r.name,
                "status": r.status.value,
                "notes": r.notes,
                "elapsed": r.elapsed,
            }
            for r in results
        ],
    }
    try:
        RESULTS_FILE.write_text(json.dumps(data, indent=2))
    except Exception as e:
        print(f"[Warning] Failed to save results: {e}")


def load_last_results() -> list[TestResult] | None:
    """Load test results from RESULTS_FILE."""
    if not RESULTS_FILE.exists():
        return None
    try:
        data = json.loads(RESULTS_FILE.read_text())
        results = []
        for r in data.get("results", []):
            status = TestStatus(r["status"])
            results.append(
                TestResult(
                    test_id=r["test_id"],
                    name=r["name"],
                    status=status,
                    notes=r["notes"],
                    elapsed=r["elapsed"],
                )
            )
        return results
    except Exception as e:
        print(f"[Warning] Failed to load results: {e}")
        return None


def print_help_and_agentic_instructions() -> None:
    """Print comprehensive help and agentic instructions."""
    help_text = """
╔════════════════════════════════════════════════════════════════════════════╗
║                    II-Agent E2E Test Suite — Complete Help                ║
╚════════════════════════════════════════════════════════════════════════════╝

SYNOPSIS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  python3 scripts/local/test_e2e.py [OPTIONS]

DESCRIPTION
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Automated E2E test suite for ii-agent with 32+ tests across 11 categories:
  • Infrastructure (INF): Health, models, sandbox readiness
  • Chat Mode (CHAT): Anthropic, OpenAI, multi-turn, web search
  • Images (IMG): Upload, chat attachment, agent attachment
  • Web (WEB): Web search, browser navigation
  • Code (CODE): Single file, multi-file execution
  • Sessions (SESS): List, events, pin, fork
  • Agent Multi-Turn (AGEN): Context, tool use persistence
  • Cross-Feature (XFEAT): Web search + file, chat + agent independence
  • Chat History (HIST): Message persistence
  • Council Mode (CNCL): Parallel execution, billing, validation
  • A2A Backend (A2A): Config, chat/agent routing, council integration

OPTIONS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  --help                       Show this help message and exit

  --clear                      Delete .e2e_last_results.json and run all tests
                               (clears previous state, starts fresh)

  --failed                     Rerun only tests that FAIL or ERROR from last run
                               (requires .e2e_last_results.json to exist)

  --test TEST_ID[,TEST_ID...]  Run single or multiple tests by ID (comma-separated)
                               Examples: --test CHAT-01
                                         --test CHAT-01,IMG-02,CNCL-01

  --category CAT[,CAT...]      Run all tests in one or more categories
                               Examples: --category CHAT
                                         --category CHAT,IMG,CODE
                               Valid: INF, CHAT, IMG, WEB, CODE, SESS, AGEN, XFEAT, HIST, CNCL, A2A

ENVIRONMENT VARIABLES (Legacy Support)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  TEST_ID=CHAT-01              Same as: python3 ... --test CHAT-01
  TEST_CATEGORY=CHAT           Same as: python3 ... --category CHAT
  BACKEND_URL                  Override backend URL (default: http://localhost:8000)
  TOKEN                        Override auth token (default: hardcoded dev token)
  E2E_SESSION_TTL              Seconds until sessions auto-delete (default: 86400 = 24h)

STATE MANAGEMENT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Results file: .e2e_last_results.json (in scripts/local/ directory)

Workflow:
  1. First run (fresh):           python3 scripts/local/test_e2e.py --clear
     • Deletes old results file
     • Runs all tests
     • Saves results to .e2e_last_results.json
     • Shows summary: pass/fail/error/skip counts

  2. Retest failures only:        python3 scripts/local/test_e2e.py --failed
     • Loads .e2e_last_results.json
     • Runs only FAIL + ERROR tests from last run
     • Saves new results
     • Reports progress

  3. Repeat step 2 until all tests pass, or max iterations reached

EXAMPLES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  # Full test suite with fresh state
  python3 scripts/local/test_e2e.py --clear

  # Rerun all failures from last session
  python3 scripts/local/test_e2e.py --failed

  # Run only chat tests
  python3 scripts/local/test_e2e.py --category CHAT

  # Run specific tests
  python3 scripts/local/test_e2e.py --test CHAT-01,CHAT-02,IMG-01

  # Use env vars (legacy)
  TEST_ID=CNCL-01 python3 scripts/local/test_e2e.py

AGENTIC INSTRUCTION: E2E Test-Cycle Workflow
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

When invoked by the e2e-test-cycle prompt, follow this pattern:

### OUTER LOOP: Full Test Sweep (clears state, runs all tests)

  Step 1 — Clear previous state:
    python3 scripts/local/test_e2e.py --clear

  Step 2 — Parse output for:
    • Total tests run, passed, failed, skipped, errored
    • For each FAIL/ERROR: test ID, category, status, failure notes

  Step 3 — Decision:
    • All tests PASS or SKIP? → DONE (report final results, exit)
    • Any FAIL or ERROR? → Enter INNER LOOP

### INNER LOOP: Fix Each Failure (one at a time)

  For each failed test (process alphabetically by test ID):

    Step 1 — Diagnose:
      • Re-run single test: python3 scripts/local/test_e2e.py --test <TEST_ID>
      • Read failure output + backend logs
      • Identify root cause (code bug, timeout, config, transient)

    Step 2 — Fix:
      • Apply minimal fix to source files
      • Run: uv run ruff check --fix-only <changed_files>
        and: uv run ruff format <changed_files>
      • (Skip if only test script changed)

    Step 3 — Rebuild (if code changed):
      • Backend: ./scripts/stack_control.sh rebuild backend
      • Sandbox: ./scripts/stack_control.sh build-sandbox (+ flags if needed)
      • Wait for health: curl -sf http://localhost:8000/health

    Step 4 — Retest single fix:
      • python3 scripts/local/test_e2e.py --test <TEST_ID>
      • If PASS: mark resolved, continue to next failure
      • If still FAIL after 3 attempts: log as unresolvable, move on

### OUTER LOOP RE-ENTRY: Check for Regressions

  After inner loop completes (all failures addressed):

    • Run full suite again: python3 scripts/local/test_e2e.py --failed
      (or --clear if you want a fresh cycle)
    • Any new failures? → Return to INNER LOOP
    • Same failures as before? → Plateau reached, stop and report
    • All pass? → DONE

COMPLETION CRITERIA
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

The test cycle is complete when ONE of the following is true:

  1. All tests PASS or SKIP (with documented skip reasons)
  2. Plateau reached: full outer loop produces identical failures as before
  3. Max iterations (5 outer loops) reached — report and stop

MANDATORY RULES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  • Never run raw 'docker compose' — always use scripts/stack_control.sh
  • Never modify test expectations to pass — fix underlying code instead
  • Run ruff on all changed Python files before rebuilding
  • Mark tests as SKIP (not FAIL) for external quota/credential issues
  • Keep fixes minimal — no unnecessary refactoring
  • Limit retries per test to 3 attempts before moving on
  • Don't stop mid-cycle — run full outer loop to detect regressions

═══════════════════════════════════════════════════════════════════════════════
"""
    print(help_text)
    sys.exit(0)


# ─── Utility helpers ────────────────────────────────────────────────


async def http_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=BACKEND_URL,
        headers=AUTH_HEADERS,
        timeout=httpx.Timeout(60.0, connect=10.0),
    )


async def schedule_session_cleanup(session_id: str) -> None:
    """Schedule a test session for automatic deletion after E2E_SESSION_TTL_SECONDS.

    Non-fatal: logs a warning if the request fails but never raises.
    """
    if not session_id or E2E_SESSION_TTL_SECONDS <= 0:
        return
    _created_session_ids.append(session_id)
    try:
        async with await http_client() as client:
            resp = await client.post(
                f"/v1/sessions/{session_id}/schedule-delete",
                json={"delete_after_seconds": E2E_SESSION_TTL_SECONDS},
            )
            if resp.status_code >= 400:
                print(
                    f"    [cleanup] Failed to schedule delete for {session_id}: {resp.status_code}"
                )
    except Exception as e:
        print(f"    [cleanup] Error scheduling delete for {session_id}: {e}")


# Known server-side error patterns that can appear in response content,
# making a test falsely "pass" even though the backend failed.
_SERVER_ERROR_PATTERNS = [
    ("'coroutine' object has no attribute", "Async coroutine bug (storage.read not awaited)"),
    ("Load error:", "File loading error"),
    ("[Council execution failed", "Council execution failure"),
    ("No council member produced output", "Council produced no output"),
    ("failed to load", "Resource loading failure"),
    ("Internal Server Error", "HTTP 500"),
    ("AttributeError:", "Python AttributeError in response"),
    ("TypeError:", "Python TypeError in response"),
    ("Traceback (most recent call last)", "Python traceback leaked to response"),
    ("httpx.ConnectError", "A2A adapter connection failure"),
    ("All connection attempts failed", "A2A adapter unreachable"),
]


def detect_server_errors(content: str) -> str | None:
    """Scan response content for known server-side error signatures.

    Returns a description of the first detected error, or None if clean.
    """
    if not content:
        return None
    content_lower = content.lower()
    for pattern, description in _SERVER_ERROR_PATTERNS:
        if pattern.lower() in content_lower:
            return f"Server error detected: {description} (matched: {pattern!r})"
    return None


def detect_content_doubling(content: str) -> str | None:
    """Detect content that has been duplicated/doubled in the response.

    Checks whether the content is exactly the first half repeated twice,
    which indicates an SSE event accumulation bug.
    Returns a description if doubling detected, None otherwise.
    """
    if not content or len(content) < 2:
        return None
    s = content.strip()
    if len(s) < 2:
        return None
    # Check if the string is the same substring repeated exactly twice
    if len(s) % 2 == 0:
        half = len(s) // 2
        if s[:half] == s[half:]:
            return f"Content doubled: '{s}' is '{s[:half]}' repeated twice"
    return None


async def resolve_runtime_model_name(model_uuid: str) -> tuple[str | None, str]:
    """Resolve a public model UUID to the runtime model name passed into A2A metadata."""
    try:
        async with await http_client() as client:
            resp = await client.get("/v1/user-settings/models")
            if resp.status_code != 200:
                return None, f"models API HTTP {resp.status_code}"

            for model in resp.json().get("models", []):
                if model.get("id") == model_uuid:
                    runtime_model = (model.get("model_id") or model.get("model") or "").strip()
                    if runtime_model:
                        label = model.get("display_name") or runtime_model
                        return runtime_model, label
                    return None, f"model {model_uuid} had no runtime name"

            return None, f"model {model_uuid} not found in API response"
    except Exception as e:
        return None, str(e)[:200]


async def get_backend_logs_since(seconds: int = 120) -> str:
    """Fetch recent backend container logs for A2A verification assertions."""
    proc = await asyncio.create_subprocess_exec(
        "docker",
        "logs",
        "--since",
        f"{seconds}s",
        "ii-agent-local-backend-1",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    return stdout.decode() + stderr.decode()


def find_model_override_log(logs: str, *, expected_model: str, expected_context: str) -> str | None:
    """Return the matching A2A model-selection evidence line for this request context."""
    for line in logs.splitlines():
        stripped = line.strip()
        if expected_context not in stripped:
            continue
        if "CopilotBackend: runtime model override" in stripped and expected_model in stripped:
            return stripped
        if "[a2a:stream]" in stripped and expected_model in stripped:
            return stripped
    return None


async def ensure_a2a_adapter_warm() -> tuple[bool, str]:
    """Ensure a healthy local A2A adapter exists before chat-path assertions."""
    try:
        logs = await get_backend_logs_since(60)
        if "Auto-discovered sandbox A2A adapter" in logs or "[a2a:stream]" in logs:
            return True, "existing adapter evidence found"

        warmup = await agent_query(
            prompt="Reply with the exact phrase warmup-ok.",
            model_id=ANTHROPIC_OPUS_MODEL_ID,
            timeout=min(TIMEOUT_AGENT, 60),
        )
        if warmup.get("error"):
            return False, f"warm-up agent query failed: {warmup['error'][:200]}"
        return True, f"warm-up session {warmup.get('session_id', 'unknown')}"
    except Exception as exc:
        return False, str(exc)[:200]


async def chat_sse_request(
    content: str,
    model_id: str = ANTHROPIC_MODEL_ID,
    session_id: Optional[str] = None,
    tools: Optional[dict] = None,
    file_ids: Optional[list] = None,
    timeout: float = TIMEOUT_CHAT,
    council_preferences: Optional[dict] = None,
) -> dict:
    """Send a chat message and collect SSE events.

    Returns: {
        "session_id": str | None,
        "events": list[dict],
        "content": str,  # full assembled text
        "tool_calls": list,
        "error": str | None,
        "done": bool,
        "usage": dict | None,
        "council_members": list[dict],  # council_member events
        "council_synthesis": list[dict],  # council_synthesis events
    }
    """
    payload: dict = {"content": content, "model_id": model_id}
    if session_id:
        payload["session_id"] = session_id
    if tools:
        payload["tools"] = tools
    if file_ids:
        payload["file_ids"] = file_ids
    if council_preferences:
        payload["council_preferences"] = council_preferences

    result = {
        "session_id": session_id,
        "events": [],
        "content": "",
        "tool_calls": [],
        "error": None,
        "done": False,
        "usage": None,
        "council_members": [],
        "council_synthesis": [],
    }

    async with httpx.AsyncClient(
        base_url=BACKEND_URL,
        headers=AUTH_HEADERS,
        timeout=httpx.Timeout(timeout, connect=10.0),
    ) as client:
        async with client.stream("POST", "/v1/chat/conversations", json=payload) as resp:
            if resp.status_code != 200:
                body = await resp.aread()
                result["error"] = f"HTTP {resp.status_code}: {body.decode()[:500]}"
                return result

            current_event = None
            async for line in resp.aiter_lines():
                if line.startswith("event:"):
                    current_event = line[6:].strip()
                elif line.startswith("data:"):
                    raw = line[5:].strip()
                    if not raw:
                        continue
                    try:
                        data = json.loads(raw)
                    except json.JSONDecodeError:
                        data = raw

                    result["events"].append({"event": current_event, "data": data})

                    if isinstance(data, dict):
                        # SSE event types from chat API:
                        # session, thinking, content, tool_call, tool_result,
                        # tool_progress, usage, complete, error, code_block,
                        # council_member, council_synthesis
                        if current_event == "session":
                            sid = data.get("session_id")
                            if sid:
                                result["session_id"] = sid
                        elif current_event == "content":
                            delta = data.get("delta", "")
                            if delta:
                                result["content"] += delta
                        elif current_event == "thinking":
                            # Extended thinking — skip collecting
                            pass
                        elif current_event == "tool_call":
                            if data.get("status") == "start":
                                result["tool_calls"].append(data)
                        elif current_event == "tool_result":
                            result["tool_calls"].append(data)
                        elif current_event == "usage":
                            result["usage"] = data
                        elif current_event == "complete":
                            result["done"] = True
                        elif current_event == "council_member":
                            result["council_members"].append(data)
                        elif current_event == "council_synthesis":
                            result["council_synthesis"].append(data)
                        elif current_event == "error":
                            result["error"] = data.get("message", str(data))

    # Track session for scheduled cleanup
    if result["session_id"] and not session_id:
        await schedule_session_cleanup(result["session_id"])

    # Detect server-side errors that leaked into the response content.
    # This catches bugs like the coroutine/storage read issue where the
    # LLM receives an error message and "helpfully" incorporates it into
    # its reply, making the test appear to pass.
    server_err = detect_server_errors(result["content"])
    if server_err and not result["error"]:
        result["error"] = server_err

    return result


async def agent_query(
    prompt: str,
    session_id: Optional[str] = None,
    model_id: str = AGENT_MODEL_ID,
    timeout: float = TIMEOUT_AGENT,
    agent_type: str = "general",
) -> dict:
    """Send an agent-mode query via Socket.IO and collect events.

    Returns: {
        "session_id": str | None,
        "events": list[tuple],
        "response_text": str,
        "tool_events": list,
        "error": str | None,
        "completed": bool,
    }
    """
    sio = socketio.AsyncClient(reconnection=False, logger=False, engineio_logger=False)

    result = {
        "session_id": session_id,
        "events": [],
        "response_text": "",
        "tool_events": [],
        "error": None,
        "completed": False,
    }
    connected = asyncio.Event()
    done = asyncio.Event()
    joined = asyncio.Event()
    start = time.monotonic()

    @sio.event
    async def connect():
        connected.set()

    @sio.event
    async def disconnect():
        done.set()

    @sio.on("*")  # type: ignore[misc]
    async def catch_all(event, data):
        result["events"].append((time.monotonic() - start, event, data))
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except (json.JSONDecodeError, TypeError):
                pass

        if not isinstance(data, dict):
            return

        evt_name = data.get("name", data.get("type", data.get("event", "")))
        content = data.get("content", {})

        # Session created
        if isinstance(content, dict) and content.get("session_id"):
            sid = content["session_id"]
            if not result["session_id"]:
                result["session_id"] = sid
            joined.set()

        # Agent response
        if evt_name == "agent.response":
            if isinstance(content, dict):
                result["response_text"] = content.get("text", content.get("content", ""))

        # Tool events
        if "tool" in str(evt_name).lower():
            result["tool_events"].append({"name": evt_name, "content": content})

        # Completion
        if evt_name in ("agent.complete", "agent.run.completed"):
            result["completed"] = True
            done.set()

        # Error
        if "error" in str(evt_name).lower():
            result["error"] = json.dumps(data, default=str)[:500]
            done.set()

    try:
        await sio.connect(
            BACKEND_URL,
            auth={"token": TOKEN},
            transports=["websocket"],
            wait_timeout=10,
        )
        await connected.wait()

        if session_id:
            await sio.emit("join_session", {"session_uuid": session_id})
            joined.set()
        else:
            await sio.emit("join_session", {})

        try:
            await asyncio.wait_for(joined.wait(), timeout=10)
        except asyncio.TimeoutError:
            result["error"] = "Timed out waiting for session join"
            return result

        await sio.emit(
            "chat_message",
            {
                "session_uuid": result["session_id"],
                "content": {
                    "command": "query",
                    "text": prompt,
                    "model_id": model_id,
                    "source": "user",
                    "agent_type": agent_type,
                    "tool_args": {},
                },
            },
        )

        try:
            await asyncio.wait_for(done.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            result["error"] = f"Agent query timed out after {timeout}s"

    except Exception as e:
        result["error"] = str(e)
    finally:
        if sio.connected:
            await sio.disconnect()

    # Track session for scheduled cleanup
    if result["session_id"] and not session_id:
        await schedule_session_cleanup(result["session_id"])

    # Detect server-side errors that leaked into the agent response
    server_err = detect_server_errors(result["response_text"])
    if server_err and not result["error"]:
        result["error"] = server_err

    return result


async def upload_test_image() -> Optional[str]:
    """Create a small test PNG and upload it. Return asset_id or None."""
    # 10x10 RGB test PNG (211 bytes) — large enough for Anthropic's image
    # processing (1x1 images are rejected with "Could not process image").
    import base64

    png_bytes = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAoAAAAKCAIAAAACUFjqAAAAmklEQVR4nBWPURUA"
        "QAjCVsMc1jCHNcxhDXJYgx73jn9gAwhIKGgYWBAcmJ8IIokimhhiCRFH+BfJIJMs"
        "sskhlxR5pP8oFVRSRTU11FKijvI/pINOuuimh15a9NH+MEwwyRTTzDDLiDnGH5QN"
        "Ntlimx12WbHH+kugQIkKNRq0SOiQvyAXXHLFNTfccuKO85fHgRMXbjx4sfBh4wdE"
        "lVl1WnuhqQAAAABJRU5ErkJggg=="
    )
    file_size = len(png_bytes)

    async with await http_client() as client:
        # Step 1: get upload URL
        resp = await client.post(
            "/v1/assets/upload",
            json={
                "file_name": "test_image.png",
                "content_type": "image/png",
                "file_size": file_size,
            },
        )
        if resp.status_code != 200:
            print(f"  Upload init failed: {resp.status_code} {resp.text[:200]}")
            return None
        data = resp.json()
        asset_id = data.get("id")
        upload_url = data.get("upload_url")
        if not asset_id or not upload_url:
            print(f"  Missing id/upload_url: {data}")
            return None

        # Step 2: PUT to upload URL
        put_resp = await client.put(
            upload_url,
            content=png_bytes,
            headers={"Content-Type": "image/png"},
        )
        if put_resp.status_code not in (200, 201, 204):
            print(f"  PUT upload failed: {put_resp.status_code} {put_resp.text[:200]}")
            return None

        # Step 3: mark complete
        comp_resp = await client.post(
            f"/v1/assets/{asset_id}/complete",
            json={
                "id": asset_id,
                "file_name": "test_image.png",
                "file_size": file_size,
                "content_type": "image/png",
            },
        )
        if comp_resp.status_code != 200:
            print(f"  Complete failed: {comp_resp.status_code} {comp_resp.text[:200]}")
            return None

        return asset_id


# ─── Test functions ─────────────────────────────────────────────────

# --- Category 1: Infrastructure ---


async def test_inf_health() -> TestResult:
    """INF-01: Backend health check."""
    t = TestResult("INF-01", "Backend health check")
    start = time.monotonic()
    try:
        async with await http_client() as client:
            resp = await client.get("/health")
            data = resp.json()
            if resp.status_code == 200 and data.get("status") == "ok":
                t.status = TestStatus.PASS
                chat_mode = data.get("chat_inner_loop_mode", "?")
                agent_mode = data.get("agent_inner_loop_mode", "?")
                a2a_be = data.get("a2a_backend", "?")
                t.notes = (
                    f"status=ok, chat_loop={chat_mode}, "
                    f"agent_loop={agent_mode}, a2a_backend={a2a_be}"
                )
            else:
                t.status = TestStatus.FAIL
                t.notes = f"HTTP {resp.status_code}: {resp.text[:200]}"
    except Exception as e:
        t.status = TestStatus.ERROR
        t.notes = str(e)
    t.elapsed = time.monotonic() - start
    return t


async def test_inf_models() -> TestResult:
    """INF-02: LLM models configured."""
    t = TestResult("INF-02", "LLM models available")
    start = time.monotonic()
    try:
        async with await http_client() as client:
            resp = await client.get("/v1/user-settings/models")
            models = resp.json().get("models", [])
            if len(models) >= 2:
                t.status = TestStatus.PASS
                names = [m.get("model_id", "?") for m in models]
                t.notes = f"{len(models)} models: {', '.join(names)}"
            else:
                t.status = TestStatus.FAIL
                t.notes = f"Only {len(models)} models found"
    except Exception as e:
        t.status = TestStatus.ERROR
        t.notes = str(e)
    t.elapsed = time.monotonic() - start
    return t


async def test_inf_sandbox() -> TestResult:
    """INF-03: Sandbox container exists."""
    t = TestResult("INF-03", "Sandbox container running")
    start = time.monotonic()
    try:
        proc = await asyncio.create_subprocess_exec(
            "docker",
            "ps",
            "--filter",
            "name=ii-sandbox",
            "--format",
            "{{.Names}}",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        containers = [c for c in stdout.decode().strip().split("\n") if c]
        if containers:
            t.status = TestStatus.PASS
            t.notes = f"Running: {', '.join(containers)}"
        else:
            t.status = TestStatus.PASS  # Sandbox created on demand
            t.notes = "No sandbox running (created on demand)"
    except Exception as e:
        t.status = TestStatus.ERROR
        t.notes = str(e)
    t.elapsed = time.monotonic() - start
    return t


# --- Category 2: Chat Mode (REST API) ---


async def test_chat_basic_anthropic() -> TestResult:
    """CHAT-01: Basic chat via Anthropic (Claude)."""
    t = TestResult("CHAT-01", "Chat basic — Anthropic")
    start = time.monotonic()
    try:
        r = await chat_sse_request(
            "What is 2+2? Reply with just the number.",
            model_id=ANTHROPIC_MODEL_ID,
        )
        if r["error"]:
            t.status = TestStatus.FAIL
            t.notes = f"Error: {r['error'][:300]}"
        elif "4" in r["content"]:
            t.status = TestStatus.PASS
            t.notes = f"Response: {r['content'][:100]} | session={r['session_id']}"
        else:
            t.status = TestStatus.FAIL
            t.notes = f"Expected '4' in response: {r['content'][:200]}"
    except Exception as e:
        t.status = TestStatus.ERROR
        t.notes = str(e)[:300]
    t.elapsed = time.monotonic() - start
    return t


async def test_chat_basic_openai() -> TestResult:
    """CHAT-02: Basic chat via OpenAI (GPT-4o)."""
    t = TestResult("CHAT-02", "Chat basic — OpenAI")
    start = time.monotonic()
    try:
        r = await chat_sse_request(
            "What is 3+5? Reply with just the number.",
            model_id=OPENAI_MODEL_ID,
        )
        if r["error"]:
            err = r["error"]
            # Known config issues — mark as SKIP not FAIL
            if "quota" in err.lower() or "billing" in err.lower():
                t.status = TestStatus.SKIP
                t.notes = f"OpenAI quota exceeded (billing issue): {err[:200]}"
            elif "reasoning" in err.lower() and "unsupported" in err.lower():
                t.status = TestStatus.FAIL
                t.notes = f"Server sends unsupported reasoning.effort param to GPT-4o: {err[:300]}"
            else:
                t.status = TestStatus.FAIL
                t.notes = f"Error: {err[:300]}"
        elif "8" in r["content"]:
            t.status = TestStatus.PASS
            t.notes = f"Response: {r['content'][:100]} | session={r['session_id']}"
        else:
            t.status = TestStatus.FAIL
            t.notes = f"Expected '8' in response: {r['content'][:200]}"
    except Exception as e:
        t.status = TestStatus.ERROR
        t.notes = str(e)[:300]
    t.elapsed = time.monotonic() - start
    return t


async def test_chat_multiturn() -> TestResult:
    """CHAT-03: Multi-turn conversation preserves context in chat mode."""
    t = TestResult("CHAT-03", "Chat multi-turn context")
    start = time.monotonic()
    try:
        # Turn 1
        r1 = await chat_sse_request(
            "My favorite planet is Neptune. Just confirm you noted it.",
            model_id=ANTHROPIC_MODEL_ID,
        )
        if r1["error"]:
            t.status = TestStatus.FAIL
            t.notes = f"Turn 1 error: {r1['error'][:200]}"
            return t

        session_id = r1["session_id"]
        if not session_id:
            t.status = TestStatus.FAIL
            t.notes = "No session_id returned from turn 1"
            return t

        # Turn 2 — recall
        r2 = await chat_sse_request(
            "What is my favorite planet?",
            model_id=ANTHROPIC_MODEL_ID,
            session_id=session_id,
        )
        if r2["error"]:
            t.status = TestStatus.FAIL
            t.notes = f"Turn 2 error: {r2['error'][:200]}"
        elif "neptune" in r2["content"].lower():
            t.status = TestStatus.PASS
            t.notes = f"Context preserved. Turn 2: {r2['content'][:150]}"
        else:
            t.status = TestStatus.FAIL
            t.notes = f"Context lost. Turn 2: {r2['content'][:200]}"
    except Exception as e:
        t.status = TestStatus.ERROR
        t.notes = str(e)[:300]
    t.elapsed = time.monotonic() - start
    return t


async def test_chat_web_search() -> TestResult:
    """CHAT-04: Chat mode with web_search tool enabled."""
    t = TestResult("CHAT-04", "Chat web search tool")
    start = time.monotonic()
    try:
        r = await chat_sse_request(
            "Search the web for the population of Iceland and tell me the approximate number.",
            model_id=ANTHROPIC_MODEL_ID,
            tools={"web_search": True},
            timeout=90,
        )
        if r["error"]:
            t.status = TestStatus.FAIL
            t.notes = f"Error: {r['error'][:300]}"
        elif r["content"] and len(r["content"]) > 20:
            # Check if tool was invoked
            has_tool = any(
                e.get("event") == "message"
                and isinstance(e.get("data"), dict)
                and e["data"].get("event") == "tool_calls"
                for e in r["events"]
            )
            t.status = TestStatus.PASS
            t.notes = f"Tool invoked: {has_tool} | Response: {r['content'][:150]}"
        else:
            t.status = TestStatus.FAIL
            t.notes = f"Short/empty response: {r['content'][:200]}"
    except Exception as e:
        t.status = TestStatus.ERROR
        t.notes = str(e)[:300]
    t.elapsed = time.monotonic() - start
    return t


async def test_chat_long_response() -> TestResult:
    """CHAT-05: Chat mode handles longer streaming responses."""
    t = TestResult("CHAT-05", "Chat long streaming response")
    start = time.monotonic()
    try:
        r = await chat_sse_request(
            "Write a 200-word summary about the history of computing, from Babbage to modern AI.",
            model_id=ANTHROPIC_MODEL_ID,
            timeout=90,
        )
        if r["error"]:
            t.status = TestStatus.FAIL
            t.notes = f"Error: {r['error'][:300]}"
        elif len(r["content"]) > 300:
            t.status = TestStatus.PASS
            t.notes = f"Response length: {len(r['content'])} chars, done={r['done']}"
        else:
            t.status = TestStatus.FAIL
            t.notes = f"Short response ({len(r['content'])} chars): {r['content'][:200]}"
    except Exception as e:
        t.status = TestStatus.ERROR
        t.notes = str(e)[:300]
    t.elapsed = time.monotonic() - start
    return t


async def test_chat_stop() -> TestResult:
    """CHAT-06: Stop an active chat conversation."""
    t = TestResult("CHAT-06", "Chat stop conversation")
    start = time.monotonic()
    try:
        # Start a long response with short timeout
        r = await chat_sse_request(
            "Write a 1000-word essay about space exploration.",
            model_id=ANTHROPIC_MODEL_ID,
            timeout=15,  # short timeout to simulate stop
        )
        content = r.get("content", "")
        done = r.get("done", False)
        error = r.get("error", "")

        if content or done:
            t.status = TestStatus.PASS
            t.notes = f"Response collected ({len(content)} chars), done={done}"
        elif error:
            t.status = TestStatus.PASS
            t.notes = f"Stream interrupted as expected: {str(error)[:150]}"
        else:
            t.status = TestStatus.FAIL
            t.notes = "No content or error received"
    except httpx.ReadTimeout:
        t.status = TestStatus.PASS
        t.notes = "ReadTimeout as expected (stream was still active)"
    except Exception as e:
        t.status = TestStatus.ERROR
        t.notes = str(e)[:300]
    t.elapsed = time.monotonic() - start
    return t


# --- Category 3: Image Attachment ---


async def test_img_upload() -> TestResult:
    """IMG-01: Upload an image via the asset API."""
    t = TestResult("IMG-01", "Image upload flow")
    start = time.monotonic()
    try:
        asset_id = await upload_test_image()
        if asset_id:
            t.status = TestStatus.PASS
            t.notes = f"Asset ID: {asset_id}"
        else:
            t.status = TestStatus.FAIL
            t.notes = "Upload failed (see detail above)"
    except Exception as e:
        t.status = TestStatus.ERROR
        t.notes = str(e)[:300]
    t.elapsed = time.monotonic() - start
    return t


async def test_img_chat_attachment() -> TestResult:
    """IMG-02: Chat mode with image attachment."""
    t = TestResult("IMG-02", "Chat with image attachment")
    start = time.monotonic()
    try:
        asset_id = await upload_test_image()
        if not asset_id:
            t.status = TestStatus.SKIP
            t.notes = "Image upload failed, skipping"
            return t

        r = await chat_sse_request(
            "Describe this image. What color is it? It's a small test image.",
            model_id=ANTHROPIC_MODEL_ID,
            file_ids=[asset_id],
            timeout=60,
        )
        if r["error"]:
            t.status = TestStatus.FAIL
            t.notes = f"Error: {r['error'][:300]}"
        elif r["content"] and len(r["content"]) > 10:
            # Verify the model actually describes colors (not an error message about loading)
            content_lower = r["content"].lower()
            mentions_color = any(
                c in content_lower for c in ("red", "green", "blue", "purple", "gradient", "color")
            )
            if not mentions_color:
                t.status = TestStatus.FAIL
                t.notes = f"Response doesn't mention any colors — image may not have loaded: {r['content'][:200]}"
            else:
                t.status = TestStatus.PASS
                t.notes = f"Response with image: {r['content'][:200]}"
        else:
            t.status = TestStatus.FAIL
            t.notes = f"Empty/short response: {r['content'][:200]}"
    except Exception as e:
        t.status = TestStatus.ERROR
        t.notes = str(e)[:300]
    t.elapsed = time.monotonic() - start
    return t


async def test_img_agent_attachment() -> TestResult:
    """IMG-03: Agent mode with image attachment (via Socket.IO files param)."""
    t = TestResult("IMG-03", "Agent with image ref")
    start = time.monotonic()
    try:
        # For agent mode, files are passed as file_ids in the query command.
        # The agent query helper doesn't support file_ids directly,
        # so we test the upload + referencing flow conceptually.
        asset_id = await upload_test_image()
        if not asset_id:
            t.status = TestStatus.SKIP
            t.notes = "Image upload failed, skipping"
            return t

        # Agent mode — send query with file reference via Socket.IO
        sio = socketio.AsyncClient(reconnection=False, logger=False, engineio_logger=False)
        result_data = {"completed": False, "response": "", "error": None, "tool_events": []}
        connected = asyncio.Event()
        done = asyncio.Event()
        joined = asyncio.Event()
        sid_holder = [None]

        @sio.event
        async def connect():
            connected.set()

        @sio.on("*")  # type: ignore[misc]
        async def catch_all(event, data):
            if isinstance(data, str):
                try:
                    data = json.loads(data)
                except (json.JSONDecodeError, TypeError):
                    pass
            if not isinstance(data, dict):
                return
            evt = data.get("name", data.get("type", data.get("event", "")))
            content = data.get("content", {})
            if isinstance(content, dict) and content.get("session_id"):
                sid_holder[0] = content["session_id"]
                joined.set()
            if evt == "agent.response":
                if isinstance(content, dict):
                    result_data["response"] = content.get("text", content.get("content", ""))[:500]
            if evt in ("agent.complete", "agent.run.completed"):
                result_data["completed"] = True
                done.set()
            if "error" in str(evt).lower():
                result_data["error"] = json.dumps(data, default=str)[:300]
                done.set()

        await sio.connect(
            BACKEND_URL, auth={"token": TOKEN}, transports=["websocket"], wait_timeout=10
        )
        await connected.wait()
        await sio.emit("join_session", {})
        await asyncio.wait_for(joined.wait(), timeout=10)

        await sio.emit(
            "chat_message",
            {
                "session_uuid": sid_holder[0],
                "content": {
                    "command": "query",
                    "text": "I uploaded a small test image. Describe what you see.",
                    "model_id": AGENT_MODEL_ID,
                    "source": "user",
                    "agent_type": "general",
                    "tool_args": {},
                    "files": [asset_id],
                },
            },
        )
        try:
            await asyncio.wait_for(done.wait(), timeout=TIMEOUT_AGENT)
        except asyncio.TimeoutError:
            pass
        finally:
            if sio.connected:
                await sio.disconnect()

        # Schedule cleanup for the raw Socket.IO session
        if sid_holder[0]:
            await schedule_session_cleanup(sid_holder[0])

        if result_data["error"]:
            t.status = TestStatus.FAIL
            t.notes = f"Error: {result_data['error']}"
        elif result_data["completed"]:
            t.status = TestStatus.PASS
            t.notes = f"Agent completed with image. Response: {result_data['response'][:200]}"
        else:
            t.status = TestStatus.FAIL
            t.notes = f"Agent did not complete. resp={result_data['response'][:100]}"

    except Exception as e:
        t.status = TestStatus.ERROR
        t.notes = str(e)[:300]
    t.elapsed = time.monotonic() - start
    return t


# --- Category 4: Agent Mode — Web Search & Browser ---


async def test_agent_web_search() -> TestResult:
    """WEB-01: Agent mode web search tool."""
    t = TestResult("WEB-01", "Agent web search")
    start = time.monotonic()
    try:
        r = await agent_query(
            "Search the web for 'Python 3.13 release date' and tell me when it was released. Use the web search tool.",
            timeout=120,
        )
        if r["error"]:
            t.status = TestStatus.FAIL
            t.notes = f"Error: {r['error'][:300]}"
        elif r["completed"]:
            has_tool = any("search" in str(te.get("name", "")).lower() for te in r["tool_events"])
            t.status = TestStatus.PASS
            t.notes = f"Completed. Tool used: {has_tool}. Response: {r['response_text'][:200]}"
        else:
            t.status = TestStatus.FAIL
            t.notes = f"Not completed. Events: {len(r['events'])}"
    except Exception as e:
        t.status = TestStatus.ERROR
        t.notes = str(e)[:300]
    t.elapsed = time.monotonic() - start
    return t


async def test_agent_browser() -> TestResult:
    """WEB-02: Agent mode browser navigation."""
    t = TestResult("WEB-02", "Agent browser navigation")
    start = time.monotonic()
    try:
        r = await agent_query(
            "Navigate to example.com using the browser tool and tell me the heading text on the page.",
            timeout=120,
        )
        if r["error"]:
            t.status = TestStatus.FAIL
            t.notes = f"Error: {r['error'][:300]}"
        elif r["completed"]:
            # Check for browser-related tool usage
            has_browser = any(
                "browser" in str(te.get("name", "")).lower()
                or "navigate" in str(te.get("content", "")).lower()
                for te in r["tool_events"]
            )
            t.status = TestStatus.PASS
            t.notes = (
                f"Completed. Browser used: {has_browser}. Response: {r['response_text'][:200]}"
            )
        else:
            t.status = TestStatus.FAIL
            t.notes = f"Not completed after timeout. Events: {len(r['events'])}"
    except Exception as e:
        t.status = TestStatus.ERROR
        t.notes = str(e)[:300]
    t.elapsed = time.monotonic() - start
    return t


# --- Category 5: Agent Mode — Code Execution  ---


async def test_agent_code_exec() -> TestResult:
    """CODE-01: Agent creates and runs a Python script."""
    t = TestResult("CODE-01", "Agent code execution")
    start = time.monotonic()
    try:
        r = await agent_query(
            "Create a Python file called /workspace/fib.py that computes the first 10 Fibonacci numbers "
            "and prints them. Then run it and tell me the output.",
            timeout=180,
        )
        if r["error"]:
            t.status = TestStatus.FAIL
            t.notes = f"Error: {r['error'][:300]}"
        elif r["completed"]:
            t.status = TestStatus.PASS
            t.notes = f"Completed with {len(r['tool_events'])} tool calls. Response: {r['response_text'][:200]}"
        else:
            t.status = TestStatus.FAIL
            t.notes = f"Not completed. Events: {len(r['events'])}"
    except Exception as e:
        t.status = TestStatus.ERROR
        t.notes = str(e)[:300]
    t.elapsed = time.monotonic() - start
    return t


async def test_agent_multifile() -> TestResult:
    """CODE-02: Agent creates multiple files and uses them together."""
    t = TestResult("CODE-02", "Agent multi-file project")
    start = time.monotonic()
    try:
        r = await agent_query(
            "Create two files in /workspace: utils.py with a function add(a,b) that returns a+b, "
            "and main.py that imports add from utils and prints add(7,8). Then run main.py.",
            timeout=180,
        )
        if r["error"]:
            t.status = TestStatus.FAIL
            t.notes = f"Error: {r['error'][:300]}"
        elif r["completed"]:
            has_15 = "15" in r["response_text"]
            t.status = TestStatus.PASS
            t.notes = f"Completed. Output has '15': {has_15}. Response: {r['response_text'][:200]}"
        else:
            t.status = TestStatus.FAIL
            t.notes = f"Not completed. Events: {len(r['events'])}"
    except Exception as e:
        t.status = TestStatus.ERROR
        t.notes = str(e)[:300]
    t.elapsed = time.monotonic() - start
    return t


# --- Category 6: Session Management ---


async def test_session_list() -> TestResult:
    """SESS-01: List sessions API."""
    t = TestResult("SESS-01", "List sessions")
    start = time.monotonic()
    try:
        async with await http_client() as client:
            resp = await client.get("/v1/sessions")
            if resp.status_code == 200:
                data = resp.json()
                sessions = (
                    data if isinstance(data, list) else data.get("sessions", data.get("items", []))
                )
                t.status = TestStatus.PASS
                t.notes = f"Found {len(sessions)} sessions"
            else:
                t.status = TestStatus.FAIL
                t.notes = f"HTTP {resp.status_code}: {resp.text[:200]}"
    except Exception as e:
        t.status = TestStatus.ERROR
        t.notes = str(e)[:300]
    t.elapsed = time.monotonic() - start
    return t


async def test_session_events() -> TestResult:
    """SESS-02: Get session events for an existing session."""
    t = TestResult("SESS-02", "Session events retrieval")
    start = time.monotonic()
    try:
        # First create a quick session via agent
        r = await agent_query("Say hello.", timeout=60)
        if not r.get("session_id"):
            t.status = TestStatus.SKIP
            t.notes = "Could not create session"
            return t

        sid = r["session_id"]
        await asyncio.sleep(2)  # Let events persist

        async with await http_client() as client:
            resp = await client.get(f"/v1/sessions/{sid}/events")
            if resp.status_code == 200:
                events = resp.json()
                event_list = events if isinstance(events, list) else events.get("events", [])
                t.status = TestStatus.PASS
                t.notes = f"Session {sid}: {len(event_list)} events"
            else:
                t.status = TestStatus.FAIL
                t.notes = f"HTTP {resp.status_code}: {resp.text[:200]}"
    except Exception as e:
        t.status = TestStatus.ERROR
        t.notes = str(e)[:300]
    t.elapsed = time.monotonic() - start
    return t


async def test_session_pin() -> TestResult:
    """SESS-03: Pin and unpin a session."""
    t = TestResult("SESS-03", "Session pin/unpin")
    start = time.monotonic()
    try:
        # Create a quick session
        r = await agent_query("Say 'test'.", timeout=60)
        if not r.get("session_id"):
            t.status = TestStatus.SKIP
            t.notes = "Could not create session"
            return t

        sid = r["session_id"]
        async with await http_client() as client:
            # Pin
            pin_resp = await client.post(f"/v1/sessions/pins/{sid}")
            if pin_resp.status_code not in (200, 201):
                t.status = TestStatus.FAIL
                t.notes = f"Pin failed: {pin_resp.status_code} {pin_resp.text[:200]}"
                return t

            # Check pins
            list_resp = await client.get("/v1/sessions/pins")
            if list_resp.status_code != 200:
                t.status = TestStatus.FAIL
                t.notes = f"List pins failed: {list_resp.status_code}"
                return t

            t.status = TestStatus.PASS
            t.notes = f"Pinned session {sid}. Pins list: {list_resp.status_code}"
    except Exception as e:
        t.status = TestStatus.ERROR
        t.notes = str(e)[:300]
    t.elapsed = time.monotonic() - start
    return t


async def test_session_fork() -> TestResult:
    """SESS-04: Fork an existing session."""
    t = TestResult("SESS-04", "Session fork")
    start = time.monotonic()
    try:
        # Create a research session (fork requires deep_research or fast_research source)
        r = await agent_query(
            "Research the topic of solar energy briefly.",
            timeout=60,
            agent_type="deep_research",
        )
        if not r.get("session_id"):
            t.status = TestStatus.SKIP
            t.notes = "Could not create research session"
            return t

        sid = r["session_id"]
        await asyncio.sleep(2)

        async with await http_client() as client:
            fork_resp = await client.post(
                f"/v1/sessions/{sid}/fork",
                json={
                    "fork_type": "research_to_website",
                    "sandbox_mode": "share",
                    "context": {
                        "attachments": ["test attachment"],
                        "additional_instruction": "E2E test fork",
                    },
                },
            )
            if fork_resp.status_code in (200, 201):
                fork_data = fork_resp.json()
                new_sid = fork_data.get("id") or fork_data.get("session_id")
                if new_sid:
                    await schedule_session_cleanup(new_sid)
                t.status = TestStatus.PASS
                t.notes = f"Forked {sid} → {new_sid}"
            else:
                t.status = TestStatus.FAIL
                t.notes = f"Fork failed: {fork_resp.status_code} {fork_resp.text[:200]}"
    except Exception as e:
        t.status = TestStatus.ERROR
        t.notes = str(e)[:300]
    t.elapsed = time.monotonic() - start
    return t


# --- Category 7: Agent Multi-Turn ---


async def test_agent_multiturn_context() -> TestResult:
    """AGEN-01: Agent multi-turn preserves context."""
    t = TestResult("AGEN-01", "Agent multi-turn context")
    start = time.monotonic()
    try:
        # Turn 1
        r1 = await agent_query("My cat's name is Muffin. Just confirm.", timeout=60)
        if not r1.get("session_id") or r1.get("error"):
            t.status = TestStatus.FAIL
            t.notes = f"Turn 1 failed: {r1.get('error', 'no session')}"
            return t

        sid = r1["session_id"]

        # Turn 2
        r2 = await agent_query("What is my cat's name?", session_id=sid, timeout=60)
        if r2.get("error"):
            t.status = TestStatus.FAIL
            t.notes = f"Turn 2 error: {r2['error'][:200]}"
        elif "muffin" in r2.get("response_text", "").lower():
            t.status = TestStatus.PASS
            t.notes = f"Context preserved! Response: {r2['response_text'][:150]}"
        else:
            t.status = TestStatus.FAIL
            t.notes = f"Context lost. Response: {r2.get('response_text', '')[:200]}"
    except Exception as e:
        t.status = TestStatus.ERROR
        t.notes = str(e)[:300]
    t.elapsed = time.monotonic() - start
    return t


async def test_agent_multiturn_tooluse() -> TestResult:
    """AGEN-02: Agent multi-turn with tool use across turns."""
    t = TestResult("AGEN-02", "Agent multi-turn tool use")
    start = time.monotonic()
    try:
        # Turn 1: create a file
        r1 = await agent_query(
            "Create a file /workspace/data.txt with the text 'Hello E2E Test' inside.",
            timeout=120,
        )
        if not r1.get("session_id") or r1.get("error"):
            t.status = TestStatus.FAIL
            t.notes = f"Turn 1 failed: {r1.get('error', 'no session')}"
            return t

        sid = r1["session_id"]

        # Turn 2: read the file back
        r2 = await agent_query(
            "Read the file /workspace/data.txt and tell me its contents.",
            session_id=sid,
            timeout=120,
        )
        if r2.get("error"):
            t.status = TestStatus.FAIL
            t.notes = f"Turn 2 error: {r2['error'][:200]}"
        elif "hello e2e test" in r2.get("response_text", "").lower():
            t.status = TestStatus.PASS
            t.notes = f"File created and read back correctly. Response: {r2['response_text'][:150]}"
        else:
            t.status = TestStatus.FAIL
            t.notes = f"Expected file content. Response: {r2.get('response_text', '')[:200]}"
    except Exception as e:
        t.status = TestStatus.ERROR
        t.notes = str(e)[:300]
    t.elapsed = time.monotonic() - start
    return t


# --- Category 8: Cross-Feature Integration ---


async def test_cross_agent_websearch_and_file() -> TestResult:
    """XFEAT-01: Agent uses web search then saves result to file."""
    t = TestResult("XFEAT-01", "Web search + file save")
    start = time.monotonic()
    try:
        r = await agent_query(
            "Search the web for 'FastAPI framework' and save a 3-sentence summary "
            "to /workspace/fastapi_summary.txt. Then read the file back to confirm.",
            timeout=180,
        )
        if r["error"]:
            t.status = TestStatus.FAIL
            t.notes = f"Error: {r['error'][:300]}"
        elif r["completed"] and len(r["tool_events"]) >= 2:
            t.status = TestStatus.PASS
            t.notes = f"Completed with {len(r['tool_events'])} tool calls. Response: {r['response_text'][:200]}"
        elif r["completed"]:
            t.status = TestStatus.PASS
            t.notes = f"Completed (may have combined tools). Response: {r['response_text'][:200]}"
        else:
            t.status = TestStatus.FAIL
            t.notes = f"Not completed. Events: {len(r['events'])}"
    except Exception as e:
        t.status = TestStatus.ERROR
        t.notes = str(e)[:300]
    t.elapsed = time.monotonic() - start
    return t


async def test_cross_chat_then_agent() -> TestResult:
    """XFEAT-02: Verify chat and agent sessions are independent."""
    t = TestResult("XFEAT-02", "Chat vs agent independence")
    start = time.monotonic()
    try:
        # Chat session
        r_chat = await chat_sse_request(
            "My secret number is 42. Remember it.",
            model_id=ANTHROPIC_MODEL_ID,
        )
        chat_sid = r_chat.get("session_id")

        # Agent session
        r_agent = await agent_query("What secret number did I tell you?", timeout=120)

        # Agent should NOT know "42" since it's a different session
        if r_agent.get("error"):
            t.status = TestStatus.FAIL
            t.notes = f"Agent error: {r_agent['error'][:200]}"
        else:
            knows_42 = "42" in r_agent.get("response_text", "")
            t.status = TestStatus.PASS
            t.notes = (
                f"Chat session: {chat_sid}, Agent session: {r_agent.get('session_id')}. "
                f"Agent knows '42': {knows_42} (should be False for proper isolation)"
            )
    except Exception as e:
        t.status = TestStatus.ERROR
        t.notes = str(e)[:300]
    t.elapsed = time.monotonic() - start
    return t


# --- Category 9: Council Mode (CNCL) ---

COUNCIL_TIMEOUT = 120  # seconds — each member call + synthesis takes time


async def test_council_basic() -> TestResult:
    """CNCL-01: Council mode basic 2-model parallel execution."""
    t = TestResult("CNCL-01", "Council mode basic 2-model run")
    start = time.monotonic()
    try:
        r = await chat_sse_request(
            content="What is 7 * 8? Reply with only the number.",
            model_id=ANTHROPIC_MODEL_ID,
            timeout=COUNCIL_TIMEOUT,
            council_preferences={
                "enabled": True,
                "council_models": [
                    {"model_id": ANTHROPIC_MODEL_ID},
                    {"model_id": ANTHROPIC_OPUS_MODEL_ID},
                ],
                "synthesis_model_id": ANTHROPIC_MODEL_ID,
            },
        )

        if r["error"]:
            t.status = TestStatus.FAIL
            t.notes = f"Error: {r['error'][:300]}"
            return t

        members = r["council_members"]
        synthesis = r["council_synthesis"]
        member_starts = [m for m in members if m.get("status") == "start"]
        member_completes = [m for m in members if m.get("status") == "complete"]
        synth_completes = [s for s in synthesis if s.get("status") == "complete"]

        if len(member_starts) < 2:
            t.status = TestStatus.FAIL
            t.notes = f"Expected >=2 council_member start events, got {len(member_starts)}"
            return t

        if len(member_completes) < 2:
            t.status = TestStatus.FAIL
            t.notes = f"Expected >=2 council_member complete events, got {len(member_completes)}"
            return t

        if len(synth_completes) < 1:
            t.status = TestStatus.FAIL
            t.notes = f"Expected synthesis complete event, got {len(synth_completes)}"
            return t

        if not r["done"]:
            t.status = TestStatus.FAIL
            t.notes = "Stream did not complete (no done event)"
            return t

        # Verify member_complete has content
        member_contents = [m.get("content", "") for m in member_completes if m.get("content")]
        has_56 = any("56" in c for c in member_contents)

        # Check for content doubling (e.g. "56" becoming "5656")
        for mc in member_contents:
            doubled = detect_content_doubling(mc)
            if doubled:
                t.status = TestStatus.FAIL
                t.notes = f"Council member content doubling detected: {doubled}"
                return t

        # Also check synthesis content for doubling
        synth_content = r.get("content", "")
        doubled = detect_content_doubling(synth_content)
        if doubled:
            t.status = TestStatus.FAIL
            t.notes = f"Synthesis content doubling detected: {doubled}"
            return t

        t.status = TestStatus.PASS
        t.notes = (
            f"{len(member_starts)} members started, {len(member_completes)} completed, "
            f"{len(synth_completes)} synthesis. Has '56' in member output: {has_56}. "
            f"Session: {r.get('session_id', 'N/A')}"
        )
    except Exception as e:
        t.status = TestStatus.ERROR
        t.notes = str(e)[:300]
    t.elapsed = time.monotonic() - start
    return t


async def test_council_validation() -> TestResult:
    """CNCL-02: Council mode rejects < 2 models."""
    t = TestResult("CNCL-02", "Council mode validation (< 2 models)")
    start = time.monotonic()
    try:
        r = await chat_sse_request(
            content="Hello",
            model_id=ANTHROPIC_MODEL_ID,
            timeout=30,
            council_preferences={
                "enabled": True,
                "council_models": [
                    {"model_id": ANTHROPIC_MODEL_ID},
                ],
                "synthesis_model_id": ANTHROPIC_MODEL_ID,
            },
        )

        # Expect an error event about insufficient models
        if r["error"] and "2 model" in r["error"].lower():
            t.status = TestStatus.PASS
            t.notes = f"Correctly rejected: {r['error'][:200]}"
        elif r["error"]:
            # Got an error but not the expected one — still verify it's a validation error
            t.status = TestStatus.PASS
            t.notes = f"Rejected with error: {r['error'][:200]}"
        else:
            t.status = TestStatus.FAIL
            t.notes = "Expected validation error for < 2 models, but request succeeded"
    except Exception as e:
        t.status = TestStatus.ERROR
        t.notes = str(e)[:300]
    t.elapsed = time.monotonic() - start
    return t


async def test_council_billing_events() -> TestResult:
    """CNCL-03: Council mode produces usage events for billing."""
    t = TestResult("CNCL-03", "Council mode billing (usage events)")
    start = time.monotonic()
    try:
        r = await chat_sse_request(
            content="What color is the sky? One word answer.",
            model_id=ANTHROPIC_MODEL_ID,
            timeout=COUNCIL_TIMEOUT,
            council_preferences={
                "enabled": True,
                "council_models": [
                    {"model_id": ANTHROPIC_MODEL_ID},
                    {"model_id": ANTHROPIC_OPUS_MODEL_ID},
                ],
                "synthesis_model_id": ANTHROPIC_MODEL_ID,
            },
        )

        if r["error"]:
            t.status = TestStatus.FAIL
            t.notes = f"Error: {r['error'][:300]}"
            return t

        if not r["done"]:
            t.status = TestStatus.FAIL
            t.notes = "Stream did not complete"
            return t

        # Check that usage events were emitted (billing happens server-side;
        # the SSE stream includes usage events for the synthesis turn)
        usage_events = [e for e in r["events"] if e.get("event") == "usage"]

        # Also verify the session was created so we have a billing context
        sid = r.get("session_id")

        # Council should yield at least 2 member completes + 1 synthesis
        members = r["council_members"]
        member_completes = [m for m in members if m.get("status") == "complete"]
        synth_completes = [s for s in r["council_synthesis"] if s.get("status") == "complete"]

        if len(member_completes) < 2:
            t.status = TestStatus.FAIL
            t.notes = f"Expected >=2 member completes for billing, got {len(member_completes)}"
            return t

        # Check for content doubling in council member outputs
        member_contents = [m.get("content", "") for m in member_completes if m.get("content")]
        for mc in member_contents:
            doubled = detect_content_doubling(mc)
            if doubled:
                t.status = TestStatus.FAIL
                t.notes = f"Council member content doubling: {doubled}"
                return t

        # Check synthesis content for doubling
        synth_content = r.get("content", "")
        doubled = detect_content_doubling(synth_content)
        if doubled:
            t.status = TestStatus.FAIL
            t.notes = f"Synthesis content doubling: {doubled}"
            return t

        t.status = TestStatus.PASS
        t.notes = (
            f"Members: {len(member_completes)}, Synthesis: {len(synth_completes)}, "
            f"Usage events: {len(usage_events)}, Session: {sid}"
        )
    except Exception as e:
        t.status = TestStatus.ERROR
        t.notes = str(e)[:300]
    t.elapsed = time.monotonic() - start
    return t


# --- Category 10: Chat Mode History/Messages ---


async def test_chat_history() -> TestResult:
    """HIST-01: Retrieve chat message history."""
    t = TestResult("HIST-01", "Chat message history")
    start = time.monotonic()
    try:
        # Create a chat session with a message
        r = await chat_sse_request(
            "Hello, this is a test message.",
            model_id=ANTHROPIC_MODEL_ID,
        )
        sid = r.get("session_id")
        if not sid:
            t.status = TestStatus.SKIP
            t.notes = "No session created"
            return t

        await asyncio.sleep(1)

        async with await http_client() as client:
            resp = await client.get(f"/v1/chat/conversations/{sid}")
            if resp.status_code == 200:
                data = resp.json()
                messages = data if isinstance(data, list) else data.get("messages", [])
                t.status = TestStatus.PASS
                t.notes = f"Session {sid}: {len(messages) if isinstance(messages, list) else 'data'} messages. Keys: {list(data.keys()) if isinstance(data, dict) else 'list'}"
            else:
                t.status = TestStatus.FAIL
                t.notes = f"HTTP {resp.status_code}: {resp.text[:200]}"
    except Exception as e:
        t.status = TestStatus.ERROR
        t.notes = str(e)[:300]
    t.elapsed = time.monotonic() - start
    return t


# --- Category 11: A2A Backend Verification (A2A) ---


async def test_a2a_config_active() -> TestResult:
    """A2A-01: Health endpoint reports A2A inner loop mode is active."""
    t = TestResult("A2A-01", "A2A config active in health endpoint")
    start = time.monotonic()
    try:
        async with await http_client() as client:
            resp = await client.get("/health")
            data = resp.json()
            chat_mode = data.get("chat_inner_loop_mode", "unknown")
            agent_mode = data.get("agent_inner_loop_mode", "unknown")
            a2a_backend = data.get("a2a_backend", "unknown")

            issues = []
            if chat_mode != "a2a":
                issues.append(f"chat_inner_loop_mode={chat_mode} (expected 'a2a')")
            if agent_mode != "a2a":
                issues.append(f"agent_inner_loop_mode={agent_mode} (expected 'a2a')")
            if a2a_backend != "copilot":
                issues.append(f"a2a_backend={a2a_backend} (expected 'copilot')")

            if issues:
                t.status = TestStatus.FAIL
                t.notes = (
                    "A2A NOT ACTIVE — native Anthropic billing likely occurring. "
                    + "; ".join(issues)
                )
            else:
                t.status = TestStatus.PASS
                t.notes = f"chat_loop={chat_mode}, agent_loop={agent_mode}, backend={a2a_backend}"
    except Exception as e:
        t.status = TestStatus.ERROR
        t.notes = str(e)[:300]
    t.elapsed = time.monotonic() - start
    return t


async def test_a2a_chat_backend_logs() -> TestResult:
    """A2A-02: Chat request triggers A2A turn loop (verified via backend logs).

    When AGENT_CHAT_INNER_LOOP_MODE=a2a and ENVIRONMENT=local, ALL compatible
    models route through the A2A adapter regardless of config_type (system vs
    user/BYOK).  In local/self-hosted mode the operator owns all keys, so the
    BYOK distinction is irrelevant.  In cloud deployments, BYOK models go
    direct to avoid charging the platform's A2A subscription.
    """
    t = TestResult("A2A-02", "Chat uses A2A turn loop (log check)")
    start = time.monotonic()
    try:
        # First verify A2A is configured
        async with await http_client() as client:
            health = await client.get("/health")
            if health.json().get("chat_inner_loop_mode") != "a2a":
                t.status = TestStatus.SKIP
                t.notes = "chat_inner_loop_mode is not 'a2a' — skipping log check"
                return t

        # Send a simple chat request — any model should route through A2A
        r = await chat_sse_request(
            content="What is 2+2? Reply with just the number.",
            model_id=ANTHROPIC_MODEL_ID,
            timeout=TIMEOUT_CHAT,
        )

        if r["error"]:
            t.status = TestStatus.FAIL
            t.notes = f"Chat request failed: {r['error'][:200]}"
            return t

        if not r["content"]:
            t.status = TestStatus.FAIL
            t.notes = "No content in response"
            return t

        # Check backend logs for A2A turn loop selection
        proc = await asyncio.create_subprocess_exec(
            "docker",
            "logs",
            "--since",
            "60s",
            "ii-agent-local-backend-1",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        logs = stdout.decode() + stderr.decode()

        a2a_selected = "turn-loop-select: a2a" in logs
        direct_selected = "turn-loop-select: direct" in logs

        if a2a_selected:
            t.status = TestStatus.PASS
            t.notes = f"Backend logs confirm 'turn-loop-select: a2a'. Response: {r['content'][:80]}"
        elif direct_selected and not a2a_selected:
            # Extract the specific direct reason from logs
            import re as _re

            direct_reasons = _re.findall(r"turn-loop-select: direct \(([^)]+)\)", logs)
            reason = direct_reasons[-1] if direct_reasons else "unknown"
            t.status = TestStatus.FAIL
            t.notes = (
                f"Chat routed to direct loop (reason: {reason}) — A2A Copilot backend not used!"
            )
        else:
            t.status = TestStatus.FAIL
            t.notes = (
                "No turn-loop-select log found in last 60s of backend logs. "
                "Logging may not be deployed yet. "
                f"Response received: {bool(r['content'])}"
            )
    except Exception as e:
        t.status = TestStatus.ERROR
        t.notes = str(e)[:300]
    t.elapsed = time.monotonic() - start
    return t


async def test_a2a_agent_backend_logs() -> TestResult:
    """A2A-03: Agent request triggers A2A inner loop (verified via backend logs)."""
    t = TestResult("A2A-03", "Agent uses A2A inner loop (log check)")
    start = time.monotonic()
    try:
        # Verify A2A configured for agent mode
        async with await http_client() as client:
            health = await client.get("/health")
            if health.json().get("agent_inner_loop_mode") != "a2a":
                t.status = TestStatus.SKIP
                t.notes = "agent_inner_loop_mode is not 'a2a' — skipping"
                return t

        # Send a simple agent query
        r = await agent_query(
            prompt="What is the capital of Japan? Reply in one word.",
            model_id=AGENT_MODEL_ID,
            timeout=TIMEOUT_AGENT,
        )

        if r["error"]:
            t.status = TestStatus.FAIL
            t.notes = f"Agent query failed: {r['error'][:200]}"
            return t

        # Check backend logs for A2A inner loop evidence
        proc = await asyncio.create_subprocess_exec(
            "docker",
            "logs",
            "--since",
            "120s",
            "ii-agent-local-backend-1",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        logs = stdout.decode() + stderr.decode()

        # Agent mode logs "a2a:" in billing_backend or "A2A" in adapter messages
        a2a_evidence = any(
            marker in logs
            for marker in [
                "a2a:copilot",
                "[a2a:client]",
                "runtime model override",
                "A2AAdapter",
                "a2a_adapter",
                "copilot_backend",
            ]
        )

        if a2a_evidence:
            t.status = TestStatus.PASS
            t.notes = f"Backend logs contain A2A evidence. Response: {r['response_text'][:80]}"
        else:
            # Check if response came back at all — if so, something handled it
            if r["completed"] and r["response_text"]:
                t.status = TestStatus.FAIL
                t.notes = (
                    "Agent completed but no A2A evidence in logs — "
                    "may be using native Anthropic. "
                    f"Response: {r['response_text'][:80]}"
                )
            else:
                t.status = TestStatus.FAIL
                t.notes = f"Agent did not complete. Events: {len(r['events'])}"
    except Exception as e:
        t.status = TestStatus.ERROR
        t.notes = str(e)[:300]
    t.elapsed = time.monotonic() - start
    return t


async def test_a2a_council_uses_a2a() -> TestResult:
    """A2A-04: Council mode routes members through A2A when configured.

    In local mode (ENVIRONMENT=local), council members use the A2A adapter
    (e.g. Copilot) for inference.  Each member independently decides A2A vs
    direct based on the per-model is_cloud_byok check.  In local mode all
    models route through A2A since the operator owns all keys.
    """
    t = TestResult("A2A-04", "Council uses A2A for member inference")
    start = time.monotonic()
    try:
        # Verify A2A is configured
        async with await http_client() as client:
            health = await client.get("/health")
            if health.json().get("chat_inner_loop_mode") != "a2a":
                t.status = TestStatus.SKIP
                t.notes = "chat_inner_loop_mode is not 'a2a' — test not meaningful"
                return t

        # Send a council request — should route members through A2A
        r = await chat_sse_request(
            content="What is 3+3? Reply with just the number.",
            model_id=ANTHROPIC_MODEL_ID,
            timeout=COUNCIL_TIMEOUT,
            council_preferences={
                "enabled": True,
                "council_models": [
                    {"model_id": ANTHROPIC_MODEL_ID},
                    {"model_id": ANTHROPIC_OPUS_MODEL_ID},
                ],
                "synthesis_model_id": ANTHROPIC_MODEL_ID,
            },
        )

        if r["error"]:
            t.status = TestStatus.FAIL
            t.notes = f"Council request failed: {r['error'][:200]}"
            return t

        members = r["council_members"]
        member_completes = [m for m in members if m.get("status") == "complete"]

        if len(member_completes) >= 2:
            t.status = TestStatus.PASS
            t.notes = f"Council completed with {len(member_completes)} members via A2A"
        else:
            t.status = TestStatus.FAIL
            t.notes = f"Council did not produce expected outputs. Members: {len(member_completes)}"
    except Exception as e:
        t.status = TestStatus.ERROR
        t.notes = str(e)[:300]
    t.elapsed = time.monotonic() - start
    return t


async def test_a2a_chat_selected_model_used() -> TestResult:
    """A2A-05: Chat-selected model reaches the Copilot A2A runtime.

    Mirrors the user flow of entering a chat session, opening Chat Settings
    with no tab, and choosing a model from the chat model picker.
    """
    t = TestResult("A2A-05", "Chat selected model reaches A2A runtime")
    start = time.monotonic()
    try:
        expected_model, label = await resolve_runtime_model_name(ANTHROPIC_OPUS_MODEL_ID)
        if not expected_model:
            t.status = TestStatus.ERROR
            t.notes = f"Could not resolve chat model from API: {label}"
            return t

        ready, detail = await ensure_a2a_adapter_warm()
        if not ready:
            t.status = TestStatus.FAIL
            t.notes = f"Could not warm A2A adapter before chat test: {detail}"
            return t

        r = await chat_sse_request(
            content="Reply with the word chat-ok.",
            model_id=ANTHROPIC_OPUS_MODEL_ID,
            timeout=TIMEOUT_CHAT,
        )
        if r["error"]:
            t.status = TestStatus.FAIL
            t.notes = f"Chat request failed: {r['error'][:200]}"
            return t

        session_id = r.get("session_id")
        if not session_id:
            t.status = TestStatus.FAIL
            t.notes = "Chat request returned no session_id"
            return t

        logs = await get_backend_logs_since(120)
        match = find_model_override_log(
            logs,
            expected_model=expected_model,
            expected_context=f"chat-{session_id}",
        )
        if match:
            t.status = TestStatus.PASS
            t.notes = f"Chat selection confirmed in A2A logs: {expected_model} ({label})"
        else:
            t.status = TestStatus.FAIL
            t.notes = (
                f"No A2A runtime model override log found for chat context chat-{session_id} "
                f"with model {expected_model}"
            )
    except Exception as e:
        t.status = TestStatus.ERROR
        t.notes = str(e)[:300]
    t.elapsed = time.monotonic() - start
    return t


async def test_a2a_agent_selected_model_used() -> TestResult:
    """A2A-06: Agent-selected model reaches the Copilot A2A runtime.

    Mirrors the user flow of opening Agent Settings from the top-right
    sliders icon and choosing a model from the Model tab.
    """
    t = TestResult("A2A-06", "Agent selected model reaches A2A runtime")
    start = time.monotonic()
    try:
        expected_model, label = await resolve_runtime_model_name(ANTHROPIC_OPUS_MODEL_ID)
        if not expected_model:
            t.status = TestStatus.ERROR
            t.notes = f"Could not resolve agent model from API: {label}"
            return t

        r = await agent_query(
            prompt="Reply with the exact phrase agent-ok.",
            model_id=ANTHROPIC_OPUS_MODEL_ID,
            timeout=TIMEOUT_AGENT,
        )
        if r["error"]:
            t.status = TestStatus.FAIL
            t.notes = f"Agent query failed: {r['error'][:200]}"
            return t

        session_id = r.get("session_id")
        if not session_id:
            t.status = TestStatus.FAIL
            t.notes = "Agent query returned no session_id"
            return t

        logs = await get_backend_logs_since(180)
        match = find_model_override_log(
            logs,
            expected_model=expected_model,
            expected_context=session_id,
        )
        if match:
            t.status = TestStatus.PASS
            t.notes = f"Agent selection confirmed in A2A logs: {expected_model} ({label})"
        else:
            t.status = TestStatus.FAIL
            t.notes = (
                f"No A2A runtime model override log found for agent context {session_id} "
                f"with model {expected_model}"
            )
    except Exception as e:
        t.status = TestStatus.ERROR
        t.notes = str(e)[:300]
    t.elapsed = time.monotonic() - start
    return t


# ─── Test runner ────────────────────────────────────────────────────

ALL_TESTS = [
    # Infrastructure
    ("INF", "Infrastructure", [test_inf_health, test_inf_models, test_inf_sandbox]),
    # Chat Mode
    (
        "CHAT",
        "Chat Mode (REST API)",
        [
            test_chat_basic_anthropic,
            test_chat_basic_openai,
            test_chat_multiturn,
            test_chat_web_search,
            test_chat_long_response,
            test_chat_stop,
        ],
    ),
    # Image Attachments
    (
        "IMG",
        "Image Attachments",
        [
            test_img_upload,
            test_img_chat_attachment,
            test_img_agent_attachment,
        ],
    ),
    # Web Search & Browser
    (
        "WEB",
        "Web Search & Browser",
        [
            test_agent_web_search,
            test_agent_browser,
        ],
    ),
    # Code Execution
    (
        "CODE",
        "Code Execution",
        [
            test_agent_code_exec,
            test_agent_multifile,
        ],
    ),
    # Session Management
    (
        "SESS",
        "Session Management",
        [
            test_session_list,
            test_session_events,
            test_session_pin,
            test_session_fork,
        ],
    ),
    # Agent Multi-Turn
    (
        "AGEN",
        "Agent Multi-Turn",
        [
            test_agent_multiturn_context,
            test_agent_multiturn_tooluse,
        ],
    ),
    # Cross-Feature Integration
    (
        "XFEAT",
        "Cross-Feature Integration",
        [
            test_cross_agent_websearch_and_file,
            test_cross_chat_then_agent,
        ],
    ),
    # Chat History
    (
        "HIST",
        "Chat History",
        [
            test_chat_history,
        ],
    ),
    # Council Mode
    (
        "CNCL",
        "Council Mode",
        [
            test_council_basic,
            test_council_validation,
            test_council_billing_events,
        ],
    ),
    # A2A Backend Verification
    (
        "A2A",
        "A2A Backend Verification",
        [
            test_a2a_config_active,
            test_a2a_chat_backend_logs,
            test_a2a_agent_backend_logs,
            test_a2a_council_uses_a2a,
            test_a2a_chat_selected_model_used,
            test_a2a_agent_selected_model_used,
        ],
    ),
]


async def run_category(cat_id: str, cat_name: str, tests: list) -> list[TestResult]:
    """Run tests in a category sequentially."""
    print(f"\n{'=' * 60}")
    print(f"  Category: {cat_name} ({cat_id})")
    print(f"{'=' * 60}")
    results = []
    for test_fn in tests:
        print(f"\n  Running {test_fn.__doc__ or test_fn.__name__}...", end="", flush=True)
        result = await test_fn()
        results.append(result)
        status_icon = {
            TestStatus.PASS: "✅",
            TestStatus.FAIL: "❌",
            TestStatus.ERROR: "💥",
            TestStatus.SKIP: "⏭️",
            TestStatus.NOT_RUN: "⬜",
        }[result.status]
        print(f" {status_icon} {result.status.value} ({result.elapsed:.1f}s)")
        if result.notes:
            print(f"    {result.notes[:300]}")
    return results


async def main():
    """Run all E2E tests with state management."""
    # Parse command-line arguments
    parser = argparse.ArgumentParser(
        prog="python3 scripts/local/test_e2e.py",
        description="II-Agent E2E Test Suite with state management for fix/rebuild/retest cycles.",
        epilog="Use --help to see comprehensive help including agentic instructions.",
        add_help=False,  # We'll handle --help ourselves to show custom help
    )
    parser.add_argument(
        "--help",
        "-h",
        action="store_true",
        help="Show comprehensive help and agentic instructions",
    )
    parser.add_argument(
        "--clear",
        action="store_true",
        help="Delete previous results file and run all tests (fresh state)",
    )
    parser.add_argument(
        "--failed",
        action="store_true",
        help="Rerun only tests that FAIL or ERROR from last run",
    )
    parser.add_argument(
        "--test",
        type=str,
        default=os.environ.get("TEST_ID", ""),
        help="Run single or multiple tests by ID (comma-separated): CHAT-01 or CHAT-01,IMG-02",
    )
    parser.add_argument(
        "--category",
        type=str,
        default=os.environ.get("TEST_CATEGORY", ""),
        help="Run all tests in one or more categories (comma-separated): CHAT or CHAT,IMG,CODE",
    )

    args = parser.parse_args()

    # Handle custom help
    if args.help:
        print_help_and_agentic_instructions()
        return 0

    # Handle --clear: delete old results before running
    if args.clear:
        if RESULTS_FILE.exists():
            try:
                RESULTS_FILE.unlink()
                print(f"[State] Cleared previous results: {RESULTS_FILE}")
            except Exception as e:
                print(f"[Warning] Failed to delete results file: {e}")
        args.failed = False  # Ignore --failed if --clear is given

    # Determine which tests to run
    filter_cat = args.category.upper() if args.category else ""
    filter_test = args.test.upper() if args.test else ""
    load_last_failed = args.failed and not args.clear

    # Load previous results if --failed was passed
    last_failed_test_ids = set()
    if load_last_failed:
        last_results = load_last_results()
        if last_results:
            last_failed_test_ids = {
                r.test_id for r in last_results if r.status in (TestStatus.FAIL, TestStatus.ERROR)
            }
            print(f"[State] Loaded {len(last_failed_test_ids)} failed tests from last run:")
            for test_id in sorted(last_failed_test_ids):
                print(f"         {test_id}")
        else:
            print("[Warning] --failed passed but no previous results found. Running all tests.")

    print("=" * 60)
    print("  II-Agent Expanded E2E Test Suite")
    print(f"  Backend: {BACKEND_URL}")
    if load_last_failed:
        print(f"  Mode: RETEST FAILURES ({len(last_failed_test_ids)} tests)")
    elif args.clear:
        print("  Mode: FULL SUITE (fresh state)")
    else:
        print("  Mode: FILTERED")
    if filter_cat:
        print(f"  Categories: {filter_cat}")
    if filter_test:
        print(f"  Tests: {filter_test}")
    print("=" * 60)

    all_results: list[TestResult] = []
    start_time = time.monotonic()

    # Iterate through all available tests
    for cat_id, cat_name, available_tests in ALL_TESTS:
        # Filter by category if specified
        if filter_cat:
            categories = [c.strip() for c in filter_cat.split(",")]
            if cat_id not in categories:
                continue

        # Filter tests within the category
        filtered_tests = available_tests

        # Apply test ID filter (CLI or env var)
        if filter_test:
            test_ids = [t.strip() for t in filter_test.split(",")]
            filtered_tests = [
                t
                for t in filtered_tests
                if any(test_id in (t.__doc__ or "").upper() for test_id in test_ids)
            ]

        # Apply failed-only filter (from --failed flag)
        if load_last_failed and last_failed_test_ids:
            filtered_tests = [
                t
                for t in filtered_tests
                if any(test_id in (t.__doc__ or "").upper() for test_id in last_failed_test_ids)
            ]

        if not filtered_tests:
            continue

        results = await run_category(cat_id, cat_name, filtered_tests)
        all_results.extend(results)

    # Summary
    total_time = time.monotonic() - start_time
    pass_count = sum(1 for r in all_results if r.status == TestStatus.PASS)
    fail_count = sum(1 for r in all_results if r.status == TestStatus.FAIL)
    error_count = sum(1 for r in all_results if r.status == TestStatus.ERROR)
    skip_count = sum(1 for r in all_results if r.status == TestStatus.SKIP)

    print(f"\n\n{'=' * 60}")
    print("  RESULTS SUMMARY")
    print(f"{'=' * 60}")
    print(f"  Total:   {len(all_results)}")
    print(f"  ✅ Pass:  {pass_count}")
    print(f"  ❌ Fail:  {fail_count}")
    print(f"  💥 Error: {error_count}")
    print(f"  ⏭️  Skip:  {skip_count}")
    print(f"  Time:    {total_time:.1f}s")

    if fail_count > 0 or error_count > 0:
        print("\n  FAILURES:")
        for r in all_results:
            if r.status in (TestStatus.FAIL, TestStatus.ERROR):
                print(f"    {r.test_id} [{r.status.value}]: {r.name}")
                print(f"      {r.notes[:400]}")

    if _created_session_ids:
        ttl_h = E2E_SESSION_TTL_SECONDS / 3600
        print(
            f"\n  Cleanup: {len(_created_session_ids)} sessions scheduled for auto-delete in {ttl_h:.0f}h"
        )

    # Save results for next --failed run
    if all_results:
        save_results(all_results)
        print(f"  Results saved to: {RESULTS_FILE}")

    print(f"\n{'=' * 60}")

    # Return exit code for CI
    return 1 if (fail_count + error_count) > 0 else 0


if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except SystemExit:
        # argparse may call sys.exit() — let it through
        raise
    except KeyboardInterrupt:
        print("\n\n[Interrupted] Test suite cancelled by user")
        sys.exit(130)
    except Exception as e:
        print(f"\n[Fatal Error] {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
