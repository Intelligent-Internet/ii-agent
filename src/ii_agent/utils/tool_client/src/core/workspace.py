"""Simple workspace manager for Docker environment."""

import os
from pathlib import Path


class WorkspaceManager:
    """Simple workspace manager that validates file paths within a workspace boundary."""
    
    def __init__(self, workspace_path="/workspace"):
        self.workspace_path = os.path.abspath(workspace_path)
        
    def get_workspace_path(self):
        """Return the workspace path."""
        return self.workspace_path
        
    def validate_boundary(self, path):
        """Check if the given path is within the workspace boundary."""
        try:
            abs_path = os.path.abspath(path)
            return abs_path.startswith(self.workspace_path)
        except Exception:
            return False