"""
Plan state manager for managing plan mode transitions and persistence.

This module provides functionality to manage plan mode state, handle plan files,
and coordinate transitions between planning and implementation phases.
"""

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, asdict

from ii_agent.core.logger import logger


@dataclass
class PlanInfo:
    """Information about a plan."""
    plan_id: str
    name: str
    description: str
    created_at: str
    updated_at: str
    status: str  # 'planning', 'ready', 'in_progress', 'completed', 'cancelled'
    file_path: str
    progress: Dict[str, Any]  # Track implementation progress


class PlanStateManager:
    """Manages plan mode state and plan file operations."""
    
    def __init__(self, workspace_path: str):
        self.workspace_path = Path(workspace_path)
        self.plans_dir = self.workspace_path / "plans"
        self.plans_dir.mkdir(exist_ok=True)
        
        # Plan state file to track current plan mode
        self.state_file = self.plans_dir / ".plan_state.json"
        
        # Load existing state
        self.current_state = self._load_state()
    
    def _load_state(self) -> Dict[str, Any]:
        """Load current plan state from file."""
        if not self.state_file.exists():
            return {
                "plan_mode_active": False,
                "current_plan_id": None,
                "last_updated": None
            }
        
        try:
            with open(self.state_file, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading plan state: {e}")
            return {
                "plan_mode_active": False,
                "current_plan_id": None,
                "last_updated": None
            }
    
    def _save_state(self) -> None:
        """Save current plan state to file."""
        try:
            self.current_state["last_updated"] = datetime.now().isoformat()
            with open(self.state_file, 'w') as f:
                json.dump(self.current_state, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving plan state: {e}")
    
    def activate_plan_mode(self, plan_id: Optional[str] = None) -> None:
        """Activate plan mode with optional specific plan."""
        self.current_state["plan_mode_active"] = True
        if plan_id:
            self.current_state["current_plan_id"] = plan_id
        self._save_state()
        logger.info(f"Plan mode activated with plan: {plan_id}")
    
    def deactivate_plan_mode(self) -> None:
        """Deactivate plan mode."""
        self.current_state["plan_mode_active"] = False
        self.current_state["current_plan_id"] = None
        self._save_state()
        logger.info("Plan mode deactivated")
    
    def is_plan_mode_active(self) -> bool:
        """Check if plan mode is currently active."""
        return self.current_state.get("plan_mode_active", False)
    
    def get_current_plan_id(self) -> Optional[str]:
        """Get the current active plan ID."""
        return self.current_state.get("current_plan_id")
    
    def create_plan(self, name: str, description: str, content: str) -> PlanInfo:
        """Create a new plan file and return plan info."""
        plan_id = str(uuid.uuid4())[:8]  # Short ID for readability
        timestamp = datetime.now().isoformat()
        
        # Create plan filename
        safe_name = "".join(c for c in name if c.isalnum() or c in (' ', '-', '_')).rstrip()
        safe_name = safe_name.replace(' ', '_').lower()
        filename = f"{plan_id}_{safe_name}.md"
        file_path = self.plans_dir / filename
        
        # Create plan info
        plan_info = PlanInfo(
            plan_id=plan_id,
            name=name,
            description=description,
            created_at=timestamp,
            updated_at=timestamp,
            status="planning",
            file_path=str(file_path.relative_to(self.workspace_path)),
            progress={}
        )
        
        # Write plan content
        full_content = self._format_plan_content(plan_info, content)
        try:
            with open(file_path, 'w') as f:
                f.write(full_content)
            
            # Save plan metadata
            self._save_plan_metadata(plan_info)
            
            logger.info(f"Created plan: {name} ({plan_id})")
            return plan_info
            
        except Exception as e:
            logger.error(f"Error creating plan file: {e}")
            raise
    
    def _format_plan_content(self, plan_info: PlanInfo, content: str) -> str:
        """Format plan content with metadata header."""
        header = f"""---
plan_id: {plan_info.plan_id}
name: {plan_info.name}
description: {plan_info.description}
created_at: {plan_info.created_at}
updated_at: {plan_info.updated_at}
status: {plan_info.status}
---

# {plan_info.name}

**Description:** {plan_info.description}
**Created:** {plan_info.created_at}
**Status:** {plan_info.status}

---

{content}
"""
        return header
    
    def _save_plan_metadata(self, plan_info: PlanInfo) -> None:
        """Save plan metadata to index file."""
        index_file = self.plans_dir / ".plans_index.json"
        
        # Load existing index
        plans_index = {}
        if index_file.exists():
            try:
                with open(index_file, 'r') as f:
                    plans_index = json.load(f)
            except Exception as e:
                logger.warning(f"Error loading plans index: {e}")
        
        # Add/update plan info
        plans_index[plan_info.plan_id] = asdict(plan_info)
        
        # Save updated index
        try:
            with open(index_file, 'w') as f:
                json.dump(plans_index, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving plans index: {e}")
    
    def get_plan_info(self, plan_id: str) -> Optional[PlanInfo]:
        """Get plan information by ID."""
        index_file = self.plans_dir / ".plans_index.json"
        
        if not index_file.exists():
            return None
        
        try:
            with open(index_file, 'r') as f:
                plans_index = json.load(f)
            
            plan_data = plans_index.get(plan_id)
            if plan_data:
                return PlanInfo(**plan_data)
            return None
            
        except Exception as e:
            logger.error(f"Error loading plan info: {e}")
            return None
    
    def list_plans(self) -> List[PlanInfo]:
        """List all available plans."""
        index_file = self.plans_dir / ".plans_index.json"
        
        if not index_file.exists():
            return []
        
        try:
            with open(index_file, 'r') as f:
                plans_index = json.load(f)
            
            plans = []
            for plan_data in plans_index.values():
                plans.append(PlanInfo(**plan_data))
            
            # Sort by creation date (newest first)
            plans.sort(key=lambda p: p.created_at, reverse=True)
            return plans
            
        except Exception as e:
            logger.error(f"Error loading plans list: {e}")
            return []
    
    def update_plan_status(self, plan_id: str, status: str) -> bool:
        """Update plan status."""
        plan_info = self.get_plan_info(plan_id)
        if not plan_info:
            return False
        
        plan_info.status = status
        plan_info.updated_at = datetime.now().isoformat()
        
        self._save_plan_metadata(plan_info)
        return True
    
    def update_plan_progress(self, plan_id: str, progress: Dict[str, Any]) -> bool:
        """Update plan implementation progress."""
        plan_info = self.get_plan_info(plan_id)
        if not plan_info:
            return False
        
        plan_info.progress.update(progress)
        plan_info.updated_at = datetime.now().isoformat()
        
        self._save_plan_metadata(plan_info)
        return True
    
    def load_plan_content(self, plan_id: str) -> Optional[str]:
        """Load plan content from file."""
        plan_info = self.get_plan_info(plan_id)
        if not plan_info:
            return None
        
        file_path = self.workspace_path / plan_info.file_path
        if not file_path.exists():
            logger.error(f"Plan file not found: {file_path}")
            return None
        
        try:
            with open(file_path, 'r') as f:
                return f.read()
        except Exception as e:
            logger.error(f"Error reading plan file: {e}")
            return None
    
    def get_plans_directory(self) -> Path:
        """Get the plans directory path."""
        return self.plans_dir
    
    def cleanup_orphaned_plans(self) -> None:
        """Clean up plans that have missing files."""
        plans = self.list_plans()
        index_file = self.plans_dir / ".plans_index.json"
        
        if not index_file.exists():
            return
        
        try:
            with open(index_file, 'r') as f:
                plans_index = json.load(f)
            
            orphaned_ids = []
            for plan_id, plan_data in plans_index.items():
                file_path = self.workspace_path / plan_data['file_path']
                if not file_path.exists():
                    orphaned_ids.append(plan_id)
                    logger.warning(f"Removing orphaned plan: {plan_id}")
            
            # Remove orphaned entries
            for plan_id in orphaned_ids:
                del plans_index[plan_id]
            
            # Save updated index
            with open(index_file, 'w') as f:
                json.dump(plans_index, f, indent=2)
                
        except Exception as e:
            logger.error(f"Error cleaning up orphaned plans: {e}")