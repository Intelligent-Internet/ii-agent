"""
Regression Runner — Baseline snapshots and diff reports for skill outputs.

Enables saving "golden" session records as baselines and comparing
subsequent runs to detect regressions in tool call sequences or outputs.

Usage:
    from ii_skills.shared.regression import RegressionRunner, BaselineSnapshot

    runner = RegressionRunner()
    baseline = runner.save_baseline(session_record)

    # Later, after another run:
    diff = runner.compare(new_session, baseline)
    if diff.regression_detected:
        print(diff.format())
"""

import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

logger = logging.getLogger(__name__)


@dataclass
class BaselineSnapshot:
    """A golden reference session for regression comparison."""
    baseline_id: str = field(default_factory=lambda: str(uuid4()))
    skill_name: str = ""
    action: str = ""
    params_hash: str = ""
    tool_sequence_hash: str = ""
    output_checksums: Dict[str, str] = field(default_factory=dict)
    session_record_path: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BaselineSnapshot":
        return cls(
            baseline_id=data.get("baseline_id", str(uuid4())),
            skill_name=data.get("skill_name", ""),
            action=data.get("action", ""),
            params_hash=data.get("params_hash", ""),
            tool_sequence_hash=data.get("tool_sequence_hash", ""),
            output_checksums=data.get("output_checksums", {}),
            session_record_path=data.get("session_record_path", ""),
            created_at=data.get("created_at", ""),
            metadata=data.get("metadata", {}),
        )


@dataclass
class DiffReport:
    """Result of comparing a current session against a baseline."""
    baseline_id: str
    current_run_id: str
    params_match: bool = True
    tool_sequence_match: bool = True
    output_match: bool = True
    tool_sequence_diff: List[str] = field(default_factory=list)
    output_diffs: Dict[str, str] = field(default_factory=dict)
    regression_detected: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def format(self) -> str:
        """Format the diff report as a human-readable string."""
        lines = [
            f"Regression Report: baseline={self.baseline_id[:12]} vs run={self.current_run_id[:12]}",
            f"  Params match:         {'YES' if self.params_match else 'NO'}",
            f"  Tool sequence match:  {'YES' if self.tool_sequence_match else 'NO'}",
            f"  Output match:         {'YES' if self.output_match else 'NO'}",
            f"  Regression detected:  {'YES' if self.regression_detected else 'NO'}",
        ]

        if self.tool_sequence_diff:
            lines.append("  Tool Sequence Diffs:")
            for diff_line in self.tool_sequence_diff[:20]:
                lines.append(f"    {diff_line}")

        if self.output_diffs:
            lines.append("  Output Diffs:")
            for filename, status in self.output_diffs.items():
                lines.append(f"    {filename}: {status}")

        return "\n".join(lines)


class RegressionRunner:
    """Manages baseline snapshots and regression comparisons.

    Baselines are stored as JSON files under:
        baselines_dir/<skill_name>/<action>/<baseline_id>.json
    """

    def __init__(self, baselines_dir: Optional[str] = None):
        """Initialize RegressionRunner.

        Args:
            baselines_dir: Directory for baseline files.
                           Defaults to "output/baselines".
        """
        self._baselines_dir = Path(baselines_dir) if baselines_dir else Path("output/baselines")

    @property
    def baselines_dir(self) -> Path:
        return self._baselines_dir

    def save_baseline(self, session) -> BaselineSnapshot:
        """Save a session record as a golden baseline.

        Args:
            session: A SessionRecord instance.

        Returns:
            The created BaselineSnapshot.
        """
        baseline = BaselineSnapshot(
            skill_name=session.skill_name,
            action=session.action,
            params_hash=session.params_hash(),
            tool_sequence_hash=session.tool_sequence_hash(),
            output_checksums=dict(session.output_checksums),
        )

        # Save the session record alongside the baseline
        baseline_dir = (
            self._baselines_dir / session.skill_name / session.action
        )
        baseline_dir.mkdir(parents=True, exist_ok=True)

        session_path = baseline_dir / f"{baseline.baseline_id}_session.json"
        session.save(session_path)
        baseline.session_record_path = str(session_path)

        # Save baseline metadata
        baseline_path = baseline_dir / f"{baseline.baseline_id}.json"
        with open(baseline_path, "w", encoding="utf-8") as f:
            json.dump(baseline.to_dict(), f, indent=2, default=str)

        logger.info(f"Baseline saved: {baseline_path}")
        return baseline

    def load_baseline(
        self,
        skill_name: str,
        action: str,
        baseline_id: Optional[str] = None,
    ) -> Optional[BaselineSnapshot]:
        """Load a baseline snapshot.

        Args:
            skill_name: The skill name.
            action: The action name.
            baseline_id: Optional specific baseline ID. If None, loads most recent.

        Returns:
            BaselineSnapshot or None.
        """
        baseline_dir = self._baselines_dir / skill_name / action
        if not baseline_dir.exists():
            return None

        if baseline_id:
            filepath = baseline_dir / f"{baseline_id}.json"
            if not filepath.exists():
                return None
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    return BaselineSnapshot.from_dict(json.load(f))
            except Exception as e:
                logger.warning(f"Failed to load baseline {filepath}: {e}")
                return None

        # Load most recent
        baseline_files = sorted(
            [f for f in baseline_dir.glob("*.json") if not f.name.endswith("_session.json")],
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )

        if not baseline_files:
            return None

        try:
            with open(baseline_files[0], "r", encoding="utf-8") as f:
                return BaselineSnapshot.from_dict(json.load(f))
        except Exception as e:
            logger.warning(f"Failed to load baseline: {e}")
            return None

    def compare(self, current, baseline: BaselineSnapshot) -> DiffReport:
        """Compare a current session against a baseline.

        Args:
            current: A SessionRecord instance.
            baseline: A BaselineSnapshot to compare against.

        Returns:
            DiffReport with comparison results.
        """
        report = DiffReport(
            baseline_id=baseline.baseline_id,
            current_run_id=current.run_id,
        )

        # Compare params
        report.params_match = current.params_hash() == baseline.params_hash

        # Compare tool sequence
        current_hash = current.tool_sequence_hash()
        report.tool_sequence_match = current_hash == baseline.tool_sequence_hash

        if not report.tool_sequence_match:
            # Build a diff of tool call names
            report.tool_sequence_diff = self._diff_tool_sequences(
                current, baseline
            )

        # Compare output checksums
        all_files = set(current.output_checksums.keys()) | set(baseline.output_checksums.keys())

        if not all_files:
            report.output_match = True
        else:
            for filename in all_files:
                current_checksum = current.output_checksums.get(filename)
                baseline_checksum = baseline.output_checksums.get(filename)

                if current_checksum is None:
                    report.output_diffs[filename] = "missing"
                    report.output_match = False
                elif baseline_checksum is None:
                    report.output_diffs[filename] = "new"
                    report.output_match = False
                elif current_checksum != baseline_checksum:
                    report.output_diffs[filename] = "changed"
                    report.output_match = False
                else:
                    report.output_diffs[filename] = "match"

        # Determine if regression detected
        report.regression_detected = (
            not report.tool_sequence_match or not report.output_match
        )

        return report

    def _diff_tool_sequences(self, current, baseline: BaselineSnapshot) -> List[str]:
        """Build human-readable diff of tool call sequences."""
        diffs = []

        # Load baseline session for detailed comparison
        baseline_session = None
        if baseline.session_record_path:
            try:
                from ii_skills.shared.session_capture import SessionRecord
                baseline_session = SessionRecord.load(Path(baseline.session_record_path))
            except Exception:
                pass

        if baseline_session is None:
            diffs.append(f"baseline_hash: {baseline.tool_sequence_hash[:16]}")
            diffs.append(f"current_hash:  {current.tool_sequence_hash()[:16]}")
            return diffs

        # Compare call-by-call
        max_len = max(len(current.tool_calls), len(baseline_session.tool_calls))
        for i in range(max_len):
            curr_call = current.tool_calls[i] if i < len(current.tool_calls) else None
            base_call = baseline_session.tool_calls[i] if i < len(baseline_session.tool_calls) else None

            if curr_call and base_call:
                if curr_call.tool_name != base_call.tool_name:
                    diffs.append(
                        f"  [{i}] tool: {base_call.tool_name} -> {curr_call.tool_name}"
                    )
                elif curr_call.tool_input != base_call.tool_input:
                    diffs.append(
                        f"  [{i}] {curr_call.tool_name}: input changed"
                    )
            elif curr_call and not base_call:
                diffs.append(f"  [{i}] + {curr_call.tool_name} (new)")
            elif base_call and not curr_call:
                diffs.append(f"  [{i}] - {base_call.tool_name} (removed)")

        return diffs

    def list_baselines(
        self, skill_name: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """List available baselines.

        Args:
            skill_name: Optional filter by skill name.

        Returns:
            List of baseline summary dicts.
        """
        results = []

        if not self._baselines_dir.exists():
            return results

        if skill_name:
            skill_dirs = [self._baselines_dir / skill_name]
        else:
            skill_dirs = [d for d in self._baselines_dir.iterdir() if d.is_dir()]

        for skill_dir in skill_dirs:
            if not skill_dir.exists():
                continue
            for action_dir in skill_dir.iterdir():
                if not action_dir.is_dir():
                    continue
                for filepath in action_dir.glob("*.json"):
                    if filepath.name.endswith("_session.json"):
                        continue
                    try:
                        with open(filepath, "r", encoding="utf-8") as f:
                            data = json.load(f)
                        results.append({
                            "baseline_id": data.get("baseline_id"),
                            "skill_name": data.get("skill_name"),
                            "action": data.get("action"),
                            "created_at": data.get("created_at"),
                            "params_hash": data.get("params_hash", "")[:16],
                            "path": str(filepath),
                        })
                    except Exception as e:
                        logger.warning(f"Failed to read baseline {filepath}: {e}")

        return results

    def run_regression_suite(
        self,
        sessions: List,
        skill_name: Optional[str] = None,
    ) -> List[DiffReport]:
        """Compare sessions against their matching baselines.

        Args:
            sessions: List of SessionRecord instances.
            skill_name: Optional filter.

        Returns:
            List of DiffReport results.
        """
        reports = []

        for session in sessions:
            if skill_name and session.skill_name != skill_name:
                continue

            baseline = self.load_baseline(session.skill_name, session.action)
            if baseline is None:
                continue

            report = self.compare(session, baseline)
            reports.append(report)

        return reports
