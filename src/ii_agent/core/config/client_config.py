from typing import Optional
from pydantic import BaseModel


class ClientConfig(BaseModel):
    """Configuration for the client."""

    server_url: Optional[str] = None
    timeout: float = 600.0
    ignore_indentation_for_str_replace: bool = False
    expand_tabs: bool = False
    default_shell: str = "/bin/bash"
    default_timeout: int = 600
    cwd: Optional[str] = None

    def update(self, settings: "ClientConfig"):
        pass
