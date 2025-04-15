from pathlib import Path
import os
import json
from typing import Dict, List, Optional, Any


class FileManager:
    """
    A manager for handling file paths and metadata for plans and content.
    
    This class persists file information even after dialog clearing,
    maintaining context about previously created files.
    """
    
    def __init__(self, workspace_root: Path):
        """Initialize the file manager.
        
        Args:
            workspace_root: The root path of the workspace
        """
        self.workspace_root = workspace_root
        
        # Store metadata about managed files
        self.managed_files = {
            "plans": {},       # plan_id -> {"path": filepath, "metadata": {...}}
            "content": {},     # content_id -> {"path": filepath, "metadata": {...}}
            "active_plan": None,  # Currently active plan ID
            "active_content": None  # Currently active content ID
        }
        
        # Create a metadata directory if it doesn't exist
        self.metadata_dir = workspace_root / ".agent_metadata"
        self.metadata_file = self.metadata_dir / "file_manager.json"
        
        os.makedirs(self.metadata_dir, exist_ok=True)
        
        # Load existing metadata if available
        self._load_metadata()
    
    def _load_metadata(self):
        """Load metadata from disk if it exists."""
        if os.path.exists(self.metadata_file):
            try:
                with open(self.metadata_file, 'r') as f:
                    self.managed_files = json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                print(f"Error loading file manager metadata: {str(e)}")
    
    def _save_metadata(self):
        """Save current metadata to disk."""
        try:
            with open(self.metadata_file, 'w') as f:
                json.dump(self.managed_files, f, indent=2)
        except IOError as e:
            print(f"Error saving file manager metadata: {str(e)}")
    
    def register_plan(self, plan_id: str, plan_path: str, metadata: Optional[Dict] = None) -> str:
        """Register a plan file with the manager.
        
        Args:
            plan_id: Unique identifier for the plan
            plan_path: Path to the plan file
            metadata: Optional metadata about the plan
            
        Returns:
            The absolute path to the plan file
        """
        abs_path = self._ensure_absolute_path(plan_path)
        
        self.managed_files["plans"][plan_id] = {
            "path": str(abs_path),
            "metadata": metadata or {}
        }
        
        self._save_metadata()
        return str(abs_path)
    
    def register_content(self, content_id: str, content_path: str, metadata: Optional[Dict] = None) -> str:
        """Register a content file with the manager.
        
        Args:
            content_id: Unique identifier for the content
            content_path: Path to the content file
            metadata: Optional metadata about the content
            
        Returns:
            The absolute path to the content file
        """
        abs_path = self._ensure_absolute_path(content_path)
        
        self.managed_files["content"][content_id] = {
            "path": str(abs_path),
            "metadata": metadata or {}
        }
        
        self._save_metadata()
        return str(abs_path)
    
    def set_active_plan(self, plan_id: str) -> None:
        """Set the currently active plan.
        
        Args:
            plan_id: ID of the plan to set as active
        """
        if plan_id in self.managed_files["plans"]:
            self.managed_files["active_plan"] = plan_id
            self._save_metadata()
        else:
            raise ValueError(f"Plan with ID {plan_id} does not exist")
    
    def set_active_content(self, content_id: str) -> None:
        """Set the currently active content.
        
        Args:
            content_id: ID of the content to set as active
        """
        if content_id in self.managed_files["content"]:
            self.managed_files["active_content"] = content_id
            self._save_metadata()
        else:
            raise ValueError(f"Content with ID {content_id} does not exist")
    
    def get_plan_path(self, plan_id: Optional[str] = None) -> Optional[str]:
        """Get the path for a plan.
        
        Args:
            plan_id: ID of the plan to get the path for. If None, uses active plan.
            
        Returns:
            The path to the plan file, or None if not found
        """
        target_id = plan_id or self.managed_files["active_plan"]
        if not target_id or target_id not in self.managed_files["plans"]:
            return None
        
        return self.managed_files["plans"][target_id]["path"]
    
    def get_content_path(self, content_id: Optional[str] = None) -> Optional[str]:
        """Get the path for content.
        
        Args:
            content_id: ID of the content to get the path for. If None, uses active content.
            
        Returns:
            The path to the content file, or None if not found
        """
        target_id = content_id or self.managed_files["active_content"]
        if not target_id or target_id not in self.managed_files["content"]:
            return None
        
        return self.managed_files["content"][target_id]["path"]
    
    def get_plan_metadata(self, plan_id: Optional[str] = None) -> Optional[Dict]:
        """Get metadata for a plan.
        
        Args:
            plan_id: ID of the plan to get metadata for. If None, uses active plan.
            
        Returns:
            The metadata for the plan, or None if not found
        """
        target_id = plan_id or self.managed_files["active_plan"]
        if not target_id or target_id not in self.managed_files["plans"]:
            return None
        
        return self.managed_files["plans"][target_id]["metadata"]
    
    def get_content_metadata(self, content_id: Optional[str] = None) -> Optional[Dict]:
        """Get metadata for content.
        
        Args:
            content_id: ID of the content to get metadata for. If None, uses active content.
            
        Returns:
            The metadata for the content, or None if not found
        """
        target_id = content_id or self.managed_files["active_content"]
        if not target_id or target_id not in self.managed_files["content"]:
            return None
        
        return self.managed_files["content"][target_id]["metadata"]
    
    def update_plan_metadata(self, metadata: Dict, plan_id: Optional[str] = None) -> None:
        """Update metadata for a plan.
        
        Args:
            metadata: New metadata to merge with existing metadata
            plan_id: ID of the plan to update metadata for. If None, uses active plan.
        """
        target_id = plan_id or self.managed_files["active_plan"]
        if not target_id or target_id not in self.managed_files["plans"]:
            raise ValueError(f"Plan with ID {target_id} does not exist")
        
        # Merge the new metadata with existing metadata
        self.managed_files["plans"][target_id]["metadata"].update(metadata)
        self._save_metadata()
    
    def update_content_metadata(self, metadata: Dict, content_id: Optional[str] = None) -> None:
        """Update metadata for content.
        
        Args:
            metadata: New metadata to merge with existing metadata
            content_id: ID of the content to update metadata for. If None, uses active content.
        """
        target_id = content_id or self.managed_files["active_content"]
        if not target_id or target_id not in self.managed_files["content"]:
            raise ValueError(f"Content with ID {target_id} does not exist")
        
        # Merge the new metadata with existing metadata
        self.managed_files["content"][target_id]["metadata"].update(metadata)
        self._save_metadata()
    
    def list_plans(self) -> List[Dict]:
        """List all registered plans.
        
        Returns:
            A list of plans with their IDs, paths, and metadata
        """
        return [
            {"id": plan_id, **plan_data}
            for plan_id, plan_data in self.managed_files["plans"].items()
        ]
    
    def list_content(self) -> List[Dict]:
        """List all registered content.
        
        Returns:
            A list of content items with their IDs, paths, and metadata
        """
        return [
            {"id": content_id, **content_data}
            for content_id, content_data in self.managed_files["content"].items()
        ]
    
    def _ensure_absolute_path(self, path: str) -> Path:
        """Ensure a path is absolute, converting relative paths to absolute.
        
        Args:
            path: Path string
            
        Returns:
            Absolute Path object
        """
        path_obj = Path(path)
        if not path_obj.is_absolute():
            return (self.workspace_root / path_obj).resolve()
        return path_obj.resolve() 