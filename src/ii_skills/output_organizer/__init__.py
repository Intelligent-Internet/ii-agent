"""
Output Organizer Skill

Auto-organize files into standardized deal folder structures.
Tags, categorizes, and retrieves outputs by deal, company, type, and date.

Wraps existing infrastructure:
- SkillStorage (shared/storage.py) for file operations
- DataStore (shared/datastore.py) for output/deal queries

Usage:
    skill = OutputOrganizerSkill()
    skill.initialize()

    # Create deal folder structure
    result = skill.execute("create_deal_folder", user_id="user1",
        deal_id="abc123", deal_name="Acme Corp LBO", deal_type="lbo")

    # Organize outputs into deal folder
    result = skill.execute("organize_outputs_by_deal", user_id="user1",
        deal_id="abc123")
"""

import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Any

from ii_skills import BaseSkill, register_skill

logger = logging.getLogger(__name__)

__version__ = "1.0.0"
__author__ = "II-Agent System"


# Standardized deal folder structures by deal type
DEAL_FOLDER_TEMPLATES = {
    "lbo": {
        "folders": [
            "01_cim",
            "02_models",
            "03_presentations",
            "04_due_diligence",
            "05_memos",
            "06_ic_materials",
        ],
        "description": "Leveraged Buyout deal folder",
    },
    "growth_equity": {
        "folders": [
            "01_research",
            "02_models",
            "03_presentations",
            "04_due_diligence",
            "05_memos",
        ],
        "description": "Growth Equity investment folder",
    },
    "add_on": {
        "folders": [
            "01_target_info",
            "02_models",
            "03_synergies",
            "04_presentations",
            "05_integration",
        ],
        "description": "Add-on / bolt-on acquisition folder",
    },
    "carve_out": {
        "folders": [
            "01_parent_info",
            "02_standalone_model",
            "03_tsa_analysis",
            "04_presentations",
            "05_transition",
        ],
        "description": "Carve-out transaction folder",
    },
    "general": {
        "folders": [
            "01_research",
            "02_analysis",
            "03_presentations",
            "04_memos",
        ],
        "description": "General analysis folder",
    },
}

# Mapping from output type / file extension to subfolder
OUTPUT_TYPE_TO_SUBFOLDER = {
    "excel": "02_models",
    "powerpoint": "03_presentations",
    "pdf": "01_cim",
    "json": "02_models",
    "csv": "02_models",
    "markdown": "05_memos",
    "html": "04_due_diligence",
}

MODULE_TO_SUBFOLDER = {
    # Model modules → models folder
    "lbo_model": "02_models",
    "dcf_model": "02_models",
    "operating_model": "02_models",
    "revenue_build": "02_models",
    "expense_build": "02_models",
    "debt_schedule": "02_models",
    "working_capital": "02_models",
    "returns_analysis": "02_models",
    "sensitivity": "02_models",
    "sources_uses": "02_models",
    "trading_comps": "02_models",
    "transaction_comps": "02_models",
    # Slide modules → presentations
    "company_deck": "03_presentations",
    "industry_slides": "03_presentations",
    "investment_deck": "03_presentations",
    "ic_presentation": "06_ic_materials",
    # DD modules
    "qoe": "04_due_diligence",
    "nwc_normalization": "04_due_diligence",
    "customer_quality": "04_due_diligence",
    "credit_analysis": "04_due_diligence",
    # Memo modules
    "ic_memo": "05_memos",
    "investment_memo": "05_memos",
    # Research
    "financial_extraction": "01_cim",
    "research_report": "01_research",
}


def _map_output_to_subfolder(
    output_type: Optional[str] = None,
    module_name: Optional[str] = None,
    file_name: Optional[str] = None,
) -> str:
    """Determine the appropriate subfolder for an output."""
    # Try module name first (most specific)
    if module_name and module_name in MODULE_TO_SUBFOLDER:
        return MODULE_TO_SUBFOLDER[module_name]

    # Try output type
    if output_type and output_type in OUTPUT_TYPE_TO_SUBFOLDER:
        return OUTPUT_TYPE_TO_SUBFOLDER[output_type]

    # Try file extension
    if file_name:
        ext = Path(file_name).suffix.lower()
        ext_map = {
            ".xlsx": "02_models",
            ".pptx": "03_presentations",
            ".pdf": "01_cim",
            ".json": "02_models",
            ".csv": "02_models",
            ".md": "05_memos",
            ".html": "04_due_diligence",
        }
        if ext in ext_map:
            return ext_map[ext]

    return "02_analysis"  # Default fallback


@register_skill
class OutputOrganizerSkill(BaseSkill):
    """Auto-organize skill outputs into standardized deal folders."""

    name = "output_organizer"
    version = __version__
    description = "Auto-organize files into deal folders with standardized structure"

    SKILL_DIR = Path(__file__).parent
    OUTPUT_DIR = SKILL_DIR / "output"

    def __init__(self, config: Optional[Dict] = None):
        super().__init__(config)
        self.OUTPUT_DIR.mkdir(exist_ok=True)

    def validate_config(self) -> List[str]:
        return []

    def get_capabilities(self) -> List[str]:
        return [
            "create_deal_folder",
            "organize_outputs_by_deal",
            "link_output_to_deal",
            "get_deal_files",
            "search_outputs",
            "get_recent_outputs",
            "export_deal_package",
        ]

    def execute(self, action: str, **kwargs) -> Dict:
        """Execute an output organizer action."""
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, self._execute_async(action, **kwargs))
                return future.result()
        return asyncio.run(self._execute_async(action, **kwargs))

    async def _execute_async(self, action: str, **kwargs) -> Dict:
        """Async action router."""
        actions = {
            "create_deal_folder": self._create_deal_folder,
            "organize_outputs_by_deal": self._organize_outputs_by_deal,
            "link_output_to_deal": self._link_output_to_deal,
            "get_deal_files": self._get_deal_files,
            "search_outputs": self._search_outputs,
            "get_recent_outputs": self._get_recent_outputs,
            "export_deal_package": self._export_deal_package,
        }

        handler = actions.get(action)
        if not handler:
            raise NotImplementedError(f"Action '{action}' not implemented")
        return await handler(**kwargs)

    # ------------------------------------------------------------------
    # Folder Management
    # ------------------------------------------------------------------

    async def _create_deal_folder(
        self,
        user_id: str,
        deal_id: str,
        deal_name: str,
        deal_type: str = "general",
        **kwargs,
    ) -> Dict:
        """Create a standardized deal folder structure.

        Stores folder metadata in the deal's state_data.
        """
        from ii_skills.shared.datastore import DataStore

        template = DEAL_FOLDER_TEMPLATES.get(deal_type, DEAL_FOLDER_TEMPLATES["general"])
        safe_name = deal_name.replace(" ", "_").replace("/", "-")
        folder_path = f"deals/{deal_id}_{safe_name}"

        folder_metadata = {
            "folder_path": folder_path,
            "deal_type": deal_type,
            "subfolders": template["folders"],
            "created_at": datetime.now(timezone.utc).isoformat(),
            "file_index": {},  # Maps subfolder → list of file records
        }

        store = DataStore()
        # Get current state_data and merge
        deal = await store.get_deal(deal_id)
        if deal:
            state_data = deal.get("state_data") or {}
            state_data["folder"] = folder_metadata
            await store.update_deal(deal_id, state_data=state_data)

        return {
            "success": True,
            "deal_id": deal_id,
            "folder_path": folder_path,
            "subfolders": template["folders"],
            "description": template["description"],
        }

    async def _organize_outputs_by_deal(
        self,
        user_id: str,
        deal_id: str,
        **kwargs,
    ) -> Dict:
        """Tag and organize all outputs for a deal's company into the deal folder."""
        from ii_skills.shared.datastore import DataStore

        store = DataStore()
        deal = await store.get_deal(deal_id)
        if not deal:
            return {"success": False, "error": f"Deal {deal_id} not found"}

        company_symbol = deal.get("company_symbol")
        folder_meta = (deal.get("state_data") or {}).get("folder")

        if not folder_meta:
            # Auto-create folder if none exists
            create_result = await self._create_deal_folder(
                user_id=user_id,
                deal_id=deal_id,
                deal_name=deal.get("deal_name", deal_id),
                deal_type=deal.get("deal_type", "general"),
            )
            folder_meta = {
                "folder_path": create_result["folder_path"],
                "subfolders": create_result["subfolders"],
                "file_index": {},
            }

        # Get all outputs that could belong to this deal
        outputs = await store.get_outputs(user_id=user_id, company_symbol=company_symbol, limit=200)

        organized = []
        for output in outputs:
            subfolder = _map_output_to_subfolder(
                output_type=output.get("output_type"),
                module_name=output.get("module_name"),
                file_name=output.get("file_name"),
            )

            organized_path = f"{folder_meta['folder_path']}/{subfolder}/{output.get('file_name', 'unknown')}"

            organized.append({
                "output_id": output["id"],
                "file_name": output.get("file_name"),
                "original_type": output.get("output_type"),
                "subfolder": subfolder,
                "organized_path": organized_path,
            })

            # Update file index in folder metadata
            if subfolder not in folder_meta.get("file_index", {}):
                folder_meta.setdefault("file_index", {})[subfolder] = []
            folder_meta["file_index"][subfolder].append({
                "output_id": output["id"],
                "file_name": output.get("file_name"),
                "output_type": output.get("output_type"),
                "organized_at": datetime.now(timezone.utc).isoformat(),
            })

        # Save updated folder index
        state_data = deal.get("state_data") or {}
        state_data["folder"] = folder_meta
        await store.update_deal(deal_id, state_data=state_data)

        return {
            "success": True,
            "deal_id": deal_id,
            "files_organized": len(organized),
            "organized": organized,
        }

    async def _link_output_to_deal(
        self,
        user_id: str,
        deal_id: str,
        output_id: str,
        subfolder: Optional[str] = None,
        **kwargs,
    ) -> Dict:
        """Associate an existing output with a deal."""
        from ii_skills.shared.datastore import DataStore

        store = DataStore()
        deal = await store.get_deal(deal_id)
        if not deal:
            return {"success": False, "error": f"Deal {deal_id} not found"}

        # Get output info
        outputs = await store.get_outputs(user_id=user_id, limit=200)
        output = next((o for o in outputs if o["id"] == output_id), None)
        if not output:
            return {"success": False, "error": f"Output {output_id} not found"}

        # Determine subfolder
        if not subfolder:
            subfolder = _map_output_to_subfolder(
                output_type=output.get("output_type"),
                module_name=output.get("module_name"),
                file_name=output.get("file_name"),
            )

        # Update deal state_data
        state_data = deal.get("state_data") or {}
        folder_meta = state_data.get("folder", {"file_index": {}})
        folder_meta.setdefault("file_index", {}).setdefault(subfolder, []).append({
            "output_id": output_id,
            "file_name": output.get("file_name"),
            "output_type": output.get("output_type"),
            "linked_at": datetime.now(timezone.utc).isoformat(),
        })
        state_data["folder"] = folder_meta
        await store.update_deal(deal_id, state_data=state_data)

        return {
            "success": True,
            "deal_id": deal_id,
            "output_id": output_id,
            "subfolder": subfolder,
        }

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    async def _get_deal_files(
        self,
        user_id: str,
        deal_id: str,
        subfolder: Optional[str] = None,
        **kwargs,
    ) -> Dict:
        """List all files for a deal, organized by subfolder."""
        from ii_skills.shared.datastore import DataStore

        store = DataStore()
        deal = await store.get_deal(deal_id)
        if not deal:
            return {"success": False, "error": f"Deal {deal_id} not found"}

        folder_meta = (deal.get("state_data") or {}).get("folder", {})
        file_index = folder_meta.get("file_index", {})

        if subfolder:
            files = file_index.get(subfolder, [])
            return {
                "success": True,
                "deal_id": deal_id,
                "subfolder": subfolder,
                "files": files,
                "count": len(files),
            }

        # Return all subfolders
        total_files = sum(len(v) for v in file_index.values())
        return {
            "success": True,
            "deal_id": deal_id,
            "folder_path": folder_meta.get("folder_path"),
            "subfolders": file_index,
            "total_files": total_files,
        }

    async def _search_outputs(
        self,
        user_id: str,
        company_symbol: Optional[str] = None,
        output_type: Optional[str] = None,
        skill_name: Optional[str] = None,
        limit: int = 50,
        **kwargs,
    ) -> Dict:
        """Find outputs by company, type, or skill."""
        from ii_skills.shared.datastore import DataStore

        store = DataStore()
        outputs = await store.get_outputs(
            user_id=user_id,
            skill_name=skill_name,
            output_type=output_type,
            company_symbol=company_symbol,
            limit=limit,
        )

        return {
            "success": True,
            "outputs": outputs,
            "count": len(outputs),
        }

    async def _get_recent_outputs(
        self,
        user_id: str,
        limit: int = 20,
        **kwargs,
    ) -> Dict:
        """List recent unorganized outputs."""
        from ii_skills.shared.datastore import DataStore

        store = DataStore()
        outputs = await store.get_outputs(user_id=user_id, limit=limit)

        return {
            "success": True,
            "outputs": outputs,
            "count": len(outputs),
        }

    async def _export_deal_package(
        self,
        user_id: str,
        deal_id: str,
        **kwargs,
    ) -> Dict:
        """Collect all deal files into a summary manifest."""
        from ii_skills.shared.datastore import DataStore

        store = DataStore()
        deal = await store.get_deal(deal_id)
        if not deal:
            return {"success": False, "error": f"Deal {deal_id} not found"}

        folder_meta = (deal.get("state_data") or {}).get("folder", {})

        # Get actual output records for all indexed files
        file_index = folder_meta.get("file_index", {})
        all_output_ids = []
        for subfolder_files in file_index.values():
            for f in subfolder_files:
                all_output_ids.append(f.get("output_id"))

        outputs = await store.get_outputs(user_id=user_id, limit=200)
        output_map = {o["id"]: o for o in outputs}

        package = {
            "deal": {
                "id": deal["id"],
                "name": deal.get("deal_name"),
                "company": deal.get("company_symbol"),
                "type": deal.get("deal_type"),
                "status": deal.get("status"),
            },
            "folder_path": folder_meta.get("folder_path"),
            "contents": {},
        }

        for subfolder, files in file_index.items():
            package["contents"][subfolder] = []
            for f in files:
                output = output_map.get(f.get("output_id"))
                package["contents"][subfolder].append({
                    "file_name": f.get("file_name"),
                    "output_type": f.get("output_type"),
                    "storage_url": output.get("storage_url") if output else None,
                    "local_path": output.get("local_path") if output else None,
                })

        # Save manifest
        safe_name = deal.get("deal_name", deal_id).replace(" ", "_").replace("/", "-")
        manifest_path = self.OUTPUT_DIR / f"{safe_name}_manifest.json"
        with open(manifest_path, "w") as f:
            json.dump(package, f, indent=2, default=str)

        return {
            "success": True,
            "deal_id": deal_id,
            "manifest_path": str(manifest_path),
            "total_files": sum(len(v) for v in package["contents"].values()),
        }


def get_output_organizer(config: Optional[Dict] = None) -> OutputOrganizerSkill:
    """Get an instance of the Output Organizer skill."""
    skill = OutputOrganizerSkill(config)
    skill.initialize()
    return skill
