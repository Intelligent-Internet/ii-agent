"""Ephemeral PTY terminals bound to live Socket.IO connections."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING

import socketio

from ii_agent.agents.sandboxes.terminal import (
    LiveTerminalHandle,
    LiveTerminalNotFoundError,
)
from ii_agent.core.db import get_db_session_local
from ii_agent.core.logger import logger

if TYPE_CHECKING:
    from ii_agent.agents.sandboxes.service import SandboxService
    from ii_agent.sessions.schemas import SessionInfo


_DEFAULT_COLS = 120
_DEFAULT_ROWS = 40
_MIN_COLS = 40
_MAX_COLS = 240
_MIN_ROWS = 12
_MAX_ROWS = 80
_TERMINAL_CWD = "/workspace"
_PTY_ENVS = {
    "TERM": "xterm-256color",
    "COLORTERM": "truecolor",
}
_BOOTSTRAP_COMMAND = (
    "export TERM='xterm-256color'\n"
    "export COLORTERM='truecolor'\n"
    "source /app/.user_env.sh >/dev/null 2>&1 || true\n"
    "clear\n"
)
_BOOTSTRAP_RETRY_ATTEMPTS = 10
_BOOTSTRAP_RETRY_DELAY_SECONDS = 0.1


@dataclass
class _LiveTerminalState:
    sid: str
    terminal_id: str
    session_id: str
    pid: int
    handle: LiveTerminalHandle
    wait_task: asyncio.Task[None] | None = None


class LiveTerminalService:
    """Manage one ephemeral PTY per connected browser socket."""

    def __init__(self, *, sandbox_service: SandboxService) -> None:
        self._sandbox_service = sandbox_service
        self._sio: socketio.AsyncServer | None = None
        self._terminals: dict[str, _LiveTerminalState] = {}
        self._lock = asyncio.Lock()
        self._sid_locks: dict[str, asyncio.Lock] = {}

    def bind_socketio(self, sio: socketio.AsyncServer) -> None:
        self._sio = sio

    async def shutdown(self) -> None:
        async with self._lock:
            sids = list(self._terminals.keys())

        for sid in sids:
            await self.close_terminal(sid, emit_event=False)

    @staticmethod
    def normalize_size(cols: int | None, rows: int | None) -> tuple[int, int]:
        safe_cols = _DEFAULT_COLS if cols is None else max(_MIN_COLS, min(cols, _MAX_COLS))
        safe_rows = _DEFAULT_ROWS if rows is None else max(_MIN_ROWS, min(rows, _MAX_ROWS))
        return safe_cols, safe_rows

    async def create_terminal(
        self,
        sid: str,
        *,
        session_info: SessionInfo,
        terminal_id: str,
        cols: int | None,
        rows: int | None,
    ) -> None:
        sid_lock = self._get_sid_lock(sid)
        try:
            async with sid_lock:
                await self._create_terminal_locked(
                    sid,
                    session_info=session_info,
                    terminal_id=terminal_id,
                    cols=cols,
                    rows=rows,
                )
        finally:
            await self._cleanup_sid_lock_if_idle(sid, sid_lock)

    async def _create_terminal_locked(
        self,
        sid: str,
        *,
        session_info: SessionInfo,
        terminal_id: str,
        cols: int | None,
        rows: int | None,
    ) -> None:
        await self._close_terminal_locked(sid, emit_event=False)

        size_cols, size_rows = self.normalize_size(cols, rows)
        loop = asyncio.get_running_loop()

        handle: LiveTerminalHandle | None = None
        state_registered = False
        try:
            async with get_db_session_local() as db:
                sandbox_manager = await self._sandbox_service.get_sandbox_for_session(
                    db, session_info.id
                )
            if sandbox_manager is None:
                raise RuntimeError(f"No sandbox found for session {session_info.id}")

            def on_data(data: bytes) -> None:
                text = data.decode("utf-8", errors="replace")
                if not text:
                    return
                loop.call_soon_threadsafe(
                    self._schedule_emit,
                    sid,
                    "pty_output",
                    {"terminal_id": terminal_id, "data": text},
                )

            handle = await sandbox_manager.create_live_terminal(
                cols=size_cols,
                rows=size_rows,
                on_data=on_data,
                cwd=_TERMINAL_CWD,
                envs=_PTY_ENVS,
                timeout=0,
            )

            await self._send_bootstrap_with_retry(
                handle=handle,
            )

            state = _LiveTerminalState(
                sid=sid,
                terminal_id=terminal_id,
                session_id=str(session_info.id),
                pid=handle.pid,
                handle=handle,
            )
            state.wait_task = asyncio.create_task(self._wait_for_exit(state))

            async with self._lock:
                self._terminals[sid] = state
                state_registered = True

            await self._emit(
                sid,
                "pty_ready",
                {
                    "terminal_id": terminal_id,
                    "pid": handle.pid,
                    "cols": size_cols,
                    "rows": size_rows,
                },
            )
        except Exception:  # noqa: BLE001
            logger.exception(f"Failed to create live PTY for session {session_info.id}")
            if state_registered:
                await self._close_terminal_locked(
                    sid,
                    terminal_id=terminal_id,
                    emit_event=False,
                )
            elif handle is not None:
                try:
                    await handle.kill()
                except Exception:  # noqa: BLE001
                    logger.warning("Failed to kill PTY after create failure", exc_info=True)
                try:
                    await handle.disconnect()
                except Exception:  # noqa: BLE001
                    logger.warning(
                        "Failed to disconnect PTY handle after create failure",
                        exc_info=True,
                    )
            await self._emit(
                sid,
                "pty_error",
                {
                    "terminal_id": terminal_id,
                    "message": "Unable to start terminal",
                },
            )

    async def write_input(self, sid: str, *, terminal_id: str, data: str) -> None:
        sid_lock = self._get_sid_lock(sid)
        try:
            async with sid_lock:
                state = await self._get_state(sid, terminal_id=terminal_id)
                if state is None:
                    return

                try:
                    await state.handle.send_input(data.encode())
                except LiveTerminalNotFoundError:
                    await self._handle_terminal_missing(state)
                except Exception:  # noqa: BLE001
                    logger.exception(f"Failed to write to live PTY {state.pid}")
                    await self._emit(
                        sid,
                        "pty_error",
                        {
                            "terminal_id": terminal_id,
                            "message": "Unable to write to terminal",
                        },
                    )
        finally:
            await self._cleanup_sid_lock_if_idle(sid, sid_lock)

    async def resize_terminal(
        self,
        sid: str,
        *,
        terminal_id: str,
        cols: int | None,
        rows: int | None,
    ) -> None:
        sid_lock = self._get_sid_lock(sid)
        try:
            async with sid_lock:
                state = await self._get_state(sid, terminal_id=terminal_id)
                if state is None:
                    return

                try:
                    size_cols, size_rows = self.normalize_size(cols, rows)
                    await state.handle.resize(size_cols, size_rows)
                except LiveTerminalNotFoundError:
                    await self._handle_terminal_missing(state)
                except Exception:  # noqa: BLE001
                    logger.exception(f"Failed to resize live PTY {state.pid}")
        finally:
            await self._cleanup_sid_lock_if_idle(sid, sid_lock)

    async def close_terminal(
        self,
        sid: str,
        *,
        terminal_id: str | None = None,
        emit_event: bool = True,
    ) -> None:
        sid_lock = self._get_sid_lock(sid)
        try:
            async with sid_lock:
                await self._close_terminal_locked(
                    sid,
                    terminal_id=terminal_id,
                    emit_event=emit_event,
                )
        finally:
            await self._cleanup_sid_lock_if_idle(sid, sid_lock)

    async def _close_terminal_locked(
        self,
        sid: str,
        *,
        terminal_id: str | None = None,
        emit_event: bool = True,
    ) -> None:
        state = await self._pop_state(sid, terminal_id=terminal_id)
        if state is None:
            return

        wait_task = state.wait_task
        if wait_task is not None:
            await self._cancel_wait_task(wait_task)

        try:
            await state.handle.kill()
        except LiveTerminalNotFoundError:
            pass
        except Exception:  # noqa: BLE001
            logger.warning(f"Failed to kill PTY {state.pid} during close", exc_info=True)

        try:
            await state.handle.disconnect()
        except Exception:  # noqa: BLE001
            logger.warning(
                f"Failed to disconnect PTY handle {state.pid} during close", exc_info=True
            )

        if emit_event:
            await self._emit(
                sid,
                "pty_closed",
                {"terminal_id": state.terminal_id},
            )

    async def _send_bootstrap_with_retry(
        self,
        *,
        handle: LiveTerminalHandle,
    ) -> None:
        for attempt in range(_BOOTSTRAP_RETRY_ATTEMPTS):
            try:
                await handle.send_input(_BOOTSTRAP_COMMAND.encode())
                return
            except LiveTerminalNotFoundError:
                if attempt == _BOOTSTRAP_RETRY_ATTEMPTS - 1:
                    raise
                await asyncio.sleep(_BOOTSTRAP_RETRY_DELAY_SECONDS)

    async def _wait_for_exit(self, state: _LiveTerminalState) -> None:
        exit_code: int | None = None
        try:
            exit_code = await state.handle.wait()
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            logger.exception(f"PTY wait failed for pid {state.pid}")
            await self._emit(
                state.sid,
                "pty_error",
                {
                    "terminal_id": state.terminal_id,
                    "message": "Terminal connection was interrupted",
                },
            )
        finally:
            removed = await self._pop_state(
                state.sid,
                terminal_id=state.terminal_id,
                pid=state.pid,
            )
            if removed is not None:
                try:
                    await removed.handle.disconnect()
                except Exception:  # noqa: BLE001
                    logger.warning(
                        "Failed to disconnect PTY handle after exit",
                        exc_info=True,
                    )
                await self._emit(
                    removed.sid,
                    "pty_closed",
                    {
                        "terminal_id": removed.terminal_id,
                        "exit_code": exit_code,
                    },
                )
                sid_lock = self._sid_locks.get(removed.sid)
                if sid_lock is not None:
                    await self._cleanup_sid_lock_if_idle(removed.sid, sid_lock)

    async def _handle_terminal_missing(self, state: _LiveTerminalState) -> None:
        removed = await self._pop_state(
            state.sid,
            terminal_id=state.terminal_id,
            pid=state.pid,
        )
        if removed is None:
            return

        if removed.wait_task is not None:
            await self._cancel_wait_task(removed.wait_task)

        try:
            await removed.handle.disconnect()
        except Exception:  # noqa: BLE001
            logger.warning("Failed to disconnect missing PTY handle", exc_info=True)

        await self._emit(
            removed.sid,
            "pty_closed",
            {"terminal_id": removed.terminal_id},
        )

    async def _get_state(
        self,
        sid: str,
        *,
        terminal_id: str | None = None,
    ) -> _LiveTerminalState | None:
        async with self._lock:
            state = self._terminals.get(sid)
            if state is None:
                return None
            if terminal_id is not None and state.terminal_id != terminal_id:
                return None
            return state

    async def _pop_state(
        self,
        sid: str,
        *,
        terminal_id: str | None = None,
        pid: int | None = None,
    ) -> _LiveTerminalState | None:
        async with self._lock:
            state = self._terminals.get(sid)
            if state is None:
                return None
            if terminal_id is not None and state.terminal_id != terminal_id:
                return None
            if pid is not None and state.pid != pid:
                return None
            return self._terminals.pop(sid, None)

    async def _cancel_wait_task(self, wait_task: asyncio.Task[None]) -> None:
        if wait_task is asyncio.current_task():
            return

        wait_task.cancel()
        try:
            await wait_task
        except asyncio.CancelledError:
            pass
        except Exception:  # noqa: BLE001
            logger.warning("Failed while cancelling PTY wait task", exc_info=True)

    def _get_sid_lock(self, sid: str) -> asyncio.Lock:
        lock = self._sid_locks.get(sid)
        if lock is None:
            lock = asyncio.Lock()
            self._sid_locks[sid] = lock
        return lock

    async def _cleanup_sid_lock_if_idle(self, sid: str, sid_lock: asyncio.Lock) -> None:
        if sid_lock.locked():
            return
        async with self._lock:
            if (
                not sid_lock.locked()
                and sid not in self._terminals
                and self._sid_locks.get(sid) is sid_lock
            ):
                self._sid_locks.pop(sid, None)

    def _schedule_emit(self, sid: str, event_name: str, payload: dict[str, object]) -> None:
        asyncio.create_task(self._emit(sid, event_name, payload))

    async def _emit(self, sid: str, event_name: str, payload: dict[str, object]) -> None:
        if self._sio is None:
            return
        await self._sio.emit(event_name, payload, room=sid)
