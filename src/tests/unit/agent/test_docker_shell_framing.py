"""Tests for the DockerShell FIFO framing protocol.

The PTY shell wrapper used to deliver commands as raw text joined by
``\n``. When a tool sent a multi-line ``python3 -c "<heredoc>"`` payload
the inner ``bash`` reader split it on newlines and ``eval``'d each
fragment as a separate shell command, producing confusing
``unexpected EOF while looking for matching '"'`` errors that the LLM
later misread as ``ImportError``. The fix base64-frames every command;
these tests lock that contract down so future refactors can't regress
into line-splitting again.
"""

from __future__ import annotations

import asyncio
import base64
from unittest.mock import AsyncMock, MagicMock

from ii_agent.agents.sandboxes.docker_shell import (
    DockerShell,
    _ENV_SOURCE_SAFE_CMD,
    _b64_frame,
    _b64_frame_payload,
)
from ii_agent.agents.sandboxes.shell import ShellSessionRecord, ShellSessionState


def _decode_payload(stdin: bytes) -> list[str]:
    """Decode a FIFO payload back into the original command list."""
    text = stdin.decode("ascii")
    assert text.endswith("\n"), "Payload must end with a newline so the reader's read -r returns"
    lines = text[:-1].split("\n")
    return [base64.b64decode(line).decode("utf-8") for line in lines]


class TestB64Framing:
    def test_single_line_command_round_trips(self) -> None:
        assert base64.b64decode(_b64_frame("ls -la")).decode() == "ls -la"

    def test_multiline_python_heredoc_survives(self) -> None:
        # This is the exact payload class that broke session e965f013.
        cmd = (
            'python3 -c "\n'
            "from PIL import Image\n"
            "img = Image.open('uploads/image_0.png').convert('RGB')\n"
            "print(img.size)\n"
            '"'
        )
        framed = _b64_frame(cmd)
        assert "\n" not in framed, "base64 output must be a single FIFO line"
        assert base64.b64decode(framed).decode() == cmd

    def test_payload_line_count_matches_command_count(self) -> None:
        # The outer protocol relies on this invariant for ``pending_prompt_seq``.
        commands = ["cd /workspace", _ENV_SOURCE_SAFE_CMD, "clear", "echo hello"]
        payload = _b64_frame_payload(commands)
        decoded = _decode_payload(payload)
        assert decoded == commands

    def test_payload_handles_quotes_and_parens(self) -> None:
        # The bug class: bash ``eval`` of partial Python source produced
        # ``syntax error near unexpected token '('``. After base64 framing
        # the reader sees one opaque line and ``eval`` only runs on the
        # decoded whole.
        commands = [
            'echo "hello (world)"',
            "for i in range(samples): print(i)",
            "img.getpixel((x, mid))",
        ]
        decoded = _decode_payload(_b64_frame_payload(commands))
        assert decoded == commands

    def test_payload_with_embedded_newlines(self) -> None:
        # Shell here-docs and multi-line strings must round-trip even though
        # the payload itself contains ``\n`` — base64 strips them.
        commands = ["bash <<'EOF'\necho a\necho b\nEOF"]
        decoded = _decode_payload(_b64_frame_payload(commands))
        assert decoded == commands

    def test_payload_with_unicode(self) -> None:
        commands = ["echo 'héllo wörld 🦀'"]
        decoded = _decode_payload(_b64_frame_payload(commands))
        assert decoded == commands

    def test_empty_command_keeps_one_frame(self) -> None:
        # An empty command is still one prompt advance; the wire frame is
        # ``"" -> b64('') -> ''`` which decodes back to ``''``.
        decoded = _decode_payload(_b64_frame_payload([""]))
        assert decoded == [""]


class _StubSandbox:
    def __init__(self) -> None:
        self._config = MagicMock()
        self._config.workspace_path = "/workspace"


def _make_record(prompt_seq: int = 0) -> ShellSessionRecord:
    return ShellSessionRecord(
        pid=42,
        cwd="/workspace",
        log_path="/workspace/.ii_agent/pty/t.log",
        state_path="/workspace/.ii_agent/pty/t.state",
        status=ShellSessionState.IDLE,
        prompt_seq=prompt_seq,
        pending_prompt_seq=None,
        updated_at="2026-04-25T00:00:00+00:00",
    )


def _make_shell() -> DockerShell:
    # DockerShell only needs ``self._sandbox._config.workspace_path``
    # for the methods we touch.
    shell = DockerShell(_StubSandbox())  # type: ignore[arg-type]
    # ``_get_file_size`` is awaited for ``log_offset``; stub to 0.
    shell._get_file_size = AsyncMock(return_value=0)  # type: ignore[assignment]
    return shell


class TestBuildCommandRequest:
    def _build(self, command: str, *, run_dir: str | None = None) -> bytes:
        shell = _make_shell()

        async def _run() -> bytes:
            req = await shell.build_command_request(_make_record(), command, run_dir=run_dir)
            return req.stdin

        return asyncio.run(_run())

    def test_run_dir_emits_cd_first(self) -> None:
        decoded = _decode_payload(self._build("echo ok", run_dir="/workspace/sub"))
        assert decoded[0] == "cd /workspace/sub"
        # Trailing user command preserved verbatim
        assert decoded[-1] == "echo ok"

    def test_env_source_appended_when_missing(self) -> None:
        decoded = _decode_payload(self._build("ls"))
        assert _ENV_SOURCE_SAFE_CMD in decoded

    def test_env_source_skipped_when_user_command_already_sources(self) -> None:
        decoded = _decode_payload(self._build("source /app/.user_env.sh && echo done"))
        # Only one entry references the env source — the user command itself
        sources = [c for c in decoded if "source /app/.user_env.sh" in c]
        assert len(sources) == 1
        assert sources[0] == "source /app/.user_env.sh && echo done"

    def test_user_command_is_single_b64_frame_even_when_multiline(self) -> None:
        # Regression for session e965f013: a multi-line command must not be
        # fragmented across multiple FIFO read iterations.
        cmd = 'python3 -c "\nfrom PIL import Image\nprint(Image)\n"'
        payload = self._build(cmd)
        # Count actual FIFO frames (newlines).  The user command must occupy
        # exactly one of them no matter how many ``\n`` it contains.
        frames = payload.decode("ascii").rstrip("\n").split("\n")
        # Decoded last frame == verbatim user command.
        assert base64.b64decode(frames[-1]).decode() == cmd

    def test_pending_prompt_seq_matches_frame_count(self) -> None:
        shell = _make_shell()

        async def _run() -> None:
            record = _make_record()
            req = await shell.build_command_request(record, "echo hi", run_dir="/workspace")
            frames = req.stdin.decode("ascii").rstrip("\n").split("\n")
            assert req.expected_prompt_seq == record.prompt_seq + len(frames)
            assert record.pending_prompt_seq == record.prompt_seq + len(frames)

        asyncio.run(_run())


class TestBuildProcessInputRequest:
    def test_press_enter_emits_one_b64_frame(self) -> None:
        shell = _make_shell()
        record = _make_record(prompt_seq=5)
        req = asyncio.run(
            shell.build_process_input_request(record, "echo via stdin", press_enter=True)
        )
        decoded = _decode_payload(req.stdin)
        assert decoded == ["echo via stdin"]
        assert record.pending_prompt_seq == 6

    def test_no_press_enter_emits_empty_payload(self) -> None:
        # Without a terminator the inner reader cannot return anyway, so we
        # send nothing rather than a half-line that would corrupt the stream.
        shell = _make_shell()
        record = _make_record(prompt_seq=5)
        req = asyncio.run(shell.build_process_input_request(record, "partial", press_enter=False))
        assert req.stdin == b""
        assert record.pending_prompt_seq is None
