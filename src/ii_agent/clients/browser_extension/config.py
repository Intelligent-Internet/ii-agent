"""Browser-extension defaults.

The wire payload's ``core_tools`` / ``core_skills`` / ``connector`` IS
the user's request and is taken as-is. These ``BROWSER_EXTENSION_*``
sets are the **fallback defaults** the factory uses only when the
request leaves the matching key empty/null. They keep a sane baseline
for silent requests; populate them deliberately as needed.
"""

from __future__ import annotations

#: Fallback for ``requested_capabilities.core_tools`` (names from
#: :data:`TOOL_CLASS_MAP`) when the request doesn't specify any.
BROWSER_EXTENSION_DEFAULT_CORE_TOOLS: set[str] = set()

#: Fallback for ``requested_capabilities.core_skills`` (names from the
#: user's persisted ``SkillTool`` registry) when the request doesn't
#: specify any.
BROWSER_EXTENSION_DEFAULT_CORE_SKILLS: set[str] = set()

#: Fallback for ``requested_capabilities.connector`` (e.g. ``"github"``,
#: ``"google_drive"``) when the request doesn't specify one. The
#: connector still requires a wired ``connector_tool`` to instantiate.
BROWSER_EXTENSION_DEFAULT_CONNECTORS: set[str] = set()

#: Fallback system prompt — used only when the request doesn't ship its own.
DEFAULT_SYSTEM_PROMPT = (
    "You are an in-browser AI assistant in the ii-browser Chrome extension. "
    "Interact with the current page and selected text via available tools. "
    "Call tools to read or act on page data; never guess missing information. "
    "After each tool call, stop and wait for the result before continuing."
)

#: Heading for the client-defined skill catalog appended to the system prompt.
CLIENT_SKILL_HEADING = "Skills available in the ii-browser extension runtime:"

#: Tag used by the shared capability helpers when emitting warnings.
LOG_PREFIX = "browser_extension"

# Recognised keys inside ``requested_capabilities.client_prompt`` for the
# browser-extension client. Kept here (and not in :mod:`proxy_capabilities`)
# because the proxy layer is intentionally agnostic about which prompt
# fragments any particular client ships — each client subpackage decides
# what it understands.
CLIENT_PROMPT_MODE_KEY = "mode"
CLIENT_PROMPT_HEADING = "Capability mode for this turn:"
