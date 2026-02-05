"""
Agent Workspace Artifacts — Opinionated per-execution workspaces.

Every skill execution gets a dedicated workspace with:
- Deterministic file naming
- Artifact manifests with provenance + SHA-256 checksums
- Replayable event logs (events.jsonl)
- Cross-reference to telemetry via run_id

Directory layout:
    output/workspaces/<YYYY-MM-DD>/<skill>_<action>_<short-run-id>/
        manifest.json       # Run metadata, inputs, outputs, provenance
        events.jsonl        # Chronological event log
        outputs/            # Generated artifacts
        inputs/             # Input parameter snapshot

Naming convention:
    <skill>_<action>_<YYYYMMDD_HHmmss>_<short-run-id>.<ext>
"""

import hashlib
import json
import logging
import os
from contextlib import contextmanager
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

logger = logging.getLogger(__name__)

MANIFEST_SCHEMA_VERSION = "1.0.0"
DEFAULT_WORKSPACE_ROOT = "output/workspaces"


# ---------------------------------------------------------------------------
# Artifact Record
# ---------------------------------------------------------------------------

@dataclass
class ArtifactRecord:
    """Metadata for a single output artifact."""
    path: str                               # Relative to workspace root
    artifact_type: str                      # e.g. "excel", "json", "pptx", "pdf"
    size_bytes: int = 0
    checksum_sha256: str = ""
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Workspace Manifest
# ---------------------------------------------------------------------------

@dataclass
class WorkspaceManifest:
    """Serializable manifest capturing full run context."""
    schema_version: str = MANIFEST_SCHEMA_VERSION
    run_id: str = field(default_factory=lambda: str(uuid4()))
    skill_name: str = ""
    action: str = ""
    status: str = "running"                 # running / completed / failed
    started_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    completed_at: Optional[str] = None
    inputs: Dict[str, Any] = field(default_factory=dict)
    outputs: List[Dict[str, Any]] = field(default_factory=list)
    provenance: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        return d

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, default=str)


# ---------------------------------------------------------------------------
# Workspace
# ---------------------------------------------------------------------------

class Workspace:
    """Active execution workspace with file management and event logging.

    Created by WorkspaceManager for each skill execution. Provides:
    - get_output_path(): deterministic file naming
    - register_artifact(): track outputs with checksums
    - log_event(): append to events.jsonl
    - complete() / fail(): finalize the manifest
    """

    def __init__(
        self,
        workspace_dir: Path,
        manifest: WorkspaceManifest,
    ):
        self._dir = workspace_dir
        self._manifest = manifest
        self._outputs_dir = workspace_dir / "outputs"
        self._inputs_dir = workspace_dir / "inputs"
        self._events_path = workspace_dir / "events.jsonl"
        self._manifest_path = workspace_dir / "manifest.json"
        self._artifacts: List[ArtifactRecord] = []

        # Create directory structure
        self._outputs_dir.mkdir(parents=True, exist_ok=True)
        self._inputs_dir.mkdir(parents=True, exist_ok=True)

        # Write initial manifest
        self._write_manifest()

        # Log workspace creation event
        self.log_event("workspace_created", {
            "workspace_dir": str(workspace_dir),
            "skill_name": manifest.skill_name,
            "action": manifest.action,
        })

    @property
    def run_id(self) -> str:
        return self._manifest.run_id

    @property
    def short_run_id(self) -> str:
        return self._manifest.run_id[:8]

    @property
    def workspace_dir(self) -> Path:
        return self._dir

    @property
    def outputs_dir(self) -> Path:
        return self._outputs_dir

    @property
    def manifest(self) -> WorkspaceManifest:
        return self._manifest

    def get_output_path(self, extension: str, suffix: str = "") -> Path:
        """Generate a deterministic output file path.

        Convention: <skill>_<action>_<YYYYMMDD_HHmmss>_<short-run-id>.<ext>

        Args:
            extension: File extension without dot (e.g. "xlsx", "json")
            suffix: Optional suffix before extension (e.g. "_summary")

        Returns:
            Absolute Path in the outputs/ directory
        """
        now = datetime.now(timezone.utc)
        timestamp = now.strftime("%Y%m%d_%H%M%S")
        skill = self._manifest.skill_name.replace(" ", "_")
        action = self._manifest.action.replace(" ", "_")
        short_id = self.short_run_id

        filename = f"{skill}_{action}_{timestamp}_{short_id}{suffix}.{extension}"
        return self._outputs_dir / filename

    def register_artifact(
        self,
        path: str | Path,
        artifact_type: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ArtifactRecord:
        """Register an output artifact and compute its checksum.

        Args:
            path: Absolute or workspace-relative path to the file
            artifact_type: Type hint (auto-detected from extension if empty)
            metadata: Optional extra metadata

        Returns:
            ArtifactRecord with populated size and checksum
        """
        abs_path = Path(path)
        if not abs_path.is_absolute():
            abs_path = self._dir / path

        # Compute relative path for manifest
        try:
            rel_path = abs_path.relative_to(self._dir)
        except ValueError:
            rel_path = abs_path

        # Auto-detect type from extension
        if not artifact_type:
            ext = abs_path.suffix.lstrip(".")
            type_map = {
                "xlsx": "excel", "xls": "excel",
                "pptx": "powerpoint", "ppt": "powerpoint",
                "pdf": "pdf",
                "json": "json",
                "csv": "csv",
                "png": "image", "jpg": "image", "jpeg": "image",
                "html": "html",
                "txt": "text", "md": "text",
            }
            artifact_type = type_map.get(ext, ext)

        # Size and checksum
        size_bytes = 0
        checksum = ""
        if abs_path.exists():
            size_bytes = abs_path.stat().st_size
            checksum = self._compute_sha256(abs_path)

        record = ArtifactRecord(
            path=str(rel_path),
            artifact_type=artifact_type,
            size_bytes=size_bytes,
            checksum_sha256=checksum,
            metadata=metadata or {},
        )
        self._artifacts.append(record)
        self._manifest.outputs.append(record.to_dict())

        self.log_event("artifact_registered", {
            "path": str(rel_path),
            "type": artifact_type,
            "size_bytes": size_bytes,
        })

        return record

    def log_event(self, event_type: str, data: Optional[Dict[str, Any]] = None) -> None:
        """Append an event to events.jsonl.

        Args:
            event_type: Event name (e.g. "workspace_created", "artifact_registered")
            data: Optional event payload
        """
        event = {
            "run_id": self._manifest.run_id,
            "event_type": event_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": data or {},
        }
        try:
            with open(self._events_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(event, default=str) + "\n")
        except OSError as e:
            logger.warning(f"Failed to write event: {e}")

    def save_inputs(self, inputs: Dict[str, Any]) -> None:
        """Snapshot input parameters to inputs/params.json."""
        self._manifest.inputs = inputs
        try:
            params_path = self._inputs_dir / "params.json"
            with open(params_path, "w", encoding="utf-8") as f:
                json.dump(inputs, f, indent=2, default=str)
        except OSError as e:
            logger.warning(f"Failed to save inputs: {e}")

    def complete(self, result: Optional[Dict[str, Any]] = None) -> None:
        """Mark the workspace run as completed."""
        self._manifest.status = "completed"
        self._manifest.completed_at = datetime.now(timezone.utc).isoformat()
        self.log_event("workspace_completed", {
            "artifact_count": len(self._artifacts),
        })
        self._write_manifest()

    def fail(self, error: str) -> None:
        """Mark the workspace run as failed."""
        self._manifest.status = "failed"
        self._manifest.completed_at = datetime.now(timezone.utc).isoformat()
        self._manifest.error = error
        self.log_event("workspace_failed", {"error": error})
        self._write_manifest()

    def _write_manifest(self) -> None:
        """Persist current manifest state to disk."""
        try:
            with open(self._manifest_path, "w", encoding="utf-8") as f:
                f.write(self._manifest.to_json())
        except OSError as e:
            logger.warning(f"Failed to write manifest: {e}")

    @staticmethod
    def _compute_sha256(path: Path, chunk_size: int = 65536) -> str:
        """Compute SHA-256 checksum of a file."""
        h = hashlib.sha256()
        try:
            with open(path, "rb") as f:
                while True:
                    chunk = f.read(chunk_size)
                    if not chunk:
                        break
                    h.update(chunk)
            return h.hexdigest()
        except OSError:
            return ""


# ---------------------------------------------------------------------------
# Workspace Manager
# ---------------------------------------------------------------------------

class WorkspaceManager:
    """Creates and manages per-execution workspaces.

    Usage:
        manager = WorkspaceManager(root_dir="output/workspaces")

        with manager.create("ib_toolkit", "quick_lbo_analysis", params={"ebitda": 50}) as ws:
            output_path = ws.get_output_path("xlsx")
            # ... generate file at output_path ...
            ws.register_artifact(output_path)
        # Workspace auto-completes on clean exit, auto-fails on exception
    """

    def __init__(self, root_dir: str | Path = DEFAULT_WORKSPACE_ROOT):
        self._root = Path(root_dir)

    @property
    def root_dir(self) -> Path:
        return self._root

    @contextmanager
    def create(
        self,
        skill_name: str,
        action: str,
        params: Optional[Dict[str, Any]] = None,
        run_id: Optional[str] = None,
        provenance: Optional[Dict[str, Any]] = None,
    ):
        """Create a workspace context manager.

        Args:
            skill_name: Name of the skill being executed
            action: Action being executed
            params: Input parameters (saved to inputs/)
            run_id: Optional run ID (auto-generated if not provided)
            provenance: Optional provenance metadata (parent_run_id, deal_id, etc.)

        Yields:
            Workspace instance
        """
        rid = run_id or str(uuid4())
        short_id = rid[:8]

        # Date-partitioned directory
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        workspace_name = f"{skill_name}_{action}_{short_id}"
        workspace_dir = self._root / date_str / workspace_name

        manifest = WorkspaceManifest(
            run_id=rid,
            skill_name=skill_name,
            action=action,
            inputs=params or {},
            provenance=provenance or {},
        )

        workspace = Workspace(workspace_dir, manifest)

        if params:
            workspace.save_inputs(params)

        try:
            yield workspace
            workspace.complete()
        except Exception as e:
            workspace.fail(str(e))
            raise

    def list_workspaces(
        self,
        date: Optional[str] = None,
        skill_name: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """List existing workspaces with optional filters.

        Args:
            date: Filter by date (YYYY-MM-DD)
            skill_name: Filter by skill name prefix

        Returns:
            List of workspace summary dicts
        """
        results = []
        if not self._root.exists():
            return results

        # Iterate date directories
        for date_dir in sorted(self._root.iterdir()):
            if not date_dir.is_dir():
                continue
            if date and date_dir.name != date:
                continue

            for ws_dir in sorted(date_dir.iterdir()):
                if not ws_dir.is_dir():
                    continue
                if skill_name and not ws_dir.name.startswith(skill_name):
                    continue

                manifest_path = ws_dir / "manifest.json"
                if manifest_path.exists():
                    try:
                        with open(manifest_path, "r", encoding="utf-8") as f:
                            manifest = json.load(f)
                        results.append({
                            "workspace_dir": str(ws_dir),
                            "date": date_dir.name,
                            **manifest,
                        })
                    except (json.JSONDecodeError, OSError):
                        results.append({
                            "workspace_dir": str(ws_dir),
                            "date": date_dir.name,
                            "error": "Could not read manifest",
                        })
                else:
                    results.append({
                        "workspace_dir": str(ws_dir),
                        "date": date_dir.name,
                        "error": "No manifest.json found",
                    })

        return results

    def get_workspace_by_run_id(self, run_id: str) -> Optional[Dict[str, Any]]:
        """Look up a workspace by its run ID.

        Args:
            run_id: Full or short (8-char) run ID

        Returns:
            Workspace manifest dict or None
        """
        for ws in self.list_workspaces():
            ws_run_id = ws.get("run_id", "")
            if ws_run_id == run_id or ws_run_id.startswith(run_id):
                return ws
        return None
