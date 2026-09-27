"""Persistent shell sessions for E2B sandboxes."""

from __future__ import annotations

import asyncio
import posixpath
import shlex
import uuid
from datetime import datetime, timezone
from pathlib import PurePosixPath
from typing import TYPE_CHECKING

from e2b import CommandResult, PtySize
from e2b.exceptions import NotFoundException

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
    from e2b_code_interpreter import AsyncSandbox

    from ii_agent.agents.sandboxes.e2b import E2BSandbox


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


class E2BShell(Shell):
    """Persistent shell runtime backend for :class:`E2BSandbox`."""

    def __init__(self, sandbox: E2BSandbox) -> None:
        self._sandbox = sandbox

    @staticmethod
    def _discard_pty_data(_: bytes) -> None:
        return None

    @staticmethod
    def _shell_timestamp() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _normalize_output(text: str) -> str:
        return sanitize_shell_output(text)

    def validate_session_name(self, session_name: str) -> None:
        if not session_name or not session_name.replace("_", "").replace("-", "").isalnum():
            raise ShellInvalidSessionNameError(
                "Invalid session name. Only alphanumeric characters, hyphens, and underscores are allowed."
            )

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

    def _get_log_path(self, session_name: str) -> str:
        return str(
            PurePosixPath(self.workspace_path) / _SHELL_STORAGE_DIRNAME / f"{session_name}.log"
        )

    def _get_state_path(self, session_name: str) -> str:
        return str(
            PurePosixPath(self.workspace_path) / _SHELL_STORAGE_DIRNAME / f"{session_name}.state"
        )

    async def _connected_sandbox(self) -> AsyncSandbox:
        await self._sandbox._ensure_sandbox_connection()
        sandbox = self._sandbox.sandbox
        if sandbox is None:
            raise ShellOperationError("connected_sandbox", "Sandbox connection is not available")
        return sandbox

    async def _run_utility_command(
        self,
        command: str,
        *,
        timeout: int = _SHELL_UTILITY_TIMEOUT,
    ) -> str:
        sandbox = await self._connected_sandbox()
        result = await sandbox.commands.run(
            command,
            background=False,
            timeout=timeout,
        )

        if not isinstance(result, CommandResult):
            raise ShellOperationError(
                "run_utility_command",
                f"Unexpected result: {result}",
            )

        if result.exit_code != 0:
            error_msg = result.stderr or result.stdout or f"Exit code: {result.exit_code}"
            raise ShellOperationError("run_utility_command", error_msg)

        return result.stdout

    async def normalize_directory(self, directory: str) -> str:
        normalized = posixpath.normpath(directory.strip())
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
            await self._run_utility_command(f"test -d {quoted_dir}")
        except ShellOperationError as exc:
            raise ShellRunDirNotFoundError(
                f"Directory does not exist or is not a directory: {normalized}"
            ) from exc

        return normalized

    async def _read_state(self, state_path: str) -> tuple[int | None, str | None]:
        sandbox = await self._connected_sandbox()
        try:
            if not await sandbox.files.exists(state_path):
                return None, None
            content = await sandbox.files.read(state_path, format="text")
        except Exception:  # noqa: BLE001
            return None, None

        if isinstance(content, bytes):
            content = content.decode("utf-8", errors="replace")

        lines = content.splitlines()
        if len(lines) < 2:
            return None, None

        try:
            prompt_seq = int(lines[0].strip())
        except ValueError:
            return None, None

        cwd = lines[1].strip() or None
        return prompt_seq, cwd

    async def _wait_for_prompt(
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
        output = await self._run_utility_command(
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

        output = await self._run_utility_command(f"if [ -f {quoted_path} ]; then {command}; fi")
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

    async def is_session_live(self, record: ShellSessionRecord) -> bool:
        sandbox = await self._connected_sandbox()
        try:
            handle = await sandbox.pty.connect(
                record.pid,
                on_data=self._discard_pty_data,
                timeout=0,
            )
            await handle.disconnect()
        except NotFoundException:
            return False
        except Exception as exc:  # noqa: BLE001
            raise ShellOperationError(
                "is_session_live",
                f"Failed to connect to PTY {record.pid}: {exc}",
            ) from exc

        return await sandbox.files.exists(record.state_path)

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

    def _build_outer_bootstrap(
        self,
        *,
        log_path: str,
        state_path: str,
    ) -> str:
        runtime_dir = str(PurePosixPath(self.workspace_path) / _SHELL_STORAGE_DIRNAME)
        lines = [
            f"export II_AGENT_LOG_PATH={shlex.quote(log_path)}",
            f"export II_AGENT_STATE_PATH={shlex.quote(state_path)}",
            f"mkdir -p {shlex.quote(runtime_dir)}",
            f": > {shlex.quote(log_path)}",
            f"rm -f {shlex.quote(state_path)} {shlex.quote(state_path + '.tmp')}",
            "export TERM='xterm-256color'",
            f"script -q -f {shlex.quote(log_path)} -c 'bash --noprofile --norc -i'",
        ]
        return "\n".join(lines) + "\n"

    def _build_inner_bootstrap(self) -> str:
        prompt_value = shlex.quote(_PROMPT_FORMAT)
        return (
            "export TERM='xterm-256color'\n"
            f"export PS1={prompt_value}\n"
            "__ii_agent_prompt() {\n"
            f"  {_ENV_SOURCE_SAFE_CMD}\n"
            "  II_AGENT_PROMPT_SEQ=$(( ${II_AGENT_PROMPT_SEQ:-0} + 1 ))\n"
            '  __ii_agent_state_tmp="${II_AGENT_STATE_PATH}.tmp"\n'
            "  {\n"
            "    printf '%s\\n' \"$II_AGENT_PROMPT_SEQ\"\n"
            "    pwd\n"
            '  } > "$__ii_agent_state_tmp"\n'
            '  mv "$__ii_agent_state_tmp" "$II_AGENT_STATE_PATH"\n'
            "}\n"
            "PROMPT_COMMAND='__ii_agent_prompt'\n"
            "clear\n"
        )

    async def create_session_record(
        self,
        session_name: str,
        start_directory: str,
        timeout: int = _DEFAULT_SHELL_TIMEOUT,
    ) -> ShellSessionRecord:
        self.validate_session_name(session_name)
        start_directory = await self.normalize_directory(start_directory)

        sandbox = await self._connected_sandbox()
        terminal = await sandbox.pty.create(
            PtySize(cols=120, rows=40),
            on_data=self._discard_pty_data,
            cwd=start_directory,
            timeout=0,
        )

        log_path = self._get_log_path(session_name)
        state_path = self._get_state_path(session_name)

        try:
            await sandbox.pty.send_stdin(
                terminal.pid,
                self._build_outer_bootstrap(
                    log_path=log_path,
                    state_path=state_path,
                ).encode(),
            )
            await asyncio.sleep(0.5)
            await sandbox.pty.send_stdin(
                terminal.pid,
                self._build_inner_bootstrap().encode(),
            )
            prompt_seq, cwd = await self._wait_for_prompt(
                state_path,
                minimum_prompt_seq=1,
                timeout=timeout,
            )
        except Exception:
            try:
                await sandbox.pty.kill(terminal.pid)
            except Exception:  # noqa: BLE001
                logger.warning(
                    f"Failed to clean up PTY {terminal.pid} during shell session bootstrap",
                    exc_info=True,
                )
            raise
        finally:
            await terminal.disconnect()

        return ShellSessionRecord(
            pid=terminal.pid,
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
        sandbox = await self._connected_sandbox()
        try:
            await sandbox.pty.kill(record.pid)
        except NotFoundException:
            logger.info(f"PTY {record.pid} already exited for session {session_name}")

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
            stdin=("\n".join(commands_to_send) + "\n").encode(),
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

        stdin_data = data + ("\n" if press_enter else "")
        return ShellExecutionRequest(
            record=record,
            stdin=stdin_data.encode(),
        )

    async def send_stdin(
        self,
        session_name: str,
        record: ShellSessionRecord,
        data: bytes,
    ) -> None:
        sandbox = await self._connected_sandbox()
        try:
            await sandbox.pty.send_stdin(record.pid, data)
        except NotFoundException as exc:
            raise ShellSessionNotFoundError(
                f"Session '{session_name}' is no longer available"
            ) from exc

    async def wait_for_prompt(
        self,
        record: ShellSessionRecord,
        *,
        minimum_prompt_seq: int,
        timeout: int,
    ) -> ShellSessionRecord:
        await self._wait_for_prompt(
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
