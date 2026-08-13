"""Persistent shell sessions for Docker sandboxes.

Uses ``docker exec`` + ``script`` (for PTY logging) + a bash prompt
hook to track prompt sequences and working directories — mirroring the
approach taken by :class:`E2BShell` via E2B's native PTY API.
"""

from __future__ import annotations

import asyncio
import base64
import os
import shlex
import uuid
from datetime import datetime, timezone
from pathlib import PurePosixPath
from typing import TYPE_CHECKING

from ii_agent.agents.sandboxes.shell import (
    Shell,
    ShellCommandTimeoutError,
    ShellExecutionRequest,
    ShellInvalidSessionNameError,
    ShellOperationError,
    ShellResult,
    ShellRunDirNotFoundError,
    ShellSessionNotFoundError,
    ShellSessionRecord,
    ShellSessionState,
    sanitize_shell_output,
    strip_ansi,
)
from ii_agent.core.logger import logger

if TYPE_CHECKING:
    from docker.models.containers import Container

    from ii_agent.agents.sandboxes.docker import DockerSandbox

# ── Constants ────────────────────────────────────────────────────────────

_DEFAULT_SHELL_TIMEOUT = 60
_MAX_SHELL_TIMEOUT = 180
_SHELL_POLL_INTERVAL = 0.25
_DEFAULT_PROMPT_PREFIX = "root@sandbox"
_PROMPT_FORMAT = r"\[\033[01;32m\]{PREFIX}\[\033[00m\]:\[\033[01;34m\]\w\[\033[00m\]\$ ".format(
    PREFIX=_DEFAULT_PROMPT_PREFIX
)
_SHELL_STORAGE_DIRNAME = ".ii_agent/pty"
_SHELL_LOG_TAIL_BYTES = 65536
_SHELL_OUTPUT_TAIL_BYTES = 131072
_SHELL_UTILITY_TIMEOUT = 30
_ENV_SOURCE_CMD = "source /app/.user_env.sh"
_ENV_SOURCE_SAFE_CMD = f"{_ENV_SOURCE_CMD} >/dev/null 2>&1 || true"


def _b64_frame(command: str) -> str:
    """Encode a shell command for transport over the PTY FIFO.

    The PTY inner loop is line-oriented (``read -r`` / ``read -d ''``
    both have edge cases with embedded NULs or backslash-escapes), so
    we frame each command as a single base64 line. The reader decodes
    that line and ``eval``s the result, so any byte sequence — embedded
    newlines, quotes, parentheses, here-docs — survives intact. A naive
    ``"\n".join(commands)`` framing splits multi-line user payloads
    (e.g. ``python3 -c \"<heredoc>\"``) across multiple ``read``
    iterations, causing bash to evaluate Python source as shell.
    """
    return base64.b64encode(command.encode("utf-8")).decode("ascii")


def _b64_frame_payload(commands: list[str]) -> bytes:
    """Encode a sequence of commands as base64 lines for FIFO transport.

    Each command becomes one base64 line; the joined payload ends with
    ``\n`` so the reader's blocking ``read -r`` returns once per command.
    The number of lines equals ``len(commands)`` exactly, matching the
    ``pending_prompt_seq`` accounting in ``build_command_request``.
    """
    return ("\n".join(_b64_frame(c) for c in commands) + "\n").encode("ascii")


class DockerShell(Shell):
    """Persistent shell runtime backend for :class:`DockerSandbox`.

    Each named session corresponds to a ``script``-wrapped bash process
    inside the Docker container, identified by a PID file.  Output is
    captured into per-session log files under ``/workspace/.ii_agent/pty/``.
    """

    def __init__(self, sandbox: DockerSandbox) -> None:
        self._sandbox = sandbox

    # ── Helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _shell_timestamp() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _normalize_output(text: str) -> str:
        return sanitize_shell_output(text)

    def _container(self) -> Container:
        c = self._sandbox._container
        if c is None:
            raise ShellOperationError("docker_shell", "Sandbox container is not available")
        return c

    def _get_log_path(self, session_name: str) -> str:
        return str(
            PurePosixPath(self.workspace_path) / _SHELL_STORAGE_DIRNAME / f"{session_name}.log"
        )

    def _get_state_path(self, session_name: str) -> str:
        return str(
            PurePosixPath(self.workspace_path) / _SHELL_STORAGE_DIRNAME / f"{session_name}.state"
        )

    def _get_pid_path(self, session_name: str) -> str:
        return str(
            PurePosixPath(self.workspace_path) / _SHELL_STORAGE_DIRNAME / f"{session_name}.pid"
        )

    def _exec_utility(self, command: str, timeout: int = _SHELL_UTILITY_TIMEOUT) -> str:
        """Run a utility command synchronously in the container."""
        container = self._container()
        exit_code, output = container.exec_run(
            ["/bin/sh", "-c", command],
            workdir="/workspace",
        )
        result = output.decode("utf-8", errors="replace") if output else ""
        if exit_code != 0:
            raise ShellOperationError("exec_utility", result or f"Exit code: {exit_code}")
        return result

    async def _run_utility(self, command: str, timeout: int = _SHELL_UTILITY_TIMEOUT) -> str:
        """Run a utility command in the container (async wrapper)."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._exec_utility, command, timeout)

    async def _read_state(self, state_path: str) -> tuple[int | None, str | None]:
        """Read the prompt_seq and cwd from the state file."""
        try:
            content = await self._run_utility(f"cat {shlex.quote(state_path)} 2>/dev/null || true")
        except ShellOperationError:
            return None, None

        if not content.strip():
            return None, None

        lines = content.strip().splitlines()
        if len(lines) < 2:
            return None, None

        try:
            prompt_seq = int(lines[0].strip())
        except ValueError:
            return None, None

        cwd = lines[1].strip() or None
        return prompt_seq, cwd

    async def _wait_for_prompt_internal(
        self,
        state_path: str,
        *,
        minimum_prompt_seq: int,
        timeout: int,
    ) -> tuple[int, str | None]:
        deadline = asyncio.get_running_loop().time() + timeout
        while asyncio.get_running_loop().time() < deadline:
            prompt_seq, cwd = await self._read_state(state_path)
            if prompt_seq is not None and prompt_seq >= minimum_prompt_seq:
                return prompt_seq, cwd
            await asyncio.sleep(_SHELL_POLL_INTERVAL)

        raise ShellCommandTimeoutError(
            f"Timed out waiting for shell prompt after {timeout} seconds."
        )

    async def _get_file_size(self, file_path: str) -> int:
        quoted_path = shlex.quote(file_path)
        output = await self._run_utility(
            f"if [ -f {quoted_path} ]; then wc -c < {quoted_path}; else echo 0; fi"
        )
        try:
            return int(output.strip() or "0")
        except ValueError:
            return 0

    async def _read_log(
        self,
        log_path: str,
        *,
        start_offset: int | None = None,
        max_bytes: int,
    ) -> str:
        file_size = await self._get_file_size(log_path)
        if file_size <= 0:
            return ""

        quoted_path = shlex.quote(log_path)
        if start_offset is not None:
            start_offset = max(start_offset, 0)
            bytes_remaining = file_size - start_offset
            if bytes_remaining <= 0:
                return ""
            if bytes_remaining <= max_bytes:
                command = f"tail -c +{start_offset + 1} {quoted_path}"
            else:
                command = f"tail -c {max_bytes} {quoted_path}"
        else:
            command = f"tail -c {max_bytes} {quoted_path}"

        output = await self._run_utility(f"if [ -f {quoted_path} ]; then {command}; fi")
        return self._normalize_output(output)

    async def _get_result(
        self,
        log_path: str,
        *,
        start_offset: int | None = None,
        max_bytes: int,
    ) -> ShellResult:
        ansi_output = await self._read_log(
            log_path,
            start_offset=start_offset,
            max_bytes=max_bytes,
        )
        return ShellResult(
            clean_output=strip_ansi(ansi_output),
            ansi_output=ansi_output,
        )

    async def _send_to_session(self, pid_path: str, data: bytes) -> None:
        """Write data to the stdin FIFO of a session."""
        fifo_path = pid_path.replace(".pid", ".fifo")
        container = self._container()

        # Write raw bytes through the FIFO
        escaped = data.decode("utf-8", errors="replace")
        # Use printf to handle special chars
        if data == b"\x03":
            cmd = f"kill -INT $(cat {shlex.quote(pid_path)}) 2>/dev/null || true"
        else:
            # Write through the FIFO pipe
            cmd = f"printf '%s' {shlex.quote(escaped)} > {shlex.quote(fifo_path)}"

        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            None,
            lambda: container.exec_run(["/bin/sh", "-c", cmd], detach=True),
        )

    # ── Shell abstract property implementations ──────────────────────

    @property
    def workspace_path(self) -> str:
        return self._sandbox._config.workspace_path

    @property
    def max_timeout(self) -> int:
        return _MAX_SHELL_TIMEOUT

    @property
    def session_output_tail_bytes(self) -> int:
        return _SHELL_LOG_TAIL_BYTES

    @property
    def command_output_tail_bytes(self) -> int:
        return _SHELL_OUTPUT_TAIL_BYTES

    @property
    def poll_interval(self) -> float:
        return _SHELL_POLL_INTERVAL

    # ── Shell abstract method implementations ────────────────────────

    def validate_session_name(self, session_name: str) -> None:
        if not session_name or not session_name.replace("_", "").replace("-", "").isalnum():
            raise ShellInvalidSessionNameError(
                "Invalid session name. Only alphanumeric characters, "
                "hyphens, and underscores are allowed."
            )

    async def normalize_directory(self, directory: str) -> str:
        normalized = os.path.normpath(directory.strip())
        normalized = str(PurePosixPath(normalized))
        if not normalized.startswith("/"):
            raise ShellRunDirNotFoundError(
                "Start directory must be an absolute path inside the workspace."
            )

        workspace_path = str(PurePosixPath(self.workspace_path))
        if normalized != workspace_path and not normalized.startswith(f"{workspace_path}/"):
            raise ShellRunDirNotFoundError(f"Directory must be inside workspace: {workspace_path}")

        quoted_dir = shlex.quote(normalized)
        try:
            await self._run_utility(f"test -d {quoted_dir}")
        except ShellOperationError as exc:
            raise ShellRunDirNotFoundError(
                f"Directory does not exist or is not a directory: {normalized}"
            ) from exc

        return normalized

    async def create_session_record(
        self,
        session_name: str,
        start_directory: str,
        timeout: int = _DEFAULT_SHELL_TIMEOUT,
    ) -> ShellSessionRecord:
        self.validate_session_name(session_name)
        start_directory = await self.normalize_directory(start_directory)

        container = self._container()
        log_path = self._get_log_path(session_name)
        state_path = self._get_state_path(session_name)
        pid_path = self._get_pid_path(session_name)
        fifo_path = pid_path.replace(".pid", ".fifo")
        runtime_dir = str(PurePosixPath(self.workspace_path) / _SHELL_STORAGE_DIRNAME)

        # Raw prompt string for PS1 (no shlex.quote — embedded directly in double quotes)
        prompt_raw = _PROMPT_FORMAT

        # Bootstrap script that:
        # 1. Creates the runtime directory and cleans stale state
        # 2. Creates a named pipe (FIFO) for stdin forwarding
        # 3. Writes the inner shell script to a file (avoids nested quoting)
        # 4. Runs the inner script under `script` for PTY logging
        # 5. Explicitly updates prompt_seq/cwd state after each command
        #
        # NOTE: `script -c` runs bash non-interactively so PROMPT_COMMAND
        # never fires.  Instead, __ii_agent_prompt is called explicitly:
        #   - once before the read loop (signals initial readiness), and
        #   - after every `eval` (tracks command completion).
        # The FIFO is opened once with `exec 3<>` (read-write) so that
        # the read fd persists across iterations and multi-line writes
        # are not lost.
        inner_script_path = str(
            PurePosixPath(self.workspace_path) / _SHELL_STORAGE_DIRNAME / f"{session_name}.inner.sh"
        )

        bootstrap = f"""
mkdir -p {shlex.quote(runtime_dir)}
rm -f {shlex.quote(log_path)} {shlex.quote(state_path)} {shlex.quote(pid_path)} {shlex.quote(fifo_path)} {shlex.quote(inner_script_path)}
mkfifo {shlex.quote(fifo_path)}
: > {shlex.quote(log_path)}

export II_AGENT_LOG_PATH={shlex.quote(log_path)}
export II_AGENT_STATE_PATH={shlex.quote(state_path)}
export TERM='xterm-256color'
export DISPLAY=:99

# Write the inner shell script to a file to avoid quoting issues
cat > {shlex.quote(inner_script_path)} << 'II_AGENT_INNER_EOF'
#!/bin/bash
export TERM=xterm-256color
export PS1="{prompt_raw}"
__ii_agent_prompt() {{
    {_ENV_SOURCE_SAFE_CMD}
    II_AGENT_PROMPT_SEQ=$(( ${{II_AGENT_PROMPT_SEQ:-0}} + 1 ))
    __ii_agent_state_tmp="${{II_AGENT_STATE_PATH}}.tmp"
    {{
        printf "%s\\n" "$II_AGENT_PROMPT_SEQ"
        pwd
    }} > "$__ii_agent_state_tmp"
    mv "$__ii_agent_state_tmp" "$II_AGENT_STATE_PATH"
}}
# Signal initial readiness (prompt_seq=1)
__ii_agent_prompt
clear
# Open FIFO as fd 3 (read-write keeps it alive across writers)
exec 3<> {fifo_path}
# Each line on the FIFO is a base64-encoded shell command (see
# _b64_frame in docker_shell.py).  Decoding before eval lets multi-line
# payloads — embedded newlines, quotes, here-docs — survive transport
# intact.  A failed decode produces an empty string, which ``eval``
# treats as a no-op; the prompt counter still advances so the protocol
# stays in lockstep with ``pending_prompt_seq`` on the writer side.
while IFS= read -r __ii_agent_b64 <&3; do
    __ii_agent_cmd=$(printf '%s' "$__ii_agent_b64" | base64 -d 2>/dev/null)
    eval "$__ii_agent_cmd"
    __ii_agent_prompt
done
exec 3<&-
II_AGENT_INNER_EOF

# Start the inner script under script(1) for PTY logging
(
    exec script -q -f {shlex.quote(log_path)} -c {shlex.quote(f"bash {inner_script_path}")}
) &
SHELL_PID=$!
echo $SHELL_PID > {shlex.quote(pid_path)}
"""

        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            None,
            lambda: container.exec_run(
                ["/bin/sh", "-c", bootstrap],
                detach=True,
                workdir=start_directory,
            ),
        )

        # Wait for the shell to initialize and produce the first prompt
        try:
            prompt_seq, cwd = await self._wait_for_prompt_internal(
                state_path,
                minimum_prompt_seq=1,
                timeout=timeout,
            )
        except ShellCommandTimeoutError:
            # Clean up on failure
            try:
                await self._run_utility(
                    f"kill $(cat {shlex.quote(pid_path)} 2>/dev/null) 2>/dev/null; "
                    f"rm -f {shlex.quote(pid_path)} {shlex.quote(fifo_path)} "
                    f"{shlex.quote(log_path)} {shlex.quote(state_path)}"
                )
            except Exception:
                pass
            raise

        # Read the PID from the file
        try:
            pid_str = await self._run_utility(f"cat {shlex.quote(pid_path)}")
            pid = int(pid_str.strip())
        except (ValueError, ShellOperationError):
            pid = 0

        return ShellSessionRecord(
            pid=pid,
            cwd=cwd or start_directory,
            log_path=log_path,
            state_path=state_path,
            status=ShellSessionState.IDLE,
            prompt_seq=prompt_seq,
            updated_at=self._shell_timestamp(),
        )

    async def delete_session(
        self,
        session_name: str,
        record: ShellSessionRecord,
    ) -> None:
        pid_path = self._get_pid_path(session_name)
        fifo_path = pid_path.replace(".pid", ".fifo")
        try:
            await self._run_utility(
                f"kill {record.pid} 2>/dev/null; "
                f"rm -f {shlex.quote(pid_path)} {shlex.quote(fifo_path)} "
                f"{shlex.quote(record.log_path)} {shlex.quote(record.state_path)}"
            )
        except ShellOperationError:
            logger.info(f"Shell process {record.pid} already exited for session {session_name}")

    async def is_session_live(self, record: ShellSessionRecord) -> bool:
        try:
            result = await self._run_utility(
                f"kill -0 {record.pid} 2>/dev/null && echo yes || echo no"
            )
            return result.strip() == "yes"
        except ShellOperationError:
            return False

    async def refresh_session_record(
        self,
        record: ShellSessionRecord,
    ) -> tuple[ShellSessionRecord, bool]:
        prompt_seq, cwd = await self._read_state(record.state_path)
        changed = False

        if prompt_seq is not None and prompt_seq != record.prompt_seq:
            record.prompt_seq = prompt_seq
            changed = True
        if cwd and cwd != record.cwd:
            record.cwd = cwd
            changed = True

        if record.pending_prompt_seq is not None:
            if prompt_seq is not None and prompt_seq >= record.pending_prompt_seq:
                record.pending_prompt_seq = None
                record.status = ShellSessionState.IDLE
                changed = True
            elif record.status != ShellSessionState.BUSY:
                record.status = ShellSessionState.BUSY
                changed = True
        elif record.status != ShellSessionState.IDLE:
            record.status = ShellSessionState.IDLE
            changed = True

        if changed:
            record.updated_at = self._shell_timestamp()

        return record, changed

    async def build_command_request(
        self,
        record: ShellSessionRecord,
        command: str,
        run_dir: str | None = None,
    ) -> ShellExecutionRequest:
        log_offset = await self._get_file_size(record.log_path)
        commands_to_send: list[str] = []
        if run_dir:
            commands_to_send.append(f"cd {shlex.quote(run_dir)}")
        if _ENV_SOURCE_CMD not in command:
            commands_to_send.append(_ENV_SOURCE_SAFE_CMD)
        commands_to_send.append("clear")
        commands_to_send.append(command)

        expected_prompt_seq = record.prompt_seq + len(commands_to_send)
        record.status = ShellSessionState.BUSY
        record.last_command_id = str(uuid.uuid4())
        record.pending_prompt_seq = expected_prompt_seq
        record.updated_at = self._shell_timestamp()

        return ShellExecutionRequest(
            record=record,
            stdin=_b64_frame_payload(commands_to_send),
            log_offset=log_offset,
            expected_prompt_seq=expected_prompt_seq,
        )

    async def build_interrupt_request(
        self,
        record: ShellSessionRecord,
    ) -> ShellExecutionRequest:
        log_offset = await self._get_file_size(record.log_path)
        current_prompt_seq = record.prompt_seq
        record.status = ShellSessionState.BUSY
        record.pending_prompt_seq = current_prompt_seq + 1
        record.updated_at = self._shell_timestamp()
        return ShellExecutionRequest(
            record=record,
            stdin=b"\x03",
            log_offset=log_offset,
            expected_prompt_seq=current_prompt_seq + 1,
        )

    async def build_process_input_request(
        self,
        record: ShellSessionRecord,
        data: str,
        press_enter: bool,
    ) -> ShellExecutionRequest:
        if press_enter and record.status != ShellSessionState.BUSY:
            record.status = ShellSessionState.BUSY
            record.pending_prompt_seq = record.prompt_seq + 1
            record.updated_at = self._shell_timestamp()

        # The PTY inner loop reads base64-framed lines (see _b64_frame).
        # Without ``press_enter`` there is nothing to deliver until the
        # caller sends a terminating newline anyway, so we frame only
        # complete payloads. Empty payloads are preserved so callers
        # that do ``press_enter`` after a previous partial write still
        # advance the prompt counter exactly once.
        if press_enter:
            stdin_bytes = _b64_frame_payload([data])
        else:
            stdin_bytes = b""
        return ShellExecutionRequest(
            record=record,
            stdin=stdin_bytes,
        )

    async def send_stdin(
        self,
        session_name: str,
        record: ShellSessionRecord,
        data: bytes,
    ) -> None:
        pid_path = self._get_pid_path(session_name)

        # Check if process is alive
        is_live = await self.is_session_live(record)
        if not is_live:
            raise ShellSessionNotFoundError(f"Session '{session_name}' is no longer available")

        await self._send_to_session(pid_path, data)

    async def wait_for_prompt(
        self,
        record: ShellSessionRecord,
        *,
        minimum_prompt_seq: int,
        timeout: int,
    ) -> ShellSessionRecord:
        await self._wait_for_prompt_internal(
            record.state_path,
            minimum_prompt_seq=minimum_prompt_seq,
            timeout=timeout,
        )
        refreshed_record, _ = await self.refresh_session_record(record)
        return refreshed_record

    async def read_command_output(
        self,
        record: ShellSessionRecord,
        *,
        start_offset: int | None = None,
    ) -> ShellResult:
        return await self._get_result(
            record.log_path,
            start_offset=start_offset,
            max_bytes=self.command_output_tail_bytes,
        )

    async def read_session_output(
        self,
        record: ShellSessionRecord,
    ) -> ShellResult:
        return await self._get_result(
            record.log_path,
            max_bytes=self.session_output_tail_bytes,
        )
