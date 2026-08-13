"""noVNC URL decoration helpers.

The sandbox image (`docker/sandbox/start-services.sh`) generates a fresh
random VNC password per container, writes it to `/tmp/.vnc_password`, and
configures `x11vnc -passwdfile`. Browsers reaching noVNC on port 6080 are
prompted for that password.

When a tool exposes port 6080 we transform the bare host URL into a
ready-to-click noVNC viewer URL with the password embedded as a query
param so the user is not left to dig the secret out of the container
filesystem. The credential is intentionally surfaced via the tool result
only — it is not persisted, logged, or exposed elsewhere.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from urllib.parse import quote

from ii_agent.core.logger import logger

if TYPE_CHECKING:
    from ii_agent.agents.sandboxes.base import Sandbox


NOVNC_PORT = 6080
VNC_PASSWORD_PATH = "/tmp/.vnc_password"


async def decorate_novnc_url(sandbox: "Sandbox", port: int, base_url: str) -> str:
    """If ``port`` is the noVNC port, return a viewer URL with the password
    embedded; otherwise return ``base_url`` unchanged.

    Failure to read the password is non-fatal — we still hand back a usable
    `/vnc.html?autoconnect=true` URL and the user can supply the password
    manually as a fallback.
    """
    if port != NOVNC_PORT:
        return base_url

    password = ""
    try:
        raw = await sandbox.run_command(
            f"cat {VNC_PASSWORD_PATH} 2>/dev/null || true",
            timeout=5,
        )
        password = (raw or "").strip()
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning(
            "Failed to read VNC password from sandbox for noVNC URL decoration: {}",
            exc,
        )

    suffix = "vnc.html?autoconnect=true&resize=remote"
    if password:
        suffix += f"&password={quote(password, safe='')}"

    sep = "" if base_url.endswith("/") else "/"
    return f"{base_url}{sep}{suffix}"
