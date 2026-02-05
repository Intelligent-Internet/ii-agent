"""
Case Study Auto-Trigger — single-command case study setup.

When you receive a case study (CIM PDF, financial model, or just a company name),
this module chains the full setup: create deal folder → notify paths → scaffold.

No Tier 1/Tier 2 files are modified.

Usage:
    from ii_skills.shared.case_trigger import CaseStudyTrigger

    trigger = CaseStudyTrigger()
    result = trigger.start_case(
        company_name="Acme Corp",
        case_type="lbo",
        cim_path="/path/to/cim.pdf",  # optional
    )
    print(result.summary)  # Formatted terminal summary
"""

from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Deal folder templates (mirrors output_organizer but standalone)
# ---------------------------------------------------------------------------

DEAL_FOLDER_TEMPLATES = {
    "lbo": [
        "01_cim",
        "02_models",
        "03_presentations",
        "04_due_diligence",
        "05_memos",
        "06_ic_materials",
    ],
    "growth_equity": [
        "01_research",
        "02_models",
        "03_presentations",
        "04_due_diligence",
        "05_memos",
    ],
    "add_on": [
        "01_target_info",
        "02_models",
        "03_synergies",
        "04_presentations",
        "05_integration",
    ],
    "carve_out": [
        "01_parent_info",
        "02_standalone_model",
        "03_tsa_analysis",
        "04_presentations",
        "05_transition",
    ],
    "general": [
        "01_research",
        "02_analysis",
        "03_presentations",
        "04_memos",
    ],
}


# ---------------------------------------------------------------------------
# CaseSetupResult — everything the user needs to know
# ---------------------------------------------------------------------------

@dataclass
class CaseSetupResult:
    """Result of a case study auto-trigger."""

    success: bool = True
    company_name: str = ""
    case_type: str = ""
    deal_folder: str = ""
    subfolders: List[str] = field(default_factory=list)
    subfolder_paths: Dict[str, str] = field(default_factory=dict)
    files_copied: List[Dict[str, str]] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    created_at: str = ""

    @property
    def summary(self) -> str:
        """Human-readable summary for terminal display."""
        lines = []
        status = "OK" if self.success else "FAILED"
        lines.append(f"  Case Study Setup [{status}]")
        lines.append(f"  {'=' * 55}")
        lines.append(f"  Company:    {self.company_name}")
        lines.append(f"  Type:       {self.case_type}")
        lines.append(f"  Created:    {self.created_at}")
        lines.append(f"  {'─' * 55}")
        lines.append(f"  Deal Folder:")
        lines.append(f"    {self.deal_folder}")
        lines.append(f"  {'─' * 55}")
        lines.append(f"  Subfolders:")
        for sf in self.subfolders:
            path = self.subfolder_paths.get(sf, "")
            lines.append(f"    {sf:.<30} {path}")

        if self.files_copied:
            lines.append(f"  {'─' * 55}")
            lines.append(f"  Files Placed:")
            for f in self.files_copied:
                lines.append(f"    {f['filename']:.<30} -> {f['subfolder']}")

        if self.errors:
            lines.append(f"  {'─' * 55}")
            lines.append(f"  Warnings:")
            for e in self.errors:
                lines.append(f"    - {e}")

        lines.append(f"  {'=' * 55}")
        return "\n".join(lines)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "company_name": self.company_name,
            "case_type": self.case_type,
            "deal_folder": self.deal_folder,
            "subfolders": self.subfolders,
            "subfolder_paths": self.subfolder_paths,
            "files_copied": self.files_copied,
            "errors": self.errors,
            "created_at": self.created_at,
        }


# ---------------------------------------------------------------------------
# CaseStudyTrigger
# ---------------------------------------------------------------------------

class CaseStudyTrigger:
    """
    One-command case study setup.

    Creates the deal folder structure under output/cases/ and optionally
    copies input files (CIM PDFs, financial models) into the right subfolders.

    All output goes to Tier 3 (output/cases/). No Tier 1 or Tier 2 touched.
    """

    def __init__(self, base_dir: Optional[str] = None):
        """
        Args:
            base_dir: Root directory for case folders.
                      Defaults to output/cases/ relative to the ii-agent repo root.
        """
        if base_dir:
            self.base_dir = Path(base_dir)
        else:
            # Find ii-agent repo root
            here = Path(__file__).resolve().parent
            repo_root = here.parent.parent.parent  # shared -> ii_skills -> src -> ii-agent
            self.base_dir = repo_root / "output" / "cases"

    def start_case(
        self,
        company_name: str,
        case_type: str = "lbo",
        cim_path: Optional[str] = None,
        model_path: Optional[str] = None,
        additional_files: Optional[Dict[str, str]] = None,
        timeframe: Optional[str] = None,
    ) -> CaseSetupResult:
        """
        Create a full case study workspace.

        Args:
            company_name: Company or deal name (e.g., "Acme Corp")
            case_type: Deal type — lbo, growth_equity, add_on, carve_out, general
            cim_path: Path to CIM PDF (auto-placed in 01_cim or 01_research)
            model_path: Path to financial model Excel (auto-placed in 02_models)
            additional_files: Dict of {filename: source_path} to copy into the deal folder
            timeframe: Optional timeframe hint (e.g., "24-hour", "48-hour")

        Returns:
            CaseSetupResult with all paths and status.
        """
        result = CaseSetupResult(
            company_name=company_name,
            case_type=case_type,
            created_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        )

        # Normalize case type
        case_type = case_type.lower().replace("-", "_").replace(" ", "_")
        if case_type not in DEAL_FOLDER_TEMPLATES:
            case_type = "general"
        result.case_type = case_type

        # Build folder name: YYYY-MM-DD_company_name_case_type
        date_str = datetime.now().strftime("%Y-%m-%d")
        safe_name = company_name.lower().replace(" ", "_").replace("/", "-")
        folder_name = f"{date_str}_{safe_name}_{case_type}"
        deal_folder = self.base_dir / folder_name

        # Create main folder and subfolders
        try:
            deal_folder.mkdir(parents=True, exist_ok=True)
            result.deal_folder = str(deal_folder)

            subfolders = DEAL_FOLDER_TEMPLATES[case_type]
            result.subfolders = subfolders

            for sf in subfolders:
                sf_path = deal_folder / sf
                sf_path.mkdir(exist_ok=True)
                result.subfolder_paths[sf] = str(sf_path)

        except OSError as e:
            result.success = False
            result.errors.append(f"Failed to create folder structure: {e}")
            return result

        # Write case metadata
        self._write_case_config(deal_folder, result, timeframe)

        # Copy CIM if provided
        if cim_path:
            self._place_file(
                result,
                source_path=cim_path,
                target_subfolder=self._find_subfolder(subfolders, ["01_cim", "01_research", "01_target_info", "01_parent_info"]),
                deal_folder=deal_folder,
            )

        # Copy financial model if provided
        if model_path:
            self._place_file(
                result,
                source_path=model_path,
                target_subfolder=self._find_subfolder(subfolders, ["02_models", "02_analysis", "02_standalone_model"]),
                deal_folder=deal_folder,
            )

        # Copy additional files
        if additional_files:
            for filename, source_path in additional_files.items():
                # Determine target subfolder by extension
                ext = Path(filename).suffix.lower()
                if ext in (".pdf", ".docx", ".doc"):
                    target = self._find_subfolder(subfolders, ["01_cim", "01_research"])
                elif ext in (".xlsx", ".xls", ".xlsm"):
                    target = self._find_subfolder(subfolders, ["02_models", "02_analysis"])
                elif ext in (".pptx", ".ppt"):
                    target = self._find_subfolder(subfolders, ["03_presentations", "04_presentations"])
                else:
                    target = subfolders[0] if subfolders else ""
                self._place_file(result, source_path, target, deal_folder)

        logger.info(
            "Case study created: %s at %s (%d subfolders, %d files placed)",
            company_name, deal_folder, len(subfolders), len(result.files_copied),
        )

        return result

    def list_cases(self, limit: int = 20) -> List[Dict[str, Any]]:
        """List existing case folders, most recent first."""
        if not self.base_dir.exists():
            return []

        cases = []
        for folder in sorted(self.base_dir.iterdir(), reverse=True):
            if folder.is_dir() and not folder.name.startswith("."):
                # Count files
                file_count = sum(1 for _ in folder.rglob("*") if _.is_file())
                subfolders = [d.name for d in folder.iterdir() if d.is_dir()]
                cases.append({
                    "folder_name": folder.name,
                    "path": str(folder),
                    "subfolders": subfolders,
                    "file_count": file_count,
                })
                if len(cases) >= limit:
                    break

        return cases

    # --- Internal helpers ---

    def _find_subfolder(self, subfolders: List[str], preferences: List[str]) -> str:
        """Find the first matching subfolder from preference list."""
        for pref in preferences:
            if pref in subfolders:
                return pref
        return subfolders[0] if subfolders else ""

    def _place_file(
        self,
        result: CaseSetupResult,
        source_path: str,
        target_subfolder: str,
        deal_folder: Path,
    ) -> None:
        """Copy a file into the target subfolder."""
        src = Path(source_path)
        if not src.exists():
            result.errors.append(f"File not found: {source_path}")
            return

        target_dir = deal_folder / target_subfolder
        target_dir.mkdir(parents=True, exist_ok=True)
        dest = target_dir / src.name

        try:
            shutil.copy2(str(src), str(dest))
            result.files_copied.append({
                "filename": src.name,
                "source": str(src),
                "destination": str(dest),
                "subfolder": target_subfolder,
            })
        except OSError as e:
            result.errors.append(f"Failed to copy {src.name}: {e}")

    def _write_case_config(
        self,
        deal_folder: Path,
        result: CaseSetupResult,
        timeframe: Optional[str],
    ) -> None:
        """Write case_config.yml metadata file."""
        import json

        config = {
            "company_name": result.company_name,
            "case_type": result.case_type,
            "created_at": result.created_at,
            "timeframe": timeframe or "not specified",
            "subfolders": result.subfolders,
            "status": "active",
        }

        config_path = deal_folder / "case_config.json"
        try:
            config_path.write_text(json.dumps(config, indent=2))
        except OSError as e:
            result.errors.append(f"Failed to write case config: {e}")
