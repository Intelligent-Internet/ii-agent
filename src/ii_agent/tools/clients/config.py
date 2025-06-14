from dataclasses import dataclass
from typing import Optional


@dataclass
class RemoteClientConfig:
    """Configuration for the RemoteClient."""

    mode: str = "local"  # "local" or "remote" or "e2b"
    container_id: Optional[str] = None
    server_url: Optional[str] = None
    timeout: float = 600.0
    ignore_indentation_for_str_replace: bool = False
    expand_tabs: bool = False
    default_shell: str = "/bin/bash"
    default_timeout: int = 600
    cwd: Optional[str] = None
