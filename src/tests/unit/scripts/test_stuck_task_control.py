from __future__ import annotations

from pathlib import Path
import subprocess

import pytest


pytestmark = pytest.mark.unit


def _get_script_path() -> Path:
    current = Path(__file__).resolve()
    for parent in current.parents:
        candidate = parent / "scripts" / "local" / "stuck_task_control.sh"
        if candidate.exists():
            return candidate
    raise FileNotFoundError("Could not locate scripts/local/stuck_task_control.sh")


def test_rejects_invalid_session_prefix_before_docker_check():
    script_path = _get_script_path()

    result = subprocess.run(
        ["bash", str(script_path), "--session", "abc' OR 1=1 --"],
        capture_output=True,
        text=True,
        check=False,
    )

    combined_output = result.stdout + result.stderr
    assert result.returncode == 1
    assert "contains invalid characters" in combined_output
    assert "PostgreSQL container" not in combined_output


def test_rejects_invalid_task_prefix_before_docker_check():
    script_path = _get_script_path()

    result = subprocess.run(
        ["bash", str(script_path), "--task", "a63c2a80$HOME"],
        capture_output=True,
        text=True,
        check=False,
    )

    combined_output = result.stdout + result.stderr
    assert result.returncode == 1
    assert "contains invalid characters" in combined_output
    assert "PostgreSQL container" not in combined_output
