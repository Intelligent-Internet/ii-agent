"""
Session Capture — Records full execution sessions for replay and regression.

Captures the ordered sequence of tool calls, their inputs/outputs,
and final skill output. Enables determinism checks and baseline comparisons.

Usage:
    from ii_skills.shared.session_capture import SessionRecord, CapturedToolCall

    record = SessionRecord(
        run_id="abc-123",
        skill_name="ib_toolkit",
        action="quick_lbo_analysis",
        user_params={"ebitda": 50},
    )
    record.add_tool_call("skill_ib_toolkit", {"action": "analyze"}, {"result": "ok"}, 123.4)
    record.complete(final_output={"irr": 0.25})
    record.save(Path("output/sessions/session.json"))
"""

import hashlib
import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class CapturedToolCall:
    """A single tool call captured during a session."""
    sequence_index: int
    tool_name: str
    tool_input: Dict[str, Any]
    tool_output: Dict[str, Any]
    duration_ms: float
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    is_error: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class SessionRecord:
    """Complete record of a skill execution session.

    Captures everything needed for replay and regression testing:
    - User parameters
    - Ordered tool call sequence
    - Final output with checksums
    """
    run_id: str
    skill_name: str
    action: str
    started_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    completed_at: Optional[str] = None
    user_params: Dict[str, Any] = field(default_factory=dict)
    tool_calls: List[CapturedToolCall] = field(default_factory=list)
    final_output: Dict[str, Any] = field(default_factory=dict)
    output_checksums: Dict[str, str] = field(default_factory=dict)
    workspace_path: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def add_tool_call(
        self,
        tool_name: str,
        tool_input: Dict[str, Any],
        tool_output: Dict[str, Any],
        duration_ms: float,
        is_error: bool = False,
    ) -> CapturedToolCall:
        """Add a tool call to the session.

        Args:
            tool_name: Name of the tool called.
            tool_input: Input parameters.
            tool_output: Output result.
            duration_ms: Execution duration in milliseconds.
            is_error: Whether the call resulted in an error.

        Returns:
            The created CapturedToolCall.
        """
        call = CapturedToolCall(
            sequence_index=len(self.tool_calls),
            tool_name=tool_name,
            tool_input=tool_input,
            tool_output=tool_output,
            duration_ms=duration_ms,
            is_error=is_error,
        )
        self.tool_calls.append(call)
        return call

    def complete(
        self,
        final_output: Optional[Dict[str, Any]] = None,
        output_files: Optional[Dict[str, str]] = None,
    ) -> None:
        """Mark the session as completed.

        Args:
            final_output: The skill's final result dict.
            output_files: Optional dict of filename -> filepath for checksum computation.
        """
        self.completed_at = datetime.now(timezone.utc).isoformat()
        if final_output is not None:
            self.final_output = final_output

        if output_files:
            for name, filepath in output_files.items():
                try:
                    path = Path(filepath)
                    if path.exists():
                        sha = hashlib.sha256(path.read_bytes()).hexdigest()
                        self.output_checksums[name] = sha
                except Exception as e:
                    logger.warning(f"Failed to compute checksum for {name}: {e}")

    def tool_sequence_hash(self) -> str:
        """Compute SHA-256 of the ordered tool call sequence.

        Uses (tool_name, canonical_tool_input) tuples to produce
        a determinism fingerprint.

        Returns:
            Hex digest string.
        """
        items = []
        for call in self.tool_calls:
            canonical = json.dumps(
                {"tool_name": call.tool_name, "tool_input": call.tool_input},
                sort_keys=True,
                default=str,
            )
            items.append(canonical)

        combined = "\n".join(items)
        return hashlib.sha256(combined.encode("utf-8")).hexdigest()

    def params_hash(self) -> str:
        """Compute SHA-256 of the canonical user parameters.

        Returns:
            Hex digest string.
        """
        canonical = json.dumps(self.user_params, sort_keys=True, default=str)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "run_id": self.run_id,
            "skill_name": self.skill_name,
            "action": self.action,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "user_params": self.user_params,
            "tool_calls": [c.to_dict() for c in self.tool_calls],
            "final_output": self.final_output,
            "output_checksums": self.output_checksums,
            "workspace_path": self.workspace_path,
            "metadata": self.metadata,
            "tool_sequence_hash": self.tool_sequence_hash(),
            "params_hash": self.params_hash(),
        }

    def save(self, path: Path) -> None:
        """Save session record to a JSON file.

        Args:
            path: File path to write to.
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2, default=str)

    @classmethod
    def load(cls, path: Path) -> "SessionRecord":
        """Load a session record from a JSON file.

        Args:
            path: File path to read from.

        Returns:
            SessionRecord instance.
        """
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        tool_calls = [
            CapturedToolCall(**tc) for tc in data.get("tool_calls", [])
        ]

        return cls(
            run_id=data.get("run_id", ""),
            skill_name=data.get("skill_name", ""),
            action=data.get("action", ""),
            started_at=data.get("started_at", ""),
            completed_at=data.get("completed_at"),
            user_params=data.get("user_params", {}),
            tool_calls=tool_calls,
            final_output=data.get("final_output", {}),
            output_checksums=data.get("output_checksums", {}),
            workspace_path=data.get("workspace_path"),
            metadata=data.get("metadata", {}),
        )
